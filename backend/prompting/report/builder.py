"""Prompt Report Builder — produces immutable PromptReport per call.

Mandatory: every LLM call must produce a report.
"""
from typing import Dict, List

from prompting.types import (
    PromptPurpose,
    PromptMode,
    PromptReport,
    SectionStatus,
    SectionOutput,
)


class PromptReportBuilder:
    """Builds an immutable PromptReport from section outputs."""

    def __init__(self, prompt_id: str, purpose: PromptPurpose, mode: PromptMode):
        self._prompt_id = prompt_id
        self._purpose = purpose
        self._mode = mode
        self._section_statuses: List[SectionStatus] = []
        self._token_estimates: Dict[str, int] = {}
        self._allowed_tools: List[str] = []

    def add_section(
        self,
        output: SectionOutput,
    ) -> None:
        """Record a section's status."""
        self._section_statuses.append(
            SectionStatus(
                section_id=output.section_id,
                included=output.included,
                gating_reason=output.gating_reason,
                cache_class=output.cache_class if output.included else None,
                tokens_est=output.tokens_est if output.included else 0,
                priority=output.priority if output.included else 0,
            )
        )
        if output.included:
            self._token_estimates[output.section_id.value] = output.tokens_est

    def add_excluded_section(
        self, section_id, gating_reason: str
    ) -> None:
        """Record a section that was excluded by policy."""
        self._section_statuses.append(
            SectionStatus(
                section_id=section_id,
                included=False,
                gating_reason=gating_reason,
            )
        )

    def set_tools(self, tools: List[str]) -> None:
        self._allowed_tools = tools

    def build(
        self, stable_hash: str, volatile_hash: str
    ) -> PromptReport:
        """Produce the immutable report."""
        return PromptReport(
            prompt_id=self._prompt_id,
            purpose=self._purpose,
            mode=self._mode,
            sections=self._section_statuses,
            token_estimates=self._token_estimates,
            budget_used=sum(self._token_estimates.values()),
            allowed_tools=self._allowed_tools,
            stable_hash=stable_hash,
            volatile_hash=volatile_hash,
        )
