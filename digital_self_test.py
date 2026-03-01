#!/usr/bin/env python3
"""
MyndLens Batch 5 Digital Self (Vector-Graph Memory) Backend Testing
Critical Tests from Review Request:

1. Store facts via REST API (/api/memory/store)
2. Register entity via REST API (/api/memory/entity)
3. Semantic recall (/api/memory/recall) (MOST IMPORTANT)
4. Cross-query recall
5. Provenance tracking
6. Write policy enforcement
7. Regression testing: Health, SSO, WS auth, L1 Scout, presence gate
"""

import asyncio
import json
import logging
import requests
import websockets
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

# Test configuration - using frontend env for backend URL
BACKEND_URL = "https://sovereign-exec-qa.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"
WS_URL = f"wss://voice-assistant-dev.preview.emergentagent.com/api/ws"

# Test user credentials
TEST_USERNAME = "mem_user"
TEST_PASSWORD = "pass"
TEST_DEVICE_ID = "memdev"

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DigitalSelfTestClient:
    def __init__(self):
        self.session_id = None
        self.websocket = None
        self.sso_token = None
        self.stored_nodes = []  # Track stored facts/entities
    
    def log_test(self, test_name: str, status: str, details: str = ""):
        """Log test results with timestamp"""
        status_emoji = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        logger.info(f"{status_emoji} {test_name}: {status} {details}")
    
    async def get_sso_token(self) -> bool:
        """Get SSO token from mock endpoint"""
        try:
            response = requests.post(f"{API_BASE}/sso/myndlens/token", json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "device_id": TEST_DEVICE_ID
            }, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.sso_token = data["token"]
                logger.info(f"SSO token obtained: ...{self.sso_token[-10:]}")
                return True
            else:
                logger.error(f"SSO token request failed: {response.status_code} {response.text}")
                return False
        except Exception as e:
            logger.error(f"SSO token error: {e}")
            return False
    
    async def connect_websocket(self) -> bool:
        """Connect and authenticate WebSocket for regression tests"""
        try:
            self.websocket = await websockets.connect(WS_URL)
            
            # Send auth message
            auth_msg = {
                "type": "auth",
                "payload": {
                    "token": self.sso_token,
                    "device_id": TEST_DEVICE_ID,
                    "client_version": "1.0.0"
                }
            }
            await self.websocket.send(json.dumps(auth_msg))
            
            # Wait for auth_ok
            response = await asyncio.wait_for(self.websocket.recv(), timeout=10)
            msg = json.loads(response)
            
            if msg.get("type") == "auth_ok":
                self.session_id = msg["payload"]["session_id"]
                logger.info(f"WebSocket authenticated, session: {self.session_id}")
                return True
            else:
                logger.error(f"Auth failed: {msg}")
                return False
                
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            return False
    
    async def send_heartbeat(self) -> bool:
        """Send heartbeat to maintain presence"""
        try:
            heartbeat_msg = {
                "type": "heartbeat", 
                "payload": {
                    "session_id": self.session_id,
                    "seq": int(time.time()),
                    "client_ts": datetime.now(timezone.utc).isoformat()
                }
            }
            await self.websocket.send(json.dumps(heartbeat_msg))
            
            # Wait for ack
            response = await asyncio.wait_for(self.websocket.recv(), timeout=5)
            msg = json.loads(response)
            
            return msg.get("type") == "heartbeat_ack"
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")
            return False
    
    async def send_text_input(self, text: str) -> Dict[str, Any]:
        """Send text input for L1 Scout regression test"""
        try:
            text_msg = {
                "type": "text_input",
                "payload": {
                    "session_id": self.session_id,
                    "text": text
                }
            }
            await self.websocket.send(json.dumps(text_msg))
            
            responses = {}
            timeout_time = time.time() + 15  # 15 second timeout
            
            while time.time() < timeout_time:
                try:
                    response = await asyncio.wait_for(self.websocket.recv(), timeout=2)
                    msg = json.loads(response)
                    msg_type = msg.get("type")
                    
                    responses[msg_type] = msg
                    logger.debug(f"Received {msg_type}")
                    
                    # Stop collecting after getting TTS audio
                    if msg_type == "tts_audio":
                        break
                        
                except asyncio.TimeoutError:
                    break
            
            return responses
            
        except Exception as e:
            logger.error(f"Text input error: {e}")
            return {}
    
    async def close(self):
        """Close WebSocket connection"""
        if self.websocket:
            await self.websocket.close()

class DigitalSelfTests:
    def __init__(self):
        self.client = DigitalSelfTestClient()
        self.test_results = {}
    
    def assert_test(self, test_name: str, condition: bool, message: str):
        """Assert test condition and log result"""
        if condition:
            self.client.log_test(test_name, "PASS", message)
            self.test_results[test_name] = "PASS"
        else:
            self.client.log_test(test_name, "FAIL", message)
            self.test_results[test_name] = "FAIL"
    
    async def test_health_endpoint(self):
        """Test 1: Health endpoint"""
        try:
            response = requests.get(f"{API_BASE}/health", timeout=10)
            data = response.json()
            
            self.assert_test(
                "Health endpoint", 
                response.status_code == 200 and data.get('status') == 'ok',
                f"Status: {data.get('status')}, Version: {data.get('version')}"
            )
            
        except Exception as e:
            self.assert_test("Health endpoint", False, f"Error: {e}")
    
    async def test_store_facts_api(self):
        """Test 2: Store facts via REST API"""
        # Test case 1: Store a FACT with EXPLICIT provenance
        try:
            fact_data = {
                "user_id": TEST_USERNAME,
                "text": "Sarah is my sister who lives in London",
                "fact_type": "FACT",
                "provenance": "EXPLICIT"
            }
            
            response = requests.post(f"{API_BASE}/memory/store", json=fact_data, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                node_id = data.get("node_id")
                status = data.get("status")
                
                self.assert_test(
                    "Store FACT - Sarah", 
                    node_id is not None and status == "stored",
                    f"Node ID: {node_id}, Status: {status}"
                )
                
                # Store node_id for later recall tests
                self.client.stored_nodes.append({"node_id": node_id, "text": fact_data["text"]})
            else:
                self.assert_test("Store FACT - Sarah", False, f"HTTP {response.status_code}: {response.text}")
        
        except Exception as e:
            self.assert_test("Store FACT - Sarah", False, f"Error: {e}")
        
        # Test case 2: Store a PREFERENCE
        try:
            preference_data = {
                "user_id": TEST_USERNAME,
                "text": "I prefer morning meetings before 10am",
                "fact_type": "PREFERENCE", 
                "provenance": "EXPLICIT"
            }
            
            response = requests.post(f"{API_BASE}/memory/store", json=preference_data, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                node_id = data.get("node_id")
                
                self.assert_test(
                    "Store PREFERENCE - Meetings", 
                    node_id is not None,
                    f"Node ID: {node_id}"
                )
                
                self.client.stored_nodes.append({"node_id": node_id, "text": preference_data["text"]})
            else:
                self.assert_test("Store PREFERENCE - Meetings", False, f"HTTP {response.status_code}")
        
        except Exception as e:
            self.assert_test("Store PREFERENCE - Meetings", False, f"Error: {e}")
    
    async def test_register_entity_api(self):
        """Test 3: Register entity via REST API"""
        try:
            entity_data = {
                "user_id": TEST_USERNAME,
                "entity_type": "PERSON",
                "name": "Sarah",
                "aliases": ["sis", "sister"]
            }
            
            response = requests.post(f"{API_BASE}/memory/entity", json=entity_data, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                entity_id = data.get("entity_id")
                status = data.get("status")
                
                self.assert_test(
                    "Register Entity - Sarah", 
                    entity_id is not None and status == "registered",
                    f"Entity ID: {entity_id}, Status: {status}"
                )
                
                self.client.stored_nodes.append({"node_id": entity_id, "text": "Sarah (PERSON)"})
            else:
                self.assert_test("Register Entity - Sarah", False, f"HTTP {response.status_code}: {response.text}")
        
        except Exception as e:
            self.assert_test("Register Entity - Sarah", False, f"Error: {e}")
    
    async def test_semantic_recall_api(self):
        """Test 4: Semantic recall (MOST IMPORTANT)"""
        # Wait a moment for storage to complete
        await asyncio.sleep(1)
        
        try:
            recall_data = {
                "user_id": TEST_USERNAME,
                "query": "Who is Sarah?",
                "n_results": 3
            }
            
            response = requests.post(f"{API_BASE}/memory/recall", json=recall_data, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                stats = data.get("stats", {})
                
                self.assert_test(
                    "Semantic Recall - Query", 
                    response.status_code == 200,
                    f"Results: {len(results)}, Stats: {stats}"
                )
                
                # Check if results contain Sarah-related information
                sarah_found = False
                for result in results:
                    node_id = result.get("node_id")
                    text = result.get("text", "")
                    provenance = result.get("provenance")
                    distance = result.get("distance")
                    
                    logger.info(f"Result: {text[:60]}... (provenance: {provenance}, distance: {distance})")
                    
                    if "Sarah" in text or "sister" in text:
                        sarah_found = True
                
                self.assert_test(
                    "Semantic Recall - Sarah Found", 
                    sarah_found,
                    f"Found Sarah-related content in {len(results)} results"
                )
                
                # Check result structure
                if results:
                    first_result = results[0]
                    required_fields = ["node_id", "text", "provenance", "distance"]
                    has_required = all(field in first_result for field in required_fields)
                    
                    self.assert_test(
                        "Recall Result Structure", 
                        has_required,
                        f"Fields: {list(first_result.keys())}"
                    )
            else:
                self.assert_test("Semantic Recall - Query", False, f"HTTP {response.status_code}: {response.text}")
        
        except Exception as e:
            self.assert_test("Semantic Recall - Query", False, f"Error: {e}")
    
    async def test_cross_query_recall(self):
        """Test 5: Cross-query recall - meeting preferences"""
        try:
            recall_data = {
                "user_id": TEST_USERNAME,
                "query": "meeting preferences",
                "n_results": 3
            }
            
            response = requests.post(f"{API_BASE}/memory/recall", json=recall_data, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                
                # Check if morning meeting preference is found
                preference_found = False
                for result in results:
                    text = result.get("text", "")
                    if "morning" in text.lower() or "10am" in text or "meeting" in text.lower():
                        preference_found = True
                        break
                
                self.assert_test(
                    "Cross-Query Recall", 
                    preference_found,
                    f"Found meeting preference in {len(results)} results"
                )
            else:
                self.assert_test("Cross-Query Recall", False, f"HTTP {response.status_code}")
        
        except Exception as e:
            self.assert_test("Cross-Query Recall", False, f"Error: {e}")
    
    async def test_provenance_tracking(self):
        """Test 6: Provenance tracking"""
        try:
            # Store a fact with OBSERVED provenance
            observed_data = {
                "user_id": TEST_USERNAME,
                "text": "User seems to work late on Fridays",
                "fact_type": "FACT",
                "provenance": "OBSERVED"
            }
            
            response = requests.post(f"{API_BASE}/memory/store", json=observed_data, timeout=10)
            
            if response.status_code == 200:
                # Now recall and check provenance
                await asyncio.sleep(1)  # Wait for storage
                
                recall_data = {
                    "user_id": TEST_USERNAME,
                    "query": "work Friday",
                    "n_results": 3
                }
                
                recall_response = requests.post(f"{API_BASE}/memory/recall", json=recall_data, timeout=10)
                
                if recall_response.status_code == 200:
                    results = recall_response.json().get("results", [])
                    
                    observed_found = False
                    for result in results:
                        text = result.get("text", "")
                        provenance = result.get("provenance")
                        
                        if "Friday" in text and provenance == "OBSERVED":
                            observed_found = True
                            break
                    
                    self.assert_test(
                        "Provenance Tracking", 
                        observed_found,
                        f"Found OBSERVED provenance in recall results"
                    )
                else:
                    self.assert_test("Provenance Tracking", False, "Recall failed")
            else:
                self.assert_test("Provenance Tracking", False, f"Store failed: HTTP {response.status_code}")
        
        except Exception as e:
            self.assert_test("Provenance Tracking", False, f"Error: {e}")
    
    async def test_write_policy_enforcement(self):
        """Test 7: Write policy enforcement"""
        try:
            # Test allowed write trigger (user_confirmation)
            allowed_data = {
                "user_id": TEST_USERNAME,
                "text": "Test fact for write policy",
                "fact_type": "FACT",
                "provenance": "EXPLICIT"
            }
            
            response = requests.post(f"{API_BASE}/memory/store", json=allowed_data, timeout=10)
            
            # The endpoint should allow this write (user_confirmation trigger is allowed)
            self.assert_test(
                "Write Policy - Allow", 
                response.status_code == 200,
                f"User confirmation write allowed: {response.status_code}"
            )
            
        except Exception as e:
            self.assert_test("Write Policy - Allow", False, f"Error: {e}")
    
    # Regression Tests
    async def test_regression_sso_ws_auth(self):
        """Test 8: REGRESSION - SSO + WS Auth still working"""
        # Get SSO token
        sso_success = await self.client.get_sso_token()
        self.assert_test("REGRESSION - SSO Token", sso_success, "SSO endpoint working")
        
        if not sso_success:
            return False
        
        # Connect WebSocket 
        ws_success = await self.client.connect_websocket()
        self.assert_test("REGRESSION - WebSocket Auth", ws_success, f"Session: {self.client.session_id}")
        
        return ws_success
    
    async def test_regression_l1_scout_flow(self):
        """Test 9: REGRESSION - L1 Scout text input flow"""
        if not self.client.websocket:
            self.assert_test("REGRESSION - L1 Scout", False, "No WebSocket connection")
            return
        
        # Send heartbeat first
        await self.client.send_heartbeat()
        
        # Test L1 Scout text input
        test_text = "What are my meeting preferences?"
        responses = await self.client.send_text_input(test_text)
        
        # Check for transcript_final and draft_update
        transcript = responses.get("transcript_final")
        draft = responses.get("draft_update")
        tts = responses.get("tts_audio")
        
        flow_working = transcript is not None and tts is not None
        
        self.assert_test(
            "REGRESSION - L1 Scout Flow", 
            flow_working,
            f"Transcript: {transcript is not None}, TTS: {tts is not None}, Draft: {draft is not None}"
        )
    
    async def test_regression_presence_gate(self):
        """Test 10: REGRESSION - Presence gate (16s stale heartbeat)"""
        if not self.client.websocket:
            self.assert_test("REGRESSION - Presence Gate", False, "No WebSocket connection")
            return
        
        # Wait 16+ seconds to make heartbeat stale
        logger.info("Testing presence gate - waiting 16 seconds for stale heartbeat...")
        await asyncio.sleep(16)
        
        # Try to execute without fresh heartbeat
        execute_msg = {
            "type": "execute_request",
            "payload": {
                "session_id": self.client.session_id,
                "draft_id": "test-draft-123"
            }
        }
        await self.client.websocket.send(json.dumps(execute_msg))
        
        # Should get execute_blocked with PRESENCE_STALE
        try:
            response = await asyncio.wait_for(self.client.websocket.recv(), timeout=10)
            msg = json.loads(response)
            
            is_blocked = msg.get("type") == "execute_blocked"
            code = msg.get("payload", {}).get("code")
            
            self.assert_test(
                "REGRESSION - Presence Gate", 
                is_blocked and code == "PRESENCE_STALE",
                f"Type: {msg.get('type')}, Code: {code}"
            )
        except Exception as e:
            self.assert_test("REGRESSION - Presence Gate", False, f"Error: {e}")
    
    async def run_all_tests(self):
        """Run all Digital Self tests"""
        logger.info("🚀 Starting MyndLens Batch 5 Testing — Digital Self (Vector-Graph Memory)")
        
        # Test 1: Health endpoint
        await self.test_health_endpoint()
        
        # Digital Self API Tests
        logger.info("🧠 Testing Digital Self REST APIs...")
        
        # Test 2-3: Store facts and register entities
        await self.test_store_facts_api()
        await self.test_register_entity_api()
        
        # Test 4-6: Recall and provenance
        await self.test_semantic_recall_api()  # MOST IMPORTANT
        await self.test_cross_query_recall()
        await self.test_provenance_tracking()
        
        # Test 7: Write policy
        await self.test_write_policy_enforcement()
        
        # Regression Tests
        logger.info("🔄 Running regression tests...")
        
        # Test 8: SSO + WebSocket setup
        regression_setup = await self.test_regression_sso_ws_auth()
        
        if regression_setup:
            # Test 9-10: L1 Scout and presence gate
            await self.test_regression_l1_scout_flow()
            await self.test_regression_presence_gate()
        else:
            logger.error("❌ Regression setup failed, skipping WebSocket tests")
        
        # Close connection
        await self.client.close()
        
        # Summary
        passed = sum(1 for result in self.test_results.values() if result == "PASS")
        total = len(self.test_results)
        
        logger.info(f"\n🎯 DIGITAL SELF TESTING COMPLETE: {passed}/{total} tests passed")
        
        if passed == total:
            logger.info("✅ ALL TESTS PASSED - Digital Self (Vector-Graph Memory) working correctly!")
        else:
            failed_tests = [name for name, result in self.test_results.items() if result == "FAIL"]
            logger.error(f"❌ FAILED TESTS: {failed_tests}")
        
        return self.test_results

async def main():
    """Run Digital Self (Batch 5) backend tests"""
    tests = DigitalSelfTests()
    await tests.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())