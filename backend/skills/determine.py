"""Skill Determination — LLM decides what skills a mandate needs.

The LLM receives:
  1. The definitive mandate (intent + dimensions + actions)
  2. The skill library as reference examples
  3. Its job: determine which skills execute each action, or create new ones

Zero hardcoding. The LLM figures out the mapping.
If no existing skill fits, the LLM designs a new one.
"""
import json
import logging
import time
from typing import Any, Dict, List

from config.settings import get_settings
from config.feature_flags import is_mock_llm
from prompting.orchestrator import PromptOrchestrator
from prompting.types import PromptContext, PromptPurpose, PromptMode
from prompting.storage.mongo import save_prompt_snapshot

logger = logging.getLogger(__name__)


async def determine_skills(
    session_id: str,
    user_id: str,
    mandate: Dict[str, Any],
) -> Dict[str, Any]:
    """LLM determines which skills are needed to execute each mandate action.

    Reads the skill library as reference. Decides:
    - Which existing skills to use
    - Which skills need adaptation
    - Which new skills need to be created
    """
    settings = get_settings()
    start = time.monotonic()

    if is_mock_llm() or not settings.EMERGENT_LLM_KEY:
        return _mock_skills(mandate)

    # Load skill library as reference
    skill_library = await _load_skill_library_summary()

    # Build the mandate summary for the LLM
    actions_summary = []
    for action in mandate.get("actions", []):
        dims = action.get("dimensions", {})
        dim_summary = {k: v.get("value", "?") if isinstance(v, dict) else v
                       for k, v in dims.items()
                       if isinstance(v, dict) and v.get("value") and v.get("value") != "missing"}
        actions_summary.append({
            "action": action.get("action", ""),
            "priority": action.get("priority", ""),
            "dimensions": dim_summary,
        })

    task = (
        f"MANDATE TO EXECUTE:\n"
        f"  Intent: {mandate.get('intent', '')}\n"
        f"  Summary: {mandate.get('mandate_summary', '')}\n"
        f"  Actions:\n" +
        "\n".join(f"    - {a['action']} [{a['priority']}]: {json.dumps(a['dimensions'])}" for a in actions_summary) +
        f"\n\nAVAILABLE SKILL LIBRARY (reference):\n{skill_library}\n\n"
        "For EACH action in the mandate, determine:\n"
        "1. Can an EXISTING skill from the library handle it? → use it\n"
        "2. Can an existing skill be ADAPTED with minor changes? → adapt it\n"
        "3. Does a NEW skill need to be CREATED? → design it\n\n"
        "Output JSON:\n"
        "{\n"
        "  \"skill_plan\": [{\n"
        "    \"action\": str (which mandate action),\n"
        "    \"decision\": \"use_existing\" | \"adapt\" | \"create_new\",\n"
        "    \"skill_name\": str (existing skill name, or new name),\n"
        "    \"from_library\": str (base skill from library, if adapting),\n"
        "    \"reason\": str (why this skill),\n"
        "    \"adaptation_notes\": str (what to change, if adapting),\n"
        "    \"execution_order\": int (1=first, 2=second...),\n"
        "    \"depends_on\": [str] (actions that must complete first)\n"
        "  }],\n"
        "  \"execution_strategy\": \"sequential\" | \"parallel\" | \"mixed\",\n"
        "  \"risk_assessment\": str,\n"
        "  \"estimated_complexity\": \"simple\" | \"moderate\" | \"complex\"\n"
        "}"
    )

    orchestrator = PromptOrchestrator()
    ctx = PromptContext(
        purpose=PromptPurpose.PLAN,
        mode=PromptMode.INTERACTIVE,
        session_id=session_id,
        user_id=user_id,
        transcript=mandate.get("mandate_summary", ""),
        task_description=task,
    )
    artifact, report = orchestrator.build(ctx)
    await save_prompt_snapshot(report)

    from prompting.llm_gateway import call_llm
    response = await call_llm(
        artifact=artifact,
        call_site_id="SKILL_DETERMINER",
        model_provider="gemini",
        model_name="gemini-2.0-flash",
        session_id=f"skill-det-{session_id}",
    )

    latency_ms = (time.monotonic() - start) * 1000
    result = _parse_skill_plan(response)
    result["_meta"] = {"latency_ms": round(latency_ms, 1)}

    logger.info(
        "[SkillDet] session=%s intent=%s skills=%d strategy=%s complexity=%s %.0fms",
        session_id, mandate.get("intent", ""),
        len(result.get("skill_plan", [])),
        result.get("execution_strategy", "?"),
        result.get("estimated_complexity", "?"),
        latency_ms,
    )
    return result


async def _load_skill_library_summary() -> str:
    """Load the skill library and format as a compact reference for the LLM."""
    import json as _json
    from pathlib import Path

    lib_path = Path(__file__).parent.parent / "assets" / "skills-library.json"
    if not lib_path.exists():
        return "(no skill library available)"

    with open(lib_path) as f:
        lib = _json.load(f)

    lines = []
    for cat in lib.get("categories", []):
        cat_name = cat.get("name", "")
        for skill in cat.get("skills", []):
            name = skill.get("name", "")
            desc = skill.get("description", "")[:80]
            tools = skill.get("required_tools", "")[:40]
            lines.append(f"  [{cat_name}] {name}: {desc} (tools: {tools})")

    return "\n".join(lines)


def _parse_skill_plan(response: str) -> Dict[str, Any]:
    try:
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("[SkillDet] Parse failed: %s", e)
        return {"skill_plan": [], "execution_strategy": "unknown",
                "risk_assessment": "parse_error", "estimated_complexity": "unknown"}


def _mock_skills(mandate: Dict[str, Any]) -> Dict[str, Any]:
    return {"skill_plan": [], "execution_strategy": "unknown",
            "risk_assessment": "mock", "estimated_complexity": "unknown",
            "_meta": {"source": "mock"}}
