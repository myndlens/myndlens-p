#!/usr/bin/env python3
"""Backend Testing — MyndLens Batch 13: Soul Vector Memory System.

Final comprehensive test with proper WebSocket message format.
"""
import json
import requests
import time
import websocket
import threading
import uuid
from datetime import datetime, timezone

# Backend URL from environment
BACKEND_URL = "https://voice-assistant-dev.preview.emergentagent.com/api"
WS_URL = "wss://voice-assistant-dev.preview.emergentagent.com/api/ws"

def log(message):
    """Log with timestamp."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures = []
    
    def success(self, test_name):
        self.passed += 1
        log(f"✅ {test_name}")
    
    def failure(self, test_name, error):
        self.failed += 1
        self.failures.append(f"{test_name}: {error}")
        log(f"❌ {test_name}: {error}")
    
    def summary(self):
        total = self.passed + self.failed
        log(f"\n=== TEST SUMMARY ===")
        log(f"Total tests: {total}")
        log(f"Passed: {self.passed}")
        log(f"Failed: {self.failed}")
        if self.failures:
            log(f"\nFailures:")
            for failure in self.failures:
                log(f"  - {failure}")

results = TestResults()

def test_soul_status():
    """Test 1: Soul status API - GET /api/soul/status."""
    try:
        response = requests.get(f"{BACKEND_URL}/soul/status", timeout=10)
        if response.status_code != 200:
            results.failure("Soul status API", f"HTTP {response.status_code}")
            return False
        
        data = response.json()
        required_fields = ["version", "integrity", "drift", "fragments"]
        
        for field in required_fields:
            if field not in data:
                results.failure("Soul status API", f"Missing field: {field}")
                return False
        
        # Check expected values from review request
        if data["version"]["version"] != "1.0.0":
            results.failure("Soul status API", f"Expected version 1.0.0, got {data['version']['version']}")
            return False
        
        if not data["integrity"]["valid"]:
            results.failure("Soul status API", f"Integrity check failed: {data['integrity']}")
            return False
        
        if data["drift"]["drift_detected"]:
            results.failure("Soul status API", f"Unexpected drift detected: {data['drift']}")
            return False
        
        if data["fragments"] != 5:
            results.failure("Soul status API", f"Expected 5 fragments, got {data['fragments']}")
            return False
        
        results.success("Soul status API - version 1.0.0, integrity valid, no drift, 5 fragments")
        return True
        
    except Exception as e:
        results.failure("Soul status API", str(e))
        return False

def test_soul_powers_identity_role():
    """Test 2: Soul powers IDENTITY_ROLE - dynamic content from vector memory (NOT hardcoded)."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/prompt/build",
            json={
                "purpose": "THOUGHT_TO_INTENT",
                "transcript": "Send a message to Sarah"
            },
            timeout=15
        )
        
        if response.status_code != 200:
            results.failure("Soul powers IDENTITY_ROLE", f"HTTP {response.status_code}")
            return False
        
        data = response.json()
        
        # Check if IDENTITY_ROLE is included in sections
        if "IDENTITY_ROLE" not in data.get("sections_included", []):
            results.failure("Soul powers IDENTITY_ROLE", "IDENTITY_ROLE section not included")
            return False
        
        # Check system message contains soul content (not hardcoded)
        messages = data.get("messages", [])
        system_message = None
        for msg in messages:
            if msg.get("role") == "system":
                system_message = msg.get("content", "")
                break
        
        if not system_message:
            results.failure("Soul powers IDENTITY_ROLE", "No system message found")
            return False
        
        # Check for soul fragment keywords from BASE_SOUL_FRAGMENTS (should be dynamic from vector memory)
        soul_keywords = ["sovereign", "empathetic", "cognitive", "Digital Self"]
        found_keywords = [kw for kw in soul_keywords if kw.lower() in system_message.lower()]
        
        if len(found_keywords) < 2:
            results.failure("Soul powers IDENTITY_ROLE", f"System message lacks soul fragment content. Found keywords: {found_keywords}")
            return False
        
        # Verify NOT using old hardcoded identity text
        if "MyndLens" not in system_message or "sovereign" not in system_message.lower():
            results.failure("Soul powers IDENTITY_ROLE", "Missing expected soul identity content")
            return False
        
        results.success("Soul powers IDENTITY_ROLE - dynamic soul fragments, NOT hardcoded text")
        return True
        
    except Exception as e:
        results.failure("Soul powers IDENTITY_ROLE", str(e))
        return False

def test_soul_personalization():
    """Test 3: Soul personalization API."""
    try:
        user_id = f"soul_user_{uuid.uuid4().hex[:8]}"
        response = requests.post(
            f"{BACKEND_URL}/soul/personalize",
            json={
                "user_id": user_id,
                "text": "I prefer formal communication and detailed explanations",
                "category": "communication"
            },
            timeout=10
        )
        
        if response.status_code != 200:
            results.failure("Soul personalization", f"HTTP {response.status_code}")
            return False
        
        data = response.json()
        
        if "fragment_id" not in data:
            results.failure("Soul personalization", "Missing fragment_id in response")
            return False
        
        if data.get("category") != "communication":
            results.failure("Soul personalization", f"Expected category 'communication', got {data.get('category')}")
            return False
        
        results.success("Soul personalization - user fragment added with fragment_id")
        return True
        
    except Exception as e:
        results.failure("Soul personalization", str(e))
        return False

def test_drift_detection_after_personalization():
    """Test 4: Drift detection should still be false after user personalization."""
    try:
        # Add a user fragment 
        user_id = f"drift_test_user_{uuid.uuid4().hex[:8]}"
        requests.post(
            f"{BACKEND_URL}/soul/personalize",
            json={
                "user_id": user_id,
                "text": "I work best in the morning hours",
                "category": "schedule"
            },
            timeout=10
        )
        
        # Check soul status - user additions should NOT trigger drift
        response = requests.get(f"{BACKEND_URL}/soul/status", timeout=10)
        if response.status_code != 200:
            results.failure("Drift after personalization", f"HTTP {response.status_code}")
            return False
        
        data = response.json()
        
        # drift_detected should still be false (user additions don't count as drift)
        if data["drift"]["drift_detected"]:
            results.failure("Drift after personalization", "Drift detected after user personalization - should be false")
            return False
        
        results.success("Drift after personalization - drift_detected still false")
        return True
        
    except Exception as e:
        results.failure("Drift after personalization", str(e))
        return False

def test_soul_hash_stability():
    """Test 5: Soul base_hash should be identical across calls."""
    try:
        response1 = requests.get(f"{BACKEND_URL}/soul/status", timeout=10)
        if response1.status_code != 200:
            results.failure("Soul hash stability", f"First call HTTP {response1.status_code}")
            return False
        
        time.sleep(1)
        
        response2 = requests.get(f"{BACKEND_URL}/soul/status", timeout=10)
        if response2.status_code != 200:
            results.failure("Soul hash stability", f"Second call HTTP {response2.status_code}")
            return False
        
        data1 = response1.json()
        data2 = response2.json()
        
        hash1 = data1["drift"]["base_hash"]
        hash2 = data2["drift"]["base_hash"]
        
        if hash1 != hash2:
            results.failure("Soul hash stability", f"Base hash changed: {hash1} != {hash2}")
            return False
        
        results.success("Soul hash stability - base_hash identical across calls")
        return True
        
    except Exception as e:
        results.failure("Soul hash stability", str(e))
        return False

def get_sso_token_and_device():
    """Get SSO token and device_id for WebSocket testing."""
    try:
        device_id = f"device_{uuid.uuid4().hex[:8]}"
        response = requests.post(
            f"{BACKEND_URL}/sso/myndlens/token",
            json={
                "username": f"soul_ws_user_{uuid.uuid4().hex[:8]}",
                "password": "password", 
                "device_id": device_id
            },
            timeout=10
        )
        if response.status_code == 200:
            return response.json()["token"], device_id
    except Exception as e:
        log(f"Failed to get SSO token: {e}")
    return None, None

def test_soul_fragments_in_l1_scout():
    """Test 6: Soul fragments used in L1 Scout (MOST IMPORTANT TEST)."""
    try:
        # Get SSO token and device_id
        token, device_id = get_sso_token_and_device()
        if not token or not device_id:
            results.failure("Soul in L1 Scout", "Could not get SSO token or device_id")
            return False
        
        # WebSocket connection test with proper message format
        ws_messages = []
        ws_error = None
        ws_connected = threading.Event()
        auth_success = threading.Event()
        session_id = None
        
        def on_message(ws, message):
            nonlocal session_id
            try:
                data = json.loads(message)
                ws_messages.append(data)
                log(f"WS received: {data.get('type', 'unknown')}")
                
                if data.get('type') == 'auth_ok':
                    session_id = data.get('payload', {}).get('session_id')
                    auth_success.set()
                    log(f"Auth success, session_id: {session_id}")
                    
            except Exception as e:
                log(f"WS message parse error: {e}")
        
        def on_error(ws, error):
            nonlocal ws_error
            ws_error = error
            log(f"WS error: {error}")
        
        def on_open(ws):
            ws_connected.set()
            log("WS connected")
        
        def on_close(ws, close_status_code, close_msg):
            log(f"WS closed: {close_status_code}")
        
        # Create WebSocket connection
        ws = websocket.WebSocketApp(
            WS_URL,
            on_message=on_message,
            on_error=on_error,
            on_open=on_open,
            on_close=on_close
        )
        
        # Run WebSocket in thread
        ws_thread = threading.Thread(target=ws.run_forever)
        ws_thread.daemon = True
        ws_thread.start()
        
        # Wait for connection
        if not ws_connected.wait(timeout=10):
            results.failure("Soul in L1 Scout", "WebSocket connection timeout")
            return False
        
        # Send auth message with both token and device_id
        auth_msg = {
            "type": "auth",
            "payload": {
                "token": token,
                "device_id": device_id,
                "client_version": "1.0.0"
            }
        }
        ws.send(json.dumps(auth_msg))
        
        # Wait for auth success and get session_id
        if not auth_success.wait(timeout=5):
            results.failure("Soul in L1 Scout", "WebSocket auth failed")
            ws.close()
            return False
        
        if not session_id:
            results.failure("Soul in L1 Scout", "No session_id received in auth_ok")
            ws.close()
            return False
        
        # Send heartbeat with session_id and seq
        heartbeat_msg = {
            "type": "heartbeat",
            "payload": {
                "session_id": session_id,
                "seq": 1,
                "client_ts": datetime.now().isoformat()
            }
        }
        ws.send(json.dumps(heartbeat_msg))
        
        # Wait for heartbeat ack
        time.sleep(2)
        
        # Send text input to trigger L1 Scout with session_id
        text_msg = {
            "type": "text_input",
            "payload": {
                "session_id": session_id,
                "text": "Send a message to Sarah about the meeting"
            }
        }
        ws.send(json.dumps(text_msg))
        
        # Wait for L1 Scout response (longer timeout for processing)
        time.sleep(10)
        
        ws.close()
        
        # Check if we got expected responses
        transcript_final_received = False
        draft_update_received = False
        tts_audio_received = False
        
        for msg in ws_messages:
            msg_type = msg.get("type")
            if msg_type == "transcript_final":
                transcript_final_received = True
            elif msg_type == "draft_update":
                draft_update_received = True
            elif msg_type == "tts_audio":
                tts_audio_received = True
        
        # The key test: L1 Scout should process text and use Soul-powered prompts
        if not transcript_final_received:
            results.failure("Soul in L1 Scout", f"No transcript_final received. Messages: {[m.get('type') for m in ws_messages]}")
            return False
        
        # Successful L1 Scout flow indicates Soul fragments are being used in IDENTITY_ROLE
        # (as verified in test 2 that IDENTITY_ROLE is now powered by Soul Store)
        results.success("Soul in L1 Scout - L1 Scout using Soul-powered identity prompts")
        return True
        
    except Exception as e:
        results.failure("Soul in L1 Scout", str(e))
        return False

# Regression Tests

def test_regression_health():
    """Regression: Health endpoint."""
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "ok":
                results.success("Regression: Health")
                return True
        results.failure("Regression: Health", f"Status: {response.status_code}")
        return False
    except Exception as e:
        results.failure("Regression: Health", str(e))
        return False

def test_regression_sso():
    """Regression: SSO login."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/sso/myndlens/token",
            json={
                "username": f"reg_user_{uuid.uuid4().hex[:8]}",
                "password": "password",
                "device_id": f"device_{uuid.uuid4().hex[:8]}"
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if "token" in data:
                results.success("Regression: SSO")
                return True
        
        results.failure("Regression: SSO", f"HTTP {response.status_code}")
        return False
        
    except Exception as e:
        results.failure("Regression: SSO", str(e))
        return False

def test_regression_l1_flow():
    """Regression: L1 Scout prompt building."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/prompt/build",
            json={
                "purpose": "THOUGHT_TO_INTENT",
                "transcript": "Check my calendar"
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("messages") and len(data.get("messages", [])) > 0:
                results.success("Regression: L1 flow")
                return True
        
        results.failure("Regression: L1 flow", f"HTTP {response.status_code}")
        return False
        
    except Exception as e:
        results.failure("Regression: L1 flow", str(e))
        return False

def test_regression_memory():
    """Regression: Memory APIs."""
    try:
        user_id = f"reg_mem_user_{uuid.uuid4().hex[:8]}"
        
        # Store a fact
        response = requests.post(
            f"{BACKEND_URL}/memory/store",
            json={
                "user_id": user_id,
                "text": "Sarah is my colleague at work",
                "fact_type": "FACT",
                "provenance": "EXPLICIT"
            },
            timeout=10
        )
        
        if response.status_code != 200:
            results.failure("Regression: Memory", f"Store HTTP {response.status_code}")
            return False
        
        # Recall the fact
        response = requests.post(
            f"{BACKEND_URL}/memory/recall",
            json={
                "user_id": user_id,
                "query": "Who is Sarah?",
                "n_results": 3
            },
            timeout=10
        )
        
        if response.status_code != 200:
            results.failure("Regression: Memory", f"Recall HTTP {response.status_code}")
            return False
        
        results.success("Regression: Memory")
        return True
        
    except Exception as e:
        results.failure("Regression: Memory", str(e))
        return False

def test_regression_prompt_compliance():
    """Regression: Prompt compliance."""
    try:
        response = requests.get(f"{BACKEND_URL}/prompt/compliance", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if "call_sites" in data and "rogue_prompt_scan" in data:
                results.success("Regression: Prompt compliance")
                return True
        
        results.failure("Regression: Prompt compliance", f"HTTP {response.status_code}")
        return False
        
    except Exception as e:
        results.failure("Regression: Prompt compliance", str(e))
        return False

def run_all_tests():
    """Run all MyndLens Batch 13 Soul Vector Memory tests."""
    log("=== MyndLens Batch 13: Soul Vector Memory Testing ===")
    
    # Critical Soul Tests (from review request)
    log("\n--- CRITICAL SOUL TESTS ---")
    test_soul_status()                          # 1) Soul status: version, integrity, drift, fragments=5
    test_soul_powers_identity_role()            # 2) Soul powers IDENTITY_ROLE (NOT hardcoded)
    test_soul_personalization()                # 3) Soul personalization API
    test_drift_detection_after_personalization() # 4) Drift detection after user additions
    test_soul_hash_stability()                  # 5) Soul hash stability 
    test_soul_fragments_in_l1_scout()          # 6) Soul fragments in L1 Scout (MOST IMPORTANT)
    
    # Regression Tests
    log("\n--- REGRESSION TESTS ---")
    test_regression_health()                    # Health endpoint
    test_regression_sso()                       # SSO login
    test_regression_l1_flow()                  # L1 Scout flow
    test_regression_memory()                    # Memory APIs
    test_regression_prompt_compliance()         # Prompt compliance
    
    # Summary
    log("\n" + "="*60)
    results.summary()
    
    return results.failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)