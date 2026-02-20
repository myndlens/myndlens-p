"""LLM Call Site Registry — canonical inventory of every LLM call path.

Every LLM call in MyndLens MUST be registered here.
Unregistered calls are violations and will be blocked by the gateway.

Fail condition: any file calls an LLM client directly without being on this list.
"""
from dataclasses import dataclass
from typing import Dict, FrozenSet, List

from prompting.types import PromptPurpose


@dataclass(frozen=True)
class CallSite:
    """A registered LLM call site."""
    call_site_id: str
    allowed_purposes: FrozenSet[PromptPurpose]
    owner_module: str
    description: str
    status: str = "active"  # active | reserved | deprecated


# ---- Canonical Registry (locked) ----

CALL_SITES: Dict[str, CallSite] = {
    "L1_SCOUT": CallSite(
        call_site_id="L1_SCOUT",
        allowed_purposes=frozenset({PromptPurpose.THOUGHT_TO_INTENT, PromptPurpose.DIMENSIONS_EXTRACT}),
        owner_module="l1.scout",
        description="High-speed intent hypothesis (Gemini Flash). Max 3 hypotheses.",
        status="active",
    ),
    "L2_SENTRY": CallSite(
        call_site_id="L2_SENTRY",
        allowed_purposes=frozenset({PromptPurpose.VERIFY, PromptPurpose.SAFETY_GATE}),
        owner_module="l2.sentry",
        description="Authoritative intent validation (Gemini Pro). Shadow derivation.",
        status="active",
    ),
    "QC_SENTRY": CallSite(
        call_site_id="QC_SENTRY",
        allowed_purposes=frozenset({PromptPurpose.VERIFY}),
        owner_module="qc.sentry",
        description="Adversarial passes: persona drift, capability leak, harm projection.",
        status="active",
    ),
    "GUARDRAILS_CLASSIFIER": CallSite(
        call_site_id="GUARDRAILS_CLASSIFIER",
        allowed_purposes=frozenset({PromptPurpose.SAFETY_GATE}),
        owner_module="guardrails.engine",
        description="LLM harm and policy classification via SAFETY_GATE. Active at extraction time.",
        status="active",
    ),
    "SKILL_RISK_CLASSIFIER": CallSite(
        call_site_id="SKILL_RISK_CLASSIFIER",
        allowed_purposes=frozenset({PromptPurpose.SAFETY_GATE}),
        owner_module="skills.library",
        description="LLM skill risk tier assessment from full SKILL.md content. Async, cached.",
        status="active",
    ),
    "SUMMARIZER": CallSite(
        call_site_id="SUMMARIZER",
        allowed_purposes=frozenset({PromptPurpose.SUMMARIZE}),
        owner_module="gateway.ws_server",
        description="User-facing compression of plans/results.",
        status="reserved",
    ),
    "DIGITAL_SELF_RERANKER": CallSite(
        call_site_id="DIGITAL_SELF_RERANKER",
        allowed_purposes=frozenset({PromptPurpose.VERIFY, PromptPurpose.SUBAGENT_TASK}),
        owner_module="memory.retriever",
        description="LLM-based memory reranking (if needed). Read-only.",
        status="reserved",
    ),
    "DIMENSION_EXTRACTOR": CallSite(
        call_site_id="DIMENSION_EXTRACTOR",
        allowed_purposes=frozenset({PromptPurpose.DIMENSIONS_EXTRACT}),
        owner_module="dimensions.extractor",
        description="Dedicated dimension extraction with Digital Self integration.",
        status="active",
    ),
    "SUBAGENT_TASK": CallSite(
        call_site_id="SUBAGENT_TASK",
        allowed_purposes=frozenset({PromptPurpose.SUBAGENT_TASK}),
        owner_module="subagent",
        description="Minimal mode narrow sub-tasks.",
        status="reserved",
    ),
}


def get_call_site(call_site_id: str) -> CallSite:
    """Get a registered call site. Raises if not found."""
    site = CALL_SITES.get(call_site_id)
    if site is None:
        raise ValueError(f"Unregistered LLM call site: {call_site_id}")
    return site


def validate_purpose(call_site_id: str, purpose: PromptPurpose) -> None:
    """Validate that a purpose is allowed for a call site."""
    site = get_call_site(call_site_id)
    if purpose not in site.allowed_purposes:
        raise ValueError(
            f"Purpose {purpose.value} not allowed for call site {call_site_id}. "
            f"Allowed: {[p.value for p in site.allowed_purposes]}"
        )


def list_all() -> List[dict]:
    """List all registered call sites."""
    return [
        {
            "call_site_id": s.call_site_id,
            "allowed_purposes": [p.value for p in s.allowed_purposes],
            "owner_module": s.owner_module,
            "description": s.description,
            "status": s.status,
        }
        for s in CALL_SITES.values()
    ]
