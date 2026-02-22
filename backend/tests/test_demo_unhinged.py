"""MyndLens Backend Tests — DEMO_UNHINGED Preset

Tests the Unhinged Demo Agent Presets feature including:
- Approval gate (2-step flow: without approved=true returns APPROVAL_REQUIRED)
- HOST_UNHINGED profile (sandbox_mode=off)
- SANDBOX_UNHINGED profile (sandbox_mode=recommended, Docker isolation)
- Soil templates (SOUL.md, TOOLS.md, AGENTS.md)
- Tools config (profile=full, elevated=true, allowFrom restricted)
- Channel config (dmPolicy=allowlist, allowFrom restricted)
- Bindings with correct agentId and demo_sender peer
- Duplicate agent creation (EXISTS status)
- Test suite endpoint (8 tests)
- Teardown options (quick_disable, full_removal)
- Teardown operations (quick mode, full mode)
- Teardown validation (non-DEMO_UNHINGED, non-existent)
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://android-build-dev.preview.emergentagent.com').rstrip('/')


class TestUnhingedApprovalGate:
    """Tests for the 2-step approval gate flow"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.demo_sender = "+15551234567"
        self.tenant_id = f"TEST_tenant_{uuid.uuid4().hex[:8]}"

    def test_create_without_approved_returns_approval_required(self):
        """POST /api/agents/unhinged/create without approved flag returns APPROVAL_REQUIRED with prompt text"""
        payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": self.demo_sender,
            "sandbox_mode": "recommended",
            "approved": False,
            "agent_id": f"TEST_unhinged_{uuid.uuid4().hex[:8]}"
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "APPROVAL_REQUIRED"
        assert "approval_prompt" in data
        assert "WARNING" in data["approval_prompt"]
        assert "UNHINGED demo agent" in data["approval_prompt"]
        assert data["demo_sender"] == self.demo_sender
        assert data["profile"] == "SANDBOX_UNHINGED"  # recommended -> SANDBOX_UNHINGED
        assert "Resend with approved=true" in data.get("message", "")
        print(f"Approval gate: status={data['status']}, profile={data['profile']}")
        print(f"Approval prompt contains warning: {len(data['approval_prompt'])} chars")

    def test_create_without_demo_sender_returns_blocked(self):
        """POST /api/agents/unhinged/create without demo_sender returns BLOCKED"""
        payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "sandbox_mode": "recommended",
            "approved": True,
            "agent_id": f"TEST_unhinged_{uuid.uuid4().hex[:8]}"
            # Missing demo_sender
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "BLOCKED"
        assert "demo_sender" in data["message"].lower()
        print(f"Blocked without demo_sender: {data['message']}")

    def test_create_empty_demo_sender_returns_blocked(self):
        """POST /api/agents/unhinged/create with empty demo_sender returns BLOCKED"""
        payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": "",  # Empty string
            "sandbox_mode": "recommended",
            "approved": True,
            "agent_id": f"TEST_unhinged_{uuid.uuid4().hex[:8]}"
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "BLOCKED"
        print(f"Blocked with empty demo_sender: {data['message']}")


class TestSandboxUnhingedProfile:
    """Tests for SANDBOX_UNHINGED profile (Profile B - recommended)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.demo_sender = "+15559876543"
        self.tenant_id = f"TEST_tenant_{uuid.uuid4().hex[:8]}"
        self.agent_id = f"TEST_sandbox_{uuid.uuid4().hex[:8]}"

    def test_create_sandbox_unhinged_agent(self):
        """POST /api/agents/unhinged/create with sandbox_mode=recommended creates SANDBOX_UNHINGED profile"""
        payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": self.demo_sender,
            "sandbox_mode": "recommended",
            "approved": True,
            "agent_id": self.agent_id
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        assert data["agent_id"] == self.agent_id
        assert data["operation"] == "CREATE_UNHINGED"
        assert data["profile"] == "SANDBOX_UNHINGED"
        
        # Verify sandbox config with Docker isolation
        sandbox = data.get("sandbox", {})
        assert sandbox.get("mode") == "all"
        assert sandbox.get("scope") == "agent"
        assert "docker" in sandbox
        assert "setupCommand" in sandbox["docker"]
        
        print(f"SANDBOX_UNHINGED created: agent_id={self.agent_id}")
        print(f"Sandbox config: mode={sandbox.get('mode')}, docker setup present")
        
        return data

    def test_sandbox_unhinged_has_correct_soil_files(self):
        """Created SANDBOX_UNHINGED agent has correct soil files (SOUL.md, TOOLS.md, AGENTS.md)"""
        payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": self.demo_sender,
            "sandbox_mode": "recommended",
            "approved": True,
            "agent_id": f"TEST_soil_{uuid.uuid4().hex[:8]}"
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        agent = data.get("agent", {})
        soil = agent.get("soil", {})
        
        # Verify all soil files present
        assert "SOUL.md" in soil
        assert "TOOLS.md" in soil
        assert "AGENTS.md" in soil
        
        # Verify SOUL.md content
        assert "Unhinged Demo Agent" in soil["SOUL.md"]
        assert "ALL tools" in soil["SOUL.md"]
        
        # Verify TOOLS.md content
        assert "Tool Usage Patterns" in soil["TOOLS.md"]
        
        # Verify AGENTS.md content (Sandbox profile)
        assert "Sandbox-Unhinged" in soil["AGENTS.md"]
        assert "Docker isolation" in soil["AGENTS.md"]
        assert self.demo_sender in soil["AGENTS.md"]
        
        print("Soil files verified: SOUL.md, TOOLS.md, AGENTS.md present with correct content")

    def test_sandbox_unhinged_has_correct_tools_config(self):
        """Created SANDBOX_UNHINGED agent has correct tools config (profile=full, elevated=true, allowFrom restricted)"""
        payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": self.demo_sender,
            "sandbox_mode": "recommended",
            "approved": True,
            "agent_id": f"TEST_tools_{uuid.uuid4().hex[:8]}"
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        agent = data.get("agent", {})
        tools = agent.get("tools", {})
        
        # Verify tools config
        assert tools.get("profile") == "full"
        assert "group:openclaw" in tools.get("allow", [])
        
        # Verify elevated config
        elevated = tools.get("elevated", {})
        assert elevated.get("enabled") is True
        
        # Verify allowFrom is restricted to demo_sender
        allow_from = elevated.get("allowFrom", {})
        assert "whatsapp" in allow_from
        assert self.demo_sender in allow_from["whatsapp"]
        
        print(f"Tools config verified: profile={tools.get('profile')}, elevated={elevated.get('enabled')}")
        print(f"allowFrom restricted to: {allow_from}")

    def test_sandbox_unhinged_has_correct_channel_config(self):
        """Created SANDBOX_UNHINGED agent has correct channel config (dmPolicy=allowlist, allowFrom restricted)"""
        payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": self.demo_sender,
            "sandbox_mode": "recommended",
            "approved": True,
            "agent_id": f"TEST_channel_{uuid.uuid4().hex[:8]}"
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        agent = data.get("agent", {})
        channels = agent.get("channels", {})
        
        # Verify WhatsApp channel config
        whatsapp = channels.get("whatsapp", {})
        assert whatsapp.get("dmPolicy") == "allowlist"
        
        # Verify allowFrom is restricted (not wildcard)
        allow_from = whatsapp.get("allowFrom", [])
        assert self.demo_sender in allow_from
        assert "*" not in allow_from  # Must not use wildcard
        
        # Verify groups require mention
        groups = whatsapp.get("groups", {})
        assert groups.get("*", {}).get("requireMention") is True
        
        print(f"Channel config verified: dmPolicy={whatsapp.get('dmPolicy')}, allowFrom={allow_from}")

    def test_sandbox_unhinged_has_correct_bindings(self):
        """Created SANDBOX_UNHINGED agent has bindings with correct agentId and demo_sender peer"""
        agent_id = f"TEST_bind_{uuid.uuid4().hex[:8]}"
        payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": self.demo_sender,
            "sandbox_mode": "recommended",
            "approved": True,
            "agent_id": agent_id
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        agent = data.get("agent", {})
        bindings = agent.get("bindings", [])
        
        # Verify at least one binding
        assert len(bindings) > 0
        
        # Find the main binding
        main_binding = bindings[0]
        assert main_binding.get("agentId") == agent_id
        
        # Verify match config
        match = main_binding.get("match", {})
        assert match.get("provider") == "whatsapp"
        
        peer = match.get("peer", {})
        assert peer.get("kind") == "dm"
        assert peer.get("id") == self.demo_sender
        
        print(f"Bindings verified: agentId={main_binding.get('agentId')}, peer={peer}")


class TestHostUnhingedProfile:
    """Tests for HOST_UNHINGED profile (Profile A - no sandbox)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.demo_sender = "+15551112222"
        self.tenant_id = f"TEST_tenant_{uuid.uuid4().hex[:8]}"

    def test_create_host_unhinged_agent(self):
        """POST /api/agents/unhinged/create with sandbox_mode=off creates HOST_UNHINGED profile"""
        agent_id = f"TEST_host_{uuid.uuid4().hex[:8]}"
        payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": self.demo_sender,
            "sandbox_mode": "off",
            "approved": True,
            "agent_id": agent_id
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        assert data["agent_id"] == agent_id
        assert data["operation"] == "CREATE_UNHINGED"
        assert data["profile"] == "HOST_UNHINGED"
        
        # Verify sandbox is off
        sandbox = data.get("sandbox", {})
        assert sandbox.get("mode") == "off"
        
        # Verify agent config
        agent = data.get("agent", {})
        
        # HOST_UNHINGED should have all tool groups
        tools = agent.get("tools", {})
        assert tools.get("profile") == "full"
        
        # Check for all tool groups in allow list
        allow = tools.get("allow", [])
        assert "group:runtime" in allow or "group:fs" in allow or len(allow) > 0
        
        print(f"HOST_UNHINGED created: agent_id={agent_id}")
        print(f"Sandbox config: mode={sandbox.get('mode')}")

    def test_host_unhinged_soil_mentions_host(self):
        """Created HOST_UNHINGED agent soil files mention Host-Unhinged profile"""
        agent_id = f"TEST_host_soil_{uuid.uuid4().hex[:8]}"
        payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": self.demo_sender,
            "sandbox_mode": "off",
            "approved": True,
            "agent_id": agent_id
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        agent = data.get("agent", {})
        soil = agent.get("soil", {})
        
        # AGENTS.md should mention Host-Unhinged
        agents_md = soil.get("AGENTS.md", "")
        assert "Host-Unhinged" in agents_md or "HOST_UNHINGED" in agents_md
        assert "Sandboxed: No" in agents_md or "sandboxed: No" in agents_md.lower()
        
        print("HOST_UNHINGED soil files verified: mentions Host-Unhinged profile")


class TestDuplicateAgentCreation:
    """Tests for duplicate agent creation handling"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.demo_sender = "+15553334444"
        self.tenant_id = f"TEST_tenant_{uuid.uuid4().hex[:8]}"
        self.agent_id = f"TEST_dup_{uuid.uuid4().hex[:8]}"

    def test_duplicate_agent_creation_returns_exists(self):
        """Duplicate agent creation returns EXISTS status"""
        payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": self.demo_sender,
            "sandbox_mode": "recommended",
            "approved": True,
            "agent_id": self.agent_id
        }
        
        # First creation should succeed
        response1 = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["status"] == "SUCCESS"
        print(f"First creation: status={data1['status']}")
        
        # Second creation with same agent_id should return EXISTS
        response2 = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response2.status_code == 200
        data2 = response2.json()
        
        assert data2["status"] == "EXISTS"
        assert "existing_agent" in data2
        assert data2["existing_agent"]["agent_id"] == self.agent_id
        print(f"Duplicate creation: status={data2['status']}, existing_agent_id={data2['existing_agent']['agent_id']}")


class TestUnhingedTestSuite:
    """Tests for the 8-test validation suite endpoint"""

    def test_get_test_suite_returns_8_tests(self):
        """GET /api/agents/unhinged/test-suite/{agent_id} returns 8 tests"""
        agent_id = f"TEST_suite_{uuid.uuid4().hex[:8]}"
        demo_sender = "+15555550123"
        
        response = requests.get(
            f"{BASE_URL}/api/agents/unhinged/test-suite/{agent_id}",
            params={"demo_sender": demo_sender}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["agent_id"] == agent_id
        assert "tests" in data
        tests = data["tests"]
        
        # Must have exactly 8 tests
        assert len(tests) == 8
        
        # Verify test structure
        for test in tests:
            assert "id" in test
            assert "name" in test
            assert "description" in test
            assert "command" in test
            assert "expected" in test
        
        # Verify specific test names per spec
        test_names = [t["name"] for t in tests]
        expected_tests = [
            "smoke_test",
            "tool_surface",
            "web_research",
            "file_operations",
            "shell_execution",
            "browser_automation",
            "cron_scheduling",
            "destructive_confirmation"
        ]
        for expected in expected_tests:
            assert expected in test_names, f"Missing test: {expected}"
        
        print(f"Test suite verified: {len(tests)} tests")
        print(f"Test names: {test_names}")


class TestTeardownOptions:
    """Tests for teardown options endpoint"""

    def test_get_teardown_options(self):
        """GET /api/agents/unhinged/teardown-options returns quick_disable and full_removal"""
        response = requests.get(f"{BASE_URL}/api/agents/unhinged/teardown-options")
        assert response.status_code == 200
        data = response.json()
        
        # Must have both options
        assert "quick_disable" in data
        assert "full_removal" in data
        
        # Verify quick_disable structure
        quick = data["quick_disable"]
        assert "description" in quick
        assert "steps" in quick
        assert "allowlist" in quick["description"].lower()
        
        # Verify full_removal structure
        full = data["full_removal"]
        assert "description" in full
        assert "steps" in full
        assert "removal" in full["description"].lower() or "delete" in full["description"].lower()
        
        print(f"Teardown options: quick_disable steps={len(quick['steps'])}, full_removal steps={len(full['steps'])}")


class TestTeardownQuickMode:
    """Tests for teardown with mode=quick"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.demo_sender = "+15556667777"
        self.tenant_id = f"TEST_tenant_{uuid.uuid4().hex[:8]}"

    def test_teardown_quick_disables_agent(self):
        """POST /api/agents/unhinged/teardown with mode=quick disables agent (removes allowFrom, disables elevated)"""
        # First create an unhinged agent
        agent_id = f"TEST_tearq_{uuid.uuid4().hex[:8]}"
        create_payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": self.demo_sender,
            "sandbox_mode": "recommended",
            "approved": True,
            "agent_id": agent_id
        }
        create_resp = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=create_payload)
        assert create_resp.status_code == 200
        assert create_resp.json()["status"] == "SUCCESS"
        print(f"Created agent for teardown: {agent_id}")
        
        # Teardown with quick mode
        teardown_payload = {
            "agent_id": agent_id,
            "mode": "quick"
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/teardown", json=teardown_payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        assert data["agent_id"] == agent_id
        assert data["operation"] == "TEARDOWN_QUICK"
        assert "allowlist" in data.get("message", "").lower() or "disabled" in data.get("message", "").lower()
        
        print(f"Quick teardown: status={data['status']}, message={data.get('message')}")
        
        # Verify agent still exists but is disabled
        get_resp = requests.get(f"{BASE_URL}/api/agents/{agent_id}")
        assert get_resp.status_code == 200
        agent = get_resp.json()
        
        # Verify elevated is disabled
        elevated = agent.get("tools", {}).get("elevated", {})
        assert elevated.get("enabled") is False
        
        # Verify allowFrom is empty
        allow_from = agent.get("channels", {}).get("whatsapp", {}).get("allowFrom", [])
        assert len(allow_from) == 0
        
        print("Agent verified: elevated disabled, allowFrom empty")


class TestTeardownFullMode:
    """Tests for teardown with mode=full"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.demo_sender = "+15558889999"
        self.tenant_id = f"TEST_tenant_{uuid.uuid4().hex[:8]}"

    def test_teardown_full_retires_agent(self):
        """POST /api/agents/unhinged/teardown with mode=full retires agent with HARD_RETIRE"""
        # First create an unhinged agent
        agent_id = f"TEST_tearf_{uuid.uuid4().hex[:8]}"
        create_payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": self.demo_sender,
            "sandbox_mode": "recommended",
            "approved": True,
            "agent_id": agent_id
        }
        create_resp = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=create_payload)
        assert create_resp.status_code == 200
        assert create_resp.json()["status"] == "SUCCESS"
        print(f"Created agent for full teardown: {agent_id}")
        
        # Teardown with full mode
        teardown_payload = {
            "agent_id": agent_id,
            "mode": "full"
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/teardown", json=teardown_payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        assert data["agent_id"] == agent_id
        assert data["operation"] == "TEARDOWN_FULL"
        assert "retire_result" in data
        
        # Verify retire_result contains HARD_RETIRE
        retire_result = data.get("retire_result", {})
        assert retire_result.get("status") == "SUCCESS" or retire_result.get("mode") == "HARD_RETIRE"
        
        print(f"Full teardown: status={data['status']}, retire_result={retire_result.get('status')}")
        
        # Verify agent is now RETIRED
        get_resp = requests.get(f"{BASE_URL}/api/agents/{agent_id}")
        assert get_resp.status_code == 200
        agent = get_resp.json()
        assert agent.get("status") == "RETIRED"
        
        print(f"Agent status verified: {agent.get('status')}")


class TestTeardownValidation:
    """Tests for teardown validation (non-DEMO_UNHINGED, non-existent)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tenant_id = f"TEST_tenant_{uuid.uuid4().hex[:8]}"

    def test_teardown_nonexistent_agent_returns_failure(self):
        """Teardown of non-existent agent returns FAILURE"""
        teardown_payload = {
            "agent_id": f"nonexistent_{uuid.uuid4().hex[:8]}",
            "mode": "quick"
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/teardown", json=teardown_payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "FAILURE"
        assert "not found" in data.get("message", "").lower()
        print(f"Non-existent teardown: status={data['status']}, message={data.get('message')}")

    def test_teardown_non_unhinged_agent_returns_failure(self):
        """Teardown of non-DEMO_UNHINGED agent returns FAILURE"""
        # Create a regular (non-unhinged) agent
        agent_id = f"TEST_regular_{uuid.uuid4().hex[:8]}"
        create_payload = {
            "agent_spec": {
                "id": agent_id,
                "name": "Regular Agent",
                "tools": {"allow": ["web_search"], "deny": []}
            },
            "tenant": {"tenant_id": self.tenant_id}
        }
        create_resp = requests.post(f"{BASE_URL}/api/agents/create", json=create_payload)
        assert create_resp.status_code == 200
        print(f"Created regular agent: {agent_id}")
        
        # Try to teardown with unhinged endpoint
        teardown_payload = {
            "agent_id": agent_id,
            "mode": "quick"
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/teardown", json=teardown_payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "FAILURE"
        assert "DEMO_UNHINGED" in data.get("message", "") or "not a" in data.get("message", "").lower()
        print(f"Non-unhinged teardown: status={data['status']}, message={data.get('message')}")


class TestApprovalPromptContent:
    """Tests for approval prompt content validation"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.demo_sender = "+15550001111"
        self.tenant_id = f"TEST_tenant_{uuid.uuid4().hex[:8]}"

    def test_approval_prompt_for_sandbox_mentions_docker(self):
        """Approval prompt for SANDBOX_UNHINGED mentions Docker isolation"""
        payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": self.demo_sender,
            "sandbox_mode": "recommended",
            "approved": False,
            "agent_id": f"TEST_prompt_{uuid.uuid4().hex[:8]}"
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "APPROVAL_REQUIRED"
        prompt = data.get("approval_prompt", "")
        
        # Should mention Docker sandboxing
        assert "Docker" in prompt or "sandbox" in prompt.lower()
        assert "recommended" in prompt.lower() or "isolated" in prompt.lower()
        
        print("Sandbox approval prompt mentions Docker isolation")

    def test_approval_prompt_for_host_warns_higher_risk(self):
        """Approval prompt for HOST_UNHINGED warns about higher risk"""
        payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": self.demo_sender,
            "sandbox_mode": "off",
            "approved": False,
            "agent_id": f"TEST_host_prompt_{uuid.uuid4().hex[:8]}"
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "APPROVAL_REQUIRED"
        assert data["profile"] == "HOST_UNHINGED"
        prompt = data.get("approval_prompt", "")
        
        # Should mention higher risk for host mode
        assert "host" in prompt.lower() or "HIGHER RISK" in prompt
        
        print("Host approval prompt warns about higher risk")


class TestValidationIntegrity:
    """Tests for validation of created agent configs"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.demo_sender = "+15552223333"
        self.tenant_id = f"TEST_tenant_{uuid.uuid4().hex[:8]}"

    def test_created_agent_passes_validation(self):
        """Created unhinged agent passes internal validation checks"""
        agent_id = f"TEST_valid_{uuid.uuid4().hex[:8]}"
        payload = {
            "tenant": {"tenant_id": self.tenant_id},
            "demo_sender": self.demo_sender,
            "sandbox_mode": "recommended",
            "approved": True,
            "agent_id": agent_id
        }
        response = requests.post(f"{BASE_URL}/api/agents/unhinged/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        
        # Check validation results
        validation = data.get("validation", {})
        assert validation.get("passed") is True
        assert validation.get("checks_run", 0) > 0
        
        # No issues should be present
        issues = validation.get("issues", [])
        assert len(issues) == 0
        
        print(f"Validation passed: checks_run={validation.get('checks_run')}, issues={len(issues)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
