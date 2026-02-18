"""Test Suite for Setup Wizard Mock API Endpoints (/api/setup/*).

This tests the 8-step setup wizard flow:
- POST /api/setup/register - Account creation
- GET /api/setup/check-slug/{slug} - Workspace slug validation
- POST /api/setup/create-tenant - Tenant creation
- GET /api/setup/plans - Plan list
- POST /api/setup/checkout - Payment checkout
- POST /api/setup/activate/{tenant_id} - Tenant activation
- GET /api/setup/tenant/{tenant_id} - Tenant status
- POST /api/setup/generate-code - Pairing code generation
- PATCH /api/setup/preferences - User preferences update

All APIs are dev-only mocks (MOCKED).
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def unique_email():
    """Generate a unique email for registration tests."""
    return f"test_setup_{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture(scope="module")
def unique_slug():
    """Generate a unique slug for tenant tests."""
    return f"test-slug-{uuid.uuid4().hex[:8]}"


class TestRegisterEndpoint:
    """Tests for POST /api/setup/register - creates account and returns access_token + user."""

    def test_register_success(self, api_client, unique_email):
        """POST /api/setup/register creates account and returns access_token + user."""
        response = api_client.post(f"{BASE_URL}/api/setup/register", json={
            "email": unique_email,
            "password": "TestPassword123!",
            "name": "Test Setup User"
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify access_token is returned
        assert "access_token" in data, "Response must contain access_token"
        assert isinstance(data["access_token"], str), "access_token must be a string"
        assert len(data["access_token"]) > 0, "access_token must not be empty"
        assert data["access_token"].startswith("mock_token_"), "access_token should be mock format"
        
        # Verify user object is returned
        assert "user" in data, "Response must contain user object"
        user = data["user"]
        assert "user_id" in user, "User must have user_id"
        assert user["email"] == unique_email, f"Expected email {unique_email}, got {user['email']}"
        assert user["name"] == "Test Setup User", "User name must match"

    def test_register_duplicate_email_returns_409(self, api_client, unique_email):
        """POST /api/setup/register returns 409 for duplicate email."""
        # First registration was already done in test_register_success
        # Try to register again with the same email
        response = api_client.post(f"{BASE_URL}/api/setup/register", json={
            "email": unique_email,
            "password": "AnotherPassword456!",
            "name": "Duplicate User"
        })
        
        assert response.status_code == 409, f"Expected 409 for duplicate email, got {response.status_code}: {response.text}"
        
        # Verify error detail
        data = response.json()
        assert "detail" in data, "Error response must contain detail"
        assert "already registered" in data["detail"].lower(), f"Error detail should mention already registered: {data['detail']}"


class TestCheckSlugEndpoint:
    """Tests for GET /api/setup/check-slug/{slug} - validates workspace slug availability."""

    def test_check_slug_valid_unused_returns_available_true(self, api_client):
        """GET /api/setup/check-slug/{slug} returns available=true for valid unused slug."""
        # Use a unique slug that hasn't been used
        unique_slug = f"valid-slug-{uuid.uuid4().hex[:8]}"
        
        response = api_client.get(f"{BASE_URL}/api/setup/check-slug/{unique_slug}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "available" in data, "Response must contain available field"
        assert data["available"] is True, f"Valid unused slug should be available, got {data}"

    def test_check_slug_invalid_format_returns_available_false(self, api_client):
        """GET /api/setup/check-slug/{slug} returns available=false with reason for invalid format."""
        # Invalid slug with uppercase and spaces
        invalid_slug = "Invalid Slug With Spaces"
        
        response = api_client.get(f"{BASE_URL}/api/setup/check-slug/{invalid_slug}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "available" in data, "Response must contain available field"
        assert data["available"] is False, "Invalid format slug should not be available"
        assert "reason" in data, "Response should contain reason for unavailability"
        assert data["reason"] == "invalid_format", f"Reason should be 'invalid_format', got {data['reason']}"
        assert "suggestion" in data, "Response should contain suggestion for fixing"

    def test_check_slug_too_short_returns_available_false(self, api_client):
        """GET /api/setup/check-slug/{slug} returns available=false for slug too short."""
        # Slug less than 3 characters
        short_slug = "ab"
        
        response = api_client.get(f"{BASE_URL}/api/setup/check-slug/{short_slug}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "available" in data, "Response must contain available field"
        assert data["available"] is False, "Too short slug should not be available"
        assert "reason" in data, "Response should contain reason"
        assert data["reason"] == "invalid_format", f"Reason should be 'invalid_format', got {data['reason']}"

    def test_check_slug_taken_returns_suggestions(self, api_client, unique_slug):
        """GET /api/setup/check-slug/{slug} returns available=false with suggestions for taken slug."""
        # First create a tenant with this slug
        api_client.post(f"{BASE_URL}/api/setup/create-tenant", json={
            "workspace_slug": unique_slug
        })
        
        # Now check the same slug - it should be taken
        response = api_client.get(f"{BASE_URL}/api/setup/check-slug/{unique_slug}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "available" in data, "Response must contain available field"
        assert data["available"] is False, "Taken slug should not be available"
        assert "reason" in data, "Response should contain reason"
        assert data["reason"] == "taken", f"Reason should be 'taken', got {data['reason']}"
        assert "suggestions" in data, "Response should contain suggestions for taken slug"
        assert isinstance(data["suggestions"], list), "Suggestions should be a list"
        assert len(data["suggestions"]) > 0, "Should provide at least one suggestion"


class TestCreateTenantEndpoint:
    """Tests for POST /api/setup/create-tenant - creates tenant with workspace_slug."""

    def test_create_tenant_success(self, api_client):
        """POST /api/setup/create-tenant creates tenant with workspace_slug."""
        unique_slug = f"tenant-{uuid.uuid4().hex[:8]}"
        
        response = api_client.post(f"{BASE_URL}/api/setup/create-tenant", json={
            "workspace_slug": unique_slug
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify tenant_id is returned
        assert "tenant_id" in data, "Response must contain tenant_id"
        assert isinstance(data["tenant_id"], str), "tenant_id must be a string"
        assert data["tenant_id"].startswith("tenant_"), "tenant_id should have proper format"
        
        # Verify workspace_slug is echoed back
        assert "workspace_slug" in data, "Response must contain workspace_slug"
        assert data["workspace_slug"] == unique_slug, f"workspace_slug should match input"


class TestPlansEndpoint:
    """Tests for GET /api/setup/plans - returns available subscription plans."""

    def test_plans_returns_three_plans(self, api_client):
        """GET /api/setup/plans returns 3 plans (Starter/Pro/Enterprise) with features."""
        response = api_client.get(f"{BASE_URL}/api/setup/plans")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Plans response should be a list"
        assert len(data) == 3, f"Expected exactly 3 plans, got {len(data)}"
        
        # Verify plan structure and names
        plan_names = [p.get("name") for p in data]
        assert "Starter" in plan_names, "Must have Starter plan"
        assert "Pro" in plan_names, "Must have Pro plan"
        assert "Enterprise" in plan_names, "Must have Enterprise plan"
        
        # Verify each plan has required fields
        for plan in data:
            assert "plan_id" in plan, f"Plan must have plan_id: {plan}"
            assert "name" in plan, f"Plan must have name: {plan}"
            assert "price" in plan, f"Plan must have price: {plan}"
            assert "currency" in plan, f"Plan must have currency: {plan}"
            assert "features" in plan, f"Plan must have features: {plan}"
            assert isinstance(plan["features"], list), f"Features should be a list"
            assert len(plan["features"]) > 0, f"Plan should have at least one feature"


class TestCheckoutEndpoint:
    """Tests for POST /api/setup/checkout - initiates payment checkout."""

    def test_checkout_returns_url(self, api_client):
        """POST /api/setup/checkout returns checkout_url."""
        response = api_client.post(f"{BASE_URL}/api/setup/checkout", json={
            "plan_id": "pro",
            "tenant_id": "tenant_test123",
            "workspace_slug": "test-workspace"
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify checkout_url is returned
        assert "checkout_url" in data, "Response must contain checkout_url"
        assert isinstance(data["checkout_url"], str), "checkout_url must be a string"
        assert "checkout" in data["checkout_url"].lower(), "URL should be a checkout URL"
        assert "pro" in data["checkout_url"], "URL should contain plan_id"
        
        # Verify session_id is returned
        assert "session_id" in data, "Response should contain session_id"
        assert isinstance(data["session_id"], str), "session_id should be a string"


class TestActivateEndpoint:
    """Tests for POST /api/setup/activate/{tenant_id} - activates tenant."""

    def test_activate_sets_status_ready(self, api_client):
        """POST /api/setup/activate/{tenant_id} sets status to READY."""
        # First create a tenant
        create_response = api_client.post(f"{BASE_URL}/api/setup/create-tenant", json={
            "workspace_slug": f"activate-test-{uuid.uuid4().hex[:8]}"
        })
        assert create_response.status_code == 200
        tenant_id = create_response.json()["tenant_id"]
        
        # Activate the tenant
        response = api_client.post(f"{BASE_URL}/api/setup/activate/{tenant_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "status" in data, "Response must contain status"
        assert data["status"] == "READY", f"Status should be READY, got {data['status']}"
        assert "tenant_id" in data, "Response must contain tenant_id"
        assert data["tenant_id"] == tenant_id, "tenant_id should match"


class TestTenantStatusEndpoint:
    """Tests for GET /api/setup/tenant/{tenant_id} - returns tenant status."""

    def test_tenant_status_pending_payment(self, api_client):
        """GET /api/setup/tenant/{tenant_id} returns current status (PENDING_PAYMENT after create)."""
        # Create a tenant
        slug = f"status-test-{uuid.uuid4().hex[:8]}"
        create_response = api_client.post(f"{BASE_URL}/api/setup/create-tenant", json={
            "workspace_slug": slug
        })
        assert create_response.status_code == 200
        tenant_id = create_response.json()["tenant_id"]
        
        # Check status (should be PENDING_PAYMENT)
        response = api_client.get(f"{BASE_URL}/api/setup/tenant/{tenant_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "status" in data, "Response must contain status"
        assert data["status"] == "PENDING_PAYMENT", f"Status should be PENDING_PAYMENT, got {data['status']}"
        assert "tenant_id" in data, "Response must contain tenant_id"
        assert "workspace_slug" in data, "Response must contain workspace_slug"
        assert data["workspace_slug"] == slug, "workspace_slug should match"

    def test_tenant_status_ready_after_activate(self, api_client):
        """GET /api/setup/tenant/{tenant_id} returns READY after activation."""
        # Create and activate a tenant
        create_response = api_client.post(f"{BASE_URL}/api/setup/create-tenant", json={
            "workspace_slug": f"ready-test-{uuid.uuid4().hex[:8]}"
        })
        assert create_response.status_code == 200
        tenant_id = create_response.json()["tenant_id"]
        
        # Activate
        activate_response = api_client.post(f"{BASE_URL}/api/setup/activate/{tenant_id}")
        assert activate_response.status_code == 200
        
        # Check status (should be READY now)
        response = api_client.get(f"{BASE_URL}/api/setup/tenant/{tenant_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["status"] == "READY", f"Status should be READY after activation, got {data['status']}"

    def test_tenant_status_not_found(self, api_client):
        """GET /api/setup/tenant/{tenant_id} returns NOT_FOUND for unknown tenant."""
        response = api_client.get(f"{BASE_URL}/api/setup/tenant/tenant_unknown_12345")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["status"] == "NOT_FOUND", f"Status should be NOT_FOUND, got {data['status']}"


class TestGenerateCodeEndpoint:
    """Tests for POST /api/setup/generate-code - generates pairing code."""

    def test_generate_code_returns_6_digit_code(self, api_client):
        """POST /api/setup/generate-code returns 6-digit code with expiry."""
        response = api_client.post(f"{BASE_URL}/api/setup/generate-code")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify code is returned
        assert "code" in data, "Response must contain code"
        assert isinstance(data["code"], str), "code must be a string"
        assert len(data["code"]) == 6, f"code must be exactly 6 digits, got {len(data['code'])}"
        assert data["code"].isdigit(), f"code must be all digits, got {data['code']}"
        
        # Verify expiry is returned
        assert "expires_in_seconds" in data, "Response must contain expires_in_seconds"
        assert isinstance(data["expires_in_seconds"], int), "expires_in_seconds must be an integer"
        assert data["expires_in_seconds"] > 0, "expires_in_seconds must be positive"


class TestPreferencesEndpoint:
    """Tests for PATCH /api/setup/preferences - updates user preferences."""

    def test_preferences_update_success(self, api_client):
        """PATCH /api/setup/preferences updates phone/timezone/notifications."""
        response = api_client.patch(f"{BASE_URL}/api/setup/preferences", json={
            "user_id": "user_test123",
            "phone_number": "+1234567890",
            "timezone": "America/New_York",
            "notifications_enabled": True
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response must contain message"
        assert "updated" in data["message"].lower() or "preferences" in data["message"].lower(), f"Message should confirm update: {data['message']}"

    def test_preferences_update_partial(self, api_client):
        """PATCH /api/setup/preferences allows partial updates."""
        # Only update timezone
        response = api_client.patch(f"{BASE_URL}/api/setup/preferences", json={
            "timezone": "Europe/London",
            "notifications_enabled": False
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response must contain message"


class TestHealthEndpoint:
    """Quick health check to verify backend is running."""

    def test_health_check(self, api_client):
        """GET /api/health returns healthy status."""
        response = api_client.get(f"{BASE_URL}/api/health")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "status" in data, "Response must contain status"
        assert data["status"] == "healthy", f"Status should be healthy, got {data['status']}"
