"""Guardrails Engine — B8.

Continuous evaluation of intents against safety constraints.
Checked as thought capture progresses, not just at execution.

Gates:
  - Ambiguity >30% → Silence/Clarify (no draft promoted)
  - Harm detection → tactful refusal
  - Policy violation → immediate block
  - Emotional load high → stability cooldown
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from dimensions.engine import DimensionState
from l1.scout import L1DraftObject

logger = logging.getLogger(__name__)


class GuardrailResult(str, Enum):
    PASS = "PASS"
    SILENCE = "SILENCE"       # Ambiguity too high
    CLARIFY = "CLARIFY"       # Need more info
    REFUSE = "REFUSE"         # Policy violation / harm
    COOLDOWN = "COOLDOWN"     # Emotional load too high


@dataclass
class GuardrailCheck:
    result: GuardrailResult
    reason: str
    nudge: Optional[str] = None  # Tactful message for user
    block_execution: bool = False


# ---- Blocked patterns (simple keyword-based for now) ----
# Note: Use word boundaries or full phrases to avoid false positives
# e.g., "hackernews" should not trigger "hack" block
_HARM_PATTERNS = [
    "hack into", "hack the", "hacking", "steal", "illegal", "kill", "attack", "exploit",
    "password", "credentials", "bypass security",
]

_POLICY_VIOLATIONS = [
    "send money to myself", "transfer all funds",
    "delete all", "wipe everything", "override safety",
]


def check_guardrails(
    transcript: str,
    dimensions: Optional[DimensionState] = None,
    l1_draft: Optional[L1DraftObject] = None,
) -> GuardrailCheck:
    """Run all guardrail checks. Returns the most restrictive result."""

    # 1. Ambiguity gate (§11.1)
    if dimensions and dimensions.b_set.ambiguity > 0.30:
        return GuardrailCheck(
            result=GuardrailResult.SILENCE,
            reason=f"Ambiguity score {dimensions.b_set.ambiguity:.0%} exceeds 30% threshold",
            nudge="I want to make sure I understand correctly. Could you tell me a bit more?",
            block_execution=True,
        )

    # 2. Emotional load cooldown (§11.3)
    if dimensions and dimensions.b_set.emotional_load > 0.7:
        return GuardrailCheck(
            result=GuardrailResult.COOLDOWN,
            reason=f"Emotional load {dimensions.b_set.emotional_load:.0%} exceeds stability threshold",
            nudge="Let's take a moment. Would you like to review this before proceeding?",
            block_execution=True,
        )

    # 3. Harm detection
    lower = transcript.lower()
    for pattern in _HARM_PATTERNS:
        if pattern in lower:
            return GuardrailCheck(
                result=GuardrailResult.REFUSE,
                reason=f"Potential harmful intent detected: pattern='{pattern}'",
                nudge="I can't help with that request. Is there something else I can assist with?",
                block_execution=True,
            )

    # 4. Policy violations
    for pattern in _POLICY_VIOLATIONS:
        if pattern in lower:
            return GuardrailCheck(
                result=GuardrailResult.REFUSE,
                reason=f"Policy violation detected: pattern='{pattern}'",
                nudge="That action isn't permitted. How else can I help?",
                block_execution=True,
            )

    # 5. Low confidence gate
    if l1_draft and l1_draft.hypotheses:
        top = l1_draft.hypotheses[0]
        if top.confidence < 0.4:
            return GuardrailCheck(
                result=GuardrailResult.CLARIFY,
                reason=f"L1 confidence too low: {top.confidence:.2f}",
                nudge="I'm not quite sure what you'd like to do. Could you rephrase that?",
                block_execution=True,
            )

    # All gates passed
    return GuardrailCheck(
        result=GuardrailResult.PASS,
        reason="All guardrails passed",
        block_execution=False,
    )
