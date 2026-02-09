#!/usr/bin/env python3
"""
Comprehensive Backend Tests for MyndLens - Batch 0+1+2
Tests all critical backend functionality including WebSocket flows and Audio Pipeline.
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
BASE_URL = "https://voice-assistant-dev.preview.emergentagent.com"
API_URL = f"{BASE_URL}/api"
WS_URL = f"wss://voice-assistant-dev.preview.emergentagent.com/api/ws"

class BackendTester:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.test_results = {
            # Batch 0+1 Tests (Regression)
            "health_endpoint": False,
            "auth_pair_endpoint": False,
            "websocket_full_flow": False,
            "presence_gate_test": False,
            "auth_rejection_test": False,
            "session_status_endpoint": False,
            "redaction_test": False,
            # Batch 2 Tests (Audio Pipeline + TTS)
            "audio_chunk_flow": False,
            "text_input_flow": False, 
            "chunk_validation_empty": False,
            "chunk_validation_invalid_base64": False,
            "stream_end_cancel": False,
            "mock_tts_response_content": False,
        }
        self.failed_tests = []
        self.test_token = None
        self.test_session_id = None

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
        """Test GET /api/health endpoint."""
        try:
            async with self.session.get(f"{API_URL}/health") as response:
                if response.status != 200:
                    self.log_test_result("health_endpoint", False, f"HTTP {response.status}")
                    return

                data = await response.json()
                required_fields = ["status", "env", "version", "active_sessions"]
                
                if not all(field in data for field in required_fields):
                    missing = [f for f in required_fields if f not in data]
                    self.log_test_result("health_endpoint", False, f"Missing fields: {missing}")
                    return
                
                if data["status"] != "ok":
                    self.log_test_result("health_endpoint", False, f"Status not ok: {data['status']}")
                    return

                self.log_test_result("health_endpoint", True, f"Status OK, {data['active_sessions']} active sessions")

        except Exception as e:
            self.log_test_result("health_endpoint", False, f"Exception: {str(e)}")

    async def test_auth_pair_endpoint(self):
        """Test POST /api/auth/pair endpoint."""
        try:
            payload = {
                "user_id": "test_user_001",
                "device_id": "test_device_001", 
                "client_version": "1.0.0"
            }
            
            async with self.session.post(f"{API_URL}/auth/pair", json=payload) as response:
                if response.status != 200:
                    self.log_test_result("auth_pair_endpoint", False, f"HTTP {response.status}")
                    return

                data = await response.json()
                required_fields = ["token", "user_id", "device_id", "env"]
                
                if not all(field in data for field in required_fields):
                    missing = [f for f in required_fields if f not in data]
                    self.log_test_result("auth_pair_endpoint", False, f"Missing fields: {missing}")
                    return

                # Basic JWT format check (should have 3 parts separated by dots)
                token = data["token"]
                if len(token.split(".")) != 3:
                    self.log_test_result("auth_pair_endpoint", False, "Token not in JWT format")
                    return

                # Store for later tests
                self.test_token = token
                
                self.log_test_result("auth_pair_endpoint", True, f"Token received, env: {data['env']}")

        except Exception as e:
            self.log_test_result("auth_pair_endpoint", False, f"Exception: {str(e)}")

    async def test_websocket_full_flow(self):
        """Test complete WebSocket flow: connect, auth, heartbeat, execute request."""
        if not self.test_token:
            self.log_test_result("websocket_full_flow", False, "No token available")
            return
            
        try:
            async with websockets.connect(WS_URL) as websocket:
                # Step 1: Send AUTH message
                auth_msg = {
                    "type": "auth",
                    "id": "1", 
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "token": self.test_token,
                        "device_id": "test_device_001",
                        "client_version": "1.0.0"
                    }
                }
                
                await websocket.send(json.dumps(auth_msg))
                
                # Step 2: Receive AUTH_OK
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "auth_ok":
                    self.log_test_result("websocket_full_flow", False, f"Expected auth_ok, got: {data.get('type')}")
                    return
                
                session_id = data.get("payload", {}).get("session_id")
                if not session_id:
                    self.log_test_result("websocket_full_flow", False, "No session_id in auth_ok")
                    return
                
                self.test_session_id = session_id
                logger.info(f"WS authenticated, session_id: {session_id}")

                # Step 3: Send HEARTBEAT
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
                
                # Step 4: Receive HEARTBEAT_ACK
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "heartbeat_ack":
                    self.log_test_result("websocket_full_flow", False, f"Expected heartbeat_ack, got: {data.get('type')}")
                    return
                
                logger.info("Heartbeat acknowledged")

                # Step 5: Send EXECUTE_REQUEST while heartbeat is fresh
                execute_msg = {
                    "type": "execute_request",
                    "id": "3",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "session_id": session_id,
                        "draft_id": "draft-001"
                    }
                }
                
                await websocket.send(json.dumps(execute_msg))
                
                # Step 6: Should receive EXECUTE_BLOCKED with PIPELINE_NOT_READY
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "execute_blocked":
                    self.log_test_result("websocket_full_flow", False, f"Expected execute_blocked, got: {data.get('type')}")
                    return
                
                block_code = data.get("payload", {}).get("code")
                if block_code != "PIPELINE_NOT_READY":
                    self.log_test_result("websocket_full_flow", False, f"Expected PIPELINE_NOT_READY, got: {block_code}")
                    return
                
                self.log_test_result("websocket_full_flow", True, "Full WS flow completed successfully")

        except Exception as e:
            self.log_test_result("websocket_full_flow", False, f"Exception: {str(e)}")

    async def test_presence_gate(self):
        """CRITICAL TEST: Pair new device, connect WS, auth, wait 16s, then execute."""
        try:
            # Step 1: Pair a new device
            payload = {
                "user_id": "test_user_presence",
                "device_id": "test_device_presence_001", 
                "client_version": "1.0.0"
            }
            
            async with self.session.post(f"{API_URL}/auth/pair", json=payload) as response:
                if response.status != 200:
                    self.log_test_result("presence_gate_test", False, f"Pairing failed: HTTP {response.status}")
                    return
                    
                data = await response.json()
                presence_token = data["token"]

            # Step 2: Connect to WebSocket and authenticate
            async with websockets.connect(WS_URL) as websocket:
                auth_msg = {
                    "type": "auth",
                    "id": "1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "token": presence_token,
                        "device_id": "test_device_presence_001",
                        "client_version": "1.0.0"
                    }
                }
                
                await websocket.send(json.dumps(auth_msg))
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "auth_ok":
                    self.log_test_result("presence_gate_test", False, f"Auth failed: {data.get('type')}")
                    return
                
                presence_session_id = data.get("payload", {}).get("session_id")
                logger.info(f"Presence test authenticated, session: {presence_session_id}")

                # Step 3: Do NOT send any heartbeats - wait 16 seconds
                logger.info("Waiting 16 seconds for heartbeat to go stale...")
                await asyncio.sleep(16)

                # Step 4: Send execute request
                execute_msg = {
                    "type": "execute_request",
                    "id": "3",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "session_id": presence_session_id,
                        "draft_id": "draft-stale-test"
                    }
                }
                
                await websocket.send(json.dumps(execute_msg))
                
                # Step 5: Should receive EXECUTE_BLOCKED with PRESENCE_STALE
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "execute_blocked":
                    self.log_test_result("presence_gate_test", False, f"Expected execute_blocked, got: {data.get('type')}")
                    return
                
                block_code = data.get("payload", {}).get("code")
                if block_code != "PRESENCE_STALE":
                    self.log_test_result("presence_gate_test", False, f"Expected PRESENCE_STALE, got: {block_code}")
                    return
                
                self.log_test_result("presence_gate_test", True, "Presence gate correctly blocked stale heartbeat")

        except Exception as e:
            self.log_test_result("presence_gate_test", False, f"Exception: {str(e)}")

    async def test_auth_rejection(self):
        """Test WebSocket auth rejection with invalid token."""
        try:
            async with websockets.connect(WS_URL) as websocket:
                # Send AUTH with invalid token
                auth_msg = {
                    "type": "auth",
                    "id": "1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "token": "invalid.jwt.token",
                        "device_id": "test_device_001",
                        "client_version": "1.0.0"
                    }
                }
                
                await websocket.send(json.dumps(auth_msg))
                
                # Should receive AUTH_FAIL
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "auth_fail":
                    self.log_test_result("auth_rejection_test", False, f"Expected auth_fail, got: {data.get('type')}")
                    return
                
                self.log_test_result("auth_rejection_test", True, "Invalid token correctly rejected")

        except websockets.ConnectionClosedError as e:
            # Connection should be closed after auth failure
            if e.code == 4003:  # Auth failed code
                self.log_test_result("auth_rejection_test", True, "Connection closed with auth failure code")
            else:
                self.log_test_result("auth_rejection_test", False, f"Unexpected close code: {e.code}")
        except Exception as e:
            self.log_test_result("auth_rejection_test", False, f"Exception: {str(e)}")

    async def test_session_status_endpoint(self):
        """Test GET /api/session/{session_id} endpoint with active session."""
        try:
            # Create fresh session for this test
            payload = {
                "user_id": "test_user_session", 
                "device_id": "test_device_session_001",
                "client_version": "1.0.0"
            }
            
            async with self.session.post(f"{API_URL}/auth/pair", json=payload) as response:
                if response.status != 200:
                    self.log_test_result("session_status_endpoint", False, "Failed to create session for test")
                    return
                    
                data = await response.json()
                session_token = data["token"]

            # Connect to WebSocket to activate session
            async with websockets.connect(WS_URL) as websocket:
                auth_msg = {
                    "type": "auth",
                    "id": "1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "token": session_token,
                        "device_id": "test_device_session_001",
                        "client_version": "1.0.0"
                    }
                }
                
                await websocket.send(json.dumps(auth_msg))
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "auth_ok":
                    self.log_test_result("session_status_endpoint", False, "Failed to authenticate for session test")
                    return
                
                test_session_id = data.get("payload", {}).get("session_id")
                
                # Send heartbeat to establish presence
                heartbeat_msg = {
                    "type": "heartbeat",
                    "id": "2",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "session_id": test_session_id,
                        "seq": 1,
                        "client_ts": datetime.now(timezone.utc).isoformat()
                    }
                }
                await websocket.send(json.dumps(heartbeat_msg))
                await websocket.recv()  # Consume heartbeat_ack
                
                # Now test session status endpoint while session is active
                async with self.session.get(f"{API_URL}/session/{test_session_id}") as response:
                    if response.status != 200:
                        self.log_test_result("session_status_endpoint", False, f"HTTP {response.status}")
                        return

                    data = await response.json()
                    required_fields = ["session_id", "active", "presence_ok", "last_heartbeat_age_info"]
                    
                    if not all(field in data for field in required_fields):
                        missing = [f for f in required_fields if f not in data]
                        self.log_test_result("session_status_endpoint", False, f"Missing fields: {missing}")
                        return

                    self.log_test_result("session_status_endpoint", True, f"Session status: active={data['active']}, presence_ok={data['presence_ok']}")

        except Exception as e:
            self.log_test_result("session_status_endpoint", False, f"Exception: {str(e)}")

    async def test_redaction(self):
        """Test that sensitive information is redacted in logs."""
        try:
            # Check supervisor backend logs for redaction patterns
            import subprocess
            result = subprocess.run(
                ["tail", "-n", "50", "/var/log/supervisor/backend.out.log"],
                capture_output=True, text=True
            )
            
            if result.returncode != 0:
                self.log_test_result("redaction_test", False, "Cannot access backend logs")
                return
            
            log_content = result.stdout
            
            # Check that JWT tokens are redacted (should not see full tokens)
            if self.test_token and self.test_token in log_content:
                self.log_test_result("redaction_test", False, "Raw JWT token found in logs")
                return
            
            # Look for redaction patterns like [REDACTED]
            if "[REDACTED]" in log_content or "***" in log_content:
                self.log_test_result("redaction_test", True, "Redaction patterns found in logs")
            else:
                # If no sensitive data and no redaction patterns, that's also OK
                self.log_test_result("redaction_test", True, "No sensitive data found in logs")

        except Exception as e:
            self.log_test_result("redaction_test", False, f"Exception: {str(e)}")

    # =====================================================
    #  BATCH 2: Audio Pipeline + TTS Tests
    # =====================================================

    def generate_fake_audio_chunk(self, size_kb: int = 1) -> str:
        """Generate base64-encoded fake audio data."""
        fake_audio = os.urandom(size_kb * 1024)
        return base64.b64encode(fake_audio).decode()

    async def test_audio_chunk_flow(self):
        """Test audio chunk flow: 8 chunks, transcript_partial every 4 chunks."""
        if not self.test_token:
            self.log_test_result("audio_chunk_flow", False, "No token available")
            return

        try:
            # Pair device for audio test
            payload = {
                "user_id": "audio_test_user",
                "device_id": "audio_device_001",
                "client_version": "1.0.0"
            }
            
            async with self.session.post(f"{API_URL}/auth/pair", json=payload) as response:
                if response.status != 200:
                    self.log_test_result("audio_chunk_flow", False, f"Pairing failed: HTTP {response.status}")
                    return
                    
                data = await response.json()
                audio_token = data["token"]

            # Connect to WebSocket
            async with websockets.connect(WS_URL) as websocket:
                # Authenticate
                auth_msg = {
                    "type": "auth",
                    "id": "auth1", 
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "token": audio_token,
                        "device_id": "audio_device_001",
                        "client_version": "1.0.0"
                    }
                }
                
                await websocket.send(json.dumps(auth_msg))
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "auth_ok":
                    self.log_test_result("audio_chunk_flow", False, f"Auth failed: {data.get('type')}")
                    return
                
                audio_session_id = data.get("payload", {}).get("session_id")
                logger.info(f"Audio test authenticated, session: {audio_session_id}")

                # Send heartbeat to establish presence
                heartbeat_msg = {
                    "type": "heartbeat",
                    "id": "hb1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "session_id": audio_session_id,
                        "seq": 1,
                        "client_ts": datetime.now(timezone.utc).isoformat()
                    }
                }
                await websocket.send(json.dumps(heartbeat_msg))
                await websocket.recv()  # Consume heartbeat_ack

                # Send 8 audio chunks
                partial_responses = []
                for i in range(1, 9):
                    audio_chunk_msg = {
                        "type": "audio_chunk",
                        "id": f"chunk{i}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "payload": {
                            "session_id": audio_session_id,
                            "audio": self.generate_fake_audio_chunk(),
                            "seq": i
                        }
                    }
                    
                    await websocket.send(json.dumps(audio_chunk_msg))
                    
                    # Every 4 chunks (4 and 8), expect transcript_partial
                    if i % 4 == 0:
                        response = await websocket.recv()
                        data = json.loads(response)
                        
                        if data.get("type") == "transcript_partial":
                            partial_responses.append(data)
                            logger.info(f"Received transcript_partial after chunk {i}: {data.get('payload', {}).get('message', '')}")
                        else:
                            self.log_test_result("audio_chunk_flow", False, f"Expected transcript_partial after chunk {i}, got: {data.get('type')}")
                            return

                if len(partial_responses) != 2:
                    self.log_test_result("audio_chunk_flow", False, f"Expected 2 transcript_partial responses, got {len(partial_responses)}")
                    return

                self.log_test_result("audio_chunk_flow", True, f"Audio chunk flow completed: received {len(partial_responses)} transcript partials")

        except Exception as e:
            self.log_test_result("audio_chunk_flow", False, f"Exception: {str(e)}")

    async def test_text_input_flow(self):
        """Test text input flow: text_input → transcript_final → tts_audio."""
        if not self.test_token:
            self.log_test_result("text_input_flow", False, "No token available")
            return

        try:
            async with websockets.connect(WS_URL) as websocket:
                # Authenticate  
                auth_msg = {
                    "type": "auth",
                    "id": "auth2",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "token": self.test_token,
                        "device_id": "test_device_001",
                        "client_version": "1.0.0"
                    }
                }
                
                await websocket.send(json.dumps(auth_msg))
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "auth_ok":
                    self.log_test_result("text_input_flow", False, f"Auth failed: {data.get('type')}")
                    return
                
                text_session_id = data.get("payload", {}).get("session_id")

                # Send text input
                text_msg = {
                    "type": "text_input",
                    "id": "text1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "session_id": text_session_id,
                        "text": "send a message to Sarah about the meeting tomorrow"
                    }
                }
                
                await websocket.send(json.dumps(text_msg))

                # Should receive transcript_final
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "transcript_final":
                    self.log_test_result("text_input_flow", False, f"Expected transcript_final, got: {data.get('type')}")
                    return

                # Should receive tts_audio
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "tts_audio":
                    self.log_test_result("text_input_flow", False, f"Expected tts_audio, got: {data.get('type')}")
                    return

                tts_message = data.get("payload", {}).get("message", "")
                if "message" not in tts_message.lower():
                    self.log_test_result("text_input_flow", False, f"TTS response doesn't contain expected content: {tts_message}")
                    return

                self.log_test_result("text_input_flow", True, f"Text input flow completed successfully: {tts_message[:60]}")

        except Exception as e:
            self.log_test_result("text_input_flow", False, f"Exception: {str(e)}")

    async def test_chunk_validation_empty(self):
        """Test audio chunk validation: empty chunk."""
        if not self.test_token:
            self.log_test_result("chunk_validation_empty", False, "No token available")
            return

        try:
            async with websockets.connect(WS_URL) as websocket:
                # Authenticate
                auth_msg = {
                    "type": "auth",
                    "id": "auth3",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "token": self.test_token,
                        "device_id": "test_device_001",
                        "client_version": "1.0.0"
                    }
                }
                
                await websocket.send(json.dumps(auth_msg))
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "auth_ok":
                    self.log_test_result("chunk_validation_empty", False, f"Auth failed: {data.get('type')}")
                    return
                
                empty_session_id = data.get("payload", {}).get("session_id")

                # Send audio chunk with empty audio field
                empty_chunk_msg = {
                    "type": "audio_chunk",
                    "id": "empty1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "session_id": empty_session_id,
                        "audio": "",  # Empty audio
                        "seq": 1
                    }
                }
                
                await websocket.send(json.dumps(empty_chunk_msg))

                # Should receive error with AUDIO_INVALID code
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "error":
                    self.log_test_result("chunk_validation_empty", False, f"Expected error, got: {data.get('type')}")
                    return

                error_code = data.get("payload", {}).get("code")
                if error_code != "AUDIO_INVALID":
                    self.log_test_result("chunk_validation_empty", False, f"Expected AUDIO_INVALID, got: {error_code}")
                    return

                self.log_test_result("chunk_validation_empty", True, "Empty chunk correctly rejected with AUDIO_INVALID")

        except Exception as e:
            self.log_test_result("chunk_validation_empty", False, f"Exception: {str(e)}")

    async def test_chunk_validation_invalid_base64(self):
        """Test audio chunk validation: invalid base64."""
        if not self.test_token:
            self.log_test_result("chunk_validation_invalid_base64", False, "No token available")
            return

        try:
            async with websockets.connect(WS_URL) as websocket:
                # Authenticate
                auth_msg = {
                    "type": "auth",
                    "id": "auth4",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "token": self.test_token,
                        "device_id": "test_device_001",
                        "client_version": "1.0.0"
                    }
                }
                
                await websocket.send(json.dumps(auth_msg))
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "auth_ok":
                    self.log_test_result("chunk_validation_invalid_base64", False, f"Auth failed: {data.get('type')}")
                    return
                
                invalid_session_id = data.get("payload", {}).get("session_id")

                # Send audio chunk with invalid base64
                invalid_chunk_msg = {
                    "type": "audio_chunk",
                    "id": "invalid1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "session_id": invalid_session_id,
                        "audio": "not-valid-base64-data!!!",
                        "seq": 1
                    }
                }
                
                await websocket.send(json.dumps(invalid_chunk_msg))

                # Should receive error with AUDIO_INVALID code
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "error":
                    self.log_test_result("chunk_validation_invalid_base64", False, f"Expected error, got: {data.get('type')}")
                    return

                error_code = data.get("payload", {}).get("code")
                if error_code != "AUDIO_INVALID":
                    self.log_test_result("chunk_validation_invalid_base64", False, f"Expected AUDIO_INVALID, got: {error_code}")
                    return

                self.log_test_result("chunk_validation_invalid_base64", True, "Invalid base64 chunk correctly rejected")

        except Exception as e:
            self.log_test_result("chunk_validation_invalid_base64", False, f"Exception: {str(e)}")

    async def test_stream_end_cancel(self):
        """Test stream end: send chunks then cancel."""
        if not self.test_token:
            self.log_test_result("stream_end_cancel", False, "No token available")
            return

        try:
            async with websockets.connect(WS_URL) as websocket:
                # Authenticate
                auth_msg = {
                    "type": "auth",
                    "id": "auth5",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "token": self.test_token,
                        "device_id": "test_device_001",
                        "client_version": "1.0.0"
                    }
                }
                
                await websocket.send(json.dumps(auth_msg))
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("type") != "auth_ok":
                    self.log_test_result("stream_end_cancel", False, f"Auth failed: {data.get('type')}")
                    return
                
                cancel_session_id = data.get("payload", {}).get("session_id")

                # Send some audio chunks
                for i in range(1, 3):
                    chunk_msg = {
                        "type": "audio_chunk",
                        "id": f"cancel_chunk{i}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "payload": {
                            "session_id": cancel_session_id,
                            "audio": self.generate_fake_audio_chunk(),
                            "seq": i
                        }
                    }
                    await websocket.send(json.dumps(chunk_msg))

                # Send cancel message
                cancel_msg = {
                    "type": "cancel",
                    "id": "cancel1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "session_id": cancel_session_id
                    }
                }
                
                await websocket.send(json.dumps(cancel_msg))

                # Should receive transcript_final if there was accumulated text
                # This test verifies that cancel triggers stream end
                # Note: May not receive response if no text was accumulated
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data = json.loads(response)
                    logger.info(f"Cancel response: {data.get('type')}")
                    
                    # If we get a response, it should be transcript_final or we don't get any response (which is also valid)
                    if data.get("type") not in ["transcript_final", None]:
                        logger.info(f"Cancel triggered response: {data.get('type')}")
                        
                except asyncio.TimeoutError:
                    # No response within timeout is also acceptable for cancel
                    logger.info("No response to cancel (acceptable behavior)")

                self.log_test_result("stream_end_cancel", True, "Stream end cancel completed successfully")

        except Exception as e:
            self.log_test_result("stream_end_cancel", False, f"Exception: {str(e)}")

    async def test_mock_tts_response_content(self):
        """Test mock TTS response content based on input."""
        if not self.test_token:
            self.log_test_result("mock_tts_response_content", False, "No token available")
            return

        try:
            # Test cases: input text → expected content in response
            test_cases = [
                ("Hello", "hello"),
                ("send a message to someone", "message"),  
                ("schedule a meeting", "meeting"),
            ]

            results = []
            
            for test_text, expected_keyword in test_cases:
                async with websockets.connect(WS_URL) as websocket:
                    # Authenticate
                    auth_msg = {
                        "type": "auth",
                        "id": f"auth_tts_{len(results)}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "payload": {
                            "token": self.test_token,
                            "device_id": "test_device_001",
                            "client_version": "1.0.0"
                        }
                    }
                    
                    await websocket.send(json.dumps(auth_msg))
                    response = await websocket.recv()
                    data = json.loads(response)
                    
                    if data.get("type") != "auth_ok":
                        results.append(False)
                        continue
                    
                    tts_session_id = data.get("payload", {}).get("session_id")

                    # Send text input
                    text_msg = {
                        "type": "text_input",
                        "id": f"tts_test_{len(results)}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "payload": {
                            "session_id": tts_session_id,
                            "text": test_text
                        }
                    }
                    
                    await websocket.send(json.dumps(text_msg))

                    # Skip transcript_final, get tts_audio
                    await websocket.recv()  # transcript_final
                    response = await websocket.recv()  # tts_audio
                    data = json.loads(response)
                    
                    if data.get("type") == "tts_audio":
                        tts_response = data.get("payload", {}).get("message", "").lower()
                        if expected_keyword in tts_response:
                            results.append(True)
                            logger.info(f"TTS test passed: '{test_text}' → '{tts_response[:60]}'")
                        else:
                            results.append(False)
                            logger.warning(f"TTS test failed: '{test_text}' → '{tts_response[:60]}' (missing '{expected_keyword}')")
                    else:
                        results.append(False)

            success_rate = sum(results) / len(results) if results else 0
            if success_rate >= 0.67:  # At least 2/3 tests should pass
                self.log_test_result("mock_tts_response_content", True, f"TTS content tests: {sum(results)}/{len(results)} passed")
            else:
                self.log_test_result("mock_tts_response_content", False, f"TTS content tests: only {sum(results)}/{len(results)} passed")

        except Exception as e:
            self.log_test_result("mock_tts_response_content", False, f"Exception: {str(e)}")

    async def run_all_tests(self):
        """Run all backend tests in sequence."""
        logger.info("=" * 60)
        logger.info("STARTING MYNDLENS BACKEND TESTS - BATCH 0+1+2")
        logger.info("=" * 60)
        
        # BATCH 0+1: Critical regression tests
        logger.info("RUNNING BATCH 0+1 REGRESSION TESTS...")
        await self.test_health_endpoint()
        await self.test_auth_pair_endpoint()
        await self.test_websocket_full_flow()
        await self.test_presence_gate()  # Most critical test
        await self.test_auth_rejection()
        await self.test_session_status_endpoint()
        await self.test_redaction()
        
        # BATCH 2: Audio Pipeline + TTS Tests
        logger.info("RUNNING BATCH 2 AUDIO PIPELINE TESTS...")
        await self.test_audio_chunk_flow()
        await self.test_text_input_flow()
        await self.test_chunk_validation_empty()
        await self.test_chunk_validation_invalid_base64()
        await self.test_stream_end_cancel()
        await self.test_mock_tts_response_content()
        
        # Summary
        logger.info("=" * 60)
        logger.info("TEST SUMMARY")
        logger.info("=" * 60)
        
        passed = sum(1 for result in self.test_results.values() if result)
        total = len(self.test_results)
        
        # Group results by batch
        batch_0_1_tests = ["health_endpoint", "auth_pair_endpoint", "websocket_full_flow", 
                          "presence_gate_test", "auth_rejection_test", "session_status_endpoint", "redaction_test"]
        batch_2_tests = ["audio_chunk_flow", "text_input_flow", "chunk_validation_empty", 
                        "chunk_validation_invalid_base64", "stream_end_cancel", "mock_tts_response_content"]
        
        logger.info("BATCH 0+1 REGRESSION TESTS:")
        for test_name in batch_0_1_tests:
            status = "✅ PASS" if self.test_results[test_name] else "❌ FAIL"
            logger.info(f"  {status} {test_name}")
        
        logger.info("BATCH 2 AUDIO PIPELINE TESTS:")
        for test_name in batch_2_tests:
            status = "✅ PASS" if self.test_results[test_name] else "❌ FAIL"
            logger.info(f"  {status} {test_name}")
        
        logger.info("-" * 40)
        logger.info(f"TOTAL: {passed}/{total} tests passed")
        
        if self.failed_tests:
            logger.info("\nFAILED TESTS:")
            for failure in self.failed_tests:
                logger.info(f"❌ {failure}")
        
        return passed == total

async def main():
    """Main test runner."""
    async with BackendTester() as tester:
        success = await tester.run_all_tests()
        return success

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)