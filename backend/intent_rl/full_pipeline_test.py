"""Full Pipeline Test — L1 Scout → Micro-Q → Dimensions → L2 Sentry → QC Sentry.

Tests the complete MyndLens intent-to-mandate pipeline with real Gemini calls
and seeded Digital Self. Each stage's output feeds the next.
"""
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from intent_rl.dataset_v2 import INTENT_DATASET_V2
from intent_rl.seed_digital_self import RL_USER_ID

logger = logging.getLogger(__name__)


@dataclass
class PipelineStageResult:
    stage: str
    latency_ms: float
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class FullPipelineResult:
    case_id: int
    transcript: str
    main_intent: str
    stages: List[PipelineStageResult] = field(default_factory=list)
    total_latency_ms: float = 0.0
    l1_l2_agreement: bool = False
    qc_passed: bool = False
    final_intent: str = ""
    final_confidence: float = 0.0
    dimensions_extracted: Dict[str, Any] = field(default_factory=dict)


_pipeline_state = {
    "running": False,
    "completed": 0,
    "total": 0,
    "results": [],
    "summary": {},
    "started_at": None,
    "completed_at": None,
}


def get_pipeline_state() -> dict:
    return _pipeline_state


async def run_full_pipeline_test(batch_size: int = 10, delay: float = 0.3) -> str:
    global _pipeline_state
    if _pipeline_state["running"]:
        return "already_running"

    _pipeline_state = {
        "running": True,
        "completed": 0,
        "total": min(batch_size, len(INTENT_DATASET_V2)),
        "results": [],
        "summary": {},
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }
    asyncio.create_task(_execute_pipeline(batch_size, delay))
    return "started"


async def _execute_pipeline(batch_size: int, delay: float) -> None:
    global _pipeline_state

    from l1.scout import run_l1_scout
    from dimensions.extractor import extract_dimensions_via_llm
    from l2.sentry import run_l2_sentry, check_l1_l2_agreement
    from qc.sentry import run_qc_sentry
    from intent.micro_questions import generate_micro_questions, should_ask_micro_questions

    dataset = INTENT_DATASET_V2[:batch_size]
    all_results: List[FullPipelineResult] = []

    for i, case in enumerate(dataset):
        case_id = case["id"]
        transcript = case["broken_thoughts"]
        session_id = f"pipe_{case_id}_{int(time.time())}"
        pipe_result = FullPipelineResult(
            case_id=case_id, transcript=transcript[:80], main_intent=case["main_intent"],
        )
        pipe_start = time.monotonic()

        # ═══════════════════════════════════════════════════════════════
        # STAGE 1: L1 Scout — Intent Hypothesis
        # ═══════════════════════════════════════════════════════════════
        s1_start = time.monotonic()
        try:
            l1 = await run_l1_scout(session_id=session_id, user_id=RL_USER_ID, transcript=transcript)
            top = l1.hypotheses[0] if l1.hypotheses else None
            l1_hyp = top.hypothesis if top else ""
            l1_class = top.intent if top else "NONE"
            l1_conf = top.confidence if top else 0.0
            l1_dims = top.dimension_suggestions if top else {}

            pipe_result.stages.append(PipelineStageResult(
                stage="L1_SCOUT", latency_ms=l1.latency_ms, success=True,
                data={"hypothesis": l1_hyp[:80], "intent": l1_class, "confidence": l1_conf},
            ))
        except Exception as e:
            pipe_result.stages.append(PipelineStageResult(
                stage="L1_SCOUT", latency_ms=(time.monotonic() - s1_start) * 1000,
                success=False, error=str(e),
            ))
            l1_class, l1_conf, l1_dims, l1_hyp = "ERROR", 0.0, {}, ""

        await asyncio.sleep(delay)

        # ═══════════════════════════════════════════════════════════════
        # STAGE 1.5: Micro-Question (if needed)
        # ═══════════════════════════════════════════════════════════════
        mq_asked = ""
        if should_ask_micro_questions(l1_conf, l1_dims):
            s15_start = time.monotonic()
            try:
                mq = await generate_micro_questions(
                    session_id=session_id, user_id=RL_USER_ID, transcript=transcript,
                    hypothesis=l1_hyp, confidence=l1_conf, dimensions=l1_dims,
                )
                mq_asked = mq.questions[0].question if mq.questions else ""
                pipe_result.stages.append(PipelineStageResult(
                    stage="MICRO_QUESTION", latency_ms=mq.latency_ms, success=True,
                    data={"question": mq_asked, "trigger": mq.trigger_reason},
                ))
            except Exception as e:
                pipe_result.stages.append(PipelineStageResult(
                    stage="MICRO_QUESTION", latency_ms=(time.monotonic() - s15_start) * 1000,
                    success=False, error=str(e),
                ))
            await asyncio.sleep(delay)

        # ═══════════════════════════════════════════════════════════════
        # STAGE 2: Dedicated Dimension Extraction
        # ═══════════════════════════════════════════════════════════════
        s2_start = time.monotonic()
        try:
            dims = await extract_dimensions_via_llm(
                session_id=session_id, user_id=RL_USER_ID,
                transcript=transcript, l1_suggestions=l1_dims,
            )
            pipe_result.dimensions_extracted = dims
            completeness = sum(1 for f in ["who", "what", "when", "where", "how"] if dims.get(f)) / 5
            pipe_result.stages.append(PipelineStageResult(
                stage="DIMENSION_EXTRACT", latency_ms=dims.get("_meta", {}).get("latency_ms", 0),
                success=True,
                data={"who": dims.get("who", "")[:40], "what": dims.get("what", "")[:40],
                      "when": dims.get("when", ""), "where": dims.get("where", ""),
                      "completeness": round(completeness * 100)},
            ))
        except Exception as e:
            pipe_result.stages.append(PipelineStageResult(
                stage="DIMENSION_EXTRACT", latency_ms=(time.monotonic() - s2_start) * 1000,
                success=False, error=str(e),
            ))
            dims = l1_dims

        await asyncio.sleep(delay)

        # ═══════════════════════════════════════════════════════════════
        # STAGE 3: L2 Sentry — Shadow Verification
        # ═══════════════════════════════════════════════════════════════
        s3_start = time.monotonic()
        try:
            l2 = await run_l2_sentry(
                session_id=session_id, user_id=RL_USER_ID, transcript=transcript,
                l1_intent=l1_class, l1_confidence=l1_conf, dimensions=dims,
            )
            agrees, reason = check_l1_l2_agreement(l1_class, l1_conf, l2)
            pipe_result.l1_l2_agreement = agrees
            pipe_result.stages.append(PipelineStageResult(
                stage="L2_SENTRY", latency_ms=l2.latency_ms, success=True,
                data={"intent": l2.intent, "confidence": l2.confidence,
                      "agrees_with_l1": agrees, "risk_tier": l2.risk_tier,
                      "chain_of_logic": l2.chain_of_logic[:60]},
            ))
            # Use L2 as authoritative when it disagrees
            if not agrees:
                pipe_result.final_intent = l2.intent
                pipe_result.final_confidence = l2.confidence
            else:
                pipe_result.final_intent = l1_class
                pipe_result.final_confidence = max(l1_conf, l2.confidence)
        except Exception as e:
            pipe_result.stages.append(PipelineStageResult(
                stage="L2_SENTRY", latency_ms=(time.monotonic() - s3_start) * 1000,
                success=False, error=str(e),
            ))
            pipe_result.final_intent = l1_class
            pipe_result.final_confidence = l1_conf

        await asyncio.sleep(delay)

        # ═══════════════════════════════════════════════════════════════
        # STAGE 4: QC Sentry — Adversarial Review
        # ═══════════════════════════════════════════════════════════════
        s4_start = time.monotonic()
        try:
            qc = await run_qc_sentry(
                session_id=session_id, user_id=RL_USER_ID, transcript=transcript,
                intent=pipe_result.final_intent,
                intent_summary=l1_hyp[:80],
                persona_summary="Concise, direct communicator. Product Manager at Acme Corp.",
                skill_risk="low",
                skill_names=["assistant"],
            )
            pipe_result.qc_passed = qc.overall_pass
            pipe_result.stages.append(PipelineStageResult(
                stage="QC_SENTRY", latency_ms=qc.latency_ms, success=True,
                data={"overall_pass": qc.overall_pass,
                      "passes": [{"name": p.pass_name, "passed": p.passed, "severity": p.severity}
                                 for p in qc.passes],
                      "block_reason": qc.block_reason},
            ))
        except Exception as e:
            pipe_result.stages.append(PipelineStageResult(
                stage="QC_SENTRY", latency_ms=(time.monotonic() - s4_start) * 1000,
                success=False, error=str(e),
            ))

        # ═══════════════════════════════════════════════════════════════
        pipe_result.total_latency_ms = (time.monotonic() - pipe_start) * 1000

        result_dict = {
            "case_id": pipe_result.case_id,
            "main_intent": pipe_result.main_intent,
            "final_class": pipe_result.final_intent,
            "final_confidence": pipe_result.final_confidence,
            "l1_l2_agree": pipe_result.l1_l2_agreement,
            "qc_passed": pipe_result.qc_passed,
            "stages": [{"stage": s.stage, "ms": round(s.latency_ms), "ok": s.success,
                        **{k: v for k, v in s.data.items() if k != "_meta"}}
                       for s in pipe_result.stages],
            "dimensions": {k: v for k, v in pipe_result.dimensions_extracted.items() if k != "_meta"},
            "total_ms": round(pipe_result.total_latency_ms),
            "micro_q": mq_asked,
        }
        all_results.append(pipe_result)
        _pipeline_state["results"].append(result_dict)
        _pipeline_state["completed"] = i + 1

        logger.info(
            "[PIPELINE %d/%d] %s | L1=%s L2_agree=%s QC=%s dims=%d%% | %.0fms%s",
            i + 1, len(dataset), case["main_intent"],
            pipe_result.final_intent, pipe_result.l1_l2_agreement,
            pipe_result.qc_passed,
            sum(1 for f in ["who", "what", "when", "where"] if dims.get(f)) * 25,
            pipe_result.total_latency_ms,
            f" MQ=\"{mq_asked}\"" if mq_asked else "",
        )

        await asyncio.sleep(delay)

    # ═══════════════════════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════════════════════
    total = len(all_results)
    _pipeline_state["summary"] = {
        "total": total,
        "l1_l2_agreement_rate": round(sum(1 for r in all_results if r.l1_l2_agreement) / total * 100, 1) if total else 0,
        "qc_pass_rate": round(sum(1 for r in all_results if r.qc_passed) / total * 100, 1) if total else 0,
        "avg_confidence": round(sum(r.final_confidence for r in all_results) / total, 3) if total else 0,
        "avg_latency_ms": round(sum(r.total_latency_ms for r in all_results) / total) if total else 0,
        "micro_questions_asked": sum(1 for r in all_results if any(s.stage == "MICRO_QUESTION" for s in r.stages)),
        "dim_completeness_avg": round(
            sum(sum(1 for f in ["who", "what", "when", "where", "how"] if r.dimensions_extracted.get(f)) / 5
                for r in all_results) / total * 100, 1) if total else 0,
    }

    _pipeline_state["running"] = False
    _pipeline_state["completed_at"] = datetime.now(timezone.utc).isoformat()

    logger.info(
        "[PIPELINE COMPLETE] cases=%d agree=%.0f%% qc=%.0f%% conf=%.3f dims=%.0f%% avg_ms=%d",
        total, _pipeline_state["summary"]["l1_l2_agreement_rate"],
        _pipeline_state["summary"]["qc_pass_rate"],
        _pipeline_state["summary"]["avg_confidence"],
        _pipeline_state["summary"]["dim_completeness_avg"],
        _pipeline_state["summary"]["avg_latency_ms"],
    )
