# MyndLens — Feb 20, 2026 (Updated)

## What Was Built

### The Core Architecture
LLM-driven, Digital Self-powered mandate pipeline. Zero hardcoding.

### The Pipeline:
```
User speaks → STT (Deepgram)
  → Gap Filler (enriches with Digital Self context)
  → L1 Scout: Extracts REAL intent ("Travel Concierge", not an enum)
  → Mandate Dimension Extractor: Execution-level dims, source-tagged
  → Micro-Question Generator: Max 3 whispers for missing dims
  → User responds → Mandate Completion Loop → re-extract until DEFINITIVE
  → Post-Mandate DS Learning: preferences stored back into Digital Self
  → L2 Sentry: Shadow verification
  → Skill Determination: LLM reads 73-skill library, decides what skills needed
  → QC Sentry: Adversarial safety check
  → Dispatch to execution
  → TTS speaks response (ElevenLabs)
```

### Key Principles
1. **ZERO HARDCODING** — The LLM decides everything.
2. **Intent is REAL** — "Travel Concierge", "Event Planning". NOT enum buckets.
3. **Mandate = Intent + Dimensions**.
4. **Digital Self is the product**.

---

## COMPLETED WORK (Feb 20, 2026)

### ✅ P0: Codebase-wide rename `action_class` → `intent`
Completed across ALL live pipeline files (25 files total):
- `l1/scout.py` — Hypothesis dataclass (action_class field removed), store_draft, get_draft
- `l2/sentry.py` — L2Verdict.intent, run_l2_sentry(l1_intent=), _parse_l2_response reads data.get('intent')
- `gateway/ws_server.py` — Uses l1_intent, l2.intent, qc_sentry(intent=), removed from draft_payload
- `server.py` — L2RunRequest.l1_intent, QCRunRequest.intent, CreateCommitRequest.intent
- `qc/sentry.py` — run_qc_sentry(intent=...)
- `qc/agent_topology.py` — assess_agent_topology removes action_class param
- `skills/library.py` — match_skills_to_intent removes action_class param
- `skills/reinforcement.py` — record_skill_outcome removes action_class param
- `commit/state_machine.py` — create_commit(intent=), stored as 'intent' in MongoDB
- `dispatcher/dispatcher.py` + `http_client.py` — intent field in MIO payload
- All `intent_rl/` files — runner, runner_v2, rl_loop, full_pipeline_test, __init__.py
- Test files updated accordingly

### ✅ P1: Remove _mock_l1 fallback from production path
- `run_l1_scout` error handler now uses `raise` instead of returning mock
- `is_mock_llm() or not EMERGENT_LLM_KEY` now raises RuntimeError
- `_mock_l1` function kept for test compatibility only, not called in production

**Testing: 34/34 backend tests PASSED (Feb 20, 2026)**

---

## UPCOMING TASKS (Priority Order)

### P2: Build and test final production APK
Critical for user validation of extensive backend changes.

### P3: Activate On-device Native Modules
Integrate stubbed logic for expo-contacts and expo-calendar (Tier 1 data ingestion).

## FUTURE TASKS (Backlog)

- Implement Digital Twin Module
- Implement Explainability UI for the Digital Self
- Add auth to /api/onboarding/* endpoints (deferred pending SSO decision)

---

## Architecture

```
/app
├── backend/
│   ├── l1/scout.py          # L1 Scout: Hypothesis.intent (NL string)
│   ├── l2/sentry.py         # L2Verdict.intent (NL string)
│   ├── gateway/ws_server.py # WS orchestrator
│   ├── qc/sentry.py         # QC Sentry: intent param
│   ├── commit/state_machine.py # Commits store 'intent' field
│   ├── dispatcher/          # MIO payload uses 'intent'
│   ├── skills/library.py    # 73 skills, no action_class filter
│   ├── skills/reinforcement.py # Outcome tracking by intent
│   ├── intent_rl/           # RL training data: intent_category key
│   └── server.py            # All API models use 'intent'
```

## Key DB Schema
- **l1_drafts**: stores `intent` (NL string), `dimensions`, no `action_class`
- **commits**: stores `intent` (NL string), replaces old `action_class`
- **intent_corrections**: RL feedback for prompt system
- **skills_library**: usage_log entries use `intent` field

## 3rd Party Integrations
- Deepgram (STT) — requires user API key
- ElevenLabs (TTS) — requires user API key
- Google Gemini (LLM) — uses Emergent LLM Key
- ClawHub Skills Ecosystem — 73 skills
- `dispatcher/dispatcher.py` — reads from mio dict
- `dispatcher/http_client.py` — function parameter and payload field
- `server.py` — multiple REST API request/response schemas
- `gateway/ws_server.py` — execute path references

### Other Cleanup Needed
- `prompting/call_sites.py` — entire file is dead code (gateway no longer enforces it), can be deleted
- `dimensions/engine.py` — old A-set/B-set system, no longer imported by live pipeline
- `guardrails/engine.py` — `check_guardrails()` function with hardcoded thresholds is dead code (WS pipeline now calls `_assess_harm_llm` directly)
- `intent/micro_questions.py` — old micro-question module (superseded by `intent/mandate_questions.py`), still imported by WS pipeline's Step 1.5

---

## Files Created/Modified Today

### New Files
| File | Purpose |
|------|---------|
| `intent_rl/__init__.py` | v1 dataset: 100 single-sentence test cases (OBSOLETE — v2 supersedes) |
| `intent_rl/runner.py` | v1 RL runner with action_class scoring (OBSOLETE) |
| `intent_rl/dataset_v2.py` | v2 dataset: 40 broken-thought cases with main intent + sub-intents |
| `intent_rl/runner_v2.py` | v2 runner: scores intent match + sub-intent coverage + entity resolution |
| `intent_rl/seed_digital_self.py` | Seeds test user's Digital Self (11 entities + 27 facts) |
| `intent_rl/rl_loop.py` | 10-iteration RL training loop, stores corrections in prompt engine |
| `intent_rl/full_pipeline_test.py` | Full pipeline test: L1 → Dims → L2 → QC |
| `intent/micro_questions.py` | OLD micro-question generator (intent-level, not mandate-level) |
| `intent/mandate_questions.py` | NEW mandate-driven question generator (clubbed, max 3, DS-powered) |
| `dimensions/extractor.py` | REWRITTEN: Intent-driven, execution-level dimension extraction |
| `skills/determine.py` | LLM-driven skill determination from 73-skill library |
| `memory/post_mandate_learning.py` | Post-mandate DS learning (every completed mandate feeds back) |
| `prompting/sections/standard/learned_examples.py` | Few-shot corrections section for prompt engine |
| `prompting/sections/standard/output_schema.py` | REWRITTEN: Real intent schema, not action_class enum |
| `CODEBASE_AUDIT_REPORT.md` | Comprehensive spec-vs-code gap analysis |

### Deleted Files
| File | Reason |
|------|--------|
| `agents/predefined.py` | 14 hardcoded agents with action_class triggers |
| `agents/selector.py` | Hardcoded action_class → agent mapping |
| `agents/composer.py` | Hardcoded agent assembly |

### Significantly Modified Files
| File | Changes |
|------|---------|
| `gateway/ws_server.py` | Replaced entire mandate pipeline: old DimensionState → new mandate extractor, old hardcoded responses → LLM-generated from mandate, old skill matching → LLM skill determination, deleted _generate_l1_response, _generate_mock_response, action_preview |
| `l1/scout.py` | New Hypothesis schema (intent + sub_intents), new parser, cleaned mock, fixed store_draft |
| `l2/sentry.py` | Prompt now extracts real intent (not forced taxonomy), cleaned mock |
| `guardrails/engine.py` | Cleaned mock (removed OBVIOUS_HARM keyword list) |
| `schemas/mio.py` | Deleted ActionClass enum, replaced with `intent: str` |
| `prompting/llm_gateway.py` | Removed CallSite registry enforcement (Hard Gate 2 + 3) |
| `prompting/registry.py` | Added LEARNED_EXAMPLES section |
| `prompting/types.py` | Added LEARNED_EXAMPLES SectionID, MICRO_QUESTION PromptPurpose |
| `prompting/call_sites.py` | Dead code — gateway no longer enforces it |
| `prompting/policy/engine.py` | Added MICRO_QUESTION policy |
| `tts/provider/elevenlabs.py` | Tuned voice_settings for warm secretary tone |
| `server.py` | Added 15+ new REST endpoints for mandate/build, mandate/complete, mandate/skills, intent-rl/*, pipeline/test/* |

---

## API Endpoints Added Today

### Mandate Pipeline
- `POST /api/mandate/build` — Full pipeline: transcript → intent → dimensions → questions
- `POST /api/mandate/complete` — Completion loop: answers → re-extract → DS learning
- `POST /api/mandate/skills` — LLM skill determination from 73-skill library

### Intent RL Testing
- `POST /api/intent-rl/run` — v1 batch test (100 cases)
- `POST /api/intent-rl/v2/run` — v2 batch test (40 broken-thought cases)
- `POST /api/intent-rl/loop/start` — 10-iteration RL training loop
- `GET /api/intent-rl/loop/status` — Live progression
- `POST /api/intent-rl/seed` — Seed Digital Self for testing

### Micro-Questions
- `POST /api/intent/micro-questions/test` — Test micro-question generation
- `POST /api/intent/clarification-loop/test` — Test full clarification loop

### Full Pipeline
- `POST /api/pipeline/test/run` — Test all stages: L1 → Dims → L2 → QC
- `GET /api/pipeline/test/status` — Live progress
- `GET /api/pipeline/test/results` — Case-by-case results

---

## RL Training Results

### v1 (single-sentence, action_class buckets — OBSOLETE approach):
| Round | Accuracy | Change |
|-------|----------|--------|
| R1 (8-class taxonomy) | 65.0% | Baseline |
| R2 (11-class taxonomy) | 91.0% | +26pp |
| R3 (with Digital Self) | 93.0% | +2pp |

### v2 (broken-thoughts, real intent — CURRENT approach):
| Metric | Score |
|--------|-------|
| Intent Accuracy | 90.0% |
| Sub-Intent Coverage | 91.5% |
| Entity Resolution | 98.8% |

### 10-Iteration RL Loop:
Average intent accuracy: 83.8% across 10 runs, with corrections stored in prompt engine (`intent_corrections` MongoDB collection → `LEARNED_EXAMPLES` prompt section).

---

## Digital Self State
The test user (`rl_test_user`) has 273 vectors in the Digital Self including:
- 11 entities (Sarah Johnson, Bob Chen, Mike Wilson, Lisa Anderson, Jacob Martinez, Soudha, Alex Kim, etc.)
- 27+ facts (preferences, routines, patterns, financial info)
- Travel preferences (JFK departure, window seat, vegetarian, Qantas FF, Hilton, Hertz)
- Work patterns (daily standup, Wednesday sync, Friday deep work)

---

## What the Next Agent Must Do FIRST

1. **Rename `action_class` → `intent`** across all 12 files listed above. This is P0 — the field name is misleading and dangerous.

2. **Delete dead code files**: `prompting/call_sites.py`, `dimensions/engine.py`, `guardrails/engine.py check_guardrails()`, old `intent/micro_questions.py`

3. **Wire `intent/mandate_questions.py`** into the WebSocket pipeline Step 1.5 (currently still uses old `intent/micro_questions.py`)

4. **Clean `intent_rl/` v1 files**: `__init__.py` (v1 dataset), `runner.py` (v1 runner) are obsolete — v2 is the active version

---

## Architecture

```
/app/backend/
├── gateway/ws_server.py        # WebSocket pipeline (UNIFIED — uses new mandate flow)
├── l1/scout.py                 # L1 Scout (real intent extraction)
├── l2/sentry.py                # L2 Shadow verification
├── qc/sentry.py                # QC Adversarial check
├── intent/
│   ├── gap_filler.py           # Enriches fragments with DS context
│   ├── micro_questions.py      # OLD — still imported by WS Step 1.5
│   └── mandate_questions.py    # NEW — clubbed questions from mandate dims
├── dimensions/
│   ├── engine.py               # OLD — dead code
│   └── extractor.py            # NEW — intent-driven execution-level dims
├── skills/
│   ├── library.py              # 73-skill library (JSON + search)
│   ├── determine.py            # NEW — LLM-driven skill determination
│   └── reinforcement.py        # Skill RL (uses action_class — needs rename)
├── memory/
│   ├── retriever.py            # Digital Self recall + store
│   └── post_mandate_learning.py # NEW — DS learns from completed mandates
├── prompting/
│   ├── orchestrator.py         # Prompt builder
│   ├── llm_gateway.py          # LLM call gate (CallSite enforcement REMOVED)
│   ├── call_sites.py           # DEAD CODE — no longer enforced
│   ├── sections/standard/
│   │   ├── output_schema.py    # REWRITTEN — real intent schema
│   │   └── learned_examples.py # NEW — few-shot corrections from RL
│   └── policy/engine.py        # Purpose policies (MICRO_QUESTION added)
├── intent_rl/
│   ├── __init__.py             # v1 dataset (OBSOLETE)
│   ├── runner.py               # v1 runner (OBSOLETE)
│   ├── dataset_v2.py           # 40 broken-thought test cases
│   ├── runner_v2.py            # v2 scorer
│   ├── rl_loop.py              # 10-iteration training loop
│   ├── seed_digital_self.py    # Test DS seeder
│   └── full_pipeline_test.py   # Full pipeline tester
├── agents/
│   ├── builder.py              # Agent CREATE (kept)
│   ├── unhinged.py             # Demo agents (kept)
│   └── workspace.py            # Workspace agents (kept)
│   # DELETED: predefined.py, selector.py, composer.py
├── guardrails/engine.py        # LLM harm check (mock cleaned, check_guardrails dead)
├── tts/provider/elevenlabs.py  # Tuned voice settings for secretary tone
└── server.py                   # FastAPI entry (~1900 lines, 15+ new endpoints)
```

---

## 3rd Party Integrations
- **Google Gemini 2.0 Flash** — all LLM calls via Emergent LLM Key
- **Deepgram** — STT (live)
- **ElevenLabs** — TTS (live, voice settings tuned)
- **MongoDB** — all persistence
- **ChromaDB** — Digital Self vector store (on-device ONNX embeddings)

## Key MongoDB Collections
- `intent_corrections` — RL corrections stored in prompt engine (not Digital Self)
- `intent_rl_runs` — Historical RL run results
- `intent_rl_loop` — RL loop iteration data
- `l1_drafts` — L1 Scout drafts (now stores `intent` + `sub_intents`)
- `prompt_snapshots` — Every prompt built (audit trail)
- `prompt_outcomes` — Outcome tracking for RL
