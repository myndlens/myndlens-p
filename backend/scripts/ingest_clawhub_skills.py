"""
ClawHub Skills Ingester — parse all skill ZIPs and upsert into MongoDB skills_library.

For each skill directory in SKILLS_DIR:
  - Parse SKILL.md (YAML frontmatter + instruction body)
  - Parse _meta.json (version, author, category)
  - Read any scripts/ and references/ files
  - Map to skills_library schema
  - Upsert into MongoDB (slug as unique key)

Run: cd /app/backend && python scripts/ingest_clawhub_skills.py
"""
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import get_db
from skills.library import classify_risk

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("ingester")

SKILLS_DIR = Path("/tmp/clawhub_skills")

# Map OpenClaw tool groups from env/bin requirements
_ENV_TO_OC_TOOLS = {
    "MATON_API_KEY":         ["group:messaging"],
    "GMAIL":                  ["group:messaging"],
    "GOG_ACCOUNT":            ["group:messaging"],
    "SLACK_BOT_TOKEN":        ["group:messaging"],
    "DISCORD_TOKEN":          ["group:messaging"],
    "HA_TOKEN":               ["group:runtime"],
    "GEMINI_API_KEY":         ["group:runtime"],
    "OPENAI_API_KEY":         ["group:runtime"],
    "TAVILY_API_KEY":         ["group:web"],
    "BRAVE_API_KEY":          ["group:web"],
    "PEXELS_API_KEY":         ["group:web"],
    "FORESEEK_API_KEY":       ["group:runtime"],
    "TWILIO_ACCOUNT_SID":     ["group:messaging"],
    "UPLOAD_POST_API_KEY":    ["group:messaging"],
    "POST_BRIDGE_API_KEY":    ["group:messaging"],
    "AISA_API_KEY":           ["group:web"],
    "CAMINO_API_KEY":         ["group:web"],
    "STRIPE_SECRET_KEY":      ["group:runtime"],
    "PINGHUMAN_API_KEY":      ["group:messaging"],
    "FORESEEK_API_KEY":       ["group:web"],
}

_BIN_TO_OC_TOOLS = {
    "jq":       [],
    "curl":     ["web_fetch"],
    "ffmpeg":   ["exec"],
    "whisper":  ["exec"],
    "node":     ["exec"],
    "python3":  ["exec"],
    "uv":       ["exec"],
    "gh":       ["exec"],
    "himalaya": ["exec"],
}

_CATEGORY_OC_PROFILE = {
    "communication":  "messaging",
    "email":          "messaging",
    "messaging":      "messaging",
    "social":         "messaging",
    "scheduling":     "messaging",
    "finance":        "coding",
    "productivity":   "coding",
    "coding":         "coding",
    "development":    "coding",
    "search":         "coding",
    "web":            "coding",
    "monitoring":     "coding",
    "security":       "coding",
    "agent":          "full",
    "infrastructure": "full",
    "media":          "coding",
    "education":      "coding",
    "healthcare":     "coding",
    "smart-home":     "coding",
    "marketing":      "messaging",
}


def parse_yaml_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from SKILL.md content."""
    frontmatter = {}
    body = text

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml  # type: ignore
                frontmatter = yaml.safe_load(parts[1]) or {}
            except Exception:
                # Parse manually for simple key:value
                for line in parts[1].strip().splitlines():
                    if ":" in line:
                        k, _, v = line.partition(":")
                        frontmatter[k.strip()] = v.strip().strip('"').strip("'")
            body = parts[2].strip()

    return frontmatter, body


def extract_requires(frontmatter: dict) -> tuple[list[str], list[str]]:
    """Extract required env vars and binaries from frontmatter."""
    requires = {}
    # Check multiple frontmatter formats
    for key in ("metadata", "clawdbot", "openclaw"):
        val = frontmatter.get(key, {})
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                continue
        if isinstance(val, dict):
            requires = val.get("requires", val.get("clawdbot", {}).get("requires", {}))
            if requires:
                break

    # Also check top-level
    if not requires:
        for key in ("requires", "env", "bins"):
            if key in frontmatter:
                requires = frontmatter
                break

    env_vars = []
    bins = []

    if isinstance(requires, dict):
        env_raw = requires.get("env", [])
        bins_raw = requires.get("bins", requires.get("binaries", []))
        if isinstance(env_raw, list):
            env_vars = [str(e) for e in env_raw]
        if isinstance(bins_raw, list):
            bins = [str(b) for b in bins_raw]

    # Also scan body for env var patterns like $MATON_API_KEY
    return env_vars, bins


def infer_env_from_body(body: str) -> list[str]:
    """Scan SKILL.md body for referenced environment variables."""
    return list(set(re.findall(r'\b([A-Z][A-Z0-9_]{3,}_(?:API_KEY|TOKEN|SECRET|KEY|ID|URL|ACCOUNT))\b', body)))


def build_oc_tools(env_vars: list, bins: list, category: str) -> dict:
    """Map to OpenClaw tool policy."""
    allow = set()
    for env in env_vars:
        allow.update(_ENV_TO_OC_TOOLS.get(env, []))
    for b in bins:
        allow.update(_BIN_TO_OC_TOOLS.get(b, []))
    if "curl" in bins or "web_fetch" in str(allow):
        allow.add("web_fetch")

    profile = _CATEGORY_OC_PROFILE.get(category.lower(), "coding")
    return {"profile": profile, "allow": sorted(allow) if allow else [f"group:{profile}"]}


def read_support_files(skill_dir: Path) -> dict[str, str]:
    """Read scripts/ and references/ content."""
    support: dict[str, str] = {}
    for subdir in ("scripts", "references", "config", "execution", "templates"):
        d = skill_dir / subdir
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.is_file() and f.suffix in (".py", ".js", ".sh", ".md", ".yaml", ".json", ".txt"):
                    try:
                        support[f"{subdir}/{f.name}"] = f.read_text(errors="replace")[:8000]
                    except Exception:
                        pass
    return support


def parse_skill_dir(skill_dir: Path) -> dict[str, Any] | None:
    """Parse one skill directory into a MongoDB document."""
    skill_name = skill_dir.name

    # Find SKILL.md
    skill_md_path = None
    for candidate in skill_dir.rglob("SKILL.md"):
        skill_md_path = candidate
        break

    if not skill_md_path:
        logger.warning("  No SKILL.md in %s — skipping", skill_name)
        return None

    skill_md_raw = skill_md_path.read_text(errors="replace")
    frontmatter, body = parse_yaml_frontmatter(skill_md_raw)

    # Parse _meta.json
    meta = {}
    for meta_path in skill_dir.rglob("_meta.json"):
        try:
            meta = json.loads(meta_path.read_text())
            break
        except Exception:
            pass

    # Extract fields
    name = (frontmatter.get("name") or meta.get("name") or skill_name).strip()
    slug = (meta.get("slug") or frontmatter.get("slug") or name.lower().replace(" ", "-")).strip()
    description = (frontmatter.get("description") or meta.get("description") or body[:200]).strip().replace("\n", " ")
    version = (meta.get("version") or frontmatter.get("version") or "1.0.0").strip()
    author = (meta.get("author") or frontmatter.get("author") or "").strip()
    homepage = (meta.get("homepage") or frontmatter.get("homepage") or "").strip()
    stars = int(meta.get("stars", 0) or 0)

    # Category
    category = (
        meta.get("category") or
        frontmatter.get("category") or
        (frontmatter.get("metadata", {}) or {}).get("category") if isinstance(frontmatter.get("metadata"), dict) else None or
        "general"
    )
    if not isinstance(category, str):
        category = "general"
    category = category.lower().replace("_", "-")

    # Required env / bins
    env_vars, bins = extract_requires(frontmatter)
    # Also scan body for env patterns
    body_env = infer_env_from_body(skill_md_raw)
    all_env = sorted(set(env_vars + body_env))

    # Risk
    risk = classify_risk(description, " ".join(all_env))

    # OpenClaw tool mapping
    oc_tools = build_oc_tools(all_env, bins, category)

    # Install command
    install_command = f"clawdhub install {slug}"

    # Support files
    support = read_support_files(skill_dir)

    # ClawHub API URL
    clawhub_api_url = f"https://clawhub.ai/api/v1/skills/{slug}"
    view_url = f"https://clawhub.ai/skills/{slug}"

    return {
        "slug": slug,
        "name": name,
        "description": description,
        "version": version,
        "author": author,
        "homepage": homepage,
        "category": category,
        "skill_md": skill_md_raw,            # Full SKILL.md — sent to ObeGee in mandate
        "skill_md_body": body,               # Just the instruction body (no frontmatter)
        "required_env": all_env,
        "required_bins": bins,
        "oc_tools": oc_tools,
        "install_command": install_command,
        "clawhub_api_url": clawhub_api_url,
        "view_url": view_url,
        "stars": stars,
        "risk": risk,
        "relevance_modifier": 1.0,
        "support_files": support,
        "source": "clawhub_zip",
        "ingested_at": datetime.now(timezone.utc),
        # Search text for MongoDB text index
        "search_text": f"{name} {description} {category} {' '.join(all_env)} {body[:500]}".lower(),
    }


async def ingest_all():
    db = get_db()
    skills_dirs = sorted([d for d in SKILLS_DIR.iterdir() if d.is_dir()])

    # Deduplicate by slug — keep first encountered (newest/clean copy)
    seen_slugs: set[str] = set()
    inserted = updated = skipped = errors = 0

    for skill_dir in skills_dirs:
        try:
            doc = parse_skill_dir(skill_dir)
            if doc is None:
                skipped += 1
                continue

            slug = doc["slug"]
            if slug in seen_slugs:
                logger.info("  SKIP DUPLICATE: %s (%s)", skill_dir.name, slug)
                skipped += 1
                continue
            seen_slugs.add(slug)

            existing = await db.skills_library.find_one({"slug": slug}, {"_id": 0, "slug": 1})
            if existing:
                await db.skills_library.update_one(
                    {"slug": slug},
                    {"$set": {**doc, "ingested_at": datetime.now(timezone.utc)}},
                )
                logger.info("  UPDATED: %-35s  v%-8s  risk=%-6s  env=%d",
                            slug, doc["version"], doc["risk"], len(doc["required_env"]))
                updated += 1
            else:
                await db.skills_library.insert_one(doc)
                logger.info("  INSERTED: %-34s  v%-8s  risk=%-6s  env=%d",
                            slug, doc["version"], doc["risk"], len(doc["required_env"]))
                inserted += 1

        except Exception as e:
            logger.error("  ERROR: %s — %s", skill_dir.name, str(e))
            errors += 1

    # Ensure indexes
    await db.skills_library.create_index("slug", unique=True)
    await db.skills_library.create_index([("search_text", "text")])
    await db.skills_library.create_index("category")
    await db.skills_library.create_index("risk")

    total = await db.skills_library.count_documents({})
    logger.info("")
    logger.info("=== Ingestion complete ===")
    logger.info("  Inserted:  %d", inserted)
    logger.info("  Updated:   %d", updated)
    logger.info("  Skipped:   %d (duplicates + no SKILL.md)", skipped)
    logger.info("  Errors:    %d", errors)
    logger.info("  Total in library: %d", total)


if __name__ == "__main__":
    asyncio.run(ingest_all())
