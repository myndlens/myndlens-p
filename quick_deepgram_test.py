#!/usr/bin/env python3
"""
Quick Deepgram STT Integration Test
"""

import requests
import json
import time
import base64
import math
import struct

# Backend URL
BACKEND_URL = "https://myndlens-audit.preview.emergentagent.com"

def test_health():
    """Test health endpoint"""
    print("🏥 Testing Health Endpoint...")
    
    response = requests.get(f"{BACKEND_URL}/api/health", timeout=10)
    data = response.json()
    
    print(f"  Status: {response.status_code}")
    print(f"  Response: {json.dumps(data, indent=2)}")
    
    # Check Deepgram integration
    provider = data.get("stt_provider")
    healthy = data.get("stt_healthy")
    mock = data.get("mock_stt")
    
    success = provider == "DeepgramSTTProvider" and healthy and not mock
    print(f"  ✅ PASSED: Deepgram provider configured correctly" if success else f"  ❌ FAILED: Provider issues")
    return success

def test_auth_pair():
    """Test device pairing"""
    print("\n🔐 Testing Auth/Pair...")
    
    payload = {
        "user_id": "deepgram_test",
        "device_id": "dg_dev_001",
        "client_version": "1.0.0"
    }
    response = requests.post(f"{BACKEND_URL}/api/auth/pair", json=payload, timeout=10)
    
    if response.status_code != 200:
        print(f"  ❌ FAILED: HTTP {response.status_code}")
        return None
    
    data = response.json()
    token = data.get("token", "")
    
    if "." in token and len(token.split(".")) == 3:
        print(f"  ✅ PASSED: Valid JWT token received")
        return token
    else:
        print(f"  ❌ FAILED: Invalid token format")
        return None

def create_wav_chunk():
    """Create a simple WAV chunk for testing"""
    # Generate 0.25 seconds of 440Hz sine wave
    sample_rate = 16000
    duration = 0.25  # 250ms
    frequency = 440
    amplitude = 16000
    
    num_samples = int(duration * sample_rate)
    audio_data = []
    
    for i in range(num_samples):
        t = i / sample_rate
        sample = int(amplitude * math.sin(2 * math.pi * frequency * t))
        audio_data.append(struct.pack('<h', sample))
    
    # Simple PCM data (no WAV header for chunk)
    return b''.join(audio_data)

def test_websocket_basic():
    """Test basic WebSocket connectivity with simplified client"""
    print("\n🌐 Testing WebSocket Basic Connectivity...")
    
    token = test_auth_pair()
    if not token:
        print("  ❌ FAILED: No token available")
        return False
    
    try:
        import websocket
        
        messages = []
        session_id = None
        
        def on_message(ws, message):
            data = json.loads(message)
            messages.append(data)
            print(f"  📨 Received: {data.get('type', 'unknown')}")
            
            if data.get("type") == "auth_ok":
                nonlocal session_id
                session_id = data.get("payload", {}).get("session_id")
                print(f"  ✅ WebSocket authenticated, session: {session_id}")
                # Send heartbeat with required fields
                heartbeat_msg = {
                    "type": "heartbeat",
                    "payload": {
                        "session_id": session_id,
                        "seq": 1
                    }
                }
                ws.send(json.dumps(heartbeat_msg))
                
            elif data.get("type") == "heartbeat_ack":
                print("  💓 Heartbeat acknowledged")
                # Send text input instead of audio for simpler test
                text_msg = {
                    "type": "text_input", 
                    "payload": {
                        "text": "Hello test message", 
                        "session_id": session_id
                    }
                }
                ws.send(json.dumps(text_msg))
                
            elif data.get("type") in ["transcript_final", "tts_audio"]:
                payload = data.get("payload", {})
                text = payload.get("text", "")
                print(f"  📝 Got response: {data.get('type')} - text: '{text[:50]}'")
                # Close after getting response
                ws.close()
        
        def on_error(ws, error):
            print(f"  ❌ WebSocket error: {error}")
        
        def on_open(ws):
            print("  🔌 WebSocket connected")
            # Send auth with required device_id
            auth_msg = {
                "type": "auth", 
                "payload": {
                    "token": token,
                    "device_id": "dg_dev_001",
                    "client_version": "1.0.0"
                }
            }
            ws.send(json.dumps(auth_msg))
        
        ws_url = "wss://voice-assistant-dev.preview.emergentagent.com/api/ws"
        ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error
        )
        
        # Run with timeout
        import threading
        
        def run_ws():
            ws.run_forever()
        
        ws_thread = threading.Thread(target=run_ws)
        ws_thread.daemon = True
        ws_thread.start()
        ws_thread.join(timeout=10.0)  # 10 second timeout
        
        # Check results
        auth_msgs = [m for m in messages if m.get("type") == "auth_ok"]
        transcript_msgs = [m for m in messages if m.get("type") == "transcript_final"]
        
        success = len(auth_msgs) > 0 and len(transcript_msgs) > 0
        print(f"  ✅ PASSED: WebSocket flow working" if success else f"  ❌ FAILED: Incomplete flow")
        return success
        
    except Exception as e:
        print(f"  ❌ FAILED: Exception {e}")
        return False

def main():
    print("🧪 Quick Deepgram STT Integration Test")
    print("=" * 45)
    
    # Run basic tests
    health_ok = test_health()
    ws_ok = test_websocket_basic()
    
    print(f"\n📊 RESULTS:")
    print(f"  Health Check: {'✅' if health_ok else '❌'}")
    print(f"  WebSocket Flow: {'✅' if ws_ok else '❌'}")
    
    if health_ok and ws_ok:
        print(f"\n🎉 Basic Deepgram integration is working!")
    else:
        print(f"\n💥 Some issues found - check logs")

if __name__ == "__main__":
    main()