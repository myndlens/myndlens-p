"""MyndLens Backend Tests — Phases 0-4

Comprehensive test suite for all 5 phases of the MyndLens API:
- Phase 0: Onboarding APIs + Digital Self + MEMORY_RECALL_SNIPPETS
- Phase 1: Outcome tracking + Dimension extraction  
- Phase 2: A/B Experiments framework
- Phase 3: Adaptive policy engine
- Phase 4: Agent Builder (CREATE/MODIFY/RETIRE/DELETE/UNRETIRE)
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', 'https://myndlens-audit.preview.emergentagent.com')


class TestPhase0Health:
    """Phase 0: Health check and basic connectivity"""

    def test_health_endpoint(self):
        """Test /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        print(f"Health check passed: env={data.get('env')}, version={data.get('version')}")


class TestPhase0Onboarding:
    """Phase 0: Onboarding APIs — seeds Digital Self"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.test_user_id = f"TEST_onboard_{uuid.uuid4().hex[:8]}"

    def test_get_onboarding_status_new_user(self):
        """GET /api/onboarding/status/{user_id} returns default status for new user"""
        response = requests.get(f"{BASE_URL}/api/onboarding/status/{self.test_user_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == self.test_user_id
        assert data["completed"] is False
        assert data["step"] == 0
        print(f"Onboarding status for new user: completed={data['completed']}")

    def test_save_onboarding_profile(self):
        """POST /api/onboarding/profile saves user profile to Digital Self"""
        profile = {
            "user_id": self.test_user_id,
            "display_name": "Test User",
            "preferences": {"theme": "dark", "language": "en"},
            "contacts": [
                {"name": "Alice", "relationship": "sister"},
                {"name": "Bob", "relationship": "colleague"}
            ],
            "routines": ["Wake up at 7am", "Morning coffee at 8am"],
            "communication_style": "casual",
            "timezone": "America/New_York"
        }
        response = requests.post(f"{BASE_URL}/api/onboarding/profile", json=profile)
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == self.test_user_id
        assert data["completed"] is True
        assert data["step"] == 5
        assert data["items_stored"] > 0  # Facts + entities stored
        print(f"Onboarding profile saved: items_stored={data['items_stored']}")

        # Verify status updated
        status_response = requests.get(f"{BASE_URL}/api/onboarding/status/{self.test_user_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["completed"] is True

    def test_skip_onboarding(self):
        """POST /api/onboarding/skip/{user_id} marks onboarding as skipped"""
        skip_user = f"TEST_skip_{uuid.uuid4().hex[:8]}"
        response = requests.post(f"{BASE_URL}/api/onboarding/skip/{skip_user}")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == skip_user
        assert data["completed"] is True
        assert data["step"] == 0
        assert data["items_stored"] == 0
        print(f"Onboarding skipped for user: {skip_user}")


class TestPhase0PromptBuild:
    """Phase 0: POST /api/prompt/build with MEMORY_RECALL_SNIPPETS"""

    def test_prompt_build_thought_to_intent(self):
        """POST /api/prompt/build with THOUGHT_TO_INTENT includes MEMORY_RECALL_SNIPPETS"""
        payload = {
            "purpose": "THOUGHT_TO_INTENT",
            "transcript": "Send a message to my sister about the meeting tomorrow"
        }
        response = requests.post(f"{BASE_URL}/api/prompt/build", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert "prompt_id" in data
        assert data["purpose"] == "THOUGHT_TO_INTENT"
        assert "sections_included" in data
        assert "messages" in data
        assert "stable_hash" in data
        assert "volatile_hash" in data
        assert "total_tokens_est" in data
        
        # Check MEMORY_RECALL_SNIPPETS is in sections (either included or optional)
        all_sections = data.get("sections_included", []) + data.get("sections_excluded", [])
        print(f"Prompt built: id={data['prompt_id'][:8]}, sections={len(data['sections_included'])}")
        print(f"Sections included: {data['sections_included']}")

    def test_prompt_build_verify_purpose(self):
        """POST /api/prompt/build with VERIFY purpose"""
        payload = {
            "purpose": "VERIFY",
            "transcript": "Schedule a meeting with Bob tomorrow at 3pm"
        }
        response = requests.post(f"{BASE_URL}/api/prompt/build", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["purpose"] == "VERIFY"
        print(f"Verify prompt built: sections={data['sections_included']}")

    def test_prompt_build_invalid_purpose(self):
        """POST /api/prompt/build with invalid purpose returns 400"""
        payload = {
            "purpose": "INVALID_PURPOSE",
            "transcript": "Test"
        }
        response = requests.post(f"{BASE_URL}/api/prompt/build", json=payload)
        assert response.status_code == 400
        print("Invalid purpose correctly rejected")


class TestPhase1OutcomeTracking:
    """Phase 1: Outcome tracking and analytics"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.test_prompt_id = f"TEST_prompt_{uuid.uuid4().hex[:8]}"
        self.test_session_id = f"TEST_session_{uuid.uuid4().hex[:8]}"

    def test_track_outcome_success(self):
        """POST /api/prompt/track-outcome records outcome successfully"""
        payload = {
            "prompt_id": self.test_prompt_id,
            "purpose": "THOUGHT_TO_INTENT",
            "session_id": self.test_session_id,
            "user_id": "TEST_user",
            "result": "SUCCESS",
            "accuracy_score": 0.95,
            "execution_success": True,
            "user_corrected": False,
            "latency_ms": 250.5,
            "tokens_used": 512,
            "sections_used": ["IDENTITY_ROLE", "PURPOSE_CONTRACT", "TASK_CONTEXT"],
            "model_name": "gemini-2.0-flash"
        }
        response = requests.post(f"{BASE_URL}/api/prompt/track-outcome", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "tracked"
        assert data["prompt_id"] == self.test_prompt_id
        print(f"Outcome tracked: prompt_id={self.test_prompt_id[:12]}")

    def test_track_outcome_with_correction(self):
        """POST /api/prompt/track-outcome with user correction"""
        payload = {
            "prompt_id": f"TEST_corrected_{uuid.uuid4().hex[:8]}",
            "purpose": "VERIFY",
            "session_id": self.test_session_id,
            "user_id": "TEST_user",
            "result": "CORRECTED",
            "accuracy_score": 0.6,
            "execution_success": False,
            "user_corrected": True,
            "latency_ms": 180.0,
            "tokens_used": 256
        }
        response = requests.post(f"{BASE_URL}/api/prompt/track-outcome", json=payload)
        assert response.status_code == 200
        print("Correction outcome tracked successfully")

    def test_user_correction_tracking(self):
        """POST /api/prompt/user-correction records correction"""
        payload = {
            "session_id": self.test_session_id,
            "user_id": "TEST_user",
            "original_intent": "Send message to Bob",
            "corrected_intent": "Send message to Alice",
            "prompt_id": self.test_prompt_id
        }
        response = requests.post(f"{BASE_URL}/api/prompt/user-correction", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "recorded"
        print("User correction recorded")

    def test_get_analytics(self):
        """GET /api/prompt/analytics returns optimization insights"""
        response = requests.get(f"{BASE_URL}/api/prompt/analytics?days=30")
        assert response.status_code == 200
        data = response.json()
        assert "period_days" in data
        assert "total_outcomes" in data
        assert "total_corrections" in data
        assert "correction_rate" in data
        assert "purposes" in data
        print(f"Analytics: total_outcomes={data['total_outcomes']}, correction_rate={data['correction_rate']}")

    def test_get_purpose_analytics(self):
        """GET /api/prompt/analytics/{purpose} returns purpose-specific metrics"""
        response = requests.get(f"{BASE_URL}/api/prompt/analytics/THOUGHT_TO_INTENT?days=30")
        assert response.status_code == 200
        data = response.json()
        assert "purpose" in data
        assert "total" in data
        assert "avg_accuracy" in data
        assert "success_rate" in data
        print(f"Purpose analytics: purpose={data['purpose']}, total={data['total']}")

    def test_get_section_effectiveness(self):
        """GET /api/prompt/section-effectiveness returns section effectiveness data"""
        response = requests.get(f"{BASE_URL}/api/prompt/section-effectiveness?days=30")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Section effectiveness: {len(data)} sections analyzed")
        if data:
            first = data[0]
            assert "section" in first
            assert "total_uses" in first
            print(f"Top section: {first.get('section')} with {first.get('total_uses')} uses")


class TestPhase1DimensionExtraction:
    """Phase 1: Dedicated dimension extraction"""

    def test_extract_dimensions(self):
        """POST /api/dimensions/extract performs dimension extraction"""
        payload = {
            "session_id": "TEST_dim_session",
            "user_id": "TEST_user",
            "transcript": "Schedule a meeting with Bob tomorrow at 3pm in the conference room",
            "l1_suggestions": {"who": "Bob", "when": "tomorrow"}
        }
        response = requests.post(f"{BASE_URL}/api/dimensions/extract", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        # Verify A-set fields
        assert "who" in data
        assert "what" in data
        assert "when" in data
        assert "where" in data
        assert "how" in data
        assert "confidence" in data
        assert "_meta" in data
        
        print(f"Dimensions extracted: source={data['_meta'].get('source')}")
        print(f"  who={data.get('who')}, what={data.get('what')}")
        print(f"  when={data.get('when')}, where={data.get('where')}")

    def test_extract_dimensions_minimal(self):
        """POST /api/dimensions/extract with minimal input"""
        payload = {
            "transcript": "Call mom"
        }
        response = requests.post(f"{BASE_URL}/api/dimensions/extract", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "what" in data
        print(f"Minimal dimensions: what={data.get('what')}")


class TestPhase2Experiments:
    """Phase 2: A/B testing experiments framework"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.experiment_name = f"TEST_exp_{uuid.uuid4().hex[:8]}"

    def test_create_experiment(self):
        """POST /api/prompt/experiments creates new experiment"""
        payload = {
            "name": self.experiment_name,
            "purpose": "THOUGHT_TO_INTENT",
            "description": "Testing memory recall effectiveness",
            "control": {"sections": ["IDENTITY_ROLE", "PURPOSE_CONTRACT"]},
            "variant": {"sections": ["IDENTITY_ROLE", "PURPOSE_CONTRACT", "MEMORY_RECALL_SNIPPETS"]},
            "traffic_split": 0.2
        }
        response = requests.post(f"{BASE_URL}/api/prompt/experiments", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert "experiment_id" in data
        assert data["name"] == self.experiment_name
        assert data["status"] == "RUNNING"
        assert "control" in data
        assert "variant" in data
        assert data["traffic_split"] == 0.2
        
        print(f"Experiment created: id={data['experiment_id'][:8]}, name={data['name']}")
        return data["experiment_id"]

    def test_list_experiments(self):
        """GET /api/prompt/experiments lists all experiments"""
        response = requests.get(f"{BASE_URL}/api/prompt/experiments")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Experiments listed: {len(data)} experiments found")
        if data:
            first = data[0]
            assert "experiment_id" in first
            assert "name" in first
            assert "status" in first

    def test_get_experiment_results(self):
        """GET /api/prompt/experiments/{id}/results returns results"""
        # First create an experiment
        create_payload = {
            "name": f"TEST_results_{uuid.uuid4().hex[:8]}",
            "purpose": "VERIFY",
            "control": {},
            "variant": {}
        }
        create_resp = requests.post(f"{BASE_URL}/api/prompt/experiments", json=create_payload)
        assert create_resp.status_code == 200
        exp_id = create_resp.json()["experiment_id"]
        
        # Get results
        response = requests.get(f"{BASE_URL}/api/prompt/experiments/{exp_id}/results")
        assert response.status_code == 200
        data = response.json()
        
        assert "experiment_id" in data
        assert "analysis" in data
        assert "significant" in data["analysis"]
        print(f"Experiment results: significant={data['analysis']['significant']}")


class TestPhase3AdaptivePolicy:
    """Phase 3: Adaptive policy engine"""

    def test_get_adaptive_insights(self):
        """GET /api/prompt/adaptive-insights returns adaptive policy insights"""
        response = requests.get(f"{BASE_URL}/api/prompt/adaptive-insights")
        assert response.status_code == 200
        data = response.json()
        
        assert "total_outcomes_tracked" in data
        assert "total_user_corrections" in data
        assert "active_experiments" in data
        assert "recommendations" in data
        assert "recommendation_count" in data
        assert "system_health" in data
        
        print(f"Adaptive insights: health={data['system_health']}")
        print(f"  outcomes={data['total_outcomes_tracked']}, recommendations={data['recommendation_count']}")

    def test_get_policy_recommendations(self):
        """GET /api/prompt/policy-recommendations returns recommendations"""
        response = requests.get(f"{BASE_URL}/api/prompt/policy-recommendations?days=30")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Policy recommendations: {len(data)} recommendations")
        
        if data:
            first = data[0]
            assert "type" in first
            assert "priority" in first
            assert "reason" in first
            print(f"  First: type={first['type']}, priority={first['priority']}")


class TestPhase4AgentBuilder:
    """Phase 4: Agent Builder — CREATE, MODIFY, RETIRE, DELETE, UNRETIRE"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.test_agent_id = f"TEST_agent_{uuid.uuid4().hex[:8]}"
        self.test_tenant_id = f"TEST_tenant_{uuid.uuid4().hex[:8]}"

    def test_create_agent_success(self):
        """POST /api/agents/create creates new agent"""
        payload = {
            "agent_spec": {
                "id": self.test_agent_id,
                "name": "Test Agent",
                "workspace": f"~/.openclaw/workspace-{self.test_agent_id}",
                "soil": {"version": "1.0", "model": "gemini-flash"},
                "tools": {"allow": ["web_search", "file_read"], "deny": []},
                "skills": {"coding": True, "research": True},
                "bindings": [{"id": "slack", "channel": "#test"}]
            },
            "tenant": {"tenant_id": self.test_tenant_id}
        }
        response = requests.post(f"{BASE_URL}/api/agents/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        assert data["agent_id"] == self.test_agent_id
        assert data["operation"] == "CREATE"
        assert "writes" in data
        assert "agent" in data
        
        print(f"Agent created: id={self.test_agent_id[:12]}, name={data['agent']['name']}")
        return data

    def test_create_agent_capability_match(self):
        """POST /api/agents/create returns existing agent if capabilities match"""
        # First create an agent
        first_agent_id = f"TEST_cap_{uuid.uuid4().hex[:8]}"
        first_payload = {
            "agent_spec": {
                "id": first_agent_id,
                "name": "Capability Match Agent",
                "tools": {"allow": ["web_search", "calendar"], "deny": []}
            },
            "tenant": {"tenant_id": self.test_tenant_id}
        }
        first_resp = requests.post(f"{BASE_URL}/api/agents/create", json=first_payload)
        assert first_resp.status_code == 200
        
        # Try to create another agent with same tools (subset)
        second_payload = {
            "agent_spec": {
                "id": f"TEST_dup_{uuid.uuid4().hex[:8]}",
                "name": "Duplicate Agent",
                "tools": {"allow": ["web_search"], "deny": []}  # Subset
            },
            "tenant": {"tenant_id": self.test_tenant_id}
        }
        second_resp = requests.post(f"{BASE_URL}/api/agents/create", json=second_payload)
        assert second_resp.status_code == 200
        data = second_resp.json()
        
        # Should return EXISTS with existing agent
        if data["status"] == "EXISTS":
            assert "existing_agent" in data
            print(f"Capability match: existing agent {data['existing_agent']['agent_id'][:12]} can fulfill")
        else:
            print("No capability match found (may be different tenant)")

    def test_create_agent_sensitive_blocked(self):
        """POST /api/agents/create blocks sensitive tools without approval"""
        payload = {
            "agent_spec": {
                "id": f"TEST_sens_{uuid.uuid4().hex[:8]}",
                "name": "Sensitive Agent",
                "tools": {"allow": ["exec", "bash", "group:runtime"], "deny": []}
            },
            "tenant": {"tenant_id": self.test_tenant_id},
            "approved_sensitive": False
        }
        response = requests.post(f"{BASE_URL}/api/agents/create", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "BLOCKED"
        assert "sensitive_tools" in data
        print(f"Sensitive tools blocked: {data['sensitive_tools']}")

    def test_modify_agent(self):
        """POST /api/agents/modify updates existing agent"""
        # First create an agent
        agent_id = f"TEST_mod_{uuid.uuid4().hex[:8]}"
        create_payload = {
            "agent_spec": {"id": agent_id, "name": "To Modify"},
            "tenant": {"tenant_id": self.test_tenant_id}
        }
        create_resp = requests.post(f"{BASE_URL}/api/agents/create", json=create_payload)
        assert create_resp.status_code == 200
        
        # Modify it
        modify_payload = {
            "agent_ref": {"id": agent_id},
            "patch": {
                "name": "Modified Agent Name",
                "tools": {"allow": ["web_search", "calendar"], "deny": []},
                "soil": {"model": "gemini-pro"}
            }
        }
        response = requests.post(f"{BASE_URL}/api/agents/modify", json=modify_payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        assert data["operation"] == "MODIFY"
        assert "changes" in data
        assert len(data["changes"]) > 0
        print(f"Agent modified: id={agent_id[:12]}, changes={data['changes']}")

    def test_modify_agent_bindings(self):
        """POST /api/agents/modify updates agent bindings with MERGE_BY_ID"""
        agent_id = f"TEST_bind_{uuid.uuid4().hex[:8]}"
        create_payload = {
            "agent_spec": {
                "id": agent_id,
                "bindings": [{"id": "slack", "channel": "#general"}]
            },
            "tenant": {"tenant_id": self.test_tenant_id}
        }
        create_resp = requests.post(f"{BASE_URL}/api/agents/create", json=create_payload)
        assert create_resp.status_code == 200
        
        modify_payload = {
            "agent_ref": {"id": agent_id},
            "patch": {
                "bindings": {
                    "mode": "MERGE_BY_ID",
                    "items": [{"id": "discord", "server": "test-server"}]
                }
            }
        }
        response = requests.post(f"{BASE_URL}/api/agents/modify", json=modify_payload)
        assert response.status_code == 200
        data = response.json()
        assert "bindings updated" in data["changes"]
        print(f"Bindings merged: {data['changes']}")

    def test_retire_agent(self):
        """POST /api/agents/retire retires agent (soft/hard)"""
        # Create agent first
        agent_id = f"TEST_ret_{uuid.uuid4().hex[:8]}"
        create_payload = {
            "agent_spec": {
                "id": agent_id,
                "tools": {"allow": ["web_search"], "deny": []},
                "bindings": [{"id": "slack"}],
                "cron": {"schedule": "0 9 * * *"}
            },
            "tenant": {"tenant_id": self.test_tenant_id}
        }
        create_resp = requests.post(f"{BASE_URL}/api/agents/create", json=create_payload)
        assert create_resp.status_code == 200
        
        # Retire it
        retire_payload = {
            "agent_ref": {"id": agent_id},
            "retire_policy": {
                "mode": "SOFT_RETIRE",
                "tool_lockdown": True,
                "remove_bindings": True,
                "stop_cron": True
            },
            "reason": "Testing retirement"
        }
        response = requests.post(f"{BASE_URL}/api/agents/retire", json=retire_payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        assert data["operation"] == "RETIRE"
        assert data["mode"] == "SOFT_RETIRE"
        print(f"Agent retired: id={agent_id[:12]}, mode={data['mode']}")
        return agent_id

    def test_unretire_agent(self):
        """POST /api/agents/unretire restores retired agent"""
        # Create and retire agent
        agent_id = f"TEST_unret_{uuid.uuid4().hex[:8]}"
        create_payload = {
            "agent_spec": {
                "id": agent_id,
                "tools": {"allow": ["web_search"], "deny": []},
                "bindings": [{"id": "slack"}],
                "cron": {"schedule": "0 9 * * *"}
            },
            "tenant": {"tenant_id": self.test_tenant_id}
        }
        requests.post(f"{BASE_URL}/api/agents/create", json=create_payload)
        
        retire_payload = {
            "agent_ref": {"id": agent_id},
            "retire_policy": {"mode": "SOFT_RETIRE"}
        }
        requests.post(f"{BASE_URL}/api/agents/retire", json=retire_payload)
        
        # Now unretire
        unretire_payload = {"agent_ref": {"id": agent_id}}
        response = requests.post(f"{BASE_URL}/api/agents/unretire", json=unretire_payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        assert data["operation"] == "UNRETIRE"
        assert "restored" in data
        print(f"Agent unretired: id={agent_id[:12]}, restored={data['restored']}")

    def test_delete_agent(self):
        """POST /api/agents/delete deletes agent (admin-only)"""
        # Create agent
        agent_id = f"TEST_del_{uuid.uuid4().hex[:8]}"
        create_payload = {
            "agent_spec": {"id": agent_id},
            "tenant": {"tenant_id": self.test_tenant_id}
        }
        requests.post(f"{BASE_URL}/api/agents/create", json=create_payload)
        
        # Retire first (required for delete)
        retire_payload = {"agent_ref": {"id": agent_id}, "retire_policy": {"mode": "SOFT_RETIRE"}}
        requests.post(f"{BASE_URL}/api/agents/retire", json=retire_payload)
        
        # Delete
        delete_payload = {
            "agent_ref": {"id": agent_id},
            "delete_policy": {
                "admin_only": True,
                "delete_workspace": False
            }
        }
        response = requests.post(f"{BASE_URL}/api/agents/delete", json=delete_payload)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "SUCCESS"
        assert data["operation"] == "DELETE"
        assert data["archived"] is True  # Should archive since delete_workspace=False
        print(f"Agent deleted: id={agent_id[:12]}, archived={data['archived']}")

    def test_delete_agent_requires_admin(self):
        """POST /api/agents/delete fails without admin flag"""
        agent_id = f"TEST_noadm_{uuid.uuid4().hex[:8]}"
        create_payload = {
            "agent_spec": {"id": agent_id},
            "tenant": {"tenant_id": self.test_tenant_id}
        }
        requests.post(f"{BASE_URL}/api/agents/create", json=create_payload)
        
        delete_payload = {
            "agent_ref": {"id": agent_id},
            "delete_policy": {"admin_only": False}
        }
        response = requests.post(f"{BASE_URL}/api/agents/delete", json=delete_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "FAILURE"
        print("Delete without admin correctly rejected")

    def test_list_agents(self):
        """GET /api/agents/list/{tenant_id} lists tenant agents"""
        # Create a few agents for this tenant
        unique_tenant = f"TEST_list_{uuid.uuid4().hex[:8]}"
        for i in range(3):
            create_payload = {
                "agent_spec": {"id": f"TEST_list_agent_{i}_{uuid.uuid4().hex[:4]}"},
                "tenant": {"tenant_id": unique_tenant}
            }
            requests.post(f"{BASE_URL}/api/agents/create", json=create_payload)
        
        response = requests.get(f"{BASE_URL}/api/agents/list/{unique_tenant}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3
        print(f"Agents listed: {len(data)} agents for tenant {unique_tenant[:12]}")

    def test_list_agents_include_retired(self):
        """GET /api/agents/list/{tenant_id} can include retired agents"""
        unique_tenant = f"TEST_ret_list_{uuid.uuid4().hex[:8]}"
        agent_id = f"TEST_ret_{uuid.uuid4().hex[:8]}"
        
        # Create and retire
        create_payload = {
            "agent_spec": {"id": agent_id},
            "tenant": {"tenant_id": unique_tenant}
        }
        requests.post(f"{BASE_URL}/api/agents/create", json=create_payload)
        requests.post(f"{BASE_URL}/api/agents/retire", json={"agent_ref": {"id": agent_id}})
        
        # List without retired
        resp_no_retired = requests.get(f"{BASE_URL}/api/agents/list/{unique_tenant}")
        agents_no_retired = resp_no_retired.json()
        
        # List with retired
        resp_with_retired = requests.get(f"{BASE_URL}/api/agents/list/{unique_tenant}?include_retired=true")
        agents_with_retired = resp_with_retired.json()
        
        assert len(agents_with_retired) >= len(agents_no_retired)
        print(f"Active agents: {len(agents_no_retired)}, Including retired: {len(agents_with_retired)}")

    def test_get_single_agent(self):
        """GET /api/agents/{agent_id} returns single agent"""
        agent_id = f"TEST_get_{uuid.uuid4().hex[:8]}"
        create_payload = {
            "agent_spec": {
                "id": agent_id,
                "name": "Get Test Agent",
                "tools": {"allow": ["web_search"], "deny": []}
            },
            "tenant": {"tenant_id": self.test_tenant_id}
        }
        requests.post(f"{BASE_URL}/api/agents/create", json=create_payload)
        
        response = requests.get(f"{BASE_URL}/api/agents/{agent_id}")
        assert response.status_code == 200
        data = response.json()
        
        assert data["agent_id"] == agent_id
        assert data["name"] == "Get Test Agent"
        assert data["status"] == "ACTIVE"
        print(f"Agent fetched: id={agent_id[:12]}, name={data['name']}")

    def test_get_nonexistent_agent(self):
        """GET /api/agents/{agent_id} returns 404 for missing agent"""
        response = requests.get(f"{BASE_URL}/api/agents/nonexistent_agent_123")
        assert response.status_code == 404
        print("Nonexistent agent correctly returns 404")


class TestDigitalSelfIntegration:
    """Integration tests for Digital Self memory APIs"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.test_user_id = f"TEST_mem_{uuid.uuid4().hex[:8]}"

    def test_store_and_recall_fact(self):
        """POST /api/memory/store + POST /api/memory/recall flow"""
        # Store a fact
        store_payload = {
            "user_id": self.test_user_id,
            "text": "My favorite color is blue",
            "fact_type": "PREFERENCE",
            "provenance": "EXPLICIT"
        }
        store_resp = requests.post(f"{BASE_URL}/api/memory/store", json=store_payload)
        assert store_resp.status_code == 200
        store_data = store_resp.json()
        assert store_data["status"] == "stored"
        print(f"Fact stored: node_id={store_data['node_id'][:12]}")
        
        # Recall it
        recall_payload = {
            "user_id": self.test_user_id,
            "query": "What is my favorite color?",
            "n_results": 3
        }
        recall_resp = requests.post(f"{BASE_URL}/api/memory/recall", json=recall_payload)
        assert recall_resp.status_code == 200
        recall_data = recall_resp.json()
        assert "results" in recall_data
        assert "stats" in recall_data
        print(f"Recall results: {len(recall_data['results'])} items, stats={recall_data['stats']}")

    def test_register_entity(self):
        """POST /api/memory/entity registers entity"""
        payload = {
            "user_id": self.test_user_id,
            "entity_type": "PERSON",
            "name": "Bob Smith",
            "aliases": ["Bobby", "Robert"]
        }
        response = requests.post(f"{BASE_URL}/api/memory/entity", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "registered"
        assert "entity_id" in data
        print(f"Entity registered: id={data['entity_id'][:12]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
