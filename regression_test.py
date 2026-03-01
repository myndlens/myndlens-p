#!/usr/bin/env python3
"""
Quick Regression Test for MyndLens B0-B2 functionality 
Ensures prompt system changes didn't break existing features
"""

import requests
import json
import sys

# Backend URL from environment
BACKEND_URL = "https://sovereign-exec-qa.preview.emergentagent.com"

def test_quick_regression():
    """Run quick regression test of critical endpoints"""
    print("🔄 Running Quick Regression Test...")
    
    # Test 1: Health endpoint
    try:
        response = requests.get(f"{BACKEND_URL}/api/health", timeout=10)
        if response.status_code == 200:
            print("✅ Health endpoint working")
        else:
            print(f"❌ Health endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health endpoint exception: {e}")
        return False
    
    # Test 2: Auth/Pair endpoint
    try:
        payload = {
            "user_id": "regression_test_user", 
            "device_id": "regression_test_device",
            "client_version": "1.0.0"
        }
        response = requests.post(f"{BACKEND_URL}/api/auth/pair", json=payload, timeout=10)
        if response.status_code == 200 and "token" in response.json():
            print("✅ Auth/Pair endpoint working")
        else:
            print(f"❌ Auth/Pair failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Auth/Pair exception: {e}")
        return False
        
    # Test 3: Prompt system working
    try:
        payload = {"purpose": "DIMENSIONS_EXTRACT", "transcript": "regression test"}
        response = requests.post(f"{BACKEND_URL}/api/prompt/build", json=payload, timeout=10)
        if response.status_code == 200 and "prompt_id" in response.json():
            print("✅ Prompt system working")
        else:
            print(f"❌ Prompt system failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Prompt system exception: {e}")
        return False
    
    print("\n🎉 All regression tests passed!")
    return True

if __name__ == "__main__":
    success = test_quick_regression()
    sys.exit(0 if success else 1)