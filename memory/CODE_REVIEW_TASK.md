# MyndLens + ObeGee — Production Hardening Code Review

## Objective
Perform a comprehensive security, reliability, and correctness audit of the entire MyndLens + ObeGee codebase. **This is a READ-ONLY review — do NOT modify any code.** Produce a detailed findings report with prioritized recommendations.

---

## Scope

### Repositories
1. **MyndLens Backend** (`backend/`) — Voice pipeline, WebSocket server, L1 Scout, Digital Self, MCP, Proactive Intelligence, Guardrails
2. **ObeGee Backend** (`backend/` on getopenclaw) — Subscriptions, Billing, Tenants, WhatsApp pairing, Gmail/IMAP extraction, Auth
3. **MyndLens Mobile App** (`frontend/`) — React Native/Expo, Talk screen, Settings, Onboarding, Login
4. **ObeGee Dashboard** (`frontend/` on getopenclaw) — React, Dashboard pages, Integrations, Checkout
5. **Runtime Scripts** — `wa_pair_v5.mjs`, `wa_ds_extractor.mjs`, `whatsapp_pairing_service.js`, `provision_tenant.sh`

### Architecture
```
Control Plane (178.62.42.175)
  ├── ObeGee Backend (Docker, port 8001)
  ├── MyndLens Backend (Docker, port 8002)
  ├── MongoDB (Docker, port 27017)
  └── Nginx (TLS termination)

Runtime Server (143.198.241.199)
  ├── Per-tenant OpenClaw containers (Docker)
  ├── WhatsApp Pairing Service (Node.js, port 8081)
  └── Provisioning scripts
```

---

## Review Categories

### 1. Authentication & Authorization (CRITICAL)

Review these files and answer:
- `backend/auth/tokens.py` — Is JWT generation/validation fail-closed? Are algorithms pinned? Is there algorithm confusion risk (RS256 vs HS256)?
- `backend/config/settings.py` — Are ALL secrets required (no fallback defaults)? What happens if env vars are missing?
- `backend/config/validators.py` — Is startup validation comprehensive? Are there secrets that should be checked but aren't?
- `backend/server.py` — CORS configuration: are origins locked to production domains? Any wildcard leakage?
- `backend/gateway/ws_server.py` — WebSocket auth flow: is the SSO token validated on every connection? Can a user access another user's session? Is `_session_auth` scoped correctly?
- `backend/routes/myndlens.py` — `/login` and `/auto-pair` endpoints: is password hashing secure (bcrypt/argon2)? Are pairing tokens single-use? Is there brute-force protection?
- `backend/helpers.py` — `get_current_user()`: does it handle all token types correctly (HS256 login JWT, RS256 SSO JWT, session tokens)?

**Questions to answer:**
- Can a user forge a token if they know the algorithm but not the secret?
- Can user A access user B's Digital Self data via MCP tools?
- Are pairing codes/tokens rate-limited against brute force?
- What happens if the MongoDB session collection is cleared — does the system fail open or closed?

### 2. Data Privacy & Confidentiality

Review these files:
- `backend/mcp/ds_server.py` — Do ALL MCP tools respect the `include_confidential` parameter? Is there a path where confidential data leaks without biometric approval?
- `backend/memory/retriever.py` — Is the `recall()` function always scoped to `user_id`? Can a query return another user's data?
- `backend/memory/ds_ingest.py` — When ingesting, is `user_id` always set? Could a missing user_id cause data to be stored without ownership?
- `backend/memory/client/vector.py` — ChromaDB queries: is the `where` filter always applied? What happens if the filter is omitted?
- `backend/guardrails/self_awareness.py` — Are any self-awareness responses leaking internal architecture details (server IPs, database names, API keys)?
- `backend/routes/gmail_extract.py` — Are Gmail OAuth tokens stored securely? Are they encrypted at rest? Can one user's token be used to access another user's email?
- `wa_ds_extractor.mjs` — After extraction, are raw messages deleted? Is the `/tmp/wa_ds_messages_*.json` file cleaned up?

**Questions to answer:**
- If I know a user_id, can I call MCP tools directly via the REST API without authentication?
- Are there any endpoints that return raw WhatsApp/email message content to the client?
- Is the confidentiality flag enforced at the TTS output boundary (not just RAG query)?
- What happens to the message store file if the extraction crashes mid-way?

### 3. Input Validation & Injection

Review these files:
- `backend/gateway/ws_server.py` — All `payload.get()` calls: is user input sanitized before being passed to LLM prompts? Could a user inject instructions via voice transcript?
- `backend/intent/fragment_analyzer.py` — Is the fragment text sanitized before being embedded in the LLM prompt?
- `backend/l1/scout.py` — Is the transcript sanitized before being passed to the prompt orchestrator?
- `backend/routes/billing.py` — Is the Stripe session creation safe from parameter injection? Can a user modify the amount client-side?
- `backend/routes/whatsapp.py` — Phone number validation: can malformed numbers cause issues?
- `wa_pair_v5.mjs` — Is the phone number sanitized before being passed to Baileys `requestPairingCode`?
- `provision_tenant.sh` — Are tenant IDs and slugs sanitized before being used in shell commands? SQL/command injection risk?

**Questions to answer:**
- Can a user say "Ignore all previous instructions and..." via voice to hijack the LLM?
- Can a malicious workspace slug like `; rm -rf /` cause shell injection during provisioning?
- Can a user modify the Stripe checkout amount by intercepting the API call?

### 4. Error Handling & Resilience

Review these files:
- `backend/gateway/ws_server.py` — All `try/except` blocks: are exceptions logged with enough context? Are there bare `except:` blocks that swallow errors silently?
- `backend/gateway/conversation_state.py` — What happens if `ConversationState` grows unbounded (memory leak)?
- `backend/proactive/scheduler.py` — If the scheduler loop crashes, does it restart? Is there a watchdog?
- `backend/proactive/nudge_engine.py` — If MCP tools fail during nudge generation, does the entire briefing fail?
- `whatsapp_pairing_service.js` — If the extract job hangs indefinitely, is there a timeout? What happens to orphaned Docker processes?
- `backend/stt/provider/deepgram.py` — If Deepgram is down, does the system fail gracefully or hang?
- `backend/tts/orchestrator.py` — If ElevenLabs is down, does TTS fall back to mock?

**Questions to answer:**
- Is there a maximum session/connection limit? What happens at 1000 concurrent WebSocket connections?
- Are there any infinite loops possible in the clarification state machine?
- What happens if MongoDB goes down mid-request?
- Are background tasks (scheduler, extraction) properly cancelled on shutdown?

### 5. Secrets & Configuration

Review these files:
- `docker-compose.yml` (control plane) — Are secrets passed via env vars (not hardcoded in the file)? Are any secrets visible in Docker inspect?
- `backend/.env` — Are there any secrets committed to git?
- `provision_tenant.sh` — Are tenant-specific secrets generated securely (sufficient entropy)?
- `whatsapp_pairing_service.js` — Is the API key (`whatsapp_pairing_secret_2026`) hardcoded?

**Questions to answer:**
- If someone gains read access to the MongoDB, what secrets can they extract?
- Are API keys rotatable without downtime?
- Is there a secrets management strategy (Vault, AWS Secrets Manager) or is everything in env vars?

### 6. Performance & Scalability

Review these files:
- `backend/gateway/ws_server.py` — In-memory dicts (`_session_contexts`, `_clarification_state`, `_session_question_count`, `_fragment_locks`, `_biometric_events`): what happens when these grow? Is there cleanup?
- `backend/memory/client/vector.py` — ChromaDB in-process: what's the vector limit? What happens at 100K vectors?
- `backend/proactive/scheduler.py` — The scheduler iterates `_active_sessions` every 60s. At 1000 users, is this efficient?
- `wa_ds_extractor.mjs` — 50 contacts × LLM call: can this be parallelized?
- `backend/routes/gmail_extract.py` — Gmail API rate limits: are we respecting them? What happens if we exceed the quota?

**Questions to answer:**
- What is the maximum number of concurrent tenants the runtime server can support?
- What is the memory footprint per active WebSocket session?
- Are there any O(n²) or worse algorithms in hot paths?

### 7. Dependency & Supply Chain

- Run `pip list --outdated` on the MyndLens backend — are there known CVEs in current dependencies?
- Check `package.json` for the MyndLens app — any outdated packages with known vulnerabilities?
- Is `emergentintegrations` pinned to a specific version?
- Are Docker base images pinned to specific digests (not just `latest` tags)?

### 8. Logging & Observability

- Are authentication failures logged with enough detail for incident response?
- Are there any logs that accidentally include secrets, tokens, or PII?
- Is there structured logging (JSON) or just plain text?
- Can we trace a request from voice input → STT → L1 → mandate → execution → result using log correlation?

---

## Output Format

Produce a report with:

```
## Finding [N]: [Title]
- **Severity:** CRITICAL / HIGH / MEDIUM / LOW / INFO
- **Category:** Auth | Privacy | Injection | Resilience | Secrets | Performance | Dependency | Logging
- **File(s):** [exact file paths]
- **Line(s):** [line numbers if applicable]
- **Description:** [what the issue is]
- **Impact:** [what could go wrong]
- **Recommendation:** [how to fix it]
- **Evidence:** [code snippet or command output]
```

Order findings by severity (CRITICAL first).

---

## Constraints

1. **DO NOT modify any code.** This is a read-only audit.
2. **DO NOT run any destructive commands.** Read-only file access and non-mutating API calls only.
3. **DO NOT expose or log any actual secrets.** Redact values in your report.
4. **You may run:** `grep`, `cat`, `find`, `ruff check`, `python -m compileall`, `pytest --collect-only`, `pip list`, `npm ls`
5. **You may call:** health check endpoints, tool discovery endpoints (GET only)
6. **You may NOT call:** any POST/PUT/DELETE endpoints, any authentication endpoints with real credentials

---

## Priority Focus Areas

Given what we know about the system:
1. **WebSocket auth bypass** — can someone connect without a valid token?
2. **Cross-tenant data leakage** — can user A see user B's Digital Self?
3. **Prompt injection** — can voice input hijack the LLM?
4. **Stripe amount manipulation** — can the payment amount be tampered?
5. **Shell injection in provisioning** — can a malicious slug cause RCE?
6. **WhatsApp message persistence** — are raw messages cleaned up after extraction?

---

## Deliverable

A structured findings report (Markdown) saved to `/app/memory/SECURITY_REVIEW.md` with all findings, severity ratings, and prioritized remediation recommendations.
