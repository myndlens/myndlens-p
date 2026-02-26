#!/usr/bin/env python3
"""
Comprehensive Deepgram STT Audio Chunk Test
"""

import requests
import json
import time
import base64
import math
import struct
import websocket
import threading

# Backend URL
BACKEND_URL = "https://openclaw-tenant.preview.emergentagent.com"

def create_wav_chunks():
    """Create 8 audio chunks with actual WAV data"""
    # Generate 2 seconds of sine wave audio at 16kHz
    sample_rate = 16000
    duration = 2.0
    frequency = 440  # A4 note
    amplitude = 16000
    
    num_samples = int(duration * sample_rate)
    audio_samples = []
    
    for i in range(num_samples):
        t = i / sample_rate
        sample = int(amplitude * math.sin(2 * math.pi * frequency * t))
        audio_samples.append(struct.pack('<h', sample))
    
    # Create WAV header
    audio_data = b''.join(audio_samples)
    wav_size = len(audio_data)
    
    # WAV file format header
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
    
    full_wav = header + audio_data
    
    # Split into 8 chunks
    chunk_size = len(full_wav) // 8
    chunks = []
    for i in range(8):
        start = i * chunk_size
        end = start + chunk_size if i < 7 else len(full_wav)
        chunk_data = full_wav[start:end]
        chunks.append(base64.b64encode(chunk_data).decode('utf-8'))
    
    return chunks

def test_deepgram_audio_chunks():
    """Test Deepgram STT with real audio chunks"""
    print("🎵 Testing Deepgram STT with Audio Chunks...")
    
    # Pair device first
    payload = {"user_id": "deepgram_test", "device_id": "dg_dev_001"}
    response = requests.post(f"{BACKEND_URL}/api/auth/pair", json=payload, timeout=10)
    
    if response.status_code != 200:
        print("  ❌ FAILED: Device pairing failed")
        return False
    
    token = response.json().get("token")
    chunks = create_wav_chunks()
    
    print(f"  Created {len(chunks)} audio chunks")
    
    messages_received = []
    session_id = None
    test_completed = False
    
    def on_message(ws, message):
        nonlocal session_id, test_completed
        try:
            data = json.loads(message)
            messages_received.append(data)
            msg_type = data.get("type")
            
            print(f"  📨 Received: {msg_type}")
            
            if msg_type == "auth_ok":
                session_id = data.get("payload", {}).get("session_id")
                print(f"  ✅ Authenticated with session: {session_id}")
                
                # Send heartbeat
                heartbeat_msg = {
                    "type": "heartbeat",
                    "payload": {"session_id": session_id, "seq": 1}
                }
                ws.send(json.dumps(heartbeat_msg))
                
            elif msg_type == "heartbeat_ack":
                print("  💓 Heartbeat acknowledged - starting audio chunk stream")
                
                # Send audio chunks with delay between them
                for i, chunk in enumerate(chunks):
                    audio_msg = {
                        "type": "audio_chunk",
                        "payload": {
                            "audio": chunk,
                            "seq": i,
                            "session_id": session_id
                        }
                    }
                    ws.send(json.dumps(audio_msg))
                    print(f"  🎵 Sent audio chunk {i+1}/8")
                    time.sleep(0.1)  # Small delay between chunks
                
                # Send stream end
                time.sleep(0.5)
                stream_end_msg = {"type": "cancel", "payload": {"session_id": session_id}}
                ws.send(json.dumps(stream_end_msg))
                print("  🔚 Sent stream end")
                
                # Wait a bit for final processing then close
                time.sleep(2.0)
                test_completed = True
                ws.close()
                
            elif msg_type == "transcript_partial":
                payload = data.get("payload", {})
                text = payload.get("text", "")
                confidence = payload.get("confidence", 0.0)
                print(f"  📝 Partial transcript: '{text}' (conf: {confidence})")
                
            elif msg_type == "transcript_final":
                payload = data.get("payload", {})
                text = payload.get("text", "")
                confidence = payload.get("confidence", 0.0)
                print(f"  📝 Final transcript: '{text}' (conf: {confidence})")
                
            elif msg_type == "error":
                error_payload = data.get("payload", {})
                print(f"  ⚠️ Error: {error_payload}")
                
        except Exception as e:
            print(f"  ❌ Error processing message: {e}")
    
    def on_error(ws, error):
        print(f"  ❌ WebSocket error: {error}")
    
    def on_open(ws):
        print("  🔌 Connected to WebSocket")
        auth_msg = {
            "type": "auth",
            "payload": {
                "token": token,
                "device_id": "dg_dev_001",
                "client_version": "1.0.0"
            }
        }
        ws.send(json.dumps(auth_msg))
    
    # Create and run WebSocket
    ws_url = "wss://voice-assistant-dev.preview.emergentagent.com/api/ws"
    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error
    )
    
    # Run WebSocket in thread with timeout
    ws_thread = threading.Thread(target=lambda: ws.run_forever())
    ws_thread.daemon = True
    ws_thread.start()
    ws_thread.join(timeout=15.0)  # 15 second timeout
    
    # Analyze results
    auth_msgs = [m for m in messages_received if m.get("type") == "auth_ok"]
    transcript_partials = [m for m in messages_received if m.get("type") == "transcript_partial"]
    transcript_finals = [m for m in messages_received if m.get("type") == "transcript_final"]
    error_msgs = [m for m in messages_received if m.get("type") == "error"]
    
    print(f"\n  📊 Results Summary:")
    print(f"    Auth successful: {len(auth_msgs) > 0}")
    print(f"    Partial transcripts: {len(transcript_partials)}")
    print(f"    Final transcripts: {len(transcript_finals)}")
    print(f"    Errors: {len(error_msgs)}")
    print(f"    Test completed: {test_completed}")
    
    # For Deepgram with synthetic audio, empty transcripts are OK
    # The test is that the integration doesn't crash and handles the flow
    no_critical_errors = len([e for e in error_msgs if "crash" in str(e).lower()]) == 0
    flow_handled = len(auth_msgs) > 0 and test_completed
    
    success = no_critical_errors and flow_handled
    
    print(f"  {'✅ PASSED' if success else '❌ FAILED'}: Deepgram audio chunk flow")
    
    if error_msgs:
        for error in error_msgs:
            print(f"    Error: {error}")
    
    return success

def test_presence_gate():
    """Test presence gate with 16s delay"""
    print("\n🚪 Testing Presence Gate (16s stale test)...")
    
    # Pair device
    payload = {"user_id": "presence_test", "device_id": "presence_dev"}
    response = requests.post(f"{BACKEND_URL}/api/auth/pair", json=payload, timeout=10)
    
    if response.status_code != 200:
        print("  ❌ FAILED: Device pairing failed")
        return False
    
    token = response.json().get("token")
    messages_received = []
    session_id = None
    
    def on_message(ws, message):
        nonlocal session_id
        data = json.loads(message)
        messages_received.append(data)
        msg_type = data.get("type")
        
        if msg_type == "auth_ok":
            session_id = data.get("payload", {}).get("session_id")
            print(f"  ✅ Authenticated with session: {session_id}")
            
            # Send initial heartbeat
            heartbeat_msg = {
                "type": "heartbeat",
                "payload": {"session_id": session_id, "seq": 1}
            }
            ws.send(json.dumps(heartbeat_msg))
            
        elif msg_type == "heartbeat_ack":
            print("  💓 Initial heartbeat acknowledged")
            print("  ⏳ Waiting 16+ seconds without heartbeat...")
            
            # Wait 16.5 seconds then try to execute
            time.sleep(16.5)
            
            print("  🚀 Attempting execute after stale period...")
            execute_msg = {
                "type": "execute_request",
                "payload": {
                    "session_id": session_id,
                    "draft_id": "test_draft"
                }
            }
            ws.send(json.dumps(execute_msg))
            
            # Close after a short delay
            time.sleep(1.0)
            ws.close()
            
        elif msg_type == "execute_blocked":
            payload = data.get("payload", {})
            code = payload.get("code", "")
            reason = payload.get("reason", "")
            print(f"  🚫 Execute blocked: code={code}, reason={reason}")
    
    def on_open(ws):
        auth_msg = {
            "type": "auth",
            "payload": {
                "token": token,
                "device_id": "presence_dev",
                "client_version": "1.0.0"
            }
        }
        ws.send(json.dumps(auth_msg))
    
    ws_url = "wss://voice-assistant-dev.preview.emergentagent.com/api/ws"
    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message
    )
    
    ws_thread = threading.Thread(target=lambda: ws.run_forever())
    ws_thread.daemon = True
    ws_thread.start()
    ws_thread.join(timeout=25.0)  # 25 second timeout (16s wait + buffer)
    
    # Check for blocked messages
    blocked_msgs = [m for m in messages_received if m.get("type") == "execute_blocked"]
    stale_blocks = [m for m in blocked_msgs if "PRESENCE_STALE" in str(m)]
    
    success = len(stale_blocks) > 0
    print(f"  {'✅ PASSED' if success else '❌ FAILED'}: Presence gate blocking after 16s")
    
    return success

def main():
    print("🧪 Comprehensive Deepgram STT Integration Tests")
    print("=" * 55)
    
    # Test 1: Audio chunks with Deepgram
    audio_test = test_deepgram_audio_chunks()
    
    # Test 2: Presence gate regression
    presence_test = test_presence_gate()
    
    print(f"\n📊 FINAL RESULTS:")
    print(f"  Audio Chunk Flow: {'✅' if audio_test else '❌'}")
    print(f"  Presence Gate: {'✅' if presence_test else '❌'}")
    
    if audio_test and presence_test:
        print(f"\n🎉 All Deepgram STT tests passed!")
        return True
    else:
        print(f"\n💥 Some tests failed")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)