"""Policy Engine — authoritative gatekeeper for prompt construction.

Decides per purpose:
  - which sections are allowed / required / banned
  - which tools are visible
  - token budgets

Policy decisions are explainable and logged.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set

from prompting.types import PromptPurpose, SectionID

logger = logging.getLogger(__name__)


@dataclass
class PurposePolicy:
    """Policy for a specific purpose."""
    required_sections: FrozenSet[SectionID]
    optional_sections: FrozenSet[SectionID]
    banned_sections: FrozenSet[SectionID]
    allowed_tools: FrozenSet[str]  # empty = no tools
    token_budget: int = 4096


# ---- Canonical Purpose Policies (Locked) ----

_POLICIES: Dict[PromptPurpose, PurposePolicy] = {
    PromptPurpose.THOUGHT_TO_INTENT: PurposePolicy(
        required_sections=frozenset({
            SectionID.IDENTITY_ROLE,
            SectionID.PURPOSE_CONTRACT,
            SectionID.OUTPUT_SCHEMA,
            SectionID.TASK_CONTEXT,
        }),
        optional_sections=frozenset({
            SectionID.MEMORY_RECALL_SNIPPETS,
        }),
        banned_sections=frozenset({
            SectionID.TOOLING,
            SectionID.SKILLS_INDEX,
            SectionID.WORKSPACE_BOOTSTRAP,
            SectionID.SAFETY_GUARDRAILS,
        }),
        allowed_tools=frozenset(),
        token_budget=4096,
    ),
    PromptPurpose.DIMENSIONS_EXTRACT: PurposePolicy(
        required_sections=frozenset({
            SectionID.IDENTITY_ROLE,
            SectionID.PURPOSE_CONTRACT,
            SectionID.OUTPUT_SCHEMA,
            SectionID.TASK_CONTEXT,
        }),
        optional_sections=frozenset({
            SectionID.MEMORY_RECALL_SNIPPETS,
        }),
        banned_sections=frozenset({
            SectionID.TOOLING,
            SectionID.SKILLS_INDEX,
            SectionID.WORKSPACE_BOOTSTRAP,
            SectionID.RUNTIME_CAPABILITIES,
            SectionID.DIMENSIONS_INJECTED,
            SectionID.CONFLICTS_SUMMARY,
            SectionID.SAFETY_GUARDRAILS,
        }),
        allowed_tools=frozenset(),  # NO tools for extraction
        token_budget=4096,
    ),
    PromptPurpose.PLAN: PurposePolicy(
        required_sections=frozenset({
            SectionID.IDENTITY_ROLE,
            SectionID.PURPOSE_CONTRACT,
            SectionID.TASK_CONTEXT,
            SectionID.DIMENSIONS_INJECTED,
            SectionID.SAFETY_GUARDRAILS,
        }),
        optional_sections=frozenset({
            SectionID.MEMORY_RECALL_SNIPPETS,
            SectionID.CONFLICTS_SUMMARY,
        }),
        banned_sections=frozenset({
            SectionID.TOOLING,
        }),
        allowed_tools=frozenset(),
        token_budget=8192,
    ),
    PromptPurpose.EXECUTE: PurposePolicy(
        required_sections=frozenset({
            SectionID.IDENTITY_ROLE,
            SectionID.PURPOSE_CONTRACT,
            SectionID.TOOLING,
            SectionID.SAFETY_GUARDRAILS,
            SectionID.TASK_CONTEXT,
            SectionID.DIMENSIONS_INJECTED,
        }),
        optional_sections=frozenset({
            SectionID.RUNTIME_CAPABILITIES,
            SectionID.CONFLICTS_SUMMARY,
        }),
        banned_sections=frozenset({
            SectionID.MEMORY_RECALL_SNIPPETS,
            SectionID.OUTPUT_SCHEMA,
        }),
        allowed_tools=frozenset(),  # populated per-call
        token_budget=8192,
    ),
    PromptPurpose.VERIFY: PurposePolicy(
        required_sections=frozenset({
            SectionID.IDENTITY_ROLE,
            SectionID.PURPOSE_CONTRACT,
            SectionID.TASK_CONTEXT,
        }),
        optional_sections=frozenset({
            SectionID.CONFLICTS_SUMMARY,
            SectionID.DIMENSIONS_INJECTED,
            SectionID.MEMORY_RECALL_SNIPPETS,
        }),
        banned_sections=frozenset({
            SectionID.TOOLING,
            SectionID.SKILLS_INDEX,
            SectionID.SAFETY_GUARDRAILS,
        }),
        allowed_tools=frozenset(),
        token_budget=4096,
    ),
    PromptPurpose.SAFETY_GATE: PurposePolicy(
        required_sections=frozenset({
            SectionID.IDENTITY_ROLE,
            SectionID.PURPOSE_CONTRACT,
            SectionID.SAFETY_GUARDRAILS,
            SectionID.TASK_CONTEXT,
        }),
        optional_sections=frozenset({
            SectionID.DIMENSIONS_INJECTED,
        }),
        banned_sections=frozenset({
            SectionID.TOOLING,
            SectionID.SKILLS_INDEX,
            SectionID.WORKSPACE_BOOTSTRAP,
        }),
        allowed_tools=frozenset(),
        token_budget=2048,
    ),
    PromptPurpose.SUMMARIZE: PurposePolicy(
        required_sections=frozenset({
            SectionID.IDENTITY_ROLE,
            SectionID.PURPOSE_CONTRACT,
            SectionID.TASK_CONTEXT,
        }),
        optional_sections=frozenset(),
        banned_sections=frozenset({
            SectionID.TOOLING,
            SectionID.SKILLS_INDEX,
            SectionID.SAFETY_GUARDRAILS,
        }),
        allowed_tools=frozenset(),
        token_budget=2048,
    ),
    PromptPurpose.SUBAGENT_TASK: PurposePolicy(
        required_sections=frozenset({
            SectionID.IDENTITY_ROLE,
            SectionID.PURPOSE_CONTRACT,
            SectionID.TASK_CONTEXT,
        }),
        optional_sections=frozenset({
            SectionID.TOOLING,
            SectionID.SAFETY_GUARDRAILS,
        }),
        banned_sections=frozenset({
            SectionID.WORKSPACE_BOOTSTRAP,
            SectionID.SKILLS_INDEX,
        }),
        allowed_tools=frozenset(),  # minimal
        token_budget=2048,
    ),
}


class PolicyEngine:
    """Authoritative gatekeeper for prompt construction."""

    def get_policy(self, purpose: PromptPurpose) -> PurposePolicy:
        """Get the policy for a given purpose."""
        policy = _POLICIES.get(purpose)
        if policy is None:
            raise ValueError(f"No policy defined for purpose: {purpose}")
        return policy

    def should_include_section(
        self, purpose: PromptPurpose, section_id: SectionID
    ) -> tuple[bool, Optional[str]]:
        """Determine if a section should be included.
        
        Returns (included: bool, gating_reason: str | None).
        """
        policy = self.get_policy(purpose)

        if section_id in policy.banned_sections:
            return False, f"Banned for purpose {purpose.value}"

        if section_id in policy.required_sections:
            return True, None

        if section_id in policy.optional_sections:
            return True, None  # optional = included if available

        # Not mentioned in any set = excluded by default
        return False, f"Not in required/optional set for purpose {purpose.value}"

    def get_allowed_tools(
        self, purpose: PromptPurpose, requested_tools: List[str]
    ) -> List[str]:
        """Filter tools through policy. Returns only allowed tools."""
        policy = self.get_policy(purpose)
        if not policy.allowed_tools:
            # If policy allows no specific tools, return empty
            # (EXECUTE will need per-call tool injection later)
            if purpose == PromptPurpose.EXECUTE:
                return requested_tools  # EXECUTE gets requested tools
            return []
        return [t for t in requested_tools if t in policy.allowed_tools]

    def get_token_budget(self, purpose: PromptPurpose) -> int:
        """Get the token budget for a purpose."""
        return self.get_policy(purpose).token_budget


# Singleton
policy_engine = PolicyEngine()
