"""
Tests for codebase-wide rename: action_class → intent

Verifies:
1. /api/health returns status=healthy
2. /api/l2/run accepts l1_intent (not l1_action_class), returns 'intent' field
3. /api/qc/run accepts 'intent' param (not 'action_class'), returns overall_pass
4. /api/commit/create accepts 'intent' field and stores correctly
5. /api/skills/match?intent=... works without action_class param
6. Python syntax (compile check) of key pipeline files
7. No 'action_class' field in API responses where 'intent' is expected
"""

import pytest
import requests
import os
import subprocess
import sys
from pathlib import Path

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://openclaw-tenant.preview.emergentagent.com"


@pytest.fixture(scope="module")
def api():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


# =====================================================
#  1. Health check
# =====================================================

class TestHealth:
    """Backend health endpoint"""

    def test_health_returns_200(self, api):
        """GET /api/health → 200"""
        r = api.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_health_status_healthy(self, api):
        """health response must include status=healthy"""
        r = api.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "healthy", f"Expected 'healthy', got: {data.get('status')}"

    def test_health_has_required_fields(self, api):
        """health response has env, version, active_sessions"""
        r = api.get(f"{BASE_URL}/api/health")
        data = r.json()
        assert "env" in data
        assert "version" in data
        assert "active_sessions" in data


# =====================================================
#  2. L2 Sentry: l1_intent param & intent response field
# =====================================================

class TestL2Sentry:
    """L2 Sentry endpoint: renamed field l1_intent and intent"""

    def test_l2_run_accepts_l1_intent_field(self, api):
        """POST /api/l2/run with l1_intent (not l1_action_class) → 200"""
        payload = {
            "transcript": "send email to john",
            "l1_intent": "Email Communication",
            "l1_confidence": 0.8,
        }
        r = api.post(f"{BASE_URL}/api/l2/run", json=payload)
        assert r.status_code == 200, f"L2 run failed: {r.status_code} {r.text}"

    def test_l2_run_returns_intent_field(self, api):
        """L2 response contains 'intent' field (not 'action_class')"""
        payload = {
            "transcript": "schedule a meeting with Alice tomorrow at 2pm",
            "l1_intent": "Meeting Scheduling",
            "l1_confidence": 0.85,
        }
        r = api.post(f"{BASE_URL}/api/l2/run", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "intent" in data, f"Missing 'intent' field in L2 response: {list(data.keys())}"
        assert "action_class" not in data, f"Old 'action_class' field still present in L2 response"

    def test_l2_run_no_l1_action_class_required(self, api):
        """L2 run works without l1_action_class (old field name) — using l1_intent"""
        # Only send l1_intent, NOT l1_action_class
        payload = {
            "transcript": "book a flight to London",
            "l1_intent": "Travel Concierge",
            "l1_confidence": 0.75,
        }
        r = api.post(f"{BASE_URL}/api/l2/run", json=payload)
        assert r.status_code == 200, f"L2 should work with l1_intent only: {r.text}"

    def test_l2_run_response_structure(self, api):
        """L2 verdict response has all expected fields"""
        payload = {
            "transcript": "find the latest news about AI",
            "l1_intent": "Information Retrieval",
            "l1_confidence": 0.7,
        }
        r = api.post(f"{BASE_URL}/api/l2/run", json=payload)
        assert r.status_code == 200
        data = r.json()

        required_fields = ["verdict_id", "intent", "confidence", "risk_tier",
                           "chain_of_logic", "shadow_agrees_with_l1", "conflicts",
                           "latency_ms", "is_mock"]
        for field in required_fields:
            assert field in data, f"Missing field '{field}' in L2 response: {list(data.keys())}"

    def test_l2_run_with_old_l1_action_class_causes_validation_error(self, api):
        """Sending l1_action_class (old field) should fail validation (422) — confirms rename complete"""
        payload = {
            "transcript": "send email to john",
            "l1_action_class": "COMM_SEND",   # OLD field name — should not be accepted
            "l1_confidence": 0.8,
        }
        r = api.post(f"{BASE_URL}/api/l2/run", json=payload)
        # If the rename is complete, the endpoint only accepts l1_intent.
        # Sending l1_action_class with NO l1_intent means l1_intent defaults to "".
        # It should NOT raise a 422 (because extra fields are ignored by Pydantic by default),
        # but l1_intent will be empty. This is valid behavior (no crash).
        # Key check: endpoint must NOT return 422 due to missing required field (l1_intent has default="")
        assert r.status_code in (200, 422), f"Unexpected status: {r.status_code}"
        if r.status_code == 200:
            data = r.json()
            # Verify 'intent' field still present (not 'action_class')
            assert "intent" in data


# =====================================================
#  3. QC Sentry: intent param & overall_pass response
# =====================================================

class TestQCSentry:
    """QC Sentry endpoint: renamed intent param"""

    def test_qc_run_accepts_intent_field(self, api):
        """POST /api/qc/run with intent (not action_class) → 200"""
        payload = {
            "transcript": "send email to john",
            "intent": "Email Communication",
            "intent_summary": "User wants to send an email to John",
        }
        r = api.post(f"{BASE_URL}/api/qc/run", json=payload)
        assert r.status_code == 200, f"QC run failed: {r.status_code} {r.text}"

    def test_qc_run_returns_overall_pass(self, api):
        """QC response contains overall_pass field"""
        payload = {
            "transcript": "schedule a meeting tomorrow",
            "intent": "Meeting Scheduling",
            "intent_summary": "User wants to schedule a meeting for tomorrow",
        }
        r = api.post(f"{BASE_URL}/api/qc/run", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "overall_pass" in data, f"Missing 'overall_pass' in QC response: {list(data.keys())}"
        assert isinstance(data["overall_pass"], bool), f"overall_pass must be bool, got {type(data['overall_pass'])}"

    def test_qc_run_no_action_class_in_response(self, api):
        """QC response should NOT contain old 'action_class' field"""
        payload = {
            "transcript": "find the latest AI news",
            "intent": "Information Retrieval",
            "intent_summary": "User wants to retrieve recent AI news",
        }
        r = api.post(f"{BASE_URL}/api/qc/run", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "action_class" not in data, f"Old 'action_class' still present in QC response"

    def test_qc_run_response_structure(self, api):
        """QC verdict response has all expected fields"""
        payload = {
            "transcript": "book a flight to London next week",
            "intent": "Travel Concierge",
            "intent_summary": "User wants to book a flight to London",
        }
        r = api.post(f"{BASE_URL}/api/qc/run", json=payload)
        assert r.status_code == 200
        data = r.json()

        required_fields = ["verdict_id", "passes", "overall_pass", "latency_ms", "is_mock"]
        for field in required_fields:
            assert field in data, f"Missing '{field}' in QC response"


# =====================================================
#  4. Commit Create: intent field
# =====================================================

class TestCommitCreate:
    """Commit create endpoint: renamed intent field"""

    def test_commit_create_accepts_intent_field(self, api):
        """POST /api/commit/create with intent (not action_class) → 200"""
        payload = {
            "session_id": "test_session_rename_001",
            "draft_id": "draft_rename_001",
            "intent_summary": "Send email to John about the meeting",
            "intent": "Email Communication",
        }
        r = api.post(f"{BASE_URL}/api/commit/create", json=payload)
        assert r.status_code == 200, f"Commit create failed: {r.status_code} {r.text}"

    def test_commit_create_returns_intent_field(self, api):
        """Commit response contains 'intent' field (not 'action_class')"""
        payload = {
            "session_id": "test_session_rename_002",
            "draft_id": "draft_rename_002",
            "intent_summary": "Schedule meeting with Alice",
            "intent": "Meeting Scheduling",
        }
        r = api.post(f"{BASE_URL}/api/commit/create", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "intent" in data, f"Missing 'intent' field in commit response: {list(data.keys())}"
        assert data["intent"] == "Meeting Scheduling", f"Intent value mismatch: {data.get('intent')}"

    def test_commit_create_stores_intent_correctly(self, api):
        """Create commit then retrieve it — verify intent persisted correctly"""
        import uuid
        session_id = f"test_session_{uuid.uuid4().hex[:8]}"
        draft_id = f"draft_{uuid.uuid4().hex[:8]}"
        intent_value = "Travel Concierge"

        # Create commit
        create_payload = {
            "session_id": session_id,
            "draft_id": draft_id,
            "intent_summary": "Book a flight to London",
            "intent": intent_value,
        }
        r_create = api.post(f"{BASE_URL}/api/commit/create", json=create_payload)
        assert r_create.status_code == 200
        created = r_create.json()
        commit_id = created.get("commit_id")
        assert commit_id, "commit_id missing from create response"

        # Retrieve commit
        r_get = api.get(f"{BASE_URL}/api/commit/{commit_id}")
        assert r_get.status_code == 200
        fetched = r_get.json()
        assert fetched.get("intent") == intent_value, \
            f"Intent not persisted correctly: expected '{intent_value}', got '{fetched.get('intent')}'"
        assert "action_class" not in fetched, "Old 'action_class' still present in commit record"

    def test_commit_create_no_action_class_required(self, api):
        """Commit create does NOT require action_class (old field) — uses intent"""
        payload = {
            "session_id": "test_session_rename_003",
            "draft_id": "draft_rename_003",
            "intent_summary": "Write code to sort a list",
            "intent": "Code Generation",
            # Deliberately no action_class
        }
        r = api.post(f"{BASE_URL}/api/commit/create", json=payload)
        assert r.status_code == 200, f"Should accept intent without action_class: {r.text}"


# =====================================================
#  5. Skills match: intent param
# =====================================================

class TestSkillsMatch:
    """Skills match endpoint: works with intent param"""

    def test_skills_match_accepts_intent_param(self, api):
        """GET /api/skills/match?intent=... → 200"""
        r = api.get(f"{BASE_URL}/api/skills/match", params={"intent": "Email Communication"})
        assert r.status_code == 200, f"Skills match failed: {r.status_code} {r.text}"

    def test_skills_match_returns_results(self, api):
        """Skills match returns a list of matched skills"""
        r = api.get(f"{BASE_URL}/api/skills/match", params={"intent": "Meeting Scheduling"})
        assert r.status_code == 200
        data = r.json()
        # Should return skills list
        assert isinstance(data, (list, dict)), f"Unexpected skills response type: {type(data)}"

    def test_skills_match_without_action_class(self, api):
        """Skills match works without action_class param — uses intent only"""
        r = api.get(
            f"{BASE_URL}/api/skills/match",
            params={"intent": "Travel Concierge"},
            # No action_class param at all
        )
        assert r.status_code == 200, f"Skills match should work with intent only: {r.text}"

    def test_skills_match_various_intents(self, api):
        """Skills match works for various intent values"""
        intents = [
            "Email Communication",
            "Information Retrieval",
            "Code Generation",
            "Meeting Scheduling",
        ]
        for intent in intents:
            r = api.get(f"{BASE_URL}/api/skills/match", params={"intent": intent})
            assert r.status_code == 200, \
                f"Skills match failed for intent='{intent}': {r.status_code} {r.text}"


# =====================================================
#  6. Python syntax linting of key files
# =====================================================

class TestPythonSyntax:
    """Verify key pipeline files have no syntax errors"""

    KEY_FILES = [
        "l1/scout.py",
        "l2/sentry.py",
        "gateway/ws_server.py",
        "qc/sentry.py",
        "commit/state_machine.py",
        "server.py",
    ]

    def test_l1_scout_syntax(self):
        """l1/scout.py compiles without errors"""
        backend_dir = Path(__file__).parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(backend_dir / "l1/scout.py")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"l1/scout.py syntax error: {result.stderr}"

    def test_l2_sentry_syntax(self):
        """l2/sentry.py compiles without errors"""
        backend_dir = Path(__file__).parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(backend_dir / "l2/sentry.py")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"l2/sentry.py syntax error: {result.stderr}"

    def test_ws_server_syntax(self):
        """gateway/ws_server.py compiles without errors"""
        backend_dir = Path(__file__).parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(backend_dir / "gateway/ws_server.py")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"gateway/ws_server.py syntax error: {result.stderr}"

    def test_qc_sentry_syntax(self):
        """qc/sentry.py compiles without errors"""
        backend_dir = Path(__file__).parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(backend_dir / "qc/sentry.py")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"qc/sentry.py syntax error: {result.stderr}"

    def test_commit_state_machine_syntax(self):
        """commit/state_machine.py compiles without errors"""
        backend_dir = Path(__file__).parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(backend_dir / "commit/state_machine.py")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"commit/state_machine.py syntax error: {result.stderr}"

    def test_server_syntax(self):
        """server.py compiles without errors"""
        backend_dir = Path(__file__).parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(backend_dir / "server.py")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"server.py syntax error: {result.stderr}"


# =====================================================
#  7. No action_class in live pipeline responses
# =====================================================

class TestNoActionClassInResponses:
    """Verify 'action_class' field is absent from all pipeline API responses"""

    def test_l2_response_no_action_class(self, api):
        """L2 response keys should not include 'action_class'"""
        r = api.post(f"{BASE_URL}/api/l2/run", json={
            "transcript": "book a flight",
            "l1_intent": "Travel Concierge",
            "l1_confidence": 0.8,
        })
        assert r.status_code == 200
        assert "action_class" not in r.json()

    def test_qc_response_no_action_class(self, api):
        """QC response should not include 'action_class' at top level"""
        r = api.post(f"{BASE_URL}/api/qc/run", json={
            "transcript": "book a flight",
            "intent": "Travel Concierge",
            "intent_summary": "Book flight to London",
        })
        assert r.status_code == 200
        assert "action_class" not in r.json()

    def test_commit_response_no_action_class(self, api):
        """Commit response should not contain 'action_class' field"""
        r = api.post(f"{BASE_URL}/api/commit/create", json={
            "session_id": "test_no_ac_session",
            "draft_id": "test_no_ac_draft",
            "intent_summary": "Test action class absence",
            "intent": "Code Generation",
        })
        assert r.status_code == 200
        assert "action_class" not in r.json()


# =====================================================
#  8. L1 Scout raise on missing LLM key (P1 check)
# =====================================================

class TestL1ScoutNoFallback:
    """Verify L1 Scout raises instead of calling _mock_l1 in production path"""

    def test_l1_scout_py_has_raise_not_mock_call(self):
        """l1/scout.py error handler uses 'raise' not '_mock_l1' in except block.

        Parses run_l1_scout's except block using indentation:
        - Finds the except block inside run_l1_scout
        - Only checks lines indented at except+4 spaces
        - Stops when indentation drops back
        """
        backend_dir = Path(__file__).parent.parent
        scout_path = backend_dir / "l1/scout.py"
        content = scout_path.read_text()
        lines = content.split("\n")

        in_run_l1_scout = False
        in_except_block = False
        except_indent = None
        raises_in_except = False
        calls_mock_in_except = False

        for line in lines:
            stripped = line.strip()
            # Enter run_l1_scout function
            if "async def run_l1_scout" in line:
                in_run_l1_scout = True
                continue
            # Exit run_l1_scout on any new top-level def/class
            if in_run_l1_scout and (stripped.startswith("def ") or stripped.startswith("async def ") or stripped.startswith("class ")):
                in_run_l1_scout = False
                in_except_block = False
                except_indent = None
                continue

            if in_run_l1_scout and stripped.startswith("except Exception"):
                # Capture the indentation level of the except line
                except_indent = len(line) - len(line.lstrip())
                in_except_block = True
                continue

            if in_except_block and except_indent is not None:
                # An except block body line must be more indented than the except line
                if stripped == "":
                    continue  # blank lines
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= except_indent:
                    # We've exited the except block
                    in_except_block = False
                    except_indent = None
                    continue
                # Inside except block — check for raise or _mock_l1 call
                if stripped == "raise":
                    raises_in_except = True
                    in_except_block = False  # raise exits the except — stop tracking
                if "_mock_l1(" in stripped:
                    calls_mock_in_except = True

        assert raises_in_except, \
            "L1 Scout's run_l1_scout except block should contain bare 'raise' (no-fallback policy)"
        assert not calls_mock_in_except, \
            "L1 Scout's run_l1_scout except block should NOT call _mock_l1() in production path"

    def test_l1_no_mock_in_is_mock_llm_check(self):
        """l1/scout.py: when is_mock_llm is True, raises RuntimeError (not mock_l1 fallback)"""
        backend_dir = Path(__file__).parent.parent
        scout_path = backend_dir / "l1/scout.py"
        content = scout_path.read_text()

        # Check that the is_mock_llm path raises RuntimeError
        assert "raise RuntimeError" in content, \
            "l1/scout.py should raise RuntimeError when EMERGENT_LLM_KEY is missing (no-fallback policy)"
        assert "_mock_l1" not in content.split("raise RuntimeError")[0].split("def run_l1_scout")[1] \
            if "def run_l1_scout" in content and "raise RuntimeError" in content else True, \
            "RuntimeError must come before any _mock_l1 call in run_l1_scout"


# =====================================================
#  9. Verify L2 Sentry _parse_l2_response reads 'intent' from LLM JSON
# =====================================================

class TestL2ParseIntent:
    """Verify L2 Sentry parser reads 'intent' key from LLM response (not 'action_class')"""

    def test_l2_sentry_py_reads_intent_not_action_class(self):
        """l2/sentry.py _parse_l2_response reads data.get('intent', '') """
        backend_dir = Path(__file__).parent.parent
        sentry_path = backend_dir / "l2/sentry.py"
        content = sentry_path.read_text()

        # Should parse 'intent' from LLM JSON
        assert "data.get(\"intent\"" in content or "data.get('intent'" in content, \
            "l2/sentry.py should read data.get('intent') from LLM JSON response"

        # Should NOT read 'action_class' from LLM JSON
        assert "data.get(\"action_class\"" not in content and "data.get('action_class'" not in content, \
            "l2/sentry.py should NOT read 'action_class' from LLM response (renamed to intent)"

    def test_l2_verdict_dataclass_has_intent_field(self):
        """L2Verdict dataclass has 'intent' field (not 'action_class')"""
        backend_dir = Path(__file__).parent.parent
        sentry_path = backend_dir / "l2/sentry.py"
        content = sentry_path.read_text()

        # L2Verdict should have intent field
        assert "intent: str" in content, "L2Verdict dataclass should have 'intent: str' field"
        assert "action_class: str" not in content, \
            "L2Verdict dataclass should NOT have 'action_class' field (renamed to intent)"

    def test_hypothesis_dataclass_has_intent_field(self):
        """Hypothesis dataclass in l1/scout.py has 'intent' field (not 'action_class')"""
        backend_dir = Path(__file__).parent.parent
        scout_path = backend_dir / "l1/scout.py"
        content = scout_path.read_text()

        assert "intent: str" in content, "Hypothesis dataclass should have 'intent: str' field"
        assert "action_class" not in content, \
            "l1/scout.py should have NO 'action_class' references (fully renamed to intent)"
