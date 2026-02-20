"""Agent Topology Assessment -- determines sub-agent structure for mandate execution.

Separate from the QC pass/fail check. Answers:
  How many agents are needed?
  What is each agent responsible for?
  Sequential or parallel execution?

Called after QC passes and before the approval gate is shown to the user.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class SubAgentSpec:
    role: str             # "email-composer" | "calendar-manager" | "researcher"
    skills: List[str]     # skill names assigned to this sub-agent
    tools: List[str]      # tools this sub-agent needs
    description: str      # human-readable role description


@dataclass
class AgentTopology:
    sub_agents: List[SubAgentSpec] = field(default_factory=list)
    coordination: str = "sequential"     # sequential | parallel | hybrid
    complexity: str = "simple"           # simple | moderate | complex
    # Human-readable approval card text shown to user before Approve
    approval_lines: List[str] = field(default_factory=list)


# Action class -> natural language role name
_ROLE_NAMES = {
    "COMM_SEND": "Message Composer",
    "SCHED_MODIFY": "Calendar Manager",
    "INFO_RETRIEVE": "Research Agent",
    "DOC_EDIT": "Document Editor",
    "CODE_GEN": "Code Generator",
    "FIN_TRANS": "Finance Agent",
    "SYS_CONFIG": "System Configurator",
}

# Tool category labels for the approval card
_TOOL_LABELS = {
    "smtp": "send emails",
    "calendar": "read/write your calendar",
    "contacts": "read your contacts",
    "files": "access your files",
    "web": "search the web",
    "code": "execute code",
    "payment": "process payments",
    "api": "call external APIs",
}


def _tools_from_skill(skill: Dict[str, Any]) -> List[str]:
    """Extract tool names from a skill's oc_tools allow list."""
    oc = skill.get("oc_tools", {})
    if isinstance(oc, dict):
        return [t for t in oc.get("allow", []) if t]
    return []


def _tool_label(tool: str) -> str:
    """Convert an OpenClaw tool name to plain English."""
    if tool.startswith("group:"):
        group = tool.replace("group:", "")
        return f"{group} access"
    return tool


async def assess_agent_topology(
    intent: str,
    action_class: str,
    skill_names: List[str],
    built_skills: List[Dict[str, Any]],
) -> AgentTopology:
    """Determine agent topology from skills and action complexity.

    Rules (no LLM -- deterministic, zero latency):
    - 1 skill: single agent, sequential
    - 2-3 skills, same category: single agent, sequential
    - 2-3 skills, different categories: 1 primary + sub-agents per category
    - >3 skills or high-risk mix: complex topology, parallel where possible
    """
    topology = AgentTopology()

    if not built_skills:
        topology.approval_lines = [f"Execute: {intent[:80]}"]
        return topology

    # Group skills by category
    category_groups: Dict[str, List[Dict]] = {}
    for s in built_skills:
        cat = s.get("category", "general").lower()
        category_groups.setdefault(cat, []).append(s)

    n_categories = len(category_groups)

    if n_categories == 1 and len(built_skills) <= 2:
        # Simple: one agent handles all skills
        all_tools = []
        for s in built_skills:
            all_tools.extend(_tools_from_skill(s))
        role = _ROLE_NAMES.get(action_class, "Execution Agent")
        topology.sub_agents = [SubAgentSpec(
            role=role,
            skills=skill_names,
            tools=list(set(all_tools)),
            description=f"{role} using {', '.join(skill_names)}",
        )]
        topology.coordination = "sequential"
        topology.complexity = "simple"

    elif n_categories <= 3:
        # Moderate: one sub-agent per category
        for cat, skills in category_groups.items():
            cat_skill_names = [s["name"] for s in skills]
            cat_tools = []
            for s in skills:
                cat_tools.extend(_tools_from_skill(s))
            role = cat.replace("-", " ").title() + " Agent"
            topology.sub_agents.append(SubAgentSpec(
                role=role,
                skills=cat_skill_names,
                tools=list(set(cat_tools)),
                description=f"{role}: {', '.join(cat_skill_names)}",
            ))
        topology.coordination = "parallel" if n_categories > 1 else "sequential"
        topology.complexity = "moderate"

    else:
        # Complex: multiple categories, needs orchestration
        topology.complexity = "complex"
        topology.coordination = "hybrid"
        for cat, skills in category_groups.items():
            cat_skill_names = [s["name"] for s in skills]
            cat_tools = []
            for s in skills:
                cat_tools.extend(_tools_from_skill(s))
            topology.sub_agents.append(SubAgentSpec(
                role=cat.replace("-", " ").title() + " Agent",
                skills=cat_skill_names,
                tools=list(set(cat_tools)),
                description=f"Handles {', '.join(cat_skill_names)}",
            ))

    # Build human-readable approval card lines
    lines = []
    if len(topology.sub_agents) == 1:
        agent = topology.sub_agents[0]
        tool_descriptions = [_tool_label(t) for t in agent.tools[:3]]
        lines.append(f"\U0001f9e0 {agent.role}")
        if tool_descriptions:
            lines.append(f"   Permissions: {', '.join(tool_descriptions)}")
        lines.append(f"   Skills: {', '.join(agent.skills)}")
    else:
        lines.append(f"{'⚡ Parallel' if topology.coordination == 'parallel' else '🔁 Sequential'} execution ({len(topology.sub_agents)} agents)")
        for i, agent in enumerate(topology.sub_agents, 1):
            tool_descriptions = [_tool_label(t) for t in agent.tools[:2]]
            perm = f" [{', '.join(tool_descriptions)}]" if tool_descriptions else ""
            lines.append(f"   {i}. {agent.role}{perm}")

    topology.approval_lines = lines

    logger.info(
        "[AgentTopology] action=%s complexity=%s agents=%d coordination=%s",
        action_class, topology.complexity, len(topology.sub_agents), topology.coordination,
    )
    return topology
