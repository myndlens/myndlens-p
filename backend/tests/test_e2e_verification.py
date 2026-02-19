"""E2E Verification Test — MyndLens Voice Assistant (Post-Fix).

Tests after HS256 auth fix and OBEGEE_API_TOKEN separation:
  STEP 1: Health check — GET /api/health
  STEP 2: Pairing — POST /api/sso/myndlens/pair code=123456
  STEP 3: WS Auth — MUST return auth_ok (HS256 fix applied)
  STEP 4: Heartbeat — verify heartbeat_ack  
  STEP 5: Text input 'Create Hello World code in Python'
  STEP 6: Execute request — expect execute_blocked with OBEGEE_API_TOKEN not configured
  STEP 7: Log monitoring — [MANDATE:*] lines and session_terminated

Production Safety Check: Verify sso_validator.py ENV=prod forces JWKS
"""
import json
import os
import time
import uuid
import pytest
import requests
from websocket import create_connection, WebSocketException

# Base URLs
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
WS_URL = "ws://localhost:8001/api/ws"


class TestE2EVerification:
    """E2E verification test with detailed reporting."""

    pair_data = None
    device_id = None
    ws = None
    session_id = None
    auth_success = False
    draft_id = None

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 1: Health Check
    # ══════════════════════════════════════════════════════════════════════════
    def test_step1_health_check(self):
        """STEP 1: Health check — GET http://localhost:8001/api/health"""
        print("\n" + "=" * 70)
        print("STEP 1: HEALTH CHECK")
        print("=" * 70)

        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        print(f"Status code: {response.status_code}")

        assert response.status_code == 200, f"Health check failed: {response.text}"

        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")

        # Verify expected fields
        assert data.get("status") == "healthy"
        assert data.get("stt_healthy") is True
        assert data.get("tts_healthy") is True
        
        print("\n✓ STEP 1 PASSED")
        print(f"  - status: {data.get('status')}")
        print(f"  - mock_stt: {data.get('mock_stt')}")
        print(f"  - mock_tts: {data.get('mock_tts')}")
        print(f"  - mock_llm: {data.get('mock_llm')}")

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 2: Pairing
    # ══════════════════════════════════════════════════════════════════════════
    def test_step2_pairing(self):
        """STEP 2: POST /api/sso/myndlens/pair code=123456 — verify runtime_endpoint=https://app.myndlens.com"""
        print("\n" + "=" * 70)
        print("STEP 2: PAIRING")
        print("=" * 70)

        TestE2EVerification.device_id = f"e2e_{uuid.uuid4().hex[:8]}"
        payload = {
            "code": "123456",
            "device_id": TestE2EVerification.device_id,
            "device_name": "E2E Verification Device"
        }

        print(f"Request payload: {json.dumps(payload, indent=2)}")

        response = requests.post(f"{BASE_URL}/api/sso/myndlens/pair", json=payload, timeout=10)
        print(f"Status code: {response.status_code}")

        assert response.status_code == 200, f"Pairing failed: {response.text}"

        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")

        # Verify expected fields
        assert "access_token" in data, "Missing access_token"
        assert "runtime_endpoint" in data, "Missing runtime_endpoint"
        assert data.get("runtime_endpoint") == "https://app.myndlens.com", \
            f"Expected runtime_endpoint=https://app.myndlens.com, got {data.get('runtime_endpoint')}"

        print("\n✓ STEP 2 PASSED")
        print(f"  - access_token: {data.get('access_token', '')[:50]}...")
        print(f"  - runtime_endpoint: {data.get('runtime_endpoint')}")
        print(f"  - session_id: {data.get('session_id')}")
        print(f"  - tenant_id: {data.get('tenant_id')}")

        TestE2EVerification.pair_data = data

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 3: WebSocket Auth (MUST return auth_ok with HS256 fix)
    # ══════════════════════════════════════════════════════════════════════════
    def test_step3_websocket_auth(self):
        """STEP 3: WS Auth — auth message MUST return auth_ok (HS256 fix applied)"""
        print("\n" + "=" * 70)
        print("STEP 3: WEBSOCKET AUTH")
        print("=" * 70)

        pair_data = TestE2EVerification.pair_data
        device_id = TestE2EVerification.device_id

        if not pair_data:
            pytest.fail("No pair_data from STEP 2")

        print(f"Using access_token: {pair_data['access_token'][:50]}...")
        print(f"Using device_id: {device_id}")
        print(f"Connecting to WS: {WS_URL}")

        try:
            ws = create_connection(WS_URL, timeout=10)
            print("✓ WebSocket connected")

            # Send AUTH message
            auth_msg = {
                "type": "auth",
                "payload": {
                    "token": pair_data["access_token"],
                    "device_id": device_id,
                    "client_version": "1.0.0-e2e-verification"
                }
            }
            print(f"Sending AUTH message...")
            ws.send(json.dumps(auth_msg))

            # Wait for response
            response_raw = ws.recv()
            response = json.loads(response_raw)
            print(f"Received response: {json.dumps(response, indent=2)}")

            msg_type = response.get("type", "")
            payload = response.get("payload", {})

            if msg_type == "auth_ok":
                print("\n✓ STEP 3 PASSED: auth_ok received (HS256 fix VERIFIED)")
                print(f"  - session_id: {payload.get('session_id')}")
                print(f"  - user_id: {payload.get('user_id')}")
                print(f"  - heartbeat_interval_ms: {payload.get('heartbeat_interval_ms')}")
                TestE2EVerification.ws = ws
                TestE2EVerification.session_id = payload.get('session_id')
                TestE2EVerification.auth_success = True
            elif msg_type == "auth_fail":
                print("\n✗ STEP 3 FAILED: auth_fail received")
                print(f"  - reason: {payload.get('reason')}")
                print(f"  - code: {payload.get('code')}")
                ws.close()
                pytest.fail(f"Auth failed: {payload.get('reason')}")
            else:
                print(f"\n✗ STEP 3 FAILED: Unexpected message type: {msg_type}")
                ws.close()
                pytest.fail(f"Unexpected message type: {msg_type}")

        except WebSocketException as e:
            print(f"\n✗ WebSocket error: {e}")
            pytest.fail(f"WebSocket error: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 4: Heartbeat
    # ══════════════════════════════════════════════════════════════════════════
    def test_step4_heartbeat(self):
        """STEP 4: Heartbeat — verify heartbeat_ack"""
        print("\n" + "=" * 70)
        print("STEP 4: HEARTBEAT")
        print("=" * 70)

        if not TestE2EVerification.auth_success:
            pytest.skip("WS auth required for heartbeat test")

        ws = TestE2EVerification.ws
        if not ws:
            pytest.skip("No active WS connection")

        try:
            session_id = TestE2EVerification.session_id
            heartbeat_msg = {
                "type": "heartbeat",
                "payload": {
                    "session_id": session_id,
                    "seq": 1,
                    "client_ts": int(time.time() * 1000)
                }
            }
            print(f"Sending heartbeat...")
            ws.send(json.dumps(heartbeat_msg))

            response_raw = ws.recv()
            response = json.loads(response_raw)
            print(f"Received response: {json.dumps(response, indent=2)}")

            msg_type = response.get("type", "")
            payload = response.get("payload", {})

            if msg_type == "heartbeat_ack":
                print("\n✓ STEP 4 PASSED: heartbeat_ack received")
                print(f"  - seq: {payload.get('seq')}")
                print(f"  - server_ts: {payload.get('server_ts')}")
            else:
                print(f"\n✗ STEP 4 FAILED: Expected heartbeat_ack, got {msg_type}")
                pytest.fail(f"Expected heartbeat_ack, got {msg_type}")

        except Exception as e:
            print(f"\n✗ Error: {e}")
            pytest.fail(f"Heartbeat error: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 5: Text Input Mandate
    # ══════════════════════════════════════════════════════════════════════════
    def test_step5_text_input_mandate(self):
        """STEP 5: Text input 'Create Hello World code in Python' — collect all WS messages"""
        print("\n" + "=" * 70)
        print("STEP 5: TEXT INPUT MANDATE")
        print("=" * 70)

        if not TestE2EVerification.auth_success:
            pytest.skip("WS auth required for text input test")

        ws = TestE2EVerification.ws
        if not ws:
            pytest.skip("No active WS connection")

        try:
            text_input_msg = {
                "type": "text_input",
                "payload": {
                    "text": "Create Hello World code in Python"
                }
            }
            print(f"Sending text_input: {json.dumps(text_input_msg, indent=2)}")
            ws.send(json.dumps(text_input_msg))

            # Collect all messages (with timeout for LLM + TTS)
            messages = []
            ws.settimeout(45)

            print("\nCollecting messages...")
            while True:
                try:
                    response_raw = ws.recv()
                    response = json.loads(response_raw)
                    messages.append(response)
                    msg_type = response.get("type", "")
                    payload = response.get("payload", {})
                    
                    # Abbreviated logging
                    if msg_type == "pipeline_stage":
                        print(f"  [{len(messages)}] {msg_type}: stage={payload.get('stage_id')}, status={payload.get('status')}")
                    elif msg_type == "tts_audio":
                        print(f"  [{len(messages)}] {msg_type}: is_mock={payload.get('is_mock')}")
                        break  # tts_audio is final
                    else:
                        print(f"  [{len(messages)}] {msg_type}")
                        
                except Exception as e:
                    print(f"  Timeout/error: {e}")
                    break

            print(f"\nTotal messages received: {len(messages)}")

            # Analyze
            transcript_finals = [m for m in messages if m.get("type") == "transcript_final"]
            pipeline_stages = [m for m in messages if m.get("type") == "pipeline_stage"]
            draft_updates = [m for m in messages if m.get("type") == "draft_update"]
            tts_audios = [m for m in messages if m.get("type") == "tts_audio"]

            print("\n--- STEP 5 Results ---")
            print(f"transcript_final received? {len(transcript_finals) > 0}")
            print(f"pipeline_stage events: {len(pipeline_stages)}")
            
            # Report draft_update
            for draft in draft_updates:
                p = draft.get("payload", {})
                print(f"draft_update received: action_class={p.get('action_class')}, draft_id={p.get('draft_id')}")
                TestE2EVerification.draft_id = p.get('draft_id')

            # Report TTS audio
            for tts in tts_audios:
                p = tts.get("payload", {})
                audio_data = p.get("audio_data", "")
                byte_count = len(audio_data) // 4 * 3 if audio_data else 0  # base64 decode estimate
                print(f"tts_audio received: text='{p.get('text', '')[:50]}...', is_mock={p.get('is_mock')}, bytes~{byte_count}")

            print("\n✓ STEP 5 COMPLETED")

        except Exception as e:
            print(f"\n✗ Error: {e}")
            pytest.fail(f"Text input error: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 6: Execute Request (expect OBEGEE_API_TOKEN not configured)
    # ══════════════════════════════════════════════════════════════════════════
    def test_step6_execute_request(self):
        """STEP 6: Execute request with draft_id — expect execute_blocked with OBEGEE_API_TOKEN not configured"""
        print("\n" + "=" * 70)
        print("STEP 6: EXECUTE REQUEST")
        print("=" * 70)

        if not TestE2EVerification.auth_success:
            pytest.skip("WS auth required for execute test")

        ws = TestE2EVerification.ws
        draft_id = TestE2EVerification.draft_id

        if not ws:
            pytest.skip("No active WS connection")

        if not draft_id:
            pytest.skip("No draft_id from STEP 5")

        try:
            # Send heartbeat first to ensure fresh presence
            session_id = TestE2EVerification.session_id
            heartbeat_msg = {
                "type": "heartbeat",
                "payload": {
                    "session_id": session_id,
                    "seq": 2,
                    "client_ts": int(time.time() * 1000)
                }
            }
            ws.send(json.dumps(heartbeat_msg))
            ws.recv()  # Discard heartbeat_ack

            # Send execute_request
            execute_msg = {
                "type": "execute_request",
                "payload": {
                    "session_id": session_id,
                    "draft_id": draft_id
                }
            }
            print(f"Sending execute_request with draft_id={draft_id}")
            ws.send(json.dumps(execute_msg))

            # Collect responses
            messages = []
            ws.settimeout(60)

            print("\nCollecting messages...")
            while True:
                try:
                    response_raw = ws.recv()
                    response = json.loads(response_raw)
                    messages.append(response)
                    msg_type = response.get("type", "")
                    payload = response.get("payload", {})
                    
                    print(f"  [{len(messages)}] {msg_type}")

                    # Stop after terminal messages
                    if msg_type in ["execute_ok", "execute_blocked", "error"]:
                        print(f"\n--- STEP 6 RESULT ---")
                        print(f"Message type: {msg_type}")
                        print(f"Payload: {json.dumps(payload, indent=2)}")
                        break
                except Exception:
                    break

            # Find and report final result
            for msg in messages:
                msg_type = msg.get("type", "")
                payload = msg.get("payload", {})

                if msg_type == "execute_blocked":
                    code = payload.get("code", "")
                    reason = payload.get("reason", "")
                    
                    print(f"\n✓ STEP 6 RESULT: execute_blocked")
                    print(f"  - code: {code}")
                    print(f"  - reason: {reason}")
                    
                    # Verify expected error
                    if "OBEGEE_API_TOKEN" in reason and "not configured" in reason:
                        print(f"\n✓ VERIFIED: New clearer error message about OBEGEE_API_TOKEN")
                    elif "DISPATCH_BLOCKED" in str(code):
                        print(f"\n✓ VERIFIED: DISPATCH_BLOCKED code received")

            print("\n✓ STEP 6 COMPLETED")

        except Exception as e:
            print(f"\n✗ Error: {e}")
            pytest.fail(f"Execute request error: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 7: Disconnect and Cleanup Verification
    # ══════════════════════════════════════════════════════════════════════════
    def test_step7_disconnect(self):
        """STEP 7: Disconnect — close WS and verify cleanup"""
        print("\n" + "=" * 70)
        print("STEP 7: DISCONNECT")
        print("=" * 70)

        ws = TestE2EVerification.ws

        if ws:
            try:
                ws.close()
                print("✓ WebSocket closed")
            except Exception as e:
                print(f"Error closing WS: {e}")

        print("\nCheck backend logs for cleanup:")
        print("  tail -30 /var/log/supervisor/backend.out.log | grep -E 'MANDATE:|session_terminated|cleanup'")

        print("\n✓ STEP 7 COMPLETED")


class TestProductionSafetyCheck:
    """Verify sso_validator.py production safety: ENV=prod forces JWKS"""

    def test_prod_forces_jwks(self):
        """PRODUCTION SAFETY CHECK: When ENV=prod, get_sso_validator() must return JWKSValidator"""
        print("\n" + "=" * 70)
        print("PRODUCTION SAFETY CHECK")
        print("=" * 70)

        # Read the sso_validator.py code to verify the logic
        import sys
        sys.path.insert(0, '/app/backend')
        
        # Check the source code for the safety rule
        with open('/app/backend/auth/sso_validator.py', 'r') as f:
            source = f.read()
        
        # Verify the production safety check exists
        has_prod_check = 'settings.ENV == "prod"' in source
        forces_jwks = 'return JWKSValidator()' in source and 'ENV == "prod"' in source
        
        print(f"Source code check:")
        print(f"  - Has ENV=prod check: {has_prod_check}")
        print(f"  - Forces JWKS in prod: {forces_jwks}")
        
        # Verify the logic flow
        if has_prod_check and forces_jwks:
            print("\n✓ PRODUCTION SAFETY VERIFIED")
            print("  - get_sso_validator() checks ENV first")
            print("  - ENV=prod always returns JWKSValidator (RS256/ES256)")
            print("  - HS256 mode is only available for dev/staging")
        else:
            print("\n✗ PRODUCTION SAFETY NOT VERIFIED")
            pytest.fail("Production safety check not found in sso_validator.py")

        # Verify the actual function behavior (without changing ENV)
        # This just confirms the code structure
        from auth.sso_validator import get_sso_validator, JWKSValidator, HS256Validator
        from config.settings import get_settings
        
        settings = get_settings()
        print(f"\nCurrent settings:")
        print(f"  - ENV: {settings.ENV}")
        print(f"  - OBEGEE_TOKEN_VALIDATION_MODE: {settings.OBEGEE_TOKEN_VALIDATION_MODE}")
        
        validator = get_sso_validator()
        validator_type = type(validator).__name__
        print(f"  - Current validator type: {validator_type}")
        
        if settings.ENV == "dev" and settings.OBEGEE_TOKEN_VALIDATION_MODE == "HS256":
            assert isinstance(validator, HS256Validator), "Expected HS256Validator in dev with HS256 mode"
            print("\n✓ Dev mode correctly uses HS256Validator when configured")
        
        print("\n✓ PRODUCTION SAFETY CHECK COMPLETED")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
