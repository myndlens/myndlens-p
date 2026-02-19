#!/usr/bin/env python3
"""
Focused ElevenLabs TTS Test - Debug WebSocket Connection Issues
===============================================================
"""

import asyncio
import base64
import json
import uuid
import aiohttp
import websockets

# Backend URL configuration
BACKEND_URL = "https://mandate-executor.preview.emergentagent.com"
WS_URL = "wss://voice-assistant-dev.preview.emergentagent.com/api/ws"
API_BASE = f"{BACKEND_URL}/api"

async def test_tts_flow():
    """Focused test for ElevenLabs TTS text input flow"""
    
    print("🔬 Starting focused ElevenLabs TTS test...")
    
    # Step 1: Get auth token
    async with aiohttp.ClientSession() as session:
        pair_data = {
            "user_id": "focused_tts_test",
            "device_id": "focused_device_123",
            "client_version": "1.0.0"
        }
        
        async with session.post(f"{API_BASE}/auth/pair", json=pair_data) as resp:
            if resp.status != 200:
                print(f"❌ Pairing failed: HTTP {resp.status}")
                return False
                
            auth_data = await resp.json()
            print(f"✅ Pairing successful: {auth_data['user_id']}")
    
    # Step 2: WebSocket connection with detailed debugging
    print("\n🔗 Connecting to WebSocket...")
    
    try:
        async with websockets.connect(WS_URL) as ws:
            print("✅ WebSocket connected")
            
            # Send auth
            auth_msg = {
                "type": "auth",
                "id": str(uuid.uuid4()),
                "payload": {
                    "token": auth_data['token'],
                    "device_id": auth_data['device_id'],
                    "client_version": "1.0.0"
                }
            }
            
            print("📤 Sending auth message...")
            await ws.send(json.dumps(auth_msg))
            
            print("📥 Waiting for auth response...")
            auth_response = await ws.recv()
            auth_resp = json.loads(auth_response)
            
            if auth_resp.get('type') != 'auth_ok':
                print(f"❌ Auth failed: {auth_resp}")
                return False
                
            session_id = auth_resp['payload']['session_id']
            print(f"✅ Authentication successful: {session_id}")
            
            # Send heartbeat first to establish presence
            heartbeat_msg = {
                "type": "heartbeat",
                "id": str(uuid.uuid4()),
                "payload": {
                    "session_id": session_id,
                    "seq": 1
                }
            }
            
            print("📤 Sending heartbeat...")
            await ws.send(json.dumps(heartbeat_msg))
            
            print("📥 Waiting for heartbeat ack...")
            heartbeat_response = await ws.recv()
            heartbeat_resp = json.loads(heartbeat_response)
            
            if heartbeat_resp.get('type') != 'heartbeat_ack':
                print(f"❌ Heartbeat failed: {heartbeat_resp}")
                return False
                
            print("✅ Heartbeat acknowledged")
            
            # Now send text input
            text_input_msg = {
                "type": "text_input",
                "id": str(uuid.uuid4()),
                "timestamp": "2024-01-01T00:00:00Z",
                "payload": {
                    "session_id": session_id,
                    "text": "Hello world"
                }
            }
            
            print(f"📤 Sending text input: '{text_input_msg['payload']['text']}'")
            await ws.send(json.dumps(text_input_msg))
            
            # Expect transcript_final first
            print("📥 Waiting for transcript_final...")
            response1 = await asyncio.wait_for(ws.recv(), timeout=10.0)
            transcript_resp = json.loads(response1)
            
            print(f"📋 Received: {transcript_resp['type']}")
            
            if transcript_resp.get('type') != 'transcript_final':
                print(f"❌ Expected transcript_final, got: {transcript_resp.get('type')}")
                print(f"Full response: {transcript_resp}")
                return False
                
            transcript_text = transcript_resp['payload'].get('text', '')
            print(f"✅ Transcript: '{transcript_text}'")
            
            # Expect tts_audio response
            print("📥 Waiting for tts_audio...")
            response2 = await asyncio.wait_for(ws.recv(), timeout=30.0)  # ElevenLabs might take a while
            tts_resp = json.loads(response2)
            
            print(f"🔊 Received: {tts_resp['type']}")
            
            if tts_resp.get('type') != 'tts_audio':
                print(f"❌ Expected tts_audio, got: {tts_resp.get('type')}")
                print(f"Full response: {tts_resp}")
                return False
                
            tts_payload = tts_resp.get('payload', {})
            
            print(f"\n🎯 TTS VALIDATION:")
            print(f"   Text: {tts_payload.get('text', 'MISSING')}")
            print(f"   Format: {tts_payload.get('format', 'MISSING')}")
            print(f"   Is Mock: {tts_payload.get('is_mock', 'MISSING')}")
            print(f"   Has Audio Field: {'audio' in tts_payload}")
            print(f"   Audio Size Bytes: {tts_payload.get('audio_size_bytes', 'MISSING')}")
            
            # Validate critical fields
            issues = []
            
            if tts_payload.get('format') != 'mp3':
                issues.append(f"Format should be 'mp3', got '{tts_payload.get('format')}'")
                
            if tts_payload.get('is_mock') != False:
                issues.append(f"is_mock should be false, got {tts_payload.get('is_mock')}")
                
            if 'audio' not in tts_payload:
                issues.append("Missing 'audio' field")
            else:
                # Validate base64 audio
                try:
                    audio_b64 = tts_payload['audio']
                    audio_bytes = base64.b64decode(audio_b64)
                    if len(audio_bytes) == 0:
                        issues.append("Audio is empty after base64 decode")
                    else:
                        print(f"   Audio B64 Length: {len(audio_b64)}")
                        print(f"   Audio Bytes Length: {len(audio_bytes)}")
                except Exception as e:
                    issues.append(f"Invalid base64 audio: {e}")
                    
            audio_size = tts_payload.get('audio_size_bytes', 0)
            if audio_size <= 0:
                issues.append(f"audio_size_bytes should be > 0, got {audio_size}")
            
            if issues:
                print(f"\n❌ VALIDATION ISSUES:")
                for issue in issues:
                    print(f"   - {issue}")
                return False
            else:
                print(f"\n✅ ALL TTS VALIDATIONS PASSED!")
                print(f"   Real ElevenLabs TTS is working correctly")
                print(f"   Generated {audio_size} bytes of MP3 audio")
                return True
                
    except websockets.ConnectionClosed as e:
        print(f"❌ WebSocket connection closed: {e}")
        return False
    except asyncio.TimeoutError:
        print(f"❌ Timeout waiting for response")
        return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_tts_flow())
    if success:
        print(f"\n🎉 ElevenLabs TTS integration test PASSED!")
    else:
        print(f"\n⚠️  ElevenLabs TTS integration test FAILED!")