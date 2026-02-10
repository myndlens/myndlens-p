# MyndLens Full Backend — Pull & Deploy Instructions for ObeGee Dev Agent

> **Status:** READY TO DEPLOY
> **Source:** `github.com/myndlens/myndlens-p`
> **Branch:** `main`
> **Commit:** `26b70f5`

---

## 1. Pull the Code

```bash
git clone git@github.com:myndlens/myndlens-p.git
cd myndlens-p
```

---

## 2. Build Docker Image

```bash
docker build -t myndlens/backend:production-v1 .
```

The Dockerfile:
- Base: `python:3.11-slim`
- Installs all Python dependencies from `backend/requirements.txt`
- Copies full backend code
- Runs as non-root user `myndlens`
- Exposes port `8002`
- Health check: `GET http://localhost:8002/api/health`
- CMD: `uvicorn server:app --host 0.0.0.0 --port 8002`

---

## 3. Push to Registry

```bash
docker push myndlens/backend:production-v1
```

---

## 4. Deploy via DAI

```bash
curl -X POST http://178.62.42.175:8001/internal/myndlens/deploy \
  -H "Content-Type: application/json" \
  -H "X-Internal-API-Key: obegee_internal_production_key_2026" \
  -d '{
    "env": "prod",
    "image_tag": "production-v1",
    "reason": "full_backend_deployment",
    "requested_by": "myndlens_dev_agent",
    "change_ref": "myndlens/myndlens-p@26b70f5"
  }'
```

---

## 5. Required Environment Variables

ObeGee injects these via docker-compose:

```yaml
# Core
ENV: "prod"
PORT: "8002"

# MongoDB (ObeGee shared)
MONGO_URL: "mongodb://host.docker.internal:27017"
DB_NAME: "obegee_production"

# SSO (JWKS mode for production)
OBEGEE_TOKEN_VALIDATION_MODE: "JWKS"
OBEGEE_JWKS_URL: "http://178.62.42.175/.well-known/jwks.json"
ENABLE_OBEGEE_MOCK_IDP: "false"

# ObeGee Shared DB
OBEGEE_MONGO_URL: "mongodb://host.docker.internal:27017"
OBEGEE_DB_NAME: "obegee_production"

# Channel Adapter
CHANNEL_ADAPTER_IP: "138.68.179.111"
MYNDLENS_DISPATCH_TOKEN: "myndlens_dispatch_secret_2026"

# LLM
EMERGENT_LLM_KEY: "sk-emergent-45aD017A777372bFe7"
MOCK_LLM: "false"

# STT / TTS
DEEPGRAM_API_KEY: "fb64e0232e13c45d0f68d014397bc9684ad8f92c"
ELEVENLABS_API_KEY: "sk_2b05fce6a8e8c2d61114dc86855a0daa0ade0adb640020b9"
MOCK_STT: "false"
MOCK_TTS: "false"

# Logging
LOG_LEVEL: "INFO"
LOG_REDACTION_ENABLED: "true"
```

---

## 6. Health Gates (G1–G5)

After deploy, verify:

| Gate | Endpoint | Expected |
|------|----------|----------|
| G1 | `GET /api/health` | `{"status": "healthy", ...}` |
| G2 | WS `/api/ws` + auth | Connection established |
| G3 | Heartbeat 5s | Acknowledged |
| G4 | Execute without heartbeat | Blocked (PRESENCE_STALE) |
| G5 | `GET /api/prompt/compliance` | `rogue_prompt_scan.clean = true` |

---

## 7. What This Replaces

This replaces the minimal stub currently running on IP-2 (139.59.200.76:8002) with the **full MyndLens Command Plane** including:

- L1 Scout (Gemini 2.0 Flash)
- L2 Sentry (Gemini 2.5 Pro)
- QC Sentry (adversarial verification)
- Digital Self (ChromaDB + NetworkX + MongoDB)
- Dynamic Prompt System with LLM Gateway enforcement
- MIO Signing (ED25519)
- Guardrails + Commit State Machine
- Deepgram STT + ElevenLabs TTS
- ObeGee SSO (JWKS validation)
- Channel Adapter dispatch
- Rate Limits + Circuit Breakers
- Soul in Vector Memory
- Full observability + PII redaction

---

## 8. Rollback

If any gate fails:

```bash
curl -X POST http://178.62.42.175:8001/internal/myndlens/rollback \
  -H "Content-Type: application/json" \
  -H "X-Internal-API-Key: obegee_internal_production_key_2026" \
  -d '{"env": "prod", "reason": "gate_failed", "requested_by": "obegee_dai"}'
```

---

## 9. Verification After Deploy

```bash
curl https://myndlens.com/api/health
curl https://myndlens.com/api/prompt/compliance
curl https://myndlens.com/api/soul/status
curl https://myndlens.com/api/metrics
```

---

**END — ObeGee Pull & Deploy Document**
