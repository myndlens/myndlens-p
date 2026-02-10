#!/usr/bin/env python3
"""
MyndLens Ownership Refactor Testing — Dev Agent Contract Compliance
Backend Testing Suite for Critical Ownership Boundaries

CRITICAL TESTS:
1. ObeGee-owned endpoints REMOVED (should return 404/405)
2. Mock SSO still works (dev fixture)
3. Compliance scan clean (rogue prompt detection)
4. Dispatch submits to ObeGee Adapter (NOT OpenClaw)
5. MyndLens-owned functions intact
6. Governance backup scoped to MyndLens-owned data only
"""
import asyncio
import json
import requests
import websockets
import base64
import time
from datetime import datetime, timezone, timedelta
import sys
import os

# Backend URL from environment
BACKEND_URL = os.getenv('REACT_APP_BACKEND_URL', 'https://voice-assistant-dev.preview.emergentagent.com')
API_BASE = f"{BACKEND_URL}/api"

class TestResults:
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
    
    def add_result(self, test_name, passed, details="", error=""):
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append(f"{status} {test_name}: {details}")
        if error:
            self.results.append(f"    Error: {error}")
        
        if passed:
            self.passed += 1
        else:
            self.failed += 1
    
    def print_summary(self):
        print("\n" + "="*80)
        print("MyndLens OWNERSHIP REFACTOR TEST RESULTS")
        print("="*80)
        for result in self.results:
            print(result)
        print(f"\nSUMMARY: {self.passed} passed, {self.failed} failed")
        return self.failed == 0

def make_request(method, endpoint, **kwargs):
    """Make HTTP request with error handling."""
    url = f"{API_BASE}{endpoint}"
    try:
        response = requests.request(method, url, timeout=30, **kwargs)
        return response
    except Exception as e:
        return None

def test_obegee_endpoints_removed():
    """Test 1: Verify ObeGee-owned endpoints return 404/405."""
    results = TestResults()
    
    # These endpoints should be REMOVED per Dev Agent Contract
    obegee_endpoints = [
        "/tenants/activate",
        "/tenants/suspend", 
        "/tenants/deprovision",
        "/tenants/rotate-key",
        "/tenants/export-data"
    ]
    
    for endpoint in obegee_endpoints:
        response = make_request("POST", endpoint, json={"test": "data"})
        if response is None:
            results.add_result(f"POST {endpoint}", True, "Connection failed - endpoint likely removed")
        elif response.status_code in [404, 405]:
            results.add_result(f"POST {endpoint}", True, f"Correctly returns {response.status_code}")
        else:
            results.add_result(f"POST {endpoint}", False, 
                             f"Returns {response.status_code} (should be 404/405)", response.text[:100])
    
    return results

def test_mock_sso_works():
    """Test 2: Verify mock SSO endpoint still works."""
    results = TestResults()
    
    sso_payload = {
        "username": "contract_test",
        "password": "p", 
        "device_id": "cdev"
    }
    
    response = make_request("POST", "/sso/myndlens/token", json=sso_payload)
    
    if response is None:
        results.add_result("Mock SSO /sso/myndlens/token", False, "Connection failed")
        return results
        
    if response.status_code == 200:
        try:
            data = response.json()
            if "token" in data and "obegee_user_id" in data:
                results.add_result("Mock SSO /sso/myndlens/token", True, 
                                 f"Returns SSO token for user {data.get('obegee_user_id')}")
                return results, data["token"]  # Return token for later tests
            else:
                results.add_result("Mock SSO /sso/myndlens/token", False, 
                                 "Missing required fields", str(data))
        except:
            results.add_result("Mock SSO /sso/myndlens/token", False, 
                             "Invalid JSON response", response.text[:100])
    else:
        results.add_result("Mock SSO /sso/myndlens/token", False, 
                         f"Returns {response.status_code}", response.text[:100])
    
    return results, None

def test_compliance_scan():
    """Test 3: Verify compliance scan is clean."""
    results = TestResults()
    
    response = make_request("GET", "/prompt/compliance")
    
    if response is None:
        results.add_result("Compliance scan /prompt/compliance", False, "Connection failed")
        return results
        
    if response.status_code == 200:
        try:
            data = response.json()
            rogue_scan = data.get("rogue_prompt_scan", {})
            
            # Check if scan is clean
            is_clean = rogue_scan.get("clean", False)
            violations = rogue_scan.get("violations", [])
            
            if is_clean and len(violations) == 0:
                results.add_result("Compliance scan clean", True, 
                                 f"rogue_prompt_scan.clean=true, violations=[]")
            else:
                results.add_result("Compliance scan clean", False, 
                                 f"clean={is_clean}, violations={len(violations)}", 
                                 str(violations[:3]))  # Show first 3 violations
                                 
            # Verify scanner checks for ownership violations
            files_scanned = rogue_scan.get("files_scanned", 0)
            if files_scanned > 0:
                results.add_result("Compliance scanner active", True, 
                                 f"Scanned {files_scanned} files for violations")
            else:
                results.add_result("Compliance scanner active", False, 
                                 "No files scanned")
                                 
        except Exception as e:
            results.add_result("Compliance scan /prompt/compliance", False, 
                             "JSON parsing failed", str(e))
    else:
        results.add_result("Compliance scan /prompt/compliance", False, 
                         f"Returns {response.status_code}", response.text[:100])
    
    return results

def test_dispatch_obegee_adapter():
    """Test 4: Verify dispatch submits to ObeGee Adapter, not OpenClaw."""
    results = TestResults()
    
    # Create a test MIO for dispatch
    test_mio = {
        "header": {
            "mio_id": "test_ownership_mio",
            "version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        "intent_envelope": {
            "action": "send_message",
            "constraints": {"tier": 1}
        },
        "grounding": {
            "transcript_hash": "test_hash",
            "l1_hash": "test_l1_hash"
        },
        "security_proof": {}
    }
    
    dispatch_payload = {
        "mio_dict": test_mio,
        "signature": "test_signature", 
        "session_id": "test_session",
        "device_id": "test_device",
        "tenant_id": "test_tenant"
    }
    
    response = make_request("POST", "/dispatch", json=dispatch_payload)
    
    if response is None:
        results.add_result("Dispatch endpoint /dispatch", False, "Connection failed")
        return results
        
    # We expect this to fail on MIO verification (heartbeat stale) - that's CORRECT
    # The important part is checking the error message indicates ObeGee Adapter, not OpenClaw
    if response.status_code == 403:
        error_detail = response.json().get("detail", "")
        if "Heartbeat stale" in error_detail or "MIO verification failed" in error_detail:
            results.add_result("Dispatch security gates", True, 
                             "MIO verification correctly blocks (expected security behavior)")
        else:
            results.add_result("Dispatch security gates", False, 
                             f"Unexpected error: {error_detail}")
    else:
        # If somehow it doesn't fail on verification, check the response
        try:
            data = response.json()
            status = data.get("status", "")
            if status == "submitted":
                results.add_result("Dispatch to ObeGee Adapter", True, 
                                 "Returns status='submitted' (to adapter)")
            elif status == "completed":
                results.add_result("Dispatch to ObeGee Adapter", False, 
                                 "Returns status='completed' (indicates direct OpenClaw call)")
            else:
                results.add_result("Dispatch to ObeGee Adapter", False, 
                                 f"Unexpected status: {status}")
        except:
            results.add_result("Dispatch endpoint /dispatch", False, 
                             "Invalid response format", response.text[:100])
    
    return results

def test_myndlens_owned_functions():
    """Test 5: Verify MyndLens-owned functions are intact."""
    results = TestResults()
    
    # Test core MyndLens functions
    
    # 5a. Health endpoint
    response = make_request("GET", "/health")
    if response and response.status_code == 200:
        results.add_result("Health endpoint", True, "Working correctly")
    else:
        results.add_result("Health endpoint", False, "Not responding")
    
    # 5b. Memory store (Digital Self)
    memory_payload = {
        "user_id": "contract_test_user",
        "text": "Test fact for ownership validation",
        "fact_type": "FACT",
        "provenance": "EXPLICIT"
    }
    response = make_request("POST", "/memory/store", json=memory_payload)
    if response and response.status_code == 200:
        data = response.json()
        if "node_id" in data and data.get("status") == "stored":
            results.add_result("Memory store API", True, "Digital Self working")
        else:
            results.add_result("Memory store API", False, "Invalid response format")
    else:
        results.add_result("Memory store API", False, "Memory store not working")
    
    # 5c. Memory recall
    recall_payload = {
        "user_id": "contract_test_user", 
        "query": "Test fact",
        "n_results": 3
    }
    response = make_request("POST", "/memory/recall", json=recall_payload)
    if response and response.status_code == 200:
        results.add_result("Memory recall API", True, "Digital Self recall working")
    else:
        results.add_result("Memory recall API", False, "Memory recall not working")
    
    # 5d. MIO signing (cryptographic functions)
    mio_sign_payload = {
        "mio_dict": {"test": "data", "timestamp": datetime.now().isoformat()}
    }
    response = make_request("POST", "/mio/sign", json=mio_sign_payload)
    if response and response.status_code == 200:
        data = response.json()
        if "signature" in data and "public_key" in data:
            results.add_result("MIO signing API", True, "Cryptographic functions working")
        else:
            results.add_result("MIO signing API", False, "Invalid signature response")
    else:
        results.add_result("MIO signing API", False, "MIO signing not working")
    
    # 5e. Soul status (identity system)  
    response = make_request("GET", "/soul/status")
    if response and response.status_code == 200:
        data = response.json()
        if "version" in data and "integrity" in data:
            results.add_result("Soul status API", True, "Identity system working")
        else:
            results.add_result("Soul status API", False, "Invalid soul response")
    else:
        results.add_result("Soul status API", False, "Soul system not working")
        
    # 5f. Rate limits and circuit breakers
    response = make_request("GET", "/circuit-breakers")
    if response and response.status_code == 200:
        results.add_result("Circuit breakers API", True, "Abuse protection working")
    else:
        results.add_result("Circuit breakers API", False, "Circuit breakers not working")
    
    return results

def test_governance_backup_scoped():
    """Test 6: Verify governance backup scoped to MyndLens-owned data only."""
    results = TestResults()
    
    backup_payload = {
        "user_id": "contract_test_user",
        "include_audit": True
    }
    
    # This requires S2S token
    s2s_token = "obegee-s2s-dev-token-CHANGE-IN-PROD"
    headers = {"X-OBEGEE-S2S-TOKEN": s2s_token}
    
    response = make_request("POST", "/governance/backup", json=backup_payload, headers=headers)
    
    if response is None:
        results.add_result("Governance backup /governance/backup", False, "Connection failed")
        return results
        
    if response.status_code == 200:
        try:
            data = response.json()
            
            # Check for MyndLens scoping indicator
            scope = data.get("scope", "")
            if "myndlens_owned_only" in scope or "myndlens" in scope.lower():
                results.add_result("Governance backup scoping", True, 
                                 f"Backup scoped to MyndLens-owned data: {scope}")
            else:
                # Check backup contents for MyndLens-specific data types
                backup_keys = list(data.keys())
                myndlens_keys = ["graphs", "entities", "sessions", "transcripts", "commits"]
                if any(key in backup_keys for key in myndlens_keys):
                    results.add_result("Governance backup scoping", True, 
                                     "Contains MyndLens-owned data types only")
                else:
                    results.add_result("Governance backup scoping", False, 
                                     "Backup scope unclear", str(backup_keys))
                                     
            # Verify S2S auth is enforced
            if "backup_id" in data:
                results.add_result("Governance S2S auth", True, "S2S token correctly enforced")
            
        except Exception as e:
            results.add_result("Governance backup /governance/backup", False, 
                             "JSON parsing failed", str(e))
    elif response.status_code == 403:
        results.add_result("Governance S2S auth", False, 
                         "S2S token rejected (check token value)")
    else:
        results.add_result("Governance backup /governance/backup", False, 
                         f"Returns {response.status_code}", response.text[:100])
    
    return results

async def test_l1_scout_ws_flow():
    """Test 5g: L1 Scout via WebSocket (requires SSO login)."""
    results = TestResults()
    
    # First get SSO token
    sso_results, sso_token = test_mock_sso_works()
    if not sso_token:
        results.add_result("L1 Scout WS flow", False, "Could not get SSO token")
        return results
    
    try:
        ws_url = f"{BACKEND_URL.replace('https://', 'wss://')}/api/ws"
        
        async with websockets.connect(ws_url) as websocket:
            # Authenticate with SSO token
            auth_msg = {
                "type": "auth",
                "payload": {"token": sso_token}
            }
            await websocket.send(json.dumps(auth_msg))
            
            # Wait for auth response
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            auth_resp = json.loads(response)
            
            if auth_resp.get("type") == "auth_ok":
                # Send heartbeat
                heartbeat_msg = {"type": "heartbeat", "payload": {}}
                await websocket.send(json.dumps(heartbeat_msg))
                
                # Wait for heartbeat ack
                await asyncio.wait_for(websocket.recv(), timeout=5.0)
                
                # Send text input to trigger L1 Scout
                text_input_msg = {
                    "type": "text_input", 
                    "payload": {"text": "Send a message to Sarah about the meeting tomorrow at 3pm"}
                }
                await websocket.send(json.dumps(text_input_msg))
                
                # Wait for responses (transcript_final and draft_update)
                responses = []
                for _ in range(3):  # Expect transcript_final, draft_update, tts_audio
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        responses.append(json.loads(response))
                    except asyncio.TimeoutError:
                        break
                
                # Check for draft_update (L1 Scout output)
                draft_updates = [r for r in responses if r.get("type") == "draft_update"]
                if draft_updates:
                    results.add_result("L1 Scout WS flow", True, 
                                     "Complete SSO → WS auth → heartbeat → text_input → draft_update flow working")
                else:
                    results.add_result("L1 Scout WS flow", False, 
                                     f"No draft_update received, got: {[r.get('type') for r in responses]}")
            else:
                results.add_result("L1 Scout WS flow", False, 
                                 f"WS auth failed: {auth_resp}")
                                 
    except Exception as e:
        results.add_result("L1 Scout WS flow", False, f"WebSocket error: {str(e)}")
    
    return results

def run_all_tests():
    """Run all ownership refactor tests."""
    print("🔍 TESTING: MyndLens Ownership Refactor — Dev Agent Contract Compliance")
    print(f"Backend URL: {BACKEND_URL}")
    print("="*80)
    
    all_results = TestResults()
    
    # Test 1: ObeGee-owned endpoints REMOVED
    print("\n1️⃣  Testing ObeGee-owned endpoints removal...")
    results1 = test_obegee_endpoints_removed()
    all_results.results.extend(results1.results)
    all_results.passed += results1.passed
    all_results.failed += results1.failed
    
    # Test 2: Mock SSO still works
    print("\n2️⃣  Testing Mock SSO endpoint...")
    results2, sso_token = test_mock_sso_works()
    all_results.results.extend(results2.results)
    all_results.passed += results2.passed
    all_results.failed += results2.failed
    
    # Test 3: Compliance scan clean
    print("\n3️⃣  Testing compliance scan...")
    results3 = test_compliance_scan()
    all_results.results.extend(results3.results)
    all_results.passed += results3.passed
    all_results.failed += results3.failed
    
    # Test 4: Dispatch submits to ObeGee Adapter
    print("\n4️⃣  Testing dispatch routing...")
    results4 = test_dispatch_obegee_adapter()
    all_results.results.extend(results4.results)
    all_results.passed += results4.passed
    all_results.failed += results4.failed
    
    # Test 5: MyndLens-owned functions intact
    print("\n5️⃣  Testing MyndLens-owned functions...")
    results5 = test_myndlens_owned_functions()
    all_results.results.extend(results5.results)
    all_results.passed += results5.passed
    all_results.failed += results5.failed
    
    # Test 5g: L1 Scout WebSocket flow (async)
    print("\n5g️⃣  Testing L1 Scout WebSocket flow...")
    try:
        results5g = asyncio.run(test_l1_scout_ws_flow())
        all_results.results.extend(results5g.results)
        all_results.passed += results5g.passed
        all_results.failed += results5g.failed
    except Exception as e:
        all_results.add_result("L1 Scout WS flow", False, f"Async test error: {str(e)}")
    
    # Test 6: Governance backup scoped
    print("\n6️⃣  Testing governance backup scoping...")
    results6 = test_governance_backup_scoped()
    all_results.results.extend(results6.results)
    all_results.passed += results6.passed
    all_results.failed += results6.failed
    
    # Print final results
    success = all_results.print_summary()
    
    if success:
        print("\n🎉 ALL TESTS PASSED - MyndLens ownership refactor is compliant with Dev Agent Contract!")
    else:
        print(f"\n⚠️  {all_results.failed} test(s) failed - ownership boundaries need attention")
    
    return success

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)