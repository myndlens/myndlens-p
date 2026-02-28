"""Input sanitizer — strips prompt injection patterns from user text.

Applied BEFORE any user text is embedded in LLM prompts.
Defends against: instruction override, role hijacking, system prompt extraction.
"""
import re
import logging

logger = logging.getLogger(__name__)

# Patterns that attempt to override LLM instructions
_INJECTION_PATTERNS = [
    re.compile(r'ignore\s+(all\s+)?previous\s+instructions?', re.IGNORECASE),
    re.compile(r'forget\s+(all\s+)?previous\s+(instructions?|context)', re.IGNORECASE),
    re.compile(r'you\s+are\s+now\s+', re.IGNORECASE),
    re.compile(r'new\s+instructions?\s*:', re.IGNORECASE),
    re.compile(r'system\s*:\s*', re.IGNORECASE),
    re.compile(r'<\s*system\s*>', re.IGNORECASE),
    re.compile(r'\[INST\]', re.IGNORECASE),
    re.compile(r'\[/INST\]', re.IGNORECASE),
    re.compile(r'###\s*(system|instruction|prompt)', re.IGNORECASE),
    re.compile(r'act\s+as\s+(if\s+you\s+are\s+)?a\s+different', re.IGNORECASE),
    re.compile(r'pretend\s+(you\s+are|to\s+be)', re.IGNORECASE),
    re.compile(r'reveal\s+(your|the)\s+(system\s+)?prompt', re.IGNORECASE),
    re.compile(r'output\s+(your|the)\s+(system\s+)?prompt', re.IGNORECASE),
    re.compile(r'what\s+(is|are)\s+your\s+(system\s+)?instructions?', re.IGNORECASE),
]


def sanitize_for_llm(text: str, context: str = "") -> str:
    """Sanitize user text before embedding in LLM prompts.

    - Strips known injection patterns
    - Truncates to reasonable length
    - Logs if injection attempt detected

    Returns sanitized text. Never raises.
    """
    if not text:
        return text

    original = text
    detected = False

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            text = pattern.sub('[filtered]', text)
            detected = True

    # Truncate overly long inputs (prevent token stuffing)
    max_len = 2000
    if len(text) > max_len:
        text = text[:max_len] + '...'
        detected = True

    if detected:
        logger.warning("[SANITIZER] Injection attempt detected context=%s original='%s'",
                      context, original[:80])

    return text
