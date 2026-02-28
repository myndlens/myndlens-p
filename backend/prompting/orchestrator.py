"""Prompt Orchestrator — single entry point per LLM call.

Stateless. Takes PromptContext, produces PromptArtifact + PromptReport.
No LLM calls happen here — this is assembly only.

Usage:
    orchestrator = PromptOrchestrator()
    artifact, report = orchestrator.build(ctx)
    # artifact.messages → pass to LLM provider
    # report → persist to prompt_snapshots
"""
import logging
import uuid
from typing import List, Tuple

from prompting.types import (
    PromptContext,
    PromptArtifact,
    PromptReport,
    PromptPurpose,
    SectionID,
    SectionOutput,
    CacheClass,
)
from prompting.policy.engine import PolicyEngine, policy_engine
from prompting.registry import SectionRegistry, build_default_registry
from prompting.report.builder import PromptReportBuilder
from prompting.hashing import compute_stable_hash, compute_volatile_hash

logger = logging.getLogger(__name__)


class PromptOrchestrator:
    """Assembles prompts from context, policy, and section generators."""

    def __init__(
        self,
        registry: SectionRegistry | None = None,
        engine: PolicyEngine | None = None,
    ):
        self._registry = registry or build_default_registry()
        self._engine = engine or policy_engine

    def build(self, ctx: PromptContext) -> Tuple[PromptArtifact, PromptReport]:
        """Build a PromptArtifact + PromptReport from context.
        
        This is the ONLY entry point for prompt construction.
        Applies per-user adjustments when user_adjustments is provided.
        """
        prompt_id = str(uuid.uuid4())
        report_builder = PromptReportBuilder(prompt_id, ctx.purpose, ctx.mode)

        # Extract user adjustments
        adj = ctx.user_adjustments or {}
        preferred_sections = set(adj.get("preferred_sections", []))
        excluded_sections = set(adj.get("excluded_sections", []))
        token_modifier = adj.get("token_budget_modifier", 1.0)
        verbosity = adj.get("verbosity", "normal")

        # 1. Resolve which sections to include/exclude
        section_outputs: List[SectionOutput] = []

        for section_id in SectionID:
            # User-level exclusion overrides policy (only for optional sections)
            if section_id.value in excluded_sections:
                report_builder.add_excluded_section(section_id, "Excluded by user profile")
                continue

            included, gating_reason = self._engine.should_include_section(
                ctx.purpose, section_id
            )

            # User-level preference: promote optional sections that the user benefits from
            if not included and section_id.value in preferred_sections:
                # Only promote if not banned by policy
                policy = self._engine.get_policy(ctx.purpose)
                if section_id not in policy.banned_sections and self._registry.has(section_id):
                    included = True
                    gating_reason = None

            if included and self._registry.has(section_id):
                output = self._registry.generate(section_id, ctx)
                # Apply verbosity adjustment to token estimates
                if verbosity == "detailed" and output.cache_class == CacheClass.VOLATILE:
                    output.tokens_est = int(output.tokens_est * 1.3)
                elif verbosity == "concise" and output.cache_class == CacheClass.VOLATILE:
                    output.tokens_est = int(output.tokens_est * 0.7)
                output.included = True
                section_outputs.append(output)
                report_builder.add_section(output)
            else:
                reason = gating_reason or "Generator not registered"
                if included and not self._registry.has(section_id):
                    reason = f"Generator not registered for {section_id.value}"
                report_builder.add_excluded_section(section_id, reason)

        # 2. Filter tools through policy
        allowed_tools = self._engine.get_allowed_tools(
            ctx.purpose, ctx.available_tools
        )
        report_builder.set_tools(allowed_tools)

        # 3. Sort sections by priority and assemble messages
        section_outputs.sort(key=lambda s: s.priority)
        messages = self._assemble_messages(section_outputs, ctx)

        # 4. Compute hashes
        stable_hash = compute_stable_hash(section_outputs)
        volatile_hash = compute_volatile_hash(section_outputs)

        # 5. Build artifact — apply token budget modifier + enforce hard cap
        raw_tokens = sum(s.tokens_est for s in section_outputs if s.included)
        adjusted_tokens = int(raw_tokens * token_modifier)

        # Token budget enforcement: trim optional sections if over cap
        MAX_TOKENS = {
            PromptPurpose.THOUGHT_TO_INTENT: 4000,
            PromptPurpose.DIMENSIONS_EXTRACT: 4000,
            PromptPurpose.VERIFY: 3000,
            PromptPurpose.SAFETY_GATE: 2000,
        }
        cap = MAX_TOKENS.get(ctx.purpose, 5000)
        trimmed_sections = []
        if adjusted_tokens > cap:
            # Trim optional/volatile sections by lowest priority first
            optional = [s for s in section_outputs if s.included and s.cache_class == CacheClass.VOLATILE]
            optional.sort(key=lambda s: s.tokens_est)
            for s in optional:
                if adjusted_tokens <= cap:
                    break
                s.included = False
                adjusted_tokens -= s.tokens_est
                trimmed_sections.append(s.section_id.value)
                messages = [m for m in messages if s.section_id.value not in str(m.get("content", ""))[:50]]
            if trimmed_sections:
                logger.info("[ORCHESTRATOR] Trimmed %d sections to meet %d token cap: %s",
                           len(trimmed_sections), cap, trimmed_sections)

        artifact = PromptArtifact(
            prompt_id=prompt_id,
            purpose=ctx.purpose,
            mode=ctx.mode,
            messages=messages,
            sections_included=[s.section_id for s in section_outputs if s.included],
            sections_excluded=[
                sid for sid in SectionID
                if sid not in [s.section_id for s in section_outputs]
            ],
            stable_hash=stable_hash,
            volatile_hash=volatile_hash,
            total_tokens_est=adjusted_tokens,
        )

        # 6. Build report
        report = report_builder.build(stable_hash, volatile_hash)

        adj_info = ""
        if token_modifier != 1.0 or verbosity != "normal" or preferred_sections or excluded_sections:
            adj_info = f" adj=[mod={token_modifier} verb={verbosity} pref={len(preferred_sections)} excl={len(excluded_sections)}]"

        logger.info(
            "Prompt built: id=%s purpose=%s included=%d excluded=%d tokens=%d stable=%s%s",
            prompt_id,
            ctx.purpose.value,
            len(artifact.sections_included),
            len(artifact.sections_excluded),
            artifact.total_tokens_est,
            stable_hash[:12],
            adj_info,
        )

        return artifact, report

    def _assemble_messages(
        self, sections: List[SectionOutput], ctx: PromptContext
    ) -> List[dict]:
        """Assemble role-tagged messages from section outputs."""
        # System message: concatenate all stable + semistable sections
        system_parts = []
        user_parts = []

        for s in sections:
            if not s.included:
                continue
            if isinstance(s.content, list):
                # Already role-tagged
                for msg in s.content:
                    if msg.get("role") == "user":
                        user_parts.append(msg["content"])
                    else:
                        system_parts.append(msg.get("content", ""))
            else:
                if s.cache_class in (CacheClass.STABLE, CacheClass.SEMISTABLE):
                    system_parts.append(s.content)
                else:
                    user_parts.append(s.content)

        messages = []
        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        if user_parts:
            messages.append({"role": "user", "content": "\n\n".join(user_parts)})

        return messages
