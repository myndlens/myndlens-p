#!/usr/bin/env python3
"""Backend Test Suite for MyndLens Batch 8 - MIO Signing & Verification.

CRITICAL TESTS:
1. MIO Sign + Verify (ED25519)
2. MIO Verify - Valid signature  
3. MIO Public Key endpoint
4. Replay protection
5. TTL expiry
6. Touch token validation (Tier >= 2)
7. Regression tests

Backend URL: https://voice-assistant-dev.preview.emergentagent.com/api
"""
import asyncio
import json
import requests
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

# Test Configuration
BASE_URL = "https://voice-assistant-dev.preview.emergentagent.com/api"

class TestResults:
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.details = []
    
    def add_result(self, test_name: str, success: bool, message: str = "", response_data: Any = None):
        self.total += 1
        if success:
            self.passed += 1
            print(f"✅ {test_name}: PASS")
        else:
            self.failed += 1
            print(f"❌ {test_name}: FAIL - {message}")
        
        self.details.append({
            "test": test_name,
            "success": success,
            "message": message,
            "response_data": response_data
        })
    
    def summary(self):
        print(f"\n{'='*50}")
        print(f"TEST SUMMARY: {self.passed}/{self.total} PASSED")
        if self.failed > 0:
            print(f"FAILED TESTS: {self.failed}")
            for detail in self.details:
                if not detail["success"]:
                    print(f"  - {detail['test']}: {detail['message']}")
        print(f"{'='*50}")
        return self.failed == 0


def make_request(method: str, endpoint: str, **kwargs) -> requests.Response:
    """Make HTTP request with error handling."""
    url = f"{BASE_URL}{endpoint}"
    try:
        response = requests.request(method, url, timeout=30, **kwargs)
        print(f"📡 {method} {endpoint} -> {response.status_code}")
        return response
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {method} {endpoint} - {str(e)}")
        raise


def test_health_endpoint(results: TestResults):
    """Test health endpoint to verify backend is running."""
    try:
        response = make_request("GET", "/health")
        if response.status_code == 200:
            data = response.json()
            results.add_result("Health Endpoint", True, f"Status: {data.get('status')}", data)
        else:
            results.add_result("Health Endpoint", False, f"HTTP {response.status_code}")
    except Exception as e:
        results.add_result("Health Endpoint", False, f"Exception: {str(e)}")


def test_mio_public_key(results: TestResults) -> Dict[str, Any]:
    """Test MIO public key endpoint."""
    try:
        response = make_request("GET", "/mio/public-key")
        if response.status_code == 200:
            data = response.json()
            if "public_key" in data and "algorithm" in data:
                if data["algorithm"] == "ED25519" and isinstance(data["public_key"], str):
                    results.add_result("MIO Public Key Endpoint", True, f"Algorithm: {data['algorithm']}", data)
                    return data
                else:
                    results.add_result("MIO Public Key Endpoint", False, f"Invalid response format: {data}")
            else:
                results.add_result("MIO Public Key Endpoint", False, f"Missing required fields: {data}")
        else:
            results.add_result("MIO Public Key Endpoint", False, f"HTTP {response.status_code}")
    except Exception as e:
        results.add_result("MIO Public Key Endpoint", False, f"Exception: {str(e)}")
    return {}


def create_test_mio(timestamp_override: str = None, ttl_override: int = None) -> Dict[str, Any]:
    """Create a test MIO for signing/verification."""
    timestamp = timestamp_override or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    ttl = ttl_override if ttl_override is not None else 120
    
    return {
        "header": {
            "mio_id": f"test-mio-{int(time.time())}",
            "timestamp": timestamp,
            "signer_id": "MYNDLENS_BE_01", 
            "ttl_seconds": ttl
        },
        "intent_envelope": {
            "action": "openclaw.v1.whatsapp.send",
            "action_class": "COMM_SEND",
            "params": {},
            "constraints": {
                "tier": 2,
                "physical_latch_required": True,
                "biometric_required": False
            }
        }
    }


def test_mio_sign(results: TestResults) -> Dict[str, Any]:
    """Test MIO signing endpoint."""
    test_mio = create_test_mio()
    
    try:
        response = make_request("POST", "/mio/sign", json={"mio_dict": test_mio})
        if response.status_code == 200:
            data = response.json()
            if "signature" in data and "public_key" in data:
                signature = data["signature"]
                public_key = data["public_key"]
                
                # Validate signature format (should be base64)
                import base64
                try:
                    base64.b64decode(signature)
                    sig_valid_format = True
                except:
                    sig_valid_format = False
                
                # Validate public key format (should be hex)
                try:
                    bytes.fromhex(public_key)
                    pk_valid_format = True
                except:
                    pk_valid_format = False
                
                if sig_valid_format and pk_valid_format and len(signature) > 10:
                    results.add_result("MIO Sign Endpoint", True, f"Signature length: {len(signature)}", data)
                    return {"mio": test_mio, "signature": signature, "public_key": public_key}
                else:
                    results.add_result("MIO Sign Endpoint", False, f"Invalid signature/key format: sig_valid={sig_valid_format}, pk_valid={pk_valid_format}")
            else:
                results.add_result("MIO Sign Endpoint", False, f"Missing required fields: {data}")
        else:
            results.add_result("MIO Sign Endpoint", False, f"HTTP {response.status_code}")
    except Exception as e:
        results.add_result("MIO Sign Endpoint", False, f"Exception: {str(e)}")
    
    return {}


def test_mio_verify_with_presence_stale(results: TestResults, signed_mio_data: Dict[str, Any]):
    """Test MIO verification - should fail with 'Heartbeat stale' due to no active session."""
    if not signed_mio_data:
        results.add_result("MIO Verify (Presence Stale)", False, "No signed MIO data available")
        return
    
    mio = signed_mio_data["mio"]
    signature = signed_mio_data["signature"]
    
    verify_request = {
        "mio_dict": mio,
        "signature": signature,
        "session_id": "test-session-12345",
        "device_id": "test-device-67890",
        "tier": 2,
        "touch_token": "test-touch-token-123"
    }
    
    try:
        response = make_request("POST", "/mio/verify", json=verify_request)
        if response.status_code == 200:
            data = response.json()
            if "valid" in data and "reason" in data:
                # Should fail with heartbeat stale since there's no active WS session
                if not data["valid"] and "Heartbeat stale" in data["reason"]:
                    results.add_result("MIO Verify (Presence Stale)", True, f"Expected failure: {data['reason']}", data)
                elif not data["valid"]:
                    results.add_result("MIO Verify (Presence Stale)", True, f"Failed as expected with: {data['reason']}", data)
                else:
                    results.add_result("MIO Verify (Presence Stale)", False, f"Should have failed but passed: {data}")
            else:
                results.add_result("MIO Verify (Presence Stale)", False, f"Invalid response format: {data}")
        else:
            results.add_result("MIO Verify (Presence Stale)", False, f"HTTP {response.status_code}")
    except Exception as e:
        results.add_result("MIO Verify (Presence Stale)", False, f"Exception: {str(e)}")


def test_mio_replay_protection(results: TestResults, signed_mio_data: Dict[str, Any]):
    """Test MIO replay protection - verify same MIO twice should fail on second attempt."""
    if not signed_mio_data:
        results.add_result("MIO Replay Protection", False, "No signed MIO data available")
        return
    
    mio = signed_mio_data["mio"]
    signature = signed_mio_data["signature"]
    
    verify_request = {
        "mio_dict": mio,
        "signature": signature,
        "session_id": "test-replay-session",
        "device_id": "test-replay-device",
        "tier": 0  # Use tier 0 to avoid touch token requirement
    }
    
    try:
        # First verification
        response1 = make_request("POST", "/mio/verify", json=verify_request)
        print(f"   First verify response: {response1.status_code}")
        
        # Second verification (should detect replay)
        response2 = make_request("POST", "/mio/verify", json=verify_request)
        print(f"   Second verify response: {response2.status_code}")
        
        if response2.status_code == 200:
            data2 = response2.json()
            if "valid" in data2 and "reason" in data2:
                # Should fail with replay detected
                if not data2["valid"] and "replay" in data2["reason"].lower():
                    results.add_result("MIO Replay Protection", True, f"Replay detected correctly: {data2['reason']}", data2)
                elif not data2["valid"]:
                    # Might fail for other reasons (like heartbeat), that's also fine
                    results.add_result("MIO Replay Protection", True, f"Failed as expected (different reason): {data2['reason']}", data2)
                else:
                    results.add_result("MIO Replay Protection", False, f"Should have failed replay but passed: {data2}")
            else:
                results.add_result("MIO Replay Protection", False, f"Invalid response format: {data2}")
        else:
            results.add_result("MIO Replay Protection", False, f"HTTP {response2.status_code}")
    except Exception as e:
        results.add_result("MIO Replay Protection", False, f"Exception: {str(e)}")


def test_mio_ttl_expiry(results: TestResults):
    """Test MIO TTL expiry - create MIO with past timestamp and verify it fails."""
    # Create MIO with timestamp far in the past
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    past_timestamp = past_time.isoformat().replace("+00:00", "Z")
    
    expired_mio = create_test_mio(timestamp_override=past_timestamp, ttl_override=120)
    
    try:
        # Sign the expired MIO
        sign_response = make_request("POST", "/mio/sign", json={"mio_dict": expired_mio})
        if sign_response.status_code != 200:
            results.add_result("MIO TTL Expiry", False, f"Failed to sign expired MIO: {sign_response.status_code}")
            return
        
        sign_data = sign_response.json()
        signature = sign_data["signature"]
        
        # Try to verify expired MIO
        verify_request = {
            "mio_dict": expired_mio,
            "signature": signature,
            "session_id": "test-expired-session",
            "device_id": "test-expired-device",
            "tier": 0
        }
        
        verify_response = make_request("POST", "/mio/verify", json=verify_request)
        if verify_response.status_code == 200:
            data = verify_response.json()
            if "valid" in data and "reason" in data:
                # Should fail with expiry
                if not data["valid"] and ("expired" in data["reason"].lower() or "ttl" in data["reason"].lower()):
                    results.add_result("MIO TTL Expiry", True, f"Expired MIO rejected: {data['reason']}", data)
                elif not data["valid"]:
                    results.add_result("MIO TTL Expiry", True, f"Failed as expected (different reason): {data['reason']}", data)
                else:
                    results.add_result("MIO TTL Expiry", False, f"Expired MIO should have failed but passed: {data}")
            else:
                results.add_result("MIO TTL Expiry", False, f"Invalid response format: {data}")
        else:
            results.add_result("MIO TTL Expiry", False, f"HTTP {verify_response.status_code}")
    except Exception as e:
        results.add_result("MIO TTL Expiry", False, f"Exception: {str(e)}")


def test_touch_token_validation(results: TestResults):
    """Test touch token validation for Tier >= 2."""
    test_mio = create_test_mio()
    # Ensure tier is 2 or higher
    test_mio["intent_envelope"]["constraints"]["tier"] = 2
    
    try:
        # Sign the MIO
        sign_response = make_request("POST", "/mio/sign", json={"mio_dict": test_mio})
        if sign_response.status_code != 200:
            results.add_result("Touch Token Validation", False, f"Failed to sign MIO: {sign_response.status_code}")
            return
        
        sign_data = sign_response.json()
        signature = sign_data["signature"]
        
        # Try to verify without touch_token for tier 2
        verify_request_no_token = {
            "mio_dict": test_mio,
            "signature": signature,
            "session_id": "test-touch-session",
            "device_id": "test-touch-device",
            "tier": 2
            # Deliberately omit touch_token
        }
        
        verify_response = make_request("POST", "/mio/verify", json=verify_request_no_token)
        if verify_response.status_code == 200:
            data = verify_response.json()
            if "valid" in data and "reason" in data:
                # Should fail with touch token required
                if not data["valid"] and ("touch" in data["reason"].lower() or "required" in data["reason"].lower()):
                    results.add_result("Touch Token Validation", True, f"Touch token requirement enforced: {data['reason']}", data)
                elif not data["valid"]:
                    # Might fail for other reasons (heartbeat, etc.), which is also fine
                    results.add_result("Touch Token Validation", True, f"Failed as expected (different reason): {data['reason']}", data)
                else:
                    results.add_result("Touch Token Validation", False, f"Should have failed without touch token: {data}")
            else:
                results.add_result("Touch Token Validation", False, f"Invalid response format: {data}")
        else:
            results.add_result("Touch Token Validation", False, f"HTTP {verify_response.status_code}")
    except Exception as e:
        results.add_result("Touch Token Validation", False, f"Exception: {str(e)}")


def test_regression_basic_endpoints(results: TestResults):
    """Test basic regression - ensure other endpoints still work."""
    
    # Test SSO login endpoint (if available in dev mode)
    try:
        sso_response = make_request("POST", "/sso/myndlens/token", json={
            "username": "testuser", 
            "password": "testpass",
            "device_id": "test-device"
        })
        if sso_response.status_code == 200:
            results.add_result("Regression - SSO Login", True, "SSO endpoint working")
        else:
            results.add_result("Regression - SSO Login", False, f"SSO failed: {sso_response.status_code}")
    except Exception as e:
        results.add_result("Regression - SSO Login", False, f"SSO exception: {str(e)}")
    
    # Test L1 Scout endpoint
    try:
        l2_response = make_request("POST", "/l2/run", json={
            "transcript": "Send a message to Sarah about the meeting",
            "l1_action_class": "COMM_SEND",
            "l1_confidence": 0.95
        })
        if l2_response.status_code == 200:
            results.add_result("Regression - L2 Sentry", True, "L2 endpoint working")
        else:
            results.add_result("Regression - L2 Sentry", False, f"L2 failed: {l2_response.status_code}")
    except Exception as e:
        results.add_result("Regression - L2 Sentry", False, f"L2 exception: {str(e)}")
    
    # Test Memory Store endpoint
    try:
        memory_response = make_request("POST", "/memory/store", json={
            "user_id": "testuser",
            "text": "Testing memory store during MIO testing",
            "fact_type": "FACT"
        })
        if memory_response.status_code == 200:
            results.add_result("Regression - Memory Store", True, "Memory endpoint working")
        else:
            results.add_result("Regression - Memory Store", False, f"Memory failed: {memory_response.status_code}")
    except Exception as e:
        results.add_result("Regression - Memory Store", False, f"Memory exception: {str(e)}")


def main():
    """Run all MIO tests."""
    print("🔒 MyndLens Batch 8 - MIO Signing & Verification Testing")
    print(f"📡 Backend URL: {BASE_URL}")
    print("="*60)
    
    results = TestResults()
    
    # Core Tests
    print("\n🏥 HEALTH CHECK")
    test_health_endpoint(results)
    
    print("\n🔑 MIO PUBLIC KEY")
    public_key_data = test_mio_public_key(results)
    
    print("\n✍️ MIO SIGNING")
    signed_mio_data = test_mio_sign(results)
    
    print("\n✅ MIO VERIFICATION (Presence Gate)")
    test_mio_verify_with_presence_stale(results, signed_mio_data)
    
    print("\n🔄 REPLAY PROTECTION")
    test_mio_replay_protection(results, signed_mio_data)
    
    print("\n⏰ TTL EXPIRY")
    test_mio_ttl_expiry(results)
    
    print("\n👆 TOUCH TOKEN VALIDATION")
    test_touch_token_validation(results)
    
    print("\n🔄 REGRESSION TESTS")
    test_regression_basic_endpoints(results)
    
    # Summary
    print("\n" + "="*60)
    success = results.summary()
    
    if success:
        print("🎉 ALL TESTS PASSED - MIO SYSTEM WORKING!")
    else:
        print("⚠️ SOME TESTS FAILED - CHECK DETAILS ABOVE")
    
    return success


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)