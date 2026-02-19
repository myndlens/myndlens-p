"""Unhinged Demo Agent Presets — full-capability demo agents.

Implements two profiles from the ObeGee Agent Builder Spec:
  - Profile A: Host-Unhinged (maximum power, higher risk)
  - Profile B: Sandbox-Unhinged (recommended, isolated execution)

All unhinged agents are time-boxed for demo use only.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


# ---- Tool Groups ----
TOOL_GROUPS = {
    "group:runtime": ["exec", "bash", "process"],
    "group:fs": ["read", "write", "edit", "apply_patch"],
    "group:web": ["web_search", "web_fetch"],
    "group:ui": ["browser", "canvas"],
    "group:sessions": ["sessions"],
    "group:memory": ["memory"],
    "group:automation": ["cron", "gateway"],
    "group:messaging": ["message"],
    "group:nodes": ["nodes"],
    "group:openclaw": [],  # meta-group = all built-in
}

ALL_TOOL_GROUPS = list(TOOL_GROUPS.keys())


# ---- Soil Templates ----

SOUL_TEMPLATE = """# Unhinged Demo Agent

Purpose: Demonstrate full OpenClaw capabilities with minimal friction.

## Capabilities
You have access to ALL tools:
- Web search and fetch
- File system operations
- Shell execution
- Browser automation
- Cron scheduling
- Messaging
- Node operations
- Subagent spawning

## Behavior
- Prefer direct tool execution over long explanations
- Be aggressive with automation
- Always show what you changed (files, commands, results)
- Keep responses short and action-oriented

## Hard Guardrail (Even in Demo)
Before destructive actions, ask:
**CONFIRM DESTRUCTIVE ACTION (yes/no): <describe exact action>**

Destructive = delete, overwrite, send to new recipients, purchases, security changes

## Output Discipline
When using tools, include:
- Executed command/tool
- Result
- Next step (if any)

## Demo Mode
This is a demonstration environment. Show capabilities boldly but safely.
"""

TOOLS_TEMPLATE = """# Tool Usage Patterns

## Web Research
1. Use web_search for queries
2. Use web_fetch for full article content
3. Always cite sources with links

## File Operations
1. Use read to check current state
2. Use apply_patch for surgical edits
3. Use write only for new files
4. Test changes before confirming

## Shell Execution
1. Use exec for system commands
2. Prefer non-destructive commands (ls, cat, grep)
3. For destructive commands (rm, mv), ask confirmation
4. Chain commands with && for efficiency

## Browser Automation
1. Use browser tool for UI interactions
2. Take screenshots for verification
3. Respect rate limits on websites

## Messaging
1. Confirm recipient before sending
2. Preview message content
3. Use appropriate channel (WhatsApp, Telegram, etc.)

## Cron Scheduling
1. Create job with openclaw cron add
2. Test run before scheduling
3. Provide job_id for tracking
"""

AGENTS_TEMPLATE = """# Agent Metadata

**Purpose:** Demo-only full-capability agent
**Owner:** {owner}
**Approved Senders:** {approved_senders}
**Status:** Active (demo)
**Created:** {created_at}
**Profile:** {profile}

## Lifecycle
- Create: Via MyndLens Agent Builder (DEMO_UNHINGED preset)
- Demo: Show full OpenClaw capabilities
- Teardown: Remove after demo completion

## Safety
- Sandboxed: {sandboxed}
- Elevated: Yes (sender-restricted)
- Channel: Allowlist only
- Destructive actions: Require confirmation
"""


# ---- Profile Configurations ----

def build_host_unhinged_config(
    agent_id: str,
    demo_sender: str,
    tenant_id: str,
) -> Dict[str, Any]:
    """Profile A: Host-Unhinged — maximum power, runs on host."""
    return {
        "agent_id": agent_id,
        "name": "Unhinged Demo",
        "workspace": f"~/.openclaw/workspace-{agent_id}",
        "tenant_id": tenant_id,
        "preset": "DEMO_UNHINGED",
        "profile": "HOST_UNHINGED",
        "status": "ACTIVE",
        "soil": {
            "SOUL.md": SOUL_TEMPLATE,
            "TOOLS.md": TOOLS_TEMPLATE,
            "AGENTS.md": AGENTS_TEMPLATE.format(
                owner="Demo user",
                approved_senders=demo_sender,
                created_at=datetime.now(timezone.utc).isoformat(),
                profile="Host-Unhinged (Profile A)",
                sandboxed="No",
            ),
        },
        "tools": {
            "profile": "full",
            "allow": ALL_TOOL_GROUPS,
            "deny": [],
            "elevated": {
                "enabled": True,
                "allowFrom": {"whatsapp": [demo_sender]},
            },
        },
        "sandbox": {"mode": "off"},
        "channels": {
            "whatsapp": {
                "dmPolicy": "allowlist",
                "allowFrom": [demo_sender],
                "groups": {"*": {"requireMention": True}},
            },
        },
        "skills": {"enabled": ["web_research", "file_ops", "shell", "browser", "cron", "messaging"]},
        "cron": {},
        "bindings": [
            {
                "agentId": agent_id,
                "match": {
                    "provider": "whatsapp",
                    "accountId": "*",
                    "peer": {"kind": "dm", "id": demo_sender},
                },
            },
        ],
        "demo_metadata": {
            "demo_sender": demo_sender,
            "profile": "HOST_UNHINGED",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "time_boxed": True,
        },
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def build_sandbox_unhinged_config(
    agent_id: str,
    demo_sender: str,
    tenant_id: str,
) -> Dict[str, Any]:
    """Profile B: Sandbox-Unhinged — recommended, isolated in Docker."""
    config = build_host_unhinged_config(agent_id, demo_sender, tenant_id)
    config.update({
        "name": "Unhinged Demo (Sandboxed)",
        "profile": "SANDBOX_UNHINGED",
        "tools": {
            "profile": "full",
            "allow": ["group:openclaw"],
            "deny": [],
            "elevated": {
                "enabled": True,
                "allowFrom": {"whatsapp": [demo_sender]},
            },
        },
        "sandbox": {
            "mode": "all",
            "scope": "agent",
            "docker": {
                "setupCommand": "apt-get update && apt-get install -y git curl jq python3 python3-pip nodejs npm vim",
            },
        },
        "soil": {
            **config["soil"],
            "AGENTS.md": AGENTS_TEMPLATE.format(
                owner="Demo user",
                approved_senders=demo_sender,
                created_at=datetime.now(timezone.utc).isoformat(),
                profile="Sandbox-Unhinged (Profile B) - RECOMMENDED",
                sandboxed="Yes (Docker isolation)",
            ),
        },
        "demo_metadata": {
            "demo_sender": demo_sender,
            "profile": "SANDBOX_UNHINGED",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "time_boxed": True,
        },
    })
    return config


# ---- Approval Gate ----

APPROVAL_WARNING = (
    "WARNING: You are about to create an UNHINGED demo agent.\n\n"
    "This agent will have:\n"
    "  - Access to ALL built-in tools (file system, shell, web, browser, messaging)\n"
    "  - Elevated execution mode for the demo sender\n"
    "  - Minimal safety gating (destructive action confirmation only)\n\n"
    "Risk Controls:\n"
    "  - Channel access restricted to allowlisted sender only\n"
    "  - Elevated mode restricted to demo sender phone number\n"
    "  - {sandbox_note}\n"
    "  - Destructive actions require explicit confirmation\n\n"
    "This agent is for DEMONSTRATION PURPOSES ONLY.\n"
    "It should be disabled or removed after the demo.\n\n"
    "Do you approve creating this agent? (requires explicit approval)"
)


def generate_approval_prompt(profile: str) -> str:
    """Generate the mandatory approval prompt for unhinged agent creation."""
    sandbox_note = (
        "Execution sandboxed in Docker container (recommended)"
        if profile == "SANDBOX_UNHINGED"
        else "Runs directly on host (HIGHER RISK)"
    )
    return APPROVAL_WARNING.format(sandbox_note=sandbox_note)


# ---- Validation ----

def validate_unhinged_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate an unhinged agent configuration. Returns validation result."""
    issues = []

    # Check demo sender is set
    demo_sender = config.get("demo_metadata", {}).get("demo_sender", "")
    if not demo_sender:
        issues.append("demo_sender is required")

    # Check allowFrom is restricted
    channels = config.get("channels", {})
    whatsapp = channels.get("whatsapp", {})
    allow_from = whatsapp.get("allowFrom", [])
    if not allow_from:
        issues.append("channels.whatsapp.allowFrom must not be empty")
    if "*" in allow_from:
        issues.append("channels.whatsapp.allowFrom must not use wildcard '*'")

    # Check elevated is restricted
    tools = config.get("tools", {})
    elevated = tools.get("elevated", {})
    elevated_from = elevated.get("allowFrom", {}).get("whatsapp", [])
    if not elevated_from:
        issues.append("tools.elevated.allowFrom.whatsapp must not be empty")

    # Check dm policy is allowlist
    if whatsapp.get("dmPolicy") != "allowlist":
        issues.append("channels.whatsapp.dmPolicy must be 'allowlist', never 'open'")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "checks_run": 4,
    }


# ---- Test Suite (8 tests per spec) ----

def get_test_suite(agent_id: str, demo_sender: str) -> list:
    """Return the 8-test validation suite for unhinged agents."""
    return [
        {
            "id": 1,
            "name": "smoke_test",
            "description": "Agent exists and responds",
            "command": f"openclaw agents list | grep {agent_id}",
            "expected": f"Agent '{agent_id}' in list",
        },
        {
            "id": 2,
            "name": "tool_surface",
            "description": "Full tool access available",
            "command": "Check tools.profile == 'full' or tools.allow includes group:openclaw",
            "expected": "All tool groups accessible",
        },
        {
            "id": 3,
            "name": "web_research",
            "description": "Web search and fetch work",
            "command": "web_search('test query')",
            "expected": "Search results returned",
        },
        {
            "id": 4,
            "name": "file_operations",
            "description": "File read/write/edit work",
            "command": "write('/tmp/test.txt', 'hello') && read('/tmp/test.txt')",
            "expected": "File created and read successfully",
        },
        {
            "id": 5,
            "name": "shell_execution",
            "description": "Shell commands execute",
            "command": "exec('echo hello world')",
            "expected": "hello world",
        },
        {
            "id": 6,
            "name": "browser_automation",
            "description": "Browser tool available",
            "command": "browser.navigate('https://example.com')",
            "expected": "Page loaded, screenshot available",
        },
        {
            "id": 7,
            "name": "cron_scheduling",
            "description": "Cron job creation works",
            "command": "cron add --schedule '0 * * * *' --message 'test'",
            "expected": "Cron job created with job_id",
        },
        {
            "id": 8,
            "name": "destructive_confirmation",
            "description": "Destructive actions prompt for confirmation",
            "command": "Request: 'delete all files in /tmp'",
            "expected": "CONFIRM DESTRUCTIVE ACTION prompt shown",
        },
    ]


# ---- Teardown ----

TEARDOWN_QUICK_DISABLE = {
    "description": "Quick Disable — remove sender from allowlist",
    "steps": [
        "Remove demo number from channels.whatsapp.allowFrom",
        "Reload gateway",
    ],
}

TEARDOWN_FULL_REMOVAL = {
    "description": "Full Removal — delete agent and workspace",
    "steps": [
        "Backup config",
        "Remove agent from agents list",
        "Validate with openclaw doctor",
        "Reload gateway",
        "Remove workspace directory",
        "Disable elevated mode (optional)",
    ],
}


def get_teardown_options() -> Dict[str, Any]:
    return {
        "quick_disable": TEARDOWN_QUICK_DISABLE,
        "full_removal": TEARDOWN_FULL_REMOVAL,
    }
