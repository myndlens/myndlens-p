#!/usr/bin/env python3
"""
Quick focused test for L1 Scout + Dimension Engine with real Gemini Flash
"""

import asyncio
import json
import requests
import websockets
from datetime import datetime, timezone
import time

BACKEND_URL = "https://mandate-pipeline-1.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"
WS_URL = f"wss://voice-assistant-dev.preview.emergentagent.com/api/ws"

async def test_l1_scout_quick():
    print("🚀 Quick L1 Scout Test with Real Gemini Flash")
    
    # 1. Get SSO token
    response = requests.post(f"{API_BASE}/sso/myndlens/token", json={
        "username": "l1test",
        "password": "pass", 
        "device_id": "l1dev"
    })
    
    if response.status_code != 200:
        print(f"❌ SSO failed: {response.status_code}")
        return
        
    sso_token = response.json()["token"]
    print(f"✅ SSO token: ...{sso_token[-10:]}")
    
    # 2. Connect WebSocket
    ws = await websockets.connect(WS_URL)
    
    auth_msg = {
        "type": "auth",
        "payload": {
            "token": sso_token,
            "device_id": "l1dev", 
            "client_version": "1.0.0"
        }
    }
    await ws.send(json.dumps(auth_msg))
    
    auth_response = await ws.recv()
    auth_data = json.loads(auth_response)
    
    if auth_data.get("type") != "auth_ok":
        print(f"❌ Auth failed: {auth_data}")
        return
        
    session_id = auth_data["payload"]["session_id"]
    print(f"✅ WebSocket auth: {session_id}")
    
    # 3. Send heartbeat
    heartbeat_msg = {
        "type": "heartbeat",
        "payload": {
            "session_id": session_id,
            "seq": 1,
            "client_ts": datetime.now(timezone.utc).isoformat()
        }
    }
    await ws.send(json.dumps(heartbeat_msg))
    hb_response = await ws.recv()
    print(f"✅ Heartbeat: {json.loads(hb_response).get('type')}")
    
    # 4. Send text input - MOST IMPORTANT TEST
    test_text = "Send a message to Sarah about the meeting tomorrow at 3pm"
    text_msg = {
        "type": "text_input",
        "payload": {
            "session_id": session_id,
            "text": test_text
        }
    }
    
    print(f"📤 Sending: '{test_text}'")
    await ws.send(json.dumps(text_msg))
    
    # 5. Collect responses 
    responses = {}
    for _ in range(5):  # Expect: transcript_final, draft_update, tts_audio
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = json.loads(response)
            msg_type = msg.get("type")
            responses[msg_type] = msg
            print(f"📥 {msg_type}")
            
            if msg_type == "tts_audio":
                break
        except asyncio.TimeoutError:
            break
    
    await ws.close()
    
    # 6. Verify critical responses
    print("\n🔍 VERIFICATION:")
    
    # Check transcript_final
    if "transcript_final" in responses:
        print("✅ transcript_final received")
    else:
        print("❌ transcript_final missing")
    
    # Check draft_update (CRITICAL for Batch 4)
    if "draft_update" in responses:
        draft = responses["draft_update"]["payload"]
        print(f"✅ draft_update received")
        print(f"   Hypothesis: {draft.get('hypothesis', 'MISSING')[:60]}...")
        print(f"   Action Class: {draft.get('action_class', 'MISSING')}")
        print(f"   Confidence: {draft.get('confidence', 'MISSING')}")
        print(f"   Is Mock: {draft.get('is_mock', 'MISSING')}")
        
        # Check dimensions
        dims = draft.get("dimensions", {})
        a_set = dims.get("a_set", {})
        b_set = dims.get("b_set", {})
        
        print(f"   A-set fields: {list(a_set.keys())}")
        print(f"   Who: {a_set.get('who', 'NONE')}")
        print(f"   When: {a_set.get('when', 'NONE')}")
        print(f"   Turn count: {dims.get('turn_count', 'NONE')}")
        
    else:
        print("❌ draft_update missing - CRITICAL FAILURE")
    
    # Check TTS response  
    if "tts_audio" in responses:
        tts = responses["tts_audio"]["payload"]
        print(f"✅ tts_audio received")
        print(f"   Text: {tts.get('text', 'MISSING')[:60]}...")
        print(f"   Format: {tts.get('format', 'MISSING')}")
        print(f"   Is Mock: {tts.get('is_mock', 'MISSING')}")
    else:
        print("❌ tts_audio missing")
    
    print(f"\n🎯 L1 Scout Test Complete - Real Gemini Flash: {not draft.get('is_mock', True) if 'draft_update' in responses else 'UNKNOWN'}")

if __name__ == "__main__":
    asyncio.run(test_l1_scout_quick())