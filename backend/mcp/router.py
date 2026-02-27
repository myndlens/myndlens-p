"""MCP HTTP Router — exposes Digital Self MCP tools as REST endpoints.

Follows the MCP JSON-RPC pattern:
  POST /api/mcp/tools/list   → list available tools
  POST /api/mcp/tools/call   → invoke a tool by name

MyndLens engines use these endpoints to access Digital Self data
during mandate processing (L1 Scout, Gap Filler, Dimensions, etc).
"""
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from mcp.ds_server import list_tools, call_tool

logger = logging.getLogger(__name__)

mcp_router = APIRouter(prefix="/api/mcp", tags=["MCP — Digital Self Tools"])


class ToolCallRequest(BaseModel):
    name: str
    params: Dict[str, Any] = {}


class ToolCallResponse(BaseModel):
    name: str
    result: Any
    error: Optional[str] = None


@mcp_router.get("/tools/list")
async def tools_list():
    """MCP tool discovery — returns all registered DS tools."""
    return {"tools": list_tools()}


@mcp_router.post("/tools/call")
async def tools_call(req: ToolCallRequest):
    """MCP tool invocation — call a DS tool by name with params."""
    logger.info("[MCP] tool_call: %s params=%s", req.name, list(req.params.keys()))
    result = await call_tool(req.name, req.params)

    if isinstance(result, dict) and "error" in result:
        return ToolCallResponse(name=req.name, result=None, error=result["error"])

    return ToolCallResponse(name=req.name, result=result)
