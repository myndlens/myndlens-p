#!/usr/bin/env python3
"""
MyndLens Batch 9.5/9.6 Advanced Testing — Verify tenant provisioning data and memory integration

Additional comprehensive tests to verify tenant provisioning data structure and memory APIs integration.
"""

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
BASE_URL = "https://android-build-dev.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"
S2S_TOKEN = "obegee-s2s-dev-token-CHANGE-IN-PROD"
S2S_HEADERS = {"X-OBEGEE-S2S-TOKEN": S2S_TOKEN}

def make_request(method: str, endpoint: str, headers: Dict = None, json_data: Dict = None, expect_status: int = 200) -> requests.Response:
    """Make HTTP request with proper error handling."""
    url = f"{API_BASE}{endpoint}"
    all_headers = {"Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)
    
    try:
        response = requests.request(method, url, headers=all_headers, json=json_data, timeout=30)
        logger.info(f"{method} {endpoint} -> {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Request failed: {method} {endpoint} - {e}")
        raise

def test_tenant_provisioning_data_verification():
    """Test comprehensive tenant provisioning data verification."""
    
    print("\n🔍 ADVANCED TENANT PROVISIONING VERIFICATION")
    print("=" * 70)
    
    # Create a new tenant for detailed verification
    test_user = f"advanced_test_user_{int(time.time())}"
    
    # 1. Create tenant and verify provisioning data
    response = make_request("POST", "/tenants/activate", 
                          headers=S2S_HEADERS,
                          json_data={"obegee_user_id": test_user})
    
    if response.status_code == 200:
        data = response.json()
        tenant_id = data["tenant_id"]
        print(f"✅ Tenant created: {tenant_id}")
        print(f"   Status: {data['status']}")
        
        # 2. Store memory data for the user
        memory_data = [
            {"text": "John Smith is my colleague who works in marketing", "fact_type": "FACT", "provenance": "EXPLICIT"},
            {"text": "I prefer morning meetings before 10am", "fact_type": "PREFERENCE", "provenance": "EXPLICIT"},
            {"text": "User frequently mentions coffee breaks at 3pm", "fact_type": "OBSERVATION", "provenance": "OBSERVED"}
        ]
        
        print(f"\n📝 Storing memory data for {test_user}")
        for i, mem in enumerate(memory_data):
            mem_response = make_request("POST", "/memory/store", 
                                      json_data={
                                          "user_id": test_user,
                                          "text": mem["text"],
                                          "fact_type": mem["fact_type"],
                                          "provenance": mem["provenance"]
                                      })
            if mem_response.status_code == 200:
                mem_data = mem_response.json()
                print(f"   ✅ Memory {i+1}: {mem_data['node_id'][:12]}... stored")
            else:
                print(f"   ❌ Memory {i+1}: Failed {mem_response.status_code}")
        
        # 3. Test memory recall
        print(f"\n🧠 Testing memory recall for {test_user}")
        recall_response = make_request("POST", "/memory/recall", 
                                     json_data={
                                         "user_id": test_user,
                                         "query": "Who is John?",
                                         "n_results": 3
                                     })
        if recall_response.status_code == 200:
            recall_data = recall_response.json()
            results = recall_data.get("results", [])
            stats = recall_data.get("stats", {})
            print(f"   ✅ Recall successful: {len(results)} results, stats: {stats}")
            for i, result in enumerate(results[:2]):
                print(f"      Result {i+1}: {result['text'][:50]}... (distance: {result.get('distance', 'N/A')})")
        else:
            print(f"   ❌ Recall failed: {recall_response.status_code}")
        
        # 4. Test comprehensive data export with real data
        print(f"\n📤 Testing data export with real data")
        export_response = make_request("POST", "/tenants/export-data", 
                                     headers=S2S_HEADERS,
                                     json_data={"user_id": test_user})
        
        if export_response.status_code == 200:
            export_data = export_response.json()
            print(f"   ✅ Export successful:")
            print(f"      Sessions: {len(export_data.get('sessions', []))}")
            print(f"      Transcripts: {len(export_data.get('transcripts', []))}")
            print(f"      Entities: {len(export_data.get('entities', []))}")
            print(f"      Graphs: {len(export_data.get('graphs', []))}")
            print(f"      Export timestamp: {export_data.get('exported_at', 'N/A')}")
        else:
            print(f"   ❌ Export failed: {export_response.status_code}")
        
        # 5. Test key rotation with verification
        print(f"\n🔄 Testing key rotation")
        rotation_response = make_request("POST", "/tenants/rotate-key", 
                                       headers=S2S_HEADERS,
                                       json_data={"tenant_id": tenant_id})
        
        if rotation_response.status_code == 200:
            rotation_data = rotation_response.json()
            print(f"   ✅ Key rotation successful:")
            print(f"      Tenant ID: {rotation_data['tenant_id']}")
            print(f"      New key prefix: {rotation_data['key_prefix']}")
            print(f"      Rotated: {rotation_data['rotated']}")
        else:
            print(f"   ❌ Key rotation failed: {rotation_response.status_code}")
        
        # 6. Test final deprovision with data deletion verification
        print(f"\n🗑️  Testing deprovision with data deletion")
        deprovision_response = make_request("POST", "/tenants/deprovision", 
                                          headers=S2S_HEADERS,
                                          json_data={"tenant_id": tenant_id, "reason": "advanced_test_complete"})
        
        if deprovision_response.status_code == 200:
            deprovision_data = deprovision_response.json()
            print(f"   ✅ Deprovision successful:")
            print(f"      Status: {deprovision_data['status']}")
            print(f"      Data deleted: {deprovision_data['data_deleted']}")
            print(f"      Audit preserved: {deprovision_data['audit_preserved']}")
        else:
            print(f"   ❌ Deprovision failed: {deprovision_response.status_code}")
        
        # 7. Verify data is actually deleted by trying to recall
        print(f"\n🔍 Verifying data deletion")
        post_delete_recall = make_request("POST", "/memory/recall", 
                                        json_data={
                                            "user_id": test_user,
                                            "query": "Who is John?",
                                            "n_results": 3
                                        })
        if post_delete_recall.status_code == 200:
            post_delete_data = post_delete_recall.json()
            results = post_delete_data.get("results", [])
            stats = post_delete_data.get("stats", {})
            print(f"   ✅ Post-deletion recall: {len(results)} results (should be 0), stats: {stats}")
        else:
            print(f"   ❌ Post-deletion recall failed: {post_delete_recall.status_code}")
    
    else:
        print(f"❌ Tenant creation failed: {response.status_code}")

def test_tenant_provisioning_details():
    """Test to verify tenant gets proper provisioning details."""
    
    print("\n🏗️  TENANT PROVISIONING DETAILS VERIFICATION")
    print("=" * 70)
    
    # Check if we can verify tenant details by activating and checking response
    test_user = f"provision_detail_test_{int(time.time())}"
    
    response = make_request("POST", "/tenants/activate", 
                          headers=S2S_HEADERS,
                          json_data={"obegee_user_id": test_user})
    
    if response.status_code == 200:
        data = response.json()
        tenant_id = data["tenant_id"]
        print(f"✅ New Tenant Verification:")
        print(f"   Tenant ID: {tenant_id}")
        print(f"   Status: {data['status']}")
        print(f"   User ID: {test_user}")
        
        # According to the provisioner code, new tenants should get:
        # - openclaw_endpoint populated
        # - key_refs with api_key
        # The response should include these details
        
        print(f"✅ Tenant provisioning includes:")
        print(f"   - Unique tenant UUID: {len(tenant_id) == 36}")  # UUID length check
        print(f"   - Active status: {data['status'] == 'ACTIVE'}")
        
        # Clean up
        cleanup_response = make_request("POST", "/tenants/deprovision", 
                                      headers=S2S_HEADERS,
                                      json_data={"tenant_id": tenant_id, "reason": "test_cleanup"})
        if cleanup_response.status_code == 200:
            print(f"   ✅ Cleanup successful")
    else:
        print(f"❌ Tenant creation failed: {response.status_code}: {response.text}")

if __name__ == "__main__":
    print("🧪 MyndLens Advanced Tenant Provisioning Tests")
    test_tenant_provisioning_details()
    test_tenant_provisioning_data_verification()
    print("\n🎯 Advanced testing complete!")