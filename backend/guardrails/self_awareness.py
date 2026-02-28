"""MyndLens Self-Awareness — LLM-powered meta-question handling.

Detects, interprets, and answers questions about MyndLens itself using
a single Gemini Flash call. No regex, no keyword matching, no string brittle.

The LLM receives our brand knowledge base and generates natural, contextual
spoken responses adapted to exactly how the user phrased the question.
"""
import logging
import time

logger = logging.getLogger(__name__)

# Brand knowledge base — the LLM uses this as context to generate responses.
# These are NOT hardcoded responses. The LLM interprets the user's question
# and composes a natural spoken answer using this knowledge.
MYNDLENS_KNOWLEDGE = """
ABOUT MYNDLENS:
MyndLens is a voice-first Personal Cognitive Proxy. You speak your thoughts — even fragmented ones — and MyndLens listens, understands, and builds a clear intent. It checks with your Living Digital Self — your personal intelligence built from your contacts, conversations, and patterns — to fill in the gaps. Then it creates a structured mandate and asks for your approval before executing anything. It uses OpenClaw as its execution engine and never acts without permission.

WHY MYNDLENS IS UNIQUE (3 things):
1. Context Aware — captures fragmented thoughts into clear intent. No typing, no menus.
2. Living Digital Self — knows your relationships, active conversations, pending commitments. Doesn't ask you to repeat context you've shared with others.
3. Sovereign execution — data stays under your control, confidential contacts are biometric-locked, never executes without explicit approval.

WHY TRUST MYNDLENS:
Trust is built into the architecture. Digital Self is continuously processed on device by default. Raw messages are never stored after processing. You control what's confidential — sealed behind biometric auth. Never executes without approval. OpenClaw workspace is isolated per user. Your data never leaves the device. Delete everything anytime from Settings.

WHY MYNDLENS CAN'T BE REPLACED (8 reasons):
1. Living Digital Self — learned from WhatsApp, email, calendar. Starting over means losing years of relationship intelligence.
2. Proactive — thinks for you. Tells you what needs attention. Siri waits. Alexa waits. MyndLens thinks.
3. Context-aware execution — zero questions for well-understood tasks.
4. Sovereign & private — data never leaves device, confidential contacts biometric-locked.
5. Cross-contact intelligence — sees patterns across all conversations, connects dots.
6. Voice-first, thought-first — understands messy human thinking, fragments into intent.
7. Relationship memory — remembers tension with vendor, promise Ravi made, sister's plans. Switch and it's all gone.
8. Gets better every day — after 6 months, knows your world better than any human assistant. That accumulated intelligence is irreplaceable.

WHAT MYNDLENS CAN DO:
Code (build, run, test apps), Communication (emails, WhatsApp context, follow-ups), Research (information, news, trends), Travel (plan trips using preferences from conversations), Tasks (manage to-dos, track commitments, reminders). Always learning from Digital Self.

WHO BUILT MYNDLENS:
Built by ObeGee — focused on sovereign AI execution. Vision: your AI assistant works for you, knows your context, never acts without permission.
"""


async def check_self_awareness_llm(transcript: str, user_first_name: str = "") -> str | None:
    """LLM-powered meta-question detection and response.

    Returns a natural spoken response if the transcript is about MyndLens itself.
    Returns None if it's a regular command/intent (not a meta-question).
    """
    if not transcript or len(transcript.split()) < 2:
        return None

    start = time.monotonic()

    prompt = f"""You are MyndLens, a voice-first Personal Cognitive Proxy.

A user just said: "{transcript}"

TASK: Determine if this is a question ABOUT MyndLens itself (how it works, why it's unique, trust, capabilities, who built it, why it can't be replaced, etc).

If YES — compose a warm, confident, spoken response using the knowledge below. Speak naturally as MyndLens in first person. Keep it concise (3-5 sentences for simple questions, up to 8 for "why can't you be replaced"). Address the user as "{user_first_name}" once at the start if the name is provided.

If NO — this is a regular command or intent (like "book a flight", "write code", "send email"). Reply with exactly: NOT_META_QUESTION

KNOWLEDGE BASE:
{MYNDLENS_KNOWLEDGE}

RULES:
- Respond as if speaking out loud (TTS-friendly, no bullet points, no markdown)
- Never say "I'm an AI" or "I'm a language model"
- Be confident and warm, like a trusted friend explaining themselves
- If the question is about privacy/trust, emphasize "data never leaves your device"
- If about uniqueness, lead with "Context Aware" and "Living Digital Self"
- Match the tone to the question — casual for casual, detailed for detailed"""

    try:
        from mcp.ds_server import call_tool
        result = await call_tool("search_memory", {
            "user_id": "system",
            "query": transcript,
            "n_results": 0,
        })
    except Exception:
        pass

    try:
        from prompting.llm_gateway import call_llm
        from prompting.types import PromptArtifact

        artifact = PromptArtifact(
            prompt_id=f"self-awareness",
            messages=[
                {"role": "system", "content": "You are MyndLens. Answer meta-questions about yourself. Reply NOT_META_QUESTION for regular commands."},
                {"role": "user", "content": prompt},
            ],
            total_tokens_est=len(prompt) // 4,
        )

        response = await call_llm(
            artifact=artifact,
            call_site_id="SELF_AWARENESS",
            model_provider="gemini",
            model_name="gemini-2.0-flash",
            session_id="self-awareness",
        )

        latency_ms = (time.monotonic() - start) * 1000

        if not response:
            return None

        text = response.strip()

        # Check if LLM classified it as NOT a meta-question
        if "NOT_META_QUESTION" in text:
            logger.info("[SELF_AWARENESS] NOT meta-question (%.0fms): '%s'", latency_ms, transcript[:40])
            return None

        logger.info("[SELF_AWARENESS] LLM response (%.0fms): '%s' → '%s'",
                    latency_ms, transcript[:40], text[:60])
        return text

    except Exception as e:
        logger.warning("[SELF_AWARENESS] LLM failed: %s", str(e)[:60])
        return None
