"""MCP HTTP Router — exposes Digital Self MCP tools as REST endpoints.

SECURITY: All MCP endpoints require authentication. user_id is derived
from the verified auth token — NEVER from the request body. This prevents
cross-tenant data leakage where an attacker submits another user's ID.

MyndLens engines use these endpoints to access Digital Self data
during mandate processing (L1 Scout, Gap Filler, Dimensions, etc).
"""
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Dict, Optional

from mcp.ds_server import list_tools, call_tool

logger = logging.getLogger(__name__)

mcp_router = APIRouter(prefix="/api/mcp", tags=["MCP — Digital Self Tools"])


async def _get_mcp_user_id(request: Request) -> str:
    """Extract and verify user_id from auth token. Never trust request body."""
    # Check internal key (for server-to-server calls)
    internal_key = request.headers.get("X-Internal-Key", "")
    if internal_key:
        from config.settings import get_settings
        settings = get_settings()
        if internal_key == settings.EMERGENT_LLM_KEY:
            # Internal call — user_id must be in query param or body, but verified by key
            body = await request.json() if request.method == "POST" else {}
            uid = body.get("params", {}).get("user_id", "") or request.query_params.get("user_id", "")
            if not uid:
                raise HTTPException(status_code=400, detail="user_id required")
            return uid

    # Check WS session token (from mobile app via auth header)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            from auth.tokens import validate_token
            claims = validate_token(token)
            return claims.user_id
        except Exception:
            pass

    # Check SSO token (from ObeGee pairing)
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            from obegee_sso import validate_myndlens_token
            claims = validate_myndlens_token(token)
            return claims.get("sub", "")
        except Exception:
            pass

    raise HTTPException(status_code=401, detail="Authentication required for MCP tools")


class ToolCallRequest(BaseModel):
    name: str
    params: Dict[str, Any] = {}


class ToolCallResponse(BaseModel):
    name: str
    result: Any
    error: Optional[str] = None


@mcp_router.get("/tools/list")
async def tools_list():
    """MCP tool discovery — returns all registered DS tools. Public (no sensitive data)."""
    return {"tools": list_tools()}


@mcp_router.post("/tools/call")
async def tools_call(req: ToolCallRequest, request: Request):
    """MCP tool invocation — requires auth. user_id derived from token, not body."""
    verified_user_id = await _get_mcp_user_id(request)

    # Override user_id in params with the verified one — NEVER trust client-provided user_id
    safe_params = dict(req.params)
    safe_params["user_id"] = verified_user_id

    logger.info("[MCP] tool_call: %s user=%s params=%s", req.name, verified_user_id, list(safe_params.keys()))
    result = await call_tool(req.name, safe_params)

    if isinstance(result, dict) and "error" in result:
        return ToolCallResponse(name=req.name, result=None, error=result["error"])

    return ToolCallResponse(name=req.name, result=result)
