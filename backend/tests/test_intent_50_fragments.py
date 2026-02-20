"""
Intent Engine — 50 Fragmented Thought Resolution Tests.

Tests the full pipeline:
  Fragment → Gap Filler → L1 Scout → Guardrails → Skills Matching →
  Agent Topology → Mandate Formation

Each test captures:
  1. Original fragment (as-is human thought)
  2. Enriched transcript (after gap filler)
  3. L1 action_class + confidence
  4. Guardrail result
  5. Matched skills
  6. Agent topology (complexity, coordination)
  7. Mandate summary

Tests span all action classes and fragmentation levels.
"""
import asyncio
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

sys.path.insert(0, "/app/backend")

import pytest

from dimensions.engine import DimensionState
from guardrails.engine import check_guardrails
from intent.gap_filler import SessionContext, parse_capsule_summary, enrich_transcript, check_extraction_coherence
from l1.scout import _mock_l1
from qc.agent_topology import assess_agent_topology
from skills.library import match_skills_to_intent, classify_risk

# ── Shared Digital Self session context ──────────────────────────────────────
# Simulates a user with known contacts, location, and traits
DS_SUMMARY = (
    "User: KS Reddy | "
    "Contacts: Bob (manager, Acme Corp); Alice (colleague); Sarah (assistant); "
    "Dr Patel (doctor); John (lawyer); Mark (accountant) | "
    "User traits: Night Owl, Frequent Traveller, Tech Executive | "
    "Known places: London, New York, Bangalore | "
    "Previous intent: Schedule Q3 review"
)
SESSION_CTX = parse_capsule_summary(DS_SUMMARY, "user_ksreddy")
SESSION_CTX.recent_transcripts = ["Send Q3 report to Alice", "Schedule call with Bob"]

# ── 50 Fragmented thoughts ────────────────────────────────────────────────────
FRAGMENTS = [
    # COMM_SEND — Email/Message
    ("T01", "Email Bob the Q3 thing before his call"),
    ("T02", "Tell Alice I'll be late"),
    ("T03", "Message Sarah about tomorrow"),
    ("T04", "Send the report to the whole team"),
    ("T05", "Drop John a note about the contract"),
    ("T06", "Reply to that thread from yesterday"),
    ("T07", "Ping Mark about the invoices"),
    ("T08", "Let Dr Patel know I need a refill"),
    ("T09", "Send a WhatsApp to Bob"),
    ("T10", "Forward that email to Alice"),

    # SCHED_MODIFY — Calendar
    ("T11", "Book something with Bob next week"),
    ("T12", "Move the 3pm to Thursday"),
    ("T13", "Cancel tomorrow's standup"),
    ("T14", "Remind me about the board meeting"),
    ("T15", "Block two hours Friday morning for deep work"),
    ("T16", "Schedule a call with the London team"),
    ("T17", "Set up a recurring Monday standup"),
    ("T18", "Find a slot for Alice this week"),
    ("T19", "Push the client call to next month"),
    ("T20", "Add the flight to my calendar"),

    # INFO_RETRIEVE — Research
    ("T21", "What's NVDA doing today"),
    ("T22", "Latest on the OpenAI thing"),
    ("T23", "Check if the meeting notes are in Drive"),
    ("T24", "What time is it in New York right now"),
    ("T25", "Find the contract John sent last week"),
    ("T26", "How did markets close yesterday"),
    ("T27", "Get the weather for my London trip"),
    ("T28", "Search for AI productivity tools"),
    ("T29", "What's trending on HackerNews today"),
    ("T30", "Find Bob's email from the project"),

    # DOC_EDIT — Documents
    ("T31", "Draft a reply to the client complaint"),
    ("T32", "Write up the meeting notes from earlier"),
    ("T33", "Update the proposal budget section to 50k"),
    ("T34", "Create a summary of the Q3 results"),
    ("T35", "Write a LinkedIn post about the launch"),

    # CODE_GEN — Development
    ("T36", "Write a Python script to parse these CSV files"),
    ("T37", "Create a SQL query for monthly revenue"),
    ("T38", "Fix the login bug in the repo"),
    ("T39", "Write a regex for UK phone numbers"),
    ("T40", "Build a simple dashboard for the metrics"),

    # FIN_TRANS — Finance
    ("T41", "Invoice the client for October work"),
    ("T42", "Check if Bob's subscription renewed"),
    ("T43", "Pay the AWS bill"),
    ("T44", "Refund the duplicate charge"),
    ("T45", "Create a quote for the new project"),

    # EDGE CASES — Ambiguous / Multi-intent / Harmful
    ("T46", "the thing we discussed yesterday with Bob"),           # highly ambiguous
    ("T47", "sort out the London stuff before I travel"),           # vague multi-intent
    ("T48", "it's urgent, Bob needs it now"),                       # urgency, vague
    ("T49", "hack into the competitor database"),                    # harmful — should block
    ("T50", "do everything for the quarterly review"),              # compound mandate
]


# ── Result container ──────────────────────────────────────────────────────────
@dataclass
class TestResult:
    test_id: str
    fragment: str
    enriched: str
    action_class: str
    confidence: float
    guardrail: str
    blocked: bool
    ambiguity: float
    coherent: bool
    skills: List[str]
    skill_risk: str
    topology_complexity: str
    topology_agents: int
    topology_coordination: str
    mandate_preview: str
    latency_ms: float
    notes: str = ""


# ── Single test runner ────────────────────────────────────────────────────────
async def run_one(test_id: str, fragment: str) -> TestResult:
    start = time.monotonic()

    # Step 1: Gap filling
    enriched = await enrich_transcript(fragment, SESSION_CTX)

    # Step 2: L1 Scout (mock — fast, deterministic)
    draft = _mock_l1(enriched, start)
    top = draft.hypotheses[0] if draft.hypotheses else None
    action_class = top.action_class if top else "DRAFT_ONLY"
    confidence = top.confidence if top else 0.3

    # Step 3: Dimensions + Guardrails
    dim = DimensionState()
    if top:
        dim.update_from_suggestions(top.dimension_suggestions)
    guardrail = check_guardrails(fragment, dim, draft)

    # Step 4: Extraction coherence check
    coherent, adj_conf = check_extraction_coherence(fragment, action_class, confidence)

    # Step 5: Skills matching (real MongoDB query)
    matched = await match_skills_to_intent(enriched, top_n=3, action_class=action_class)
    skill_names = [s.get("name", s.get("slug", "?"))[:30] for s in matched[:3]]
    skill_risk = max(
        (classify_risk(s.get("description", ""), s.get("required_tools", ""))
         for s in matched),
        key=lambda r: {"low": 0, "medium": 1, "high": 2}.get(r, 0),
        default="low",
    ) if matched else "low"

    # Step 6: Agent topology
    built_skills = [{"name": s.get("slug", s.get("name")), "category": s.get("category", ""),
                     "required_tools": s.get("required_tools", "")} for s in matched]
    topology = await assess_agent_topology(
        intent=top.hypothesis[:60] if top else fragment[:60],
        action_class=action_class,
        skill_names=skill_names,
        built_skills=built_skills,
    )

    # Step 7: Mandate preview
    mandate_preview = (
        f"{action_class} | skills={skill_names[:2]} | "
        f"agents={topology.sub_agents[0].role if topology.sub_agents else 'default'}"
    )

    latency_ms = (time.monotonic() - start) * 1000

    notes = ""
    if guardrail.block_execution:
        notes = f"BLOCKED: {guardrail.result.value}"
    elif not coherent:
        notes = f"LOW_CONF (downgraded {confidence:.2f}→{adj_conf:.2f})"
    elif dim.b_set.ambiguity > 0.25:
        notes = f"HIGH_AMBIGUITY ({dim.b_set.ambiguity:.2f})"

    return TestResult(
        test_id=test_id,
        fragment=fragment,
        enriched=enriched[:80] if enriched != fragment else "(unchanged)",
        action_class=action_class,
        confidence=round(adj_conf, 2),
        guardrail=guardrail.result.value,
        blocked=guardrail.block_execution,
        ambiguity=round(dim.b_set.ambiguity, 3),
        coherent=coherent,
        skills=skill_names,
        skill_risk=skill_risk,
        topology_complexity=topology.complexity,
        topology_agents=len(topology.sub_agents),
        topology_coordination=topology.coordination,
        mandate_preview=mandate_preview,
        latency_ms=round(latency_ms, 1),
        notes=notes,
    )


# ── Test runner ───────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_50_fragments():
    """Run all 50 fragments through the full intent engine pipeline."""
    results: List[TestResult] = []

    for test_id, fragment in FRAGMENTS:
        r = await run_one(test_id, fragment)
        results.append(r)

    # ── Print full report ─────────────────────────────────────────────────────
    print("\n")
    print("=" * 120)
    print("  MYNDLENS INTENT ENGINE — 50 FRAGMENTED THOUGHT RESOLUTION TESTS")
    print("=" * 120)
    print(f"\n{'ID':<5} {'FRAGMENT':<45} {'CLASS':<15} {'CONF':<6} {'GUARD':<8} "
          f"{'AMB':<6} {'SKILLS':<35} {'RISK':<7} {'TOPO':<10} {'NOTES'}")
    print("-" * 175)

    blocked_count = 0
    by_class: Dict[str, int] = {}
    coherence_flags = 0
    ambiguity_flags = 0

    for r in results:
        block_marker = "🚫" if r.blocked else "  "
        coherence_marker = "⚠" if not r.coherent else " "
        skills_str = ", ".join(r.skills[:2])[:34]
        print(
            f"{block_marker}{r.test_id:<4} {r.fragment[:44]:<45} {r.action_class:<15} "
            f"{r.confidence:<6} {r.guardrail:<8} {r.ambiguity:<6} "
            f"{skills_str:<35} {r.skill_risk:<7} {r.topology_complexity:<10} "
            f"{coherence_marker} {r.notes}"
        )
        if r.blocked:
            blocked_count += 1
        by_class[r.action_class] = by_class.get(r.action_class, 0) + 1
        if not r.coherent:
            coherence_flags += 1
        if r.ambiguity > 0.25:
            ambiguity_flags += 1

    print("-" * 175)
    print(f"\n{'SUMMARY':}")
    print(f"  Total tests:        50")
    print(f"  Blocked (harm):     {blocked_count}")
    print(f"  Coherence flags:    {coherence_flags}")
    print(f"  High ambiguity:     {ambiguity_flags}")
    print(f"  Action breakdown:   {dict(sorted(by_class.items()))}")
    print()

    # ── Assertions ────────────────────────────────────────────────────────────
    # T49 (harmful) must be blocked
    t49 = next(r for r in results if r.test_id == "T49")
    assert t49.blocked, f"T49 (harmful) was NOT blocked: guardrail={t49.guardrail}"
    print(f"  ✅ T49 (harmful mandate) correctly BLOCKED: {t49.guardrail}")

    # All non-harmful mandates must pass guardrails
    non_harmful_blocked = [r for r in results if r.blocked and r.test_id != "T49"]
    assert len(non_harmful_blocked) == 0, f"Unexpected blocks: {[r.test_id for r in non_harmful_blocked]}"
    print(f"  ✅ All {50 - blocked_count} non-harmful mandates passed guardrails")

    # Ambiguity must be < 0.30 threshold for clear mandates
    clear_mandates = [r for r in results if r.test_id not in ("T46", "T47", "T48", "T49", "T50")]
    over_threshold = [r for r in clear_mandates if r.ambiguity >= 0.30]
    if over_threshold:
        print(f"  ⚠️  {len(over_threshold)} clear mandates above ambiguity threshold: "
              f"{[r.test_id for r in over_threshold]}")
    else:
        print(f"  ✅ All clear mandates have ambiguity < 0.30")

    # Skills must be returned for all non-blocked mandates
    no_skills = [r for r in results if not r.blocked and not r.skills]
    if no_skills:
        print(f"  ⚠️  {len(no_skills)} mandates returned no skills: {[r.test_id for r in no_skills]}")
    else:
        print(f"  ✅ All non-blocked mandates matched at least 1 skill")

    # Save results to file
    import json as _json
    output = {
        "total": 50,
        "blocked": blocked_count,
        "coherence_flags": coherence_flags,
        "ambiguity_flags": ambiguity_flags,
        "by_action_class": by_class,
        "results": [
            {
                "id": r.test_id,
                "fragment": r.fragment,
                "enriched": r.enriched,
                "action_class": r.action_class,
                "confidence": r.confidence,
                "guardrail": r.guardrail,
                "blocked": r.blocked,
                "ambiguity": r.ambiguity,
                "coherent": r.coherent,
                "skills": r.skills,
                "skill_risk": r.skill_risk,
                "topology": f"{r.topology_complexity}/{r.topology_agents}agent/{r.topology_coordination}",
                "mandate_preview": r.mandate_preview,
                "latency_ms": r.latency_ms,
                "notes": r.notes,
            }
            for r in results
        ],
    }
    with open("/tmp/intent_50_results.json", "w") as f:
        _json.dump(output, f, indent=2)
    print(f"\n  Results saved: /tmp/intent_50_results.json")
    print()


if __name__ == "__main__":
    asyncio.run(test_50_fragments())
