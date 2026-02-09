#!/usr/bin/env python3
"""
MyndLens Dynamic Prompt Compliance Enforcement Testing

Critical Tests:
1. Compliance endpoint GET /api/prompt/compliance 
2. L1 Scout still works through gateway (MOST CRITICAL)
3. Prompt snapshots persist with THOUGHT_TO_INTENT purpose
4. REGRESSION: Health, SSO, WS auth, presence gate, memory APIs

Backend URL: https://voice-assistant-dev.preview.emergentagent.com/api
"""
import asyncio
import json
import time
import base64
import websockets
from typing import Dict, Any, List
import aiohttp
import logging

# Configure logging to see backend interactions
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKEND_URL = "https://voice-assistant-dev.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"
WS_URL = f"{BACKEND_URL.replace('https://', 'wss://')}/api/ws"

class TestSession:
    def __init__(self):
        self.session = None
        self.token = None
        self.session_id = None
        self.ws = None
        self.test_results = []
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()
            
    def log_result(self, test_name: str, success: bool, details: str = ""):
        self.test_results.append({
            "test": test_name,
            "success": success, 
            "details": details
        })
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status}: {test_name} - {details}")


async def test_compliance_endpoint(test_session: TestSession):
    """Test 1: Compliance endpoint GET /api/prompt/compliance"""
    logger.info("=== Testing Compliance Endpoint ===")
    
    try:
        async with test_session.session.get(f"{API_BASE}/prompt/compliance") as response:
            if response.status != 200:
                test_session.log_result("Compliance Endpoint", False, f"HTTP {response.status}")
                return False
                
            data = await response.json()
            
            # Check call_sites (should have 7 entries)
            call_sites = data.get("call_sites", [])
            if len(call_sites) != 7:
                test_session.log_result("Compliance Endpoint - Call Sites", False, 
                    f"Expected 7 call sites, got {len(call_sites)}")
                return False
                
            # Check required fields
            required_fields = ["call_sites", "stable_hashes", "bypass_attempts", "rogue_prompt_scan"]
            for field in required_fields:
                if field not in data:
                    test_session.log_result("Compliance Endpoint", False, f"Missing field: {field}")
                    return False
                    
            # Check bypass attempts (should be 0)
            bypass_count = data["bypass_attempts"].get("total_count", -1)
            if bypass_count != 0:
                test_session.log_result("Compliance Endpoint - Bypass Attempts", False, 
                    f"Expected 0 bypass attempts, got {bypass_count}")
                return False
                
            # Check rogue prompt scan (should be clean=true, violations=[])
            rogue_scan = data["rogue_prompt_scan"]
            if not rogue_scan.get("clean", False):
                test_session.log_result("Compliance Endpoint - Rogue Scan", False, 
                    f"Rogue scan not clean: {rogue_scan}")
                return False
                
            if len(rogue_scan.get("violations", [])) > 0:
                test_session.log_result("Compliance Endpoint - Rogue Violations", False, 
                    f"Found rogue violations: {rogue_scan['violations']}")
                return False
                
            test_session.log_result("Compliance Endpoint", True, 
                f"All checks passed: {len(call_sites)} call sites, {bypass_count} bypass attempts, clean scan")
            return True
            
    except Exception as e:
        test_session.log_result("Compliance Endpoint", False, f"Exception: {str(e)}")
        return False


async def test_sso_login(test_session: TestSession):
    """Test SSO login for L1 Scout testing"""
    logger.info("=== Testing SSO Login ===")
    
    try:
        login_data = {
            "username": "compliance_test",
            "password": "p", 
            "device_id": "cdev"
        }
        
        async with test_session.session.post(f"{API_BASE}/sso/myndlens/token", 
                                           json=login_data) as response:
            if response.status != 200:
                test_session.log_result("SSO Login", False, f"HTTP {response.status}")
                return False
                
            data = await response.json()
            test_session.token = data.get("token")
            
            if not test_session.token:
                test_session.log_result("SSO Login", False, "No token received")
                return False
                
            test_session.log_result("SSO Login", True, f"Token received: {test_session.token[:20]}...")
            return True
            
    except Exception as e:
        test_session.log_result("SSO Login", False, f"Exception: {str(e)}")
        return False


async def test_websocket_auth_heartbeat(test_session: TestSession):
    """Test WebSocket connection, authentication, and heartbeat"""
    logger.info("=== Testing WebSocket Auth & Heartbeat ===")
    
    try:
        logger.info(f"Connecting to WebSocket: {WS_URL}")
        
        # Add extra headers for proper connection
        extra_headers = {
            "Origin": BACKEND_URL,
            "User-Agent": "MyndLens-Test-Client/1.0"
        }
        
        # Connect to WebSocket with extra headers
        test_session.ws = await websockets.connect(
            WS_URL, 
            extra_headers=extra_headers,
            ping_interval=None,
            ping_timeout=None
        )
        logger.info("WebSocket connected successfully")
        
        # Send auth message
        auth_msg = {
            "type": "auth",
            "payload": {
                "token": test_session.token,
                "device_id": "cdev",
                "client_version": "1.0.0"
            }
        }
        logger.info(f"Sending auth message: {auth_msg['type']}")
        await test_session.ws.send(json.dumps(auth_msg))
        
        # Wait for auth response
        logger.info("Waiting for auth response...")
        response = await asyncio.wait_for(test_session.ws.recv(), timeout=10)
        auth_response = json.loads(response)
        logger.info(f"Auth response: {auth_response}")
        
        if auth_response.get("type") != "auth_ok":
            test_session.log_result("WebSocket Auth", False, f"Auth failed: {auth_response}")
            return False
            
        test_session.session_id = auth_response.get("payload", {}).get("session_id")
        if not test_session.session_id:
            test_session.log_result("WebSocket Auth", False, "No session_id received")
            return False
            
        # Send heartbeat
        heartbeat_msg = {
            "type": "heartbeat",
            "payload": {"session_id": test_session.session_id}
        }
        logger.info(f"Sending heartbeat: {heartbeat_msg['type']}")
        await test_session.ws.send(json.dumps(heartbeat_msg))
        
        # Wait for heartbeat ack
        logger.info("Waiting for heartbeat ack...")
        response = await asyncio.wait_for(test_session.ws.recv(), timeout=10)
        heartbeat_response = json.loads(response)
        logger.info(f"Heartbeat response: {heartbeat_response}")
        
        if heartbeat_response.get("type") != "heartbeat_ack":
            test_session.log_result("WebSocket Heartbeat", False, f"Heartbeat failed: {heartbeat_response}")
            return False
            
        test_session.log_result("WebSocket Auth & Heartbeat", True, 
            f"Session {test_session.session_id[:8]} authenticated and heartbeat OK")
        return True
        
    except websockets.exceptions.ConnectionClosed as e:
        test_session.log_result("WebSocket Auth & Heartbeat", False, f"Connection closed: {e}")
        return False
    except asyncio.TimeoutError as e:
        test_session.log_result("WebSocket Auth & Heartbeat", False, f"Timeout waiting for response")
        return False
    except Exception as e:
        test_session.log_result("WebSocket Auth & Heartbeat", False, f"Exception: {str(e)}")
        return False


async def test_l1_scout_gateway_flow(test_session: TestSession):
    """Test L1 Scout through gateway (MOST CRITICAL TEST)"""
    logger.info("=== Testing L1 Scout Gateway Flow (MOST CRITICAL) ===")
    
    try:
        # Send text input to trigger L1 Scout
        text_input_msg = {
            "type": "text_input",
            "payload": {
                "text": "Send a message to Sarah about the meeting tomorrow",
                "session_id": test_session.session_id
            }
        }
        await test_session.ws.send(json.dumps(text_input_msg))
        
        # Collect responses
        responses = []
        draft_update_received = False
        tts_audio_received = False
        
        # Wait for multiple responses (transcript_final, draft_update, tts_audio)
        for _ in range(5):  # Max 5 responses expected
            try:
                response = await asyncio.wait_for(test_session.ws.recv(), timeout=15)
                msg = json.loads(response)
                responses.append(msg)
                
                msg_type = msg.get("type")
                if msg_type == "draft_update":
                    draft_update_received = True
                    # Check for hypothesis and dimensions in draft_update
                    payload = msg.get("payload", {})
                    hypotheses = payload.get("hypotheses", [])
                    if len(hypotheses) > 0:
                        test_session.log_result("L1 Scout - Hypothesis Generation", True,
                            f"Generated {len(hypotheses)} hypotheses")
                    else:
                        test_session.log_result("L1 Scout - Hypothesis Generation", False,
                            "No hypotheses in draft_update")
                        
                elif msg_type == "tts_audio":
                    tts_audio_received = True
                    
            except asyncio.TimeoutError:
                break
                
        # Check if we received expected messages
        if not draft_update_received:
            test_session.log_result("L1 Scout - Draft Update", False, "No draft_update message received")
            return False
            
        if not tts_audio_received:
            test_session.log_result("L1 Scout - TTS Response", False, "No tts_audio message received")
            return False
            
        test_session.log_result("L1 Scout Gateway Flow", True, 
            f"Complete flow working: draft_update and tts_audio received. Total responses: {len(responses)}")
        return True
        
    except Exception as e:
        test_session.log_result("L1 Scout Gateway Flow", False, f"Exception: {str(e)}")
        return False


async def test_prompt_snapshots_persistence(test_session: TestSession):
    """Test that prompt snapshots persist with THOUGHT_TO_INTENT purpose"""
    logger.info("=== Testing Prompt Snapshots Persistence ===")
    
    try:
        # Wait a moment for the L1 call to be processed and snapshot saved
        await asyncio.sleep(2)
        
        # Check compliance endpoint again for snapshots
        async with test_session.session.get(f"{API_BASE}/prompt/compliance") as response:
            if response.status != 200:
                test_session.log_result("Prompt Snapshots Check", False, f"HTTP {response.status}")
                return False
                
            data = await response.json()
            snapshots_by_purpose = data.get("snapshots_by_purpose", {})
            
            # Check for THOUGHT_TO_INTENT snapshots
            thought_to_intent_snaps = snapshots_by_purpose.get("THOUGHT_TO_INTENT", [])
            if len(thought_to_intent_snaps) == 0:
                test_session.log_result("Prompt Snapshots Persistence", False, 
                    "No THOUGHT_TO_INTENT snapshots found")
                return False
                
            # Check snapshot structure
            latest_snap = thought_to_intent_snaps[0]
            required_fields = ["prompt_id", "purpose", "stable_hash", "created_at"]
            for field in required_fields:
                if field not in latest_snap:
                    test_session.log_result("Prompt Snapshots Persistence", False,
                        f"Missing field in snapshot: {field}")
                    return False
                    
            test_session.log_result("Prompt Snapshots Persistence", True,
                f"THOUGHT_TO_INTENT snapshot found: {latest_snap['prompt_id']}")
            return True
            
    except Exception as e:
        test_session.log_result("Prompt Snapshots Persistence", False, f"Exception: {str(e)}")
        return False


async def test_health_regression(test_session: TestSession):
    """Test Health endpoint regression"""
    logger.info("=== Testing Health Regression ===")
    
    try:
        async with test_session.session.get(f"{API_BASE}/health") as response:
            if response.status != 200:
                test_session.log_result("Health Regression", False, f"HTTP {response.status}")
                return False
                
            data = await response.json()
            if data.get("status") != "ok":
                test_session.log_result("Health Regression", False, f"Status not OK: {data}")
                return False
                
            test_session.log_result("Health Regression", True, "Health endpoint working")
            return True
            
    except Exception as e:
        test_session.log_result("Health Regression", False, f"Exception: {str(e)}")
        return False


async def test_presence_gate_regression(test_session: TestSession):
    """Test presence gate still blocks stale heartbeat"""
    logger.info("=== Testing Presence Gate Regression ===")
    
    try:
        # Wait 16 seconds to make heartbeat stale
        logger.info("Waiting 16 seconds for heartbeat to become stale...")
        await asyncio.sleep(16)
        
        # Try to send execute request (should be blocked)
        execute_msg = {
            "type": "execute_request",
            "payload": {"session_id": test_session.session_id}
        }
        await test_session.ws.send(json.dumps(execute_msg))
        
        # Wait for response
        response = await asyncio.wait_for(test_session.ws.recv(), timeout=10)
        execute_response = json.loads(response)
        
        # Should receive EXECUTE_BLOCKED with PRESENCE_STALE
        if execute_response.get("type") != "execute_blocked":
            test_session.log_result("Presence Gate Regression", False, 
                f"Expected execute_blocked, got: {execute_response}")
            return False
            
        payload = execute_response.get("payload", {})
        if payload.get("code") != "PRESENCE_STALE":
            test_session.log_result("Presence Gate Regression", False,
                f"Expected PRESENCE_STALE code, got: {payload}")
            return False
            
        test_session.log_result("Presence Gate Regression", True, 
            "Presence gate correctly blocked stale session")
        return True
        
    except Exception as e:
        test_session.log_result("Presence Gate Regression", False, f"Exception: {str(e)}")
        return False


async def test_memory_api_regression(test_session: TestSession):
    """Test memory APIs regression"""
    logger.info("=== Testing Memory API Regression ===")
    
    try:
        # Test memory store
        store_data = {
            "user_id": "compliance_test",
            "text": "Sarah works at TechCorp",
            "fact_type": "FACT",
            "provenance": "EXPLICIT"
        }
        
        async with test_session.session.post(f"{API_BASE}/memory/store", 
                                           json=store_data) as response:
            if response.status != 200:
                test_session.log_result("Memory Store Regression", False, f"HTTP {response.status}")
                return False
                
            data = await response.json()
            if data.get("status") != "stored":
                test_session.log_result("Memory Store Regression", False, f"Store failed: {data}")
                return False
        
        # Test memory recall
        recall_data = {
            "user_id": "compliance_test",
            "query": "Who is Sarah?",
            "n_results": 3
        }
        
        async with test_session.session.post(f"{API_BASE}/memory/recall",
                                           json=recall_data) as response:
            if response.status != 200:
                test_session.log_result("Memory Recall Regression", False, f"HTTP {response.status}")
                return False
                
            data = await response.json()
            results = data.get("results", [])
            if len(results) == 0:
                test_session.log_result("Memory Recall Regression", False, "No recall results")
                return False
                
        test_session.log_result("Memory API Regression", True, 
            f"Store and recall working, {len(results)} results found")
        return True
        
    except Exception as e:
        test_session.log_result("Memory API Regression", False, f"Exception: {str(e)}")
        return False


async def main():
    """Run all compliance enforcement tests"""
    logger.info("🔒 STARTING MyndLens Dynamic Prompt Compliance Enforcement Testing 🔒")
    
    async with TestSession() as test_session:
        # Critical tests in order
        tests = [
            ("Compliance Endpoint", test_compliance_endpoint),
            ("SSO Login", test_sso_login),
            ("WebSocket Auth & Heartbeat", test_websocket_auth_heartbeat),
            ("L1 Scout Gateway Flow (MOST CRITICAL)", test_l1_scout_gateway_flow),
            ("Prompt Snapshots Persistence", test_prompt_snapshots_persistence),
            ("Health Regression", test_health_regression),
            ("Presence Gate Regression", test_presence_gate_regression),
            ("Memory API Regression", test_memory_api_regression),
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            logger.info(f"\n--- Running {test_name} ---")
            try:
                result = await test_func(test_session)
                if result:
                    passed += 1
            except Exception as e:
                test_session.log_result(test_name, False, f"Unhandled exception: {str(e)}")
                
        # Print summary
        logger.info(f"\n🔒 COMPLIANCE ENFORCEMENT TEST SUMMARY 🔒")
        logger.info(f"Passed: {passed}/{total} tests")
        
        if passed == total:
            logger.info("🎉 ALL COMPLIANCE TESTS PASSED! 🎉")
        else:
            logger.info(f"⚠️  {total - passed} TESTS FAILED")
            
        # Print detailed results
        logger.info("\n--- DETAILED RESULTS ---")
        for result in test_session.test_results:
            status = "✅" if result["success"] else "❌"
            logger.info(f"{status} {result['test']}: {result['details']}")
            
        return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)