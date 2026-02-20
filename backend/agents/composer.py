"""
Agent Composer -- assembles the right agent collection for each mandate.

Two paths:
  PATH 1 (Catalogue Match):
    Skills matched → find existing named agents that cover those skills
    → assemble a collection (may be more than one agent)

  PATH 2 (Skill Composition):
    No catalogue agent fits → take the closest available skills
    → tweak SKILL.md with mandate-specific context
    → name it → create a new agent for this mandate

The composed agent collection is shown to the user for approval before
anything is pushed to OpenClaw.
"""
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class AssembledAgent:
    """One agent in the collection assembled for this mandate."""
    agent_id: str
    name: str
    purpose: str            # what this agent does IN THIS mandate
    skills: list[str]       # ClawHub skill slugs
    tools: dict             # OpenClaw tool policy
    skill_md: str           # SKILL.md content (possibly tweaked)
    source: str             # "catalogue" | "composed" | "tweaked"
    is_new: bool            # True = created fresh for this mandate


@dataclass
class AgentCollection:
    """All agents assembled for a mandate, ready for user approval."""
    agents: list[AssembledAgent] = field(default_factory=list)
    coordination: str = "sequential"    # sequential | parallel | hybrid
    source: str = "catalogue"           # catalogue | composed | mixed
    approval_lines: list[str] = field(default_factory=list)  # shown to user


# ── Skill SKILL.md tweaker ────────────────────────────────────────────────────

def tweak_skill_md(skill_md: str, mandate_context: str, agent_name: str) -> str:
    """Inject mandate-specific context into a SKILL.md.

    Adds a mandate preamble above the original instructions so OpenClaw
    knows exactly what this agent is being asked to do for this specific mandate.
    No LLM required — pure text transformation.
    """
    # Parse existing frontmatter / body
    if skill_md.startswith("---"):
        parts = skill_md.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            original_body = parts[2].strip()
            tweaked_body = (
                f"## Mandate Context for This Execution\n\n"
                f"{mandate_context}\n\n"
                f"---\n\n"
                f"{original_body}"
            )
            return f"---{frontmatter}---\n\n{tweaked_body}"

    # No frontmatter — prepend context
    return (
        f"## Mandate Context for This Execution\n\n"
        f"{mandate_context}\n\n"
        f"---\n\n"
        f"{skill_md}"
    )


def name_composed_agent(mandate_intent: str, action_class: str, skills: list[str]) -> str:
    """Generate a descriptive name from mandate content — no hardcoded verb map."""
    action_label = action_class.replace("_", " ").title()

    words = [w for w in re.findall(r'\b[A-Za-z]{4,}\b', mandate_intent)
             if w.lower() not in {"send", "email", "make", "write", "find", "search",
                                   "create", "update", "with", "from", "that", "this",
                                   "about", "using", "user", "manager"}][:2]
    if words:
        return f"{action_label} Agent — {' '.join(words).title()}"
    if skills:
        return f"{action_label} Agent ({skills[0]})"
    return f"{action_label} Agent"


# ── Path 1: Catalogue matching ────────────────────────────────────────────────

async def find_catalogue_agents(
    tenant_id: str,
    action_class: str,
    intent: str,
    skill_names: list[str],
) -> list[dict]:
    """Find existing catalogue agents that cover the mandate's skills.

    Returns a list of matching agents (may be more than one).
    An agent 'matches' if:
      - Its action_class covers this mandate, AND
      - It shares at least one skill with the matched skills list
    """
    from agents.predefined import score_agent_for_mandate
    from core.database import get_db
    from agents.predefined import provision_predefined_agents

    db = get_db()

    # Auto-provision if empty
    count = await db.agents.count_documents({"tenant_id": tenant_id, "status": "ACTIVE"})
    if count == 0 and tenant_id:
        await provision_predefined_agents(tenant_id)

    catalogue = await db.agents.find(
        {"tenant_id": tenant_id, "status": "ACTIVE"},
        {"_id": 0},
    ).to_list(50)

    # Find every agent that covers at least one of the mandate's skills
    mandate_skills = set(skill_names)
    covering: list[tuple[float, dict]] = []

    for agent in catalogue:
        agent_skills = set(agent.get("skills", []))
        shared = agent_skills & mandate_skills
        if not shared:
            continue

        # Score: purpose match + skill coverage
        purpose_score = score_agent_for_mandate(agent, intent, action_class)
        skill_coverage = len(shared) / max(len(mandate_skills), 1)
        total = purpose_score + skill_coverage * 3.0

        if total > 0:
            covering.append((round(total, 2), agent, shared))

    covering.sort(key=lambda x: x[0], reverse=True)

    if not covering:
        return []

    # Select agents greedily: keep adding until all mandate skills are covered
    selected = []
    covered_skills: set = set()

    for score, agent, shared in covering:
        uncovered = mandate_skills - covered_skills
        if not uncovered:
            break
        if shared & uncovered:
            selected.append(agent)
            covered_skills |= shared

    logger.info(
        "[Composer] Catalogue match: %d agents cover %d/%d skills",
        len(selected), len(covered_skills), len(mandate_skills),
    )
    return selected


# ── Path 2: Skill composition (no catalogue match) ────────────────────────────

async def compose_from_skills(
    matched_skills: list[dict],
    mandate_intent: str,
    action_class: str,
    tenant_id: str,
) -> list[AssembledAgent]:
    """Compose new agents from available skills when no catalogue agent fits.

    Groups skills by category → one agent per group.
    Tweaks each skill's SKILL.md with the mandate context.
    Saves the new agent to the catalogue for future reuse.
    """
    from core.database import get_db

    if not matched_skills:
        return []

    db = get_db()

    # Group skills by category — merge all skills of same category into ONE agent
    # (prevents duplicates when multiple skills share a category like "general")
    groups: dict[str, list[dict]] = {}
    for skill in matched_skills:
        cat = skill.get("category", "general").lower()
        # Consolidate noisy categories into their parent
        if cat in ("general", "utility", "tools"):
            cat = action_class.lower().replace("_", "-")
        groups.setdefault(cat, []).append(skill)

    composed: list[AssembledAgent] = []
    mandate_context = f"Mandate: {mandate_intent}"
    seen_categories: set = set()  # prevent duplicate agents for same category

    for cat, skills in groups.items():
        if cat in seen_categories:
            continue
        seen_categories.add(cat)
        slugs = [s.get("slug", s.get("name", "")) for s in skills]
        name = name_composed_agent(mandate_intent, action_class, slugs)

        # Use the first skill's SKILL.md as the base — tweak it
        base_skill = skills[0]
        base_md = base_skill.get("skill_md", "")
        tweaked_md = tweak_skill_md(base_md, mandate_context, name) if base_md else ""

        # Derive tools from skill oc_tools
        all_tools: set = set()
        for s in skills:
            oc = s.get("oc_tools", {})
            if isinstance(oc, dict):
                all_tools.update(oc.get("allow", []))

        oc_tools = {
            "profile": base_skill.get("oc_tools", {}).get("profile", "messaging"),
            "allow": sorted(all_tools) or ["group:web"],
        }

        agent_id = f"composed_{uuid.uuid4().hex[:8]}"

        agent = AssembledAgent(
            agent_id=agent_id,
            name=name,
            purpose=f"Handles {cat} tasks for: {mandate_intent[:60]}",
            skills=slugs,
            tools=oc_tools,
            skill_md=tweaked_md,
            source="composed",
            is_new=True,
        )
        composed.append(agent)

        # Save to catalogue for future reuse
        await db.agents.insert_one({
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "name": name,
            "description": agent.purpose,
            "skills": slugs,
            "tools": oc_tools,
            "action_class": [action_class],
            "triggers": [],
            "status": "ACTIVE",
            "source": "composed",
            "created_at": datetime.now(timezone.utc),
        })
        logger.info("[Composer] Composed new agent: '%s' skills=%s", name, slugs)

    return composed


# ── Main entry point ──────────────────────────────────────────────────────────

async def assemble_agent_collection(
    mandate_intent: str,
    action_class: str,
    matched_skills: list[dict],
    skill_names: list[str],
    tenant_id: str,
    topology_coordination: str = "sequential",
) -> AgentCollection:
    """Assemble the right agent collection for a mandate.

    PATH 1: catalogue agents cover the skills → use them
    PATH 2: no catalogue match → compose new agents from skills
    MIXED:  some skills covered by catalogue, rest composed

    Returns AgentCollection with:
      - agents: list of AssembledAgent (for approval card)
      - approval_lines: human-readable summary for the user
    """
    collection = AgentCollection()

    # PATH 1: Try catalogue
    catalogue_agents = await find_catalogue_agents(tenant_id, action_class, mandate_intent, skill_names)

    if catalogue_agents:
        # Determine which skills are still uncovered after catalogue agents
        catalogue_skills: set = set()
        for a in catalogue_agents:
            catalogue_skills.update(a.get("skills", []))

        uncovered = set(skill_names) - catalogue_skills

        # Convert catalogue agents to AssembledAgent
        for a in catalogue_agents:
            agent_skills = [s for s in a.get("skills", []) if s in set(skill_names)]
            collection.agents.append(AssembledAgent(
                agent_id=a["agent_id"],
                name=a["name"],
                purpose=_purpose_for_mandate(a["name"], mandate_intent),
                skills=agent_skills or a.get("skills", [])[:3],
                tools=a.get("tools", {}),
                skill_md="",   # catalogue agents — ObeGee loads from clawdhub
                source="catalogue",
                is_new=False,
            ))

        # PATH 2: Compose agents for uncovered skills
        if uncovered:
            remaining = [s for s in matched_skills if s.get("slug", s.get("name")) in uncovered]
            if remaining:
                composed = await compose_from_skills(remaining, mandate_intent, action_class, tenant_id)
                collection.agents.extend(composed)
                collection.source = "mixed"
            else:
                collection.source = "catalogue"
        else:
            collection.source = "catalogue"

    else:
        # PATH 2 entirely: compose all from skills
        composed = await compose_from_skills(matched_skills, mandate_intent, action_class, tenant_id)
        collection.agents.extend(composed)
        collection.source = "composed"

    # Coordination
    collection.coordination = topology_coordination if len(collection.agents) > 1 else "sequential"

    # Build approval lines for the user
    collection.approval_lines = _build_approval_lines(collection, mandate_intent)

    logger.info(
        "[Composer] Collection assembled: agents=%d source=%s coordination=%s",
        len(collection.agents), collection.source, collection.coordination,
    )
    return collection


def _purpose_for_mandate(agent_name: str, intent: str) -> str:
    """State what this agent does in plain English for this specific mandate."""
    verbs = {
        "Email": "Send email",
        "WhatsApp": "Send WhatsApp message",
        "Slack": "Post to Slack",
        "Calendar": "Update calendar",
        "Morning": "Research and summarise",
        "Research": "Search and summarise",
        "Marketing": "Create content",
        "Social Media": "Publish to social",
        "Finance": "Handle financials",
        "Code": "Write code",
        "Document": "Draft document",
        "Smart Home": "Control devices",
        "Phone": "Make call/send SMS",
        "General": "Handle mandate",
    }
    for keyword, verb in verbs.items():
        if keyword.lower() in agent_name.lower():
            return f"{verb} — {intent[:50]}"
    return f"{agent_name} — {intent[:50]}"


def _build_approval_lines(collection: AgentCollection, intent: str) -> list[str]:
    """Build human-readable approval summary for the user."""
    lines = []

    if len(collection.agents) == 1:
        a = collection.agents[0]
        badge = "📦" if a.source == "catalogue" else "🆕"
        lines.append(f"{badge} {a.name}")
        lines.append(f"   {a.purpose}")
        if a.skills:
            lines.append(f"   Skills: {', '.join(a.skills[:3])}")
    else:
        coord_label = {"sequential": "🔁 One after another", "parallel": "⚡ Simultaneously",
                       "hybrid": "🔀 Coordinated"}.get(collection.coordination, "")
        lines.append(f"{coord_label} — {len(collection.agents)} agents")
        for i, a in enumerate(collection.agents, 1):
            badge = "📦" if a.source == "catalogue" else "🆕"
            lines.append(f"   {i}. {badge} {a.name} ({', '.join(a.skills[:2])})")

    if any(a.is_new for a in collection.agents):
        lines.append("   🆕 = new agent created for this mandate, saved for future use")

    return lines
