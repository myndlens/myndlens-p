"""Mock Dashboard API — dev-only endpoints mimicking ObeGee dashboard APIs.

These endpoints let the MyndLens mobile app test dashboard integration
without a live ObeGee backend. MUST NOT exist in production.
"""
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard-mock"])


@router.get("/workspace/config")
async def mock_workspace_config():
    return {
        "workspace": {"tenant_id": "tenant_dev", "slug": "dev-workspace", "name": "Dev Workspace", "status": "READY", "model": "gemini-2.0-flash"},
        "subscription": {"plan_id": "pro", "status": "active", "current_period_end": "2026-03-17T00:00:00Z"},
        "tools": {"enabled": ["web-browser", "file-system", "data-analysis"]},
        "approval_policy": {"auto_approve_low": True, "auto_approve_medium": False},
        "integrations": ["google_oauth"],
        "runtime": {"status": "running", "port": 10010, "myndlens_port": 18791},
    }


@router.patch("/workspace/tools")
async def mock_update_tools(data: dict):
    return {"message": "Tools updated", "enabled_tools": data.get("enabled_tools", [])}


@router.patch("/workspace/model")
async def mock_update_model(data: dict):
    return {"message": "API key updated", "provider": data.get("provider", "unknown")}


@router.get("/workspace/agents")
async def mock_agents():
    return {
        "agents": [
            {"id": "python-coder", "name": "Python Developer", "model": "gemini-2.0-flash", "status": "active", "skills": ["python-dev", "file-operations"], "tools": ["read", "write", "exec"]},
            {"id": "research-bot", "name": "Research Assistant", "model": "gemini-2.0-flash", "status": "active", "skills": ["web-research", "summarization"], "tools": ["web_search", "web_fetch"]},
        ],
        "total": 2,
    }


@router.get("/workspace/usage")
async def mock_usage():
    return {
        "today": {"messages": 45, "tokens": 12453, "tool_calls": 8},
        "limits": {"messages": 500, "tokens": 100000},
        "subscription": {"plan_name": "Pro", "status": "active"},
    }


@router.get("/dashboard-url")
async def mock_dashboard_url():
    return {"webview_url": "https://obegee.co.uk/dashboard", "expires_in": 3600}
