# ObeGee — MyndLens Pairing Code SMS Delivery Spec

**Owner:** ObeGee Platform Team  
**Consumer:** MyndLens app (iOS + Android)  
**Date:** February 2026  
**Status:** Ready for implementation

---

## 1. Overview

When a user pairs MyndLens with their ObeGee workspace, they receive a 6-digit one-time pairing code. This spec defines the SMS format and delivery requirements so the code arrives in a form that iOS and Android can **automatically surface as an OTP suggestion** in the keyboard — eliminating manual entry entirely.

The MyndLens app already implements:
- `textContentType="oneTimeCode"` — iOS keyboard suggestion (works automatically when SMS arrives)
- `autoComplete="sms-otp"` — Android Autofill framework suggestion

Both require the SMS to be correctly formatted. This spec ensures it is.

---

## 2. SMS Message Format

### 2.1 Required Format

```
Your MyndLens pairing code is: 847291

This code expires in 10 minutes. Do not share it.
```

### 2.2 Format Rules

| Rule | Requirement | Reason |
|---|---|---|
| **Code position** | Code must appear as a standalone 6-digit integer, separated from surrounding text by non-digit characters | iOS and Android regex look for isolated digit sequences |
| **Code length** | Exactly 6 digits (`[0-9]{6}`) | App enforces 6-digit validation |
| **No spaces within code** | `847291` not `847 291` | App strips spaces, but OS suggestions work better with unsplit codes |
| **App name in message** | Must contain "MyndLens" | iOS uses app name matching for `textContentType="oneTimeCode"` confidence scoring |
| **Single SMS** | The code must be in a single SMS message, not split across parts | Multi-part MMS breaks OS OTP detection |
| **Max length** | Under 160 characters | Avoids multi-part SMS concatenation |

### 2.3 iOS-Specific: Domain Association (Optional Enhancement)

For the highest-confidence autofill on iOS 14+, append this line to the SMS body:

```
@myndlens.app #847291
```

Format: `@<domain> #<code>` — this is the [Apple one-time code format](https://developer.apple.com/news/technotes/tn3007/) and eliminates any ambiguity. iOS will show the suggestion banner immediately rather than analysing the message text.

**Full recommended message with domain association:**

```
Your MyndLens pairing code is: 847291

@myndlens.app #847291

Expires in 10 minutes. Do not share.
```

### 2.4 Android-Specific: SMS Retriever Hash (Optional Enhancement)

For zero-permission automatic code injection on Android (bypasses the Autofill suggestion step entirely — code fills itself without user interaction), each SMS must end with the app's 11-character hash:

```
Your MyndLens pairing code is: 847291

Expires in 10 minutes.
[AppHash: FA+9qCX9VSu]
```

The hash is computed from the app's signing certificate + package name. ObeGee must request this hash from the MyndLens build team once the production APK signing certificate is finalised.

**Note:** Without the hash, `autoComplete="sms-otp"` still works — Android shows the code as a keyboard suggestion. The hash only upgrades this to silent auto-injection.

---

## 3. API Contract

### 3.1 Trigger Endpoint (ObeGee → SMS Gateway)

When the MyndLens app calls the pairing endpoint, ObeGee must send the SMS as part of code generation:

**Internal ObeGee flow:**
```
POST /myndlens/generate-code
  → generate 6-digit code
  → store { code, device_id, expires_at } 
  → send SMS to user's registered phone
  → return { code } to caller (shown in Dashboard as fallback)
```

### 3.2 SMS Delivery Requirements

| Parameter | Value |
|---|---|
| **Sender ID** | `MyndLens` (alphanumeric) or a dedicated short code |
| **Delivery window** | Within 30 seconds of code generation |
| **Retry policy** | 1 retry after 30s if delivery receipt not received |
| **Carrier support** | Must support delivery to UK, US, UAE, AU at minimum |

### 3.3 Code Properties

| Parameter | Value |
|---|---|
| **Length** | 6 digits |
| **Charset** | `[0-9]` only — no letters, no ambiguous chars (0/O, 1/l) |
| **Expiry** | 10 minutes from generation |
| **Single-use** | Code invalidated immediately on first successful use |
| **Rate limit** | Max 3 codes per device per 15 minutes |
| **Max attempts** | 5 incorrect attempts → code invalidated |

---

## 4. User Registration Prerequisite

ObeGee must collect and verify the user's mobile number during workspace creation **before** the pairing flow. MyndLens assumes ObeGee holds a verified phone number for every user who generates a pairing code.

**Recommended:** Phone number verified via its own SMS OTP during ObeGee account sign-up.

---

## 5. Dashboard Fallback

Even with SMS delivery, the pairing code must remain visible in the ObeGee Dashboard (Settings → Pairing Code) for:
- Users without cellular reception at pairing time
- Users who prefer manual entry
- Debugging / enterprise IT provisioning scenarios

The Dashboard display is already implemented on both sides — this is a safety net, not the primary path.

---

## 6. Security Considerations

| Concern | Mitigation |
|---|---|
| **SMS interception** | Code is single-use and 10-minute expiry limits exposure window |
| **Brute force** | 5-attempt lockout + rate limit makes `10^6` space infeasible |
| **SIM swap** | ObeGee should flag pairing from a new device_id on an existing account for review |
| **Phishing SMS** | Domain association (`@myndlens.app #code`) prevents spoofed SMS from triggering autofill |
| **Shared devices** | MyndLens app binds the token to `device_id` at pairing — token is non-transferable |

---

## 7. Suggested SMS Provider

| Provider | Notes |
|---|---|
| **Twilio Verify** | Purpose-built OTP API — handles delivery, retry, expiry, rate limiting automatically |
| **AWS SNS** | Lower cost, requires manual code management |
| **Vonage (Nexmo)** | Strong UK/EU coverage |

Twilio Verify is recommended because it manages the entire lifecycle (generate → deliver → verify) and produces GSMA-compliant OTP messages automatically.

---

## 8. MyndLens Integration Points Already Done

For ObeGee's awareness — no changes needed on the MyndLens side for the basic SMS autofill path:

- `login.tsx`: `TextInput` has `textContentType="oneTimeCode"` (iOS) and `autoComplete="sms-otp"` (Android)
- `login.tsx`: 6-digit numeric-only validation, strips whitespace
- Pairing endpoint: already calls `POST /api/myndlens/pair` with `{ code, device_id, device_name }`
- Success path: stores token + routes to loading screen

The only thing MyndLens needs from ObeGee for the Android SMS Retriever silent auto-injection upgrade is the 11-character app hash (see §2.4). This can be computed with the tool below once the signing cert is ready:

```bash
# Run after APK is signed
keytool -exportcert -alias <key-alias> -keystore <keystore.jks> | xxd | python3 -c "
import sys, hashlib, base64
cert = bytes.fromhex(''.join(sys.stdin.read().split()[1::2]))
hash = base64.b64encode(hashlib.sha256(cert).digest())[:11].decode()
print('App Hash:', hash)
"
```
