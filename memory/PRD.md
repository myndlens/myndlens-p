# MyndLens - Product Requirements Document (Consolidated)

> Last Updated: February 2026
> Version: 6.0 (Post-Comprehensive Audit)

## System Grade Progression
- **Pre-Implementation:** D (45/100) — 29% feature completeness
- **Post Phase 0-4:** B+ (85/100) — 85%+ feature completeness
- **Post Audit:** A- (88/100) — All spec requirements accounted for
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

### Phase 0: Critical Fixes (COMPLETE)
- Digital Self Integration: Memory recall section, L1/L2 enrichment, gap filler engine
- Onboarding Wizard: Backend API + mobile 5-step wizard
- Landing Page: N/A (mobile app)

### Phase 1: Core Functionality (COMPLETE)
- Outcome Tracking: Schema, API, analytics, user corrections
- Analytics Engine: Purpose-level accuracy, section effectiveness
- Dedicated Dimension Extraction: `dimensions/extractor.py` using DIMENSIONS_EXTRACT

### Phase 2: Continuous Improvement (COMPLETE)
- A/B Testing Framework: Experiments, variants, statistical significance
- Experiment APIs: Create, list, results with winner detection

### Phase 3: Advanced Features (COMPLETE)
- Adaptive Policy Engine: Recommendations, insights dashboard
- Per-user optimization profiles

### Phase 4: Agent Builder (COMPLETE)
- Full lifecycle: CREATE/MODIFY/RETIRE/DELETE/UNRETIRE
- Capability matching, state machine, safety gates
- DEMO_UNHINGED presets (Profile A: Host, Profile B: Sandbox)

### Additional (COMPLETE)
- Dynamic Agent Composition: Catalogue assembly + skill composition
- ClawHub Skill Ingestion: 73 skills indexed from 11 categories
- Hardcoding Elimination: All replaced with Dynamic Prompt System
- On-device Digital Self: AES-256-GCM encrypted PKG, hardware-backed keys
- Gap Filler Engine: Session-ambient context enrichment
- Setup Wizard: 8-step flow for workspace creation
- Dashboard: Mock data, UI complete
- Settings Screen: Multi-section granular controls
- MIO Signing: Ed25519 mandate signing
- Audit Log: Viewer screen

---

## COMPREHENSIVE AUDIT (Feb 2026)

### Full Report: `/app/CODEBASE_AUDIT_REPORT.md`

### Key Findings:
- **17+ spec documents audited** against current implementation
- **9/9 Master Plan phases COMPLETE**
- **All 6 Meta-Principles COMPLIANT**
- **No critical deviations or missing core features**
- **Architecture intentionally deviated** on Digital Self (on-device-first = better privacy)

### Remaining Gaps (by category):
1. **Blocked on ObeGee**: Live API integration (20 endpoints mocked)
2. **Blocked on Native Build**: On-device AI, expo-contacts, expo-calendar
3. **Ready to Implement**: Prompt optimizations (58% token reduction potential)

---

## KEY API ENDPOINTS

### Core
- `GET /api/health` — System health
- `WS /api/ws` — WebSocket for mobile client
- `POST /api/sso/myndlens/pair` — 6-digit code pairing (mock in dev)

### Onboarding
- `GET /api/onboarding/status/{user_id}` — Onboarding status
- `POST /api/onboarding/profile` — Save onboarding profile
- `POST /api/onboarding/skip/{user_id}` — Skip onboarding

### Prompt System
- `POST /api/prompt/track-outcome` — Track prompt outcome
- `POST /api/prompt/user-correction` — Record user correction
- `GET /api/prompt/analytics` — Optimization insights
- `POST /api/prompt/experiments` — Create experiment
- `GET /api/prompt/adaptive-insights` — Adaptive insights

### Agents
- `POST /api/agents/create` — Create agent
- `POST /api/agents/modify` — Modify agent
- `POST /api/agents/retire` — Retire agent
- `POST /api/agents/delete` — Delete agent (admin-only)
- `GET /api/agents/list/{tenant_id}` — List tenant agents

### Dimensions
- `POST /api/dimensions/extract` — Dedicated dimension extraction

---

## MOCKED COMPONENTS
- ObeGee SSO pairing (dev mock)
- ObeGee Dashboard APIs (mock responses)
- ObeGee Dispatch/Execution (mock adapter)
- OpenClaw runtime (mock)
- LLM fallback to mock when Gemini API unavailable

---

## PRIORITIZED BACKLOG

### P0 (Immediate)
- [x] Comprehensive code audit ← DONE

### P1 (Build & Deploy)
- [ ] Add auth middleware to onboarding endpoints
- [ ] Build production APK with latest changes
- [ ] Activate native modules (expo-contacts, expo-calendar, ONNX)

### P2 (Performance)
- [ ] Implement prompt optimizations (6 items, 58% token reduction)
- [ ] E2E test with live ObeGee (when available)

### P3 (Future)
- [ ] Digital Twin module (Tier 2 data scraping)
- [ ] Micro-questions engine (clarification UI)
- [ ] Explainability UI (data provenance)
- [ ] User profile decay
- [ ] Prompt version auto-promotion from experiments

---

## CODE ARCHITECTURE
```
/app
├── backend/
│   ├── agents/         # Agent lifecycle + dynamic composition
│   ├── api/            # Onboarding, dashboard mock, setup wizard
│   ├── auth/           # SSO, device binding, tokens
│   ├── config/         # Settings, feature flags
│   ├── core/           # Database, logging, exceptions
│   ├── dimensions/     # Engine + dedicated extractor
│   ├── dispatcher/     # Mandate dispatch, idempotency
│   ├── guardrails/     # LLM-based harm assessment
│   ├── intent/         # Gap filler engine
│   ├── l1/             # Scout (hypothesis generator)
│   ├── l2/             # Sentry (shadow verifier)
│   ├── memory/         # Retriever, write policy, provenance
│   ├── mio/            # Ed25519 signing
│   ├── prompting/      # Orchestrator, sections, versioning, experiments
│   ├── qc/             # QC sentry, agent topology
│   ├── skills/         # Library, reinforcement, ingester
│   ├── soul/           # Store, drift controls, versioning
│   └── server.py       # FastAPI entry point (~1600 lines)
├── frontend/
│   ├── app/            # Expo screens (talk, settings, setup, dashboard, etc.)
│   └── src/
│       ├── digital-self/  # On-device encrypted PKG
│       ├── audio/         # VAD, recorder
│       ├── ws/            # WebSocket client
│       └── state/         # Session store, settings prefs
├── docs/               # 17+ specification documents
└── CODEBASE_AUDIT_REPORT.md  # Comprehensive gap analysis
```
