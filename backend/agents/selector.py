"""
Agent Selector — selects or defines the right agent based on functional requirements.

Principle: agents are selected by WHAT THEY CAN DO, not by name or list order.

Functional capability is derived from the matched skills' oc_tools:
  - gmail skill (oc_tools: group:messaging) → needs a messaging-capable agent
  - tavily-search (oc_tools: group:web) → needs a web-capable agent
  - github (oc_tools: group:runtime) → needs a runtime/coding agent

If no existing agent covers the required tools, a new agent spec is defined
dynamically and sent to ObeGee for provisioning.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# OpenClaw tool group hierarchy (superset → subset)
_TOOL_HIERARCHY = {
    "full":        {"group:messaging", "group:web", "group:fs", "group:runtime",
                    "group:sessions", "exec", "web_fetch", "web_search", "message", "cron"},
    "coding":      {"group:fs", "group:runtime", "exec", "group:sessions", "web_fetch"},
    "messaging":   {"group:messaging", "message", "web_fetch"},
    "web":         {"group:web", "web_fetch", "web_search", "browser"},
}

# action_class → recommended OpenClaw tool profile
_ACTION_PROFILE = {
    "COMM_SEND":     "messaging",
    "SCHED_MODIFY":  "messaging",
    "INFO_RETRIEVE": "web",
    "DOC_EDIT":      "coding",
    "CODE_GEN":      "coding",
    "FIN_TRANS":     "messaging",
    "SYS_CONFIG":    "coding",
    "DRAFT_ONLY":    "messaging",
}


@dataclass
class AgentSpec:
    """A fully-defined agent specification ready to send to ObeGee."""
    agent_id: str
    profile: str                       # OpenClaw tool profile
    tools_allow: List[str]             # OpenClaw allow list
    tools_deny: List[str] = field(default_factory=list)
    model: str = "claude-opus-4-5"     # default model (can be overridden by ObeGee)
    workspace: str = "~/.openclaw/workspace"
    source: str = "dynamic"            # "existing" | "dynamic"
    name: str = ""
    coverage_score: float = 0.0


def _normalise_oc_tool(tool: str) -> str:
    """Normalise a tool name to OpenClaw format."""
    tool = tool.strip().lower()
    if not tool:
        return ""
    # Already group: format
    if tool.startswith("group:") or tool in ("exec", "web_fetch", "web_search",
                                               "message", "cron", "browser",
                                               "canvas", "nodes", "sessions_spawn"):
        return tool
    # Map common non-OC names to OC groups
    _MAP = {
        "smtp": "group:messaging", "email": "group:messaging",
        "slack": "group:messaging", "discord": "group:messaging",
        "whatsapp": "group:messaging", "sms": "group:messaging",
        "http": "web_fetch", "api": "web_fetch", "fetch": "web_fetch",
        "web": "group:web", "search": "web_search",
        "file": "group:fs", "fs": "group:fs", "disk": "group:fs",
        "python": "exec", "bash": "exec", "shell": "exec", "run": "exec",
        "code": "exec", "runtime": "group:runtime",
        "calendar": "group:messaging", "contacts": "group:messaging",
        "database": "group:fs", "sql": "exec",
    }
    return _MAP.get(tool, "group:web")  # default to web for unknown tools


def derive_required_oc_tools(
    built_skills: List[Dict[str, Any]],
    action_class: str,
) -> tuple[str, List[str]]:
    """Derive the required OpenClaw tool profile and allow list from matched skills.

    Returns (profile, allow_list).
    """
    # Collect all oc_tools from matched skills
    all_tools: set = set()
    for skill in built_skills:
        oc = skill.get("oc_tools", {})
        if isinstance(oc, dict):
            for t in oc.get("allow", []):
                normalised = _normalise_oc_tool(t)
                if normalised:
                    all_tools.add(normalised)
            # Also use profile hint
            skill_profile = oc.get("profile", "")
            if skill_profile in _TOOL_HIERARCHY:
                all_tools.update(_TOOL_HIERARCHY[skill_profile])

    # Determine minimum sufficient profile
    recommended_profile = _ACTION_PROFILE.get(action_class, "messaging")

    # Choose the most restrictive profile that covers all required tools
    if all_tools.issubset(_TOOL_HIERARCHY.get("messaging", set())):
        profile = "messaging"
    elif all_tools.issubset(_TOOL_HIERARCHY.get("web", set())):
        profile = "web"
    elif all_tools.issubset(_TOOL_HIERARCHY.get("coding", set())):
        profile = "coding"
    else:
        profile = "full"

    # If action class recommends stricter profile and it covers all tools, use that
    action_tools = _TOOL_HIERARCHY.get(recommended_profile, set())
    if all_tools.issubset(action_tools):
        profile = recommended_profile

    # Build explicit allow list (deduplicated, sorted)
    allow_list = sorted(set(list(all_tools) + [f"group:{profile}"]))
    if not allow_list:
        allow_list = [f"group:{profile}"]

    return profile, allow_list


def score_agent_coverage(
    agent: Dict[str, Any],
    required_tools: List[str],
    profile: str,
) -> float:
    """Score an agent 0.0–1.0 based on how well it covers the required tools.

    Scoring:
      1.0 = perfect match (covers all required tools, correct profile)
      0.5-0.9 = partial match (covers most tools)
      0.0 = incompatible (missing critical tools or blocked profile)
    """
    agent_allow = set(agent.get("tools", {}).get("allow", []))
    agent_deny = set(agent.get("tools", {}).get("deny", []))
    agent_profile = agent.get("tools", {}).get("profile", "")

    if not required_tools:
        return 0.8 if agent_allow else 0.5

    # Check denied tools — instant disqualification
    for t in required_tools:
        if t in agent_deny:
            return 0.0

    # Coverage ratio
    covered = sum(1 for t in required_tools if t in agent_allow or
                  any(t.startswith(g.replace("group:", "")) for g in agent_allow if g.startswith("group:")))
    coverage = covered / len(required_tools)

    # Profile match bonus
    profile_match = 1.0 if agent_profile == profile else (0.8 if profile in ("messaging", "web") else 0.9)

    # Least-privilege bonus (fewer extra tools = better)
    extra = len(agent_allow) - covered
    lp_bonus = max(0, 0.1 - extra * 0.01)

    return round(min(1.0, coverage * profile_match + lp_bonus), 3)


async def select_agent(
    tenant_id: str,
    action_class: str,
    built_skills: List[Dict[str, Any]],
    skill_names: List[str],
    fallback_agent_id: str = "default",
) -> AgentSpec:
    """Select the best agent for this mandate based on functional capability.

    Priority:
    1. Existing tenant agents scored by tool coverage → highest score wins
    2. If no agents exist or no agent scores > 0.3 → define a new agent dynamically
    3. Dynamic agent spec is built from the skills' oc_tools requirements
    """
    profile, allow_list = derive_required_oc_tools(built_skills, action_class)

    # Try existing agents
    if tenant_id and tenant_id != "default":
        try:
            from core.database import get_db
            db = get_db()
            agents = await db.agents.find(
                {"tenant_id": tenant_id, "status": "ACTIVE"},
                {"_id": 0},
            ).to_list(50)

            if agents:
                # Score every agent by functional coverage
                scored = [
                    (score_agent_coverage(a, allow_list, profile), a)
                    for a in agents
                ]
                scored.sort(key=lambda x: x[0], reverse=True)
                best_score, best_agent = scored[0]

                if best_score >= 0.3:
                    spec = AgentSpec(
                        agent_id=best_agent["agent_id"],
                        profile=best_agent.get("tools", {}).get("profile", profile),
                        tools_allow=best_agent.get("tools", {}).get("allow", allow_list),
                        tools_deny=best_agent.get("tools", {}).get("deny", []),
                        model=best_agent.get("config", {}).get("model", "claude-opus-4-5"),
                        workspace=best_agent.get("workspace", "~/.openclaw/workspace"),
                        source="existing",
                        name=best_agent.get("name", best_agent["agent_id"]),
                        coverage_score=best_score,
                    )
                    logger.info(
                        "[AgentSelect] Existing agent: id=%s score=%.2f profile=%s",
                        spec.agent_id, best_score, spec.profile,
                    )
                    return spec
        except Exception as e:
            logger.warning("[AgentSelect] DB lookup failed: %s — using dynamic spec", str(e))

    # No suitable existing agent — define agent dynamically from skill requirements
    import uuid
    dynamic_id = f"dyn_{action_class.lower()[:4]}_{uuid.uuid4().hex[:6]}"
    skill_label = skill_names[0] if skill_names else action_class.lower()

    spec = AgentSpec(
        agent_id=dynamic_id,
        profile=profile,
        tools_allow=allow_list,
        tools_deny=[],
        model="claude-opus-4-5",
        workspace=f"~/.openclaw/workspace-{tenant_id or 'default'}",
        source="dynamic",
        name=f"{profile.title()} Agent ({skill_label})",
        coverage_score=1.0,    # Dynamic spec is purpose-built → perfect coverage
    )

    logger.info(
        "[AgentSelect] Dynamic spec: id=%s profile=%s tools=%s skills=%s",
        dynamic_id, profile, allow_list, skill_names,
    )
    return spec
