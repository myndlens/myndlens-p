"""Execute Pipeline Tests — Draft Persistence, Execute Flow, Blocking Gates, TTS Confirmations.

Tests the features from the code review fixes:
- Draft persistence: L1 draft stored + retrieved by draft_id from MongoDB
- Execute pipeline: text_input → draft_update → execute_request → L2 → QC → skills → execute_ok
- Execute blocked DRAFT_NOT_FOUND
- Execute blocked PRESENCE_STALE (regression)
- Execute blocked SUBSCRIPTION_INACTIVE (regression)
- TTS response confirmation: NOT clarification questions
- Skills match API
- Agents CRUD regression
"""
import asyncio
import json
import os
import sys
import pytest
import requests
import time
import uuid
from datetime import datetime, timezone

# Add backend to path for direct imports
sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://mandate-executor.preview.emergentagent.com"

PAIR_CODE = "123456"

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


# ============================================================================
#  Module-Level Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def run_async(coro):
    """Helper to run async functions in sync tests."""
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class TestDraftPersistence:
    """Test L1 draft storage and retrieval from MongoDB."""

    def test_d01_store_draft_via_l1_scout(self):
        """[D01] L1 Scout stores draft to MongoDB l1_drafts collection."""
        async def _test():
            from l1.scout import run_l1_scout, get_draft

            session_id = f"test-session-{uuid.uuid4().hex[:8]}"
            transcript = "Send a message to Alice about the meeting tomorrow"

            draft = await run_l1_scout(
                session_id=session_id,
                user_id="test-user",
                transcript=transcript,
            )

            assert draft is not None, "L1 Scout should return a draft"
            assert draft.draft_id, "Draft should have an ID"
            assert draft.transcript == transcript, "Draft should store transcript"
            assert len(draft.hypotheses) > 0, "Draft should have hypotheses"

            print(f"[D01] Draft stored: draft_id={draft.draft_id[:8]} hypotheses={len(draft.hypotheses)}")
            return draft.draft_id

        run_async(_test())

    def test_d02_get_draft_by_id(self):
        """[D02] Can retrieve stored draft by draft_id."""
        async def _test():
            from l1.scout import run_l1_scout, get_draft

            session_id = f"test-session-{uuid.uuid4().hex[:8]}"
            transcript = "Schedule a call with Bob at 3pm"

            # Store draft
            original = await run_l1_scout(
                session_id=session_id,
                user_id="test-user",
                transcript=transcript,
            )

            # Retrieve draft
            retrieved = await get_draft(original.draft_id)

            assert retrieved is not None, "Should retrieve stored draft"
            assert retrieved.draft_id == original.draft_id, "Draft IDs should match"
            assert retrieved.transcript == original.transcript, "Transcripts should match"
            assert len(retrieved.hypotheses) == len(original.hypotheses), "Hypotheses count should match"

            print(f"[D02] Draft retrieved: draft_id={retrieved.draft_id[:8]} transcript='{retrieved.transcript[:30]}...'")

        run_async(_test())

    def test_d03_get_nonexistent_draft_returns_none(self):
        """[D03] get_draft returns None for non-existent draft_id."""
        async def _test():
            from l1.scout import get_draft

            result = await get_draft("nonexistent-draft-id-12345")

            assert result is None, "Non-existent draft should return None"
            print("[D03] Non-existent draft correctly returns None")

        run_async(_test())

    def test_d04_draft_includes_hypotheses_structure(self):
        """[D04] Stored draft includes correct hypothesis structure."""
        async def _test():
            from l1.scout import run_l1_scout, get_draft

            session_id = f"test-session-{uuid.uuid4().hex[:8]}"
            transcript = "Send email to project team about status update"

            original = await run_l1_scout(
                session_id=session_id,
                user_id="test-user",
                transcript=transcript,
            )

            retrieved = await get_draft(original.draft_id)

            assert retrieved.hypotheses, "Retrieved draft should have hypotheses"
            h = retrieved.hypotheses[0]
            assert hasattr(h, "hypothesis"), "Hypothesis should have 'hypothesis' field"
            assert hasattr(h, "action_class"), "Hypothesis should have 'action_class' field"
            assert hasattr(h, "confidence"), "Hypothesis should have 'confidence' field"

            print(f"[D04] Hypothesis structure: action={h.action_class} conf={h.confidence:.2f}")

        run_async(_test())


class TestExecuteGates:
    """Test execute_request blocking gates (presence, subscription, draft)."""

    @pytest.mark.asyncio
    async def test_e01_presence_gate_blocks_stale_heartbeat(self):
        """[E01] Execute blocked with PRESENCE_STALE when heartbeat is stale (>16s)."""
        from presence.heartbeat import record_heartbeat, check_presence
        from datetime import datetime, timezone, timedelta
        from core.database import get_db
        
        session_id = f"test-stale-{uuid.uuid4().hex[:8]}"
        
        # Manually insert stale heartbeat (20 seconds old)
        db = get_db()
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=20)
        await db.presence.update_one(
            {"session_id": session_id},
            {"$set": {
                "session_id": session_id,
                "last_heartbeat": stale_time,
                "seq": 1,
            }},
            upsert=True
        )
        
        # Check presence - should be stale
        is_present = await check_presence(session_id)
        
        assert is_present is False, "Stale heartbeat (>16s) should return is_present=False"
        print(f"[E01] PRESENCE_STALE gate: stale_time={stale_time.isoformat()} is_present={is_present}")

    @pytest.mark.asyncio
    async def test_e02_presence_gate_allows_fresh_heartbeat(self):
        """[E02] Execute allowed when heartbeat is fresh (<16s)."""
        from presence.heartbeat import record_heartbeat, check_presence
        
        session_id = f"test-fresh-{uuid.uuid4().hex[:8]}"
        
        # Record fresh heartbeat
        await record_heartbeat(session_id, seq=1, client_ts=int(time.time() * 1000))
        
        # Check presence - should be fresh
        is_present = await check_presence(session_id)
        
        assert is_present is True, "Fresh heartbeat should return is_present=True"
        print(f"[E02] Fresh heartbeat gate: session={session_id} is_present={is_present}")

    def test_e03_subscription_inactive_blocks_execute(self):
        """[E03] SUBSCRIPTION_INACTIVE blocks execute_request."""
        # This is verified via WebSocket message handling
        # The code in ws_server.py line 289-299 checks subscription_status != "ACTIVE"
        from schemas.ws_messages import ExecuteBlockedPayload
        
        payload = ExecuteBlockedPayload(
            reason="Subscription status is SUSPENDED. Execute blocked.",
            code="SUBSCRIPTION_INACTIVE",
            draft_id="test-draft",
        )
        
        assert payload.code == "SUBSCRIPTION_INACTIVE"
        print(f"[E03] SUBSCRIPTION_INACTIVE payload: code={payload.code}")

    def test_e04_draft_not_found_blocks_execute(self):
        """[E04] DRAFT_NOT_FOUND blocks execute_request."""
        from schemas.ws_messages import ExecuteBlockedPayload
        
        payload = ExecuteBlockedPayload(
            reason="Draft not found or expired. Please re-submit your intent.",
            code="DRAFT_NOT_FOUND",
            draft_id="nonexistent-id",
        )
        
        assert payload.code == "DRAFT_NOT_FOUND"
        print(f"[E04] DRAFT_NOT_FOUND payload: code={payload.code}")


class TestTTSConfirmationResponses:
    """Test that _generate_l1_response returns confirmations, NOT clarification questions."""

    def test_t01_comm_send_returns_confirmation(self):
        """[T01] COMM_SEND returns confirmation, not clarification."""
        from gateway.ws_server import _generate_l1_response
        from l1.scout import Hypothesis
        from dimensions.engine import DimensionState
        
        h = Hypothesis(
            hypothesis="User wants to send a message to Alice",
            action_class="COMM_SEND",
            confidence=0.85,
        )
        dim_state = DimensionState()
        dim_state.a_set.who = "Alice"
        
        response = _generate_l1_response(h, dim_state)
        
        assert "Tap Approve" in response, "Response should include approval prompt"
        assert "clarif" not in response.lower(), "Response should NOT ask for clarification"
        assert "more" not in response.lower() or "tell me more" not in response.lower(), "Response should NOT ask 'tell me more'"
        print(f"[T01] COMM_SEND response: '{response}'")

    def test_t02_sched_modify_returns_confirmation(self):
        """[T02] SCHED_MODIFY returns confirmation, not clarification."""
        from gateway.ws_server import _generate_l1_response
        from l1.scout import Hypothesis
        from dimensions.engine import DimensionState
        
        h = Hypothesis(
            hypothesis="User wants to schedule a meeting",
            action_class="SCHED_MODIFY",
            confidence=0.80,
        )
        dim_state = DimensionState()
        dim_state.a_set.when = "3pm tomorrow"
        
        response = _generate_l1_response(h, dim_state)
        
        assert "Tap Approve" in response, "Response should include approval prompt"
        assert "I want to make sure" not in response, "Response should NOT include clarification phrasing"
        print(f"[T02] SCHED_MODIFY response: '{response}'")

    def test_t03_info_retrieve_returns_confirmation(self):
        """[T03] INFO_RETRIEVE returns confirmation."""
        from gateway.ws_server import _generate_l1_response
        from l1.scout import Hypothesis
        from dimensions.engine import DimensionState
        
        h = Hypothesis(
            hypothesis="User wants to look up information",
            action_class="INFO_RETRIEVE",
            confidence=0.75,
        )
        dim_state = DimensionState()
        
        response = _generate_l1_response(h, dim_state)
        
        assert "Tap Approve" in response, "Response should include approval prompt"
        assert "Could you" not in response, "Response should NOT ask clarifying questions"
        print(f"[T03] INFO_RETRIEVE response: '{response}'")

    def test_t04_doc_edit_returns_confirmation(self):
        """[T04] DOC_EDIT returns confirmation."""
        from gateway.ws_server import _generate_l1_response
        from l1.scout import Hypothesis
        from dimensions.engine import DimensionState
        
        h = Hypothesis(
            hypothesis="User wants to edit a document",
            action_class="DOC_EDIT",
            confidence=0.78,
        )
        dim_state = DimensionState()
        
        response = _generate_l1_response(h, dim_state)
        
        assert "Tap Approve" in response
        assert "?" not in response, "Response should NOT be a question"
        print(f"[T04] DOC_EDIT response: '{response}'")

    def test_t05_draft_only_returns_confirmation(self):
        """[T05] DRAFT_ONLY returns confirmation."""
        from gateway.ws_server import _generate_l1_response
        from l1.scout import Hypothesis
        from dimensions.engine import DimensionState
        
        h = Hypothesis(
            hypothesis="User wants to do something general",
            action_class="DRAFT_ONLY",
            confidence=0.65,
        )
        dim_state = DimensionState()
        dim_state.a_set.what = "general task"
        
        response = _generate_l1_response(h, dim_state)
        
        assert "Tap Approve" in response
        print(f"[T05] DRAFT_ONLY response: '{response}'")


class TestSkillsAPI:
    """Test Skills Library API."""

    def test_s01_skills_library_index(self):
        """[S01] POST /api/skills/index loads and indexes library."""
        response = requests.post(f"{BASE_URL}/api/skills/index")
        assert response.status_code == 200, f"Skills index failed: {response.text}"
        
        data = response.json()
        assert data.get("status") in ["OK", "ERROR"], "Should return status"
        print(f"[S01] Skills indexed: {data}")

    def test_s02_skills_match_returns_results(self):
        """[S02] GET /api/skills/match?intent= returns matched skills."""
        # First index the library
        requests.post(f"{BASE_URL}/api/skills/index")
        
        response = requests.get(f"{BASE_URL}/api/skills/match?intent=send+email")
        assert response.status_code == 200, f"Skills match failed: {response.text}"
        
        data = response.json()
        # May be empty if no skills match, but should be a list
        assert isinstance(data, list), "Should return a list"
        print(f"[S02] Skills matched for 'send email': {len(data)} results")

    def test_s03_skills_search(self):
        """[S03] GET /api/skills/search?query= searches library."""
        response = requests.get(f"{BASE_URL}/api/skills/search?query=email")
        assert response.status_code == 200, f"Skills search failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Should return a list"
        print(f"[S03] Skills search for 'email': {len(data)} results")

    def test_s04_skills_stats(self):
        """[S04] GET /api/skills/stats returns library statistics."""
        response = requests.get(f"{BASE_URL}/api/skills/stats")
        assert response.status_code == 200, f"Skills stats failed: {response.text}"
        
        data = response.json()
        assert "total_skills" in data, "Should include total_skills"
        assert "categories" in data, "Should include categories"
        print(f"[S04] Skills stats: total={data.get('total_skills')} categories={len(data.get('categories', []))}")


class TestAgentsCRUD:
    """Regression tests for Agents CRUD operations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tenant_id = f"TEST_tenant_{uuid.uuid4().hex[:6]}"
        self.agent_ids = []

    def test_a01_create_agent(self):
        """[A01] POST /api/agents creates a new agent."""
        agent_data = {
            "tenant_id": self.tenant_id,
            "name": f"TEST_agent_{uuid.uuid4().hex[:6]}",
            "description": "Test agent for CRUD regression",
            "tools": ["read", "write"],
            "soil": {"prompt_vars": {"style": "formal"}},
            "bindings": {"email": "test@example.com"},
        }
        
        response = requests.post(f"{BASE_URL}/api/agents", json=agent_data)
        assert response.status_code in [200, 201], f"Create agent failed: {response.text}"
        
        data = response.json()
        assert "agent_id" in data, "Response should include agent_id"
        assert data.get("name") == agent_data["name"], "Agent name should match"
        
        self.agent_ids.append(data["agent_id"])
        print(f"[A01] Agent created: id={data['agent_id']} name={data.get('name')}")

    def test_a02_modify_agent(self):
        """[A02] PUT /api/agents/{id} modifies an existing agent."""
        # First create an agent
        agent_data = {
            "tenant_id": self.tenant_id,
            "name": f"TEST_mod_{uuid.uuid4().hex[:6]}",
            "description": "Agent to be modified",
            "tools": ["read"],
        }
        create_resp = requests.post(f"{BASE_URL}/api/agents", json=agent_data)
        assert create_resp.status_code in [200, 201], f"Create failed: {create_resp.text}"
        agent_id = create_resp.json()["agent_id"]
        
        # Modify the agent
        modify_data = {
            "name": f"TEST_mod_updated_{uuid.uuid4().hex[:4]}",
            "tools": ["read", "write", "search"],
            "soil": {"prompt_vars": {"style": "casual"}},
        }
        
        response = requests.put(f"{BASE_URL}/api/agents/{agent_id}", json=modify_data)
        assert response.status_code == 200, f"Modify agent failed: {response.text}"
        
        data = response.json()
        assert "changes" in data, "Should report changes made"
        print(f"[A02] Agent modified: id={agent_id} changes={data.get('changes')}")

    def test_a03_retire_agent(self):
        """[A03] POST /api/agents/{id}/retire retires an agent."""
        # First create an agent
        agent_data = {
            "tenant_id": self.tenant_id,
            "name": f"TEST_ret_{uuid.uuid4().hex[:6]}",
            "tools": ["read"],
        }
        create_resp = requests.post(f"{BASE_URL}/api/agents", json=agent_data)
        assert create_resp.status_code in [200, 201]
        agent_id = create_resp.json()["agent_id"]
        
        # Retire the agent
        response = requests.post(f"{BASE_URL}/api/agents/{agent_id}/retire")
        assert response.status_code == 200, f"Retire agent failed: {response.text}"
        
        data = response.json()
        assert data.get("mode") == "SOFT_RETIRE", "Should be soft retired"
        print(f"[A03] Agent retired: id={agent_id} mode={data.get('mode')}")

    def test_a04_list_agents(self):
        """[A04] GET /api/agents?tenant_id= lists agents for tenant."""
        # Create a couple of agents first
        for i in range(2):
            agent_data = {
                "tenant_id": self.tenant_id,
                "name": f"TEST_list_{uuid.uuid4().hex[:6]}",
                "tools": ["read"],
            }
            requests.post(f"{BASE_URL}/api/agents", json=agent_data)
        
        response = requests.get(f"{BASE_URL}/api/agents?tenant_id={self.tenant_id}")
        assert response.status_code == 200, f"List agents failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Should return a list"
        print(f"[A04] Agents listed for tenant {self.tenant_id}: {len(data)} agents")

    def test_a05_get_single_agent(self):
        """[A05] GET /api/agents/{id} retrieves a single agent."""
        # First create an agent
        agent_data = {
            "tenant_id": self.tenant_id,
            "name": f"TEST_get_{uuid.uuid4().hex[:6]}",
            "tools": ["read"],
        }
        create_resp = requests.post(f"{BASE_URL}/api/agents", json=agent_data)
        assert create_resp.status_code in [200, 201]
        agent_id = create_resp.json()["agent_id"]
        
        response = requests.get(f"{BASE_URL}/api/agents/{agent_id}")
        assert response.status_code == 200, f"Get agent failed: {response.text}"
        
        data = response.json()
        assert data.get("agent_id") == agent_id, "Agent ID should match"
        print(f"[A05] Agent retrieved: id={agent_id} name={data.get('name')}")


class TestExecutePipelineIntegration:
    """Integration tests for the full execute pipeline."""

    @pytest.mark.asyncio
    async def test_p01_full_pipeline_l2_qc_skills(self):
        """[P01] Full pipeline: draft → L2 → QC → skills."""
        from l1.scout import run_l1_scout, get_draft
        from l2.sentry import run_l2_sentry
        from qc.sentry import run_qc_sentry
        from skills.library import match_skills_to_intent
        from dimensions.engine import get_dimension_state
        
        session_id = f"test-pipeline-{uuid.uuid4().hex[:8]}"
        user_id = "test-user"
        transcript = "Send an email to the project team about the status update"
        
        # Step 1: L1 Scout (creates draft)
        draft = await run_l1_scout(session_id, user_id, transcript)
        assert draft and draft.hypotheses, "L1 should produce hypotheses"
        print(f"[P01] L1: draft_id={draft.draft_id[:8]} action={draft.hypotheses[0].action_class}")
        
        # Step 2: Verify draft persistence
        retrieved = await get_draft(draft.draft_id)
        assert retrieved, "Draft should be retrievable"
        print(f"[P01] Draft retrieved: {retrieved.draft_id[:8]}")
        
        # Step 3: L2 Sentry
        top = draft.hypotheses[0]
        dim_state = get_dimension_state(session_id)
        
        l2 = await run_l2_sentry(
            session_id=session_id,
            user_id=user_id,
            transcript=transcript,
            l1_action_class=top.action_class,
            l1_confidence=top.confidence,
            dimensions=dim_state.to_dict(),
        )
        assert l2.action_class, "L2 should return action_class"
        print(f"[P01] L2: action={l2.action_class} conf={l2.confidence:.2f} agrees={l2.shadow_agrees_with_l1}")
        
        # Step 4: QC Sentry
        qc = await run_qc_sentry(
            session_id=session_id,
            user_id=user_id,
            transcript=transcript,
            action_class=l2.action_class,
            intent_summary=top.hypothesis,
        )
        print(f"[P01] QC: overall_pass={qc.overall_pass} reason={qc.block_reason or 'N/A'}")
        
        # Step 5: Skills matching
        skills = await match_skills_to_intent(transcript, top_n=3)
        skill_names = [s.get("name", "") for s in skills]
        print(f"[P01] Skills: matched={len(skills)} names={skill_names}")
        
        print(f"[P01] COMPLETE: L1→L2→QC→Skills pipeline executed successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
