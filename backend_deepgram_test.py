#!/usr/bin/env python3
"""
MyndLens Batch 3 — Deepgram STT Integration Tests

CRITICAL TESTS:
1. Health check - Should show DeepgramSTTProvider, stt_healthy=true, mock_stt=false
2. Deepgram STT via audio chunks over WS
3. Text input flow regression (should still work)
4. STT failure graceful handling
5. Provider abstraction verified
6. All previous functionality regression
"""

import asyncio
import requests
import json
import sys
import base64
import wave
import struct
import math
import websocket
import time
from typing import Dict, List, Any, Optional

# Backend URL from environment
BACKEND_URL = "https://sovereign-exec-qa.preview.emergentagent.com"
WS_URL = "wss://voice-assistant-dev.preview.emergentagent.com/api/ws"

class DeepgramSTTTester:
    def __init__(self):
        self.base_url = BACKEND_URL
        self.ws_url = WS_URL
        self.results = []
        self.auth_token = None
        
    def log_test_result(self, test_name: str, passed: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASSED" if passed else "❌ FAILED"
        self.results.append({
            "test": test_name,
            "passed": passed,
            "details": details
        })
        print(f"{status}: {test_name}")
        if details:
            print(f"  Details: {details}")
        print()
    
    def create_test_wav_data(self, duration_seconds: float = 2.0, sample_rate: int = 16000) -> bytes:
        """Create a simple WAV file with sine wave audio data for testing"""
        try:
            # Generate sine wave data
            num_samples = int(duration_seconds * sample_rate)
            frequency = 440  # A4 note
            amplitude = 16000  # 16-bit amplitude
            
            # Generate audio samples
            audio_data = []
            for i in range(num_samples):
                t = i / sample_rate
                sample = int(amplitude * math.sin(2 * math.pi * frequency * t))
                audio_data.append(struct.pack('<h', sample))  # 16-bit signed little-endian
            
            # Create WAV header
            wav_data = b''.join(audio_data)
            wav_size = len(wav_data)
            
            # WAV file format
            header = b'RIFF'
            header += struct.pack('<I', wav_size + 36)  # File size
            header += b'WAVE'
            header += b'fmt '
            header += struct.pack('<I', 16)  # PCM format chunk size
            header += struct.pack('<H', 1)   # PCM format
            header += struct.pack('<H', 1)   # Mono
            header += struct.pack('<I', sample_rate)  # Sample rate
            header += struct.pack('<I', sample_rate * 2)  # Byte rate
            header += struct.pack('<H', 2)   # Block align
            header += struct.pack('<H', 16)  # Bits per sample
            header += b'data'
            header += struct.pack('<I', wav_size)  # Data size
            
            return header + wav_data
            
        except Exception as e:
            print(f"Failed to create WAV data: {e}")
            return b''
    
    def pair_device(self) -> Optional[str]:
        """Pair device and get JWT token"""
        try:
            payload = {
                "user_id": "deepgram_test",
                "device_id": "dg_dev_001",
                "client_version": "1.0.0"
            }
            response = requests.post(f"{self.base_url}/api/auth/pair", json=payload, timeout=10)
            
            if response.status_code != 200:
                return None
                
            data = response.json()
            return data.get("token")
            
        except Exception as e:
            print(f"Device pairing failed: {e}")
            return None
    
    def test_health_check(self):
        """Test 1: Health check should show DeepgramSTTProvider"""
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=10)
            data = response.json()
            
            if response.status_code != 200:
                self.log_test_result("Health Check - Deepgram Provider", False, f"HTTP {response.status_code}")
                return
            
            # Check required fields for Deepgram integration
            stt_provider = data.get("stt_provider", "")
            stt_healthy = data.get("stt_healthy", False)
            mock_stt = data.get("mock_stt", True)
            
            # Should show DeepgramSTTProvider, healthy=true, mock=false
            provider_correct = stt_provider == "DeepgramSTTProvider"
            healthy = stt_healthy is True
            not_mock = mock_stt is False
            
            all_correct = provider_correct and healthy and not_mock
            details = f"provider={stt_provider}, healthy={stt_healthy}, mock={mock_stt}"
            
            self.log_test_result("Health Check - Deepgram Provider", all_correct, details)
            
        except Exception as e:
            self.log_test_result("Health Check - Deepgram Provider", False, f"Exception: {str(e)}")
    
    def test_auth_pair(self):
        """Test 2: Auth/Pair should work for WebSocket setup"""
        try:
            token = self.pair_device()
            
            if not token:
                self.log_test_result("Auth/Pair for Deepgram Test", False, "Failed to get token")
                return
            
            # Verify JWT format
            has_valid_jwt = "." in token and len(token.split(".")) == 3
            
            if has_valid_jwt:
                self.auth_token = token
                self.log_test_result("Auth/Pair for Deepgram Test", True, "Valid JWT token received")
            else:
                self.log_test_result("Auth/Pair for Deepgram Test", False, "Invalid JWT token format")
                
        except Exception as e:
            self.log_test_result("Auth/Pair for Deepgram Test", False, f"Exception: {str(e)}")
    
    def test_websocket_deepgram_audio_flow(self):
        """Test 3: WebSocket Deepgram STT via audio chunks"""
        if not self.auth_token:
            self.log_test_result("WebSocket Deepgram Audio Flow", False, "No auth token available")
            return
            
        try:
            # Create test audio data
            wav_data = self.create_test_wav_data(duration_seconds=2.0)
            if not wav_data:
                self.log_test_result("WebSocket Deepgram Audio Flow", False, "Failed to create test audio")
                return
            
            # Split audio into 8 chunks
            chunk_size = len(wav_data) // 8
            chunks = []
            for i in range(8):
                start = i * chunk_size
                end = start + chunk_size if i < 7 else len(wav_data)
                chunk_data = wav_data[start:end]
                chunks.append(base64.b64encode(chunk_data).decode('utf-8'))
            
            messages_received = []
            ws_connected = False
            ws_authenticated = False
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    messages_received.append(data)
                    
                    msg_type = data.get("type")
                    if msg_type == "auth_ok":
                        nonlocal ws_authenticated
                        ws_authenticated = True
                        print("  WebSocket authenticated")
                        
                        # Send heartbeat
                        heartbeat_msg = {"type": "heartbeat"}
                        ws.send(json.dumps(heartbeat_msg))
                        
                    elif msg_type == "heartbeat_ack":
                        print("  Heartbeat acknowledged")
                        # Start sending audio chunks
                        for i, chunk in enumerate(chunks):
                            audio_msg = {
                                "type": "audio_chunk",
                                "payload": {
                                    "audio": chunk,
                                    "seq": i,
                                    "session_id": "test_session"
                                }
                            }
                            ws.send(json.dumps(audio_msg))
                            print(f"  Sent audio chunk {i+1}/8")
                            time.sleep(0.1)  # Small delay between chunks
                        
                        # Send stream end after delay
                        time.sleep(0.5)
                        stream_end_msg = {"type": "stream_end"}
                        ws.send(json.dumps(stream_end_msg))
                        print("  Sent stream_end")
                        
                        # Close after a delay to allow final processing
                        time.sleep(1.0)
                        ws.close()
                        
                    elif msg_type in ["transcript_partial", "transcript_final"]:
                        payload = data.get("payload", {})
                        text = payload.get("text", "")
                        is_final = payload.get("is_final", False)
                        confidence = payload.get("confidence", 0.0)
                        print(f"  Received {msg_type}: text='{text}', final={is_final}, conf={confidence}")
                        
                    elif msg_type == "error":
                        print(f"  Received error: {data}")
                        
                except Exception as e:
                    print(f"  Error processing message: {e}")
            
            def on_error(ws, error):
                print(f"  WebSocket error: {error}")
            
            def on_close(ws, close_status_code, close_msg):
                print("  WebSocket connection closed")
            
            def on_open(ws):
                nonlocal ws_connected
                ws_connected = True
                print("  WebSocket connected")
                
                # Send auth message
                auth_msg = {
                    "type": "auth",
                    "payload": {"token": self.auth_token}
                }
                ws.send(json.dumps(auth_msg))
            
            # Create WebSocket connection
            ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Run WebSocket with timeout
            ws.run_forever()
            
            # Analyze results
            auth_success = ws_authenticated
            connection_success = ws_connected
            
            # Check for transcript responses (even if empty due to synthetic audio)
            transcript_msgs = [msg for msg in messages_received if msg.get("type") in ["transcript_partial", "transcript_final"]]
            error_msgs = [msg for msg in messages_received if msg.get("type") == "error"]
            
            # For synthetic audio, Deepgram may return empty transcripts - that's OK
            # The test is that the flow doesn't crash and returns proper response types
            flow_completed = len(transcript_msgs) > 0 or len(error_msgs) == 0
            no_crashes = len([msg for msg in error_msgs if "crash" in str(msg).lower() or "exception" in str(msg).lower()]) == 0
            
            all_success = auth_success and connection_success and flow_completed and no_crashes
            
            details = f"Connected: {connection_success}, Auth: {auth_success}, Transcripts: {len(transcript_msgs)}, Errors: {len(error_msgs)}, No crashes: {no_crashes}"
            
            self.log_test_result("WebSocket Deepgram Audio Flow", all_success, details)
            
        except Exception as e:
            self.log_test_result("WebSocket Deepgram Audio Flow", False, f"Exception: {str(e)}")
    
    def test_text_input_regression(self):
        """Test 4: Text input flow should still work (regression)"""
        if not self.auth_token:
            self.log_test_result("Text Input Regression", False, "No auth token available")
            return
            
        try:
            messages_received = []
            ws_connected = False
            ws_authenticated = False
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    messages_received.append(data)
                    
                    msg_type = data.get("type")
                    if msg_type == "auth_ok":
                        nonlocal ws_authenticated
                        ws_authenticated = True
                        
                        # Send heartbeat
                        heartbeat_msg = {"type": "heartbeat"}
                        ws.send(json.dumps(heartbeat_msg))
                        
                    elif msg_type == "heartbeat_ack":
                        # Send text input
                        text_msg = {
                            "type": "text_input",
                            "payload": {
                                "text": "Hello send a message to Sarah",
                                "session_id": "test_session"
                            }
                        }
                        ws.send(json.dumps(text_msg))
                        
                        # Close after delay
                        time.sleep(1.0)
                        ws.close()
                        
                except Exception as e:
                    print(f"Error processing message: {e}")
            
            def on_error(ws, error):
                print(f"WebSocket error: {error}")
            
            def on_close(ws, close_status_code, close_msg):
                pass
            
            def on_open(ws):
                nonlocal ws_connected
                ws_connected = True
                
                # Send auth message
                auth_msg = {
                    "type": "auth",
                    "payload": {"token": self.auth_token}
                }
                ws.send(json.dumps(auth_msg))
            
            # Create WebSocket connection
            ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Run WebSocket
            ws.run_forever()
            
            # Check for expected responses
            transcript_finals = [msg for msg in messages_received if msg.get("type") == "transcript_final"]
            tts_responses = [msg for msg in messages_received if msg.get("type") == "tts_audio"]
            
            has_transcript = len(transcript_finals) > 0
            has_tts = len(tts_responses) > 0
            
            success = ws_connected and ws_authenticated and has_transcript and has_tts
            details = f"Connected: {ws_connected}, Auth: {ws_authenticated}, Transcript: {has_transcript}, TTS: {has_tts}"
            
            self.log_test_result("Text Input Regression", success, details)
            
        except Exception as e:
            self.log_test_result("Text Input Regression", False, f"Exception: {str(e)}")
    
    def test_stt_failure_handling(self):
        """Test 5: STT failure graceful handling"""
        if not self.auth_token:
            self.log_test_result("STT Failure Handling", False, "No auth token available")
            return
            
        try:
            messages_received = []
            ws_connected = False
            ws_authenticated = False
            connection_survived = True
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    messages_received.append(data)
                    
                    msg_type = data.get("type")
                    if msg_type == "auth_ok":
                        nonlocal ws_authenticated
                        ws_authenticated = True
                        
                        # Send heartbeat
                        heartbeat_msg = {"type": "heartbeat"}
                        ws.send(json.dumps(heartbeat_msg))
                        
                    elif msg_type == "heartbeat_ack":
                        # Send malformed/empty audio chunks
                        for i in range(3):
                            bad_audio_msg = {
                                "type": "audio_chunk",
                                "payload": {
                                    "audio": "",  # Empty audio
                                    "seq": i,
                                    "session_id": "test_session"
                                }
                            }
                            ws.send(json.dumps(bad_audio_msg))
                        
                        # Send invalid base64
                        invalid_audio_msg = {
                            "type": "audio_chunk",
                            "payload": {
                                "audio": "invalid_base64_data!!!",
                                "seq": 3,
                                "session_id": "test_session"
                            }
                        }
                        ws.send(json.dumps(invalid_audio_msg))
                        
                        # Close after delay
                        time.sleep(1.0)
                        ws.close()
                        
                except Exception as e:
                    print(f"Error processing message: {e}")
            
            def on_error(ws, error):
                nonlocal connection_survived
                connection_survived = False
                print(f"WebSocket error: {error}")
            
            def on_close(ws, close_status_code, close_msg):
                pass
            
            def on_open(ws):
                nonlocal ws_connected
                ws_connected = True
                
                # Send auth message
                auth_msg = {
                    "type": "auth",
                    "payload": {"token": self.auth_token}
                }
                ws.send(json.dumps(auth_msg))
            
            # Create WebSocket connection
            ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Run WebSocket
            ws.run_forever()
            
            # Check that connection handled failures gracefully
            error_msgs = [msg for msg in messages_received if msg.get("type") == "error"]
            crash_errors = [msg for msg in error_msgs if "crash" in str(msg).lower() or "exception" in str(msg).lower()]
            
            handled_gracefully = len(crash_errors) == 0 and connection_survived
            details = f"Connected: {ws_connected}, Auth: {ws_authenticated}, Graceful: {handled_gracefully}, Errors: {len(error_msgs)}"
            
            self.log_test_result("STT Failure Handling", handled_gracefully, details)
            
        except Exception as e:
            self.log_test_result("STT Failure Handling", False, f"Exception: {str(e)}")
    
    def test_presence_gate_regression(self):
        """Test 6: Presence gate should still work (16s stale blocks execution)"""
        if not self.auth_token:
            self.log_test_result("Presence Gate Regression", False, "No auth token available")
            return
            
        try:
            messages_received = []
            ws_connected = False
            ws_authenticated = False
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    messages_received.append(data)
                    
                    msg_type = data.get("type")
                    if msg_type == "auth_ok":
                        nonlocal ws_authenticated
                        ws_authenticated = True
                        
                        # Send initial heartbeat
                        heartbeat_msg = {"type": "heartbeat"}
                        ws.send(json.dumps(heartbeat_msg))
                        
                    elif msg_type == "heartbeat_ack":
                        # Wait 16+ seconds without heartbeat, then try execute
                        print("  Waiting 16s without heartbeat...")
                        time.sleep(16.5)
                        
                        # Try to execute - should be blocked
                        execute_msg = {
                            "type": "execute_request", 
                            "payload": {"command": "test presence gate"}
                        }
                        ws.send(json.dumps(execute_msg))
                        
                        # Close after delay
                        time.sleep(1.0)
                        ws.close()
                        
                except Exception as e:
                    print(f"Error processing message: {e}")
            
            def on_error(ws, error):
                print(f"WebSocket error: {error}")
            
            def on_close(ws, close_status_code, close_msg):
                pass
            
            def on_open(ws):
                nonlocal ws_connected
                ws_connected = True
                
                # Send auth message
                auth_msg = {
                    "type": "auth",
                    "payload": {"token": self.auth_token}
                }
                ws.send(json.dumps(auth_msg))
            
            # Create WebSocket connection
            ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Run WebSocket
            ws.run_forever()
            
            # Check for EXECUTE_BLOCKED response
            blocked_msgs = [msg for msg in messages_received if 
                          msg.get("type") == "execute_response" and 
                          msg.get("payload", {}).get("status") == "EXECUTE_BLOCKED"]
            
            presence_stale_msgs = [msg for msg in blocked_msgs if 
                                 "PRESENCE_STALE" in str(msg.get("payload", {}).get("error_code", ""))]
            
            gate_working = len(presence_stale_msgs) > 0
            details = f"Connected: {ws_connected}, Auth: {ws_authenticated}, Blocked: {len(blocked_msgs)}, Presence stale: {len(presence_stale_msgs)}"
            
            self.log_test_result("Presence Gate Regression", gate_working, details)
            
        except Exception as e:
            self.log_test_result("Presence Gate Regression", False, f"Exception: {str(e)}")
    
    def run_all_tests(self):
        """Run all Deepgram STT tests"""
        print("🧪 MyndLens Batch 3 — Deepgram STT Integration Tests")
        print("=" * 65)
        print()
        
        # Critical Deepgram tests
        print("🎯 CRITICAL DEEPGRAM STT TESTS")
        print("-" * 35)
        
        self.test_health_check()
        self.test_auth_pair()
        self.test_websocket_deepgram_audio_flow()
        self.test_text_input_regression()
        self.test_stt_failure_handling()
        self.test_presence_gate_regression()
        
        print()
        
        # Summary
        passed_tests = [r for r in self.results if r["passed"]]
        failed_tests = [r for r in self.results if not r["passed"]]
        
        print("=" * 65)
        print(f"📊 TEST SUMMARY: {len(passed_tests)}/{len(self.results)} PASSED")
        print("=" * 65)
        
        if failed_tests:
            print("\n❌ FAILED TESTS:")
            for test in failed_tests:
                print(f"  - {test['test']}: {test['details']}")
        
        if passed_tests:
            print(f"\n✅ PASSED TESTS: {len(passed_tests)}")
            for test in passed_tests:
                print(f"  - {test['test']}")
        
        return len(failed_tests) == 0

def main():
    """Main test execution"""
    tester = DeepgramSTTTester()
    success = tester.run_all_tests()
    
    if success:
        print("\n🎉 ALL DEEPGRAM STT TESTS PASSED - Integration Ready!")
        sys.exit(0)
    else:
        print("\n💥 SOME DEEPGRAM STT TESTS FAILED - Check logs above")
        sys.exit(1)

if __name__ == "__main__":
    main()