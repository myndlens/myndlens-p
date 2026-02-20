"""E2E Test — Full Mandate Pipeline with ObeGee Dispatch.

Tests all 8 steps per the review request:
  STEP 1: Health — GET /api/health
  STEP 2: Pair — verify tenant_id=dev_myndlens_test, runtime_endpoint=https://app.myndlens.com
  STEP 3: WS Auth — send AUTH with token, expect auth_ok
  STEP 4: Heartbeat — verify heartbeat_ack
  STEP 5: Text input 'Create Hello World code in Python' — collect messages
  STEP 6: Execute request — CRITICAL step, report ObeGee response
  STEP 7: Monitor for pipeline_stage events (stages 8-9)
  STEP 8: Backend logs analysis

EXPECTED: With OBEGEE_DEV_TENANT_ID=dev_myndlens_test and valid OBEGEE_API_TOKEN,
ObeGee should return HTTP 200 with execution_id.
"""
import json
import time
import pytest
import requests
from websocket import create_connection

BASE_URL = "http://localhost:8001"
WS_URL = "ws://localhost:8001/api/ws"


class TestMyndLensObeGeeDispatch:
    """Full E2E workflow testing ObeGee dispatch integration."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Store state across tests."""
        self.pair_data = None
        self.device_id = None
        self.ws = None
        self.session_id = None
        self.draft_id = None

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 1: Health Check
    # ══════════════════════════════════════════════════════════════════════════
    def test_step1_health_check(self):
        """STEP 1: Health check — GET /api/health."""
        print("\n" + "=" * 70)
        print("STEP 1: HEALTH CHECK")
        print("=" * 70)

        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        print(f"Status code: {response.status_code}")

        assert response.status_code == 200, f"Health check failed: {response.text}"

        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")

        assert data.get("status") == "healthy"
        assert data.get("stt_healthy") is True
        assert data.get("tts_healthy") is True

        print("\n✓ STEP 1 PASSED: Health check succeeded")
        print(f"  - status: {data.get('status')}")
        print(f"  - stt_provider: {data.get('stt_provider')}")
        print(f"  - tts_provider: {data.get('tts_provider')}")

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 2: Pairing — verify fixed tenant_id
    # ══════════════════════════════════════════════════════════════════════════
    def test_step2_pairing(self):
        """STEP 2: Pairing — POST /api/sso/myndlens/pair with code=123456.

        EXPECTED: tenant_id=dev_myndlens_test (NOT a random UUID),
        runtime_endpoint=https://app.myndlens.com
        """
        print("\n" + "=" * 70)
        print("STEP 2: PAIRING")
        print("=" * 70)

        import uuid
        self.device_id = f"test_e2e_{uuid.uuid4().hex[:8]}"
        payload = {
            "code": "123456",
            "device_id": self.device_id,
            "device_name": "E2E ObeGee Test"
        }

        print(f"Request payload: {json.dumps(payload, indent=2)}")

        response = requests.post(
            f"{BASE_URL}/api/sso/myndlens/pair",
            json=payload,
            timeout=10
        )
        print(f"Status code: {response.status_code}")

        assert response.status_code == 200, f"Pairing failed: {response.text}"

        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")

        # Verify expected fields
        assert "access_token" in data
        assert "runtime_endpoint" in data
        assert "tenant_id" in data

        # CRITICAL: Verify tenant_id is the fixed dev tenant
        tenant_id = data.get("tenant_id", "")
        assert tenant_id == "dev_myndlens_test", \
            f"STEP 2 FAILED: Expected tenant_id='dev_myndlens_test', got '{tenant_id}'"

        # Verify runtime_endpoint
        runtime_endpoint = data.get("runtime_endpoint", "")
        assert runtime_endpoint == "https://app.myndlens.com", \
            f"STEP 2 FAILED: Expected runtime_endpoint='https://app.myndlens.com', got '{runtime_endpoint}'"

        print("\n✓ STEP 2 PASSED: Pairing successful")
        print(f"  - tenant_id: {tenant_id} (CORRECT - not random UUID)")
        print(f"  - runtime_endpoint: {runtime_endpoint}")
        print(f"  - access_token: {data.get('access_token', '')[:50]}...")

        self.pair_data = data
        TestMyndLensObeGeeDispatch._pair_data = data
        TestMyndLensObeGeeDispatch._device_id = self.device_id

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 3: WebSocket Auth — expect auth_ok
    # ══════════════════════════════════════════════════════════════════════════
    def test_step3_websocket_auth(self):
        """STEP 3: WebSocket auth — connect and send AUTH message.

        EXPECTED: auth_ok (HS256 mode validates mock IDP token correctly).
        """
        print("\n" + "=" * 70)
        print("STEP 3: WEBSOCKET AUTH")
        print("=" * 70)

        pair_data = getattr(TestMyndLensObeGeeDispatch, '_pair_data', None)
        device_id = getattr(TestMyndLensObeGeeDispatch, '_device_id', None)

        if not pair_data:
            pytest.skip("No pair data from STEP 2")

        print(f"Using access_token: {pair_data['access_token'][:50]}...")
        print(f"Using device_id: {device_id}")
        print(f"Connecting to WS: {WS_URL}")

        ws = create_connection(WS_URL, timeout=15)
        print("✓ WebSocket connected")

        # Send AUTH message
        auth_msg = {
            "type": "auth",
            "payload": {
                "token": pair_data["access_token"],
                "device_id": device_id,
                "client_version": "1.0.0-e2e-obegee"
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

        assert msg_type == "auth_ok", \
            f"STEP 3 FAILED: Expected auth_ok, got {msg_type}: {payload}"

        print("\n✓ STEP 3 PASSED: auth_ok received")
        print(f"  - session_id: {payload.get('session_id')}")
        print(f"  - user_id: {payload.get('user_id')}")
        print(f"  - heartbeat_interval_ms: {payload.get('heartbeat_interval_ms')}")

        TestMyndLensObeGeeDispatch._ws = ws
        TestMyndLensObeGeeDispatch._session_id = payload.get('session_id')

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 4: Heartbeat — verify heartbeat_ack
    # ══════════════════════════════════════════════════════════════════════════
    def test_step4_heartbeat(self):
        """STEP 4: Heartbeat — send heartbeat and verify heartbeat_ack."""
        print("\n" + "=" * 70)
        print("STEP 4: HEARTBEAT")
        print("=" * 70)

        ws = getattr(TestMyndLensObeGeeDispatch, '_ws', None)
        session_id = getattr(TestMyndLensObeGeeDispatch, '_session_id', None)

        if not ws:
            pytest.skip("No WebSocket connection from STEP 3")

        heartbeat_msg = {
            "type": "heartbeat",
            "payload": {
                "session_id": session_id,
                "seq": 1,
                "client_ts": int(time.time() * 1000)
            }
        }
        print(f"Sending heartbeat: {json.dumps(heartbeat_msg, indent=2)}")
        ws.send(json.dumps(heartbeat_msg))

        response_raw = ws.recv()
        response = json.loads(response_raw)
        print(f"Received response: {json.dumps(response, indent=2)}")

        msg_type = response.get("type", "")
        payload = response.get("payload", {})

        assert msg_type == "heartbeat_ack", \
            f"STEP 4 FAILED: Expected heartbeat_ack, got {msg_type}"

        print("\n✓ STEP 4 PASSED: heartbeat_ack received")
        print(f"  - seq: {payload.get('seq')}")
        print(f"  - server_ts: {payload.get('server_ts')}")

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 5: Text Input Mandate
    # ══════════════════════════════════════════════════════════════════════════
    def test_step5_text_input_mandate(self):
        """STEP 5: Text input — send 'Create Hello World code in Python'.

        Collect and report:
          - transcript_final (yes/no)
          - pipeline_stage count
          - draft_update action_class and draft_id
          - tts_audio is_mock and byte_count
        """
        print("\n" + "=" * 70)
        print("STEP 5: TEXT INPUT MANDATE")
        print("=" * 70)

        ws = getattr(TestMyndLensObeGeeDispatch, '_ws', None)

        if not ws:
            pytest.skip("No WebSocket connection")

        text_input_msg = {
            "type": "text_input",
            "payload": {
                "text": "Create Hello World code in Python"
            }
        }
        print(f"Sending text_input: {json.dumps(text_input_msg, indent=2)}")
        ws.send(json.dumps(text_input_msg))

        # Collect all messages
        messages = []
        ws.settimeout(45)

        print("\nCollecting messages...")
        while True:
            try:
                response_raw = ws.recv()
                response = json.loads(response_raw)
                messages.append(response)
                msg_type = response.get("type", "")
                payload_preview = str(response.get("payload", {}))[:150]
                print(f"  [{len(messages)}] {msg_type}: {payload_preview}...")

                if msg_type == "tts_audio":
                    break
            except Exception as e:
                print(f"  Timeout/error: {e}")
                break

        print(f"\n--- STEP 5 ANALYSIS ---")
        print(f"Total messages received: {len(messages)}")

        # Analyze messages
        transcript_finals = [m for m in messages if m.get("type") == "transcript_final"]
        pipeline_stages = [m for m in messages if m.get("type") == "pipeline_stage"]
        draft_updates = [m for m in messages if m.get("type") == "draft_update"]
        tts_audios = [m for m in messages if m.get("type") == "tts_audio"]

        # Report
        print(f"\n  transcript_final: {'YES' if transcript_finals else 'NO'} (count={len(transcript_finals)})")
        print(f"  pipeline_stage count: {len(pipeline_stages)}")

        if draft_updates:
            draft = draft_updates[0].get("payload", {})
            action_class = draft.get("intent", "")
            draft_id = draft.get("draft_id", "")
            print(f"  draft_update: action_class={action_class}, draft_id={draft_id}")
            TestMyndLensObeGeeDispatch._draft_id = draft_id
        else:
            print(f"  draft_update: NOT RECEIVED")

        if tts_audios:
            tts = tts_audios[0].get("payload", {})
            is_mock = tts.get("is_mock", True)
            audio_b64 = tts.get("audio", "")
            byte_count = len(audio_b64) * 3 // 4 if audio_b64 else 0  # Approximate
            print(f"  tts_audio: is_mock={is_mock}, byte_count~={byte_count}")
        else:
            print(f"  tts_audio: NOT RECEIVED")

        print("\n✓ STEP 5 COMPLETED")
        assert draft_updates, "STEP 5 FAILED: No draft_update received"

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 6: Execute Request — CRITICAL STEP
    # ══════════════════════════════════════════════════════════════════════════
    def test_step6_execute_request(self):
        """STEP 6: Execute request — send execute_request with draft_id.

        This is the CRITICAL step. Report:
          a) What HTTP status did ObeGee return?
          b) What was the response body from ObeGee?
          c) Was execute_ok or execute_blocked received?
          d) If execute_ok: execution_id and dispatch_status
          e) If execute_blocked: code and reason
        """
        print("\n" + "=" * 70)
        print("STEP 6: EXECUTE REQUEST (CRITICAL)")
        print("=" * 70)

        ws = getattr(TestMyndLensObeGeeDispatch, '_ws', None)
        draft_id = getattr(TestMyndLensObeGeeDispatch, '_draft_id', None)
        session_id = getattr(TestMyndLensObeGeeDispatch, '_session_id', None)

        if not ws:
            pytest.skip("No WebSocket connection")

        if not draft_id:
            pytest.skip("No draft_id from STEP 5")

        # Send heartbeat first to ensure presence is fresh
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
        print(f"Sending execute_request: {json.dumps(execute_msg, indent=2)}")
        ws.send(json.dumps(execute_msg))

        # Collect responses
        messages = []
        ws.settimeout(90)  # Long timeout for LLM + dispatch

        print("\nCollecting messages...")
        while True:
            try:
                response_raw = ws.recv()
                response = json.loads(response_raw)
                messages.append(response)
                msg_type = response.get("type", "")
                payload_str = json.dumps(response.get("payload", {}))[:300]
                print(f"  [{len(messages)}] {msg_type}: {payload_str}")

                if msg_type in ["execute_ok", "execute_blocked", "error"]:
                    break
            except Exception as e:
                print(f"  Timeout/error: {e}")
                break

        print(f"\n--- STEP 6 CRITICAL REPORT ---")
        print(f"Total messages: {len(messages)}")

        # Find final result
        final_msg = None
        for msg in messages:
            if msg.get("type") in ["execute_ok", "execute_blocked", "error"]:
                final_msg = msg
                break

        if not final_msg:
            print("\n✗ STEP 6 FAILED: No execute_ok or execute_blocked received")
            print("  Last messages:")
            for m in messages[-5:]:
                print(f"    {m.get('type')}: {json.dumps(m.get('payload', {}))[:200]}")
            pytest.fail("No final execution message received")

        msg_type = final_msg.get("type", "")
        payload = final_msg.get("payload", {})

        if msg_type == "execute_ok":
            print("\n✓ STEP 6 RESULT: execute_ok")
            print(f"  a) ObeGee HTTP status: 200 (implied by execute_ok)")
            print(f"  b) ObeGee response: SUCCESS (mandate dispatched)")
            print(f"  c) Message type: execute_ok")
            print(f"  d) execution_id: {payload.get('execution_id', 'NOT_IN_PAYLOAD')}")
            print(f"     dispatch_status: {payload.get('dispatch_status')}")
            TestMyndLensObeGeeDispatch._execute_ok = True
            TestMyndLensObeGeeDispatch._execution_id = payload.get('execution_id')
        elif msg_type == "execute_blocked":
            print("\n✗ STEP 6 RESULT: execute_blocked")
            reason = payload.get("reason", "")
            code = payload.get("code", "")
            print(f"  a) ObeGee HTTP status: (in reason) {reason}")
            print(f"  b) ObeGee response body: {reason}")
            print(f"  c) Message type: execute_blocked")
            print(f"  e) code: {code}")
            print(f"     reason: {reason}")
            TestMyndLensObeGeeDispatch._execute_ok = False

            # Extract HTTP status from reason if present
            if "HTTP" in reason:
                import re
                match = re.search(r'HTTP (\d+)', reason)
                if match:
                    http_status = match.group(1)
                    print(f"\n  Extracted HTTP status: {http_status}")
        else:
            print(f"\n? STEP 6 RESULT: Unexpected message type: {msg_type}")
            print(f"  payload: {json.dumps(payload)}")
            TestMyndLensObeGeeDispatch._execute_ok = False

        print("\n--- STEP 6 COMPLETE ---")

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 7: Monitor for pipeline_stage events (stages 8-9)
    # ══════════════════════════════════════════════════════════════════════════
    def test_step7_wait_for_execution_progress(self):
        """STEP 7: If execute_ok, wait 10 seconds for pipeline_stage events."""
        print("\n" + "=" * 70)
        print("STEP 7: WAIT FOR EXECUTION PROGRESS")
        print("=" * 70)

        ws = getattr(TestMyndLensObeGeeDispatch, '_ws', None)
        execute_ok = getattr(TestMyndLensObeGeeDispatch, '_execute_ok', False)

        if not execute_ok:
            print("SKIPPED: execute_blocked received, no execution progress expected")
            pytest.skip("Execute was blocked")

        if not ws:
            pytest.skip("No WebSocket connection")

        print("Waiting 10 seconds for pipeline_stage events (stages 8-9)...")
        ws.settimeout(10)

        stage_events = []
        start = time.time()
        while time.time() - start < 10:
            try:
                response_raw = ws.recv()
                response = json.loads(response_raw)
                msg_type = response.get("type", "")
                if msg_type == "pipeline_stage":
                    stage_events.append(response)
                    payload = response.get("payload", {})
                    print(f"  stage_index={payload.get('stage_index')}, status={payload.get('status')}, sub_status={payload.get('sub_status', '')}")
            except Exception:
                break

        print(f"\nReceived {len(stage_events)} pipeline_stage events")

        if stage_events:
            print("\n✓ STEP 7 PASSED: Execution progress events received")
        else:
            print("\n? STEP 7: No additional pipeline_stage events (execution may be async)")

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 8: Backend logs analysis
    # ══════════════════════════════════════════════════════════════════════════
    def test_step8_backend_logs(self):
        """STEP 8: Check backend logs for ObeGee dispatch result."""
        print("\n" + "=" * 70)
        print("STEP 8: BACKEND LOGS ANALYSIS")
        print("=" * 70)

        import subprocess
        result = subprocess.run(
            ["tail", "-50", "/var/log/supervisor/backend.out.log"],
            capture_output=True, text=True
        )
        logs = result.stdout

        # Look for dispatch-related logs
        dispatch_lines = [
            line for line in logs.split("\n")
            if any(kw in line for kw in ["dispatch", "ObeGee", "execution", "MANDATE", "rejected", "HTTP", "execute_blocked"])
        ]

        print("Dispatch-related log lines:")
        for line in dispatch_lines[-10:]:
            print(f"  {line}")

        print("\n✓ STEP 8 COMPLETED: Backend logs captured")

    # ══════════════════════════════════════════════════════════════════════════
    #  Cleanup
    # ══════════════════════════════════════════════════════════════════════════
    def test_step9_cleanup(self):
        """Cleanup: close WebSocket connection."""
        print("\n" + "=" * 70)
        print("STEP 9: CLEANUP")
        print("=" * 70)

        ws = getattr(TestMyndLensObeGeeDispatch, '_ws', None)
        if ws:
            try:
                ws.close()
                print("✓ WebSocket closed")
            except Exception as e:
                print(f"Error closing WS: {e}")

        print("\n✓ TEST COMPLETE")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
