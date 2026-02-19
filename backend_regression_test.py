#!/usr/bin/env python3
"""
REGRESSION TEST for MyndLens Backend - Batch 2 Truth-Audit Patches
Testing critical WebSocket schema payload changes: 
- transcript_partial/transcript_final now use TranscriptPayload (field `text` instead of `message`)
- tts_audio now uses TTSAudioPayload (field `text` instead of `message`)
"""
import asyncio
import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import websockets
from websockets import WebSocketServerProtocol

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Backend URL from frontend .env
BASE_URL = "https://mandate-executor.preview.emergentagent.com"
API_URL = f"{BASE_URL}/api"
WS_URL = f"wss://voice-assistant-dev.preview.emergentagent.com/api/ws"

class RegressionTester:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.test_results = {
            # Critical regression tests for schema changes
            "health_endpoint": False,
            "text_input_flow_schema": False,  # Verify `text` field in transcript_final & tts_audio
            "audio_chunk_schema": False,      # Verify `text` field in transcript_partial
            "presence_gate_16s": False,       # Regression: 16s stale → EXECUTE_BLOCKED
            "auth_rejection": False,          # Regression: invalid token → auth_fail
        }
        self.failed_tests = []
        self.test_token = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def log_test_result(self, test_name: str, success: bool, details: str = ""):
        """Log test results and track failures."""
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {test_name}: {details}")
        
        self.test_results[test_name] = success
        if not success:
            self.failed_tests.append(f"{test_name}: {details}")

    async def test_health_endpoint(self):
        """Test GET /api/health → {status: ok}"""
        try:
            async with self.session.get(f"{API_URL}/health") as response:
                if response.status != 200:
                    self.log_test_result("health_endpoint", False, f"HTTP {response.status}")
                    return

                data = await response.json()
                
                if data.get("status") != "ok":
                    self.log_test_result("health_endpoint", False, f"Status not ok: {data.get('status')}")
                    return

                self.log_test_result("health_endpoint", True, f"Health OK: {data}")

        except Exception as e:
            self.log_test_result("health_endpoint", False, f"Exception: {str(e)}")

    async def setup_auth_token(self):
        """Setup authentication token for tests."""
        try:
            payload = {
                "user_id": "patch_test",
                "device_id": "patch_dev"
            }
            
            async with self.session.post(f"{API_URL}/auth/pair", json=payload) as response:
                if response.status != 200:
                    logger.error(f"Failed to pair device: HTTP {response.status}")
                    return False
                    
                data = await response.json()
                self.test_token = data["token"]
                logger.info(f"Device paired successfully")
                return True

        except Exception as e:
            logger.error(f"Exception during pairing: {str(e)}")
            return False

    async def test_text_input_flow_schema(self):
        """CRITICAL: Test text input → transcript_final → tts_audio flow with new schema fields."""
        if not self.test_token:
            await self.setup_auth_token()

        if not self.test_token:
            self.log_test_result("text_input_flow_schema", False, "No token available")
            return

        try:
            async with websockets.connect(WS_URL) as websocket:
                # Step 1: Authenticate
                auth_msg = {
                    "type": "auth",
                    "id": "1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "token": self.test_token,
                        "device_id": "patch_dev"
                    }
                }
                
                await websocket.send(json.dumps(auth_msg))
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "auth_ok":
                    self.log_test_result("text_input_flow_schema", False, f"Auth failed: {data.get('type')}")
                    return
                
                session_id = data.get("payload", {}).get("session_id")
                logger.info(f"Authenticated, session_id: {session_id}")

                # Step 2: Send heartbeat to establish presence
                heartbeat_msg = {
                    "type": "heartbeat",
                    "id": "2",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "session_id": session_id,
                        "seq": 1,
                        "client_ts": datetime.now(timezone.utc).isoformat()
                    }
                }
                await websocket.send(json.dumps(heartbeat_msg))
                await websocket.recv()  # consume heartbeat_ack

                # Step 3: Send text input
                text_input_msg = {
                    "type": "text_input",
                    "id": "3",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "session_id": session_id,
                        "text": "Hello send a message"
                    }
                }
                
                await websocket.send(json.dumps(text_input_msg))

                # Step 4: Should receive transcript_final with `payload.text` field (NOT `payload.message`)
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "transcript_final":
                    self.log_test_result("text_input_flow_schema", False, f"Expected transcript_final, got: {data.get('type')}")
                    return

                transcript_payload = data.get("payload", {})
                if "text" not in transcript_payload:
                    self.log_test_result("text_input_flow_schema", False, f"transcript_final missing 'text' field: {transcript_payload}")
                    return
                
                if "message" in transcript_payload:
                    self.log_test_result("text_input_flow_schema", False, f"transcript_final still has old 'message' field: {transcript_payload}")
                    return

                transcript_text = transcript_payload["text"]
                logger.info(f"✓ transcript_final has correct 'text' field: {transcript_text}")

                # Step 5: Should receive tts_audio with `payload.text` field (NOT `payload.message`)
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "tts_audio":
                    self.log_test_result("text_input_flow_schema", False, f"Expected tts_audio, got: {data.get('type')}")
                    return

                tts_payload = data.get("payload", {})
                if "text" not in tts_payload:
                    self.log_test_result("text_input_flow_schema", False, f"tts_audio missing 'text' field: {tts_payload}")
                    return
                
                if "message" in tts_payload:
                    self.log_test_result("text_input_flow_schema", False, f"tts_audio still has old 'message' field: {tts_payload}")
                    return

                tts_text = tts_payload["text"]
                logger.info(f"✓ tts_audio has correct 'text' field: {tts_text}")

                self.log_test_result("text_input_flow_schema", True, f"Schema update verified: transcript.text='{transcript_text}', tts.text='{tts_text[:50]}'")

        except Exception as e:
            self.log_test_result("text_input_flow_schema", False, f"Exception: {str(e)}")

    async def test_audio_chunk_schema(self):
        """Test audio chunk flow with new TranscriptPayload schema."""
        if not self.test_token:
            await self.setup_auth_token()

        if not self.test_token:
            self.log_test_result("audio_chunk_schema", False, "No token available")
            return

        try:
            async with websockets.connect(WS_URL) as websocket:
                # Authenticate
                auth_msg = {
                    "type": "auth",
                    "id": "1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "token": self.test_token,
                        "device_id": "patch_dev"
                    }
                }
                
                await websocket.send(json.dumps(auth_msg))
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "auth_ok":
                    self.log_test_result("audio_chunk_schema", False, f"Auth failed: {data.get('type')}")
                    return
                
                session_id = data.get("payload", {}).get("session_id")

                # Send heartbeat for presence
                heartbeat_msg = {
                    "type": "heartbeat",
                    "id": "2",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "session_id": session_id,
                        "seq": 1,
                        "client_ts": datetime.now(timezone.utc).isoformat()
                    }
                }
                await websocket.send(json.dumps(heartbeat_msg))
                await websocket.recv()  # consume heartbeat_ack

                # Send 8 audio chunks (base64 encoded random 1KB)
                schema_verified = False
                for i in range(1, 9):
                    fake_audio = base64.b64encode(os.urandom(1024)).decode()
                    audio_chunk_msg = {
                        "type": "audio_chunk",
                        "id": f"chunk{i}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "payload": {
                            "session_id": session_id,
                            "audio": fake_audio,
                            "seq": i
                        }
                    }
                    
                    await websocket.send(json.dumps(audio_chunk_msg))
                    
                    # Every 4 chunks should produce transcript_partial
                    if i % 4 == 0:
                        response = await websocket.recv()
                        data = json.loads(response)
                        
                        if data.get("type") == "transcript_partial":
                            partial_payload = data.get("payload", {})
                            
                            # Verify new schema fields
                            if "text" not in partial_payload:
                                self.log_test_result("audio_chunk_schema", False, f"transcript_partial missing 'text' field: {partial_payload}")
                                return
                            
                            if "message" in partial_payload:
                                self.log_test_result("audio_chunk_schema", False, f"transcript_partial still has old 'message' field: {partial_payload}")
                                return

                            # Verify required fields exist
                            required_fields = ["text", "is_final", "confidence", "span_ids"]
                            missing = [f for f in required_fields if f not in partial_payload]
                            if missing:
                                self.log_test_result("audio_chunk_schema", False, f"transcript_partial missing required fields: {missing}")
                                return

                            partial_text = partial_payload["text"]
                            logger.info(f"✓ transcript_partial chunk {i} has correct schema: text='{partial_text}', is_final={partial_payload['is_final']}, confidence={partial_payload['confidence']}")
                            schema_verified = True

                if schema_verified:
                    self.log_test_result("audio_chunk_schema", True, "Audio chunk flow - TranscriptPayload schema verified with 'text' field")
                else:
                    self.log_test_result("audio_chunk_schema", False, "No transcript_partial received to verify schema")

        except Exception as e:
            self.log_test_result("audio_chunk_schema", False, f"Exception: {str(e)}")

    async def test_presence_gate_16s(self):
        """REGRESSION: Test presence gate - 16s stale → EXECUTE_BLOCKED with PRESENCE_STALE."""
        if not self.test_token:
            await self.setup_auth_token()

        if not self.test_token:
            self.log_test_result("presence_gate_16s", False, "No token available")
            return

        try:
            async with websockets.connect(WS_URL) as websocket:
                # Authenticate
                auth_msg = {
                    "type": "auth",
                    "id": "1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "token": self.test_token,
                        "device_id": "patch_dev"
                    }
                }
                
                await websocket.send(json.dumps(auth_msg))
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "auth_ok":
                    self.log_test_result("presence_gate_16s", False, f"Auth failed: {data.get('type')}")
                    return
                
                session_id = data.get("payload", {}).get("session_id")
                logger.info(f"Presence gate test authenticated, session: {session_id}")

                # DO NOT send heartbeat - wait 16 seconds for stale
                logger.info("Waiting 16 seconds for heartbeat to go stale...")
                await asyncio.sleep(16)

                # Send execute request - should be blocked
                execute_msg = {
                    "type": "execute_request",
                    "id": "3",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "session_id": session_id,
                        "draft_id": "draft-presence-test"
                    }
                }
                
                await websocket.send(json.dumps(execute_msg))
                
                # Should receive EXECUTE_BLOCKED with PRESENCE_STALE
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "execute_blocked":
                    self.log_test_result("presence_gate_16s", False, f"Expected execute_blocked, got: {data.get('type')}")
                    return
                
                block_code = data.get("payload", {}).get("code")
                if block_code != "PRESENCE_STALE":
                    self.log_test_result("presence_gate_16s", False, f"Expected PRESENCE_STALE, got: {block_code}")
                    return
                
                self.log_test_result("presence_gate_16s", True, "Presence gate correctly blocks stale heartbeat after 16s")

        except Exception as e:
            self.log_test_result("presence_gate_16s", False, f"Exception: {str(e)}")

    async def test_auth_rejection(self):
        """REGRESSION: Test auth rejection - invalid token → auth_fail."""
        try:
            async with websockets.connect(WS_URL) as websocket:
                # Send AUTH with invalid token
                auth_msg = {
                    "type": "auth",
                    "id": "1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "token": "invalid.jwt.token",
                        "device_id": "patch_dev"
                    }
                }
                
                await websocket.send(json.dumps(auth_msg))
                
                # Should receive auth_fail
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "auth_fail":
                    self.log_test_result("auth_rejection", False, f"Expected auth_fail, got: {data.get('type')}")
                    return
                
                self.log_test_result("auth_rejection", True, "Invalid token correctly rejected with auth_fail")

        except websockets.ConnectionClosedError as e:
            # Connection should be closed after auth failure
            if e.code == 4003:  # Auth failed code
                self.log_test_result("auth_rejection", True, "Connection closed with auth failure code 4003")
            else:
                self.log_test_result("auth_rejection", False, f"Unexpected close code: {e.code}")
        except Exception as e:
            self.log_test_result("auth_rejection", False, f"Exception: {str(e)}")

    async def run_regression_tests(self):
        """Run all regression tests focusing on schema changes."""
        logger.info("=" * 80)
        logger.info("MYNDLENS BATCH 2 REGRESSION TEST - WebSocket Schema Changes")
        logger.info("=" * 80)
        logger.info("CRITICAL: Testing transcript_partial/transcript_final/tts_audio field changes")
        logger.info("OLD: payload.message → NEW: payload.text")
        logger.info("=" * 80)
        
        # Run critical regression tests
        await self.test_health_endpoint()
        await self.test_text_input_flow_schema()    # CRITICAL: Verify text field in transcript_final & tts_audio
        await self.test_audio_chunk_schema()        # CRITICAL: Verify text field in transcript_partial 
        await self.test_presence_gate_16s()         # REGRESSION: Ensure presence gate still works
        await self.test_auth_rejection()            # REGRESSION: Ensure auth rejection still works
        
        # Summary
        logger.info("=" * 80)
        logger.info("REGRESSION TEST SUMMARY")
        logger.info("=" * 80)
        
        passed = sum(1 for result in self.test_results.values() if result)
        total = len(self.test_results)
        
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result else "❌ FAIL" 
            logger.info(f"{status} {test_name}")
        
        logger.info("-" * 50)
        logger.info(f"TOTAL: {passed}/{total} tests passed")
        
        if self.failed_tests:
            logger.info("\n❌ FAILED TESTS:")
            for failure in self.failed_tests:
                logger.info(f"  {failure}")
        else:
            logger.info("\n🎉 ALL REGRESSION TESTS PASSED!")
            logger.info("Schema changes working correctly: message → text")
        
        return passed == total

async def main():
    """Main regression test runner."""
    async with RegressionTester() as tester:
        success = await tester.run_regression_tests()
        return success

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)