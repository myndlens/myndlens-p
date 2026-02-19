"""Write policy — controls when memory writes are allowed.

Writes ONLY allowed:
  - Post-execution (confirmed action completed)
  - Via explicit user confirmation

NEVER allowed:
  - Policy writes
  - Silent preference mutation
  - LLM-initiated self-learning without user signal
"""
import logging

logger = logging.getLogger(__name__)


def can_write(trigger: str) -> bool:
    """Check if a write trigger is allowed."""
    ALLOWED_TRIGGERS = {
        "post_execution",       # Action completed successfully
        "user_confirmation",    # User explicitly approved
        "onboarding",           # Initial setup
        "ONBOARDING_AUTO",      # Automated onboarding data import
    }

    DENIED_TRIGGERS = {
        "llm_inference",        # LLM decided on its own
        "policy_mutation",      # Changing rules
        "silent_update",        # No user signal
    }

    if trigger in DENIED_TRIGGERS:
        logger.warning("[WritePolicy] DENIED write trigger: %s", trigger)
        return False

    if trigger in ALLOWED_TRIGGERS:
        return True

    logger.warning("[WritePolicy] Unknown trigger: %s (denied by default)", trigger)
    return False
