#!/usr/bin/env python3
"""
Final Deepgram STT Integration Test Suite
Tests all critical requirements for Batch 3
"""

import requests
import json
import time
import base64
import math
import struct
import websocket
import threading

BACKEND_URL = "https://sovereign-exec-qa.preview.emergentagent.com"

class DeepgramTester:
    def __init__(self):
        self.results = []
    
    def log_result(self, test_name: str, passed: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASSED" if passed else "❌ FAILED"
        self.results.append({"test": test_name, "passed": passed, "details": details})
        print(f"{status}: {test_name}")
        if details:
            print(f"  Details: {details}")
        print()
    
    def test_health_endpoint(self):
        """Test 1: Health check shows DeepgramSTTProvider"""
        try:
            response = requests.get(f"{BACKEND_URL}/api/health", timeout=10)
            data = response.json()
            
            provider = data.get("stt_provider")
            healthy = data.get("stt_healthy")
            mock = data.get("mock_stt")
            
            success = (provider == "DeepgramSTTProvider" and 
                      healthy is True and 
                      mock is False)
            
            details = f"provider={provider}, healthy={healthy}, mock={mock}"
            self.log_result("Health Endpoint - Deepgram Configuration", success, details)
            return success
            
        except Exception as e:
            self.log_result("Health Endpoint - Deepgram Configuration", False, f"Exception: {e}")
            return False
    
    def test_auth_pair(self):
        """Test 2: Device pairing works"""
        try:
            payload = {"user_id": "deepgram_test", "device_id": "dg_dev_001"}
            response = requests.post(f"{BACKEND_URL}/api/auth/pair", json=payload, timeout=10)
            
            if response.status_code != 200:
                self.log_result("Device Pairing", False, f"HTTP {response.status_code}")
                return None
            
            token = response.json().get("token", "")
            valid_jwt = "." in token and len(token.split(".")) == 3
            
            self.log_result("Device Pairing", valid_jwt, "JWT token created")
            return token if valid_jwt else None
            
        except Exception as e:
            self.log_result("Device Pairing", False, f"Exception: {e}")
            return None
    
    def test_deepgram_audio_chunks(self):
        """Test 3: Deepgram STT via audio chunks"""
        token = self.test_auth_pair()
        if not token:
            self.log_result("Deepgram Audio Chunks", False, "No auth token")
            return False
        
        try:
            # Create simple audio chunks
            chunks = self._create_audio_chunks()
            
            messages = []
            session_id = None
            completed = False
            
            def on_message(ws, message):
                nonlocal session_id, completed
                data = json.loads(message)
                messages.append(data)
                msg_type = data.get("type")
                
                if msg_type == "auth_ok":
                    session_id = data.get("payload", {}).get("session_id")
                    ws.send(json.dumps({"type": "heartbeat", "payload": {"session_id": session_id, "seq": 1}}))
                    
                elif msg_type == "heartbeat_ack":
                    # Send 8 audio chunks
                    for i, chunk in enumerate(chunks):
                        audio_msg = {
                            "type": "audio_chunk",
                            "payload": {"audio": chunk, "seq": i, "session_id": session_id}
                        }
                        ws.send(json.dumps(audio_msg))
                        time.sleep(0.1)
                    
                    # End stream
                    time.sleep(0.5)
                    ws.send(json.dumps({"type": "cancel", "payload": {"session_id": session_id}}))
                    time.sleep(1.0)
                    completed = True
                    ws.close()
            
            def on_open(ws):
                auth_msg = {
                    "type": "auth",
                    "payload": {"token": token, "device_id": "dg_dev_001", "client_version": "1.0.0"}
                }
                ws.send(json.dumps(auth_msg))
            
            ws_url = "wss://voice-assistant-dev.preview.emergentagent.com/api/ws"
            ws = websocket.WebSocketApp(ws_url, on_open=on_open, on_message=on_message)
            
            ws_thread = threading.Thread(target=lambda: ws.run_forever())
            ws_thread.daemon = True
            ws_thread.start()
            ws_thread.join(timeout=15.0)
            
            # Check results
            auth_ok = any(m.get("type") == "auth_ok" for m in messages)
            no_crashes = not any("crash" in str(m).lower() for m in messages)
            
            success = auth_ok and completed and no_crashes
            details = f"Auth: {auth_ok}, Completed: {completed}, No crashes: {no_crashes}"
            
            self.log_result("Deepgram Audio Chunks Flow", success, details)
            return success
            
        except Exception as e:
            self.log_result("Deepgram Audio Chunks Flow", False, f"Exception: {e}")
            return False
    
    def test_text_input_regression(self):
        """Test 4: Text input still works"""
        token = self.test_auth_pair()
        if not token:
            self.log_result("Text Input Regression", False, "No auth token")
            return False
        
        try:
            messages = []
            session_id = None
            
            def on_message(ws, message):
                nonlocal session_id
                data = json.loads(message)
                messages.append(data)
                msg_type = data.get("type")
                
                if msg_type == "auth_ok":
                    session_id = data.get("payload", {}).get("session_id")
                    ws.send(json.dumps({"type": "heartbeat", "payload": {"session_id": session_id, "seq": 1}}))
                    
                elif msg_type == "heartbeat_ack":
                    text_msg = {
                        "type": "text_input",
                        "payload": {"text": "Hello send a message to Sarah", "session_id": session_id}
                    }
                    ws.send(json.dumps(text_msg))
                    time.sleep(1.0)
                    ws.close()
            
            def on_open(ws):
                auth_msg = {
                    "type": "auth",
                    "payload": {"token": token, "device_id": "dg_dev_001", "client_version": "1.0.0"}
                }
                ws.send(json.dumps(auth_msg))
            
            ws_url = "wss://voice-assistant-dev.preview.emergentagent.com/api/ws"
            ws = websocket.WebSocketApp(ws_url, on_open=on_open, on_message=on_message)
            
            ws_thread = threading.Thread(target=lambda: ws.run_forever())
            ws_thread.daemon = True
            ws_thread.start()
            ws_thread.join(timeout=10.0)
            
            # Check for expected responses
            transcript_finals = [m for m in messages if m.get("type") == "transcript_final"]
            tts_responses = [m for m in messages if m.get("type") == "tts_audio"]
            
            success = len(transcript_finals) > 0 and len(tts_responses) > 0
            details = f"Transcripts: {len(transcript_finals)}, TTS: {len(tts_responses)}"
            
            self.log_result("Text Input Regression", success, details)
            return success
            
        except Exception as e:
            self.log_result("Text Input Regression", False, f"Exception: {e}")
            return False
    
    def test_stt_failure_handling(self):
        """Test 5: STT graceful failure handling"""
        token = self.test_auth_pair()
        if not token:
            self.log_result("STT Failure Handling", False, "No auth token")
            return False
        
        try:
            messages = []
            session_id = None
            connection_survived = True
            
            def on_message(ws, message):
                nonlocal session_id
                data = json.loads(message)
                messages.append(data)
                msg_type = data.get("type")
                
                if msg_type == "auth_ok":
                    session_id = data.get("payload", {}).get("session_id")
                    ws.send(json.dumps({"type": "heartbeat", "payload": {"session_id": session_id, "seq": 1}}))
                    
                elif msg_type == "heartbeat_ack":
                    # Send malformed audio chunks
                    for i in range(3):
                        bad_audio = {
                            "type": "audio_chunk",
                            "payload": {"audio": "", "seq": i, "session_id": session_id}  # Empty audio
                        }
                        ws.send(json.dumps(bad_audio))
                    
                    # Send invalid base64
                    invalid_audio = {
                        "type": "audio_chunk", 
                        "payload": {"audio": "invalid_base64!!!", "seq": 3, "session_id": session_id}
                    }
                    ws.send(json.dumps(invalid_audio))
                    
                    time.sleep(1.0)
                    ws.close()
            
            def on_error(ws, error):
                nonlocal connection_survived
                connection_survived = False
            
            def on_open(ws):
                auth_msg = {
                    "type": "auth",
                    "payload": {"token": token, "device_id": "dg_dev_001", "client_version": "1.0.0"}
                }
                ws.send(json.dumps(auth_msg))
            
            ws_url = "wss://voice-assistant-dev.preview.emergentagent.com/api/ws"
            ws = websocket.WebSocketApp(ws_url, on_open=on_open, on_message=on_message, on_error=on_error)
            
            ws_thread = threading.Thread(target=lambda: ws.run_forever())
            ws_thread.daemon = True
            ws_thread.start()
            ws_thread.join(timeout=10.0)
            
            # Check graceful handling
            error_msgs = [m for m in messages if m.get("type") == "error"]
            crash_errors = [m for m in error_msgs if "crash" in str(m).lower()]
            
            success = len(crash_errors) == 0 and connection_survived
            details = f"Survived: {connection_survived}, Errors: {len(error_msgs)}, Crashes: {len(crash_errors)}"
            
            self.log_result("STT Failure Handling", success, details)
            return success
            
        except Exception as e:
            self.log_result("STT Failure Handling", False, f"Exception: {e}")
            return False
    
    def test_presence_gate_regression(self):
        """Test 6: Presence gate blocks after 16s"""
        token = self.test_auth_pair()
        if not token:
            self.log_result("Presence Gate Regression", False, "No auth token")
            return False
        
        try:
            messages = []
            session_id = None
            blocked_received = False
            
            def on_message(ws, message):
                nonlocal session_id, blocked_received
                data = json.loads(message)
                messages.append(data)
                msg_type = data.get("type")
                
                if msg_type == "auth_ok":
                    session_id = data.get("payload", {}).get("session_id")
                    ws.send(json.dumps({"type": "heartbeat", "payload": {"session_id": session_id, "seq": 1}}))
                    
                elif msg_type == "heartbeat_ack":
                    # Wait 16.5 seconds
                    time.sleep(16.5)
                    
                    # Try execute
                    execute_msg = {
                        "type": "execute_request",
                        "payload": {"session_id": session_id, "draft_id": "test_draft"}
                    }
                    ws.send(json.dumps(execute_msg))
                    
                elif msg_type == "execute_blocked":
                    blocked_received = True
                    ws.close()
            
            def on_open(ws):
                auth_msg = {
                    "type": "auth",
                    "payload": {"token": token, "device_id": "presence_dev", "client_version": "1.0.0"}
                }
                ws.send(json.dumps(auth_msg))
            
            ws_url = "wss://voice-assistant-dev.preview.emergentagent.com/api/ws"
            ws = websocket.WebSocketApp(ws_url, on_open=on_open, on_message=on_message)
            
            ws_thread = threading.Thread(target=lambda: ws.run_forever())
            ws_thread.daemon = True
            ws_thread.start()
            ws_thread.join(timeout=25.0)
            
            # Check for blocked response
            blocked_msgs = [m for m in messages if m.get("type") == "execute_blocked"]
            stale_blocks = [m for m in blocked_msgs if "PRESENCE_STALE" in str(m)]
            
            success = blocked_received and len(stale_blocks) > 0
            details = f"Blocked received: {blocked_received}, Stale blocks: {len(stale_blocks)}"
            
            self.log_result("Presence Gate Regression", success, details)
            return success
            
        except Exception as e:
            self.log_result("Presence Gate Regression", False, f"Exception: {e}")
            return False
    
    def _create_audio_chunks(self):
        """Create 8 simple audio chunks"""
        # Generate simple sine wave audio data
        sample_rate = 16000
        duration = 2.0  # 2 seconds
        frequency = 440  # A4 note
        
        num_samples = int(duration * sample_rate)
        audio_samples = []
        
        for i in range(num_samples):
            t = i / sample_rate
            sample = int(16000 * math.sin(2 * math.pi * frequency * t))
            audio_samples.append(struct.pack('<h', sample))
        
        # Simple PCM data
        audio_data = b''.join(audio_samples)
        
        # Split into 8 chunks
        chunk_size = len(audio_data) // 8
        chunks = []
        for i in range(8):
            start = i * chunk_size
            end = start + chunk_size if i < 7 else len(audio_data)
            chunk_data = audio_data[start:end]
            chunks.append(base64.b64encode(chunk_data).decode('utf-8'))
        
        return chunks
    
    def run_all_tests(self):
        """Run all critical Deepgram tests"""
        print("🧪 MyndLens Batch 3 — Deepgram STT Integration Tests")
        print("=" * 60)
        print()
        
        # Run all tests
        test_results = [
            self.test_health_endpoint(),
            self.test_deepgram_audio_chunks(),
            self.test_text_input_regression(),
            self.test_stt_failure_handling(),
            self.test_presence_gate_regression()
        ]
        
        # Summary
        passed_count = sum(1 for result in test_results if result)
        total_count = len(test_results)
        
        print("=" * 60)
        print(f"📊 TEST SUMMARY: {passed_count}/{total_count} PASSED")
        print("=" * 60)
        
        failed_tests = [r for r in self.results if not r["passed"]]
        if failed_tests:
            print("\n❌ FAILED TESTS:")
            for test in failed_tests:
                print(f"  - {test['test']}: {test['details']}")
        
        passed_tests = [r for r in self.results if r["passed"]]
        if passed_tests:
            print(f"\n✅ PASSED TESTS: {len(passed_tests)}")
            for test in passed_tests:
                print(f"  - {test['test']}")
        
        return passed_count == total_count

def main():
    tester = DeepgramTester()
    success = tester.run_all_tests()
    
    if success:
        print("\n🎉 ALL DEEPGRAM STT TESTS PASSED!")
        print("Deepgram integration is ready for production.")
    else:
        print("\n💥 SOME TESTS FAILED")
        print("Check the details above and fix issues before production.")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)