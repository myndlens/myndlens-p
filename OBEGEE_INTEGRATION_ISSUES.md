# ObeGee Integration — Issues & Fix Requirements

**Raised by:** MyndLens Agent  
**Date:** 2026-02-19  
**Repo:** `myndlens/myndlens-p` (branch: `main`)  
**Priority:** P0 — Blocking production go-live

---

## Summary

MyndLens backend has been fully built and is production-ready. Two infrastructure blockers are preventing end-to-end production testing. Both require action from the ObeGee team or the infrastructure admin.

---

## Issue 1 — `api.obegee.co.uk` Does Not Exist (P0)

### What was found

```
$ curl https://api.obegee.co.uk
curl: (6) Could not resolve host: api.obegee.co.uk
```

DNS lookup for `api.obegee.co.uk` returns **no record**. The subdomain is not provisioned.

### Where this is used in MyndLens

MyndLens backend dispatches approved mandates via:

```
POST {OBEGEE_API_URL}/dispatch/mandate
GET  {OBEGEE_API_URL}/dispatch/status/{execution_id}
```

`OBEGEE_API_URL` is set in `backend/.env`. Without a valid URL, any user tapping **Approve** in the app will receive:

```
DispatchBlockedError: OBEGEE_API_URL is not configured.
Set OBEGEE_API_URL=https://obegee.co.uk/api in backend/.env
```

### What MyndLens needs from ObeGee

1. Confirm the correct base URL for mandate dispatch API. e.g.:
   - `https://obegee.co.uk/api`
   - `https://api.obegee.co.uk` (once provisioned)
   - Or another URL

2. Confirm the exact endpoint paths:
   - Mandate dispatch: `POST {base}/dispatch/mandate`
   - Execution status poll: `GET {base}/dispatch/status/{execution_id}`

3. Confirm the authentication header format:
   - MyndLens currently sends: `Authorization: Bearer {api_token}`
   - Confirm if this is correct or if a different token/header is expected

4. Provide the expected request payload schema for `POST /dispatch/mandate`. MyndLens currently sends:

```json
{
  "mandate_id": "string",
  "tenant_id": "string",
  "intent": "string",
  "action_class": "string",
  "dimensions": { "a_set": {}, "b_set": {} },
  "generated_skills": ["skill-name-1", "skill-name-2"],
  "assigned_agent_id": "string or null"
}
```

5. Confirm the response schema for `POST /dispatch/mandate`. MyndLens expects:
```json
{ "execution_id": "string" }
```

6. Confirm the response schema for `GET /dispatch/status/{execution_id}`. MyndLens expects:
```json
{
  "status": "EXECUTING | DELIVERING | COMPLETED | FAILED",
  "sub_status": "optional string describing current step"
}
```

---

## Issue 2 — `app.myndlens.com` SSL Certificate Mismatch (P0)

### What was found

The domain `app.myndlens.com` resolves to IP `139.59.200.76` (a Digital Ocean server). The server is reachable on port 443, TLS handshake completes, but the certificate presented is:

```
Subject: CN = obegee.co.uk
Subject Alternative Names: DNS:obegee.co.uk, DNS:www.obegee.co.uk
```

The certificate does **not** include `app.myndlens.com` as a Subject Alternative Name.

```
SSL: no alternative certificate subject name matches target host name 'app.myndlens.com'
```

This causes every HTTPS call from the MyndLens mobile app (APK) to fail:

```
TLS certificate verification failed → connection aborted
```

### Impact

- The production APK (built with `https://app.myndlens.com` baked in) **cannot connect to the backend at all**
- All API calls, WebSocket connections, and authentication fail at the TLS layer
- No end-to-end testing is possible until this is resolved

### Root Cause

The DNS for `app.myndlens.com` points to the same server IP as `obegee.co.uk` (`139.59.200.76`). The server is serving the `obegee.co.uk` certificate for all requests on that IP, including those for `app.myndlens.com`.

### Fix Required

**Option A — Recommended: Issue a separate TLS certificate for `app.myndlens.com`**

On the server `139.59.200.76`:

```bash
# Using Let's Encrypt / Certbot with nginx
sudo certbot --nginx -d app.myndlens.com

# Or using certbot standalone
sudo certbot certonly --standalone -d app.myndlens.com
```

Then configure nginx to serve the correct certificate for `app.myndlens.com` requests (SNI-based virtual hosting).

Nginx config example:
```nginx
server {
    listen 443 ssl;
    server_name app.myndlens.com;

    ssl_certificate     /etc/letsencrypt/live/app.myndlens.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.myndlens.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8001;  # MyndLens FastAPI backend
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";  # Required for WebSocket
    }
}
```

**Option B: Point `app.myndlens.com` to a different server**

If MyndLens backend is deployed to a different Digital Ocean droplet, update DNS:
- Change the A record for `app.myndlens.com` to the new server IP
- Issue a TLS certificate on that server

---

## Issue 3 — JWKS URL (Informational — No Action Needed)

The JWKS endpoint for token validation is live and returning valid keys:

```
GET https://obegee.co.uk/.well-known/jwks.json  →  200 OK
Returns: RSA RS256 public key
```

MyndLens currently uses `OBEGEE_TOKEN_VALIDATION_MODE=HS256` (shared secret) for development.  
For production, set `OBEGEE_TOKEN_VALIDATION_MODE=JWKS` in `backend/.env` and this endpoint will be used automatically. No changes needed on the ObeGee side.

---

## Issue 4 — ObeGee Channel Adapter IP (Needs Confirmation)

The MyndLens codebase references `CHANNEL_ADAPTER_IP=138.68.179.111` (found in code comments as "prod value"). 

Please confirm:
1. Is `138.68.179.111` the correct IP for the ObeGee Channel Adapter?
2. Is port `8080` correct for the dispatch endpoint (`http://{IP}:8080/v1/dispatch`)?
3. What is the `X-MYNDLENS-DISPATCH-TOKEN` value to use in the dispatch header?

---

## What MyndLens Has Already Done

For reference, here is what has been implemented and is ready for integration:

| Component | Status |
|---|---|
| WebSocket gateway (`/api/ws`) | ✅ Ready |
| SSO token validation (HS256 + JWKS) | ✅ Ready |
| L1 Scout (intent classification, Gemini Flash) | ✅ Ready |
| L2 Sentry (shadow verification, Gemini Pro) | ✅ Ready |
| QC Sentry (adversarial check, Gemini Flash) | ✅ Ready |
| Skills library (73 skills, searchable) | ✅ Ready |
| Agent lifecycle (CREATE/MODIFY/RETIRE/DELETE) | ✅ Ready |
| Mandate dispatch pipeline (L2→QC→Skills→Agent→Dispatch) | ✅ Ready |
| MIO signing + verification (ED25519) | ✅ Ready |
| `OBEGEE_API_URL` config key | ✅ Ready — set in `.env` |
| `CHANNEL_ADAPTER_IP` config key | ✅ Ready — set in `.env` |
| `OBEGEE_MONGO_URL` config key | ✅ Ready — set in `.env` |
| Mandate polling loop (`/dispatch/status/{id}`) | ✅ Ready |
| Webhook receiver (`/api/dispatch/delivery-webhook`) | ✅ Ready |

---

## Production `.env` Values Needed from ObeGee Team

Once the above issues are resolved, set these in `backend/.env` on the production server:

```env
# Required — currently missing
OBEGEE_API_URL=<confirmed mandate dispatch base URL>
CHANNEL_ADAPTER_IP=<confirmed channel adapter IP>
OBEGEE_MONGO_URL=<mongodb connection string for ObeGee shared DB>

# Switch to JWKS in production
OBEGEE_TOKEN_VALIDATION_MODE=JWKS

# Disable mock IDP in production
ENV=prod
ENABLE_OBEGEE_MOCK_IDP=false
MYNDLENS_BASE_URL=https://app.myndlens.com
```

---

## Contact / Repo

- **GitHub Repo:** `https://github.com/myndlens/myndlens-p`
- **Branch:** `main`
- **This document:** `OBEGEE_INTEGRATION_ISSUES.md` (root of repo)
- **Deployment instructions:** `OBEGEE_DEPLOYMENT_INSTRUCTIONS.md`
- **API spec (existing):** `OBEGEE_API_REQUIREMENTS_SPEC.md`
