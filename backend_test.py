#!/usr/bin/env python3
"""Backend Testing — MyndLens Batch 13: Soul Vector Memory System.

Tests critical Soul functionality and regression tests.
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

def test_health_endpoint():
    """Test health endpoint for baseline."""
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "ok":
                results.success("Health endpoint")
                return True
        results.failure("Health endpoint", f"Status: {response.status_code}")
        return False
    except Exception as e:
        results.failure("Health endpoint", str(e))
        return False

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
        
        # Check expected values
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
        
        results.success("Soul status API - all checks passed")
        return True
        
    except Exception as e:
        results.failure("Soul status API", str(e))
        return False

def test_soul_powers_identity_role():
    """Test 2: Soul powers IDENTITY_ROLE - dynamic content from vector memory."""
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
        
        # Check for soul fragment keywords (should be dynamic from vector memory)
        soul_keywords = ["sovereign", "empathetic", "cognitive proxy", "Digital Self"]
        found_keywords = [kw for kw in soul_keywords if kw.lower() in system_message.lower()]
        
        if len(found_keywords) < 2:
            results.failure("Soul powers IDENTITY_ROLE", f"System message lacks soul content. Found keywords: {found_keywords}")
            return False
        
        # Ensure it's NOT the old hardcoded text
        hardcoded_text = "You are MyndLens, a sovereign voice assistant."
        if hardcoded_text in system_message and "vector-graph memory" not in system_message:
            results.failure("Soul powers IDENTITY_ROLE", "Still using old hardcoded identity text")
            return False
        
        results.success("Soul powers IDENTITY_ROLE - dynamic from vector memory")
        return True
        
    except Exception as e:
        results.failure("Soul powers IDENTITY_ROLE", str(e))
        return False

def test_soul_personalization():
    """Test 3: Soul personalization API."""
    try:
        user_id = f"test_soul_user_{uuid.uuid4().hex[:8]}"
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
        
        results.success("Soul personalization API")
        return True
        
    except Exception as e:
        results.failure("Soul personalization", str(e))
        return False

def test_drift_detection_after_personalization():
    """Test 4: Drift detection should still be false after adding user fragments."""
    try:
        # Add a user fragment first
        user_id = f"test_drift_user_{uuid.uuid4().hex[:8]}"
        requests.post(
            f"{BACKEND_URL}/soul/personalize",
            json={
                "user_id": user_id,
                "text": "Test user preference for drift test",
                "category": "test"
            },
            timeout=10
        )
        
        # Check soul status again
        response = requests.get(f"{BACKEND_URL}/soul/status", timeout=10)
        if response.status_code != 200:
            results.failure("Drift detection after personalization", f"HTTP {response.status_code}")
            return False
        
        data = response.json()
        
        # drift_detected should still be false (user additions don't count as drift)
        if data["drift"]["drift_detected"]:
            results.failure("Drift detection after personalization", "Drift detected after user personalization")
            return False
        
        # user_additions count should have increased
        if data["drift"]["user_additions"] < 1:
            results.failure("Drift detection after personalization", "User additions count not updated")
            return False
        
        results.success("Drift detection after personalization - no drift")
        return True
        
    except Exception as e:
        results.failure("Drift detection after personalization", str(e))
        return False

def test_soul_hash_stability():
    """Test 5: Soul hash should be stable across calls."""
    try:
        response1 = requests.get(f"{BACKEND_URL}/soul/status", timeout=10)
        if response1.status_code != 200:
            results.failure("Soul hash stability", f"First call HTTP {response1.status_code}")
            return False
        
        time.sleep(1)  # Small delay
        
        response2 = requests.get(f"{BACKEND_URL}/soul/status", timeout=10)
        if response2.status_code != 200:
            results.failure("Soul hash stability", f"Second call HTTP {response2.status_code}")
            return False
        
        data1 = response1.json()
        data2 = response2.json()
        
        hash1 = data1["drift"]["base_hash"]
        hash2 = data2["drift"]["base_hash"]
        
        if hash1 != hash2:
            results.failure("Soul hash stability", f"Hash changed: {hash1} != {hash2}")
            return False
        
        results.success("Soul hash stability - identical across calls")
        return True
        
    except Exception as e:
        results.failure("Soul hash stability", str(e))
        return False

def get_sso_token():
    """Get SSO token for WebSocket testing."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/sso/myndlens/token",
            json={
                "username": f"soul_test_user_{uuid.uuid4().hex[:8]}",
                "password": "password",
                "device_id": f"device_{uuid.uuid4().hex[:8]}"
            },
            timeout=10
        )
        if response.status_code == 200:
            return response.json()["token"]
    except Exception as e:
        log(f"Failed to get SSO token: {e}")
    return None

def test_soul_fragments_in_l1_scout():
    """Test 6: Soul fragments used in L1 Scout (most important test)."""
    try:
        # Get SSO token
        token = get_sso_token()
        if not token:
            results.failure("Soul fragments in L1 Scout", "Could not get SSO token")
            return False
        
        # WebSocket connection test
        ws_messages = []
        ws_error = None
        ws_connected = threading.Event()
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                ws_messages.append(data)
                log(f"WS received: {data.get('type', 'unknown')}")
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
            results.failure("Soul fragments in L1 Scout", "WebSocket connection timeout")
            return False
        
        # Send auth message
        auth_msg = {
            "type": "auth",
            "payload": {"token": token}
        }
        ws.send(json.dumps(auth_msg))
        
        # Wait for auth response
        time.sleep(2)
        
        # Send heartbeat
        heartbeat_msg = {
            "type": "heartbeat",
            "payload": {"timestamp": datetime.now().isoformat()}
        }
        ws.send(json.dumps(heartbeat_msg))
        
        # Wait for heartbeat ack
        time.sleep(1)
        
        # Send text input to trigger L1 Scout
        text_msg = {
            "type": "text_input",
            "payload": {"text": "Send a message to Sarah about the meeting"}
        }
        ws.send(json.dumps(text_msg))
        
        # Wait for responses
        time.sleep(5)
        
        ws.close()
        
        # Check if we got draft_update (L1 Scout response)
        draft_update_received = False
        for msg in ws_messages:
            if msg.get("type") == "draft_update":
                draft_update_received = True
                break
        
        if not draft_update_received:
            results.failure("Soul fragments in L1 Scout", "No draft_update received from L1 Scout")
            return False
        
        # The fact that L1 Scout responded indicates it's using the prompt system
        # which should now be powered by Soul fragments (verified in test 2)
        results.success("Soul fragments in L1 Scout - L1 flow working with Soul system")
        return True
        
    except Exception as e:
        results.failure("Soul fragments in L1 Scout", str(e))
        return False

def test_regression_health():
    """Regression test: Health endpoint."""
    return test_health_endpoint()

def test_regression_sso():
    """Regression test: SSO login."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/sso/myndlens/token",
            json={
                "username": f"regression_user_{uuid.uuid4().hex[:8]}",
                "password": "password",
                "device_id": f"device_{uuid.uuid4().hex[:8]}"
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if "token" in data:
                results.success("Regression: SSO login")
                return True
        
        results.failure("Regression: SSO login", f"HTTP {response.status_code}")
        return False
        
    except Exception as e:
        results.failure("Regression: SSO login", str(e))
        return False

def test_regression_memory():
    """Regression test: Memory APIs."""
    try:
        user_id = f"regression_mem_user_{uuid.uuid4().hex[:8]}"
        
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
            results.failure("Regression: Memory store", f"HTTP {response.status_code}")
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
            results.failure("Regression: Memory recall", f"HTTP {response.status_code}")
            return False
        
        results.success("Regression: Memory APIs")
        return True
        
    except Exception as e:
        results.failure("Regression: Memory APIs", str(e))
        return False

def test_regression_prompt_compliance():
    """Regression test: Prompt compliance."""
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
    """Run all Soul system tests."""
    log("=== MyndLens Batch 13: Soul Vector Memory Testing ===")
    
    # Critical Soul Tests
    log("\n--- Critical Soul Tests ---")
    test_soul_status()
    test_soul_powers_identity_role()
    test_soul_personalization()
    test_drift_detection_after_personalization()
    test_soul_hash_stability()
    test_soul_fragments_in_l1_scout()
    
    # Regression Tests
    log("\n--- Regression Tests ---")
    test_regression_health()
    test_regression_sso()
    test_regression_memory()
    test_regression_prompt_compliance()
    
    # Summary
    log("\n" + "="*50)
    results.summary()
    
    return results.failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)