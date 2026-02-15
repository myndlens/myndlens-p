# MyndLens - Product Requirements Document (Consolidated)

> Last Updated: February 2026
> Version: 5.0 (Post-ObeGee Audit Implementation)

## System Grade Progression
- **Pre-Implementation:** D (45/100) — 29% feature completeness
- **Post Phase 0-4:** B+ (85/100) — 85%+ feature completeness
- **Target:** A (95/100)

---

## 0. NON-NEGOTIABLE META-PRINCIPLES (6 Laws)
1. **No Drift**: Nothing may deviate from spec without an ADR
2. **No Hallucination**: No invented APIs, fields, flows, or capabilities
3. **Sovereignty First**: Execution authority is centralized, auditable, revocable
4. **Isolation by Design**: Isolation enforced at IP, proxy, network, data, secrets, keys
5. **Human-in-the-loop for risk**: Irreversible/sensitive actions require physical latch
6. **To-the-point behavior**: System avoids data dumps; uses minimal clarifying nudges

---

## WHAT'S BEEN IMPLEMENTED

### Phase 0: Critical Fixes (COMPLETE - Feb 2026)
- **Digital Self Integration**: Memory recall section generator (`memory_recall.py`) created, registered in `SectionRegistry`, wired into L1 Scout and L2 Sentry. Prompts now include `MEMORY_RECALL_SNIPPETS`.
- **Onboarding Wizard**: Backend API (`/api/onboarding/*`) and frontend Expo screen created. Stores name, timezone, communication style, contacts (as entities), and routines in Digital Self.
- **Landing Page**: N/A for mobile app (Expo/React Native).

### Phase 1: Core Functionality (COMPLETE - Feb 2026)
- **Outcome Tracking**: `PromptOutcome` schema, `track_outcome` API, user correction capture. MongoDB collection `prompt_outcomes`.
- **Analytics Engine**: Purpose-level accuracy, section effectiveness scoring, optimization insights dashboard.
- **Dedicated Dimension Extraction**: `dimensions/extractor.py` using `DIMENSIONS_EXTRACT` purpose with Digital Self entity resolution. Registered as `DIMENSION_EXTRACTOR` call site.

### Phase 2: Continuous Improvement (COMPLETE - Feb 2026)
- **A/B Testing Framework**: `experiments.py` with experiment creation, variant assignment, outcome recording, and statistical significance analysis.
- **Experiment APIs**: Create, list, and get results with winner detection.

### Phase 3: Advanced Features (COMPLETE - Feb 2026)
- **Adaptive Policy Engine**: `policy/adaptive.py` generates policy recommendations based on outcome data (accuracy thresholds, correction rates, section effectiveness).
- **Insights Dashboard**: System health assessment, recommendation prioritization.

### Phase 4: Agent Builder (COMPLETE - Feb 2026)
- **Full Agent Lifecycle**: CREATE, MODIFY, RETIRE (soft/hard), DELETE (admin-only), UNRETIRE operations.
- **Capability Matching**: Prevents agent proliferation by checking existing agents.
- **State Machine**: ACTIVE ↔ RETIRED → DELETED (irreversible).
- **Safety Gates**: Sensitive tools require explicit approval, DELETE requires admin_only flag.
- **Archive on Delete**: Workspace archived by default, not destroyed.
- **DEMO_UNHINGED Presets**: Two profiles per ObeGee spec:
  - Profile A (HOST_UNHINGED): Full tool access, runs on host
  - Profile B (SANDBOX_UNHINGED): Docker-isolated, recommended
  - 2-step approval gate, soil templates, 8-test validation suite, teardown options

---

## KEY API ENDPOINTS

### Core
- `GET /api/health` — System health
- `WS /api/ws` — WebSocket for mobile client
- `POST /api/sso/myndlens/pair` — 6-digit code pairing (mock in dev)

### Phase 0
- `GET /api/onboarding/status/{user_id}` — Onboarding status
- `POST /api/onboarding/profile` — Save onboarding profile
- `POST /api/onboarding/skip/{user_id}` — Skip onboarding

### Phase 1
- `POST /api/prompt/track-outcome` — Track prompt outcome
- `POST /api/prompt/user-correction` — Record user correction
- `GET /api/prompt/analytics` — Optimization insights
- `GET /api/prompt/analytics/{purpose}` — Purpose-specific metrics
- `GET /api/prompt/section-effectiveness` — Section effectiveness
- `POST /api/dimensions/extract` — Dedicated dimension extraction

### Phase 2
- `POST /api/prompt/experiments` — Create experiment
- `GET /api/prompt/experiments` — List experiments
- `GET /api/prompt/experiments/{id}/results` — Experiment results

### Phase 3
- `GET /api/prompt/adaptive-insights` — Adaptive insights
- `GET /api/prompt/policy-recommendations` — Policy recommendations

### Phase 4
- `POST /api/agents/create` — Create agent
- `POST /api/agents/modify` — Modify agent
- `POST /api/agents/retire` — Retire agent
- `POST /api/agents/delete` — Delete agent (admin-only)
- `POST /api/agents/unretire` — Restore retired agent
- `GET /api/agents/list/{tenant_id}` — List tenant agents
- `GET /api/agents/{agent_id}` — Get single agent

### Prompt Versioning
- `POST /api/prompt/versions` — Create new version
- `GET /api/prompt/versions/{purpose}` — List versions
- `GET /api/prompt/versions/{purpose}/active` — Active version
- `GET /api/prompt/version/{version_id}` — Get specific version
- `POST /api/prompt/versions/rollback` — Rollback to version
- `POST /api/prompt/versions/compare` — Compare two versions

### Per-User Optimization
- `GET /api/user-profile/{user_id}` — Get user profile
- `PUT /api/user-profile/{user_id}` — Update user profile
- `POST /api/user-profile/{user_id}/learn` — Learn from outcomes
- `GET /api/user-profile/{user_id}/adjustments` — Prompt adjustments

### Optimization Scheduler
- `POST /api/optimization/run` — Manual optimization cycle
- `POST /api/optimization/scheduler/start` — Start background scheduler
- `POST /api/optimization/scheduler/stop` — Stop scheduler
- `GET /api/optimization/scheduler/status` — Scheduler status
- `GET /api/optimization/runs` — List run history

### Workspace File I/O
- `POST /api/workspace/create` — Create workspace with soil files
- `GET /api/workspace/{id}/files` — List workspace files
- `GET /api/workspace/{id}/file/{name}` — Read file
- `PUT /api/workspace/{id}/file/{name}` — Write/overwrite file
- `DELETE /api/workspace/{id}/file/{name}` — Delete file
- `GET /api/workspace/{id}/stats` — Workspace stats
- `POST /api/workspace/{id}/archive` — Archive workspace
- `DELETE /api/workspace/{id}` — Delete workspace
- `GET /api/workspace/archives` — List archives

---

## EXISTING BLOCKERS
- ~~ElevenLabs TTS~~ — **RESOLVED** (working with valid API key)

## MOCKED COMPONENTS
- ObeGee SSO pairing (dev mock)
- OpenClaw dispatch adapter (mock)
- LLM fallback to mock when Gemini API unavailable

---

## REMAINING BACKLOG
- Production deployment via ObeGee DAI
- Wire user profile adjustments into PromptOrchestrator (close feedback loop)
- User profile decay (reduce confidence of stale data)
- Prompt version auto-promotion from experiments
