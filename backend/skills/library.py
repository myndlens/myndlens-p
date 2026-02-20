"""Skills Library — OC Hub skills reference, matching, and dynamic generation.

Spec 7: Loads the ClawHub skills library, indexes for search,
matches skills to user intent via keyword similarity, and generates
custom skills by combining hub skills with MyndLens capabilities.
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.database import get_db

logger = logging.getLogger(__name__)

LIBRARY_PATH = Path(__file__).parent.parent / "assets" / "skills-library.json"
_indexed = False


async def load_and_index_library() -> Dict[str, Any]:
    """Load skills library JSON and index into MongoDB for search."""
    global _indexed
    db = get_db()

    if not LIBRARY_PATH.exists():
        return {"status": "ERROR", "message": f"Library not found: {LIBRARY_PATH}"}

    with open(LIBRARY_PATH, "r") as f:
        library = json.load(f)

    categories = library.get("categories", [])
    total = 0

    for cat in categories:
        cat_name = cat.get("name", "")
        for skill in cat.get("skills", []):
            doc = {
                "category": cat_name,
                "name": skill.get("name", ""),
                "description": skill.get("description", ""),
                "required_tools": skill.get("required_tools", ""),
                "usage_examples": skill.get("usage_examples", ""),
                "downloads": skill.get("downloads") or 0,
                "stars": skill.get("stars") or 0,
                "install_command": skill.get("install_command", ""),
                "view_url": skill.get("view_url", ""),
                "search_text": f"{skill.get('name', '')} {skill.get('description', '')} {cat_name}".lower(),
            }
            await db.skills_library.update_one(
                {"name": doc["name"], "category": doc["category"]},
                {"$set": doc},
                upsert=True,
            )
            total += 1

    # Create text index for search
    await db.skills_library.create_index([("search_text", "text")])
    _indexed = True

    logger.info("Skills library indexed: %d skills from %d categories", total, len(categories))
    return {
        "status": "OK",
        "skills_indexed": total,
        "categories": len(categories),
        "library_version": library.get("library_version", "unknown"),
    }


async def search_skills(
    query: str,
    limit: int = 10,
    category_filter: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """Search skills by keyword. Optionally pre-filter by category list."""
    db = get_db()
    q = query.lower().strip()

    # Category pre-filter — narrows search before keyword matching
    base_filter: dict = {}
    if category_filter:
        cat_pattern = "|".join(re.escape(c) for c in category_filter)
        base_filter["category"] = {"$regex": cat_pattern, "$options": "i"}

    # Text search with optional category filter
    text_filter = {"$text": {"$search": q}, **base_filter}
    cursor = db.skills_library.find(
        text_filter,
        {"_id": 0, "search_text": 0, "score": {"$meta": "textScore"}},
    ).sort([("score", {"$meta": "textScore"})]).limit(limit)
    results = await cursor.to_list(limit)

    # If category-filtered text search returned nothing, fall back to regex without category filter
    if not results:
        pattern = "|".join(re.escape(w) for w in q.split() if len(w) > 2)
        if not pattern:
            return []
        cursor = db.skills_library.find(
            {"search_text": {"$regex": pattern, "$options": "i"}},
            {"_id": 0, "search_text": 0},
        ).sort("stars", -1).limit(limit)
        results = await cursor.to_list(limit)

    return results


async def match_skills_to_intent(
    intent: str,
    top_n: int = 5,
    action_class: str = "",
) -> List[Dict[str, Any]]:
    """Match skills to intent using full-text search across name, description AND skill_md body.

    ClawHub-ingested skills now include full SKILL.md content, enabling semantic
    matching against the complete instruction text — not just the description line.

    action_class filters by category before keyword search (higher precision).
    required_env pre-flight: skills needing unconfigured env vars are deprioritised.
    """
    ACTION_CATEGORIES = {
        "COMM_SEND":     ["communication", "email", "messaging", "social"],
        "SCHED_MODIFY":  ["scheduling", "calendar", "productivity"],
        "INFO_RETRIEVE": ["search", "data", "api", "utility", "monitoring"],
        "DOC_EDIT":      ["writing", "documents", "productivity", "marketing"],
        "CODE_GEN":      ["coding", "development", "tools", "utility"],
        "FIN_TRANS":     ["finance", "payment", "commerce"],
    }

    # Env vars configured in backend settings (pre-flight availability check)
    from config.settings import get_settings
    settings = get_settings()
    configured_envs: set = set()
    for field_name, val in settings.__dict__.items():
        if val and isinstance(val, str) and len(val) > 4:
            configured_envs.add(field_name.upper())
    # Add known-configured Maton/integration vars from env
    import os
    for k in os.environ:
        if os.environ[k]:
            configured_envs.add(k.upper())

    stop_words = {
        "i", "want", "to", "the", "a", "an", "my", "me", "is", "do",
        "can", "you", "please", "for", "with", "on", "in", "of", "and", "or",
        "user", "context", "contacts", "locations", "traits", "manager",
        "colleague", "mandate",
    }
    keywords = [w for w in re.findall(r'\w+', intent.lower())
                if w not in stop_words and len(w) > 2]
    query = " ".join(keywords[:8])

    if not query:
        return []

    category_filter = ACTION_CATEGORIES.get(action_class.upper(), [])

    results = await search_skills(query, limit=top_n * 3, category_filter=category_filter)

    for r in results:
        name_lower = r.get("name", "").lower()
        desc_lower = r.get("description", "").lower()
        # Include skill_md body in scoring (ClawHub skills have full instruction text)
        skill_body = r.get("skill_md", "")[:2000].lower()

        score = sum(1 for k in keywords if k in name_lower) * 4
        score += sum(1 for k in keywords if k in desc_lower) * 2
        score += sum(1 for k in keywords if k in skill_body)
        score += min(r.get("stars", 0) / 50, 2)
        score *= r.get("relevance_modifier", 1.0)

        # Pre-flight: deprioritise skills whose required_env vars are not configured
        required_env = r.get("required_env", [])
        if required_env:
            missing = [e for e in required_env
                       if e not in configured_envs
                       and not any(e.lower() in ck.lower() for ck in configured_envs)]
            if missing:
                score *= 0.3   # Deprioritise — skill won't work without these
                r["_missing_env"] = missing

        r["relevance_score"] = round(score, 2)

    results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return results[:top_n]


def classify_risk(description: str, required_tools: str = "") -> str:
    """Classify skill risk level for ObeGee governance.

    HIGH:   Irreversible or system-level actions (delete, deploy, execute code, payment)
    MEDIUM: Communication actions and API calls (email, message, file read)
    LOW:    Read-only or purely informational

    Note: 'send' is deliberately MEDIUM (not HIGH) -- COMM_SEND is the most
    common action class and email/messaging is routine, not high-risk.
    """
    text = f"{description} {required_tools}".lower()
    if re.search(r'execute|delete|deploy|push|publish|payment|purchase|drop|reset|wipe|admin', text):
        return "high"
    if re.search(r'send|write|api|file|network|http|database|cloud|external|message|email', text):
        return "medium"
    return "low"


async def fetch_skill_spec(view_url: str) -> dict:
    """Fetch skill metadata from ClawHub JSON API.

    view_url format: https://clawhub.ai/skills/{slug}
    API endpoint:    https://clawhub.ai/api/v1/skills/{slug}
    """
    if not view_url or "clawhub.ai" not in view_url:
        return {}
    try:
        slug_match = re.search(r"/skills/([^/?#]+)", view_url)
        if not slug_match:
            return {}
        slug = slug_match.group(1)
        api_url = f"https://clawhub.ai/api/v1/skills/{slug}"

        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(api_url, headers={"Accept": "application/json"})
            if resp.status_code == 200:
                data = resp.json()
                skill_meta = data.get("skill", {})
                version_meta = data.get("latestVersion", {})
                return {
                    "clawhub_slug": slug,
                    "clawhub_summary": skill_meta.get("summary", ""),
                    "clawhub_version": version_meta.get("version", ""),
                    "clawhub_changelog": version_meta.get("changelog", ""),
                    "clawhub_downloads": skill_meta.get("stats", {}).get("downloads", 0),
                    "clawhub_api_url": api_url,
                }
    except Exception as e:
        logger.debug("[SkillFetch] Failed to fetch %s: %s", view_url, str(e))
    return {}


async def build_skill(
    matched_skills: List[Dict[str, Any]],
    intent: str,
    device_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a skill contract — enriched with live ClawHub metadata.

    Fetches /api/v1/skills/{slug} from ClawHub to get current version,
    summary and download stats. This is the machine-readable spec ClawHub
    exposes; the full execution schema is not yet public and is referenced
    via view_url for human inspection.
    """
    base = matched_skills[0] if matched_skills else {"name": "custom", "description": "Generated skill"}
    device_data = device_data or {}

    # Fetch live metadata from ClawHub JSON API
    clawhub_meta = await fetch_skill_spec(base.get("view_url", ""))
    if clawhub_meta:
        # Prefer ClawHub summary over local description when available
        if clawhub_meta.get("clawhub_summary"):
            base = {**base, "description": clawhub_meta["clawhub_summary"]}
        logger.info(
            "[SkillFetch] Enriched: slug=%s version=%s downloads=%d",
            clawhub_meta.get("clawhub_slug"),
            clawhub_meta.get("clawhub_version"),
            clawhub_meta.get("clawhub_downloads", 0),
        )

    # Generate enhanced description
    enhancements = list(device_data.keys()) if device_data else []
    desc = base.get("description", "Custom skill")
    if enhancements:
        desc += f". Enhanced with: {', '.join(enhancements)}"

    # Extract intent action word for naming
    action = intent.split()[0].capitalize() if intent else "Custom"
    name = f"{base['name']}-{action}" if base.get("name") != "custom" else f"custom-{action}"

    risk = classify_risk(desc, base.get("required_tools", ""))

    # Collect source code references from all matched skills
    source_refs = [
        {"name": s.get("name"), "view_url": s.get("view_url"), "install_command": s.get("install_command")}
        for s in matched_skills if s.get("view_url")
    ]

    skill = {
        "name": name,
        "description": desc,
        "baseHubSkill": base.get("name", "custom"),
        "baseCategory": base.get("category", ""),
        "baseViewUrl": base.get("view_url", ""),
        "install_command": base.get("install_command", "custom-build"),
        "required_tools": base.get("required_tools", ""),
        "risk": risk,
        "enhancements": enhancements,
        "intent_source": intent,
        "source_references": source_refs,
        "skill_md": _generate_skill_md(
            name, desc, risk, base.get("required_tools", ""),
            enhancements, base.get("view_url", ""), source_refs,
        ),
        "llm_context": _build_llm_context(base, matched_skills, intent, enhancements),
    }

    logger.info("Skill built: %s (base=%s, risk=%s, refs=%d)", name, base.get("name"), risk, len(source_refs))
    return skill


def _build_llm_context(
    base: Dict[str, Any],
    matched: List[Dict[str, Any]],
    intent: str,
    enhancements: List[str],
) -> str:
    """Build context string for LLM to understand how to generate the skill.

    Includes source code URLs the LLM can reference/fetch to understand
    how existing hub skills work before creating a custom one.
    """
    lines = [
        f"Generate a custom OpenClaw skill for intent: \"{intent}\"",
        f"\nBase skill: {base.get('name', 'custom')}",
        f"Description: {base.get('description', '')}",
    ]

    if base.get("view_url"):
        lines.append(f"Source code reference: {base['view_url']}")
        lines.append("  ^ Fetch this URL to see the base skill's implementation, then adapt it.")

    if base.get("required_tools"):
        lines.append(f"Required tools: {base['required_tools']}")

    if base.get("install_command"):
        lines.append(f"Install: {base['install_command']}")

    if len(matched) > 1:
        lines.append("\nAdditional reference skills (can chain/combine):")
        for s in matched[1:]:
            ref = f"  - {s.get('name', '')}: {s.get('description', '')[:60]}"
            if s.get("view_url"):
                ref += f"\n    Code: {s['view_url']}"
            lines.append(ref)

    if enhancements:
        lines.append(f"\nMyndLens enhancements to integrate: {', '.join(enhancements)}")

    lines.append("\nOutput: Generate SKILL.md with description, tools, and implementation notes.")
    return "\n".join(lines)


def _generate_skill_md(
    name: str, desc: str, risk: str, tools: str,
    enhancements: List[str], base_url: str = "", source_refs: List[Dict] = None,
) -> str:
    """Generate SKILL.md content for OC workspace. Includes source code URLs."""
    lines = [
        f"# {name}",
        f"\n**Description:** {desc}",
        f"\n**Risk Level:** {risk.upper()}",
    ]
    if tools:
        lines.append(f"\n**Required Tools:** {tools}")
    if enhancements:
        lines.append(f"\n**MyndLens Enhancements:** {', '.join(enhancements)}")
    if base_url:
        lines.append(f"\n**Base Skill Source:** {base_url}")
    if source_refs:
        lines.append("\n**Reference Skills (source code):**")
        for ref in source_refs:
            lines.append(f"  - [{ref.get('name')}]({ref.get('view_url')}) — `{ref.get('install_command', '')}`")
    lines.append("\n**Source:** Generated by MyndLens Skills Library (Spec 7)")
    return "\n".join(lines)


async def get_library_stats() -> Dict[str, Any]:
    """Get library statistics."""
    db = get_db()
    total = await db.skills_library.count_documents({})

    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}, "avg_stars": {"$avg": "$stars"}}},
        {"$sort": {"count": -1}},
    ]
    cats = await db.skills_library.aggregate(pipeline).to_list(20)

    return {
        "total_skills": total,
        "categories": [{"name": c["_id"], "count": c["count"], "avg_stars": round(c.get("avg_stars", 0), 1)} for c in cats],
        "indexed": _indexed,
    }
