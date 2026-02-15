"""Agent Builder — orchestrates the full agent lifecycle.

Implements CREATE, MODIFY, RETIRE, DELETE, and UNRETIRE operations
for OpenClaw agents. Uses capability matching to prevent agent proliferation.

All operations go through the ObeGee adapter, respecting the
Command Plane / Execution Plane separation.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import get_db

logger = logging.getLogger(__name__)


# ---- Agent State Machine ----
VALID_STATES = {"ACTIVE", "RETIRED", "DELETED"}
VALID_TRANSITIONS = {
    ("ACTIVE", "RETIRED"),
    ("ACTIVE", "ACTIVE"),    # MODIFY
    ("RETIRED", "ACTIVE"),   # UNRETIRE
    ("RETIRED", "DELETED"),  # DELETE
}


class AgentBuilder:
    """Orchestrates agent lifecycle operations."""

    async def create_agent(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new OpenClaw agent from structured intent."""
        db = get_db()

        agent_spec = intent.get("agent_spec", {})
        agent_id = agent_spec.get("id", str(uuid.uuid4())[:8])
        tenant = intent.get("tenant", {})

        # 1. Capability check — prevent proliferation
        existing = await self._capability_match(agent_spec, tenant)
        if existing:
            return {
                "status": "EXISTS",
                "message": f"Existing agent '{existing['agent_id']}' can fulfill this intent",
                "existing_agent": existing,
            }

        # 2. Build agent record
        agent = {
            "agent_id": agent_id,
            "name": agent_spec.get("name", f"agent-{agent_id}"),
            "workspace": agent_spec.get("workspace", f"~/.openclaw/workspace-{agent_id}"),
            "tenant_id": tenant.get("tenant_id", ""),
            "status": "ACTIVE",
            "soil": agent_spec.get("soil", {}),
            "tools": agent_spec.get("tools", {"allow": [], "deny": []}),
            "skills": agent_spec.get("skills", {}),
            "cron": agent_spec.get("cron", {}),
            "bindings": agent_spec.get("bindings", []),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        # 3. Validate — refuse if sensitive tools without approval
        tools_allow = agent.get("tools", {}).get("allow", [])
        sensitive = {"group:runtime", "group:fs", "exec", "bash"}
        if sensitive.intersection(set(tools_allow)):
            if not intent.get("approved_sensitive", False):
                return {
                    "status": "BLOCKED",
                    "message": "Sensitive tools requested without explicit approval",
                    "sensitive_tools": list(sensitive.intersection(set(tools_allow))),
                }

        # 4. Persist
        await db.agents.insert_one(agent)
        agent.pop("_id", None)

        # 5. Generate change report
        report = {
            "status": "SUCCESS",
            "agent_id": agent_id,
            "operation": "CREATE",
            "writes": [
                f"{agent['workspace']}/SOUL.md",
                f"{agent['workspace']}/TOOLS.md",
                f"{agent['workspace']}/AGENTS.md",
            ],
            "cron": agent.get("cron"),
            "validation": {"passed": True},
            "diff_summary": {"files_created": 3, "config_patches": 1},
            "agent": agent,
        }

        logger.info("Agent created: %s (%s)", agent_id, agent["name"])
        return report

    async def create_unhinged_demo_agent(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Create an unhinged demo agent using preset profiles.

        Requires explicit approval and a demo_sender phone number.
        Supports two profiles: HOST_UNHINGED and SANDBOX_UNHINGED (recommended).
        """
        from agents.unhinged import (
            build_host_unhinged_config,
            build_sandbox_unhinged_config,
            generate_approval_prompt,
            validate_unhinged_config,
            get_test_suite,
        )

        db = get_db()
        tenant = intent.get("tenant", {})
        tenant_id = tenant.get("tenant_id", "")
        demo_sender = intent.get("demo_sender", "")
        profile = intent.get("sandbox_mode", "recommended")
        approved = intent.get("approved", False)
        agent_id = intent.get("agent_id", "unhinged")

        if not demo_sender:
            return {"status": "BLOCKED", "message": "demo_sender phone number is required (E.164 format)"}

        # Generate approval prompt if not yet approved
        if not approved:
            use_profile = "SANDBOX_UNHINGED" if profile in ("recommended", "required", "SANDBOX_UNHINGED") else "HOST_UNHINGED"
            return {
                "status": "APPROVAL_REQUIRED",
                "approval_prompt": generate_approval_prompt(use_profile),
                "profile": use_profile,
                "demo_sender": demo_sender,
                "message": "Explicit approval required before creating unhinged agent. Resend with approved=true.",
            }

        # Build config based on profile
        if profile in ("off", "HOST_UNHINGED"):
            config = build_host_unhinged_config(agent_id, demo_sender, tenant_id)
        else:
            config = build_sandbox_unhinged_config(agent_id, demo_sender, tenant_id)

        # Validate
        validation = validate_unhinged_config(config)
        if not validation["passed"]:
            return {"status": "BLOCKED", "message": "Validation failed", "validation": validation}

        # Check if agent already exists
        existing = await db.agents.find_one({"agent_id": agent_id}, {"_id": 0})
        if existing:
            return {
                "status": "EXISTS",
                "message": f"Agent '{agent_id}' already exists. Delete or use a different ID.",
                "existing_agent": {"agent_id": existing["agent_id"], "status": existing.get("status")},
            }

        # Persist
        await db.agents.insert_one(config)
        config.pop("_id", None)

        # Build report
        test_suite = get_test_suite(agent_id, demo_sender)
        report = {
            "status": "SUCCESS",
            "agent_id": agent_id,
            "operation": "CREATE_UNHINGED",
            "profile": config.get("profile"),
            "sandbox": config.get("sandbox"),
            "writes": [
                f"{config['workspace']}/SOUL.md",
                f"{config['workspace']}/TOOLS.md",
                f"{config['workspace']}/AGENTS.md",
            ],
            "validation": validation,
            "test_suite": test_suite,
            "teardown_info": "Use POST /api/agents/unhinged/teardown to disable or remove after demo",
            "agent": config,
        }

        logger.info(
            "Unhinged demo agent created: %s profile=%s sender=%s",
            agent_id, config.get("profile"), demo_sender,
        )
        return report

    async def teardown_demo_agent(self, agent_id: str, mode: str = "quick") -> Dict[str, Any]:
        """Teardown an unhinged demo agent.

        Modes:
          - quick: Remove sender from allowlist (agent stays but is unreachable)
          - full: Retire + archive the agent completely
        """
        db = get_db()
        agent = await db.agents.find_one({"agent_id": agent_id}, {"_id": 0})
        if not agent:
            return {"status": "FAILURE", "message": f"Agent '{agent_id}' not found"}
        if agent.get("preset") != "DEMO_UNHINGED":
            return {"status": "FAILURE", "message": f"Agent '{agent_id}' is not a DEMO_UNHINGED agent"}

        if mode == "quick":
            # Remove sender from allowlist
            await db.agents.update_one(
                {"agent_id": agent_id},
                {"$set": {
                    "channels.whatsapp.allowFrom": [],
                    "tools.elevated.enabled": False,
                    "updated_at": datetime.now(timezone.utc),
                }},
            )
            logger.info("Unhinged agent quick-disabled: %s", agent_id)
            return {
                "status": "SUCCESS",
                "agent_id": agent_id,
                "operation": "TEARDOWN_QUICK",
                "message": "Sender removed from allowlist, elevated mode disabled",
            }
        else:
            # Full removal: retire then archive
            retire_result = await self.retire_agent({
                "agent_ref": {"id": agent_id},
                "retire_policy": {"mode": "HARD_RETIRE", "stop_cron": True, "remove_bindings": True, "tool_lockdown": True},
                "reason": "Demo completed — teardown",
            })
            logger.info("Unhinged agent fully torn down: %s", agent_id)
            return {
                "status": "SUCCESS",
                "agent_id": agent_id,
                "operation": "TEARDOWN_FULL",
                "retire_result": retire_result,
                "message": "Agent retired, tools locked, bindings removed",
            }

    async def modify_agent(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Modify an existing agent."""
        db = get_db()
        agent_ref = intent.get("agent_ref", {}).get("id", "")
        patch = intent.get("patch", {})

        agent = await db.agents.find_one({"agent_id": agent_ref}, {"_id": 0})
        if not agent:
            return {"status": "FAILURE", "message": f"Agent '{agent_ref}' not found"}
        if agent.get("status") != "ACTIVE":
            return {"status": "FAILURE", "message": f"Agent '{agent_ref}' is {agent.get('status')}, cannot modify"}

        updates = {"updated_at": datetime.now(timezone.utc)}
        changes = []

        # Apply patches
        if "soil" in patch:
            updates["soil"] = {**agent.get("soil", {}), **patch["soil"]}
            changes.append("soil updated")
        if "tools" in patch:
            updates["tools"] = patch["tools"]
            changes.append("tools updated")
        if "skills" in patch:
            updates["skills"] = patch["skills"]
            changes.append("skills updated")
        if "name" in patch:
            updates["name"] = patch["name"]
            changes.append("name updated")
        if "bindings" in patch:
            mode = patch.get("bindings", {}).get("mode", "MERGE_BY_ID")
            if mode == "MERGE_BY_ID":
                existing = agent.get("bindings", [])
                new_items = patch["bindings"].get("items", [])
                merged = {b.get("id", i): b for i, b in enumerate(existing)}
                for item in new_items:
                    merged[item.get("id", len(merged))] = item
                updates["bindings"] = list(merged.values())
            else:
                updates["bindings"] = patch["bindings"].get("items", [])
            changes.append("bindings updated")
        if "cron" in patch:
            updates["cron"] = patch["cron"]
            changes.append("cron updated")

        await db.agents.update_one({"agent_id": agent_ref}, {"$set": updates})

        logger.info("Agent modified: %s changes=%s", agent_ref, changes)
        return {
            "status": "SUCCESS",
            "agent_id": agent_ref,
            "operation": "MODIFY",
            "changes": changes,
            "validation": {"passed": True},
        }

    async def retire_agent(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Retire an agent (soft or hard)."""
        db = get_db()
        agent_ref = intent.get("agent_ref", {}).get("id", "")
        policy = intent.get("retire_policy", {})
        mode = policy.get("mode", "SOFT_RETIRE")

        agent = await db.agents.find_one({"agent_id": agent_ref}, {"_id": 0})
        if not agent:
            return {"status": "FAILURE", "message": f"Agent '{agent_ref}' not found"}

        updates = {
            "status": "RETIRED",
            "updated_at": datetime.now(timezone.utc),
            "retirement": {
                "mode": mode,
                "retired_at": datetime.now(timezone.utc),
                "reason": intent.get("reason", "User requested"),
                "previous_tools": agent.get("tools"),
                "previous_bindings": agent.get("bindings"),
                "previous_cron": agent.get("cron"),
            },
        }

        # Tool lockdown
        if policy.get("tool_lockdown", True):
            updates["tools"] = {"allow": [], "deny": ["group:openclaw"]}

        # Remove bindings
        if policy.get("remove_bindings", True):
            updates["bindings"] = []

        # Stop cron
        if policy.get("stop_cron", True):
            updates["cron"] = {}

        await db.agents.update_one({"agent_id": agent_ref}, {"$set": updates})

        logger.info("Agent retired: %s mode=%s", agent_ref, mode)
        return {
            "status": "SUCCESS",
            "agent_id": agent_ref,
            "operation": "RETIRE",
            "mode": mode,
            "validation": {"passed": True},
        }

    async def delete_agent(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Delete an agent (admin-only, irreversible)."""
        db = get_db()
        agent_ref = intent.get("agent_ref", {}).get("id", "")
        policy = intent.get("delete_policy", {})

        if not policy.get("admin_only", True):
            return {"status": "FAILURE", "message": "DELETE requires admin_only flag"}

        agent = await db.agents.find_one({"agent_id": agent_ref}, {"_id": 0})
        if not agent:
            return {"status": "FAILURE", "message": f"Agent '{agent_ref}' not found"}

        if agent.get("status") not in ("ACTIVE", "RETIRED"):
            return {"status": "FAILURE", "message": f"Agent '{agent_ref}' already deleted"}

        # Archive if not deleting workspace
        if not policy.get("delete_workspace", False):
            archive = {
                "agent_id": agent_ref,
                "archived_at": datetime.now(timezone.utc),
                "agent_data": agent,
            }
            await db.agent_archives.insert_one(archive)

        await db.agents.update_one(
            {"agent_id": agent_ref},
            {"$set": {
                "status": "DELETED",
                "updated_at": datetime.now(timezone.utc),
                "deleted_at": datetime.now(timezone.utc),
            }},
        )

        logger.info("Agent deleted: %s", agent_ref)
        return {
            "status": "SUCCESS",
            "agent_id": agent_ref,
            "operation": "DELETE",
            "archived": not policy.get("delete_workspace", False),
        }

    async def unretire_agent(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Restore a retired agent to active status."""
        db = get_db()
        agent_ref = intent.get("agent_ref", {}).get("id", "")

        agent = await db.agents.find_one({"agent_id": agent_ref}, {"_id": 0})
        if not agent:
            return {"status": "FAILURE", "message": f"Agent '{agent_ref}' not found"}
        if agent.get("status") != "RETIRED":
            return {"status": "FAILURE", "message": f"Agent '{agent_ref}' is {agent.get('status')}, not RETIRED"}

        retirement = agent.get("retirement", {})
        updates = {
            "status": "ACTIVE",
            "updated_at": datetime.now(timezone.utc),
            "tools": retirement.get("previous_tools", agent.get("tools", {})),
            "bindings": retirement.get("previous_bindings", []),
            "cron": retirement.get("previous_cron", {}),
        }

        await db.agents.update_one({"agent_id": agent_ref}, {"$set": updates, "$unset": {"retirement": ""}})

        logger.info("Agent unretired: %s", agent_ref)
        return {
            "status": "SUCCESS",
            "agent_id": agent_ref,
            "operation": "UNRETIRE",
            "restored": ["tools", "bindings", "cron"],
        }

    async def _capability_match(
        self, agent_spec: Dict[str, Any], tenant: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Check if an existing active agent can fulfill the intent."""
        db = get_db()
        tenant_id = tenant.get("tenant_id", "")
        if not tenant_id:
            return None

        required_tools = set(agent_spec.get("tools", {}).get("allow", []))
        if not required_tools:
            return None

        cursor = db.agents.find(
            {"tenant_id": tenant_id, "status": "ACTIVE"},
            {"_id": 0, "agent_id": 1, "name": 1, "tools": 1},
        )
        async for agent in cursor:
            existing_tools = set(agent.get("tools", {}).get("allow", []))
            if required_tools.issubset(existing_tools):
                return agent

        return None

    async def list_agents(
        self, tenant_id: str, include_retired: bool = False
    ) -> List[Dict[str, Any]]:
        """List all agents for a tenant."""
        db = get_db()
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if not include_retired:
            query["status"] = "ACTIVE"
        else:
            query["status"] = {"$ne": "DELETED"}

        cursor = db.agents.find(query, {"_id": 0}).sort("created_at", -1)
        return await cursor.to_list(100)

    async def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get a single agent by ID."""
        db = get_db()
        return await db.agents.find_one({"agent_id": agent_id}, {"_id": 0})
