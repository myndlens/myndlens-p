"""Intent RL Runner v2 — evaluates holistic intent extraction from broken thoughts.

Evaluates:
  1. Does the LLM identify the MAIN INTENT correctly?
  2. Does it capture the KEY SUB-INTENTS?
  3. Does it resolve entities from the Digital Self?
  4. Does it extract the right dimensions (who/what/when/where)?
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from intent_rl.dataset_v2 import INTENT_DATASET_V2, MAIN_INTENTS

logger = logging.getLogger(__name__)


@dataclass
class V2CaseResult:
    case_id: int
    broken_thoughts: str
    ground_truth_intent: str
    ground_truth_sub_intents: List[str]
    extracted_hypothesis: str
    extracted_action_class: str
    confidence: float
    # Scoring
    intent_match: bool            # Did it get the main intent right?
    sub_intents_found: List[str]  # Which sub-intents were captured
    sub_intent_coverage: float    # % of sub-intents captured
    entities_resolved: List[str]  # Which entities were resolved from DS
    entity_coverage: float        # % of expected entities resolved
    latency_ms: float
    prompt_id: str
    is_mock: bool
    all_hypotheses: List[Dict] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class V2BatchResult:
    run_id: str
    version: str = "v2"
    started_at: str = ""
    completed_at: Optional[str] = None
    total: int = 0
    completed: int = 0
    in_progress: bool = True
    # Main intent accuracy
    intent_correct: int = 0
    intent_accuracy: float = 0.0
    # Sub-intent coverage
    avg_sub_intent_coverage: float = 0.0
    # Entity resolution
    avg_entity_coverage: float = 0.0
    # Per-intent breakdown
    per_intent: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # Timing
    avg_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    # Cases
    cases: List[Dict[str, Any]] = field(default_factory=list)
    failures: List[Dict[str, Any]] = field(default_factory=list)
    corrections_submitted: int = 0


_current_v2_run: Optional[V2BatchResult] = None
_v2_lock = asyncio.Lock()


def get_current_v2_run() -> Optional[V2BatchResult]:
    return _current_v2_run


async def run_v2_batch(batch_size: int = 40, delay: float = 0.5) -> str:
    """Run the v2 intent RL batch with broken thoughts."""
    global _current_v2_run

    async with _v2_lock:
        if _current_v2_run and _current_v2_run.in_progress:
            return _current_v2_run.run_id

    run_id = f"rl2_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    dataset = INTENT_DATASET_V2[:batch_size]

    _current_v2_run = V2BatchResult(
        run_id=run_id,
        started_at=datetime.now(timezone.utc).isoformat(),
        total=len(dataset),
        per_intent={intent: {"total": 0, "correct": 0, "avg_sub_coverage": 0.0, "avg_entity_coverage": 0.0}
                    for intent in MAIN_INTENTS},
    )
    for case in dataset:
        mi = case["main_intent"]
        if mi in _current_v2_run.per_intent:
            _current_v2_run.per_intent[mi]["total"] += 1

    asyncio.create_task(_execute_v2_batch(dataset, delay))
    return run_id


async def _execute_v2_batch(dataset: list, delay: float) -> None:
    global _current_v2_run
    if not _current_v2_run:
        return

    from l1.scout import run_l1_scout
    from intent_rl.seed_digital_self import RL_USER_ID

    sub_coverages = []
    entity_coverages = []

    for i, case in enumerate(dataset):
        case_id = case["id"]
        broken_thoughts = case["broken_thoughts"]
        main_intent = case["main_intent"]
        expected_subs = case["sub_intents"]
        expected_entities = case.get("expected_entities", [])
        session_id = f"rl2_{_current_v2_run.run_id}_{case_id}"

        try:
            draft = await run_l1_scout(
                session_id=session_id,
                user_id=RL_USER_ID,
                transcript=broken_thoughts,
            )

            # Collect ALL hypotheses (the LLM returns up to 3)
            all_hyps = []
            for h in draft.hypotheses:
                all_hyps.append({
                    "hypothesis": h.hypothesis,
                    "action_class": h.action_class,
                    "confidence": h.confidence,
                    "dimensions": h.dimension_suggestions,
                })

            top = draft.hypotheses[0] if draft.hypotheses else None
            extracted_hyp = top.hypothesis if top else ""
            extracted_class = top.action_class if top else "NONE"
            confidence = top.confidence if top else 0.0

            # ── Score main intent ──
            intent_match = _check_intent_match(extracted_hyp, extracted_class, all_hyps, main_intent)

            # ── Score sub-intent coverage ──
            sub_found, sub_coverage = _check_sub_intents(extracted_hyp, all_hyps, expected_subs)

            # ── Score entity resolution ──
            entities_resolved, entity_coverage = _check_entity_resolution(extracted_hyp, all_hyps, expected_entities)

            result = V2CaseResult(
                case_id=case_id,
                broken_thoughts=broken_thoughts,
                ground_truth_intent=main_intent,
                ground_truth_sub_intents=expected_subs,
                extracted_hypothesis=extracted_hyp,
                extracted_action_class=extracted_class,
                confidence=confidence,
                intent_match=intent_match,
                sub_intents_found=sub_found,
                sub_intent_coverage=sub_coverage,
                entities_resolved=entities_resolved,
                entity_coverage=entity_coverage,
                latency_ms=draft.latency_ms,
                prompt_id=draft.prompt_id,
                is_mock=draft.is_mock,
                all_hypotheses=all_hyps,
            )
        except Exception as e:
            logger.error("RL v2 case %d failed: %s", case_id, str(e))
            result = V2CaseResult(
                case_id=case_id, broken_thoughts=broken_thoughts,
                ground_truth_intent=main_intent, ground_truth_sub_intents=expected_subs,
                extracted_hypothesis="", extracted_action_class="ERROR",
                confidence=0.0, intent_match=False, sub_intents_found=[],
                sub_intent_coverage=0.0, entities_resolved=[], entity_coverage=0.0,
                latency_ms=0.0, prompt_id="", is_mock=False, error=str(e),
            )

        # Update progress
        _current_v2_run.completed = i + 1
        if result.intent_match:
            _current_v2_run.intent_correct += 1
        _current_v2_run.intent_accuracy = _current_v2_run.intent_correct / _current_v2_run.completed

        sub_coverages.append(result.sub_intent_coverage)
        _current_v2_run.avg_sub_intent_coverage = sum(sub_coverages) / len(sub_coverages)

        entity_coverages.append(result.entity_coverage)
        _current_v2_run.avg_entity_coverage = sum(entity_coverages) / len(entity_coverages)

        _current_v2_run.total_latency_ms += result.latency_ms
        _current_v2_run.avg_latency_ms = _current_v2_run.total_latency_ms / _current_v2_run.completed

        # Per-intent stats
        mi = main_intent
        if mi in _current_v2_run.per_intent:
            if result.intent_match:
                _current_v2_run.per_intent[mi]["correct"] += 1
            _current_v2_run.per_intent[mi]["avg_sub_coverage"] = round(result.sub_intent_coverage * 100, 1)
            _current_v2_run.per_intent[mi]["avg_entity_coverage"] = round(result.entity_coverage * 100, 1)

        case_dict = {
            "case_id": result.case_id,
            "broken_thoughts": result.broken_thoughts[:80],
            "main_intent": result.ground_truth_intent,
            "extracted_hypothesis": result.extracted_hypothesis[:100],
            "extracted_class": result.extracted_action_class,
            "intent_match": result.intent_match,
            "sub_coverage": round(result.sub_intent_coverage * 100, 1),
            "entity_coverage": round(result.entity_coverage * 100, 1),
            "sub_intents_found": result.sub_intents_found,
            "entities_resolved": result.entities_resolved,
            "confidence": result.confidence,
            "latency_ms": round(result.latency_ms, 1),
        }
        _current_v2_run.cases.append(case_dict)
        if not result.intent_match:
            case_dict["all_hypotheses"] = result.all_hypotheses
            _current_v2_run.failures.append(case_dict)

        logger.info(
            "[RLv2 %d/%d] %s | Intent=%s | Match=%s | SubCov=%.0f%% | EntCov=%.0f%% | %.0fms",
            i + 1, len(dataset), main_intent, "YES" if result.intent_match else "NO",
            result.intent_match, result.sub_intent_coverage * 100,
            result.entity_coverage * 100, result.latency_ms,
        )

        if delay > 0:
            await asyncio.sleep(delay)

    # Complete
    _current_v2_run.completed_at = datetime.now(timezone.utc).isoformat()
    _current_v2_run.in_progress = False

    # Persist
    await _persist_v2_run()

    logger.info(
        "[RLv2 COMPLETE] run=%s intent_acc=%.1f%% sub_cov=%.1f%% entity_cov=%.1f%% latency=%.0fms",
        _current_v2_run.run_id, _current_v2_run.intent_accuracy * 100,
        _current_v2_run.avg_sub_intent_coverage * 100,
        _current_v2_run.avg_entity_coverage * 100, _current_v2_run.avg_latency_ms,
    )


# ── Scoring Functions ────────────────────────────────────────────────────────

# Map main intents to keywords the LLM is likely to use
_INTENT_KEYWORDS = {
    "Travel Concierge": ["travel", "trip", "flight", "hotel", "book", "fly", "journey", "destination", "accommodation"],
    "Event Planning": ["event", "party", "venue", "catering", "celebrate", "plan", "organize", "gathering", "offsite"],
    "Project Kickoff": ["project", "kickoff", "kick off", "sprint", "repo", "jira", "timeline", "assign"],
    "Hiring Pipeline": ["hire", "hiring", "recruit", "candidate", "interview", "job", "position", "resume", "offer"],
    "Financial Operations": ["invoice", "payment", "expense", "budget", "cost", "subscription", "financial", "billing", "quote"],
    "Content Creation": ["blog", "content", "write", "article", "newsletter", "post", "publish", "draft", "copy"],
    "Customer Success": ["customer", "client", "onboarding", "account", "retention", "churn", "check-in"],
    "Personal Wellness": ["health", "gym", "wellness", "fitness", "doctor", "stretching", "meal", "burnout", "self-care"],
    "Data & Analytics": ["dashboard", "analytics", "data", "chart", "metric", "trend", "revenue", "funnel", "report"],
    "Incident Response": ["incident", "outage", "down", "breach", "emergency", "war room", "page", "critical"],
    "Weekly Planning": ["week", "plan", "schedule", "sprint planning", "standup", "calendar", "status report"],
    "Relocation Planning": ["office", "lease", "relocat", "property", "space", "move", "real estate"],
    "Marketing Campaign": ["campaign", "marketing", "email blast", "social media", "ads", "webinar", "launch"],
    "Vendor Management": ["vendor", "supplier", "provider", "quote", "compare", "procurement", "switch"],
    "Automation Setup": ["automat", "workflow", "auto-assign", "recurring", "trigger", "every week", "compile"],
    "Conflict Resolution": ["conflict", "mediation", "friction", "not getting along", "reassign", "dispute"],
    "Product Launch": ["release", "launch", "deploy", "changelog", "feature flag", "app store", "go live"],
    "Knowledge Management": ["wiki", "documentation", "docs", "reorganize", "templates", "knowledge base"],
    "Personal Finance": ["tax", "budget", "deduction", "subscription", "expense", "savings", "accountant"],
    "Team Development": ["mentor", "career", "grow", "learning", "conference", "upskill", "training", "development"],
}


def _check_intent_match(hypothesis: str, action_class: str, all_hyps: list, ground_truth: str) -> bool:
    """Check if the LLM identified the correct main intent."""
    combined = hypothesis.lower()
    for h in all_hyps:
        combined += " " + h.get("hypothesis", "").lower()

    keywords = _INTENT_KEYWORDS.get(ground_truth, [])
    matches = sum(1 for kw in keywords if kw in combined)
    return matches >= 2  # At least 2 keyword matches = correct intent


def _check_sub_intents(hypothesis: str, all_hyps: list, expected_subs: list) -> tuple:
    """Check how many sub-intents were captured in the hypothesis."""
    combined = hypothesis.lower()
    for h in all_hyps:
        combined += " " + h.get("hypothesis", "").lower()
        dims = h.get("dimensions", {})
        combined += " " + " ".join(str(v) for v in dims.values()).lower()

    # Map sub-intent slugs to detection keywords
    SUB_KEYWORDS = {
        "book_flight": ["flight", "fly", "airline", "book"],
        "book_hotel": ["hotel", "accommodation", "stay", "lodge"],
        "rent_car": ["car", "rental", "drive"],
        "schedule_meeting": ["meeting", "schedule", "call", "session"],
        "arrange_dinner": ["dinner", "restaurant", "eat"],
        "check_availability": ["check", "available", "free", "town"],
        "find_venue": ["venue", "space", "location", "room"],
        "arrange_catering": ["catering", "food", "lunch", "meal"],
        "set_budget": ["budget", "cost", "spending"],
        "delegate_task": ["assign", "delegate", "handle", "leads"],
        "book_restaurant": ["restaurant", "book", "reserve"],
        "send_invitations": ["invite", "invitation", "send"],
        "order_cake": ["cake", "order"],
        "keep_secret": ["surprise", "secret", "don't tell"],
        "prepare_demo": ["demo", "prepare", "ready"],
        "create_repository": ["repo", "repository", "set up"],
        "create_project_board": ["jira", "board", "project"],
        "assign_team": ["assign", "team", "member"],
        "create_timeline": ["timeline", "schedule", "plan"],
        "assign_tasks": ["assign", "frontend", "backend", "task"],
        "schedule_sprint": ["sprint", "start"],
        "post_job_listing": ["post", "linkedin", "careers", "job"],
        "delegate_screening": ["screen", "resume", "review"],
        "follow_up_contact": ["follow up", "contact", "reach out"],
        "schedule_interview": ["interview", "schedule"],
        "prepare_offer": ["offer", "letter"],
        "check_references": ["reference", "check"],
        "process_invoices": ["invoice", "process", "pending"],
        "pay_bill": ["pay", "bill", "aws"],
        "submit_expenses": ["expense", "submit", "report"],
        "prepare_report": ["report", "prepare", "numbers", "usage"],
        "cancel_subscription": ["cancel", "subscription", "netflix"],
        "downgrade_service": ["downgrade", "free tier"],
        "calculate_savings": ["save", "total", "cost"],
        "revise_quote": ["quote", "revise", "lower"],
        "add_package": ["package", "maintenance", "include"],
        "send_document": ["send", "before"],
        "write_blog_post": ["blog", "write", "post"],
        "add_screenshots": ["screenshot", "image"],
        "optimize_seo": ["seo", "search"],
        "publish": ["publish", "post", "site"],
        "share_social": ["linkedin", "twitter", "share", "social"],
        "get_review": ["review", "approve", "check"],
        "compile_highlights": ["highlight", "compile", "pull"],
        "add_photos": ["photo", "image"],
        "write_section": ["section", "write", "add"],
        "send_newsletter": ["newsletter", "email", "send"],
        "draft_email": ["email", "draft", "write"],
        "include_explanation": ["explain", "what happened"],
        "add_compensation": ["compensation", "offer"],
        "get_approval": ["approval", "run by", "check with"],
        "schedule_call": ["call", "check-in", "schedule"],
        "create_offer": ["offer", "free", "premium"],
        "setup_workspace": ["workspace", "set up"],
        "import_data": ["import", "data", "migrate"],
        "schedule_training": ["training", "session"],
        "assign_manager": ["assign", "manager", "account"],
        "book_gym": ["gym", "book", "session"],
        "set_reminder": ["remind", "reminder", "alert"],
        "find_service": ["find", "service", "meal", "deliver"],
        "schedule_appointment": ["appointment", "doctor", "schedule"],
        "block_calendar": ["block", "calendar", "no meetings"],
        "reschedule_meetings": ["reschedule", "cancel", "clear"],
        "plan_trip": ["trip", "day trip", "plan"],
        "create_dashboard": ["dashboard", "create", "build"],
        "analyze_funnel": ["funnel", "drop", "analyze"],
        "compare_rates": ["compare", "rate", "signup"],
        "investigate_technical": ["technical", "check", "investigate"],
        "page_team": ["page", "team", "on-call"],
        "check_logs": ["log", "check", "monitor"],
        "notify_customers": ["notify", "customer", "affected"],
        "setup_call": ["war room", "call", "meeting"],
        "assign_lead": ["lead", "investigation", "assign"],
        "lock_accounts": ["lock", "account", "down"],
        "notify_legal": ["legal", "notify"],
        "start_forensics": ["forensic", "analysis", "investigate"],
        "draft_notification": ["notification", "draft", "customer"],
        "organize_calendar": ["calendar", "organize", "plan"],
        "block_deep_work": ["deep work", "block", "focus"],
        "plan_sprint": ["sprint", "plan", "backlog"],
        "assign_stories": ["assign", "stories", "team"],
        "check_capacity": ["capacity", "vacation", "available"],
        "search_properties": ["search", "look", "property", "office"],
        "schedule_tours": ["tour", "schedule", "visit"],
        "set_criteria": ["criteria", "budget", "size", "location"],
        "send_email_blast": ["email", "blast", "send"],
        "post_social_media": ["social", "post", "platform"],
        "setup_ads": ["ads", "google", "campaign"],
        "update_landing_page": ["landing page", "update"],
        "setup_tracking": ["track", "conversion", "analytics"],
        "setup_webinar": ["webinar", "zoom", "setup"],
        "create_registration": ["registration", "sign up"],
        "prepare_slides": ["slide", "deck", "present"],
        "assign_roles": ["moderate", "present", "role"],
        "request_quotes": ["quote", "get", "request"],
        "compare_pricing": ["compare", "pricing", "cost"],
        "schedule_calls": ["call", "schedule", "sales"],
        "create_auto_assignment": ["auto", "assign", "route"],
        "setup_welcome_email": ["welcome", "pack", "email"],
        "crm_integration": ["crm", "log"],
        "conditional_notification": ["notify", "enterprise", "only"],
        "schedule_compilation": ["compile", "friday", "weekly"],
        "send_report": ["email", "send", "sarah"],
        "save_backup": ["save", "shared", "drive", "copy"],
        "setup_reminder": ["ping", "remind", "thursday"],
        "schedule_mediation": ["mediation", "meeting", "schedule"],
        "review_history": ["history", "review", "what happened"],
        "prepare_talking_points": ["talking points", "prepare"],
        "reassign_tasks": ["reassign", "task", "reduce"],
        "write_changelog": ["changelog", "write", "release note"],
        "update_docs": ["docs", "update", "documentation"],
        "send_announcement": ["email", "customer", "announce"],
        "configure_feature_flags": ["feature flag", "rollout", "gradual"],
        "setup_monitoring": ["monitor", "error", "track"],
        "submit_app_stores": ["app store", "play store", "submit"],
        "write_release_notes": ["what's new", "release note"],
        "coordinate_press": ["press", "marketing", "coordinate"],
        "assign_qa": ["qa", "test", "final"],
        "reorganize_docs": ["reorganize", "restructure", "clean"],
        "archive_old": ["archive", "outdated", "old"],
        "create_templates": ["template", "create", "new"],
        "assign_ownership": ["own", "assign", "section"],
        "schedule_reviews": ["review", "quarterly", "schedule"],
        "gather_receipts": ["receipt", "gather", "collect"],
        "calculate_deductions": ["deduction", "calculate", "tax"],
        "transfer_funds": ["transfer", "savings", "amount"],
        "check_deadlines": ["file", "quarterly", "deadline"],
        "audit_subscriptions": ["subscription", "audit", "spending"],
        "cancel_unused": ["cancel", "unused", "under"],
        "setup_expense_tracker": ["tracker", "shared", "team"],
        "schedule_mentorship": ["mentorship", "session", "bi-weekly"],
        "find_conference": ["conference", "attend", "find"],
        "delegate_ownership": ["ownership", "sprint", "lead"],
        "schedule_review": ["review", "progress", "3 months"],
        "find_courses": ["course", "online", "learn"],
        "schedule_learning_days": ["learning day", "every two weeks"],
    }

    found = []
    for sub in expected_subs:
        kws = SUB_KEYWORDS.get(sub, [sub.replace("_", " ")])
        if any(kw in combined for kw in kws):
            found.append(sub)

    coverage = len(found) / len(expected_subs) if expected_subs else 1.0
    return found, coverage


def _check_entity_resolution(hypothesis: str, all_hyps: list, expected_entities: list) -> tuple:
    """Check if expected entities were resolved in the output."""
    if not expected_entities:
        return [], 1.0

    combined = hypothesis.lower()
    for h in all_hyps:
        combined += " " + h.get("hypothesis", "").lower()
        dims = h.get("dimensions", {})
        combined += " " + " ".join(str(v) for v in dims.values()).lower()

    resolved = [e for e in expected_entities if e.lower() in combined]
    coverage = len(resolved) / len(expected_entities)
    return resolved, coverage


async def _persist_v2_run() -> None:
    from core.database import get_db
    db = get_db()
    if not _current_v2_run:
        return
    doc = {
        "run_id": _current_v2_run.run_id,
        "version": "v2",
        "started_at": _current_v2_run.started_at,
        "completed_at": _current_v2_run.completed_at,
        "total": _current_v2_run.total,
        "intent_correct": _current_v2_run.intent_correct,
        "intent_accuracy": _current_v2_run.intent_accuracy,
        "avg_sub_intent_coverage": _current_v2_run.avg_sub_intent_coverage,
        "avg_entity_coverage": _current_v2_run.avg_entity_coverage,
        "per_intent": _current_v2_run.per_intent,
        "avg_latency_ms": round(_current_v2_run.avg_latency_ms, 1),
        "cases": _current_v2_run.cases,
        "failures": _current_v2_run.failures,
    }
    await db.intent_rl_runs.replace_one({"run_id": _current_v2_run.run_id}, doc, upsert=True)
