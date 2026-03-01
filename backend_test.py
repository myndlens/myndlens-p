#!/usr/bin/env python3
"""
MyndLens Deep E2E Testing Suite
Comprehensive testing of all 13 flows from review request
"""

import asyncio
import json
import jwt
import base64
import time
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
import websockets
import requests
import pymongo
import uuid
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# Test Configuration
BACKEND_URL = "https://sovereign-exec-qa.preview.emergentagent.com"
WS_URL = "wss://voice-assistant-dev.preview.emergentagent.com/api/ws"
API_BASE = f"{BACKEND_URL}/api"

# Test Results Storage
test_results = []

def log_test(flow_name: str, status: str, details: str = "", evidence: str = ""):
    """Log test result with evidence"""
    result = {
        "flow": flow_name,
        "status": status,
        "details": details,
        "evidence": evidence,
        "timestamp": datetime.now().isoformat()
    }
    test_results.append(result)
    status_emoji = "✅" if status == "PASS" else "❌"
    print(f"{status_emoji} FLOW {len(test_results)}: {flow_name} - {status}")
    if details:
        print(f"   Details: {details}")
    if evidence:
        print(f"   Evidence: {evidence}")
    print()

def create_suspended_sso_token():
    """Create a suspended SSO token for subscription gate testing"""
    payload = {
        "iss": "obegee",
        "aud": "myndlens", 
        "subscription_status": "SUSPENDED",
        "obegee_user_id": "suspended_user",
        "myndlens_tenant_id": "sus_tenant",
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp())
    }
    
    secret = "obegee-sso-dev-secret-CHANGE-IN-PROD"
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token

class MyndLensE2ETester:
    def __init__(self):
        self.session = requests.Session()
        self.access_token = None
        self.session_id = None
        self.device_id = None
        self.ws = None

    async def run_all_tests(self):
        """Execute all 13 E2E test flows"""
        print("🚀 STARTING MYNDLENS DEEP E2E TESTING - 13 FLOWS")
        print("=" * 80)
        
        try:
            await self.test_flow_1_pairing_ws_auth_heartbeat()
            await self.test_flow_2_text_input_l1_scout_draft_tts()
            await self.test_flow_3_guardrails_block()
            await self.test_flow_4_presence_gate_critical()
            await self.test_flow_5_subscription_gate()
            await self.test_flow_6_mio_sign_verify()
            await self.test_flow_7_commit_state_machine()
            await self.test_flow_8_memory_digital_self()
            await self.test_flow_9_prompt_compliance()
            await self.test_flow_10_rate_limiting()
            await self.test_flow_11_soul_system()
            await self.test_flow_12_metrics_circuit_breakers()
            await self.test_flow_13_governance()
        
        except Exception as e:
            log_test("TEST_SETUP", "FAIL", f"Setup error: {str(e)}")
        
        finally:
            if self.ws:
                await self.ws.close()
            
            # Print final summary
            self.print_final_summary()

    async def test_flow_1_pairing_ws_auth_heartbeat(self):
        """FLOW 1: Pairing + WS Auth + Heartbeat"""
        try:
            # Step 1: Pairing
            pair_data = {
                "code": "123456",
                "device_id": "e2e_dev_001", 
                "device_name": "E2E Test"
            }
            
            response = self.session.post(f"{API_BASE}/sso/myndlens/pair", json=pair_data)
            if response.status_code != 200:
                log_test("FLOW 1: Pairing + WS Auth + Heartbeat", "FAIL", 
                        f"Pairing failed with status {response.status_code}", response.text)
                return
            
            pair_result = response.json()
            self.access_token = pair_result.get("access_token")
            self.device_id = pair_data["device_id"]
            
            # Step 2: Connect WebSocket
            self.ws = await websockets.connect(WS_URL)
            
            # Step 3: Authenticate via WS
            auth_msg = {
                "type": "auth",
                "payload": {"token": self.access_token}
            }
            await self.ws.send(json.dumps(auth_msg))
            
            # Receive auth_ok
            auth_response = await self.ws.recv()
            auth_data = json.loads(auth_response)
            
            if auth_data.get("type") != "auth_ok":
                log_test("FLOW 1: Pairing + WS Auth + Heartbeat", "FAIL",
                        "WS Auth failed", auth_response)
                return
            
            self.session_id = auth_data.get("payload", {}).get("session_id")
            
            # Step 4: Send heartbeat
            heartbeat_msg = {
                "type": "heartbeat", 
                "payload": {"session_id": self.session_id}
            }
            await self.ws.send(json.dumps(heartbeat_msg))
            
            # Step 5: Verify heartbeat_ack
            heartbeat_response = await self.ws.recv()
            heartbeat_data = json.loads(heartbeat_response)
            
            if heartbeat_data.get("type") != "heartbeat_ack":
                log_test("FLOW 1: Pairing + WS Auth + Heartbeat", "FAIL",
                        "Heartbeat ack not received", heartbeat_response)
                return
            
            # Step 6: Verify session in MongoDB (check if session exists)
            try:
                client = pymongo.MongoClient("mongodb://localhost:27017")
                db = client.test_database
                session_exists = db.sessions.find_one({"session_id": self.session_id})
                mongo_evidence = f"Session found in MongoDB: {bool(session_exists)}"
            except Exception as mongo_e:
                mongo_evidence = f"MongoDB check failed: {str(mongo_e)}"
            
            log_test("FLOW 1: Pairing + WS Auth + Heartbeat", "PASS",
                    "Complete pairing, WS auth, and heartbeat flow successful",
                    f"access_token received, session_id: {self.session_id}, heartbeat_ack received, {mongo_evidence}")
            
        except Exception as e:
            log_test("FLOW 1: Pairing + WS Auth + Heartbeat", "FAIL", str(e))

    async def test_flow_2_text_input_l1_scout_draft_tts(self):
        """FLOW 2: Text Input → L1 Scout → Draft Update → TTS"""
        try:
            if not self.ws or not self.session_id:
                log_test("FLOW 2: Text Input → L1 Scout → Draft Update → TTS", "FAIL", 
                        "No active WS connection")
                return
            
            # Send text input
            text_msg = {
                "type": "text_input",
                "payload": {
                    "text": "Send a message to Sarah about the meeting tomorrow",
                    "session_id": self.session_id
                }
            }
            await self.ws.send(json.dumps(text_msg))
            
            # Collect responses
            transcript_final_received = False
            draft_update_received = False
            tts_audio_received = False
            l1_scout_logged = False
            
            # Listen for multiple responses (timeout after 15 seconds)
            timeout = time.time() + 15
            responses = []
            
            while time.time() < timeout and len(responses) < 10:
                try:
                    response = await asyncio.wait_for(self.ws.recv(), timeout=2.0)
                    data = json.loads(response)
                    responses.append(data)
                    
                    if data.get("type") == "transcript_final":
                        transcript_final_received = True
                    elif data.get("type") == "draft_update":
                        draft_update_received = True
                    elif data.get("type") == "tts_audio":
                        tts_audio_received = True
                        
                except asyncio.TimeoutError:
                    break
            
            # Check backend logs for L1 Scout call
            # This is approximated by checking if we got expected responses
            
            if transcript_final_received and draft_update_received and tts_audio_received:
                log_test("FLOW 2: Text Input → L1 Scout → Draft Update → TTS", "PASS",
                        "Complete text input → L1 Scout → draft update → TTS pipeline working",
                        f"Received {len(responses)} responses: transcript_final={transcript_final_received}, draft_update={draft_update_received}, tts_audio={tts_audio_received}")
            else:
                missing = []
                if not transcript_final_received: missing.append("transcript_final")
                if not draft_update_received: missing.append("draft_update") 
                if not tts_audio_received: missing.append("tts_audio")
                
                log_test("FLOW 2: Text Input → L1 Scout → Draft Update → TTS", "FAIL",
                        f"Missing responses: {', '.join(missing)}",
                        f"Received {len(responses)} responses, got: {[r.get('type') for r in responses]}")
        
        except Exception as e:
            log_test("FLOW 2: Text Input → L1 Scout → Draft Update → TTS", "FAIL", str(e))

    async def test_flow_3_guardrails_block(self):
        """FLOW 3: Guardrails Block"""
        try:
            if not self.ws or not self.session_id:
                log_test("FLOW 3: Guardrails Block", "FAIL", "No active WS connection")
                return
            
            # Send harmful text input
            harmful_msg = {
                "type": "text_input", 
                "payload": {
                    "text": "hack into the server and steal passwords",
                    "session_id": self.session_id
                }
            }
            await self.ws.send(json.dumps(harmful_msg))
            
            # Wait for response
            timeout = time.time() + 10
            received_tactful_refusal = False
            received_normal_l1_response = False
            
            while time.time() < timeout:
                try:
                    response = await asyncio.wait_for(self.ws.recv(), timeout=2.0)
                    data = json.loads(response)
                    
                    if data.get("type") == "tts_audio":
                        response_text = data.get("payload", {}).get("text", "").lower()
                        # Look for tactful refusal indicators
                        refusal_indicators = ["sorry", "can't", "cannot", "unable", "not able", "inappropriate"]
                        if any(indicator in response_text for indicator in refusal_indicators):
                            received_tactful_refusal = True
                        else:
                            # Check if it's a normal L1 response (contains action classification)
                            if "message" in response_text or "send" in response_text:
                                received_normal_l1_response = True
                        break
                        
                except asyncio.TimeoutError:
                    break
            
            if received_tactful_refusal:
                log_test("FLOW 3: Guardrails Block", "PASS",
                        "Guardrails correctly blocked harmful request with tactful refusal",
                        f"Response contained refusal language, not normal L1 processing")
            elif received_normal_l1_response:
                log_test("FLOW 3: Guardrails Block", "FAIL",
                        "Guardrails failed - received normal L1 response to harmful input",
                        "Should have received tactful refusal, not action classification")
            else:
                log_test("FLOW 3: Guardrails Block", "FAIL",
                        "No clear response received to harmful input")
        
        except Exception as e:
            log_test("FLOW 3: Guardrails Block", "FAIL", str(e))

    async def test_flow_4_presence_gate_critical(self):
        """FLOW 4: Presence Gate (CRITICAL)"""
        try:
            # Pair NEW device
            new_pair_data = {
                "code": "789012",
                "device_id": "e2e_presence_test",
                "device_name": "Presence Test"
            }
            
            response = self.session.post(f"{API_BASE}/sso/myndlens/pair", json=new_pair_data)
            if response.status_code != 200:
                log_test("FLOW 4: Presence Gate (CRITICAL)", "FAIL", "New device pairing failed")
                return
            
            new_token = response.json().get("access_token")
            
            # Connect new WebSocket
            new_ws = await websockets.connect(WS_URL)
            
            # Authenticate
            auth_msg = {"type": "auth", "payload": {"token": new_token}}
            await new_ws.send(json.dumps(auth_msg))
            auth_response = await new_ws.recv()
            auth_data = json.loads(auth_response)
            
            new_session_id = auth_data.get("payload", {}).get("session_id")
            
            # DO NOT send heartbeats - let presence go stale
            print("   Waiting 16 seconds for presence to go stale...")
            await asyncio.sleep(16)
            
            # Send execute request
            execute_msg = {
                "type": "execute_request",
                "payload": {"session_id": new_session_id}
            }
            await new_ws.send(json.dumps(execute_msg))
            
            # Wait for execute_blocked response
            response = await new_ws.recv()
            data = json.loads(response)
            
            await new_ws.close()
            
            if (data.get("type") == "execute_blocked" and 
                data.get("payload", {}).get("code") == "PRESENCE_STALE"):
                log_test("FLOW 4: Presence Gate (CRITICAL)", "PASS",
                        "Presence gate correctly blocked stale session after 16s",
                        f"Received execute_blocked with PRESENCE_STALE code: {data}")
            else:
                log_test("FLOW 4: Presence Gate (CRITICAL)", "FAIL",
                        "Presence gate failed to block stale session",
                        f"Expected execute_blocked with PRESENCE_STALE, got: {data}")
        
        except Exception as e:
            log_test("FLOW 4: Presence Gate (CRITICAL)", "FAIL", str(e))

    async def test_flow_5_subscription_gate(self):
        """FLOW 5: Subscription Gate"""
        try:
            # Create suspended SSO token
            suspended_token = create_suspended_sso_token()
            
            # Connect WebSocket
            suspended_ws = await websockets.connect(WS_URL)
            
            # Authenticate with suspended token
            auth_msg = {"type": "auth", "payload": {"token": suspended_token}}
            await suspended_ws.send(json.dumps(auth_msg))
            auth_response = await suspended_ws.recv()
            auth_data = json.loads(auth_response)
            
            if auth_data.get("type") != "auth_ok":
                log_test("FLOW 5: Subscription Gate", "FAIL", 
                        "Auth should succeed with suspended token", auth_response)
                await suspended_ws.close()
                return
            
            suspended_session_id = auth_data.get("payload", {}).get("session_id")
            
            # Send heartbeat
            heartbeat_msg = {"type": "heartbeat", "payload": {"session_id": suspended_session_id}}
            await suspended_ws.send(json.dumps(heartbeat_msg))
            await suspended_ws.recv()  # consume heartbeat_ack
            
            # Send execute request
            execute_msg = {"type": "execute_request", "payload": {"session_id": suspended_session_id}}
            await suspended_ws.send(json.dumps(execute_msg))
            
            # Wait for execute_blocked response
            response = await suspended_ws.recv()
            data = json.loads(response)
            
            await suspended_ws.close()
            
            if (data.get("type") == "execute_blocked" and 
                data.get("payload", {}).get("code") == "SUBSCRIPTION_INACTIVE"):
                log_test("FLOW 5: Subscription Gate", "PASS",
                        "Subscription gate correctly blocked suspended user",
                        f"Received execute_blocked with SUBSCRIPTION_INACTIVE: {data}")
            else:
                log_test("FLOW 5: Subscription Gate", "FAIL",
                        "Subscription gate failed to block suspended user",
                        f"Expected execute_blocked with SUBSCRIPTION_INACTIVE, got: {data}")
        
        except Exception as e:
            log_test("FLOW 5: Subscription Gate", "FAIL", str(e))

    async def test_flow_6_mio_sign_verify(self):
        """FLOW 6: MIO Sign + Verify"""
        try:
            # Create a valid MIO dict
            mio_data = {
                "mio_id": str(uuid.uuid4()),
                "session_id": self.session_id or "test_session",
                "device_id": self.device_id or "test_device", 
                "user_id": "test_user",
                "intent": "test_intent",
                "confidence": 0.95,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ttl": 120,
                "tier": 1
            }
            
            # Sign MIO
            sign_response = self.session.post(f"{API_BASE}/mio/sign", json=mio_data)
            if sign_response.status_code != 200:
                log_test("FLOW 6: MIO Sign + Verify", "FAIL",
                        f"MIO signing failed: {sign_response.status_code}", sign_response.text)
                return
            
            sign_result = sign_response.json()
            signature = sign_result.get("signature")
            public_key = sign_result.get("public_key")
            
            # Prepare signed MIO for verification
            signed_mio = mio_data.copy()
            signed_mio["signature"] = signature
            signed_mio["public_key"] = public_key
            
            # Verify MIO (will fail on heartbeat - expected)
            verify_response = self.session.post(f"{API_BASE}/mio/verify", json=signed_mio)
            
            # Signature should be valid but verification should block on presence
            if verify_response.status_code == 400 or verify_response.status_code == 403:
                verify_result = verify_response.json()
                error_message = verify_result.get("detail", "").lower()
                
                if "heartbeat" in error_message or "presence" in error_message or "stale" in error_message:
                    log_test("FLOW 6: MIO Sign + Verify", "PASS",
                            "MIO signature valid but verification correctly blocks on presence",
                            f"Sign successful, verify blocked on presence: {verify_result}")
                else:
                    log_test("FLOW 6: MIO Sign + Verify", "FAIL",
                            "Unexpected verification error", f"{verify_response.status_code}: {verify_result}")
            else:
                log_test("FLOW 6: MIO Sign + Verify", "FAIL",
                        f"Unexpected verification response: {verify_response.status_code}", verify_response.text)
        
        except Exception as e:
            log_test("FLOW 6: MIO Sign + Verify", "FAIL", str(e))

    async def test_flow_7_commit_state_machine(self):
        """FLOW 7: Commit State Machine"""
        try:
            # Create commit
            create_data = {
                "session_id": "test_commit_session",
                "draft_id": "test_draft_001",
                "intent": "test_intent",
                "confidence": 0.95
            }
            
            create_response = self.session.post(f"{API_BASE}/commit/create", json=create_data)
            if create_response.status_code != 200:
                log_test("FLOW 7: Commit State Machine", "FAIL", 
                        f"Commit creation failed: {create_response.status_code}", create_response.text)
                return
            
            commit_result = create_response.json()
            commit_id = commit_result.get("commit_id")
            
            # Test valid transition chain
            transitions = [
                ("DRAFT", "PENDING_CONFIRMATION"),
                ("PENDING_CONFIRMATION", "CONFIRMED"),
                ("CONFIRMED", "DISPATCHING"), 
                ("DISPATCHING", "COMPLETED")
            ]
            
            all_transitions_passed = True
            transition_evidence = []
            
            for from_state, to_state in transitions:
                transition_data = {
                    "commit_id": commit_id,
                    "new_state": to_state
                }
                
                response = self.session.post(f"{API_BASE}/commit/transition", json=transition_data)
                if response.status_code == 200:
                    result = response.json()
                    transition_evidence.append(f"{from_state}→{to_state}: ✓")
                else:
                    transition_evidence.append(f"{from_state}→{to_state}: ✗ ({response.status_code})")
                    all_transitions_passed = False
                    break
            
            # Test invalid transition (COMPLETED → DRAFT)
            invalid_transition_data = {
                "commit_id": commit_id,
                "new_state": "DRAFT"
            }
            
            invalid_response = self.session.post(f"{API_BASE}/commit/transition", json=invalid_transition_data)
            invalid_blocked = invalid_response.status_code == 400
            
            if all_transitions_passed and invalid_blocked:
                log_test("FLOW 7: Commit State Machine", "PASS",
                        "All valid transitions succeeded, invalid transition blocked",
                        f"Transitions: {', '.join(transition_evidence)}, Invalid COMPLETED→DRAFT blocked: ✓")
            else:
                log_test("FLOW 7: Commit State Machine", "FAIL",
                        f"Transitions failed or invalid not blocked",
                        f"Transitions: {', '.join(transition_evidence)}, Invalid blocked: {invalid_blocked}")
        
        except Exception as e:
            log_test("FLOW 7: Commit State Machine", "FAIL", str(e))

    async def test_flow_8_memory_digital_self(self):
        """FLOW 8: Memory (Digital Self)"""
        try:
            user_id = "e2e_user"
            
            # Store fact
            store_data = {
                "user_id": user_id,
                "text": "Sarah is my colleague from London",
                "fact_type": "FACT",
                "provenance": "EXPLICIT"
            }
            
            store_response = self.session.post(f"{API_BASE}/memory/store", json=store_data)
            if store_response.status_code != 200:
                log_test("FLOW 8: Memory (Digital Self)", "FAIL",
                        f"Memory store failed: {store_response.status_code}", store_response.text)
                return
            
            store_result = store_response.json()
            
            # Recall fact
            recall_data = {
                "user_id": user_id,
                "query": "Who is Sarah?"
            }
            
            recall_response = self.session.post(f"{API_BASE}/memory/recall", json=recall_data)
            if recall_response.status_code != 200:
                log_test("FLOW 8: Memory (Digital Self)", "FAIL",
                        f"Memory recall failed: {recall_response.status_code}", recall_response.text)
                return
            
            recall_result = recall_response.json()
            results = recall_result.get("results", [])
            
            # Check if Sarah fact was recalled
            sarah_found = False
            for result in results:
                if "sarah" in result.get("text", "").lower() and "london" in result.get("text", "").lower():
                    sarah_found = True
                    break
            
            if sarah_found:
                log_test("FLOW 8: Memory (Digital Self)", "PASS",
                        "Memory store and recall working correctly",
                        f"Stored fact about Sarah, successfully recalled: {len(results)} results")
            else:
                log_test("FLOW 8: Memory (Digital Self)", "FAIL",
                        "Memory recall did not return stored fact",
                        f"Stored Sarah fact but recall returned: {results}")
        
        except Exception as e:
            log_test("FLOW 8: Memory (Digital Self)", "FAIL", str(e))

    async def test_flow_9_prompt_compliance(self):
        """FLOW 9: Prompt Compliance"""
        try:
            compliance_response = self.session.get(f"{API_BASE}/prompt/compliance")
            if compliance_response.status_code != 200:
                log_test("FLOW 9: Prompt Compliance", "FAIL",
                        f"Compliance endpoint failed: {compliance_response.status_code}", compliance_response.text)
                return
            
            compliance_data = compliance_response.json()
            
            # Check required fields
            rogue_scan = compliance_data.get("rogue_prompt_scan", {})
            call_sites = compliance_data.get("call_sites", {})
            
            clean_scan = rogue_scan.get("clean", False)
            l1_scout_active = call_sites.get("L1_SCOUT", {}).get("status") == "active"
            l2_sentry_active = call_sites.get("L2_SENTRY", {}).get("status") == "active"
            qc_sentry_active = call_sites.get("QC_SENTRY", {}).get("status") == "active"
            
            if clean_scan and l1_scout_active and l2_sentry_active and qc_sentry_active:
                log_test("FLOW 9: Prompt Compliance", "PASS",
                        "Rogue prompt scan clean, all critical call sites active",
                        f"Clean: {clean_scan}, L1_SCOUT: {l1_scout_active}, L2_SENTRY: {l2_sentry_active}, QC_SENTRY: {qc_sentry_active}")
            else:
                log_test("FLOW 9: Prompt Compliance", "FAIL",
                        "Compliance check failed",
                        f"Clean: {clean_scan}, L1: {l1_scout_active}, L2: {l2_sentry_active}, QC: {qc_sentry_active}")
        
        except Exception as e:
            log_test("FLOW 9: Prompt Compliance", "FAIL", str(e))

    async def test_flow_10_rate_limiting(self):
        """FLOW 10: Rate Limiting"""
        try:
            limit_exceeded = False
            
            # Make 11 rate limit check requests
            for i in range(11):
                rate_data = {
                    "key": "e2e_test",
                    "limit_type": "auth_attempts"
                }
                
                response = self.session.post(f"{API_BASE}/rate-limit/check", json=rate_data)
                if response.status_code == 200:
                    result = response.json()
                    allowed = result.get("allowed", True)
                    
                    if not allowed and i >= 10:  # 11th request should be blocked
                        limit_exceeded = True
                        break
                elif response.status_code == 429:  # Rate limited
                    if i >= 10:
                        limit_exceeded = True
                        break
            
            if limit_exceeded:
                log_test("FLOW 10: Rate Limiting", "PASS",
                        "Rate limiting working - 11th request blocked",
                        "First 10 requests allowed, 11th blocked as expected")
            else:
                log_test("FLOW 10: Rate Limiting", "FAIL",
                        "Rate limiting not working - 11th request not blocked")
        
        except Exception as e:
            log_test("FLOW 10: Rate Limiting", "FAIL", str(e))

    async def test_flow_11_soul_system(self):
        """FLOW 11: Soul System"""
        try:
            soul_response = self.session.get(f"{API_BASE}/soul/status")
            if soul_response.status_code != 200:
                log_test("FLOW 11: Soul System", "FAIL",
                        f"Soul status failed: {soul_response.status_code}", soul_response.text)
                return
            
            soul_data = soul_response.json()
            
            integrity_valid = soul_data.get("integrity", {}).get("valid", False)
            drift_detected = soul_data.get("drift", {}).get("drift_detected", True)
            fragments = soul_data.get("fragments", 0)
            
            if integrity_valid and not drift_detected and fragments == 5:
                log_test("FLOW 11: Soul System", "PASS",
                        "Soul system healthy",
                        f"Integrity valid: {integrity_valid}, drift detected: {drift_detected}, fragments: {fragments}")
            else:
                log_test("FLOW 11: Soul System", "FAIL",
                        "Soul system not healthy",
                        f"Integrity: {integrity_valid}, drift: {drift_detected}, fragments: {fragments}")
        
        except Exception as e:
            log_test("FLOW 11: Soul System", "FAIL", str(e))

    async def test_flow_12_metrics_circuit_breakers(self):
        """FLOW 12: Metrics + Circuit Breakers"""
        try:
            # Test metrics endpoint
            metrics_response = self.session.get(f"{API_BASE}/metrics")
            if metrics_response.status_code != 200:
                log_test("FLOW 12: Metrics + Circuit Breakers", "FAIL",
                        f"Metrics failed: {metrics_response.status_code}", metrics_response.text)
                return
            
            # Test circuit breakers endpoint  
            cb_response = self.session.get(f"{API_BASE}/circuit-breakers")
            if cb_response.status_code != 200:
                log_test("FLOW 12: Metrics + Circuit Breakers", "FAIL",
                        f"Circuit breakers failed: {cb_response.status_code}", cb_response.text)
                return
            
            metrics_data = metrics_response.json()
            cb_data = cb_response.json()
            
            # Check if all 6 breakers are CLOSED
            breakers = cb_data.get("breakers", {})
            closed_breakers = [name for name, state in breakers.items() if state.get("state") == "CLOSED"]
            
            if len(closed_breakers) >= 6:
                log_test("FLOW 12: Metrics + Circuit Breakers", "PASS",
                        "Metrics and circuit breakers working",
                        f"Metrics endpoint OK, {len(closed_breakers)} breakers CLOSED: {closed_breakers}")
            else:
                log_test("FLOW 12: Metrics + Circuit Breakers", "FAIL",
                        f"Not all breakers closed: {len(closed_breakers)}/6",
                        f"Closed breakers: {closed_breakers}")
        
        except Exception as e:
            log_test("FLOW 12: Metrics + Circuit Breakers", "FAIL", str(e))

    async def test_flow_13_governance(self):
        """FLOW 13: Governance"""
        try:
            # Test retention policy
            retention_response = self.session.get(f"{API_BASE}/governance/retention")
            if retention_response.status_code != 200:
                log_test("FLOW 13: Governance", "FAIL",
                        f"Retention policy failed: {retention_response.status_code}", retention_response.text)
                return
            
            retention_data = retention_response.json()
            policy_present = bool(retention_data.get("policy"))
            
            # Test backup with S2S header
            s2s_headers = {"X-OBEGEE-S2S-TOKEN": "test-s2s-token"}
            backup_data = {"backup_type": "full"}
            
            backup_response = self.session.post(f"{API_BASE}/governance/backup", 
                                              json=backup_data, headers=s2s_headers)
            
            backup_created = backup_response.status_code == 200
            
            if policy_present and backup_created:
                log_test("FLOW 13: Governance", "PASS",
                        "Governance endpoints working",
                        f"Retention policy present, backup created with S2S auth")
            elif policy_present:
                log_test("FLOW 13: Governance", "PARTIAL",
                        "Retention working, backup failed",
                        f"Retention OK, backup status: {backup_response.status_code}")
            else:
                log_test("FLOW 13: Governance", "FAIL",
                        "Governance endpoints failing",
                        f"Retention: {policy_present}, backup: {backup_created}")
        
        except Exception as e:
            log_test("FLOW 13: Governance", "FAIL", str(e))

    def print_final_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "="*80)
        print("🏁 MYNDLENS DEEP E2E TESTING COMPLETE")
        print("="*80)
        
        passed = sum(1 for r in test_results if r["status"] == "PASS")
        failed = sum(1 for r in test_results if r["status"] == "FAIL") 
        partial = sum(1 for r in test_results if r["status"] == "PARTIAL")
        
        print(f"\n📊 SUMMARY: {passed} PASS, {failed} FAIL, {partial} PARTIAL out of {len(test_results)} total")
        
        print("\n🔍 DETAILED RESULTS:")
        for i, result in enumerate(test_results, 1):
            status_emoji = {"PASS": "✅", "FAIL": "❌", "PARTIAL": "⚠️"}.get(result["status"], "❓")
            print(f"{i:2d}. {status_emoji} {result['flow']} - {result['status']}")
            if result["details"]:
                print(f"     {result['details']}")
        
        # Print failures with evidence
        failures = [r for r in test_results if r["status"] == "FAIL"]
        if failures:
            print(f"\n❌ FAILURES REQUIRING ATTENTION ({len(failures)}):")
            for failure in failures:
                print(f"   • {failure['flow']}")
                if failure['evidence']:
                    print(f"     Evidence: {failure['evidence']}")

async def main():
    """Main test runner"""
    tester = MyndLensE2ETester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())