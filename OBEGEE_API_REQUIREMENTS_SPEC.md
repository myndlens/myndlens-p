# ObeGee API Requirements Specification for MyndLens Integration

**Date:** February 18, 2026
**From:** MyndLens Dev Agent
**To:** ObeGee Dev Agent
**Purpose:** Define all APIs that ObeGee must expose for MyndLens mobile app integration

---

## Overview

MyndLens mobile app currently uses **mock endpoints** for all ObeGee interactions. This spec defines the exact API contracts that the ObeGee backend must implement so MyndLens can switch from mocks to live APIs.

**Base URL expected:** `https://obegee.co.uk/api/myndlens`
**Auth:** All endpoints (except register, plans, check-slug) require `Authorization: Bearer <access_token>` header. The token is issued at registration or pairing.

---

## API Group 1: Authentication & Pairing

### 1.1 POST `/auth/register`

**Purpose:** Create a new user account from the MyndLens setup wizard.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword",
  "name": "John Doe"
}
```

**Response (201):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "user_id": "user_abc123",
    "email": "user@example.com",
    "name": "John Doe"
  }
}
```

**Response (409):**
```json
{
  "detail": "Email already registered"
}
```

---

### 1.2 POST `/auth/pair`

**Purpose:** Pair a MyndLens mobile device using a 6-digit code generated from the ObeGee Dashboard.

**Request:**
```json
{
  "code": "123456",
  "device_id": "dev_abc123xyz"
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "tenant_id": "tenant_abc123",
  "workspace_slug": "my-workspace",
  "runtime_endpoint": "https://my-workspace.obegee.co.uk",
  "dispatch_endpoint": "https://my-workspace.obegee.co.uk/api/dispatch",
  "session_id": "mls_abc123"
}
```

**Token Claims (JWT payload):**
```json
{
  "iss": "obegee",
  "aud": "myndlens",
  "sub": "user_abc123",
  "obegee_user_id": "user_abc123",
  "myndlens_tenant_id": "tenant_abc123",
  "subscription_status": "ACTIVE",
  "iat": 1708300000,
  "exp": 1710892000,
  "jti": "unique-token-id"
}
```

**Error (401):** Invalid or expired pairing code
**Error (400):** Invalid code format (must be 6 digits)

---

### 1.3 POST `/auth/extend-pairing`

**Purpose:** Exchange pairing session for a persistent API token for dashboard access.

**Request:**
```json
{
  "code": "123456",
  "device_id": "dev_abc123xyz"
}
```

**Response (200):**
```json
{
  "api_token": "persistent-token-for-dashboard-apis"
}
```

---

## API Group 2: Setup Wizard

### 2.1 GET `/setup/check-slug/{slug}`

**Purpose:** Check if a workspace slug is available. No auth required.

**Response (available):**
```json
{
  "available": true
}
```

**Response (taken):**
```json
{
  "available": false,
  "reason": "taken",
  "suggestions": ["my-workspace-1", "my-workspace-ai", "my-my-workspace"]
}
```

**Response (invalid format):**
```json
{
  "available": false,
  "reason": "invalid_format",
  "suggestion": "my-workspace"
}
```

**Validation:** Slug must match `^[a-z0-9-]{3,30}$`

---

### 2.2 POST `/setup/create-tenant`

**Purpose:** Create a new tenant/workspace after account registration.

**Request:**
```json
{
  "workspace_slug": "my-workspace"
}
```

**Response (201):**
```json
{
  "tenant_id": "tenant_abc123",
  "workspace_slug": "my-workspace"
}
```

---

### 2.3 GET `/setup/plans`

**Purpose:** List available subscription plans. No auth required.

**Response (200):**
```json
[
  {
    "plan_id": "starter",
    "name": "Starter",
    "price": 9,
    "currency": "GBP",
    "features": ["1 Agent", "5,000 messages/mo", "Basic tools", "Community support"]
  },
  {
    "plan_id": "pro",
    "name": "Pro",
    "price": 29,
    "currency": "GBP",
    "features": ["5 Agents", "50,000 messages/mo", "All tools", "Priority support", "Custom models (BYOK)"]
  },
  {
    "plan_id": "enterprise",
    "name": "Enterprise",
    "price": 99,
    "currency": "GBP",
    "features": ["Unlimited Agents", "Unlimited messages", "All tools + custom", "Dedicated support", "SSO & audit logs"]
  }
]
```

---

### 2.4 POST `/setup/checkout`

**Purpose:** Initiate a Stripe checkout session for the selected plan.

**Request:**
```json
{
  "plan_id": "pro",
  "tenant_id": "tenant_abc123"
}
```

**Response (200):**
```json
{
  "checkout_url": "https://checkout.stripe.com/pay/cs_test_...",
  "session_id": "cs_test_abc123"
}
```

MyndLens opens `checkout_url` in a WebView. Stripe redirects back after payment.

---

### 2.5 POST `/setup/activate/{tenant_id}`

**Purpose:** Activate/provision a workspace after successful payment.

**Response (200):**
```json
{
  "status": "READY",
  "tenant_id": "tenant_abc123"
}
```

**Status values:** `PENDING_PAYMENT` → `PROVISIONING` → `READY` → `ERROR`

---

### 2.6 GET `/setup/tenant/{tenant_id}`

**Purpose:** Poll tenant provisioning status during workspace activation.

**Response (200):**
```json
{
  "status": "READY",
  "tenant_id": "tenant_abc123",
  "workspace_slug": "my-workspace"
}
```

---

### 2.7 POST `/setup/generate-code`

**Purpose:** Generate a 6-digit pairing code for auto-pairing after workspace creation.

**Response (200):**
```json
{
  "code": "847291",
  "expires_in_seconds": 600
}
```

---

### 2.8 PATCH `/setup/preferences`

**Purpose:** Save user preferences including delivery channel configuration.

**Request:**
```json
{
  "user_id": "user_abc123",
  "phone_number": "+447123456789",
  "timezone": "Europe/London",
  "notifications_enabled": true,
  "delivery_channels": ["whatsapp", "email"],
  "channel_details": {
    "whatsapp": "+447123456789",
    "email": "user@example.com"
  }
}
```

**Response (200):**
```json
{
  "message": "Preferences updated",
  "delivery_channels": ["whatsapp", "email"]
}
```

**Supported delivery channels:** `whatsapp`, `email`, `telegram`, `slack`, `sms`, `in_app`

---

## API Group 3: Dashboard

### 3.1 GET `/dashboard/workspace/config`

**Purpose:** Get full workspace configuration for the Dashboard overview tab.

**Response (200):**
```json
{
  "workspace": {
    "tenant_id": "tenant_abc123",
    "slug": "my-workspace",
    "name": "My Workspace",
    "status": "READY",
    "model": "gemini-2.0-flash"
  },
  "subscription": {
    "plan_id": "pro",
    "status": "active",
    "current_period_end": "2026-03-17T00:00:00Z"
  },
  "tools": {
    "enabled": ["web-browser", "file-system", "data-analysis"]
  },
  "approval_policy": {
    "auto_approve_low": true,
    "auto_approve_medium": false
  },
  "integrations": ["google_oauth"],
  "runtime": {
    "status": "running",
    "port": 10010,
    "myndlens_port": 18791
  }
}
```

---

### 3.2 PATCH `/dashboard/workspace/tools`

**Purpose:** Enable/disable tools for the workspace.

**Request:**
```json
{
  "enabled_tools": ["web-browser", "file-system", "email"]
}
```

**Response (200):**
```json
{
  "message": "Tools updated",
  "enabled_tools": ["web-browser", "file-system", "email"]
}
```

---

### 3.3 PATCH `/dashboard/workspace/model`

**Purpose:** Update the LLM model or set a BYOK API key.

**Request:**
```json
{
  "provider": "openai",
  "api_key": "sk-..."
}
```

**Response (200):**
```json
{
  "message": "API key updated",
  "provider": "openai"
}
```

---

### 3.4 GET `/dashboard/workspace/agents`

**Purpose:** List all agents in the workspace.

**Response (200):**
```json
{
  "agents": [
    {
      "id": "python-coder",
      "name": "Python Developer",
      "model": "gemini-2.0-flash",
      "status": "active",
      "skills": ["python-dev", "file-operations"],
      "tools": ["read", "write", "exec"]
    }
  ],
  "total": 1
}
```

---

### 3.5 GET `/dashboard/workspace/usage`

**Purpose:** Get today's usage metrics and subscription limits.

**Response (200):**
```json
{
  "today": {
    "messages": 45,
    "tokens": 12453,
    "tool_calls": 8
  },
  "limits": {
    "messages": 500,
    "tokens": 100000
  },
  "subscription": {
    "plan_name": "Pro",
    "status": "active"
  }
}
```

---

### 3.6 GET `/dashboard/dashboard-url`

**Purpose:** Get a time-limited URL for opening the full ObeGee dashboard in a WebView.

**Response (200):**
```json
{
  "webview_url": "https://obegee.co.uk/dashboard?token=...",
  "expires_in": 3600
}
```

---

## API Group 4: Mandate Dispatch (OpenClaw Integration)

### 4.1 POST `/dispatch/mandate`

**Purpose:** MyndLens sends an approved mandate artefact to ObeGee for OpenClaw execution.

**Request:**
```json
{
  "mandate_id": "mio_abc123",
  "tenant_id": "tenant_abc123",
  "intent": "Send weekly report to team",
  "dimensions": {
    "who": "team@company.com",
    "what": "weekly status report",
    "when": "every Monday 9am",
    "where": "email",
    "how": "summarize project updates"
  },
  "generated_skills": [
    {
      "name": "Report-Generator",
      "baseHubSkill": "report-generator",
      "risk": "medium",
      "install_command": "clawhub install report-generator"
    }
  ],
  "delivery_channels": ["email"],
  "channel_details": {
    "email": "user@example.com"
  },
  "mio_signature": "base64-ed25519-signature",
  "approved_at": "2026-02-18T22:00:00Z"
}
```

**Response (202):**
```json
{
  "execution_id": "exec_abc123",
  "status": "QUEUED",
  "estimated_completion": "2026-02-18T22:05:00Z"
}
```

---

### 4.2 GET `/dispatch/status/{execution_id}`

**Purpose:** Poll execution status for the pipeline progress card.

**Response (200):**
```json
{
  "execution_id": "exec_abc123",
  "status": "EXECUTING",
  "current_stage": "agents_assigned",
  "stage_index": 5,
  "total_stages": 10,
  "stages_completed": [
    "intent_captured",
    "digital_self_enriched",
    "dimensions_extracted",
    "mandate_created",
    "approval_received"
  ],
  "started_at": "2026-02-18T22:00:00Z",
  "updated_at": "2026-02-18T22:02:30Z"
}
```

**Status values:** `QUEUED` → `EXECUTING` → `DELIVERING` → `COMPLETED` → `FAILED`

---

### 4.3 POST `/dispatch/delivery-confirm`

**Purpose:** ObeGee notifies MyndLens that results have been delivered to the user's chosen channels.

**Request (webhook from ObeGee → MyndLens):**
```json
{
  "execution_id": "exec_abc123",
  "status": "COMPLETED",
  "delivered_to": ["whatsapp", "email"],
  "summary": "Weekly report sent to team@company.com via email and WhatsApp",
  "completed_at": "2026-02-18T22:05:00Z"
}
```

---

## Summary of All Endpoints

| # | Method | Path | Auth | Group |
|---|--------|------|------|-------|
| 1 | POST | `/auth/register` | No | Auth |
| 2 | POST | `/auth/pair` | No | Auth |
| 3 | POST | `/auth/extend-pairing` | No | Auth |
| 4 | GET | `/setup/check-slug/{slug}` | No | Setup |
| 5 | POST | `/setup/create-tenant` | Yes | Setup |
| 6 | GET | `/setup/plans` | No | Setup |
| 7 | POST | `/setup/checkout` | Yes | Setup |
| 8 | POST | `/setup/activate/{tenant_id}` | Yes | Setup |
| 9 | GET | `/setup/tenant/{tenant_id}` | Yes | Setup |
| 10 | POST | `/setup/generate-code` | Yes | Setup |
| 11 | PATCH | `/setup/preferences` | Yes | Setup |
| 12 | GET | `/dashboard/workspace/config` | Yes | Dashboard |
| 13 | PATCH | `/dashboard/workspace/tools` | Yes | Dashboard |
| 14 | PATCH | `/dashboard/workspace/model` | Yes | Dashboard |
| 15 | GET | `/dashboard/workspace/agents` | Yes | Dashboard |
| 16 | GET | `/dashboard/workspace/usage` | Yes | Dashboard |
| 17 | GET | `/dashboard/dashboard-url` | Yes | Dashboard |
| 18 | POST | `/dispatch/mandate` | Yes | Dispatch |
| 19 | GET | `/dispatch/status/{execution_id}` | Yes | Dispatch |
| 20 | POST | `/dispatch/delivery-confirm` | Webhook | Dispatch |

**Total: 20 endpoints across 4 groups**

---

## MyndLens Integration Notes

1. **Base URL config:** MyndLens will read `OBEGEE_API_URL` from backend `.env` (e.g., `https://obegee.co.uk/api/myndlens`)
2. **Token storage:** Access token stored in device SecureStore, passed as `Authorization: Bearer <token>`
3. **Mock fallback:** In dev mode (`ENV=dev`), MyndLens falls back to local mock endpoints if ObeGee is unreachable
4. **CORS:** ObeGee must allow requests from MyndLens mobile app (no origin restriction for native apps, but WebView requests need `app.myndlens.com` in allowed origins)
5. **Rate limits:** MyndLens respects standard rate limits. Please document any per-endpoint limits in your API response headers.
6. **Webhook:** For `/dispatch/delivery-confirm`, ObeGee calls MyndLens at `https://app.myndlens.com/api/dispatch/delivery-webhook`

---

**Once these APIs are live, MyndLens will switch from mock mode to production by setting `OBEGEE_API_URL` in the backend `.env` and `ENV=prod`.**
