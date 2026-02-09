#!/usr/bin/env python3
"""
MyndLens Prompt System Testing — Step 1 Infrastructure Tests
Testing dynamic prompt assembly without LLM calls

Critical Tests:
1. Golden prompt assembly test (DIMENSIONS_EXTRACT)
2. Golden prompt assembly test (THOUGHT_TO_INTENT)  
3. Cache stability test (deterministic hashing)
4. Tool gating test (EXECUTE vs DIMENSIONS_EXTRACT)
5. Report completeness + snapshot persistence
6. Purpose isolation test
7. Regression tests for B0-B2 functionality
"""

import asyncio
import requests
import json
import sys
from typing import Dict, List, Any

# Backend URL from environment
BACKEND_URL = "https://voice-assistant-dev.preview.emergentagent.com"

class PromptSystemTester:
    def __init__(self):
        self.base_url = BACKEND_URL
        self.results = []
        
    def log_test_result(self, test_name: str, passed: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASSED" if passed else "❌ FAILED"
        self.results.append({
            "test": test_name,
            "passed": passed,
            "details": details
        })
        print(f"{status}: {test_name}")
        if details:
            print(f"  Details: {details}")
        print()
    
    def test_health_regression(self):
        """Regression test: Health endpoint"""
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=10)
            data = response.json()
            
            # Verify expected fields
            expected_fields = ["status", "env", "version", "active_sessions"]
            missing_fields = [field for field in expected_fields if field not in data]
            
            if response.status_code == 200 and not missing_fields and data["status"] == "ok":
                self.log_test_result("Health Endpoint Regression", True, f"status={data['status']}, env={data['env']}")
            else:
                self.log_test_result("Health Endpoint Regression", False, f"Missing fields: {missing_fields}")
                
        except Exception as e:
            self.log_test_result("Health Endpoint Regression", False, f"Exception: {str(e)}")
    
    def test_auth_pair_regression(self):
        """Regression test: Auth/Pair endpoint"""
        try:
            payload = {
                "user_id": "test_user_prompt_system",
                "device_id": "test_device_prompt_system",
                "client_version": "1.0.0"
            }
            response = requests.post(f"{self.base_url}/api/auth/pair", json=payload, timeout=10)
            data = response.json()
            
            # Verify token creation
            expected_fields = ["token", "user_id", "device_id", "env"]
            missing_fields = [field for field in expected_fields if field not in data]
            
            # Verify JWT format (3 parts separated by dots)
            has_valid_jwt = "." in data.get("token", "") and len(data.get("token", "").split(".")) == 3
            
            if response.status_code == 200 and not missing_fields and has_valid_jwt:
                self.log_test_result("Auth/Pair Regression", True, f"JWT token created, user_id={data['user_id']}")
            else:
                self.log_test_result("Auth/Pair Regression", False, f"Missing fields: {missing_fields} or invalid JWT")
                
        except Exception as e:
            self.log_test_result("Auth/Pair Regression", False, f"Exception: {str(e)}")
    
    def test_prompt_build_dimensions_extract(self):
        """Critical Test 1: Golden prompt assembly test (DIMENSIONS_EXTRACT)"""
        try:
            payload = {
                "purpose": "DIMENSIONS_EXTRACT",
                "transcript": "Send a message to Sarah about the meeting tomorrow"
            }
            response = requests.post(f"{self.base_url}/api/prompt/build", json=payload, timeout=10)
            data = response.json()
            
            if response.status_code != 200:
                self.log_test_result("Prompt Build DIMENSIONS_EXTRACT", False, f"HTTP {response.status_code}: {response.text}")
                return
            
            # Verify required sections are included
            required_sections = {"IDENTITY_ROLE", "PURPOSE_CONTRACT", "OUTPUT_SCHEMA", "TASK_CONTEXT"}
            included = set(data.get("sections_included", []))
            missing_required = required_sections - included
            
            # Verify banned sections are excluded  
            banned_sections = {"TOOLING", "SKILLS_INDEX", "WORKSPACE_BOOTSTRAP"}
            excluded = set(data.get("sections_excluded", []))
            incorrectly_included = banned_sections - excluded
            
            # Verify messages array structure
            messages = data.get("messages", [])
            has_system_user_msgs = len(messages) >= 1 and any(msg.get("role") == "system" for msg in messages)
            
            # Verify report structure
            report = data.get("report", {})
            has_report_sections = "sections" in report
            
            all_checks_pass = (
                not missing_required and 
                not incorrectly_included and 
                has_system_user_msgs and 
                has_report_sections
            )
            
            details = f"Required included: {required_sections <= included}, Banned excluded: {banned_sections <= excluded}, Messages: {len(messages)}, Report: {has_report_sections}"
            
            self.log_test_result("Prompt Build DIMENSIONS_EXTRACT", all_checks_pass, details)
            return data
            
        except Exception as e:
            self.log_test_result("Prompt Build DIMENSIONS_EXTRACT", False, f"Exception: {str(e)}")
            return None
    
    def test_prompt_build_thought_to_intent(self):
        """Critical Test 2: Golden prompt assembly test (THOUGHT_TO_INTENT)"""
        try:
            payload = {
                "purpose": "THOUGHT_TO_INTENT",
                "transcript": "I need to call John"
            }
            response = requests.post(f"{self.base_url}/api/prompt/build", json=payload, timeout=10)
            data = response.json()
            
            if response.status_code != 200:
                self.log_test_result("Prompt Build THOUGHT_TO_INTENT", False, f"HTTP {response.status_code}: {response.text}")
                return
            
            # Verify required sections are included
            required_sections = {"IDENTITY_ROLE", "PURPOSE_CONTRACT", "OUTPUT_SCHEMA", "TASK_CONTEXT"}
            included = set(data.get("sections_included", []))
            missing_required = required_sections - included
            
            # Verify TOOLING is excluded for this purpose
            excluded = set(data.get("sections_excluded", []))
            tooling_excluded = "TOOLING" in excluded
            
            all_checks_pass = not missing_required and tooling_excluded
            details = f"Required included: {required_sections <= included}, TOOLING excluded: {tooling_excluded}"
            
            self.log_test_result("Prompt Build THOUGHT_TO_INTENT", all_checks_pass, details)
            return data
            
        except Exception as e:
            self.log_test_result("Prompt Build THOUGHT_TO_INTENT", False, f"Exception: {str(e)}")
            return None
    
    def test_cache_stability(self):
        """Critical Test 3: Cache stability test (deterministic hashing)"""
        try:
            payload = {
                "purpose": "DIMENSIONS_EXTRACT",
                "transcript": "Send a message to Sarah about the meeting tomorrow"
            }
            
            # Call the same endpoint twice
            response1 = requests.post(f"{self.base_url}/api/prompt/build", json=payload, timeout=10)
            response2 = requests.post(f"{self.base_url}/api/prompt/build", json=payload, timeout=10)
            
            if response1.status_code != 200 or response2.status_code != 200:
                self.log_test_result("Cache Stability Test", False, f"HTTP errors: {response1.status_code}, {response2.status_code}")
                return
            
            data1 = response1.json()
            data2 = response2.json()
            
            # Verify stable_hash is identical (deterministic)
            stable_hash1 = data1.get("stable_hash", "")
            stable_hash2 = data2.get("stable_hash", "")
            stable_identical = stable_hash1 == stable_hash2 and stable_hash1 != ""
            
            # Volatile hash should be same with same transcript
            volatile_hash1 = data1.get("volatile_hash", "")
            volatile_hash2 = data2.get("volatile_hash", "")
            volatile_identical = volatile_hash1 == volatile_hash2 and volatile_hash1 != ""
            
            all_checks_pass = stable_identical and volatile_identical
            details = f"Stable hash identical: {stable_identical}, Volatile hash identical: {volatile_identical}"
            
            self.log_test_result("Cache Stability Test", all_checks_pass, details)
            
        except Exception as e:
            self.log_test_result("Cache Stability Test", False, f"Exception: {str(e)}")
    
    def test_tool_gating(self):
        """Critical Test 4: Tool gating test"""
        try:
            # Test EXECUTE purpose - TOOLING should be included
            execute_payload = {
                "purpose": "EXECUTE",
                "transcript": "delete the file"
            }
            execute_response = requests.post(f"{self.base_url}/api/prompt/build", json=execute_payload, timeout=10)
            
            # Test DIMENSIONS_EXTRACT purpose - TOOLING should be excluded
            extract_payload = {
                "purpose": "DIMENSIONS_EXTRACT", 
                "transcript": "test"
            }
            extract_response = requests.post(f"{self.base_url}/api/prompt/build", json=extract_payload, timeout=10)
            
            if execute_response.status_code != 200 or extract_response.status_code != 200:
                self.log_test_result("Tool Gating Test", False, f"HTTP errors: {execute_response.status_code}, {extract_response.status_code}")
                return
            
            execute_data = execute_response.json()
            extract_data = extract_response.json()
            
            # Verify TOOLING inclusion/exclusion
            execute_included = set(execute_data.get("sections_included", []))
            execute_has_tooling = "TOOLING" in execute_included
            
            extract_excluded = set(extract_data.get("sections_excluded", []))
            extract_no_tooling = "TOOLING" in extract_excluded
            
            all_checks_pass = execute_has_tooling and extract_no_tooling
            details = f"EXECUTE includes TOOLING: {execute_has_tooling}, DIMENSIONS_EXTRACT excludes TOOLING: {extract_no_tooling}"
            
            self.log_test_result("Tool Gating Test", all_checks_pass, details)
            
        except Exception as e:
            self.log_test_result("Tool Gating Test", False, f"Exception: {str(e)}")
    
    def test_report_completeness_and_persistence(self):
        """Critical Test 5: Report completeness + snapshot persistence"""
        try:
            payload = {
                "purpose": "DIMENSIONS_EXTRACT",
                "transcript": "test report completeness"
            }
            response = requests.post(f"{self.base_url}/api/prompt/build", json=payload, timeout=10)
            
            if response.status_code != 200:
                self.log_test_result("Report Completeness & Persistence", False, f"HTTP {response.status_code}: {response.text}")
                return
            
            data = response.json()
            report = data.get("report", {})
            
            # Verify report has all 12 SectionIDs (from types.py enum)
            expected_section_ids = {
                "IDENTITY_ROLE", "PURPOSE_CONTRACT", "OUTPUT_SCHEMA", "TOOLING",
                "WORKSPACE_BOOTSTRAP", "SKILLS_INDEX", "RUNTIME_CAPABILITIES", 
                "SAFETY_GUARDRAILS", "TASK_CONTEXT", "MEMORY_RECALL_SNIPPETS",
                "DIMENSIONS_INJECTED", "CONFLICTS_SUMMARY"
            }
            
            report_sections = report.get("sections", [])
            reported_section_ids = {section.get("section_id") for section in report_sections}
            
            all_sections_present = expected_section_ids <= reported_section_ids
            
            # Verify excluded sections have gating_reason
            excluded_sections = [s for s in report_sections if not s.get("included", True)]
            excluded_have_reasons = all(s.get("gating_reason") for s in excluded_sections)
            
            # Verify report has prompt_id (indicates persistence)
            has_prompt_id = "prompt_id" in report and report["prompt_id"] != ""
            
            all_checks_pass = all_sections_present and excluded_have_reasons and has_prompt_id
            details = f"All 12 sections: {all_sections_present} ({len(reported_section_ids)}/12), Excluded reasons: {excluded_have_reasons}, Prompt ID: {has_prompt_id}"
            
            self.log_test_result("Report Completeness & Persistence", all_checks_pass, details)
            
        except Exception as e:
            self.log_test_result("Report Completeness & Persistence", False, f"Exception: {str(e)}")
    
    def test_purpose_isolation(self):
        """Critical Test 6: Purpose isolation test"""
        try:
            # Test DIMENSIONS_EXTRACT - should NOT contain execution instructions
            extract_payload = {
                "purpose": "DIMENSIONS_EXTRACT",
                "transcript": "test isolation"
            }
            extract_response = requests.post(f"{self.base_url}/api/prompt/build", json=extract_payload, timeout=10)
            
            # Test EXECUTE - should contain safety guardrails  
            execute_payload = {
                "purpose": "EXECUTE",
                "transcript": "delete something"
            }
            execute_response = requests.post(f"{self.base_url}/api/prompt/build", json=execute_payload, timeout=10)
            
            if extract_response.status_code != 200 or execute_response.status_code != 200:
                self.log_test_result("Purpose Isolation Test", False, f"HTTP errors: {extract_response.status_code}, {execute_response.status_code}")
                return
            
            extract_data = extract_response.json()
            execute_data = execute_response.json()
            
            # Check system message content differs between purposes
            extract_messages = extract_data.get("messages", [])
            execute_messages = execute_data.get("messages", [])
            
            extract_system = ""
            execute_system = ""
            
            for msg in extract_messages:
                if msg.get("role") == "system":
                    extract_system = msg.get("content", "")
                    
            for msg in execute_messages:
                if msg.get("role") == "system":
                    execute_system = msg.get("content", "")
            
            # Verify they are different (purpose isolation)
            systems_differ = extract_system != execute_system and extract_system != "" and execute_system != ""
            
            # Verify EXECUTE includes safety but DIMENSIONS_EXTRACT doesn't
            execute_included = set(execute_data.get("sections_included", []))
            extract_included = set(extract_data.get("sections_included", []))
            
            execute_has_safety = "SAFETY_GUARDRAILS" in execute_included
            extract_no_tooling = "TOOLING" not in extract_included
            
            all_checks_pass = systems_differ and execute_has_safety and extract_no_tooling
            details = f"System messages differ: {systems_differ}, EXECUTE has safety: {execute_has_safety}, EXTRACT no tools: {extract_no_tooling}"
            
            self.log_test_result("Purpose Isolation Test", all_checks_pass, details)
            
        except Exception as e:
            self.log_test_result("Purpose Isolation Test", False, f"Exception: {str(e)}")
    
    def run_all_tests(self):
        """Run all prompt system tests"""
        print("🧪 MyndLens Prompt System Infrastructure Tests")
        print("=" * 60)
        print()
        
        # Regression tests first
        print("📋 REGRESSION TESTS (B0-B2)")
        print("-" * 30)
        self.test_health_regression()
        self.test_auth_pair_regression()
        print()
        
        # Critical prompt system tests  
        print("🎯 CRITICAL PROMPT SYSTEM TESTS")
        print("-" * 35)
        self.test_prompt_build_dimensions_extract()
        self.test_prompt_build_thought_to_intent()
        self.test_cache_stability()
        self.test_tool_gating()
        self.test_report_completeness_and_persistence()
        self.test_purpose_isolation()
        print()
        
        # Summary
        passed_tests = [r for r in self.results if r["passed"]]
        failed_tests = [r for r in self.results if not r["passed"]]
        
        print("=" * 60)
        print(f"📊 TEST SUMMARY: {len(passed_tests)}/{len(self.results)} PASSED")
        print("=" * 60)
        
        if failed_tests:
            print("\n❌ FAILED TESTS:")
            for test in failed_tests:
                print(f"  - {test['test']}: {test['details']}")
        
        if passed_tests:
            print(f"\n✅ PASSED TESTS: {len(passed_tests)}")
            for test in passed_tests:
                print(f"  - {test['test']}")
        
        return len(failed_tests) == 0

def main():
    """Main test execution"""
    tester = PromptSystemTester()
    success = tester.run_all_tests()
    
    if success:
        print("\n🎉 ALL TESTS PASSED - Prompt System Infrastructure Ready!")
        sys.exit(0)
    else:
        print("\n💥 SOME TESTS FAILED - Check logs above")
        sys.exit(1)

if __name__ == "__main__":
    main()