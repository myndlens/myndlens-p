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
def derive_required_oc_tools(
    built_skills: list,
    action_class: str,
) -> tuple[str, list[str]]:
    """Derive OpenClaw tool profile and allow list from matched skills' oc_tools.

    No hardcoded action_class → tool maps.
    The skills themselves carry their tool requirements in the oc_tools field.
    Profile is the most common profile across the skills; allow list is the union.
    """
    all_tools: set = set()
    profiles: list[str] = []

    for skill in built_skills:
        oc = skill.get("oc_tools", {})
        if isinstance(oc, dict):
            for t in oc.get("allow", []):
                if t:
                    all_tools.add(t.strip())
            skill_profile = oc.get("profile", "")
            if skill_profile:
                profiles.append(skill_profile)

    # Profile = most common across skills; default to messaging for COMM_SEND actions
    profile = max(set(profiles), key=profiles.count) if profiles else (
        "messaging" if "SEND" in action_class else "coding"
    )

    allow_list = sorted(all_tools) if all_tools else [f"group:{profile}"]
    return profile, allow_list


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


def derive_required_oc_tools(
    built_skills: list,
    action_class: str,
) -> tuple[str, list[str]]:
    """Derive OpenClaw tool profile and allow list from matched skills' oc_tools.

    No hardcoded action_class → tool maps.
    The skills themselves carry their tool requirements in the oc_tools field.
    Profile is the most common profile across the skills; allow list is the union.
    """
    all_tools: set = set()
    profiles: list[str] = []

    for skill in built_skills:
        oc = skill.get("oc_tools", {})
        if isinstance(oc, dict):
            for t in oc.get("allow", []):
                if t:
                    all_tools.add(t.strip())
            skill_profile = oc.get("profile", "")
            if skill_profile:
                profiles.append(skill_profile)

    profile = max(set(profiles), key=profiles.count) if profiles else (
        "messaging" if "SEND" in action_class else "coding"
    )
    allow_list = sorted(all_tools) if all_tools else [f"group:{profile}"]
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
    intent: str = "",
) -> AgentSpec:
    """Select the best agent by PURPOSE MATCH against pre-defined named agents.

    Priority:
    1. Score all tenant agents by: action_class fit + trigger keyword match + skill overlap
    2. Best-scoring pre-defined agent wins
    3. If no agents provisioned yet, auto-provision the 14 pre-defined agents first
    4. If still no match (score=0), build a dynamic spec from skills

    This is FUNCTIONALITY-BASED selection: agent is chosen for what it DOES,
    not by its name or list order.
    """
    from agents.predefined import score_agent_for_mandate, provision_predefined_agents

    try:
        from core.database import get_db
        db = get_db()

        # Auto-provision pre-defined agents if none exist for this tenant
        count = await db.agents.count_documents({"tenant_id": tenant_id, "status": "ACTIVE"})
        if count == 0 and tenant_id:
            inserted = await provision_predefined_agents(tenant_id)
            logger.info("[AgentSelect] Provisioned %d pre-defined agents for tenant=%s",
                        inserted, tenant_id)

        # Load all active agents for this tenant
        agents = await db.agents.find(
            {"tenant_id": tenant_id, "status": "ACTIVE"},
            {"_id": 0},
        ).to_list(50)

        if agents:
            # Score each agent by PURPOSE: action_class + trigger + skill overlap
            scored = []
            for agent in agents:
                # Purpose score (action class + trigger keywords)
                purpose_score = score_agent_for_mandate(agent, intent or " ".join(skill_names), action_class)

                # Skill overlap: does this agent have the skills we matched?
                agent_skills = set(agent.get("skills", []))
                mandate_skills = set(skill_names)
                skill_overlap = len(agent_skills & mandate_skills) / max(len(mandate_skills), 1)
                total_score = purpose_score + skill_overlap * 3.0

                scored.append((round(total_score, 3), agent))

            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, best_agent = scored[0]

            if best_score > 0:
                spec = AgentSpec(
                    agent_id=best_agent["agent_id"],
                    profile=best_agent.get("tools", {}).get("profile", "messaging"),
                    tools_allow=best_agent.get("tools", {}).get("allow", []),
                    tools_deny=best_agent.get("tools", {}).get("deny", []),
                    model=best_agent.get("config", {}).get("model", "claude-opus-4-5"),
                    workspace=best_agent.get("workspace", "~/.openclaw/workspace"),
                    source="existing",
                    name=best_agent.get("name", ""),
                    coverage_score=best_score,
                )
                logger.info(
                    "[AgentSelect] Selected '%s' score=%.2f action=%s",
                    spec.name, best_score, action_class,
                )
                return spec

    except Exception as e:
        logger.warning("[AgentSelect] DB lookup failed: %s — using dynamic spec", str(e))

    # No suitable pre-defined agent — build dynamic spec from skill requirements
    profile, allow_list = derive_required_oc_tools(built_skills, action_class)
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
        coverage_score=1.0,
    )
    logger.info("[AgentSelect] Dynamic spec: id=%s profile=%s skills=%s",
                dynamic_id, profile, skill_names)
    return spec
