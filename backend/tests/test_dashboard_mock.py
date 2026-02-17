"""Test Dashboard Mock APIs - ObeGee Dashboard Integration (dev only)

Tests the mock ObeGee dashboard API endpoints:
- GET /api/dashboard/workspace/config - workspace config (name, model, status, subscription, tools, runtime)
- PATCH /api/dashboard/workspace/tools - update enabled tools
- PATCH /api/dashboard/workspace/model - update provider and API key  
- GET /api/dashboard/workspace/agents - agent list (id, name, model, status, skills, tools)
- GET /api/dashboard/workspace/usage - usage stats (messages, tokens, tool_calls) with limits
- GET /api/dashboard/dashboard-url - webview URL

All endpoints are dev-only mocks for ObeGee dashboard integration testing.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestDashboardWorkspaceConfig:
    """Tests for GET /api/dashboard/workspace/config"""
    
    def test_workspace_config_returns_200(self):
        """Workspace config endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/workspace/config")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/dashboard/workspace/config returns 200")
    
    def test_workspace_config_has_workspace_info(self):
        """Workspace config should contain workspace name, model, status"""
        response = requests.get(f"{BASE_URL}/api/dashboard/workspace/config")
        data = response.json()
        
        assert "workspace" in data, "Response should have 'workspace' field"
        workspace = data["workspace"]
        
        assert "name" in workspace, "Workspace should have 'name'"
        assert "model" in workspace, "Workspace should have 'model'"
        assert "status" in workspace, "Workspace should have 'status'"
        
        print(f"PASS: Workspace config has name='{workspace['name']}', model='{workspace['model']}', status='{workspace['status']}'")
    
    def test_workspace_config_has_subscription(self):
        """Workspace config should contain subscription info"""
        response = requests.get(f"{BASE_URL}/api/dashboard/workspace/config")
        data = response.json()
        
        assert "subscription" in data, "Response should have 'subscription' field"
        subscription = data["subscription"]
        
        assert "plan_id" in subscription, "Subscription should have 'plan_id'"
        assert "status" in subscription, "Subscription should have 'status'"
        
        print(f"PASS: Subscription has plan_id='{subscription['plan_id']}', status='{subscription['status']}'")
    
    def test_workspace_config_has_tools(self):
        """Workspace config should contain tools list"""
        response = requests.get(f"{BASE_URL}/api/dashboard/workspace/config")
        data = response.json()
        
        assert "tools" in data, "Response should have 'tools' field"
        tools = data["tools"]
        
        assert "enabled" in tools, "Tools should have 'enabled' list"
        assert isinstance(tools["enabled"], list), "Enabled tools should be a list"
        assert len(tools["enabled"]) > 0, "Should have at least one enabled tool"
        
        print(f"PASS: Tools enabled: {tools['enabled']}")
    
    def test_workspace_config_has_runtime(self):
        """Workspace config should contain runtime info"""
        response = requests.get(f"{BASE_URL}/api/dashboard/workspace/config")
        data = response.json()
        
        assert "runtime" in data, "Response should have 'runtime' field"
        runtime = data["runtime"]
        
        assert "status" in runtime, "Runtime should have 'status'"
        
        print(f"PASS: Runtime status='{runtime['status']}'")


class TestDashboardUpdateTools:
    """Tests for PATCH /api/dashboard/workspace/tools"""
    
    def test_update_tools_returns_200(self):
        """Update tools endpoint should return 200"""
        response = requests.patch(
            f"{BASE_URL}/api/dashboard/workspace/tools",
            json={"enabled_tools": ["web-browser", "code-runner"]}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: PATCH /api/dashboard/workspace/tools returns 200")
    
    def test_update_tools_returns_updated_list(self):
        """Update tools should echo back the updated list"""
        tools_to_enable = ["web-browser", "file-system", "data-analysis"]
        response = requests.patch(
            f"{BASE_URL}/api/dashboard/workspace/tools",
            json={"enabled_tools": tools_to_enable}
        )
        data = response.json()
        
        assert "enabled_tools" in data, "Response should have 'enabled_tools'"
        assert data["enabled_tools"] == tools_to_enable, f"Expected {tools_to_enable}, got {data['enabled_tools']}"
        
        print(f"PASS: Updated tools returned: {data['enabled_tools']}")


class TestDashboardUpdateModel:
    """Tests for PATCH /api/dashboard/workspace/model"""
    
    def test_update_model_returns_200(self):
        """Update model endpoint should return 200"""
        response = requests.patch(
            f"{BASE_URL}/api/dashboard/workspace/model",
            json={"provider": "openai", "api_key": "sk-test-key"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: PATCH /api/dashboard/workspace/model returns 200")
    
    def test_update_model_returns_provider(self):
        """Update model should return the provider"""
        response = requests.patch(
            f"{BASE_URL}/api/dashboard/workspace/model",
            json={"provider": "google", "api_key": "aaa-test-key"}
        )
        data = response.json()
        
        assert "provider" in data, "Response should have 'provider'"
        assert data["provider"] == "google", f"Expected 'google', got '{data['provider']}'"
        
        print(f"PASS: Model provider updated to: {data['provider']}")


class TestDashboardAgents:
    """Tests for GET /api/dashboard/workspace/agents"""
    
    def test_agents_returns_200(self):
        """Agents endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/workspace/agents")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/dashboard/workspace/agents returns 200")
    
    def test_agents_returns_list(self):
        """Agents endpoint should return agents list"""
        response = requests.get(f"{BASE_URL}/api/dashboard/workspace/agents")
        data = response.json()
        
        assert "agents" in data, "Response should have 'agents' field"
        assert isinstance(data["agents"], list), "Agents should be a list"
        
        print(f"PASS: Found {len(data['agents'])} agents")
    
    def test_agents_have_required_fields(self):
        """Each agent should have id, name, model, status, skills, tools"""
        response = requests.get(f"{BASE_URL}/api/dashboard/workspace/agents")
        data = response.json()
        agents = data["agents"]
        
        for agent in agents:
            assert "id" in agent, f"Agent should have 'id': {agent}"
            assert "name" in agent, f"Agent should have 'name': {agent}"
            assert "model" in agent, f"Agent should have 'model': {agent}"
            assert "status" in agent, f"Agent should have 'status': {agent}"
            assert "skills" in agent, f"Agent should have 'skills': {agent}"
            assert "tools" in agent, f"Agent should have 'tools': {agent}"
            
            print(f"PASS: Agent '{agent['name']}' has all required fields (id, name, model, status, skills, tools)")


class TestDashboardUsage:
    """Tests for GET /api/dashboard/workspace/usage"""
    
    def test_usage_returns_200(self):
        """Usage endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/workspace/usage")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/dashboard/workspace/usage returns 200")
    
    def test_usage_has_today_stats(self):
        """Usage should have today's usage (messages, tokens, tool_calls)"""
        response = requests.get(f"{BASE_URL}/api/dashboard/workspace/usage")
        data = response.json()
        
        assert "today" in data, "Response should have 'today' field"
        today = data["today"]
        
        assert "messages" in today, "Today should have 'messages'"
        assert "tokens" in today, "Today should have 'tokens'"
        assert "tool_calls" in today, "Today should have 'tool_calls'"
        
        print(f"PASS: Today's usage - messages={today['messages']}, tokens={today['tokens']}, tool_calls={today['tool_calls']}")
    
    def test_usage_has_limits(self):
        """Usage should have limits for messages and tokens"""
        response = requests.get(f"{BASE_URL}/api/dashboard/workspace/usage")
        data = response.json()
        
        assert "limits" in data, "Response should have 'limits' field"
        limits = data["limits"]
        
        assert "messages" in limits, "Limits should have 'messages'"
        assert "tokens" in limits, "Limits should have 'tokens'"
        
        print(f"PASS: Limits - messages={limits['messages']}, tokens={limits['tokens']}")
    
    def test_usage_has_subscription(self):
        """Usage should have subscription info"""
        response = requests.get(f"{BASE_URL}/api/dashboard/workspace/usage")
        data = response.json()
        
        assert "subscription" in data, "Response should have 'subscription' field"
        subscription = data["subscription"]
        
        assert "plan_name" in subscription, "Subscription should have 'plan_name'"
        assert "status" in subscription, "Subscription should have 'status'"
        
        print(f"PASS: Subscription - plan={subscription['plan_name']}, status={subscription['status']}")


class TestDashboardUrl:
    """Tests for GET /api/dashboard/dashboard-url"""
    
    def test_dashboard_url_returns_200(self):
        """Dashboard URL endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/dashboard/dashboard-url")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/dashboard/dashboard-url returns 200")
    
    def test_dashboard_url_has_webview_url(self):
        """Dashboard URL should return webview URL"""
        response = requests.get(f"{BASE_URL}/api/dashboard/dashboard-url")
        data = response.json()
        
        assert "webview_url" in data, "Response should have 'webview_url' field"
        assert data["webview_url"].startswith("http"), f"URL should start with http: {data['webview_url']}"
        
        print(f"PASS: Dashboard webview URL: {data['webview_url']}")
    
    def test_dashboard_url_has_expiry(self):
        """Dashboard URL should have expiry time"""
        response = requests.get(f"{BASE_URL}/api/dashboard/dashboard-url")
        data = response.json()
        
        assert "expires_in" in data, "Response should have 'expires_in' field"
        assert isinstance(data["expires_in"], int), "expires_in should be integer"
        assert data["expires_in"] > 0, "expires_in should be positive"
        
        print(f"PASS: URL expires in {data['expires_in']} seconds")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
