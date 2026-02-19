# Enable Stripe Sandbox — ObeGee Action Required

**Raised by:** MyndLens Dev Agent  
**Date:** 2026-02-19  
**Priority:** P0 — Blocks MyndLens setup wizard end-to-end

---

## What Is Broken

`POST https://obegee.co.uk/api/billing/checkout` returns **HTTP 500 text/plain** for every call.

```bash
curl -X POST https://obegee.co.uk/api/billing/checkout \
  -H "Authorization: Bearer <valid-token>" \
  -H "Content-Type: application/json" \
  -d '{"plan_id":"plan_starter_early_bird","origin_url":"https://app.myndlens.com","tenant_id":"<tenant_id>"}'

# Returns: HTTP 500 — Internal Server Error
```

**Root cause:** Stripe API keys are not set in the ObeGee backend environment.

---

## What ObeGee Must Do

### Step 1 — Get Stripe test keys

Go to: **https://dashboard.stripe.com/test/apikeys**

Copy:
- **Secret key** — `sk_test_...`
- **Publishable key** — `pk_test_...`

### Step 2 — Get Stripe webhook secret

Go to: **https://dashboard.stripe.com/test/webhooks**

Create a new webhook:
- Endpoint URL: `https://obegee.co.uk/api/billing/webhook` (or your actual webhook path)
- Events to listen for:
  - `checkout.session.completed`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
- Copy the **Signing secret** — `whsec_...`

### Step 3 — Add to ObeGee docker-compose.yml

```yaml
# In the obegee-backend service environment section:
- STRIPE_SECRET_KEY=sk_test_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
- STRIPE_PUBLISHABLE_KEY=pk_test_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
- STRIPE_WEBHOOK_SECRET=whsec_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
- STRIPE_MODE=test
```

### Step 4 — Also create test prices in Stripe

For each plan in your `/billing/plans` response, create a corresponding test price in Stripe dashboard and map `plan_id` → `stripe_price_id` in your backend config.

Current plans from `/billing/plans`:
- `plan_starter_early_bird` — £19.99/month
- `plan_pro_early_bird` — £39.99/month

### Step 5 — Rebuild and redeploy ObeGee backend

```bash
docker-compose up --build -d obegee-backend
```

### Step 6 — Verify

```bash
# Should return a Stripe checkout URL under the "url" key:
TOKEN=$(curl -s -X POST https://obegee.co.uk/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"stripetest@verify.com","password":"Test1234!","name":"Test"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

TENANT_ID=$(curl -s -X POST https://obegee.co.uk/api/tenants/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"workspace_slug":"stripetest","name":"Stripe Test"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['tenant_id'])")

curl -s -X POST https://obegee.co.uk/api/billing/checkout \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"plan_id\":\"plan_starter_early_bird\",\"origin_url\":\"https://app.myndlens.com\",\"tenant_id\":\"$TENANT_ID\"}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('url:', d.get('url','MISSING')[:60])"

# Expected: url: https://checkout.stripe.com/c/pay/...
# Must NOT return: HTTP 500
```

---

## What Happens After This Fix

Once Stripe sandbox is live, the MyndLens setup wizard completes end-to-end:

```
Step 1: Register       → POST /auth/signup          ✅ Working
Step 2: Validate slug  → POST /tenants/validate-slug ✅ Working  
Step 3: Create tenant  → POST /tenants/              ✅ Working
Step 4: Checkout       → POST /billing/checkout      ❌ Broken (this fix)
        User opens Stripe URL → enters test card: 4242 4242 4242 4242
        Stripe webhook fires → ObeGee marks subscription active
Step 5: Activate       → POST /tenants/{id}/activate ⏳ Blocked by Step 4
Step 6: Poll status    → GET /tenants/my-tenant      ✅ Working
Step 7: Generate code  → POST /myndlens/generate-code ⏳ Blocked by Step 5
```

**No MyndLens APK rebuild required.** The current APK already handles the full Stripe flow — it opens the checkout URL in the device browser via `Linking.openURL()`, then polls for activation.

---

## Stripe Test Card

Once sandbox is live, use this card for test payments:

| Field | Value |
|---|---|
| Card number | `4242 4242 4242 4242` |
| Expiry | Any future date |
| CVC | Any 3 digits |
| Name | Any |
