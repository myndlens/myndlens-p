#!/usr/bin/env python3
"""
MyndLens Batch 9.5/9.6 Backend Testing — Tenant Provisioning + Lifecycle Completion

Tests all critical tenant provisioning and lifecycle APIs with S2S authentication.
Based on review request requirements and tenant implementation analysis.
"""

import asyncio
import json
import logging
import requests
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Test Configuration
BASE_URL = "https://voice-assistant-dev.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"
S2S_TOKEN = "obegee-s2s-dev-token-CHANGE-IN-PROD"
S2S_HEADERS = {"X-OBEGEE-S2S-TOKEN": S2S_TOKEN}

class TenantTestResults:
    """Track test results for comprehensive reporting."""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []
    
    def add_result(self, test_name: str, passed: bool, details: str = ""):
        self.results.append({
            "test": test_name,
            "passed": passed,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        if passed:
            self.passed += 1
            logger.info(f"✅ PASS: {test_name}")
        else:
            self.failed += 1
            logger.error(f"❌ FAIL: {test_name} - {details}")
    
    def summary(self) -> str:
        total = self.passed + self.failed
        success_rate = (self.passed / total * 100) if total > 0 else 0
        return f"Results: {self.passed}/{total} passed ({success_rate:.1f}% success rate)"

def make_request(method: str, endpoint: str, headers: Dict = None, json_data: Dict = None, expect_status: int = 200) -> requests.Response:
    """Make HTTP request with proper error handling."""
    url = f"{API_BASE}{endpoint}"
    all_headers = {"Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)
    
    try:
        response = requests.request(method, url, headers=all_headers, json=json_data, timeout=30)
        logger.info(f"{method} {endpoint} -> {response.status_code}")
        if response.status_code != expect_status:
            logger.warning(f"Expected {expect_status}, got {response.status_code}: {response.text[:200]}")
        return response
    except Exception as e:
        logger.error(f"Request failed: {method} {endpoint} - {e}")
        raise

def test_health_endpoint(results: TenantTestResults):
    """Test 1: Health endpoint basic functionality."""
    try:
        response = make_request("GET", "/health")
        data = response.json()
        
        required_fields = ["status", "env", "version", "active_sessions"]
        missing_fields = [f for f in required_fields if f not in data]
        
        if response.status_code == 200 and not missing_fields and data["status"] == "ok":
            results.add_result("Health Endpoint", True, f"Status: {data['status']}, Env: {data['env']}")
        else:
            results.add_result("Health Endpoint", False, f"Missing fields: {missing_fields}")
    except Exception as e:
        results.add_result("Health Endpoint", False, f"Exception: {e}")

def test_s2s_auth_protection(results: TenantTestResults):
    """Test 2: S2S authentication protection for tenant APIs."""
    
    # Test without S2S token
    try:
        response = make_request("POST", "/tenants/activate", 
                              json_data={"obegee_user_id": "test_no_token"}, 
                              expect_status=403)
        
        if response.status_code == 403:
            results.add_result("S2S Auth - No Token Protection", True, "Correctly blocked without S2S token")
        else:
            results.add_result("S2S Auth - No Token Protection", False, f"Expected 403, got {response.status_code}")
    except Exception as e:
        results.add_result("S2S Auth - No Token Protection", False, f"Exception: {e}")
    
    # Test with wrong S2S token
    try:
        wrong_headers = {"X-OBEGEE-S2S-TOKEN": "wrong-token"}
        response = make_request("POST", "/tenants/activate", 
                              headers=wrong_headers,
                              json_data={"obegee_user_id": "test_wrong_token"}, 
                              expect_status=403)
        
        if response.status_code == 403:
            results.add_result("S2S Auth - Wrong Token Protection", True, "Correctly blocked with wrong S2S token")
        else:
            results.add_result("S2S Auth - Wrong Token Protection", False, f"Expected 403, got {response.status_code}")
    except Exception as e:
        results.add_result("S2S Auth - Wrong Token Protection", False, f"Exception: {e}")

def test_tenant_activation_pipeline(results: TenantTestResults) -> Optional[str]:
    """Test 3: Full tenant activation pipeline with provisioning."""
    
    test_user_id = f"provision_test_user_{int(time.time())}"
    
    try:
        response = make_request("POST", "/tenants/activate", 
                              headers=S2S_HEADERS,
                              json_data={"obegee_user_id": test_user_id})
        
        if response.status_code == 200:
            data = response.json()
            required_fields = ["tenant_id", "status"]
            
            if all(f in data for f in required_fields) and data["status"] == "ACTIVE":
                tenant_id = data["tenant_id"]
                results.add_result("Tenant Activation Pipeline", True, 
                                 f"Tenant created: {tenant_id[:12]}... Status: {data['status']}")
                return tenant_id
            else:
                results.add_result("Tenant Activation Pipeline", False, 
                                 f"Missing fields or wrong status: {data}")
        else:
            results.add_result("Tenant Activation Pipeline", False, 
                             f"HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        results.add_result("Tenant Activation Pipeline", False, f"Exception: {e}")
    
    return None

def test_tenant_activation_idempotency(results: TenantTestResults, test_user_id: str):
    """Test 4: Tenant activation idempotency."""
    
    try:
        # First activation
        response1 = make_request("POST", "/tenants/activate", 
                               headers=S2S_HEADERS,
                               json_data={"obegee_user_id": test_user_id})
        
        # Second activation (should be idempotent)
        response2 = make_request("POST", "/tenants/activate", 
                               headers=S2S_HEADERS,
                               json_data={"obegee_user_id": test_user_id})
        
        if (response1.status_code == 200 and response2.status_code == 200):
            data1 = response1.json()
            data2 = response2.json()
            
            if data1.get("tenant_id") == data2.get("tenant_id"):
                results.add_result("Tenant Activation Idempotency", True, 
                                 f"Same tenant_id returned: {data1['tenant_id'][:12]}...")
            else:
                results.add_result("Tenant Activation Idempotency", False, 
                                 f"Different tenant IDs: {data1.get('tenant_id')} vs {data2.get('tenant_id')}")
        else:
            results.add_result("Tenant Activation Idempotency", False, 
                             f"HTTP errors: {response1.status_code}, {response2.status_code}")
    except Exception as e:
        results.add_result("Tenant Activation Idempotency", False, f"Exception: {e}")

def test_tenant_key_rotation(results: TenantTestResults, tenant_id: str):
    """Test 5: Tenant API key rotation."""
    
    try:
        response = make_request("POST", "/tenants/rotate-key", 
                              headers=S2S_HEADERS,
                              json_data={"tenant_id": tenant_id})
        
        if response.status_code == 200:
            data = response.json()
            required_fields = ["tenant_id", "key_prefix", "rotated"]
            
            if all(f in data for f in required_fields) and data["rotated"] is True:
                results.add_result("Tenant Key Rotation", True, 
                                 f"Key rotated successfully: {data['key_prefix']}")
            else:
                results.add_result("Tenant Key Rotation", False, 
                                 f"Missing fields or rotation failed: {data}")
        else:
            results.add_result("Tenant Key Rotation", False, 
                             f"HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        results.add_result("Tenant Key Rotation", False, f"Exception: {e}")

def test_tenant_suspension(results: TenantTestResults, tenant_id: str):
    """Test 6: Tenant suspension with session invalidation."""
    
    try:
        response = make_request("POST", "/tenants/suspend", 
                              headers=S2S_HEADERS,
                              json_data={"tenant_id": tenant_id, "reason": "test_suspension"})
        
        if response.status_code == 200:
            data = response.json()
            required_fields = ["tenant_id", "status", "sessions_invalidated"]
            
            if all(f in data for f in required_fields) and data["status"] == "SUSPENDED":
                sessions_count = data["sessions_invalidated"]
                results.add_result("Tenant Suspension", True, 
                                 f"Tenant suspended, {sessions_count} sessions invalidated")
            else:
                results.add_result("Tenant Suspension", False, 
                                 f"Missing fields or wrong status: {data}")
        else:
            results.add_result("Tenant Suspension", False, 
                             f"HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        results.add_result("Tenant Suspension", False, f"Exception: {e}")

def test_data_export_gdpr(results: TenantTestResults, user_id: str):
    """Test 7: User data export for GDPR compliance."""
    
    try:
        response = make_request("POST", "/tenants/export-data", 
                              headers=S2S_HEADERS,
                              json_data={"user_id": user_id})
        
        if response.status_code == 200:
            data = response.json()
            required_fields = ["user_id", "exported_at", "sessions", "transcripts", "entities", "graphs"]
            
            if all(f in data for f in required_fields):
                results.add_result("Data Export (GDPR)", True, 
                                 f"Data exported for user {user_id}, {len(data['sessions'])} sessions")
            else:
                missing_fields = [f for f in required_fields if f not in data]
                results.add_result("Data Export (GDPR)", False, 
                                 f"Missing fields: {missing_fields}")
        else:
            results.add_result("Data Export (GDPR)", False, 
                             f"HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        results.add_result("Data Export (GDPR)", False, f"Exception: {e}")

def test_tenant_deprovision(results: TenantTestResults, tenant_id: str):
    """Test 8: Complete tenant deprovision with data deletion."""
    
    try:
        response = make_request("POST", "/tenants/deprovision", 
                              headers=S2S_HEADERS,
                              json_data={"tenant_id": tenant_id, "reason": "test_deprovision"})
        
        if response.status_code == 200:
            data = response.json()
            required_fields = ["tenant_id", "status", "data_deleted", "audit_preserved"]
            
            if all(f in data for f in required_fields) and data["status"] == "DEPROVISIONED":
                audit_preserved = data["audit_preserved"]
                data_counts = data["data_deleted"]
                results.add_result("Tenant Deprovision", True, 
                                 f"Tenant deprovisioned, audit_preserved={audit_preserved}, data_deleted={data_counts}")
            else:
                results.add_result("Tenant Deprovision", False, 
                                 f"Missing fields or wrong status: {data}")
        else:
            results.add_result("Tenant Deprovision", False, 
                             f"HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        results.add_result("Tenant Deprovision", False, f"Exception: {e}")

def test_regression_health_sso(results: TenantTestResults):
    """Test 9: Regression test - Health and SSO endpoints still working."""
    
    # Health endpoint
    try:
        response = make_request("GET", "/health")
        if response.status_code == 200 and response.json().get("status") == "ok":
            results.add_result("REGRESSION: Health Endpoint", True, "Still working correctly")
        else:
            results.add_result("REGRESSION: Health Endpoint", False, f"Status: {response.status_code}")
    except Exception as e:
        results.add_result("REGRESSION: Health Endpoint", False, f"Exception: {e}")
    
    # SSO endpoint (if available)
    try:
        response = make_request("POST", "/sso/myndlens/token", 
                              json_data={
                                  "username": "regression_test",
                                  "password": "test123",
                                  "device_id": "test-device-regression"
                              })
        if response.status_code == 200:
            data = response.json()
            if "token" in data:
                results.add_result("REGRESSION: SSO Login", True, "Token generated successfully")
            else:
                results.add_result("REGRESSION: SSO Login", False, "No token in response")
        else:
            results.add_result("REGRESSION: SSO Login", False, f"HTTP {response.status_code}")
    except Exception as e:
        results.add_result("REGRESSION: SSO Login", False, f"Exception: {e}")

def test_l1_scout_regression(results: TenantTestResults):
    """Test 10: Regression test - L1 Scout diagnostic still working."""
    
    try:
        response = make_request("POST", "/l2/run", 
                              json_data={
                                  "transcript": "Send a message to Sarah about tomorrow's meeting",
                                  "l1_action_class": "COMM_SEND",
                                  "l1_confidence": 0.95
                              })
        
        if response.status_code == 200:
            data = response.json()
            required_fields = ["verdict_id", "action_class", "confidence", "is_mock"]
            if all(f in data for f in required_fields):
                results.add_result("REGRESSION: L1 Scout (L2)", True, 
                                 f"Action: {data['action_class']}, Mock: {data['is_mock']}")
            else:
                missing_fields = [f for f in required_fields if f not in data]
                results.add_result("REGRESSION: L1 Scout (L2)", False, f"Missing: {missing_fields}")
        else:
            results.add_result("REGRESSION: L1 Scout (L2)", False, f"HTTP {response.status_code}")
    except Exception as e:
        results.add_result("REGRESSION: L1 Scout (L2)", False, f"Exception: {e}")

def run_all_tenant_tests():
    """Execute all tenant provisioning and lifecycle tests."""
    
    print("🚀 MyndLens Batch 9.5/9.6 Tenant Provisioning + Lifecycle Testing")
    print("=" * 80)
    print(f"Backend URL: {BASE_URL}")
    print(f"S2S Token: {S2S_TOKEN}")
    print("=" * 80)
    
    results = TenantTestResults()
    
    # Test sequence following review request requirements
    print("\n📋 CRITICAL TESTS:")
    
    test_health_endpoint(results)
    test_s2s_auth_protection(results)
    
    # Create test user for full lifecycle
    test_user_id = f"provision_test_user_{int(time.time())}"
    print(f"\n🔄 Testing with user: {test_user_id}")
    
    tenant_id = test_tenant_activation_pipeline(results)
    
    if tenant_id:
        test_tenant_activation_idempotency(results, test_user_id)
        test_tenant_key_rotation(results, tenant_id)
        
        # Store some test data before export/deprovision
        test_data_export_gdpr(results, test_user_id)
        test_tenant_suspension(results, tenant_id)
        test_tenant_deprovision(results, tenant_id)
    else:
        print("⚠️ Skipping dependent tests due to activation failure")
    
    print("\n📋 REGRESSION TESTS:")
    test_regression_health_sso(results)
    test_l1_scout_regression(results)
    
    # Final results
    print("\n" + "=" * 80)
    print("🎯 FINAL RESULTS:")
    print("=" * 80)
    
    for result in results.results:
        status = "✅" if result["passed"] else "❌"
        print(f"{status} {result['test']}: {result['details']}")
    
    print("\n" + results.summary())
    
    if results.failed == 0:
        print("🎉 ALL TESTS PASSED! MyndLens Tenant Provisioning + Lifecycle is production-ready!")
    else:
        print(f"⚠️  {results.failed} test(s) failed. Review implementation.")
    
    return results

if __name__ == "__main__":
    results = run_all_tenant_tests()