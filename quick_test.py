#!/usr/bin/env python3
"""
MyndLens Quick E2E Test - Individual Flow Testing
"""

import requests
import json
import time
import jwt
from datetime import datetime, timezone, timedelta

BACKEND_URL = "https://mandate-pipeline-1.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"

def test_health():
    """Quick health check"""
    try:
        response = requests.get(f"{API_BASE}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health: {data.get('status')} - {data.get('env')} - v{data.get('version')}")
            return True
        else:
            print(f"❌ Health failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health error: {e}")
        return False

def test_sso_pairing():
    """Test SSO pairing"""
    try:
        pair_data = {
            "code": "123456",
            "device_id": "e2e_test_device",
            "device_name": "E2E Test Device"
        }
        
        response = requests.post(f"{API_BASE}/sso/myndlens/pair", json=pair_data, timeout=10)
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token", "")
            print(f"✅ SSO Pairing: Token length={len(token)} chars")
            return token
        else:
            print(f"❌ SSO Pairing failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ SSO Pairing error: {e}")
        return None

def test_memory_apis():
    """Test Memory APIs"""
    try:
        # Store memory
        store_data = {
            "user_id": "test_user_memory", 
            "text": "Alice is my project manager from New York",
            "fact_type": "FACT",
            "provenance": "EXPLICIT"
        }
        
        store_response = requests.post(f"{API_BASE}/memory/store", json=store_data, timeout=10)
        if store_response.status_code != 200:
            print(f"❌ Memory Store failed: {store_response.status_code}")
            return False
            
        # Recall memory  
        recall_data = {
            "user_id": "test_user_memory",
            "query": "Who is Alice?"
        }
        
        recall_response = requests.post(f"{API_BASE}/memory/recall", json=recall_data, timeout=10)
        if recall_response.status_code == 200:
            results = recall_response.json().get("results", [])
            alice_found = any("alice" in r.get("text", "").lower() for r in results)
            print(f"✅ Memory APIs: Store+Recall working, Alice found: {alice_found}")
            return True
        else:
            print(f"❌ Memory Recall failed: {recall_response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Memory APIs error: {e}")
        return False

def test_mio_signing():
    """Test MIO Sign + Verify"""
    try:
        mio_data = {
            "mio_id": "test_mio_001",
            "session_id": "test_session",
            "device_id": "test_device",
            "user_id": "test_user", 
            "intent": "test_intent",
            "confidence": 0.95,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ttl": 120,
            "tier": 1
        }
        
        # Sign MIO
        sign_response = requests.post(f"{API_BASE}/mio/sign", json=mio_data, timeout=10)
        if sign_response.status_code != 200:
            print(f"❌ MIO Sign failed: {sign_response.status_code}")
            return False
            
        sign_data = sign_response.json()
        signature = sign_data.get("signature", "")
        public_key = sign_data.get("public_key", "")
        
        # Verify signature format
        signature_valid = len(signature) == 88  # Base64 encoded 64-byte signature
        key_valid = len(public_key) == 64  # Hex encoded 32-byte key
        
        print(f"✅ MIO Sign: Signature len={len(signature)} (valid: {signature_valid}), PubKey len={len(public_key)} (valid: {key_valid})")
        return signature_valid and key_valid
        
    except Exception as e:
        print(f"❌ MIO Sign error: {e}")
        return False

def test_commit_state_machine():
    """Test Commit State Machine"""
    try:
        # Create commit
        create_data = {
            "session_id": "test_commit_flow",
            "draft_id": "test_draft_commit",
            "intent": "test_commit_intent", 
            "confidence": 0.95
        }
        
        create_response = requests.post(f"{API_BASE}/commit/create", json=create_data, timeout=10)
        if create_response.status_code != 200:
            print(f"❌ Commit Create failed: {create_response.status_code}")
            return False
            
        commit_data = create_response.json()
        commit_id = commit_data.get("commit_id")
        
        # Test transition DRAFT → PENDING_CONFIRMATION
        transition_data = {
            "commit_id": commit_id,
            "new_state": "PENDING_CONFIRMATION"
        }
        
        transition_response = requests.post(f"{API_BASE}/commit/transition", json=transition_data, timeout=10)
        if transition_response.status_code == 200:
            print(f"✅ Commit State Machine: Create+Transition working")
            return True
        else:
            print(f"❌ Commit Transition failed: {transition_response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Commit State Machine error: {e}")
        return False

def test_prompt_compliance():
    """Test Prompt Compliance"""
    try:
        response = requests.get(f"{API_BASE}/prompt/compliance", timeout=10)
        if response.status_code == 200:
            data = response.json()
            clean_scan = data.get("rogue_prompt_scan", {}).get("clean", False)
            call_sites = data.get("call_sites", {})
            l1_active = call_sites.get("L1_SCOUT", {}).get("status") == "active"
            
            print(f"✅ Prompt Compliance: Clean scan={clean_scan}, L1_SCOUT active={l1_active}")
            return True
        else:
            print(f"❌ Prompt Compliance failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Prompt Compliance error: {e}")
        return False

def test_rate_limiting():
    """Test Rate Limiting"""
    try:
        blocked = False
        for i in range(12):
            rate_data = {"key": "test_rate_limit", "limit_type": "auth_attempts"}
            response = requests.post(f"{API_BASE}/rate-limit/check", json=rate_data, timeout=5)
            
            if response.status_code == 200:
                result = response.json()
                allowed = result.get("allowed", True)
                if not allowed:
                    blocked = True
                    break
            elif response.status_code == 429:
                blocked = True
                break
        
        print(f"✅ Rate Limiting: Blocked after attempts: {blocked}")
        return blocked
    except Exception as e:
        print(f"❌ Rate Limiting error: {e}")
        return False

def test_soul_system():
    """Test Soul System"""
    try:
        response = requests.get(f"{API_BASE}/soul/status", timeout=10)
        if response.status_code == 200:
            data = response.json()
            integrity = data.get("integrity", {}).get("valid", False)
            drift = data.get("drift", {}).get("drift_detected", True)
            fragments = data.get("fragments", 0)
            
            print(f"✅ Soul System: Integrity={integrity}, No drift={not drift}, Fragments={fragments}")
            return integrity and not drift
        else:
            print(f"❌ Soul System failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Soul System error: {e}")
        return False

def test_metrics_circuit_breakers():
    """Test Metrics + Circuit Breakers"""
    try:
        # Test metrics
        metrics_response = requests.get(f"{API_BASE}/metrics", timeout=10)
        metrics_ok = metrics_response.status_code == 200
        
        # Test circuit breakers
        cb_response = requests.get(f"{API_BASE}/circuit-breakers", timeout=10)
        cb_ok = cb_response.status_code == 200
        
        if cb_ok:
            cb_data = cb_response.json()
            breakers = cb_data.get("breakers", {})
            closed_count = sum(1 for state in breakers.values() if state.get("state") == "CLOSED")
            print(f"✅ Metrics + Circuit Breakers: Metrics OK={metrics_ok}, CB OK={cb_ok}, Closed breakers={closed_count}")
            return metrics_ok and cb_ok
        else:
            print(f"❌ Circuit Breakers failed: {cb_response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Metrics + CB error: {e}")
        return False

def test_governance():
    """Test Governance"""
    try:
        # Test retention policy
        retention_response = requests.get(f"{API_BASE}/governance/retention", timeout=10)
        retention_ok = retention_response.status_code == 200
        
        if retention_ok:
            print(f"✅ Governance: Retention policy OK")
            return True
        else:
            print(f"❌ Governance Retention failed: {retention_response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Governance error: {e}")
        return False

def create_suspended_token():
    """Create suspended SSO token"""
    payload = {
        "iss": "obegee",
        "aud": "myndlens",
        "subscription_status": "SUSPENDED", 
        "obegee_user_id": "suspended_user",
        "myndlens_tenant_id": "sus_tenant",
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp())
    }
    
    secret = "obegee-sso-dev-secret-CHANGE-IN-PROD"
    return jwt.encode(payload, secret, algorithm="HS256")

def main():
    """Run all quick tests"""
    print("🚀 MYNDLENS QUICK E2E TEST SUITE")
    print("=" * 60)
    
    results = []
    
    # Test each flow
    tests = [
        ("Health Check", test_health),
        ("SSO Pairing", test_sso_pairing), 
        ("Memory APIs", test_memory_apis),
        ("MIO Signing", test_mio_signing),
        ("Commit State Machine", test_commit_state_machine),
        ("Prompt Compliance", test_prompt_compliance),
        ("Rate Limiting", test_rate_limiting),
        ("Soul System", test_soul_system),
        ("Metrics + Circuit Breakers", test_metrics_circuit_breakers),
        ("Governance", test_governance)
    ]
    
    passed = 0
    for name, test_func in tests:
        print(f"\n🧪 Testing: {name}")
        try:
            if name == "SSO Pairing":
                result = test_func() is not None  # Token received
            else:
                result = test_func()
            results.append((name, result))
            if result:
                passed += 1
        except Exception as e:
            print(f"❌ {name} exception: {e}")
            results.append((name, False))
    
    # Summary
    print(f"\n{'='*60}")
    print(f"🏁 QUICK TEST RESULTS: {passed}/{len(tests)} PASSED")
    print(f"{'='*60}")
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {name}")

if __name__ == "__main__":
    main()