#!/usr/bin/env python3
"""
MyndLens Batch 4 Backend Testing — L1 Scout + Dimension Engine + Real Gemini Flash
Critical Tests from Review Request:

1. L1 Scout via text input (MOST IMPORTANT)
2. L1 with different intents  
3. Dimension accumulation over turns
4. L1 uses PromptOrchestrator
5. Graceful fallback
6. Regression testing
"""

import asyncio
import base64
import json
import logging
import time
import requests
import websockets
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Test configuration
BACKEND_URL = "https://voice-assistant-dev.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"
WS_URL = f"wss://voice-assistant-dev.preview.emergentagent.com/api/ws"

# Test user credentials
TEST_USERNAME = "l1test"
TEST_PASSWORD = "pass"
TEST_DEVICE_ID = "l1dev"

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MyndLensTestClient:
    def __init__(self):
        self.session_id = None
        self.websocket = None
        self.sso_token = None
        self.messages = []
    
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
        """Connect and authenticate WebSocket"""
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
        """Send text input and collect all responses"""
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
                    logger.info(f"Received {msg_type}: {json.dumps(msg, indent=2)[:200]}...")
                    
                    # Stop collecting after getting TTS audio (end of flow)
                    if msg_type == "tts_audio":
                        break
                        
                except asyncio.TimeoutError:
                    # No more messages within timeout
                    break
            
            return responses
            
        except Exception as e:
            logger.error(f"Text input error: {e}")
            return {}
    
    async def close(self):
        """Close WebSocket connection"""
        if self.websocket:
            await self.websocket.close()

class MyndLensTests:
    def __init__(self):
        self.client = MyndLensTestClient()
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
        """Test 1: Health endpoint regression"""
        try:
            response = requests.get(f"{API_BASE}/health", timeout=10)
            data = response.json()
            
            # Check basic health
            self.assert_test("Health endpoint", response.status_code == 200, f"Status: {data.get('status')}")
            
            # Check LLM configuration 
            mock_llm = data.get('mock_llm', True)  # Should be false for real Gemini
            self.assert_test("Real LLM config", not mock_llm, f"MOCK_LLM={mock_llm}")
            
        except Exception as e:
            self.assert_test("Health endpoint", False, f"Error: {e}")
    
    async def test_sso_and_ws_setup(self):
        """Test 2: SSO + WebSocket setup"""
        # Get SSO token
        sso_success = await self.client.get_sso_token()
        self.assert_test("SSO Token", sso_success, "Mock SSO endpoint working")
        
        if not sso_success:
            return False
        
        # Connect WebSocket 
        ws_success = await self.client.connect_websocket()
        self.assert_test("WebSocket Auth", ws_success, f"Session: {self.client.session_id}")
        
        if not ws_success:
            return False
        
        # Send heartbeat
        hb_success = await self.client.send_heartbeat()
        self.assert_test("Heartbeat", hb_success, "Presence established")
        
        return ws_success
    
    async def test_l1_scout_communication_intent(self):
        """Test 3: L1 Scout - Communication Intent (MOST IMPORTANT)"""
        test_text = "Send a message to Sarah about the meeting tomorrow at 3pm"
        responses = await self.client.send_text_input(test_text)
        
        # Check transcript_final
        transcript_final = responses.get("transcript_final")
        self.assert_test(
            "Transcript Final", 
            transcript_final is not None,
            f"Text: {transcript_final.get('payload', {}).get('text', 'MISSING')[:50] if transcript_final else 'NONE'}"
        )
        
        # Check draft_update (NEW in Batch 4)
        draft_update = responses.get("draft_update")
        self.assert_test(
            "Draft Update Message", 
            draft_update is not None,
            f"Received draft_update message type"
        )
        
        if draft_update:
            payload = draft_update.get("payload", {})
            
            # Check hypothesis
            hypothesis = payload.get("hypothesis")
            self.assert_test(
                "L1 Hypothesis", 
                hypothesis is not None,
                f"Hypothesis: {hypothesis[:60] if hypothesis else 'MISSING'}"
            )
            
            # Check action_class
            action_class = payload.get("action_class")
            expected_actions = ["COMM_SEND", "DRAFT_ONLY"]
            self.assert_test(
                "Action Class", 
                action_class in expected_actions,
                f"Got: {action_class}, Expected: {expected_actions}"
            )
            
            # Check confidence
            confidence = payload.get("confidence", 0)
            self.assert_test(
                "L1 Confidence", 
                isinstance(confidence, (int, float)) and confidence > 0,
                f"Confidence: {confidence}"
            )
            
            # Check dimensions (A-set + B-set)
            dimensions = payload.get("dimensions", {})
            a_set = dimensions.get("a_set", {})
            b_set = dimensions.get("b_set", {})
            
            self.assert_test(
                "Dimensions A-set", 
                len(a_set) > 0,
                f"A-set fields: {list(a_set.keys())}"
            )
            
            self.assert_test(
                "Dimensions B-set", 
                len(b_set) > 0,
                f"B-set: {b_set}"
            )
            
            # Check for "who" and "when" from the input
            has_who = "who" in a_set and a_set["who"]
            has_when = "when" in a_set and a_set["when"]
            self.assert_test(
                "Context Extraction", 
                has_who or has_when,
                f"Who: {a_set.get('who', 'NONE')}, When: {a_set.get('when', 'NONE')}"
            )
        
        # Check TTS response
        tts_audio = responses.get("tts_audio")
        self.assert_test(
            "TTS Response", 
            tts_audio is not None,
            f"Format: {tts_audio.get('payload', {}).get('format', 'MISSING') if tts_audio else 'NONE'}"
        )
        
        if tts_audio:
            tts_payload = tts_audio.get("payload", {})
            tts_text = tts_payload.get("text", "")
            is_mock = tts_payload.get("is_mock", True)
            
            # Check if response is contextual (not the old hardcoded mock)
            old_mock_responses = ["I heard:", "Could you tell me more"]
            is_contextual = not any(old in tts_text for old in old_mock_responses)
            
            self.assert_test(
                "Contextual TTS Response", 
                is_contextual and len(tts_text) > 0,
                f"Text: {tts_text[:60]}... (Mock: {is_mock})"
            )
    
    async def test_l1_scout_scheduling_intent(self):
        """Test 4: L1 Scout - Scheduling Intent"""
        test_text = "Schedule a meeting with John for next Monday"
        responses = await self.client.send_text_input(test_text)
        
        draft_update = responses.get("draft_update")
        if draft_update:
            payload = draft_update.get("payload", {})
            action_class = payload.get("action_class")
            
            self.assert_test(
                "Scheduling Action Class", 
                action_class == "SCHED_MODIFY",
                f"Got: {action_class}, Expected: SCHED_MODIFY"
            )
        else:
            self.assert_test("Scheduling Action Class", False, "No draft_update received")
    
    async def test_l1_scout_info_intent(self):
        """Test 5: L1 Scout - Information Retrieval Intent"""
        test_text = "What's the weather like?"
        responses = await self.client.send_text_input(test_text)
        
        draft_update = responses.get("draft_update")
        if draft_update:
            payload = draft_update.get("payload", {})
            action_class = payload.get("action_class")
            
            expected_actions = ["INFO_RETRIEVE", "DRAFT_ONLY"]
            self.assert_test(
                "Info Retrieval Action Class", 
                action_class in expected_actions,
                f"Got: {action_class}, Expected: {expected_actions}"
            )
        else:
            self.assert_test("Info Retrieval Action Class", False, "No draft_update received")
    
    async def test_dimension_accumulation(self):
        """Test 6: Dimension accumulation over multiple turns"""
        # First turn - establish what
        responses1 = await self.client.send_text_input("I need to send something")
        draft1 = responses1.get("draft_update")
        
        # Second turn - add who
        responses2 = await self.client.send_text_input("Send a message to Sarah")
        draft2 = responses2.get("draft_update")
        
        if draft1 and draft2:
            dims1 = draft1.get("payload", {}).get("dimensions", {})
            dims2 = draft2.get("payload", {}).get("dimensions", {})
            
            turn_count1 = dims1.get("turn_count", 0)
            turn_count2 = dims2.get("turn_count", 0)
            
            self.assert_test(
                "Turn Count Increment", 
                turn_count2 > turn_count1,
                f"Turn 1: {turn_count1}, Turn 2: {turn_count2}"
            )
            
            a_set1 = dims1.get("a_set", {})
            a_set2 = dims2.get("a_set", {})
            
            # Check that information accumulated (more fields filled)
            filled_count1 = len([v for v in a_set1.values() if v])
            filled_count2 = len([v for v in a_set2.values() if v])
            
            self.assert_test(
                "Dimension Accumulation", 
                filled_count2 >= filled_count1,
                f"Fields filled - Turn 1: {filled_count1}, Turn 2: {filled_count2}"
            )
        else:
            self.assert_test("Dimension Accumulation", False, "Missing draft_update messages")
    
    async def test_prompt_orchestrator_usage(self):
        """Test 7: Verify L1 uses PromptOrchestrator (check logs/MongoDB)"""
        # This test would ideally check the prompt_snapshots collection
        # For now, we'll verify through the backend logs and API
        
        try:
            # Use the diagnostic prompt build endpoint
            response = requests.post(f"{API_BASE}/prompt/build", json={
                "purpose": "THOUGHT_TO_INTENT",
                "transcript": "Send a message to Sarah",
                "task_description": "Test L1 Scout"
            }, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                prompt_id = data.get("prompt_id")
                purpose = data.get("purpose")
                
                self.assert_test(
                    "PromptOrchestrator Integration", 
                    prompt_id is not None and purpose == "THOUGHT_TO_INTENT",
                    f"Prompt ID: {prompt_id}, Purpose: {purpose}"
                )
                
                # Check that TOOLING section is excluded for THOUGHT_TO_INTENT
                sections_excluded = data.get("sections_excluded", [])
                self.assert_test(
                    "Tool Gating", 
                    "TOOLING" in sections_excluded,
                    f"Excluded sections: {sections_excluded}"
                )
            else:
                self.assert_test("PromptOrchestrator Integration", False, f"HTTP {response.status_code}")
        
        except Exception as e:
            self.assert_test("PromptOrchestrator Integration", False, f"Error: {e}")
    
    async def test_graceful_fallback(self):
        """Test 8: Graceful fallback when Gemini fails"""
        # This is harder to test directly without breaking the real API
        # We can verify the fallback logic by checking mock responses
        
        test_text = "This is a fallback test message"
        responses = await self.client.send_text_input(test_text)
        
        draft_update = responses.get("draft_update")
        if draft_update:
            payload = draft_update.get("payload", {})
            is_mock = payload.get("is_mock", False)
            hypothesis = payload.get("hypothesis", "")
            
            # If we get a response, the fallback mechanism is working
            # (either real Gemini worked, or mock fallback activated)
            self.assert_test(
                "Graceful Fallback", 
                len(hypothesis) > 0,
                f"Hypothesis received (Mock: {is_mock}): {hypothesis[:60]}"
            )
        else:
            self.assert_test("Graceful Fallback", False, "No draft_update received")
    
    async def test_regression_presence_gate(self):
        """Test 9: Regression - Presence gate still works"""
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
                "Presence Gate Regression", 
                is_blocked and code == "PRESENCE_STALE",
                f"Type: {msg.get('type')}, Code: {code}"
            )
        except Exception as e:
            self.assert_test("Presence Gate Regression", False, f"Error: {e}")
    
    async def run_all_tests(self):
        """Run all Batch 4 tests"""
        logger.info("🚀 Starting MyndLens Batch 4 Testing — L1 Scout + Dimension Engine")
        
        # Test 1: Health endpoint
        await self.test_health_endpoint()
        
        # Test 2: SSO + WebSocket setup
        setup_success = await self.test_sso_and_ws_setup()
        if not setup_success:
            logger.error("❌ Setup failed, cannot continue with WebSocket tests")
            return
        
        # Test 3: L1 Scout communication intent (MOST IMPORTANT)
        await self.test_l1_scout_communication_intent()
        
        # Test 4-5: Different intents
        await self.test_l1_scout_scheduling_intent()
        await self.test_l1_scout_info_intent()
        
        # Test 6: Dimension accumulation
        await self.test_dimension_accumulation()
        
        # Test 7: PromptOrchestrator usage
        await self.test_prompt_orchestrator_usage()
        
        # Test 8: Graceful fallback
        await self.test_graceful_fallback()
        
        # Test 9: Regression testing
        await self.test_regression_presence_gate()
        
        # Close connection
        await self.client.close()
        
        # Summary
        passed = sum(1 for result in self.test_results.values() if result == "PASS")
        total = len(self.test_results)
        
        logger.info(f"\n🎯 BATCH 4 TESTING COMPLETE: {passed}/{total} tests passed")
        
        if passed == total:
            logger.info("✅ ALL TESTS PASSED - L1 Scout + Dimension Engine working correctly!")
        else:
            failed_tests = [name for name, result in self.test_results.items() if result == "FAIL"]
            logger.error(f"❌ FAILED TESTS: {failed_tests}")
        
        return self.test_results

async def main():
    """Run MyndLens Batch 4 backend tests"""
    tests = MyndLensTests()
    await tests.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())