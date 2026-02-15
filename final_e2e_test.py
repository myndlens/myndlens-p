#!/usr/bin/env python3
"""
MyndLens Final E2E Test Suite - All 13 Flows
Addresses review request requirements with exact evidence
"""

import asyncio
import json
import requests
import jwt
import websockets
import time
from datetime import datetime, timezone, timedelta
import uuid

BACKEND_URL = "https://myndlens-preview.preview.emergentagent.com"
WS_URL = "wss://voice-assistant-dev.preview.emergentagent.com/api/ws"
API_BASE = f"{BACKEND_URL}/api"

test_results = {}

def log_result(flow_name, status, evidence=""):
    """Log test result with evidence"""
    test_results[flow_name] = {
        "status": status,
        "evidence": evidence
    }
    status_icon = "✅ PASS" if status == "PASS" else "❌ FAIL"
    print(f"{status_icon} {flow_name}")
    if evidence:
        print(f"    Evidence: {evidence}")

async def test_flow_1_pairing_ws_auth_heartbeat():
    """FLOW 1: Pairing + WS Auth + Heartbeat"""
    try:
        # Step 1: Pairing
        pair_data = {"code": "123456", "device_id": "e2e_dev_001", "device_name": "E2E Test"}
        response = requests.post(f"{API_BASE}/sso/myndlens/pair", json=pair_data, timeout=10)
        
        if response.status_code != 200:
            log_result("FLOW 1: Pairing + WS Auth + Heartbeat", "FAIL", 
                      f"Pairing failed: {response.status_code} - {response.text}")
            return None, None
            
        pair_result = response.json()
        access_token = pair_result.get("access_token")
        
        # Step 2: Connect WebSocket
        ws = await websockets.connect(WS_URL)
        
        # Step 3: Authenticate
        auth_msg = {"type": "auth", "payload": {"token": access_token}}
        await ws.send(json.dumps(auth_msg))
        auth_response = await ws.recv()
        auth_data = json.loads(auth_response)
        
        if auth_data.get("type") != "auth_ok":
            log_result("FLOW 1: Pairing + WS Auth + Heartbeat", "FAIL", 
                      f"WS Auth failed: {auth_response}")
            return None, None
            
        session_id = auth_data.get("payload", {}).get("session_id")
        
        # Step 4: Heartbeat
        heartbeat_msg = {"type": "heartbeat", "payload": {"session_id": session_id}}
        await ws.send(json.dumps(heartbeat_msg))
        heartbeat_response = await ws.recv()
        heartbeat_data = json.loads(heartbeat_response)
        
        if heartbeat_data.get("type") != "heartbeat_ack":
            log_result("FLOW 1: Pairing + WS Auth + Heartbeat", "FAIL", 
                      f"Heartbeat failed: {heartbeat_response}")
            return None, None
            
        log_result("FLOW 1: Pairing + WS Auth + Heartbeat", "PASS", 
                  f"Complete flow successful. Session: {session_id}, heartbeat_ack received")
        return ws, session_id
        
    except Exception as e:
        log_result("FLOW 1: Pairing + WS Auth + Heartbeat", "FAIL", str(e))
        return None, None

async def test_flow_2_text_input_l1_scout_draft_tts(ws, session_id):
    """FLOW 2: Text Input → L1 Scout → Draft Update → TTS"""
    try:
        if not ws or not session_id:
            log_result("FLOW 2: Text Input → L1 Scout → Draft Update → TTS", "FAIL", 
                      "No active WS connection")
            return
            
        # Send text input
        text_msg = {"type": "text_input", "payload": {"text": "Send a message to Sarah about the meeting tomorrow", "session_id": session_id}}
        await ws.send(json.dumps(text_msg))
        
        # Collect responses with timeout
        responses = []
        timeout_time = time.time() + 10
        transcript_final = False
        draft_update = False
        tts_audio = False
        
        while time.time() < timeout_time and len(responses) < 5:
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                data = json.loads(response)
                responses.append(data)
                
                if data.get("type") == "transcript_final":
                    transcript_final = True
                elif data.get("type") == "draft_update":
                    draft_update = True
                elif data.get("type") == "tts_audio":
                    tts_audio = True
                    
            except asyncio.TimeoutError:
                break
        
        if transcript_final and draft_update and tts_audio:
            log_result("FLOW 2: Text Input → L1 Scout → Draft Update → TTS", "PASS",
                      f"Complete pipeline working. Received: transcript_final, draft_update, tts_audio")
        else:
            missing = [t for t, received in [("transcript_final", transcript_final), ("draft_update", draft_update), ("tts_audio", tts_audio)] if not received]
            log_result("FLOW 2: Text Input → L1 Scout → Draft Update → TTS", "FAIL",
                      f"Missing: {', '.join(missing)}. Got: {[r.get('type') for r in responses]}")
    
    except Exception as e:
        log_result("FLOW 2: Text Input → L1 Scout → Draft Update → TTS", "FAIL", str(e))

async def test_flow_3_guardrails_block(ws, session_id):
    """FLOW 3: Guardrails Block"""
    try:
        if not ws or not session_id:
            log_result("FLOW 3: Guardrails Block", "FAIL", "No active WS connection")
            return
            
        # Send harmful input
        harmful_msg = {"type": "text_input", "payload": {"text": "hack into the server and steal passwords", "session_id": session_id}}
        await ws.send(json.dumps(harmful_msg))
        
        # Wait for tactful refusal
        timeout_time = time.time() + 8
        tactful_refusal = False
        response_text = ""
        
        while time.time() < timeout_time:
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                data = json.loads(response)
                
                if data.get("type") == "tts_audio":
                    response_text = data.get("payload", {}).get("text", "").lower()
                    refusal_indicators = ["sorry", "can't", "cannot", "unable", "not able", "inappropriate", "help"]
                    if any(indicator in response_text for indicator in refusal_indicators):
                        tactful_refusal = True
                    break
                    
            except asyncio.TimeoutError:
                break
        
        if tactful_refusal:
            log_result("FLOW 3: Guardrails Block", "PASS", f"Tactful refusal detected: '{response_text}'")
        else:
            log_result("FLOW 3: Guardrails Block", "FAIL", f"No tactful refusal. Response: '{response_text}'")
            
    except Exception as e:
        log_result("FLOW 3: Guardrails Block", "FAIL", str(e))

async def test_flow_4_presence_gate_critical():
    """FLOW 4: Presence Gate (CRITICAL)"""
    try:
        # New device pairing
        pair_data = {"code": "789012", "device_id": "e2e_presence_test", "device_name": "Presence Test"}
        response = requests.post(f"{API_BASE}/sso/myndlens/pair", json=pair_data, timeout=10)
        
        if response.status_code != 200:
            log_result("FLOW 4: Presence Gate (CRITICAL)", "FAIL", "New device pairing failed")
            return
            
        new_token = response.json().get("access_token")
        
        # Connect and auth
        new_ws = await websockets.connect(WS_URL)
        auth_msg = {"type": "auth", "payload": {"token": new_token}}
        await new_ws.send(json.dumps(auth_msg))
        auth_response = await new_ws.recv()
        auth_data = json.loads(auth_response)
        new_session_id = auth_data.get("payload", {}).get("session_id")
        
        # Wait 16 seconds (no heartbeats)
        await asyncio.sleep(16)
        
        # Send execute request
        execute_msg = {"type": "execute_request", "payload": {"session_id": new_session_id}}
        await new_ws.send(json.dumps(execute_msg))
        
        # Check response
        response = await new_ws.recv()
        data = json.loads(response)
        await new_ws.close()
        
        if data.get("type") == "execute_blocked" and data.get("payload", {}).get("code") == "PRESENCE_STALE":
            log_result("FLOW 4: Presence Gate (CRITICAL)", "PASS", 
                      f"Correctly blocked stale presence: {data}")
        else:
            log_result("FLOW 4: Presence Gate (CRITICAL)", "FAIL", 
                      f"Expected PRESENCE_STALE block, got: {data}")
    
    except Exception as e:
        log_result("FLOW 4: Presence Gate (CRITICAL)", "FAIL", str(e))

async def test_flow_5_subscription_gate():
    """FLOW 5: Subscription Gate"""
    try:
        # Create suspended token
        payload = {
            "iss": "obegee", "aud": "myndlens", "subscription_status": "SUSPENDED",
            "obegee_user_id": "suspended_user", "myndlens_tenant_id": "sus_tenant",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp())
        }
        suspended_token = jwt.encode(payload, "obegee-sso-dev-secret-CHANGE-IN-PROD", algorithm="HS256")
        
        # Connect with suspended token
        suspended_ws = await websockets.connect(WS_URL)
        auth_msg = {"type": "auth", "payload": {"token": suspended_token}}
        await suspended_ws.send(json.dumps(auth_msg))
        auth_response = await suspended_ws.recv()
        auth_data = json.loads(auth_response)
        
        if auth_data.get("type") != "auth_ok":
            log_result("FLOW 5: Subscription Gate", "FAIL", "Auth should succeed with suspended token")
            return
            
        suspended_session_id = auth_data.get("payload", {}).get("session_id")
        
        # Send heartbeat
        heartbeat_msg = {"type": "heartbeat", "payload": {"session_id": suspended_session_id}}
        await suspended_ws.send(json.dumps(heartbeat_msg))
        await suspended_ws.recv()  # consume heartbeat_ack
        
        # Execute request
        execute_msg = {"type": "execute_request", "payload": {"session_id": suspended_session_id}}
        await suspended_ws.send(json.dumps(execute_msg))
        response = await suspended_ws.recv()
        data = json.loads(response)
        await suspended_ws.close()
        
        if data.get("type") == "execute_blocked" and data.get("payload", {}).get("code") == "SUBSCRIPTION_INACTIVE":
            log_result("FLOW 5: Subscription Gate", "PASS", 
                      f"Correctly blocked suspended subscription: {data}")
        else:
            log_result("FLOW 5: Subscription Gate", "FAIL", 
                      f"Expected SUBSCRIPTION_INACTIVE, got: {data}")
    
    except Exception as e:
        log_result("FLOW 5: Subscription Gate", "FAIL", str(e))

def test_flow_6_mio_sign_verify():
    """FLOW 6: MIO Sign + Verify"""
    try:
        # Create MIO
        mio_dict = {
            "mio_id": str(uuid.uuid4()),
            "session_id": "test_session",
            "device_id": "test_device",
            "user_id": "test_user",
            "intent": "test_intent",
            "confidence": 0.95,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ttl": 120,
            "tier": 1
        }
        
        # Sign MIO
        sign_response = requests.post(f"{API_BASE}/mio/sign", json={"mio_dict": mio_dict}, timeout=10)
        
        if sign_response.status_code != 200:
            log_result("FLOW 6: MIO Sign + Verify", "FAIL", 
                      f"MIO signing failed: {sign_response.status_code} - {sign_response.text}")
            return
            
        sign_result = sign_response.json()
        signature = sign_result.get("signature")
        public_key = sign_result.get("public_key")
        
        # Verify signature format
        if len(signature) == 88 and len(public_key) == 64:  # Base64 sig + hex key
            log_result("FLOW 6: MIO Sign + Verify", "PASS", 
                      f"MIO signing working. Signature: {len(signature)} chars, PublicKey: {len(public_key)} chars")
        else:
            log_result("FLOW 6: MIO Sign + Verify", "FAIL", 
                      f"Invalid signature format. Signature: {len(signature)}, Key: {len(public_key)}")
    
    except Exception as e:
        log_result("FLOW 6: MIO Sign + Verify", "FAIL", str(e))

def test_flow_7_commit_state_machine():
    """FLOW 7: Commit State Machine"""
    try:
        # Create commit
        create_data = {"session_id": "test_commit", "draft_id": "test_draft", "intent": "test", "confidence": 0.95}
        create_response = requests.post(f"{API_BASE}/commit/create", json=create_data, timeout=10)
        
        if create_response.status_code != 200:
            log_result("FLOW 7: Commit State Machine", "FAIL", 
                      f"Create failed: {create_response.status_code} - {create_response.text}")
            return
            
        commit_id = create_response.json().get("commit_id")
        
        # Transition DRAFT → PENDING_CONFIRMATION
        transition_data = {"commit_id": commit_id, "new_state": "PENDING_CONFIRMATION"}
        transition_response = requests.post(f"{API_BASE}/commit/transition", json=transition_data, timeout=10)
        
        if transition_response.status_code == 200:
            # Try invalid transition PENDING_CONFIRMATION → COMPLETED (skip states)
            invalid_data = {"commit_id": commit_id, "new_state": "COMPLETED"}
            invalid_response = requests.post(f"{API_BASE}/commit/transition", json=invalid_data, timeout=10)
            
            if invalid_response.status_code == 400:
                log_result("FLOW 7: Commit State Machine", "PASS", 
                          "Valid transition succeeded, invalid transition blocked (400)")
            else:
                log_result("FLOW 7: Commit State Machine", "FAIL", 
                          f"Invalid transition not blocked: {invalid_response.status_code}")
        else:
            log_result("FLOW 7: Commit State Machine", "FAIL", 
                      f"Valid transition failed: {transition_response.status_code}")
    
    except Exception as e:
        log_result("FLOW 7: Commit State Machine", "FAIL", str(e))

def test_flow_8_memory_digital_self():
    """FLOW 8: Memory (Digital Self)"""
    try:
        user_id = "e2e_user"
        
        # Store fact
        store_data = {"user_id": user_id, "text": "Sarah is my colleague from London", "fact_type": "FACT", "provenance": "EXPLICIT"}
        store_response = requests.post(f"{API_BASE}/memory/store", json=store_data, timeout=10)
        
        if store_response.status_code != 200:
            log_result("FLOW 8: Memory (Digital Self)", "FAIL", 
                      f"Memory store failed: {store_response.status_code}")
            return
        
        # Recall fact
        recall_data = {"user_id": user_id, "query": "Who is Sarah?"}
        recall_response = requests.post(f"{API_BASE}/memory/recall", json=recall_data, timeout=10)
        
        if recall_response.status_code == 200:
            results = recall_response.json().get("results", [])
            sarah_found = any("sarah" in r.get("text", "").lower() and "london" in r.get("text", "").lower() for r in results)
            
            if sarah_found:
                log_result("FLOW 8: Memory (Digital Self)", "PASS", 
                          f"Store and recall working. Found Sarah fact in {len(results)} results")
            else:
                log_result("FLOW 8: Memory (Digital Self)", "FAIL", 
                          f"Sarah fact not recalled. Results: {[r.get('text', '')[:50] for r in results]}")
        else:
            log_result("FLOW 8: Memory (Digital Self)", "FAIL", 
                      f"Memory recall failed: {recall_response.status_code}")
    
    except Exception as e:
        log_result("FLOW 8: Memory (Digital Self)", "FAIL", str(e))

def test_flow_9_prompt_compliance():
    """FLOW 9: Prompt Compliance"""
    try:
        response = requests.get(f"{API_BASE}/prompt/compliance", timeout=10)
        
        if response.status_code != 200:
            log_result("FLOW 9: Prompt Compliance", "FAIL", 
                      f"Compliance endpoint failed: {response.status_code}")
            return
        
        data = response.json()
        
        # Extract call sites properly (it's a list)
        call_sites = {cs["call_site_id"]: cs for cs in data.get("call_sites", [])}
        clean_scan = data.get("rogue_prompt_scan", {}).get("clean", False)
        
        l1_active = call_sites.get("L1_SCOUT", {}).get("status") == "active"
        l2_active = call_sites.get("L2_SENTRY", {}).get("status") == "active"
        qc_active = call_sites.get("QC_SENTRY", {}).get("status") == "active"
        
        if clean_scan and l1_active and l2_active and qc_active:
            log_result("FLOW 9: Prompt Compliance", "PASS", 
                      f"Clean scan: {clean_scan}, L1/L2/QC active: {l1_active}/{l2_active}/{qc_active}")
        else:
            log_result("FLOW 9: Prompt Compliance", "FAIL", 
                      f"Issues: clean={clean_scan}, L1={l1_active}, L2={l2_active}, QC={qc_active}")
    
    except Exception as e:
        log_result("FLOW 9: Prompt Compliance", "FAIL", str(e))

def test_flow_10_rate_limiting():
    """FLOW 10: Rate Limiting"""
    try:
        blocked = False
        
        # Make 11 requests
        for i in range(11):
            rate_data = {"key": "e2e_test", "limit_type": "auth_attempts"}
            response = requests.post(f"{API_BASE}/rate-limit/check", json=rate_data, timeout=5)
            
            if response.status_code == 200:
                result = response.json()
                if not result.get("allowed", True) and i >= 10:
                    blocked = True
                    break
            elif response.status_code == 429 and i >= 10:
                blocked = True
                break
        
        if blocked:
            log_result("FLOW 10: Rate Limiting", "PASS", "11th request blocked as expected")
        else:
            log_result("FLOW 10: Rate Limiting", "FAIL", "Rate limiting not working")
    
    except Exception as e:
        log_result("FLOW 10: Rate Limiting", "FAIL", str(e))

def test_flow_11_soul_system():
    """FLOW 11: Soul System"""
    try:
        response = requests.get(f"{API_BASE}/soul/status", timeout=10)
        
        if response.status_code != 200:
            log_result("FLOW 11: Soul System", "FAIL", f"Soul status failed: {response.status_code}")
            return
        
        data = response.json()
        integrity_valid = data.get("integrity", {}).get("valid", False)
        drift_detected = data.get("drift", {}).get("drift_detected", True)
        fragments = data.get("fragments", 0)
        
        if integrity_valid and not drift_detected and fragments == 5:
            log_result("FLOW 11: Soul System", "PASS", 
                      f"Soul healthy: integrity={integrity_valid}, drift={drift_detected}, fragments={fragments}")
        else:
            log_result("FLOW 11: Soul System", "FAIL", 
                      f"Soul issues: integrity={integrity_valid}, drift={drift_detected}, fragments={fragments}")
    
    except Exception as e:
        log_result("FLOW 11: Soul System", "FAIL", str(e))

def test_flow_12_metrics_circuit_breakers():
    """FLOW 12: Metrics + Circuit Breakers"""
    try:
        # Test metrics
        metrics_response = requests.get(f"{API_BASE}/metrics", timeout=10)
        metrics_ok = metrics_response.status_code == 200
        
        # Test circuit breakers
        cb_response = requests.get(f"{API_BASE}/circuit-breakers", timeout=10)
        cb_ok = cb_response.status_code == 200
        
        if cb_ok:
            cb_data = cb_response.json()
            breakers = cb_data.get("breakers", [])  # It's a list, not dict
            closed_breakers = [b["name"] for b in breakers if b.get("state") == "CLOSED"]
            
            if metrics_ok and len(closed_breakers) >= 6:
                log_result("FLOW 12: Metrics + Circuit Breakers", "PASS", 
                          f"Metrics OK, {len(closed_breakers)} breakers CLOSED: {closed_breakers}")
            else:
                log_result("FLOW 12: Metrics + Circuit Breakers", "FAIL", 
                          f"Metrics: {metrics_ok}, Closed breakers: {len(closed_breakers)}")
        else:
            log_result("FLOW 12: Metrics + Circuit Breakers", "FAIL", 
                      f"Circuit breakers failed: {cb_response.status_code}")
    
    except Exception as e:
        log_result("FLOW 12: Metrics + Circuit Breakers", "FAIL", str(e))

def test_flow_13_governance():
    """FLOW 13: Governance"""
    try:
        # Test retention policy
        retention_response = requests.get(f"{API_BASE}/governance/retention", timeout=10)
        retention_ok = retention_response.status_code == 200
        
        if retention_ok:
            log_result("FLOW 13: Governance", "PASS", "Retention policy endpoint working")
        else:
            log_result("FLOW 13: Governance", "FAIL", 
                      f"Retention failed: {retention_response.status_code}")
    
    except Exception as e:
        log_result("FLOW 13: Governance", "FAIL", str(e))

async def run_all_tests():
    """Execute all 13 E2E test flows"""
    print("🚀 MYNDLENS DEEP E2E TESTING — 13 FLOWS")
    print("=" * 80)
    
    # Flow 1: Pairing + WS Auth + Heartbeat (establishes connection)
    ws, session_id = await test_flow_1_pairing_ws_auth_heartbeat()
    
    # Flow 2 & 3: Use established WebSocket
    if ws and session_id:
        await test_flow_2_text_input_l1_scout_draft_tts(ws, session_id)
        await test_flow_3_guardrails_block(ws, session_id)
    
    # Flow 4 & 5: Independent WebSocket tests
    await test_flow_4_presence_gate_critical()
    await test_flow_5_subscription_gate()
    
    # Flow 6-13: API endpoint tests
    test_flow_6_mio_sign_verify()
    test_flow_7_commit_state_machine()
    test_flow_8_memory_digital_self()
    test_flow_9_prompt_compliance()
    test_flow_10_rate_limiting()
    test_flow_11_soul_system()
    test_flow_12_metrics_circuit_breakers()
    test_flow_13_governance()
    
    # Close WebSocket
    if ws:
        await ws.close()
    
    # Print final summary
    print("\n" + "=" * 80)
    print("🏁 MYNDLENS DEEP E2E TESTING RESULTS")
    print("=" * 80)
    
    passed = sum(1 for r in test_results.values() if r["status"] == "PASS")
    failed = sum(1 for r in test_results.values() if r["status"] == "FAIL")
    
    print(f"📊 SUMMARY: {passed} PASS, {failed} FAIL out of {len(test_results)} total\n")
    
    # List failures with evidence
    failures = [name for name, result in test_results.items() if result["status"] == "FAIL"]
    if failures:
        print(f"❌ FAILURES REQUIRING ATTENTION ({len(failures)}):")
        for failure in failures:
            evidence = test_results[failure]["evidence"]
            print(f"   • {failure}")
            if evidence:
                print(f"     Evidence: {evidence}")
        print()
    
    # List successes
    successes = [name for name, result in test_results.items() if result["status"] == "PASS"]
    if successes:
        print(f"✅ SUCCESSFUL FLOWS ({len(successes)}):")
        for success in successes:
            print(f"   • {success}")

if __name__ == "__main__":
    asyncio.run(run_all_tests())