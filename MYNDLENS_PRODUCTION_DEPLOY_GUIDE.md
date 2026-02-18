# MyndLens Production Deployment Guide — For ObeGee Dev Agent

**Date:** February 18, 2026
**Repository:** `myndlens/myndlens-p` (branch: `main`)
**Target:** Docker container on Digital Ocean VPS, accessible at `app.myndlens.com`

---

## Architecture

```
Mobile App (Expo)
  |
  v  HTTPS / WSS
app.myndlens.com (Nginx reverse proxy)
  |
  v  :8001
MyndLens Backend (FastAPI in Docker)
  |
  v  :27017
MongoDB Cluster (persistent data)
```

---

## 1. Docker Image Build

### Dockerfile (already at `/app/Dockerfile`)

**Build from repo root:**
```bash
docker build -t myndlens-backend:latest .
```

**Key requirements inside the container:**
- Python 3.11+
- All pip packages from `backend/requirements.txt`
- ChromaDB (in-memory vector store, no external service needed)
- The `backend/assets/skills-library.json` file MUST be included in the image

### Environment Variables (backend/.env)

```env
MONGO_URL="mongodb://<PRODUCTION_MONGO_HOST>:27017"
DB_NAME="myndlens_prod"
DEEPGRAM_API_KEY="fb64e0232e13c45d0f68d014397bc9684ad8f92c"
ELEVENLABS_API_KEY="sk_0cedb93d8dcab1db866929e5ef78d5afccfd22eca9e8d60d"
MOCK_STT=False
MOCK_TTS=False
MOCK_LLM=False
EMERGENT_LLM_KEY="sk-emergent-45aD017A777372bFe7"
```

**CRITICAL:** Do NOT set `MOCK_LLM=True` in production.

---

## 2. MongoDB Collections

The backend auto-creates all collections on startup. No manual schema setup needed.

### Collections Created Automatically:

| Collection | Purpose | Auto-populated on startup? |
|---|---|---|
| `sessions` | WebSocket sessions | On first connection |
| `audit_events` | Security audit trail | On first event |
| `transcripts` | Voice transcripts | On first voice session |
| `prompt_snapshots` | LLM prompt audit trail | On first LLM call |
| `commits` | Commit state machine | On first commit |
| `digital_self_kv` | Entity resolution (KV) | On first onboarding |
| `onboarding` | Onboarding status | On first user setup |
| `prompt_outcomes` | Prompt accuracy tracking | On first outcome track |
| `user_corrections` | User correction feedback | On first correction |
| `prompt_experiments` | A/B test experiments | On first experiment |
| `prompt_versions` | Prompt version history | On first version create |
| `user_profiles` | Per-user optimization | On first profile update |
| `optimization_runs` | Scheduled optimization | On first optimization run |
| `agents` | Agent lifecycle (CRUD) | On first agent create |
| `agent_archives` | Deleted agent archives | On first agent delete |
| `nicknames` | Proxy nickname per user | On first nickname set |
| `soul_versions` | Soul version metadata | On startup (auto) |
| **`skills_library`** | **OC Hub skills index** | **On startup (auto)** |
| `setup_users` | Setup wizard accounts (dev) | On first registration |
| `setup_tenants` | Setup wizard tenants (dev) | On first tenant create |

### Auto-Indexed on Startup:

The backend lifespan handler runs these automatically:
1. `init_indexes()` — MongoDB indexes for all collections
2. `initialize_base_soul()` — Seeds ChromaDB with soul fragments (1 merged fragment)
3. **`load_and_index_library()`** — Indexes 73 skills from `skills-library.json` into `skills_library` collection with text search index

**No manual MongoDB seeding required.**

---

## 3. Nginx Configuration

```nginx
server {
    listen 443 ssl;
    server_name app.myndlens.com;

    ssl_certificate /etc/letsencrypt/live/app.myndlens.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.myndlens.com/privkey.pem;

    # API routes
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

---

## 4. Docker Run Command

```bash
docker run -d \
  --name myndlens-backend \
  --restart unless-stopped \
  -p 8001:8001 \
  -v /opt/myndlens/backend/.env:/app/backend/.env:ro \
  -e TZ=UTC \
  myndlens-backend:latest
```

---

## 5. Startup Verification

After container starts, verify:

```bash
# Health check
curl https://app.myndlens.com/api/health

# Expected response:
# {"status": "healthy", "env": "dev", "version": "0.2.0", ...}

# Skills library loaded
curl https://app.myndlens.com/api/skills/stats

# Expected: {"total_skills": 73, "categories": [...], "indexed": true}

# Soul initialized
curl https://app.myndlens.com/api/soul/status

# Expected: {"fragments": 1, ...}
```

---

## 6. Mobile App Configuration

The Expo mobile app is configured to point to:
```
EXPO_PUBLIC_BACKEND_URL=https://app.myndlens.com
```

This means:
- **REST API:** `https://app.myndlens.com/api/*`
- **WebSocket:** `wss://app.myndlens.com/api/ws`
- **Pairing:** `POST https://app.myndlens.com/api/sso/myndlens/pair`

---

## 7. Mock vs Production Endpoints

The following endpoints are **dev mocks** and should be replaced with live ObeGee APIs in production:

| Mock Endpoint | Production Replacement |
|---|---|
| `/api/dashboard/*` | `https://obegee.co.uk/api/myndlens-dashboard/*` |
| `/api/setup/*` | `https://obegee.co.uk/api/*` (auth, tenants, billing) |
| `/api/sso/myndlens/pair` | `https://obegee.co.uk/api/myndlens/pair` |

**To disable dev mocks in production:** Set `ENV=prod` in backend `.env`. The mock pairing endpoint is already gated behind `ENV != "prod"`.

---

## 8. Post-Deployment Checklist

- [ ] Docker image built and pushed
- [ ] MongoDB accessible from container (test connection string)
- [ ] `.env` file in place with production credentials
- [ ] Nginx configured with SSL for `app.myndlens.com`
- [ ] Container started and healthy (`/api/health` returns 200)
- [ ] Skills library auto-indexed (check logs for "Skills library indexed: 73 skills")
- [ ] Soul initialized (check logs for "Base soul initialized: 1 fragments")
- [ ] WebSocket connections working (`wss://app.myndlens.com/api/ws`)
- [ ] Mobile app can pair with 6-digit code
- [ ] TTS working (ElevenLabs key valid)
- [ ] STT working (Deepgram key valid)
- [ ] LLM working (Emergent key valid)

---

## 9. Monitoring

**Logs:** `docker logs -f myndlens-backend`

**Key log lines to watch:**
```
MyndLens BE starting — env=prod
MongoDB indexes initialized
Base soul initialized: 1 fragments
Skills library indexed: 73 skills from 11 categories
MyndLens BE ready
```

**Error indicators:**
- `ELEVENLABS_API_KEY` errors → Check key permissions
- `DEEPGRAM_API_KEY` errors → Check key validity
- `EMERGENT_LLM_KEY` errors → Check balance
- MongoDB connection errors → Check MONGO_URL and network

---

**This guide is sufficient for the ObeGee Dev Agent to deploy MyndLens to production. All data seeding is automatic — just start the container with the correct `.env`.**
