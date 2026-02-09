#!/usr/bin/env python3
"""
MyndLens SSO Consumer + Tenant Activation Backend Test Suite
Critical Test Gates from review request - Testing all SSO and tenant functionality.
"""
import asyncio
import base64
import json
import jwt
import os
import sys
import uuid
import websockets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

import httpx


# Test configuration
BACKEND_URL = os.getenv("REACT_APP_BACKEND_URL", "http://localhost:8001")
API_BASE = f"{BACKEND_URL}/api"
WS_URL = f"{BACKEND_URL.replace('http://', 'ws://').replace('https://', 'wss://')}/api/ws"

# Test secrets and tokens (matching backend config)
OBEGEE_SSO_SECRET = "obegee-sso-dev-secret-CHANGE-IN-PROD"
S2S_TOKEN = "obegee-s2s-dev-token-CHANGE-IN-PROD"


class TestResults:
    def __init__(self):
        self.results = []
        self.failed_tests = []
        
    def add_result(self, test_name: str, success: bool, details: str = ""):
        status = "✅ PASS" if success else "❌ FAIL"
        result = f"{status}: {test_name}"
        if details:
            result += f" - {details}"
        self.results.append(result)
        if not success:
            self.failed_tests.append(f"{test_name}: {details}")
        print(result)
        
    def summary(self):
        total = len(self.results)
        failed = len(self.failed_tests)
        passed = total - failed
        print(f"\n📊 TEST SUMMARY: {passed}/{total} passed")
        if self.failed_tests:
            print("🚨 FAILED TESTS:")
            for failed in self.failed_tests:
                print(f"  - {failed}")
        return failed == 0


def create_manual_sso_token(obegee_user_id: str, tenant_id: str, subscription_status: str = "ACTIVE", exp_hours: int = 24) -> str:
    """Create a manual SSO token with specific subscription status."""
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "obegee",
        "aud": "myndlens", 
        "obegee_user_id": obegee_user_id,
        "myndlens_tenant_id": tenant_id,
        "subscription_status": subscription_status,
        "iat": now.timestamp(),
        "exp": (now + timedelta(hours=exp_hours)).timestamp(),
    }
    return jwt.encode(payload, OBEGEE_SSO_SECRET, algorithm="HS256")


async def test_health_endpoint(results: TestResults):
    """Test health endpoint returns correct status."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE}/health")
            
        if response.status_code == 200:
            data = response.json()
            required_fields = ["status", "env", "version", "active_sessions"]
            if all(field in data for field in required_fields) and data["status"] == "ok":
                results.add_result("Health endpoint", True, f"status={data['status']}, env={data['env']}")
            else:
                results.add_result("Health endpoint", False, f"Missing required fields or status != ok: {data}")
        else:
            results.add_result("Health endpoint", False, f"HTTP {response.status_code}")
    except Exception as e:
        results.add_result("Health endpoint", False, f"Exception: {e}")


async def test_mock_sso_login(results: TestResults) -> Dict[str, Any]:
    """Test 1: Mock SSO Login → token generation."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_BASE}/sso/myndlens/token", json={
                "username": "testuser",
                "password": "pass", 
                "device_id": "dev001"
            })
            
        if response.status_code == 200:
            data = response.json()
            required_fields = ["token", "obegee_user_id", "myndlens_tenant_id", "subscription_status"]
            
            if all(field in data for field in required_fields):
                # Validate JWT token
                try:
                    decoded = jwt.decode(data["token"], OBEGEE_SSO_SECRET, 
                                      algorithms=["HS256"], audience="myndlens", issuer="obegee")
                    
                    if (decoded.get("iss") == "obegee" and 
                        decoded.get("aud") == "myndlens" and
                        data["subscription_status"] == "ACTIVE"):
                        results.add_result("Mock SSO Login", True, 
                                         f"Valid JWT issued for user={data['obegee_user_id']}, tenant={data['myndlens_tenant_id']}")
                        return data
                    else:
                        results.add_result("Mock SSO Login", False, "JWT validation failed - incorrect claims")
                except jwt.InvalidTokenError as e:
                    results.add_result("Mock SSO Login", False, f"JWT validation failed: {e}")
            else:
                results.add_result("Mock SSO Login", False, f"Missing required fields: {data}")
        else:
            results.add_result("Mock SSO Login", False, f"HTTP {response.status_code}: {response.text}")
            
        return {}
    except Exception as e:
        results.add_result("Mock SSO Login", False, f"Exception: {e}")
        return {}


async def test_ws_auth_with_sso_token(results: TestResults, token: str, device_id: str = "dev001") -> str:
    """Test WebSocket authentication with SSO token."""
    try:
        async with websockets.connect(WS_URL) as ws:
            # Send auth message
            auth_msg = {
                "type": "auth",
                "payload": {
                    "token": token,
                    "device_id": device_id,
                    "client_version": "1.0.0"
                }
            }
            await ws.send(json.dumps(auth_msg))
            
            # Wait for auth response
            response = await ws.recv()
            data = json.loads(response)
            
            if data.get("type") == "auth_ok":
                session_id = data["payload"]["session_id"]
                results.add_result("WebSocket SSO Auth", True, f"Authenticated, session_id={session_id}")
                return session_id
            elif data.get("type") == "auth_fail":
                results.add_result("WebSocket SSO Auth", False, f"Auth failed: {data['payload']['reason']}")
            else:
                results.add_result("WebSocket SSO Auth", False, f"Unexpected response: {data}")
                
    except Exception as e:
        results.add_result("WebSocket SSO Auth", False, f"Exception: {e}")
        
    return ""


async def test_sso_full_flow(results: TestResults):
    """Test 1: Complete SSO flow → WS auth → heartbeat → text input."""
    # Get SSO token
    sso_data = await test_mock_sso_login(results)
    if not sso_data:
        return
        
    token = sso_data["token"]
    
    try:
        async with websockets.connect(WS_URL) as ws:
            # Authenticate
            auth_msg = {
                "type": "auth", 
                "payload": {
                    "token": token,
                    "device_id": "dev001",
                    "client_version": "1.0.0"
                }
            }
            await ws.send(json.dumps(auth_msg))
            
            auth_response = await ws.recv()
            auth_data = json.loads(auth_response)
            
            if auth_data.get("type") != "auth_ok":
                results.add_result("SSO Full Flow", False, f"Auth failed: {auth_data}")
                return
                
            session_id = auth_data["payload"]["session_id"]
            
            # Send heartbeat
            heartbeat_msg = {
                "type": "heartbeat",
                "payload": {
                    "seq": 1,
                    "client_ts": datetime.now(timezone.utc).timestamp()
                }
            }
            await ws.send(json.dumps(heartbeat_msg))
            
            hb_response = await ws.recv()
            hb_data = json.loads(hb_response)
            
            if hb_data.get("type") != "heartbeat_ack":
                results.add_result("SSO Full Flow", False, f"Heartbeat failed: {hb_data}")
                return
                
            # Send text input → should get transcript_final + tts_audio
            text_msg = {
                "type": "text_input",
                "payload": {
                    "text": "Hello, this is a test message"
                }
            }
            await ws.send(json.dumps(text_msg))
            
            # Wait for responses
            received_transcript = False
            received_tts = False
            
            for _ in range(3):  # Wait for up to 3 messages
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(response)
                    
                    if data.get("type") == "transcript_final":
                        received_transcript = True
                    elif data.get("type") == "tts_audio":
                        received_tts = True
                        
                    if received_transcript and received_tts:
                        break
                except asyncio.TimeoutError:
                    break
                    
            if received_transcript and received_tts:
                results.add_result("SSO Full Flow (Mock IDP → WS auth → heartbeat → text input)", True, 
                                 "Complete flow working: transcript_final + tts_audio received")
            else:
                results.add_result("SSO Full Flow (Mock IDP → WS auth → heartbeat → text input)", False, 
                                 f"Incomplete flow: transcript={received_transcript}, tts={received_tts}")
                
    except Exception as e:
        results.add_result("SSO Full Flow (Mock IDP → WS auth → heartbeat → text input)", False, f"Exception: {e}")


async def test_suspended_token_flow(results: TestResults):
    """Test 2: SUSPENDED token → WS auth OK but execute blocked."""
    # First get a regular token and tenant ID
    sso_data = await test_mock_sso_login(results) 
    if not sso_data:
        results.add_result("Suspended Token Flow", False, "Could not get initial SSO token")
        return
        
    tenant_id = sso_data["myndlens_tenant_id"]
    
    # Suspend the tenant
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_BASE}/tenants/suspend", 
                                       headers={"X-OBEGEE-S2S-TOKEN": S2S_TOKEN},
                                       json={"tenant_id": tenant_id, "reason": "test"})
                                       
        if response.status_code != 200:
            results.add_result("Suspended Token Flow", False, f"Failed to suspend tenant: HTTP {response.status_code}")
            return
            
    except Exception as e:
        results.add_result("Suspended Token Flow", False, f"Failed to suspend tenant: {e}")
        return
    
    # Create a SUSPENDED SSO token manually
    suspended_token = create_manual_sso_token("testuser", tenant_id, "SUSPENDED")
    
    try:
        async with websockets.connect(WS_URL) as ws:
            # Authenticate with suspended token (should succeed)
            auth_msg = {
                "type": "auth",
                "payload": {
                    "token": suspended_token,
                    "device_id": "dev002",
                    "client_version": "1.0.0"
                }
            }
            await ws.send(json.dumps(auth_msg))
            
            auth_response = await ws.recv()
            auth_data = json.loads(auth_response)
            
            if auth_data.get("type") != "auth_ok":
                results.add_result("Suspended Token Flow", False, f"WS auth should succeed with SUSPENDED token: {auth_data}")
                return
                
            # Send heartbeat (should work)
            heartbeat_msg = {
                "type": "heartbeat", 
                "payload": {
                    "seq": 1,
                    "client_ts": datetime.now(timezone.utc).timestamp()
                }
            }
            await ws.send(json.dumps(heartbeat_msg))
            
            hb_response = await ws.recv()
            hb_data = json.loads(hb_response)
            
            if hb_data.get("type") != "heartbeat_ack":
                results.add_result("Suspended Token Flow", False, f"Heartbeat should work with SUSPENDED token: {hb_data}")
                return
                
            # Send execute_request (should be blocked with SUBSCRIPTION_INACTIVE)
            execute_msg = {
                "type": "execute_request",
                "payload": {
                    "draft_id": str(uuid.uuid4())
                }
            }
            await ws.send(json.dumps(execute_msg))
            
            exec_response = await ws.recv()
            exec_data = json.loads(exec_response)
            
            if (exec_data.get("type") == "execute_blocked" and 
                exec_data.get("payload", {}).get("code") == "SUBSCRIPTION_INACTIVE"):
                results.add_result("Suspended Token Flow (SUSPENDED token → WS auth OK → execute blocked)", True, 
                                 "Execute correctly blocked with SUBSCRIPTION_INACTIVE")
            else:
                results.add_result("Suspended Token Flow (SUSPENDED token → WS auth OK → execute blocked)", False, 
                                 f"Expected EXECUTE_BLOCKED/SUBSCRIPTION_INACTIVE, got: {exec_data}")
                
    except Exception as e:
        results.add_result("Suspended Token Flow (SUSPENDED token → WS auth OK → execute blocked)", False, f"Exception: {e}")


async def test_activate_idempotency(results: TestResults):
    """Test 3: Activate idempotency - same tenant_id returned on duplicate calls."""
    try:
        # First activation
        async with httpx.AsyncClient() as client:
            response1 = await client.post(f"{API_BASE}/tenants/activate",
                                        headers={"X-OBEGEE-S2S-TOKEN": S2S_TOKEN},
                                        json={"obegee_user_id": "idempotency_test_user"})
                                        
        if response1.status_code != 200:
            results.add_result("Activate Idempotency", False, f"First activation failed: HTTP {response1.status_code}")
            return
            
        data1 = response1.json()
        tenant_id1 = data1.get("tenant_id")
        
        # Second activation (should return same tenant_id)
        async with httpx.AsyncClient() as client:
            response2 = await client.post(f"{API_BASE}/tenants/activate",
                                        headers={"X-OBEGEE-S2S-TOKEN": S2S_TOKEN}, 
                                        json={"obegee_user_id": "idempotency_test_user"})
                                        
        if response2.status_code != 200:
            results.add_result("Activate Idempotency", False, f"Second activation failed: HTTP {response2.status_code}")
            return
            
        data2 = response2.json()
        tenant_id2 = data2.get("tenant_id")
        
        if tenant_id1 and tenant_id2 and tenant_id1 == tenant_id2:
            results.add_result("Activate Idempotency", True, f"Same tenant_id returned: {tenant_id1}")
        else:
            results.add_result("Activate Idempotency", False, f"Different tenant_ids: {tenant_id1} vs {tenant_id2}")
            
    except Exception as e:
        results.add_result("Activate Idempotency", False, f"Exception: {e}")


async def test_s2s_auth_enforcement(results: TestResults):
    """Test 4: Tenant S2S auth enforcement."""
    
    # Test without S2S header
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_BASE}/tenants/activate",
                                       json={"obegee_user_id": "test_no_auth"})
                                       
        if response.status_code == 403:
            results.add_result("S2S Auth - No Header", True, "Correctly rejected without S2S token")
        else:
            results.add_result("S2S Auth - No Header", False, f"Should return 403, got {response.status_code}")
    except Exception as e:
        results.add_result("S2S Auth - No Header", False, f"Exception: {e}")
        
    # Test with wrong S2S token
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_BASE}/tenants/activate",
                                       headers={"X-OBEGEE-S2S-TOKEN": "wrong-token"},
                                       json={"obegee_user_id": "test_wrong_auth"})
                                       
        if response.status_code == 403:
            results.add_result("S2S Auth - Wrong Token", True, "Correctly rejected with wrong S2S token")
        else:
            results.add_result("S2S Auth - Wrong Token", False, f"Should return 403, got {response.status_code}")
    except Exception as e:
        results.add_result("S2S Auth - Wrong Token", False, f"Exception: {e}")


async def test_sso_token_validation(results: TestResults):
    """Test 5: SSO token validation edge cases."""
    
    # Wrong issuer
    wrong_iss_token = jwt.encode({
        "iss": "wrong_issuer",
        "aud": "myndlens", 
        "obegee_user_id": "test",
        "myndlens_tenant_id": str(uuid.uuid4()),
        "subscription_status": "ACTIVE",
        "iat": datetime.now(timezone.utc).timestamp(),
        "exp": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp(),
    }, OBEGEE_SSO_SECRET, algorithm="HS256")
    
    # Wrong audience  
    wrong_aud_token = jwt.encode({
        "iss": "obegee",
        "aud": "wrong_audience",
        "obegee_user_id": "test", 
        "myndlens_tenant_id": str(uuid.uuid4()),
        "subscription_status": "ACTIVE",
        "iat": datetime.now(timezone.utc).timestamp(),
        "exp": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp(),
    }, OBEGEE_SSO_SECRET, algorithm="HS256")
    
    # Expired token
    expired_token = jwt.encode({
        "iss": "obegee",
        "aud": "myndlens",
        "obegee_user_id": "test",
        "myndlens_tenant_id": str(uuid.uuid4()), 
        "subscription_status": "ACTIVE",
        "iat": (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp(),
        "exp": (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp(),
    }, OBEGEE_SSO_SECRET, algorithm="HS256")
    
    # Missing required claims
    missing_claims_token = jwt.encode({
        "iss": "obegee",
        "aud": "myndlens",
        "obegee_user_id": "test",
        # Missing myndlens_tenant_id and subscription_status
        "iat": datetime.now(timezone.utc).timestamp(),
        "exp": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp(),
    }, OBEGEE_SSO_SECRET, algorithm="HS256")
    
    test_cases = [
        ("Wrong Issuer", wrong_iss_token),
        ("Wrong Audience", wrong_aud_token), 
        ("Expired Token", expired_token),
        ("Missing Claims", missing_claims_token)
    ]
    
    for test_name, token in test_cases:
        try:
            async with websockets.connect(WS_URL) as ws:
                auth_msg = {
                    "type": "auth",
                    "payload": {
                        "token": token,
                        "device_id": "test_device",
                        "client_version": "1.0.0"
                    }
                }
                await ws.send(json.dumps(auth_msg))
                
                response = await ws.recv()
                data = json.loads(response)
                
                if data.get("type") == "auth_fail":
                    results.add_result(f"SSO Validation - {test_name}", True, "Correctly rejected invalid token")
                else:
                    results.add_result(f"SSO Validation - {test_name}", False, f"Should reject token, got: {data}")
                    
        except Exception as e:
            results.add_result(f"SSO Validation - {test_name}", False, f"Exception: {e}")


async def test_legacy_auth_regression(results: TestResults):
    """Test 6: REGRESSION - Legacy auth/pair still works."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_BASE}/auth/pair", json={
                "user_id": "regression_test_user",
                "device_id": "regression_device",
                "client_version": "1.0.0"
            })
            
        if response.status_code == 200:
            data = response.json()
            token = data.get("token")
            
            if token:
                # Test WS auth with legacy token
                session_id = await test_ws_auth_with_sso_token(results, token, "regression_device")
                if session_id:
                    results.add_result("Legacy Auth Regression", True, "Legacy /auth/pair still works")
                else:
                    results.add_result("Legacy Auth Regression", False, "Legacy token WS auth failed")
            else:
                results.add_result("Legacy Auth Regression", False, "No token in legacy auth response")
        else:
            results.add_result("Legacy Auth Regression", False, f"Legacy auth failed: HTTP {response.status_code}")
            
    except Exception as e:
        results.add_result("Legacy Auth Regression", False, f"Exception: {e}")


async def test_presence_gate_regression(results: TestResults):
    """Test 6: REGRESSION - Presence gate (16s stale) still blocks execution."""
    # Get a valid SSO token first
    sso_data = await test_mock_sso_login(results)
    if not sso_data:
        results.add_result("Presence Gate Regression", False, "Could not get SSO token")
        return
        
    token = sso_data["token"]
    
    try:
        async with websockets.connect(WS_URL) as ws:
            # Authenticate
            auth_msg = {
                "type": "auth",
                "payload": {
                    "token": token,
                    "device_id": "presence_test",
                    "client_version": "1.0.0"
                }
            }
            await ws.send(json.dumps(auth_msg))
            
            auth_response = await ws.recv()
            auth_data = json.loads(auth_response)
            
            if auth_data.get("type") != "auth_ok":
                results.add_result("Presence Gate Regression", False, f"Auth failed: {auth_data}")
                return
                
            # Send one heartbeat, then wait 16+ seconds before execute
            heartbeat_msg = {
                "type": "heartbeat",
                "payload": {
                    "seq": 1,
                    "client_ts": datetime.now(timezone.utc).timestamp()
                }
            }
            await ws.send(json.dumps(heartbeat_msg))
            await ws.recv()  # heartbeat_ack
            
            # Wait 16 seconds (presence timeout is 15s)
            print("⏱️  Waiting 16 seconds for presence to go stale...")
            await asyncio.sleep(16)
            
            # Send execute_request (should be blocked with PRESENCE_STALE)
            execute_msg = {
                "type": "execute_request",
                "payload": {
                    "draft_id": str(uuid.uuid4())
                }
            }
            await ws.send(json.dumps(execute_msg))
            
            exec_response = await ws.recv()
            exec_data = json.loads(exec_response)
            
            if (exec_data.get("type") == "execute_blocked" and 
                exec_data.get("payload", {}).get("code") == "PRESENCE_STALE"):
                results.add_result("Presence Gate Regression (16s stale)", True, 
                                 "Execute correctly blocked after 16s stale heartbeat")
            else:
                results.add_result("Presence Gate Regression (16s stale)", False, 
                                 f"Expected EXECUTE_BLOCKED/PRESENCE_STALE, got: {exec_data}")
                
    except Exception as e:
        results.add_result("Presence Gate Regression (16s stale)", False, f"Exception: {e}")


async def main():
    """Run all SSO Consumer + Tenant Activation tests."""
    print("🚀 MyndLens SSO Consumer + Tenant Activation Test Suite")
    print("=" * 60)
    
    results = TestResults()
    
    # Basic health check
    await test_health_endpoint(results)
    
    # CRITICAL TEST GATES from review request
    print("\n🔥 CRITICAL SSO + TENANT TEST GATES:")
    
    # Gate 1: Mock SSO Login → WS auth → heartbeat → draft flows
    await test_sso_full_flow(results)
    
    # Gate 2: SUSPENDED token → WS auth OK but execute blocked  
    await test_suspended_token_flow(results)
    
    # Gate 3: Activate idempotency
    await test_activate_idempotency(results)
    
    # Gate 4: Tenant S2S auth enforcement
    await test_s2s_auth_enforcement(results)
    
    # Gate 5: SSO token validation edge cases
    await test_sso_token_validation(results)
    
    # Gate 6: REGRESSION tests
    print("\n🔄 REGRESSION TESTS:")
    await test_legacy_auth_regression(results) 
    await test_presence_gate_regression(results)
    
    # Summary
    success = results.summary()
    
    if success:
        print("\n🎉 ALL SSO + TENANT ACTIVATION TESTS PASSED!")
        print("✅ MyndLens SSO Consumer integration is working correctly")
        print("✅ Tenant lifecycle management is functional")  
        print("✅ All security gates and validation working")
        print("✅ Regression tests pass - existing functionality intact")
    else:
        print("\n❌ SOME TESTS FAILED - See details above")
        
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)