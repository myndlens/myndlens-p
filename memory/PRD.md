# MyndLens Handoff — February 20, 2026

## What Was Built Today

### The Core Architecture Shift
We fundamentally rewired MyndLens from a hardcoded action-class bucket system to a fully LLM-driven, Digital Self-powered mandate pipeline. Every decision is now made by the LLM using examples as reference — zero hardcoding.

### The Pipeline (as it should work end-to-end):
```
User speaks broken thoughts
  → STT (Deepgram)
  → Gap Filler (enriches with Digital Self context)
  → L1 Scout: Extracts REAL intent ("Travel Concierge", not "SCHED_MODIFY")
  → Mandate Dimension Extractor: Execution-level dimensions, source-tagged
       Each dim tagged: [USER] stated | [DS] Digital Self | [INF] inferred | [???] missing
  → Micro-Question Generator: Max 3 clubbed whispers for ALL missing dims
       Secretary tone, max 6 words, DS-powered, never generic
  → User responds → Mandate Completion Loop → re-extract until DEFINITIVE
  → Post-Mandate DS Learning: every stated preference stored back into Digital Self
  → L2 Sentry: Shadow verification
  → Skill Determination: LLM reads 73-skill library, decides what skills needed
       Execution methods: api / browser / hybrid / manual
  → QC Sentry: Adversarial safety check
  → Dispatch to execution
  → TTS speaks response (warm secretary tone, ElevenLabs with tuned voice settings)
```

### Key Principles Established
1. **ZERO HARDCODING** without explicit user permission. The LLM decides everything — intents, dimensions, questions, skills, options. Libraries and schemas are EXAMPLES, not enforced templates.
2. **Intent is the REAL intent** — "Travel Concierge", "Event Planning", "Hiring Pipeline". NOT action_class buckets like COMM_SEND/SCHED_MODIFY.
3. **Mandate = Intent + Dimensions**. A mandate cannot execute with any missing dimension.
4. **Digital Self is the product**. The richer it gets, the fewer questions needed. Trip 1: 30 questions. Trip 10: 0 questions.
5. **TTS never breaks chain of thought**. Max 6 words. Secretary whisper. Clubbed into max 3 questions.
6. **Browser scraping is always available** as execution method when no API exists.

---

## CRITICAL UNFINISHED WORK

### P0: `action_class` → `intent` rename across 12 files
The field name `action_class` still exists throughout the codebase as parameter names, field names, API schemas, and database fields. The VALUE is now the real intent ("Travel Concierge"), but the FIELD NAME still says `action_class`. This is dangerous — any code that checks `if action_class == "COMM_SEND"` will silently fail.

**Files that need the rename:**
- `l1/scout.py` — Hypothesis dataclass field, parser, store_draft
- `l2/sentry.py` — L2Verdict dataclass, function params, defaults ("DRAFT_ONLY"), parse function
- `qc/sentry.py` — function parameter
- `qc/agent_topology.py` — function parameter
- `skills/library.py` — match_skills_to_intent parameter
- `skills/reinforcement.py` — record_skill_outcome parameter and DB field
- `commit/state_machine.py` — function parameter and DB field
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
