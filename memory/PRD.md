# MyndLens - Product Requirements Document (Consolidated)

> This document consolidates all specification documents for MyndLens development.
> Last Updated: July 2025

---

## 1. PRODUCT OBJECTIVE

Extract user intent from **brief, natural, interactive conversation** and generate **dimensions** to initiate actions with Sovereign safety.

### Core Interaction Truths:
- Proxy does NOT know the goal at start; only user does
- Conversation must be natural and empathetic, not structured Q&A
- Users speak in fragmented thoughts; proxy connects fragments
- Gap-bridging uses Digital Self (Vector-Graph Memory)
- Guardrails checked continuously; immediate tactful refusal if crossed

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

---

## 3. SYSTEM ARCHITECTURE

### 3.1 Two Planes

**Command Plane (MyndLens BE)** - Authoritative
- Session authority (WebSocket)
- STT orchestration
- L1 Scout, L2 Sentry, QC Sentry
- Digital Self service
- Guardrails (continuous)
- Dimension Engine (A + B sets)
- Commit Manager + server-side state machine
- Presence verification (heartbeat + touch)
- MIO signing (ED25519)
- Dispatcher
- Audit & observability

**Execution Plane (OpenClaw)** - Stateless peripheral
- Tenant docker containers
- Executes only translated, signed MIOs
- Receives no transcripts, hypotheses, or memory
- Zero-Code-Change rule: interact only via existing API

### 3.2 Mobile App (Expo)

**Audio State Machine:**
1. LISTENING
2. CAPTURING
3. COMMITTING
4. THINKING
5. RESPONDING

**Key Features:**
- Local VAD (mandatory for UX)
- ~250ms audio chunk streaming
- Hybrid control: STT flow + Execute button
- Execute button = primary control for Sovereign review
- TTS with interruption support
- Heartbeat every 5s

---

## 4. INTENT EXTRACTION STACK

### 4.1 L1 Scout
- High-speed, low-latency (Gemini Flash)
- Running hypothesis; max 3
- Produces L1_Draft_Object with evidence
- Outputs are NON-authoritative

### 4.2 L2 Sentry (BE-only)
- Frontier-class model (Gemini Pro)
- Shadow Derivation (ignores L1 initially)
- Runs ONLY on: Draft finalization OR Execute attempt
- NEVER per transcript fragment

### 4.3 QC Sentry
- Runs after L2, before MIO signing
- Adversarial passes:
  1. Persona Drift
  2. Capability Leak
  3. Harm Projection
- Must cite transcript spans to block; else can only nudge/downgrade

### 4.4 Confidence Gate
- Combined = min(L1_conf, L2_conf)
- abs(delta) ≤ 0.15
- Combined > 0.9
- If failed → Silence/Clarify

---

## 5. DIMENSIONS

### A-Set (Action)
- what, who, when, where, how, constraints

### B-Set (Cognitive)
- urgency, emotional_load, ambiguity, reversibility, user_confidence

### Stability Buffer
- urgency and emotional_load are moving averages
- risky proposals gated until stability

---

## 6. DIGITAL SELF (VECTOR-GRAPH MEMORY)

### Storage Layers:
1. **Vector DB (ChromaDB)** - semantic similarity
2. **Canonical Graph (NetworkX)** - UUID nodes + typed edges
3. **KV Entity Registry (MongoDB)** - human refs → canonical IDs

### Provenance Model:
- `EXPLICIT` - user stated
- `OBSERVED` - inferred
- **Rule:** OBSERVED dependency → Tier 2 downgrade (physical latch required)

### Access Rules:
- ONLY `myndlens-digital-self` service can query/traverse/write
- L1 may suggest nodes (non-authoritative)
- L2 must verify deterministically

### Write Rules:
- Only post-execution OR explicit user confirmation
- Never: policy writes, silent preference mutation, LLM self-learning

---

## 7. ACTION TAXONOMY & RISK TIERS

| Action_Class | Description | Default Tier |
|--------------|-------------|--------------|
| COMM_SEND | Messages (WhatsApp, Email, SMS) | Tier 2 |
| SCHED_MODIFY | Calendar/reminder CRUD | Tier 2 |
| INFO_RETRIEVE | Web/memory/local retrieval | Tier 0 |
| DOC_EDIT | Modify notes/docs/code | Tier 2 |
| FIN_TRANS | Financial/value movement | Tier 3 |
| SYS_CONFIG | Settings/permissions/graph | Tier 2 |
| DRAFT_ONLY | Local-only draft | Tier 0 |

### Tier Requirements:
- **Tier 0**: No latch required
- **Tier 1**: Voice repeat latch (250ms cooldown)
- **Tier 2**: Physical touch token (10s correlation)
- **Tier 3**: Biometric proof (OS-level)

---

## 8. MIO (MASTER INTENT OBJECT)

Non-repudiable signed package containing:
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
    "params": {},
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
    "memory_node_ids": ["uuid1", "uuid2"],
    "provenance_flags": { "uuid1": "EXPLICIT" }
  },
  "security_proof": {
    "touch_event_token": "TOUCH_SIG",
    "signature": "ED25519_SIG"
  }
}
```

**No execution without valid MIO.**

---

## 9. PRESENCE & PHYSICAL LATCH

### Heartbeat:
- Mobile sends encrypted heartbeat every 5s
- BE refuses MIO if heartbeat lost > 15s

### Touch Correlation:
- Tier ≥2 requires Physical-Touch-Timestamp within 10s
- Touch tokens are single-use, bound to mio_id+session_id+device_id

---

## 10. SAFETY GATES

### Silence-Is-Intelligence:
- Ambiguity Score > 30% → Silence/Clarify state
- No draft promoted to execution-eligible

### Chain-of-Logic (CoL):
- L1 must emit CoL trace for every dimension
- Speculative reasoning → L2 triggers Clarification Nudge

### Emotional Load Cooldown:
- High emotional load → Stability Cooldown
- Complex plans blocked until stability criteria met

### Kill-Switch:
- Mode 0: Normal
- Mode 1: Read-only safe mode
- Mode 2: Hard stop

---

## 11. DYNAMIC PROMPT SYSTEM

### Purposes:
1. THOUGHT_TO_INTENT
2. DIMENSIONS_EXTRACT
3. PLAN
4. EXECUTE
5. VERIFY
6. SAFETY_GATE
7. SUMMARIZE
8. SUBAGENT_TASK

### Section Types:
- **Stable**: identity, purpose contract, schema, safety rules
- **Semi-stable**: tools list, skills index, workspace bootstrap
- **Volatile**: task context, recalled memory, injected dimensions

### DimensionsStore:
- type: time/entity/constraint/preference/risk/privacy/budget/urgency/authority
- value, confidence (0-1), source (explicit/inferred/memory)
- expiry, scope

---

## 12. INFRASTRUCTURE (Production)

### IP Topology:
- IP1 → ObeGee Stack
- IP2 → MyndLens Stack

### DNS: DigitalOcean DNS
- api.myndlens.obegee.co.uk → IP2

### Proxy: Nginx
- MyndLens binds IP2:443 only
- Port 80 closed
- No 0.0.0.0 bindings

### TLS: DNS-01 via acme.sh

### Docker Networks:
- `obegee_net` - ObeGee only
- `myndlens_net` - MyndLens only
- No shared networks

### Stack Services:
- myndlens-nginx (public, IP2:443)
- myndlens-gateway
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

---

## 13. BATCH EXECUTION PLAN

| Batch | Focus | Modules |
|-------|-------|---------|
| 0 | Foundations | I1, I2, I5, B16, B18 |
| 1 | Identity + Presence | B1, B2, M2, M6 |
| 2 | Audio Pipeline + TTS | M1, M3, B1, B4 |
| 3 | Managed STT | B3, B4, M2 |
| 4 | L1 Scout + Dimensions | B5, B7 |
| 5 | Digital Self | B6 |
| 6 | Guardrails + Commit | B8, B11 |
| 7 | L2 + QC Sentry | B9, B10 |
| 8 | Presence Latch + MIO | B12, B13, M5 |
| 9 | Dispatcher + Tenant | B14, B15, C2 |
| 9.5 | Tenant Provisioning | B21, C4 |
| 9.6 | Suspension/Deprovision | B22 |
| 10 | OpenClaw Integration | C3, C1 |
| 11 | Observability | B16, B17, B18 |
| 12 | Data Governance | B19 |
| 13 | Prompt Soul | B20 |

---

## 14. NON-NEGOTIABLES

1. No execution without signed MIO
2. No bypass of L2 + QC
3. No memory write without provenance
4. Tiers enforced
5. No orphan code
6. No drift in prompts
7. Failure is safer than action
8. Sequential batch execution only

---

## 15. SUPPLEMENTARY RULES (S1-S18)

- S1: User-Device-Session binding with device keypair
- S2: ED25519 keys encrypted, rotatable, revocation invalidates MIOs
- S3: No raw audio storage, encrypted transcripts, export/delete support
- S4: Tenant Registry authoritative, per-tenant isolation
- S5: STT fail → pause+retry/text; L2 offline → read-only
- S6: Draft Card shows action/target/timing/tier; Tier≥2 needs confirmation
- S7: Server = time authority; device timezone explicit
- S8: Tiered logs, PII redacted, role-restricted access
- S9: Same-name disambiguation, explicit channel binding
- S10: Touch tokens single-use, bound to mio_id+session_id+device_id
- S11: Durable commit state machine, exactly-once
- S12: Rate limits per user/device/tenant, circuit breakers
- S13: Prompt injection detection, sanitized retrieval
- S14: Versioned schemas (WS, L1, MIO), backward compat
- S15: Hard env separation (dev/staging/prod)
- S16: Backup Digital Self + audit, restore preserves provenance
- S17: Execute disabled without heartbeat, buffer limits
- S18: OS-level biometric for Tier 3

---

# END OF PRD
