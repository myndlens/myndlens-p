# Combined ObeGee + MyndLens Codebase Analysis

**Analysis Date:** February 15, 2026  
**Scope:** Complete system architecture review (ObeGee + MyndLens)

---

## 🏗️ System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Production Architecture                   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐    ┌──────────────────┐               │
│  │   ObeGee Web     │    │  MyndLens Mobile │               │
│  │   (React SPA)    │    │      App         │               │
│  └────────┬─────────┘    └────────┬─────────┘               │
│           │                       │                          │
│           ├───────────────────────┤                          │
│           ↓                       ↓                          │
│  ┌────────────────────────────────────────┐                 │
│  │      ObeGee Backend (FastAPI)          │                 │
│  │   Server 1: 178.62.42.175:8001         │                 │
│  │   • User Management                     │                 │
│  │   • Tenant Provisioning                 │                 │
│  │   • Billing & Subscriptions             │                 │
│  │   • SSO Provider (JWKS)                 │                 │
│  │   • Deployment Authority (DAI)          │                 │
│  └────────┬───────────────────────────────┘                 │
│           │                                                  │
│           ↓                                                  │
│  ┌────────────────────────────────────────┐                 │
│  │    MyndLens Backend (FastAPI)          │                 │
│  │   Server 1: 178.62.42.175:8002         │                 │
│  │   (Docker Container)                    │                 │
│  │   • Digital Self / Intent Resolution    │                 │
│  │   • Dimensions Verification             │                 │
│  │   • Approval Gates / Governance         │                 │
│  │   • WebSocket Gateway                   │                 │
│  │   • STT/TTS Orchestration               │                 │
│  └────────┬───────────────────────────────┘                 │
│           │                                                  │
│           ↓                                                  │
│  ┌────────────────────────────────────────┐                 │
│  │    Runtime Manager (PM2)                │                 │
│  │   Server 3: 138.68.179.111:9000        │                 │
│  │   • OpenClaw Container Orchestration    │                 │
│  │   • Tenant Isolation                    │                 │
│  │   • Lifecycle Management                │                 │
│  └────────────────────────────────────────┘                 │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Combined Codebase Statistics

### Overall System Metrics

| Component | Files | Lines of Code | Size | Language |
|-----------|-------|---------------|------|----------|
| **ObeGee Backend** | 32 | 9,366 | 1.2 MB | Python (FastAPI) |
| **ObeGee Frontend** | 92 | 16,962 | 737 MB* | React/JS/CSS |
| **MyndLens Backend** | 111 | 7,530 | 568 KB | Python (FastAPI) |
| **Runtime Manager** | ~5 | ~500** | ~50 KB | Node.js |
| **Config/Deployment** | 68 | ~2,000 | ~5 MB | Shell/YAML/JSON |
| **TOTAL** | **~308** | **~36,358** | **~745 MB** | Multi-language |

*Includes node_modules  
**Estimated based on typical PM2 setup

---

## 🎯 ObeGee Codebase Deep Dive

### Backend Structure (9,366 lines)

**Core Files:**
- `server.py` (313 lines) - Thin orchestrator, mounts all route modules
- `helpers.py` (350 lines) - Shared utilities, DB connection, auth helpers
- `models.py` - Pydantic data models
- `admin_apis.py` (1,869 lines) - Comprehensive admin management APIs

**Route Modules (13 files):**
```
routes/
├── auth.py (355 lines) - User authentication, signup, login, password reset
├── billing.py (458 lines) - Stripe integration, subscriptions, checkout
├── tenants.py (393 lines) - Tenant CRUD, provisioning, policy management
├── chat.py (202 lines) - Chat message handling
├── approvals.py - Approval gate management
├── channels.py - Channel configuration (WhatsApp, Web, API)
├── tools.py - Tool allowlist management
├── model_provider.py - LLM provider configuration
├── usage_audit.py (192 lines) - Usage tracking and audit logs
├── integrations.py - Third-party integrations
├── runtime.py (221 lines) - Runtime container management
├── internal.py (307 lines) - Internal APIs for runtime manager
├── whatsapp.py (201 lines) - WhatsApp channel integration
├── early_access.py - Early access booking
├── observability.py - Prometheus metrics endpoint
└── myndlens.py - MyndLens mobile app pairing flow
```

**Specialized Modules:**
- `obegee_deployd.py` (305 lines) - Deployment Authority Interface (DAI)
- `obegee_sso.py` - SSO/JWKS provider for MyndLens authentication
- `seed_plans.py` - Database seeding for subscription plans

**Testing (8 files):**
- Comprehensive E2E tests (802 lines)
- Admin functionality tests (3 phases, ~680 lines)
- Subscription renewal tests (343 lines)
- Feature-specific tests (~650 lines total)

### Frontend Structure (16,962 lines)

**Landing & Public Pages:**
- `LandingPageUpgraded.jsx` (1,446 lines) - Main marketing page
- `LoginPage.jsx`, `SignupPage.jsx` - Authentication
- `ForgotPasswordPage.jsx` - Password reset flow
- `TermsPage.jsx`, `PrivacyPage.jsx` - Legal pages
- `CheckoutSuccessPage.jsx` - Post-checkout flow

**User Dashboard (~15 pages):**
```
dashboard/
├── HomePage.jsx - Main tenant dashboard
├── OnboardingPage.jsx - Multi-step setup wizard
├── ChatPage.jsx - Chat interface
├── IntegrationsPage.jsx - Third-party integrations
├── ChannelsPage.jsx - WhatsApp/Web/API setup
├── ToolsPage.jsx - Tool allowlist configuration
├── ModelProviderPage.jsx - LLM provider settings
├── ApprovalGatesPage.jsx - Approval policy management
├── UsagePage.jsx - Usage statistics
├── BillingPage.jsx - Subscription management
├── SettingsPage.jsx - Account settings
└── [others]
```

**Admin Portal (~16 pages):**
```
admin/
├── AdminDashboard.jsx - System overview
├── AdminUsersPage.jsx - User management
├── AdminTenantsPage.jsx - Tenant management
├── AdminSubscriptionsPage.jsx - Billing oversight
├── AdminBookingsPage.jsx - Early access bookings
├── AdminProvisioningPage.jsx - Manual provisioning
├── AdminRuntimeNodesPage.jsx - Runtime server management
├── AdminUsagePage.jsx - System-wide usage analytics
├── AdminAuditPage.jsx - Audit trail viewer
├── AdminObservabilityPage.jsx - Metrics dashboard
└── [others]
```

**Component Library:**
- shadcn/ui components in `src/components/ui/`
- Custom components and utilities
- Styling: landing.css, globals.css

---

## 🧠 MyndLens Codebase Deep Dive

### Backend Structure (7,530 lines, 111 files)

**Architecture:** Highly modular, domain-driven design

**Core Infrastructure:**
```
core/
├── database.py - MongoDB connection and utilities
├── logging_config.py - Structured logging setup
├── exceptions.py - Custom exception hierarchy
└── __init__.py
```

**Authentication & Authorization:**
```
auth/
├── sso_validator.py (159 lines) - ObeGee JWKS validation
├── tokens.py - JWT token management
└── device_binding.py - Mobile device pairing
```

**Tenant Management:**
```
tenants/
├── registry.py - Tenant registry and lookup
└── obegee_reader.py - Read tenant config from ObeGee
```

**Intent Processing Pipeline:**
```
soul/ (Digital Self)
└── store.py (201 lines) - User intent history and context

dimensions/
└── engine.py (128 lines) - Risk/scope/boundary analysis

governance/
└── [approval gate orchestration]

guardrails/
└── engine.py - Safety checks and validation

commit/
└── state_machine.py (179 lines) - Execution state management
```

**Communication Layer:**
```
gateway/
└── ws_server.py (546 lines) - WebSocket server for mobile app

stt/ (Speech-to-Text)
├── orchestrator.py
└── provider/
    ├── deepgram.py (194 lines)
    └── mock.py

tts/ (Text-to-Speech)
├── orchestrator.py
└── provider/
    ├── elevenlabs.py
    └── mock.py
```

**LLM Integration:**
```
prompting/
├── orchestrator.py (148 lines) - LLM request routing
├── llm_gateway.py (126 lines) - Provider abstraction
├── types.py (162 lines) - Type definitions
└── policy/
    └── engine.py (229 lines) - Policy evaluation
```

**Dispatcher (OpenClaw Integration):**
```
dispatcher/
├── dispatcher.py (142 lines) - Command dispatcher to OpenClaw
└── http_client.py (135 lines) - HTTP client for runtime manager
```

**Safety & Reliability:**
```
abuse/
├── rate_limit.py - Rate limiting
└── circuit_breakers.py (123 lines) - Circuit breaker pattern

qc/
└── sentry.py (177 lines) - Quality control and monitoring

presence/
├── heartbeat.py - Connection health monitoring
├── touch_correlation.py - User activity tracking
└── rules.py - Presence-based rules
```

**Observability:**
```
observability/
└── [metrics and monitoring]

transcript/
└── [conversation history management]

memory/
└── retriever.py (162 lines) - Context retrieval
```

**Main Server:**
- `server.py` (815 lines) - FastAPI application orchestrator

**Key Modules by Size:**
1. `server.py` - 815 lines
2. `gateway/ws_server.py` - 546 lines
3. `prompting/policy/engine.py` - 229 lines
4. `soul/store.py` - 201 lines
5. `stt/provider/deepgram.py` - 194 lines

---

## 🔄 Integration Points

### 1. ObeGee → MyndLens Integration

**Authentication (SSO):**
- ObeGee acts as Identity Provider (IdP)
- Exposes JWKS endpoint: `/api/.well-known/jwks.json`
- MyndLens validates JWTs using ObeGee's public keys
- Implementation: `obegee_sso.py` ↔ `auth/sso_validator.py`

**Tenant Configuration:**
- MyndLens reads tenant config from ObeGee database
- Connection: `OBEGEE_MONGO_URL` environment variable
- Implementation: `tenants/obegee_reader.py`

**Mobile App Pairing:**
- Flow: User requests pairing code → ObeGee generates → MyndLens validates
- QR code + 6-digit code for secure device binding
- Implementation: `routes/myndlens.py` ↔ `auth/device_binding.py`

### 2. MyndLens → Runtime Manager Integration

**Command Dispatch:**
- MyndLens sends approved commands to Runtime Manager
- HTTP API: `138.68.179.111:9000`
- Channel adapter on runtime server
- Implementation: `dispatcher/` module

**Tenant Isolation:**
- Each tenant has dedicated OpenClaw container
- Runtime manager provides containerized execution
- Implementation: `runtime/myndlens_channel_adapter.js`

### 3. ObeGee → Runtime Manager Integration

**Provisioning:**
- ObeGee triggers tenant container creation
- Deployment Authority Interface (DAI)
- Implementation: `obegee_deployd.py` ↔ Runtime Manager API

**Lifecycle Management:**
- Start, stop, restart containers
- Health monitoring
- Implementation: `routes/runtime.py` ↔ `routes/internal.py`

---

## 🔐 Security Architecture

### Authentication Flow
```
1. User Login (ObeGee Web)
   ↓
2. ObeGee issues JWT
   ↓
3. Mobile app pairs using pairing code
   ↓
4. MyndLens validates JWT via JWKS
   ↓
5. Device binding established
```

### Authorization Layers
- **ObeGee:** Subscription-based access control
- **MyndLens:** Intent-based approval gates
- **Runtime:** Container-level isolation

### Data Security
- **Encryption:** HTTPS/TLS for all communication
- **Isolation:** Separate containers per tenant
- **Audit Trail:** All actions logged as MIOs (Master Intent Objects)
- **Secrets:** Environment variables, no hardcoded credentials

---

## 💾 Database Architecture

### MongoDB Collections (ObeGee)
- `users` - User accounts
- `tenants` - Tenant configurations
- `subscriptions` - Stripe subscriptions
- `payment_transactions` - Payment history
- `slug_reservations` - Temporary slug holds
- `usage_counters` - Daily usage tracking
- `audit_events` - System audit log
- `chat_messages` - Chat history
- `action_requests` - Approval queue
- `myndlens_connections` - Mobile pairing data

### MongoDB Collections (MyndLens)
- Intent history (soul/store)
- Dimension analysis records
- Approval decisions
- Conversation transcripts
- User context/memory
- Execution state

---

## 🤖 Can We Review Both Codebases Together?

### Token Analysis

**Combined Codebase:**
- ObeGee: 26,328 lines (backend + frontend)
- MyndLens: 7,530 lines (backend only)
- **Total:** 33,858 lines of application code

**Estimated Token Requirements:**
- ObeGee Backend: ~486,000 tokens
- ObeGee Frontend: ~1,102,000 tokens
- MyndLens Backend: ~390,000 tokens
- **Total:** ~1,978,000 tokens

**Available Context:** 870,943 tokens (87% remaining)

**Verdict:** ❌ **Cannot fit entire combined codebase in single context**

---

## ✅ Recommended Review Strategy

### Phase 1: Architecture & Integration Review (Current Session)
**✅ FEASIBLE - ~200k tokens**

Focus on:
1. System architecture (completed above)
2. Integration points analysis
3. Authentication/authorization flow
4. Data flow diagrams
5. Security assessment
6. API contract review

### Phase 2: ObeGee Core Review
**✅ FEASIBLE - Split into 3 sessions**

**Session 2A: Backend Core** (~200k tokens)
- server.py, helpers.py, models.py
- Authentication & billing routes
- Tenant management

**Session 2B: Backend Features** (~200k tokens)
- Chat, approvals, channels
- Admin APIs (review in sections)
- Integration modules

**Session 2C: Frontend** (~300k tokens per session)
- Landing page + public pages
- User dashboard (2-3 pages at a time)
- Admin portal (2-3 pages at a time)

### Phase 3: MyndLens Deep Dive
**✅ FEASIBLE - Split into 2 sessions**

**Session 3A: Intent Pipeline** (~200k tokens)
- Digital Self (soul)
- Dimensions engine
- Governance & guardrails
- Commit state machine

**Session 3B: Communication & Integration** (~200k tokens)
- WebSocket gateway
- STT/TTS orchestration
- LLM integration
- Dispatcher
- ObeGee integration

### Phase 4: Integration Testing & E2E Review
**✅ FEASIBLE - 1 session**

- End-to-end flow analysis
- Integration test coverage
- Security penetration testing recommendations
- Performance optimization opportunities

---

## 🎯 Current Session Recommendation

**Option A: Complete Architecture Review** ⭐ **BEST FOR COMBINED REVIEW**
- ✅ All integration points (SSO, pairing, dispatch)
- ✅ Data flow analysis
- ✅ Security model assessment
- ✅ API contract verification
- ✅ Deployment architecture
- **Tokens:** ~150-200k ✅

**Option B: Integration Deep Dive**
- ✅ Focus on ObeGee ↔ MyndLens integration
- ✅ Authentication flow (JWKS/SSO)
- ✅ Mobile pairing mechanism
- ✅ Tenant configuration sync
- ✅ Command dispatch to OpenClaw
- **Tokens:** ~100-150k ✅

**Option C: Security Audit**
- ✅ Authentication/authorization review
- ✅ Secrets management
- ✅ Container isolation
- ✅ Audit trail coverage
- ✅ API security
- **Tokens:** ~100k ✅

---

## 💡 What I Can Access Right Now

### In Current Environment (/app):
- ✅ Complete ObeGee codebase
- ✅ MyndLens integration specs
- ✅ Deployment scripts
- ✅ Runtime manager adapter

### On Production Server (SSH access):
- ✅ Complete MyndLens codebase (/srv/myndlens/myndlens-p)
- ✅ Git repository with history
- ✅ Production configurations
- ✅ Docker container setup

### I CAN:
1. Pull specific files from MyndLens server for review
2. Analyze architecture and integration contracts
3. Review critical code paths end-to-end
4. Identify security or performance issues
5. Provide comprehensive improvement recommendations

---

## 🚀 Next Steps - Your Choice!

**Which review would you prefer?**

1. **🏗️ Architecture & Integration Review** (Recommended)
   - Understand complete system flow
   - Verify all integration points
   - Identify architectural improvements
   - Security assessment

2. **🔐 Security Audit Focus**
   - Authentication mechanisms
   - Authorization boundaries
   - Data protection
   - Container isolation

3. **🔄 Integration Deep Dive**
   - ObeGee ↔ MyndLens SSO
   - Mobile pairing flow
   - Command dispatch pipeline
   - Tenant configuration sync

4. **📊 Specific Module Review**
   - Tell me which modules to analyze
   - Can pull and review specific files

**I'm ready to proceed - what's your preference?**
