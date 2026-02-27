"""Digital Self MCP Server — Model Context Protocol tools for DS access.

Exposes the Digital Self as standardized MCP tools that MyndLens engines
(L1 Scout, Dimension Extractor, Gap Filler, Micro Questions) call to
retrieve user intelligence during mandate processing.

Architecture:
  MyndLens Engine → MCP Client → DS MCP Server → RAG Vector Store + MongoDB
  
  OC NEVER accesses DS. It receives a fully-enriched mandate.

Tools:
  search_memory     — RAG vector search across all DS data
  get_contact       — full contact profile with active threads
  get_pending_actions — all pending actions across all contacts
  get_active_threads — active conversations, filtered by type
  get_inner_circle  — ranked list of closest contacts
  get_schedule      — upcoming meetings/events from threads

Confidentiality:
  All tools respect the `confidential` flag by default.
  Biometric-unlocked queries pass `include_confidential=True`.
"""
import logging
from typing import Any, Dict, List, Optional

from core.database import get_db

logger = logging.getLogger(__name__)


# ── Tool Registry ──────────────────────────────────────────────────────────────

_TOOLS = {}


def mcp_tool(name: str, description: str):
    """Register a function as an MCP tool."""
    def decorator(fn):
        _TOOLS[name] = {
            "name": name,
            "description": description,
            "handler": fn,
        }
        return fn
    return decorator


def list_tools() -> List[Dict[str, str]]:
    """Return all registered MCP tools (for tool discovery)."""
    return [
        {"name": t["name"], "description": t["description"]}
        for t in _TOOLS.values()
    ]


async def call_tool(name: str, params: Dict[str, Any]) -> Any:
    """Invoke an MCP tool by name with parameters."""
    tool = _TOOLS.get(name)
    if not tool:
        return {"error": f"Unknown tool: {name}"}
    try:
        return await tool["handler"](**params)
    except TypeError as e:
        return {"error": f"Invalid params for {name}: {str(e)}"}
    except Exception as e:
        logger.error("[DS_MCP] tool %s error: %s", name, str(e)[:80])
        return {"error": str(e)[:200]}


# ── MCP Tools ──────────────────────────────────────────────────────────────────

@mcp_tool("search_memory", "Search Digital Self memory using natural language query. Returns relevant memories, contacts, threads, and facts.")
async def search_memory(
    user_id: str,
    query: str,
    n_results: int = 5,
    include_confidential: bool = False,
) -> Dict[str, Any]:
    """RAG vector search across all DS data."""
    from memory.retriever import recall
    results = await recall(
        user_id=user_id,
        query_text=query,
        n_results=n_results,
        include_confidential=include_confidential,
    )
    return {"results": results, "count": len(results)}


@mcp_tool("get_contact", "Get full Digital Self profile for a specific contact by name or phone.")
async def get_contact(
    user_id: str,
    name: str = "",
    phone: str = "",
    include_confidential: bool = False,
) -> Dict[str, Any]:
    """Full contact profile with active threads, pending actions, pattern."""
    from memory.retriever import recall

    query = name or phone
    if not query:
        return {"error": "name or phone required"}

    # Search vector store for this contact
    results = await recall(
        user_id=user_id,
        query_text=f"contact {query}",
        n_results=10,
        include_confidential=include_confidential,
    )

    # Filter to results about this specific contact
    contact_docs = []
    for r in results:
        meta = r.get("metadata", {})
        contact_name = meta.get("contact_name", "").lower()
        contact_id = meta.get("contact_id", "").lower()
        if name.lower() in contact_name or (phone and phone in contact_id):
            contact_docs.append(r)

    if not contact_docs:
        return {"found": False, "query": query}

    # Assemble profile from documents
    profile = {"name": query, "documents": []}
    for doc in contact_docs:
        profile["documents"].append({
            "type": doc.get("metadata", {}).get("doc_type", "unknown"),
            "text": doc.get("text", ""),
            "metadata": doc.get("metadata", {}),
        })

    return {"found": True, "profile": profile}


@mcp_tool("get_pending_actions", "Get all pending actions — things user owes others and things others owe user.")
async def get_pending_actions(
    user_id: str,
    include_confidential: bool = False,
) -> Dict[str, Any]:
    """All pending actions across all contacts."""
    from memory.retriever import recall

    user_owes = await recall(
        user_id=user_id,
        query_text="user owes pending action commitment deadline",
        n_results=10,
        include_confidential=include_confidential,
    )
    they_owe = await recall(
        user_id=user_id,
        query_text="owes user waiting on promised committed",
        n_results=10,
        include_confidential=include_confidential,
    )

    # Filter to actual pending action docs
    actions = {
        "user_owes": [
            {"text": r["text"], "contact": r.get("metadata", {}).get("contact_name", "?")}
            for r in user_owes
            if r.get("metadata", {}).get("doc_type") == "pending_action"
            and r.get("metadata", {}).get("direction") == "user_owes"
        ],
        "they_owe": [
            {"text": r["text"], "contact": r.get("metadata", {}).get("contact_name", "?")}
            for r in they_owe
            if r.get("metadata", {}).get("doc_type") == "pending_action"
            and r.get("metadata", {}).get("direction") == "they_owe"
        ],
    }
    return actions


@mcp_tool("get_active_threads", "Get active conversation threads, optionally filtered by type (CONFLICT, PLANNING, TASK, MEETING, TRAVEL, DELEGATION, REQUEST, ASPIRATION, etc).")
async def get_active_threads(
    user_id: str,
    thread_type: Optional[str] = None,
    include_confidential: bool = False,
) -> Dict[str, Any]:
    """Active threads across all contacts."""
    query = "active thread discussion conversation"
    if thread_type:
        query += f" {thread_type.lower()}"

    from memory.retriever import recall
    results = await recall(
        user_id=user_id,
        query_text=query,
        n_results=15,
        include_confidential=include_confidential,
    )

    threads = []
    for r in results:
        meta = r.get("metadata", {})
        if meta.get("doc_type") != "active_thread":
            continue
        if thread_type and meta.get("thread_type", "").upper() != thread_type.upper():
            continue
        threads.append({
            "text": r.get("text", ""),
            "contact": meta.get("contact_name", "?"),
            "type": meta.get("thread_type", "?"),
            "tension": meta.get("tension", "none"),
        })

    return {"threads": threads, "count": len(threads)}


@mcp_tool("get_inner_circle", "Get the user's inner circle — ranked list of closest contacts with relationship context.")
async def get_inner_circle(
    user_id: str,
    top_n: int = 10,
    include_confidential: bool = False,
) -> Dict[str, Any]:
    """Ranked inner circle contacts."""
    from memory.retriever import recall
    results = await recall(
        user_id=user_id,
        query_text="close relationship family friend colleague inner circle",
        n_results=top_n * 2,
        include_confidential=include_confidential,
    )

    # Filter to identity docs and sort by rank
    contacts = []
    seen = set()
    for r in results:
        meta = r.get("metadata", {})
        if meta.get("doc_type") != "identity":
            continue
        name = meta.get("contact_name", "")
        if name in seen:
            continue
        seen.add(name)
        contacts.append({
            "name": name,
            "rank": meta.get("inner_circle_rank", 99),
            "text": r.get("text", ""),
            "source": meta.get("source", "?"),
            "confidential": meta.get("confidential", False),
        })

    contacts.sort(key=lambda c: c["rank"])
    return {"inner_circle": contacts[:top_n], "count": len(contacts[:top_n])}


@mcp_tool("get_schedule", "Get upcoming meetings, events, and travel from active threads.")
async def get_schedule(
    user_id: str,
    include_confidential: bool = False,
) -> Dict[str, Any]:
    """Upcoming events from active threads."""
    from memory.retriever import recall
    results = await recall(
        user_id=user_id,
        query_text="meeting travel event schedule appointment date time upcoming",
        n_results=10,
        include_confidential=include_confidential,
    )

    events = []
    for r in results:
        meta = r.get("metadata", {})
        tt = meta.get("thread_type", "").upper()
        if tt in ("MEETING", "TRAVEL") or "meeting" in r.get("text", "").lower() or "travel" in r.get("text", "").lower():
            events.append({
                "text": r.get("text", ""),
                "contact": meta.get("contact_name", "?"),
                "type": tt or "EVENT",
            })

    return {"events": events, "count": len(events)}
