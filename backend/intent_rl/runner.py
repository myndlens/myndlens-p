"""Intent RL Runner — executes the 100-case test, scores results, feeds back corrections.

Workflow:
  1. Run each fragment through L1 Scout (real Gemini)
  2. Compare extracted action_class vs ground truth
  3. Score semantic similarity of hypothesis vs expected intent
  4. Track outcomes via existing prompt outcome system
  5. Submit corrections for failures → reinforcement learning loop
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from intent_rl import INTENT_DATASET, INTENT_CATEGORIES as ACTION_CLASSES

logger = logging.getLogger(__name__)

# ── Types ────────────────────────────────────────────────────────────────────

@dataclass
class CaseResult:
    case_id: int
    fragment: str
    ground_truth_class: str
    ground_truth_intent: str
    extracted_class: str
    extracted_hypothesis: str
    confidence: float
    class_match: bool
    latency_ms: float
    prompt_id: str
    is_mock: bool
    error: Optional[str] = None


@dataclass
class BatchResult:
    run_id: str
    started_at: str
    completed_at: Optional[str] = None
    total: int = 0
    completed: int = 0
    in_progress: bool = True
    # Accuracy
    class_correct: int = 0
    class_accuracy: float = 0.0
    # Per-class breakdown
    per_class: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # Timing
    avg_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    # Cases
    cases: List[Dict[str, Any]] = field(default_factory=list)
    failures: List[Dict[str, Any]] = field(default_factory=list)
    # Feedback
    corrections_submitted: int = 0


# ── Globals (in-memory state for the running batch) ──────────────────────────

_current_run: Optional[BatchResult] = None
_run_lock = asyncio.Lock()


def get_current_run() -> Optional[BatchResult]:
    return _current_run


# ── Runner ───────────────────────────────────────────────────────────────────

async def run_intent_rl_batch(
    batch_size: int = 100,
    user_id: str = "rl_test_user",
    delay_between_calls: float = 0.5,
) -> str:
    """Run the full intent RL batch. Returns run_id.

    Executes in background — poll get_current_run() for progress.
    """
    global _current_run

    async with _run_lock:
        if _current_run and _current_run.in_progress:
            return _current_run.run_id  # Already running

    run_id = f"rl_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    dataset = INTENT_DATASET[:batch_size]

    _current_run = BatchResult(
        run_id=run_id,
        started_at=datetime.now(timezone.utc).isoformat(),
        total=len(dataset),
        per_class={cls: {"total": 0, "correct": 0, "wrong": 0} for cls in ACTION_CLASSES},
    )

    # Count ground truth per class
    for case in dataset:
        cls = case["ground_truth"]["intent_category"]
        if cls in _current_run.per_class:
            _current_run.per_class[cls]["total"] += 1

    # Run in background
    asyncio.create_task(_execute_batch(dataset, user_id, delay_between_calls))
    return run_id


async def _execute_batch(
    dataset: list,
    user_id: str,
    delay: float,
) -> None:
    """Execute all test cases sequentially (to respect rate limits)."""
    global _current_run
    if not _current_run:
        return

    from l1.scout import run_l1_scout

    results: List[CaseResult] = []

    for i, case in enumerate(dataset):
        case_id = case["id"]
        fragment = case["fragment"]
        gt = case["ground_truth"]
        session_id = f"rl_{_current_run.run_id}_{case_id}"

        try:
            draft = await run_l1_scout(
                session_id=session_id,
                user_id=user_id,
                transcript=fragment,
            )

            # Extract top hypothesis
            if draft.hypotheses:
                top = draft.hypotheses[0]
                extracted_class = top.intent
                extracted_hypothesis = top.hypothesis
                confidence = top.confidence
            else:
                extracted_class = "NO_HYPOTHESIS"
                extracted_hypothesis = ""
                confidence = 0.0

            class_match = _normalize_class(extracted_class) == _normalize_class(gt["intent_category"])

            result = CaseResult(
                case_id=case_id,
                fragment=fragment,
                ground_truth_class=gt["intent_category"],
                ground_truth_intent=gt["intent"],
                extracted_class=extracted_class,
                extracted_hypothesis=extracted_hypothesis,
                confidence=confidence,
                class_match=class_match,
                latency_ms=draft.latency_ms,
                prompt_id=draft.prompt_id,
                is_mock=draft.is_mock,
            )

        except Exception as e:
            logger.error("RL case %d failed: %s", case_id, str(e))
            result = CaseResult(
                case_id=case_id,
                fragment=fragment,
                ground_truth_class=gt["intent_category"],
                ground_truth_intent=gt["intent"],
                extracted_class="ERROR",
                extracted_hypothesis="",
                confidence=0.0,
                class_match=False,
                latency_ms=0.0,
                prompt_id="",
                is_mock=False,
                error=str(e),
            )

        results.append(result)

        # Update progress
        _current_run.completed = i + 1
        if result.class_match:
            _current_run.class_correct += 1
        _current_run.class_accuracy = _current_run.class_correct / _current_run.completed

        # Update per-class
        gt_cls = gt["intent_category"]
        if gt_cls in _current_run.per_class:
            if result.class_match:
                _current_run.per_class[gt_cls]["correct"] += 1
            else:
                _current_run.per_class[gt_cls]["wrong"] += 1

        case_dict = {
            "case_id": result.case_id,
            "fragment": result.fragment,
            "ground_truth_class": result.ground_truth_class,
            "ground_truth_intent": result.ground_truth_intent,
            "extracted_class": result.extracted_class,
            "extracted_hypothesis": result.extracted_hypothesis,
            "confidence": result.confidence,
            "class_match": result.class_match,
            "latency_ms": round(result.latency_ms, 1),
            "is_mock": result.is_mock,
        }
        _current_run.cases.append(case_dict)
        if not result.class_match:
            _current_run.failures.append(case_dict)

        _current_run.total_latency_ms += result.latency_ms
        _current_run.avg_latency_ms = _current_run.total_latency_ms / _current_run.completed

        logger.info(
            "[RL %d/%d] %s | GT=%s | Got=%s | Match=%s | Conf=%.2f | %.0fms",
            i + 1, len(dataset),
            fragment[:40],
            gt["intent_category"],
            extracted_class,
            result.class_match,
            confidence,
            result.latency_ms,
        )

        # Rate limit protection
        if delay > 0:
            await asyncio.sleep(delay)

    # ── Batch complete ────────────────────────────────────────────────
    _current_run.completed_at = datetime.now(timezone.utc).isoformat()
    _current_run.in_progress = False

    # Track outcomes + submit corrections for failures
    await _submit_feedback(results)

    # Persist to MongoDB
    await _persist_run_results(results)

    logger.info(
        "[RL COMPLETE] run=%s accuracy=%.1f%% (%d/%d) avg_latency=%.0fms",
        _current_run.run_id,
        _current_run.class_accuracy * 100,
        _current_run.class_correct,
        _current_run.total,
        _current_run.avg_latency_ms,
    )


# ── Feedback Loop ────────────────────────────────────────────────────────────

async def _submit_feedback(results: List[CaseResult]) -> None:
    """Track outcomes and submit corrections for failed cases."""
    from prompting.outcomes import PromptOutcome, OutcomeResult, track_outcome, track_user_correction

    corrections = 0
    for r in results:
        if not r.prompt_id or r.error:
            continue

        # Track outcome for every case
        outcome = PromptOutcome(
            prompt_id=r.prompt_id,
            purpose="THOUGHT_TO_INTENT",
            session_id=f"rl_{r.case_id}",
            user_id="rl_test_user",
            result=OutcomeResult.SUCCESS if r.class_match else OutcomeResult.CORRECTED,
            accuracy_score=1.0 if r.class_match else 0.0,
            execution_success=r.class_match,
            user_corrected=not r.class_match,
            correction_type="action_class_mismatch" if not r.class_match else None,
            latency_ms=r.latency_ms,
            model_name="gemini-2.0-flash",
            metadata={
                "ground_truth_class": r.ground_truth_class,
                "extracted_class": r.extracted_class,
                "fragment": r.fragment,
                "rl_batch": True,
            },
        )
        try:
            await track_outcome(outcome)
        except Exception as e:
            logger.warning("Failed to track outcome for case %d: %s", r.case_id, e)

        # Submit correction for failures → feeds the learning loop
        if not r.class_match:
            try:
                await track_user_correction(
                    session_id=f"rl_{r.case_id}",
                    user_id="rl_test_user",
                    original_intent=f"[{r.extracted_class}] {r.extracted_hypothesis}",
                    corrected_intent=f"[{r.ground_truth_class}] {r.ground_truth_intent}",
                    prompt_id=r.prompt_id,
                )
                corrections += 1
            except Exception as e:
                logger.warning("Failed to submit correction for case %d: %s", r.case_id, e)

    if _current_run:
        _current_run.corrections_submitted = corrections

    logger.info("[RL Feedback] Tracked %d outcomes, submitted %d corrections", len(results), corrections)


async def _persist_run_results(results: List[CaseResult]) -> None:
    """Save full run results to MongoDB for historical analysis."""
    from core.database import get_db
    db = get_db()

    if not _current_run:
        return

    doc = {
        "run_id": _current_run.run_id,
        "started_at": _current_run.started_at,
        "completed_at": _current_run.completed_at,
        "total": _current_run.total,
        "class_correct": _current_run.class_correct,
        "class_accuracy": _current_run.class_accuracy,
        "per_class": _current_run.per_class,
        "avg_latency_ms": round(_current_run.avg_latency_ms, 1),
        "corrections_submitted": _current_run.corrections_submitted,
        "cases": _current_run.cases,
        "failures": _current_run.failures,
    }
    await db.intent_rl_runs.replace_one({"run_id": _current_run.run_id}, doc, upsert=True)
    logger.info("[RL] Run persisted to MongoDB: %s", _current_run.run_id)


# ── Helpers ──────────────────────────────────────────────────────────────────

# Map LLM-returned classes to our canonical classes (fuzzy matching)
_CLASS_ALIASES = {
    "COMM_SEND": ["COMM_SEND", "COMMUNICATION", "SEND_MESSAGE", "EMAIL", "MESSAGE", "NOTIFY"],
    "SCHED_MODIFY": ["SCHED_MODIFY", "SCHEDULE", "CALENDAR", "MEETING", "BOOK", "RESCHEDULE"],
    "INFO_RETRIEVE": ["INFO_RETRIEVE", "INFORMATION", "SEARCH", "LOOKUP", "QUERY", "FIND", "CHECK"],
    "DOC_EDIT": ["DOC_EDIT", "DOCUMENT", "WRITE", "DRAFT", "EDIT", "CREATE_DOCUMENT", "CONTENT_CREATE"],
    "CODE_GEN": ["CODE_GEN", "CODE", "PROGRAMMING", "DEVELOP", "BUILD", "FIX_BUG", "SOFTWARE"],
    "FIN_TRANS": ["FIN_TRANS", "FINANCIAL", "PAYMENT", "INVOICE", "EXPENSE", "MONEY", "BILLING"],
    "TASK_CREATE": ["TASK_CREATE", "TASK", "TODO", "ACTION_ITEM", "TRACK", "NOTE"],
    "REMINDER_SET": ["REMINDER_SET", "REMINDER", "ALARM", "ALERT", "NOTIFY_LATER"],
    "DATA_ANALYZE": ["DATA_ANALYZE", "ANALYSIS", "ANALYTICS", "CHART", "REPORT", "FORECAST", "COMPARE"],
    "AUTOMATION": ["AUTOMATION", "AUTOMATE", "WORKFLOW", "TRIGGER", "RECURRING", "RULE"],
}

_ALIAS_LOOKUP = {}
for canonical, aliases in _CLASS_ALIASES.items():
    for alias in aliases:
        _ALIAS_LOOKUP[alias.upper()] = canonical


def _normalize_class(raw_class: str) -> str:
    """Normalize an LLM-returned action class to our canonical set."""
    upper = raw_class.strip().upper().replace(" ", "_").replace("-", "_")
    if upper in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[upper]
    # Fuzzy: check if any canonical class is a substring
    for canonical in ACTION_CLASSES:
        if canonical in upper or upper in canonical:
            return canonical
    return upper


async def get_historical_runs(limit: int = 10) -> list:
    """Retrieve historical RL run results from MongoDB."""
    from core.database import get_db
    db = get_db()
    cursor = db.intent_rl_runs.find(
        {}, {"_id": 0, "cases": 0}  # Exclude bulky case data
    ).sort("started_at", -1).limit(limit)
    return await cursor.to_list(length=limit)
