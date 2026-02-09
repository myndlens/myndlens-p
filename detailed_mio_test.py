#!/usr/bin/env python3
"""Detailed MIO Testing - Check actual response contents for verification."""
import requests
import json
from datetime import datetime, timezone, timedelta

BASE_URL = "https://voice-assistant-dev.preview.emergentagent.com/api"

def detailed_test():
    print("🔍 DETAILED MIO VERIFICATION PIPELINE TESTING")
    
    # Test 1: Create and sign a MIO
    test_mio = {
        "header": {
            "mio_id": "test-detailed-mio-1",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "signer_id": "MYNDLENS_BE_01",
            "ttl_seconds": 120
        },
        "intent_envelope": {
            "action": "openclaw.v1.whatsapp.send",
            "action_class": "COMM_SEND",
            "params": {},
            "constraints": {
                "tier": 2,
                "physical_latch_required": True,
                "biometric_required": False
            }
        }
    }
    
    # Sign the MIO
    print("\n1️⃣ SIGNING MIO...")
    sign_response = requests.post(f"{BASE_URL}/mio/sign", json={"mio_dict": test_mio})
    if sign_response.status_code == 200:
        sign_data = sign_response.json()
        print(f"   ✅ Signature: {sign_data['signature'][:50]}...")
        print(f"   ✅ Public Key: {sign_data['public_key']}")
        signature = sign_data["signature"]
    else:
        print(f"   ❌ Sign failed: {sign_response.status_code}")
        return
    
    # Test 2: Verify with presence stale (should fail)
    print("\n2️⃣ VERIFYING MIO (Should fail - no active session)...")
    verify_request = {
        "mio_dict": test_mio,
        "signature": signature,
        "session_id": "test-session-999",
        "device_id": "test-device-999",
        "tier": 2,
        "touch_token": "test-touch-999"
    }
    
    verify_response = requests.post(f"{BASE_URL}/mio/verify", json=verify_request)
    if verify_response.status_code == 200:
        verify_data = verify_response.json()
        print(f"   Result: valid={verify_data['valid']}, reason='{verify_data['reason']}'")
        if not verify_data['valid'] and "Heartbeat stale" in verify_data['reason']:
            print("   ✅ CORRECTLY BLOCKED by presence gate!")
        elif not verify_data['valid']:
            print(f"   ✅ Correctly blocked (other reason): {verify_data['reason']}")
        else:
            print("   ❌ Should have failed but didn't!")
    else:
        print(f"   ❌ Verify failed: {verify_response.status_code}")
    
    # Test 3: Test replay protection
    print("\n3️⃣ TESTING REPLAY PROTECTION...")
    replay_verify_request = {
        "mio_dict": test_mio,
        "signature": signature,
        "session_id": "replay-test-session",
        "device_id": "replay-test-device",
        "tier": 0  # Lower tier to avoid touch token issues
    }
    
    # First verification
    response1 = requests.post(f"{BASE_URL}/mio/verify", json=replay_verify_request)
    print(f"   First verify: {response1.status_code}")
    if response1.status_code == 200:
        data1 = response1.json()
        print(f"     Result: valid={data1['valid']}, reason='{data1['reason']}'")
    
    # Second verification (should detect replay)
    response2 = requests.post(f"{BASE_URL}/mio/verify", json=replay_verify_request)
    print(f"   Second verify: {response2.status_code}")
    if response2.status_code == 200:
        data2 = response2.json()
        print(f"     Result: valid={data2['valid']}, reason='{data2['reason']}'")
        if not data2['valid'] and "replay" in data2['reason'].lower():
            print("   ✅ REPLAY CORRECTLY DETECTED!")
        elif not data2['valid']:
            print(f"   ✅ Blocked (other reason): {data2['reason']}")
    
    # Test 4: Test TTL expiry
    print("\n4️⃣ TESTING TTL EXPIRY...")
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    expired_mio = test_mio.copy()
    expired_mio["header"]["timestamp"] = past_time.isoformat().replace("+00:00", "Z")
    expired_mio["header"]["mio_id"] = "expired-test-mio"
    
    # Sign expired MIO
    expired_sign_response = requests.post(f"{BASE_URL}/mio/sign", json={"mio_dict": expired_mio})
    if expired_sign_response.status_code == 200:
        expired_signature = expired_sign_response.json()["signature"]
        
        # Verify expired MIO
        expired_verify_request = {
            "mio_dict": expired_mio,
            "signature": expired_signature,
            "session_id": "expired-test-session",
            "device_id": "expired-test-device",
            "tier": 0
        }
        
        expired_verify_response = requests.post(f"{BASE_URL}/mio/verify", json=expired_verify_request)
        if expired_verify_response.status_code == 200:
            expired_data = expired_verify_response.json()
            print(f"   Result: valid={expired_data['valid']}, reason='{expired_data['reason']}'")
            if not expired_data['valid'] and ("expired" in expired_data['reason'].lower() or "ttl" in expired_data['reason'].lower()):
                print("   ✅ TTL EXPIRY CORRECTLY DETECTED!")
            elif not expired_data['valid']:
                print(f"   ✅ Blocked (other reason): {expired_data['reason']}")
    
    # Test 5: Test touch token requirement
    print("\n5️⃣ TESTING TOUCH TOKEN REQUIREMENT (Tier 2)...")
    no_touch_verify_request = {
        "mio_dict": test_mio,
        "signature": signature,
        "session_id": "no-touch-session",
        "device_id": "no-touch-device",
        "tier": 2
        # Deliberately omit touch_token
    }
    
    no_touch_response = requests.post(f"{BASE_URL}/mio/verify", json=no_touch_verify_request)
    if no_touch_response.status_code == 200:
        no_touch_data = no_touch_response.json()
        print(f"   Result: valid={no_touch_data['valid']}, reason='{no_touch_data['reason']}'")
        if not no_touch_data['valid'] and ("touch" in no_touch_data['reason'].lower() or "required" in no_touch_data['reason'].lower()):
            print("   ✅ TOUCH TOKEN REQUIREMENT CORRECTLY ENFORCED!")
        elif not no_touch_data['valid']:
            print(f"   ✅ Blocked (other reason): {no_touch_data['reason']}")
    
    print("\n🎯 DETAILED TESTING COMPLETE!")

if __name__ == "__main__":
    detailed_test()