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
    PromptPurpose,
    PromptArtifact,
    PromptReport,
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
        """
        prompt_id = str(uuid.uuid4())
        report_builder = PromptReportBuilder(prompt_id, ctx.purpose, ctx.mode)

        # 1. Resolve which sections to include/exclude
        section_outputs: List[SectionOutput] = []

        for section_id in SectionID:
            included, gating_reason = self._engine.should_include_section(
                ctx.purpose, section_id
            )

            if included and self._registry.has(section_id):
                # Generate section content
                output = self._registry.generate(section_id, ctx)
                output.included = True
                section_outputs.append(output)
                report_builder.add_section(output)
            else:
                # Section excluded or not registered
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

        # 5. Build artifact
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
            total_tokens_est=sum(s.tokens_est for s in section_outputs if s.included),
        )

        # 6. Build report
        report = report_builder.build(stable_hash, volatile_hash)

        logger.info(
            "Prompt built: id=%s purpose=%s included=%d excluded=%d tokens=%d stable=%s",
            prompt_id,
            ctx.purpose.value,
            len(artifact.sections_included),
            len(artifact.sections_excluded),
            artifact.total_tokens_est,
            stable_hash[:12],
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
