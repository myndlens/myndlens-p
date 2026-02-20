"""Intent RL Multi-Iteration Runner — trains the Intent Extraction Engine.

After each iteration:
  1. Collect failures
  2. Store corrections in `intent_corrections` collection (PROMPT ENGINE, not Digital Self)
  3. Update the LEARNED_EXAMPLES prompt section cache
  4. Next iteration: L1 Scout prompt now includes few-shot corrections
  5. Track accuracy progression
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from intent_rl.dataset_v2 import INTENT_DATASET_V2
from intent_rl.seed_digital_self import RL_USER_ID

logger = logging.getLogger(__name__)


_rl_loop_state = {
    "running": False,
    "current_iteration": 0,
    "total_iterations": 0,
    "iterations": [],
    "started_at": None,
    "completed_at": None,
}


def get_rl_loop_state() -> dict:
    return _rl_loop_state


async def run_rl_loop(n_iterations: int = 10, delay_between_calls: float = 0.3) -> str:
    global _rl_loop_state
    if _rl_loop_state["running"]:
        return "already_running"

    _rl_loop_state = {
        "running": True,
        "current_iteration": 0,
        "total_iterations": n_iterations,
        "iterations": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }
    asyncio.create_task(_execute_rl_loop(n_iterations, delay_between_calls))
    return "started"


async def _execute_rl_loop(n_iterations: int, delay: float) -> None:
    global _rl_loop_state

    from l1.scout import run_l1_scout
    from core.database import get_db
    from prompting.sections.standard.learned_examples import update_correction_cache
    from intent_rl.runner_v2 import (
        _check_intent_match, _check_sub_intents, _check_entity_resolution,
        _INTENT_KEYWORDS,
    )

    db = get_db()
    dataset = INTENT_DATASET_V2

    for iteration in range(1, n_iterations + 1):
        _rl_loop_state["current_iteration"] = iteration
        logger.info("[RL Loop] === Iteration %d/%d ===", iteration, n_iterations)

        # ── Load existing corrections into prompt cache BEFORE this run ──
        existing = await db.intent_corrections.find(
            {}, {"_id": 0}
        ).sort("created_at", -1).limit(10).to_list(length=10)
        update_correction_cache(existing)
        logger.info("[RL Loop] Loaded %d corrections into prompt engine", len(existing))

        # ── Run all 40 cases ──
        results = []
        for case in dataset:
            session_id = f"rl_loop_i{iteration}_{case['id']}"
            try:
                draft = await run_l1_scout(
                    session_id=session_id,
                    user_id=RL_USER_ID,
                    transcript=case["broken_thoughts"],
                )
                all_hyps = [{"hypothesis": h.hypothesis, "action_class": h.intent,
                             "confidence": h.confidence, "dimensions": h.dimension_suggestions}
                            for h in draft.hypotheses]

                top = draft.hypotheses[0] if draft.hypotheses else None
                extracted_hyp = top.hypothesis if top else ""
                extracted_class = top.action_class if top else "NONE"

                intent_match = _check_intent_match(extracted_hyp, extracted_class, all_hyps, case["main_intent"])
                _, sub_cov = _check_sub_intents(extracted_hyp, all_hyps, case["sub_intents"])
                _, ent_cov = _check_entity_resolution(extracted_hyp, all_hyps, case.get("expected_entities", []))

                results.append({
                    "case_id": case["id"], "main_intent": case["main_intent"],
                    "intent_match": intent_match, "sub_coverage": sub_cov, "entity_coverage": ent_cov,
                    "extracted_hypothesis": extracted_hyp, "extracted_class": extracted_class,
                    "broken_thoughts": case["broken_thoughts"],
                })
            except Exception as e:
                logger.error("[RL Loop] Case %d failed: %s", case["id"], e)
                results.append({
                    "case_id": case["id"], "main_intent": case["main_intent"],
                    "intent_match": False, "sub_coverage": 0.0, "entity_coverage": 0.0,
                    "extracted_hypothesis": str(e), "extracted_class": "ERROR",
                    "broken_thoughts": case["broken_thoughts"],
                })

            await asyncio.sleep(delay)

        # ── Score ──
        correct = sum(1 for r in results if r["intent_match"])
        total = len(results)
        intent_acc = correct / total if total else 0
        avg_sub = sum(r["sub_coverage"] for r in results) / total if total else 0
        avg_ent = sum(r["entity_coverage"] for r in results) / total if total else 0
        failures = [r for r in results if not r["intent_match"]]

        # ── Store corrections in INTENT ENGINE (not Digital Self) ──
        corrections_added = 0
        for f in failures:
            correction_doc = {
                "fragment": f["broken_thoughts"][:100],
                "correct_intent": f["main_intent"],
                "wrong_class": f["extracted_class"],
                "wrong_hypothesis": f["extracted_hypothesis"][:100],
                "iteration": iteration,
                "case_id": f["case_id"],
                "created_at": datetime.now(timezone.utc),
            }
            # Upsert — don't duplicate corrections for the same case
            await db.intent_corrections.replace_one(
                {"case_id": f["case_id"]},
                correction_doc,
                upsert=True,
            )
            corrections_added += 1

        # ── Record iteration ──
        iter_result = {
            "iteration": iteration,
            "intent_accuracy": round(intent_acc * 100, 1),
            "sub_intent_coverage": round(avg_sub * 100, 1),
            "entity_coverage": round(avg_ent * 100, 1),
            "correct": correct, "total": total,
            "failure_count": len(failures),
            "corrections_in_engine": corrections_added,
            "total_corrections_stored": await db.intent_corrections.count_documents({}),
            "failures": [
                {"case_id": f["case_id"], "intent": f["main_intent"],
                 "got": f["extracted_class"], "hyp": f["extracted_hypothesis"][:60]}
                for f in failures
            ],
        }
        _rl_loop_state["iterations"].append(iter_result)

        logger.info(
            "[RL Loop] Iteration %d: acc=%.1f%% sub=%.1f%% ent=%.1f%% failures=%d corrections_stored=%d",
            iteration, intent_acc * 100, avg_sub * 100, avg_ent * 100,
            len(failures), iter_result["total_corrections_stored"],
        )

        # Persist progress
        await db.intent_rl_loop.replace_one(
            {"loop_id": _rl_loop_state["started_at"]},
            {"loop_id": _rl_loop_state["started_at"],
             "iterations": _rl_loop_state["iterations"],
             "updated_at": datetime.now(timezone.utc).isoformat()},
            upsert=True,
        )

    # ── Complete ──
    _rl_loop_state["running"] = False
    _rl_loop_state["completed_at"] = datetime.now(timezone.utc).isoformat()

    accs = [i["intent_accuracy"] for i in _rl_loop_state["iterations"]]
    logger.info("[RL Loop] COMPLETE. Accuracy: %s", " → ".join(f"{a}%" for a in accs))
