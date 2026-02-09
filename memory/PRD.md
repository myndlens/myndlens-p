# MyndLens - Product Requirements Document (Consolidated)

> This document consolidates all 5 specification documents for MyndLens development.
> Last Updated: July 2025
> Version: 4.0 (FINAL - Line-by-Line Verification Complete)

**Verification Status:**
- ✅ Unified Truth Spec vNext (§0-21, Appendix A/B/C) - 100% captured
- ✅ Implementation Plan v1 (§1-6, All Batches 0-13) - 100% captured
- ✅ Dynamic Prompt System Spec (§0-13) - 100% captured
- ✅ Supplementary Spec (S1-S18) - 100% captured
- ✅ Infrastructure & Deployment Spec (§1-10, §7A) - 100% captured

---

## 0. NON-NEGOTIABLE META-PRINCIPLES (6 Laws)

1. **No Drift**: Nothing may deviate from this spec without an ADR
2. **No Hallucination**: No invented APIs, fields, flows, or capabilities
3. **Sovereignty First**: Execution authority is centralized, auditable, revocable
4. **Isolation by Design**: Isolation enforced at IP, proxy, network, data, secrets, keys
5. **Human-in-the-loop for risk**: Irreversible/sensitive actions require physical latch
6. **To-the-point behavior**: System avoids data dumps; uses minimal clarifying nudges

---

## 1. PRODUCT OBJECTIVE & INTERACTION PHILOSOPHY

### 1.1 Objective
Extract user intent from **brief, natural, interactive conversation** and generate **dimensions** to initiate actions with Sovereign safety.

### 1.2 Core Interaction Truths
- Proxy does NOT know the goal at start; only user does
- Conversation must be natural and empathetic, NOT structured Q&A
- Users speak in fragmented thoughts; proxy connects fragments
- Gap-bridging uses Digital Self (Vector-Graph Memory)
- Digital Self prevents wrong-entity execution

### 1.3 Safety Posture During Conversation
- Guardrails checked continuously as thought capture progresses
- If guardrails crossed → immediate tactful refusal
- Never harsh rejection; always empathetic redirection

---

## 2. TECHNOLOGY STACK (CONFIRMED)

| Component | Technology | Purpose |
|-----------|------------|---------|
| **STT** | Deepgram | Real-time streaming speech-to-text |
| **L1 Scout** | Gemini 2.0 Flash | Fast intent hypothesis (max 3) |
| **L2 Sentry** | Gemini 2.0 Pro | Authoritative intent validation |
| **TTS** | ElevenLabs | Natural voice responses |
| **Vector DB** | ChromaDB (self-hosted) | Semantic similarity search |
| **Graph Store** | NetworkX + MongoDB | Canonical graph (UUID nodes + typed edges) |
| **KV Registry** | MongoDB | Human refs → canonical entity IDs |
| **Signing** | ED25519 | MIO cryptographic signatures |

---

## 3. SYSTEM ARCHITECTURE

### 3.1 Two Planes

**Command Plane (MyndLens BE)** - Authoritative
- Runs on the **same VPS as ObeGee** but in **isolated containers and networks**
- Session authority (WebSocket)
- STT orchestration
- L1 Scout, L2 Sentry, QC Sentry (Devil's Advocate)
- Digital Self service (sole memory authority)
- Guardrails (continuous)
- Dimension Engine (A + B sets)
- Commit Manager + server-side state machine
- Presence verification (heartbeat + touch)
- MIO signing (ED25519)
- Dispatcher
- Audit & observability

**Execution Plane (OpenClaw)** - Stateless peripheral / muscle
- Tenant docker containers
- Executes only translated, signed MIOs
- Receives NO transcripts, hypotheses, or memory
- **Rule of Zero-Code-Change**: Orchestrator interacts only via existing OpenClaw API

### 3.2 Mobile App (Expo)

**First Challenge (§3.1)**: Design interactive STT ↔ TTS loop for Siri-like UX

**Audio State Machine:**
```
1. LISTENING   - Waiting for speech
2. CAPTURING   - Recording audio
3. COMMITTING  - Processing commit
4. THINKING    - Backend processing
5. RESPONDING  - TTS playback
```

**Key Features:**
- Local VAD (MANDATORY for UX quality)
- ~250ms audio chunk streaming over WebSocket
- Hybrid control: STT flow + Execute button (user chooses)
- Execute button = PRIMARY control for Sovereign review/latch
- TTS playback with interruption support
- Heartbeat every 5s (encrypted)

**TTS Rules:**
- TTS playback must support interruption
- 250ms cooldown rule for voice token loops (Tier 1 voice latch)

---

## 4. STT STRATEGY

### 4.1 Kickstart Strategy
- Start with **Managed API** (Deepgram) for STT
- When traffic builds, switch to self-hosted/alternative providers

### 4.2 Provider Abstraction
- STT is provider-agnostic behind an interface
- STT provides ONLY: transcript fragments + confidence + latency
- **STT does NOT provide**: intent inference, VAD, emotion inference

### 4.3 Failure Mode
- STT fail → pause listening, prompt user for retry or text input
- Never silent fallback

---

## 5. INTENT EXTRACTION STACK

### 5.1 L1 Scout
- High-speed, low-latency (Gemini Flash)
- Maintains running hypothesis; updates dimension map as text arrives
- **Max 3 hypotheses**
- Produces `L1_Draft_Object` with:
  - Hypothesis
  - Evidence spans (transcript references)
  - Dimension suggestions
  - Confidence scores
- Outputs are **NON-authoritative** (suggestions only)

### 5.2 L2 Sentry (BE-only)
- Frontier-class model (Gemini Pro)
- Runs ONLY on MyndLens BE (Command Plane)
- Performs **Shadow Derivation** (ignores L1 initially)
- Large context window for full session analysis

**Invocation Timing (HARD RULE):**
- L2 runs ONLY on:
  1. Draft finalization
  2. Execute attempt (button-initiated or server commit)
- **NEVER** per transcript fragment
- Any implementation invoking L2 outside these points is INVALID

### 5.3 QC Sentry
- Runs AFTER L2 and BEFORE MIO signing
- **Adversarial Passes:**
  1. **Persona Drift**: Compare draft tone vs DigitalSelf.Communication_Profile
  2. **Capability Leak**: Ensure minimum necessary OpenClaw skill only
  3. **Harm Projection**: Must map negative interpretation to specific transcript spans

**Grounding Rule:**
- If QC cannot cite transcript spans, it CANNOT block
- May only nudge/downgrade without span evidence

### 5.4 L1/L2 Conflict Resolution

**Intent Equality (Structural Identity):**
- Action_Class must match
- Canonical_Target must match
- Primary_Outcome must match
- Risk_Tier must match

**Confidence Gate:**
- Combined = min(L1_conf, L2_conf)
- abs(delta) ≤ 0.15
- Combined > 0.9
- If ANY condition fails → Silence/Clarify

---

## 6. DIMENSIONS

### 6.1 A-Set (Action Dimensions)
- **what**: Action to perform
- **who**: Target entity/person
- **when**: Timing/schedule
- **where**: Location/channel
- **how**: Method/approach
- **constraints**: Limitations/conditions

### 6.2 B-Set (Cognitive Dimensions)
- **urgency**: Time pressure (moving average)
- **emotional_load**: Emotional intensity (moving average)
- **ambiguity**: Clarity score
- **reversibility**: Can action be undone
- **user_confidence**: User's certainty level

### 6.3 Stability Buffer
- urgency and emotional_load are **moving averages**
- Risky proposals gated until stability via Low-VAD / turn cycle rule
- Prevents impulsive high-risk actions

---

## 7. DIGITAL SELF (VECTOR-GRAPH MEMORY)

### 7.1 Purpose
The Digital Self is a **living store of user info** collected by another agent into a Vector-Graph Memory.

It is used to:
- Bridge fragmented user thoughts
- Fill conversational gaps empathetically
- Ground intent extraction in prior facts, preferences, entities
- Prevent wrong-entity execution
- **First-class system dependency, not optional add-on**

### 7.2 Storage Layers
1. **Vector DB (ChromaDB)** - Semantic layer
   - Stores node-documents with embeddings
   - Used for semantic retrieval and similarity search

2. **Canonical Graph (NetworkX)** - Deterministic layer
   - Nodes have canonical UUIDs
   - Typed relationships: FACT, PREFERENCE, ENTITY, HISTORY, POLICY
   - Each node includes provenance metadata

3. **KV Entity Registry (MongoDB)**
   - Maps human references → canonical entity IDs
   - Prevents wrong-entity execution (e.g., wrong contact)

### 7.3 Provenance Model (NON-NEGOTIABLE)
- `EXPLICIT` - Directly stated by user
- `OBSERVED` - Inferred / low confidence

**Tier Downgrade Rule:**
- If ANY execution-critical dimension depends on OBSERVED node
- → Action automatically downgraded to **Tier 2** (Physical Latch required)

### 7.4 Service Authority & Access Rules
- **ONLY** `myndlens-digital-self` service may:
  - Query vector DB
  - Traverse the graph
  - Write or update memory nodes
- Other services **NEVER** access memory storage directly

**Access Pattern:**
```
L1 Scout  ──► suggests memory hints (non-authoritative)
L2 Sentry ──► requests deterministic retrieval from Digital Self service
Digital Self Service ──► returns node-docs + provenance
```

### 7.5 Read vs Write Semantics

**Read:**
- Allowed for L1 (suggestive only)
- Authoritative for L2 (verification only)
- Queries are deterministic, auditable, side-effect free

**Write:**
- Only allowed post-execution OR via explicit user confirmation
- Writes must include: source, confidence, timestamp

**NEVER Allowed:**
- Policy writes
- Silent preference mutation
- LLM-initiated self-learning without user signal

### 7.6 Runtime Guarantees
- Digital Self co-located with L2 Sentry on Command Plane
- Minimizes injection surface
- Preserves Sovereign Integrity

---

## 8. ACTION TAXONOMY & RISK TIERS

### 8.1 Action Classes

| Action_Class | Description | Default Tier |
|--------------|-------------|--------------|
| COMM_SEND | Messages (WhatsApp, Email, SMS) | Tier 2 |
| SCHED_MODIFY | Calendar/reminder CRUD | Tier 2 |
| INFO_RETRIEVE | Web/memory/local retrieval | Tier 0 |
| DOC_EDIT | Modify notes/docs/code | Tier 2 |
| FIN_TRANS | Financial/value movement | Tier 3 |
| SYS_CONFIG | Settings/permissions/graph | Tier 2 |
| DRAFT_ONLY | Local-only draft | Tier 0 |

### 8.2 Tier Requirements

| Tier | Name | Requirement | Details |
|------|------|-------------|---------|
| 0 | No Latch | None | Safe read-only operations |
| 1 | Voice Latch | Voice repeat | 250ms cooldown between repeats |
| 2 | Physical Latch | Touch token | 10s correlation window |
| 3 | Biometric | OS biometric | Proof bound to touch + mio_id |

---

## 9. MIO (MASTER INTENT OBJECT)

### 9.1 Purpose
Non-repudiable signed package containing the specific, audited intent.
**No execution without valid MIO.**

### 9.2 Canonical Schema
```json
{
  "header": {
    "mio_id": "UUID",
    "timestamp": "ISO-8601",
    "signer_id": "MYNDLENS_BE_01",
    "ttl_seconds": 120
  },
  "intent_envelope": {
    "action": "openclaw.v1.<skill>.<verb>",
    "action_class": "COMM_SEND|SCHED_MODIFY|...",
    "params": { },
    "constraints": {
      "tier": 2,
      "physical_latch_required": true,
      "biometric_required": false
    }
  },
  "grounding": {
    "transcript_hash": "SHA-256",
    "l1_hash": "SHA-256",
    "l2_audit_hash": "SHA-256",
    "memory_node_ids": ["node_uuid_1", "node_uuid_2"],
    "provenance_flags": { "node_uuid_1": "EXPLICIT" }
  },
  "security_proof": {
    "touch_event_token": "TOUCH_SIG",
    "signature": "ED25519_SIG"
  }
}
```

### 9.3 TTL & Replay Protection
- TTL is SHORT (120 seconds default)
- Replay cache enforced server-side
- Touch tokens are single-use
- Tokens bound to: mio_id + session_id + device_id

---

## 10. PRESENCE & PHYSICAL LATCH

### 10.1 Heartbeat
- Mobile sends **encrypted** heartbeat every **5 seconds**
- BE refuses to generate MIO if heartbeat lost > **15 seconds**

### 10.2 Touch Correlation
- For Tier ≥2, server refuses execution unless Physical-Touch-Timestamp correlates within **10 seconds**
- Touch tokens are single-use
- Tokens bound to: mio_id + session_id + device_id
- Replay cache prevents token reuse

---

## 11. SAFETY GATES

### 11.1 Silence-Is-Intelligence Gate
- If **Ambiguity Score > 30%** → Silence/Clarify state
- No draft promoted to execution-eligible
- System requests minimal clarification nudge only

### 11.2 Chain-of-Logic (CoL) Requirement
- L1 MUST emit CoL trace for every inferred dimension
- L2 REQUIRES this trace to evaluate dimensional validity
- If reasoning is speculative/weakly grounded → L2 triggers Clarification Nudge
- Execution CANNOT proceed without grounded reasoning

### 11.3 Emotional Load Cooldown (Execution Dampener)
- Emotional load derived from turn dynamics and interaction patterns
- If high emotional load detected:
  - L2 enforces **Stability Cooldown**
  - Complex/high-impact plans blocked from immediate execution
  - System downgrades to Draft/Clarify until stability criteria met

### 11.4 Kill-Switch
| Mode | Name | Effect |
|------|------|--------|
| 0 | Normal | Full operation |
| 1 | Read-only Safe Mode | INFO_RETRIEVE and DRAFT_ONLY only |
| 2 | Hard Stop | All operations blocked |

**Enforcement Points:**
- Block MIO signing
- Block dispatch
- Refuse touch validation

---

## 12. DISPATCHER & HANDSHAKE

### 12.1 Dispatcher Responsibilities
- Wraps approved plan in signed MIO
- Translates sovereign intent to OpenClaw REST/WS schema
- Injects tenant API key (from Tenant Registry)
- Executes HTTPS to tenant docker endpoint
- Logs logic trace for CEO-level observability

### 12.2 Translation Example
```
Receive: Approved MIO
Translate: openclaw.v1.whatsapp.send → mapped tenant endpoint
Example: POST https://tenant-docker-4.obegee.com/api/send
Auth: Inject tenant API key in header
Transport: HTTPS only
```

### 12.3 Idempotency
- Idempotency key = `{session_id + mio_id}`
- Duplicate dispatch requests with same key MUST NOT re-execute

---

## 13. FAILURE & SAFETY STATES

| Condition | Response |
|-----------|----------|
| L1/L2 disagree | Default to Ambiguity / Ask User (Clarify) |
| L2 offline | Read-Only Safe Mode (**No silent fallback to L1-only execution**) |
| Signature fails | Hard Rejection |
| Touch correlation fails | Hard Rejection |
| Heartbeat lost >15s | Refuse MIO generation |

---

## 13A. GUARDRAILS PURPOSE & BEHAVIOR

### Purpose
Guardrails provide constraints on:
- What intents can be acted upon
- What should be refused

### Continuous Evaluation
- As thought capture progresses, continuously verify guardrails are not being crossed
- Evaluation happens in real-time, not just at execution time

### Response Behavior
- If crossing detected → immediate response that action is not right
- Refusal must be **tactful** (never harsh)
- Always provide empathetic redirection

---

## 14. DYNAMIC PROMPT SYSTEM

### 14.1 Core Principles
- **Prompt = Program, not String**: Assembled from composable sections at runtime
- **Least-Privilege Context**: Only inject context required for current purpose
- **Minimize Prompt Surface Area**: Smaller prompt = lower hallucination/drift risk
- **Non-goal**: One monolithic prompt that tries to do everything

### 14.2 System Components

| Component | Purpose |
|-----------|---------|
| PromptOrchestrator | Entry point per LLM call; produces PromptArtifact |
| SectionRegistry | Maps SectionID → generator(ctx) → SectionOutput |
| ContextProviders | Tool catalog, workspace, skills, runtime, memory, safety |
| PolicyEngine | Decides allowed tools, sections, budgets, thresholds |
| PromptReportBuilder | Creates breakdown for debugging/regression control |

### 14.3 Purposes (First-Class)

| Purpose | Use Case |
|---------|----------|
| THOUGHT_TO_INTENT | Interpret user input, propose candidate intents |
| DIMENSIONS_EXTRACT | Structured extraction only (no planning/execution) |
| PLAN | Sequencing, dependencies, fallback paths |
| EXECUTE | Tool-using, strongly constrained |
| VERIFY | Fact-check, consistency check, audit |
| SAFETY_GATE | Risk classification + escalation |
| SUMMARIZE | Compress for user display |
| SUBAGENT_TASK | Minimal mode, narrow task |

### 14.4 Purpose-to-Sections Mapping

**DIMENSIONS_EXTRACT:**
- Include: identity, purpose contract, output schema, dimension taxonomy, 1-2 examples
- Exclude: execution instructions, full tool list, large workspace dumps
- Tools: none (or read-only memory if explicitly needed)

**EXECUTE:**
- Include: identity, purpose contract, tooling (filtered), constraints, confirmations, safety
- Exclude: raw memory dumps, irrelevant skills
- Tools: only those required for step (least privilege)

### 14.5 Standard Section Set (12 Sections)

| # | Section | Cache Class |
|---|---------|-------------|
| 1 | IDENTITY_ROLE | Stable |
| 2 | PURPOSE_CONTRACT | Stable per purpose |
| 3 | OUTPUT_SCHEMA | Stable per purpose |
| 4 | TOOLING | Semi-stable |
| 5 | WORKSPACE_BOOTSTRAP | Semi-stable |
| 6 | SKILLS_INDEX | Semi-stable |
| 7 | RUNTIME_CAPABILITIES | Semi-stable |
| 8 | SAFETY_GUARDRAILS | Stable |
| 9 | TASK_CONTEXT | Volatile |
| 10 | MEMORY_RECALL_SNIPPETS | Volatile |
| 11 | DIMENSIONS_INJECTED | Volatile |
| 12 | CONFLICTS_SUMMARY | Volatile |

### 14.6 Section Contract
Each section generator returns:
- `content`: string OR list of role-tagged message chunks
- `priority`: int (ordering)
- `cache_class`: STABLE | SEMISTABLE | VOLATILE
- `tokens_est`: int
- `included`: bool
- `gating_reason`: str (if excluded)

### 14.7 DimensionsStore

**Record Structure:**
```python
@dataclass
class DimensionRecord:
    type: str  # time/entity/constraint/preference/risk/privacy/budget/urgency/authority
    value: Any
    confidence: float  # 0-1
    source: Literal["explicit", "inferred", "memory"]
    expiry: datetime
    scope: List[str]  # applies to which intents
```

**Injection Policy (Hard Rules):**
Only inject dimensions that satisfy:
- **relevant** to current purpose + candidate/hardened intent
- **not expired**
- either **explicit** OR confidence ≥ threshold
- top-K by relevance (K depends on purpose)

### 14.8 Conflict Handling
Detect conflicts before prompt finalization:
- contradictory times
- preference vs constraint
- authority ambiguity

If conflicts exist:
- Generate CONFLICTS_SUMMARY section
- Mark execution as blocked unless user confirms

### 14.9 Tool Filtering (5 Layers)
1. Global allow/deny
2. Purpose allowlist
3. Agent allowlist
4. Channel/group policy
5. Sandbox/runtime policy

TOOLING section MUST only include tools that passed ALL filters.

### 14.10 Skills System
- SkillsIndex: compact list (skill_name, description, path)
- On-demand loading: LLM instructed to load skill docs only if required
- Security: skills allowlisted, versioned, cannot escalate privileges

### 14.11 Cache Stability
- **Stable**: identity/role, purpose contract, schema, safety rules
- **Semi-stable**: tools list, skills index, workspace bootstrap
- **Volatile**: task context, recalled memory, injected dimensions
- **Rule**: No "ticking clock" in stable prompt (use runtime/tool for current time)

### 14.12 PromptReport (Required per call)
```python
@dataclass
class PromptReport:
    purpose: PromptPurpose
    mode: PromptMode
    sections: List[SectionStatus]  # included/excluded + reasons
    token_estimates: Dict[str, int]
    budget_used: int
    allowed_tools: List[str]
    stable_hash: str
```

### 14.13 Prompt Snapshots (Audit Trail)
Persist per-call:
- prompt_id
- purpose/mode
- stable hashes
- volatile hashes
- model/provider
- tool calls executed

### 14.14 Testing Requirements (5 Types)
1. **Golden prompt tests**: Per purpose/mode (section list + hashes)
2. **Token budget tests**: Deterministic truncation
3. **Tool gating tests**: EXECUTE never sees forbidden tools
4. **Safety regression tests**: Known risky prompts get blocked
5. **Cache stability tests**: Stable segments unchanged unless config changes

### 14.15 Rollout Plan (6 Steps)
1. Build orchestrator + registry + report (no behavior change)
2. Convert DIMENSIONS_EXTRACT first (tight schema + no tools)
3. Add EXECUTE purpose with strict tool gating
4. Add dimension gating + conflict summary
5. Add skills index + on-demand loading
6. Add subagent minimal mode

### 14.16 Acceptance Criteria (5 Requirements)
- A) Prompt output differs by purpose in measurable way (sections/tools)
- B) DIMENSIONS_EXTRACT never produces plans or tool calls
- C) EXECUTE never sees tools it cannot use
- D) PromptReport explains every included/excluded section
- E) Stable hashes remain stable across calls when config unchanged

---

## 15. INFRASTRUCTURE (PRODUCTION)

### 15.1 Core Deployment Principle
MyndLens and ObeGee MUST be cleanly isolated systems.
Isolation enforced at **4 layers**: Public IP, Reverse Proxy, Docker Network, Data/Secrets/Keys

### 15.2 IP Topology
- VPS Provider: **DigitalOcean**
- **IP1** → ObeGee Stack
- **IP2** → MyndLens Stack

### 15.3 DNS
- Provider: **DigitalOcean DNS** (migrated from GoDaddy)
- Records:
  | Hostname | Points To |
  |----------|-----------|
  | obegee.co.uk | IP1 |
  | www.obegee.co.uk | IP1 |
  | api.myndlens.obegee.co.uk | IP2 |
  | admin.myndlens.obegee.co.uk | IP2 |

**DNS Migration Preservation:**
- A / CNAME records
- MX records
- TXT: SPF, DKIM, DMARC
- Verification TXT records

### 15.4 Reverse Proxy (Nginx)

**Binding Rules (CRITICAL):**
- `obegee-nginx` binds ONLY to: IP1:80, IP1:443
- `myndlens-nginx` binds ONLY to: IP2:443
- **HARD RULE**: No proxy may bind to `0.0.0.0:443`
- Port 80 CLOSED for MyndLens (HTTPS-only)

**WebSocket Contract (NON-NEGOTIABLE):**
```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_buffering off;
proxy_read_timeout 86400;
proxy_send_timeout 86400;
```

### 15.5 TLS & Certificates
- Method: **DNS-01 challenge**
- Tooling: **acme.sh**
- Provider: **DigitalOcean DNS API**
- Certificates for: api.myndlens.obegee.co.uk, admin.myndlens.obegee.co.uk
- **DigitalOcean API token is ROOT-GRADE secret**
- Auto renewals + reload hook for Nginx (graceful only)
- Token stored as Docker secret or root-only file; NEVER logged

### 15.6 Docker Networks
- `obegee_net` - ObeGee only
- `myndlens_net` - MyndLens only
- **NO shared networks**
- **NO container-to-container shortcuts across stacks**
- Cross-stack communication (if ever allowed) MUST use public DNS + HTTPS

### 15.7 Stack Services

**Public-Facing:**
- myndlens-nginx (IP2:443, TLS-terminating)

**Internal Services (Private):**
- myndlens-gateway (WebSocket + HTTP API)
- myndlens-l1-scout
- myndlens-l2-sentry
- myndlens-qc-sentry
- myndlens-digital-self
- myndlens-guardrails
- myndlens-planner
- myndlens-presence
- myndlens-mio-signer
- myndlens-dispatcher
- myndlens-audit

**Data Services:**
- Postgres
- Redis
- ChromaDB (Vector DB)

### 15.8 Firewall Rules (IP2 / MyndLens)
- Allow inbound: TCP 443
- Block inbound: TCP 80, all other ports
- Internal services accessible ONLY via myndlens_net

---

## 16. IDENTITY, AUTH & SESSION BINDING (S1)

### 16.1 User-Device-Session Binding
Each user session bound to:
- User ID
- Device ID
- Device-generated keypair
- Reconnection requires re-validation of device key

### 16.2 WebSocket Authentication
- WS connections require short-lived auth tokens
- Tokens scoped to: user + device + environment
- Token expiry forces re-authentication

---

## 17. SECRETS & KEY MANAGEMENT (S2)

### 17.1 Signing Keys (ED25519)
- Generated on BE only
- Stored encrypted at rest
- Rotation policy: time-based + incident-based
- Revocation immediately invalidates pending MIOs

### 17.2 Tenant API Keys
- Unique per tenant
- Stored encrypted
- Rotatable without downtime

---

## 18. AUDIO, TRANSCRIPT & PRIVACY (S3)

### 18.1 Audio Retention
- Raw audio NEVER stored by default
- Temporary in-memory buffers only

### 18.2 Transcript Retention
- Stored only if required for audit
- Encrypted at rest
- Retention duration configurable

### 18.3 User Data Rights
- Support export on request
- Support deletion on request

---

## 19. MULTI-TENANT ISOLATION (S4)

- Tenant Registry is authoritative
- Dispatcher enforces tenant isolation on every request
- Per-tenant quotas and rate limits applied
- Tenant-specific audit trails maintained

---

## 20. UX CONTRACT FOR DRAFT & CONFIRMATION (S6)

Draft Card MUST show:
- Action summary
- Target
- Timing
- Risk tier

Rules:
- Tier ≥2 requires explicit user confirmation
- Cancel/undo always available before dispatch

---

## 20A. TIME, LOCALE & SCHEDULING RESOLUTION (S7)

### Time Authority
- **Server is source of truth for time**
- Device timezone is transmitted explicitly with each request
- All timestamps stored in UTC

### Relative Time Handling
- Relative times (e.g., "tomorrow", "next week") MUST be resolved
- Resolution MUST be confirmed in draft card before execution
- User sees both relative input and absolute resolved time

### Locale Handling
- Date/time formats respect user locale
- Ambiguous dates (e.g., 01/02/2025) require disambiguation

---

## 20B. CANONICAL ENTITY RESOLUTION SAFETY (S9)

### Same-Name Disambiguation
- When multiple entities share the same name, system MUST disambiguate
- Present options with distinguishing context (e.g., "John Smith (Work)" vs "John Smith (Family)")
- Never auto-select without user confirmation

### Channel Binding
- Channel must be **explicit** (WhatsApp vs SMS vs Email)
- If entity has multiple channels, user must confirm which
- Default channel can be suggested based on Digital Self history

### Verification Markers
- Show "last-used" or "verified" markers to user
- Verified entities from explicit user confirmation get priority
- OBSERVED entities shown with lower confidence indicator

---

## 20C. SERVER COMMIT STATE PERSISTENCE (S11)

### State Machine States
```
DRAFT → PENDING_CONFIRMATION → CONFIRMED → DISPATCHING → COMPLETED
                            → CANCELLED
                            → FAILED
```

### Persistence Rules
- Commit state machine is **persisted durably** (not in-memory only)
- **Exactly-once semantics** enforced via idempotency keys
- State transitions are atomic and logged

### Recovery Rules (BE Restart)
- On restart, recover pending commits from durable storage
- DISPATCHING state → re-verify MIO validity and heartbeat before retry
- Stale PENDING_CONFIRMATION → timeout and notify user
- Never auto-resume DISPATCHING without fresh presence verification

### Audit Trail
- Every state transition logged with timestamp and reason
- Failed transitions include error details
- Recovery actions are auditable

---

## 21. OBSERVABILITY & REDACTION (S8)

### 21.1 Log Tiers
- System metrics
- Audit events

### 21.2 Redaction
- PII redacted from logs
- Secrets never logged
- Access to detailed logs is role-restricted

---

## 22. RATE LIMITING & ABUSE (S12)

Rate limits per:
- User
- Device
- Tenant

Circuit breakers for:
- Repeated ambiguity loops
- STT failures
- API abuse patterns

---

## 23. PROMPT INJECTION CONTROLS (S13)

- Detect and block instruction override patterns
- Retrieval outputs are sanitized
- Tool access is least-privilege
- No unsanitized user input in system prompts

---

## 24. VERSIONING & COMPATIBILITY (S14)

Versioned schemas:
- WS messages
- L1 outputs
- MIO format

Rule: Backward compatibility required during rollout

---

## 25. ENVIRONMENT SEPARATION (S15)

- Separate dev/staging/prod environments
- No prod dispatch from non-prod environments
- Keys and tenants are environment-scoped
- Hard guards prevent cross-environment execution

---

## 26. BACKUP, RESTORE & DR (S16)

- Digital Self and audit logs backed up
- Restore preserves provenance integrity
- Key recovery is limited and auditable

---

## 27. MOBILE OFFLINE & LOW-NETWORK (S17)

- Execute DISABLED without heartbeat
- Partial drafts discarded safely on disconnect
- Local buffering has strict limits
- Graceful degradation UX

---

## 28. BIOMETRIC GATE - TIER 3 (S18)

- OS-level biometric prompt required
- Proof bound to: touch + mio_id
- No biometric → execution denied
- Cannot be bypassed

---

## 29. BUILD & PROJECT CONSTRAINTS

### 29.1 Project Separation
- MyndLens is a **SEPARATE Emergent project**
- Cannot be developed in ObeGee dev environment
- Deployed to same VPS via isolated Docker stacks
- Clean separation at all layers

### 29.2 Build Order (MANDATORY Sequential)
1. Define schemas & interfaces (Draft only)
2. Freeze schemas (no code)
3. Implement BE core services
4. Implement Mobile App
5. Integrate OpenClaw via Dispatcher
6. Add guardrails, QC, and kill-switch
7. Add observability & audit

Skipping or parallelizing steps is FORBIDDEN.

---

## 30. MODULE DEFINITIONS

### 30.1 Mobile Modules (M1-M7)

| Module | Name | Description |
|--------|------|-------------|
| M1 | Audio Capture | Local VAD + chunker (~250ms) |
| M2 | WebSocket Client | Auth + reconnect logic |
| M3 | TTS Playback | Interruption support |
| M4 | Draft Card UI | Tier-aware confirmations |
| M5 | Execute Button | Touch token + biometric proof (Tier 3) |
| M6 | Heartbeat Sender | 5s interval + presence UX |
| M7 | Offline Behavior | Buffering limits + graceful degradation |

### 30.2 Backend Modules (B1-B22)

| Module | Name | Description |
|--------|------|-------------|
| B1 | Gateway | WS session authority + message router |
| B2 | Identity/Auth | User-device-session binding |
| B3 | STT Orchestrator | Managed API adapter + abstraction |
| B4 | Transcript Assembler | Evidence spans |
| B5 | L1 Scout | Running hypothesis, max 3 |
| B6 | Digital Self | Vector + graph + KV registry + retriever |
| B7 | Dimension Engine | A-set/B-set + stability buffer |
| B8 | Guardrails Engine | Continuous checks |
| B9 | L2 Sentry | Shadow derivation, BE-only |
| B10 | QC Sentry | Persona drift, capability leak, harm projection |
| B11 | Commit Manager | Server commit state machine + durable persistence |
| B12 | Presence Verifier | Heartbeat (>15s refuse) + touch correlation (10s) |
| B13 | MIO Signer | ED25519 + TTL + replay cache |
| B14 | Dispatcher | Translate MIO → OpenClaw API, inject tenant key |
| B15 | Tenant Registry | Endpoints + keys + quotas + env scoping |
| B16 | Observability/Audit | Tiered logs + redaction |
| B17 | Rate Limiting | Per user/device/tenant + circuit breakers |
| B18 | Environment Separation | Dev/stage/prod hard guards |
| B19 | Backup/Restore/DR | Memory + audit + provenance preservation |
| B20 | Prompting "Soul" | Dynamic prompt store in vector memory |
| B21 | Subscription Provisioner | Tenant Account + Doctor Docker |
| B22 | Tenant Lifecycle | Suspend/Deprovision |

### 30.3 Channel/Integration Modules (C1-C4)

| Module | Name | Description |
|--------|------|-------------|
| C1 | ObeGee Tenancy Boundary | Identity, routing, deployment |
| C2 | MyndLens Channel | Zero-change bridge contract |
| C3 | OpenClaw Multi-Tenant | Docker endpoints validation |
| C4 | Docker Bootstrap | Channel preinstall |

### 30.4 Infrastructure Modules (I1-I5)

| Module | Name | Description |
|--------|------|-------------|
| I1 | Repo Separation | CI/CD scaffolding |
| I2 | Two IP Topology | Nginx separation + IP-scoped binds |
| I3 | DNS Migration | GoDaddy → DO + record parity |
| I4 | TLS DNS-01 | acme.sh + renewal hooks |
| I5 | Docker Networks | Separation + secret management |

---

## 31. BATCH EXECUTION PLAN

### Batch 0 — Foundations (Repo + Infra Skeleton)
**Modules**: I1, I2, I5, B16 (minimal), B18 (minimal)
**Scope**:
- Separate project repo
- Docker compose skeleton (myndlens_net only)
- Nginx container bound to IP2:443 only
- Secrets baseline
- Minimal logging with redaction hooks

**Tests**:
- Container boot tests
- Port exposure test (only IP2:443)
- Network isolation test

**Spec Trace**: Unified §§17-18, 18.2, 18.6; Appendix B12; Supplement S2, S15

---

### Batch 1 — Identity + Presence Baseline
**Modules**: B1, B2, M2, M6
**Scope**:
- WS auth handshake
- User-device-session binding
- Heartbeat every 5s; BE refuses if >15s missing

**Tests**:
- Unit: token validation, device binding
- Integration: mobile connects, heartbeats recorded
- E2E: heartbeat drop → BE blocks execute attempt

**Spec Trace**: Unified §2.1, §12.1; Appendix C1/C2/C6; Supplement S1, S17

---

### Batch 2 — Audio Pipeline + TTS Loop
**Modules**: M1, M3, B1 (extend), B4
**Scope**:
- Local VAD for UX
- 250ms audio chunk streaming over WS
- Transcript assembler accepts partials (STT stubbed)
- TTS playback + interruption rules

**Tests**:
- Unit: chunker, VAD decisions, TTS interrupt
- Integration: WS streaming throughput
- E2E: audio stream → server receives → TTS response

**Spec Trace**: Unified §3.2, Appendix B1, §3.6; Supplement S5, S17

---

### Batch 3 — Managed STT Integration
**Modules**: B3, B4 (finalize), M2 (retry UX)
**Scope**:
- Managed STT adapter + abstraction
- Confidence/latency metrics only
- Failure mode: STT down → pause + retry/text fallback

**Tests**:
- Unit: adapter, timeouts, retries
- Integration: STT mocked + real sandbox
- E2E: audio → transcript fragments; STT outage behavior

**Spec Trace**: Unified §4.1-4.2; Supplement S5

---

### Batch 4 — L1 Scout + Dimension Engine
**Modules**: B5, B7
**Scope**:
- L1 running hypothesis, max 3
- A-set/B-set dimensions
- B-set moving averages + stability buffer

**Tests**:
- Unit: hypothesis update, dimension updates
- Integration: transcript fragments → L1 drafts
- E2E: continuous conversation → draft object updated (no execution)

**Spec Trace**: Unified §5.1, §11

---

### Batch 5 — Digital Self
**Modules**: B6
**Scope**:
- Digital Self service as sole memory gateway
- Vector + graph + KV entity registry
- Provenance model (EXPLICIT/OBSERVED)
- Read/write rules
- Retriever authority

**Tests**:
- Unit: provenance enforcement, write gating
- Integration: retrieval returns node-docs + provenance
- E2E: L1 suggests node → DS verifies; observed → tier downgrade flag

**Spec Trace**: Unified §6, §9, Appendix B5, §21.5-21.6; Supplement S9, S16

---

### Batch 6 — Guardrails + Commit State Machine
**Modules**: B8, B11
**Scope**:
- Continuous guardrails checks
- Ambiguity Score >30% → Silence/Clarify
- Server commit state machine persisted durably

**Tests**:
- Unit: guardrail triggers, ambiguity gate
- Integration: draft lifecycle across states
- E2E: ambiguous conversation → silence/clarify; commit persists across restart

**Spec Trace**: Unified §7, Appendix B2, §21.2; Supplement S11, S12

---

### Batch 7 — L2 Sentry + QC Sentry
**Modules**: B9, B10
**Scope**:
- L2 runs BE-only
- L2 invocation only at draft finalization / execute attempt
- CoL trace requirement
- Emotional load cooldown
- QC: persona drift, capability leak, harm projection (span-grounded)

**Tests**:
- Unit: invocation timing enforcement
- Integration: L2 shadow derivation conflict resolver
- E2E: L1/L2 mismatch → clarify; high emotional load → cooldown; QC span grounding required

**Spec Trace**: Unified §5.2-5.3, §10, §21.1-21.4; Supplement S13

---

### Batch 8 — Presence Latch + MIO Signing
**Modules**: B12, B13, M5
**Scope**:
- Touch correlation (10s)
- Tier 1 voice repeat latch rules
- Tier 2 physical touch token
- Tier 3 biometric proof
- MIO canonical schema + TTL
- Replay cache for touch tokens + MIOs

**Tests**:
- Unit: nonce/replay, TTL expiry
- Integration: mobile touch → BE correlation window
- E2E: stale touch token rejected; replay rejected; Tier 3 without biometric denied

**Spec Trace**: Unified §12.2, §13, Appendix B6; §21.6; Supplement S10, S18

---

### Batch 9 — Dispatcher + Tenant Registry
**Modules**: B14, B15, C2
**Scope**:
- Dispatcher schema translation (zero-change)
- Inject tenant API key
- Idempotency {session_id+mio_id}
- Tenant Registry for endpoints/keys
- Start with stub tenant; then real OpenClaw

**Tests**:
- Unit: mapping tables, idempotency
- Integration: signed MIO required
- E2E: MIO → dispatcher → stub executes once; duplicates no-op

**Spec Trace**: Unified §14, Appendix B7-B8, §2.2; Supplement S4

---

### Batch 9.5 — Tenant Provisioning
**Modules**: B21, C4, B15 extensions
**Scope**:
For every subscribed user, provision:
1. MyndLens Tenant Account (tenant_id)
2. Mobile app fully authenticated and paired
3. Dedicated OpenClaw tenant Docker ("Doctor" instance)
4. MyndLens ↔ OpenClaw channel preinstalled

**Tests**:
- Unit: provisioner creates tenant_id, stores endpoint/key refs
- Integration: docker bootstrap applies channel config
- E2E: subscribe → provision → mobile pairs → MIO dispatch reaches tenant docker

**Spec Trace**: Unified §2.2, §14, §17-18; Appendix C1/C2/C6; Supplement S1, S2, S4, S15

---

### Batch 9.6 — Tenant Suspension & Deprovisioning
**Modules**: B22, B15/B16/B19 extensions
**Scope**:

**Suspend (reversible):**
- Disable dispatch (hard gate)
- Revoke/rotate tenant API key
- Invalidate sessions/tokens
- Enforce Read-only mode

**Deprovision (irreversible, policy-gated):**
- Stop and delete tenant docker
- Revoke/delete tenant keys
- Detach mobile bindings
- Delete/export user data
- Preserve legally-required audit metadata

**Tests**:
- Unit: state transitions, key revocation
- Integration: suspended tenant cannot dispatch
- E2E: cancel → suspend → deprovision after grace window

**Spec Trace**: Unified §14-15, §18-20; Supplement S2, S3, S4, S8, S15, S16

---

### Batch 10 — OpenClaw Multi-Tenant Integration
**Modules**: C3, C1
**Scope**:
- Validate multi-tenant OpenClaw docker endpoints
- Confirm zero-code-change interaction
- Bind MyndLens to ObeGee tenancy boundary

**Tests**:
- Integration: tenant isolation enforcement
- E2E: two tenants, ensure no cross-talk

**Spec Trace**: Unified §2.2, §14; Appendix A items 18-19; Supplement S4, S1

---

### Batch 11 — Observability, Rate Limits, Environments
**Modules**: B16, B17, B18
**Scope**:
- Tiered logs (metrics vs audit)
- Redaction policy
- Rate limits per user/device/tenant
- Circuit breakers
- Hard env separation

**Tests**:
- Unit: redaction, rate limit policies
- Integration: env guard prevents prod dispatch from non-prod
- E2E: abuse scenario throttled; logs contain no secrets

**Spec Trace**: Unified §15, §18; Appendix C2/C6/C8; Supplement S8, S12, S14, S15

---

### Batch 12 — Data Governance + Backup/Restore
**Modules**: B19, B16 policy integration
**Scope**:
- Transcript retention policy
- Export/delete workflows
- Backups for Digital Self + audit trails
- Restore preserves provenance integrity

**Tests**:
- Integration: backup + restore in staging
- E2E: delete request removes user data, preserves system integrity

**Spec Trace**: Unified §6.6, §15; Supplement S3, S16

---

### Batch 13 — Prompt "Soul" in Vector Memory
**Modules**: B20
**Scope**:
- Dynamic prompt system (PromptOrchestrator + SectionRegistry)
- "Soul" stored in vector memory (NOT a file)
- Prompts must be **dynamic and continuously learning**
- Personalization allowed; drift forbidden
- Explicit user signal required for self-modification

**Tests**:
- Unit: soul retrieval, version pinning
- Integration: change requires explicit signal
- E2E: personalization applied without instruction drift

**Spec Trace**: Unified §16; Appendix A items 9-11; Supplement S13

---

## 32. GLOBAL EXECUTION RULES

1. **Sequential batches only**: Finish Batch N tests before starting Batch N+1
2. **No schema drift**: All interfaces versioned; changes require ADR + test updates
3. **No execution without MIO**: Enforced from first dispatcher stub onward
4. **Isolation enforced early**: 2 IPs, separate proxies, networks, repos
5. **Failure is safer than action**: Ambiguity → silence/clarify; L2 offline → read-only
6. **No orphan code**: Every module must have tests, docs, cleanup

---

## 33. DELIVERABLES

### Per Module
- Code + unit tests
- Public interface schema (versioned)
- Security & failure-mode notes

### Per Batch
- Integrated modules
- Integration tests
- E2E tests (mobile ↔ BE ↔ dispatcher stub)
- Regression suite update
- Deployment notes (if infra changes)

---

## 34. FINAL RELEASE GATE (DoD)

Release is permitted ONLY if:
- [ ] E2E demonstrates Tier 0/1/2/3 behavior correctly
- [ ] No execution without MIO verified
- [ ] Replay protection verified
- [ ] Tenant isolation verified
- [ ] Read-only safe mode verified
- [ ] Logs redacted (no PII, no secrets)
- [ ] DR tested (backup + restore)
- [ ] Unit + integration + adversarial + regression tests pass
- [ ] No orphan code

---

## 35. TRACEABILITY CHECKLIST

Before closing each batch, verify:
- [ ] Unified Spec Sections 0-21 all mapped
- [ ] Appendix A (decision ledger) items 1-25 all mapped
- [ ] Appendix B (verification patches) B1-B12 all mapped
- [ ] Appendix C (master prompt) C1-C8 all mapped
- [ ] Supplement Spec S1-S18 all mapped

---

## 36. NON-NEGOTIABLES (10 Laws)

1. No execution without signed MIO
2. No bypass of L2 + QC
3. No memory write without provenance
4. Tiers enforced always
5. No orphan code
6. No drift in prompts (personalization yes, drift no)
7. Failure is safer than action
8. Sequential batch execution only
9. MyndLens signing keys NEVER exist in ObeGee containers
10. Any deviation requires ADR referencing this spec

### Additional Cross-System Rules (Infrastructure Spec §10)
- **ObeGee cannot dispatch or execute MyndLens intents**
- **MyndLens cannot assume availability of ObeGee runtime**
- No shared runtime, no shared proxy, no shared signing authority

---

## 37. OPERATIONAL GUARANTEES

This deployment guarantees:
- Independent TLS lifecycle for MyndLens
- Independent proxy reloads and failures
- Zero blast-radius crossover with ObeGee
- Stronger audit and compliance boundaries
- Full alignment with Sovereign Orchestrator principles

---

## 38. DATA STRUCTURES (Python)

### 38.1 Enums
```python
class PromptPurpose(Enum):
    THOUGHT_TO_INTENT = "thought_to_intent"
    DIMENSIONS_EXTRACT = "dimensions_extract"
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"
    SAFETY_GATE = "safety_gate"
    SUMMARIZE = "summarize"
    SUBAGENT_TASK = "subagent_task"

class CacheClass(Enum):
    STABLE = "stable"
    SEMISTABLE = "semistable"
    VOLATILE = "volatile"

class ProvenanceType(Enum):
    EXPLICIT = "explicit"
    OBSERVED = "observed"

class ActionClass(Enum):
    COMM_SEND = "comm_send"
    SCHED_MODIFY = "sched_modify"
    INFO_RETRIEVE = "info_retrieve"
    DOC_EDIT = "doc_edit"
    FIN_TRANS = "fin_trans"
    SYS_CONFIG = "sys_config"
    DRAFT_ONLY = "draft_only"

class RiskTier(Enum):
    TIER_0 = 0  # No latch
    TIER_1 = 1  # Voice latch
    TIER_2 = 2  # Physical latch
    TIER_3 = 3  # Biometric

class KillSwitchMode(Enum):
    NORMAL = 0
    READ_ONLY = 1
    HARD_STOP = 2

class AudioState(Enum):
    LISTENING = "listening"
    CAPTURING = "capturing"
    COMMITTING = "committing"
    THINKING = "thinking"
    RESPONDING = "responding"
```

### 38.2 Core Types
```python
@dataclass
class DimensionRecord:
    type: str  # time/entity/constraint/preference/risk/privacy/budget/urgency/authority
    value: Any
    confidence: float  # 0-1
    source: Literal["explicit", "inferred", "memory"]
    expiry: datetime
    scope: List[str]

@dataclass
class SectionOutput:
    content: Union[str, List[Dict]]
    priority: int
    cache_class: CacheClass
    tokens_est: int
    included: bool
    gating_reason: Optional[str]

@dataclass
class PromptArtifact:
    messages: List[Dict]
    prompt_report: 'PromptReport'
    token_budget_used: int
    stable_hash: str

@dataclass
class MemoryNode:
    id: str  # UUID
    content: str
    embedding: List[float]
    node_type: str  # FACT, PREFERENCE, ENTITY, HISTORY, POLICY
    provenance: ProvenanceType
    confidence: float
    created_at: datetime
    updated_at: datetime
    source: str

@dataclass
class MIO:
    header: Dict
    intent_envelope: Dict
    grounding: Dict
    security_proof: Dict
```

---

# END OF PRD v2.0 (Pass 1 Complete)
