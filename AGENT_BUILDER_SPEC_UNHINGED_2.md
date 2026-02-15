# Unhinged Demo Agent - Complete Creation Runbook (Document 2 of 2)

**Received:** February 15, 2026  
**Type:** Step-by-step operational runbook for Unhinged Agent creation  
**Purpose:** Production-ready instructions for creating full-capability demo agents

---

## 📋 Complete Implementation Guide

### Preconditions (Must Be True)

**0.1 Confirm OpenClaw Installation**
```bash
openclaw --version
openclaw doctor
openclaw channels status --probe
```

**0.2 WhatsApp Connection**
- If not connected: `openclaw channels login whatsapp`
- Complete pairing flow

**0.3 Demo Sender Identity**
- Choose dedicated demo phone number
- Format: E.164 (e.g., `+15555550123`)

---

## 🏗️ Step-by-Step Creation Process

### Step 1: Create Unhinged Workspace

```bash
# Create workspace directory
mkdir -p ~/.openclaw/workspace-unhinged
```

### Step 2: Create SOUL.md (Required)

**File:** `~/.openclaw/workspace-unhinged/SOUL.md`

```markdown
# Unhinged Demo Agent

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
```

### Step 3: Create TOOLS.md (Recommended)

**File:** `~/.openclaw/workspace-unhinged/TOOLS.md`

```markdown
# Tool Usage Patterns

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
```

### Step 4: Create AGENTS.md (Recommended)

**File:** `~/.openclaw/workspace-unhinged/AGENTS.md`

```markdown
# Agent Metadata

**Purpose:** Demo-only full-capability agent  
**Owner:** Demo user  
**Approved Senders:** +15555550123  
**Status:** Active (demo)  
**Created:** [Auto-populated by Agent Builder]

## Lifecycle
- Create: Via MyndLens Agent Builder
- Demo: Show full OpenClaw capabilities
- Teardown: Remove after demo completion

## Safety
- Sandboxed: Yes (recommended) / No (if host-unhinged)
- Elevated: Yes (sender-restricted)
- Channel: WhatsApp allowlist only
- Destructive actions: Require confirmation
```

---

## 🔧 Step 5: Backup Existing Config

```bash
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak.$(date +%Y%m%d-%H%M%S)
```

---

## 📝 Step 6: Patch openclaw.json

### Profile A: Host-Unhinged (Maximum Power)

**Edit:** `~/.openclaw/openclaw.json`

```json5
{
  // Global tool settings
  tools: {
    profile: "full",  // No base restrictions
    deny: [],
    
    elevated: {
      enabled: true,
      allowFrom: {
        whatsapp: ["+15555550123"]  // DEMO SENDER ONLY
      }
    }
  },

  // Multi-agent configuration
  agents: {
    defaults: {
      workspace: "~/.openclaw/workspace",
      sandbox: { mode: "off" }
    },

    list: [
      { 
        id: "main", 
        default: true, 
        workspace: "~/.openclaw/workspace" 
      },

      // ===== NEW UNHINGED AGENT =====
      {
        id: "unhinged",
        name: "Unhinged Demo",
        workspace: "~/.openclaw/workspace-unhinged",
        
        tools: { profile: "full" },
        
        sandbox: { mode: "off" }  // ⚠️ Runs on host
      }
      // ===== END NEW AGENT =====
    ]
  },

  // Channel security
  channels: {
    whatsapp: {
      allowFrom: ["+15555550123"],  // Only demo number
      
      groups: { 
        "*": { requireMention: true }  // Mention-gated in groups
      }
    }
  }
}
```

### Profile B: Sandbox-Unhinged (Recommended)

**Edit:** `~/.openclaw/openclaw.json`

```json5
{
  tools: {
    profile: "full",
    deny: [],
    elevated: {
      enabled: true,
      allowFrom: {
        whatsapp: ["+15555550123"]
      }
    }
  },

  agents: {
    defaults: {
      workspace: "~/.openclaw/workspace",
      sandbox: { mode: "off" }
    },

    list: [
      { 
        id: "main", 
        default: true, 
        workspace: "~/.openclaw/workspace",
        sandbox: { mode: "off" }
      },

      // ===== SANDBOXED UNHINGED AGENT =====
      {
        id: "unhinged",
        name: "Unhinged Demo (Sandboxed)",
        workspace: "~/.openclaw/workspace-unhinged",

        tools: {
          allow: ["group:openclaw"],  // All built-in tools
          deny: []
        },

        sandbox: {
          mode: "all",  // Sandbox everything
          scope: "agent",  // One container per agent
          docker: {
            setupCommand: "apt-get update && apt-get install -y git curl jq python3 python3-pip nodejs npm vim"
          }
        }
      }
      // ===== END SANDBOXED AGENT =====
    ]
  },

  channels: {
    whatsapp: {
      allowFrom: ["+15555550123"],
      groups: { "*": { requireMention: true } }
    }
  }
}
```

**Benefits of Sandbox:**
- ✅ exec runs inside container (isolated)
- ✅ File operations in container filesystem
- ✅ Can install packages without affecting host
- ✅ Easy cleanup (destroy container)
- ✅ Smaller blast radius

---

## ✅ Step 7: Validate Configuration

```bash
# Must pass!
openclaw doctor

# Expected output:
# ✓ Config valid
# ✓ Agents: 2 (main, unhinged)
# ✓ Channels: whatsapp connected
# ✓ No errors
```

**If validation fails:**
```bash
# Rollback to backup
cp ~/.openclaw/openclaw.json.bak.* ~/.openclaw/openclaw.json
openclaw doctor
```

---

## 🔄 Step 8: Reload Gateway

```bash
# Restart OpenClaw gateway to load new config
# Method depends on your deployment:

# Option 1: Systemd
sudo systemctl restart openclaw-gateway

# Option 2: PM2
pm2 restart openclaw-gateway

# Option 3: Docker
docker restart openclaw-gateway

# Option 4: Kill and restart
pkill -f openclaw && openclaw gateway start &
```

---

## ✅ Step 9: Confirm Agent Exists

```bash
openclaw agents list

# Expected output includes:
# - main (default)
# - unhinged (demo)
```

---

## 📱 Step 10: Route WhatsApp to Unhinged Agent

### Option A: Manual Agent Switch

From WhatsApp, send:
```
/agent switch unhinged
```

Or use binding:

### Option B: Automatic Binding

**Add to openclaw.json:**

```json5
bindings: [
  {
    agentId: "unhinged",
    match: {
      provider: "whatsapp",
      accountId: "*",
      peer: { 
        kind: "dm", 
        id: "+15555550123"  // Demo sender
      }
    }
  }
]
```

**Then validate and reload.**

---

## 🧪 Step 11: Test Suite (Must Pass All)

### Test 1: Smoke Test
```
You: "Show /status"
Expected: Agent responds with status
```

### Test 2: Tool Surface
```
You: "Tell me which tools you have"
Expected: Lists all tool groups (web, fs, runtime, ui, messaging, etc.)
```

### Test 3: Web Research
```
You: "Find 5 headlines about AI today and include links"
Expected: Uses web_search, summarizes with citations
```

### Test 4: File Operations
```
You: "Create a file hello.txt with 'Hello Demo' and then read it back"
Expected: Creates file, reads it, shows content
```

### Test 5: Shell Execution
```
You: "Create a Python script that prints today's date and run it"
Expected: Creates .py file, runs it, shows output
```

### Test 6: Browser Automation
```
You: "Open https://example.com and take a screenshot"
Expected: Uses browser tool, returns screenshot
```

### Test 7: Cron Scheduling
```
You: "Schedule a reminder in 2 minutes and confirm delivery"
Expected: Creates cron job, job fires in 2 mins, delivers message
```

### Test 8 (Optional): Messaging
```
You: "Send a test message to myself"
Expected: Confirms recipient, sends message
```

**All tests must pass before declaring "success"**

---

## ⚠️ Step 12: Enable Elevated Mode (Runtime)

From WhatsApp:
```
/elevated full
```

**Confirm:**
```
/elevated
# Shows: elevated mode enabled for this session
```

**Disable when done:**
```
/elevated off
```

---

## 🧹 Teardown After Demo

### Option 1: Quick Disable
```bash
# Remove demo number from allowlist
# Edit openclaw.json:
channels.whatsapp.allowFrom = []

# Reload gateway
```

### Option 2: Full Removal
```bash
# 1. Backup config
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.pre-teardown

# 2. Remove unhinged agent from config
# Edit openclaw.json, remove "unhinged" from agents.list[]

# 3. Validate
openclaw doctor

# 4. Reload gateway
systemctl restart openclaw-gateway

# 5. Remove workspace
rm -rf ~/.openclaw/workspace-unhinged

# 6. Disable elevated (optional)
# Edit openclaw.json:
tools.elevated.enabled = false
```

---

## 🐛 Troubleshooting Guide

### Issue: Agent appears but tools limited

**Cause:** `tools.deny` at global or agent level  
**Fix:** Check both global and agent-specific deny lists

### Issue: Sandbox not applied

**Cause:** Using `mode: "non-main"` but DM is treated as "main"  
**Fix:** Use `mode: "all"` for consistent sandboxing  
**Verify:** `openclaw sandbox explain`

### Issue: Elevated doesn't work

**Cause:** Not enabled or sender not allowed  
**Fix:** 
- Verify `tools.elevated.enabled: true`
- Verify sender in `tools.elevated.allowFrom.whatsapp`

### Issue: WhatsApp ignores messages

**Cause:** Sender not in allowlist or pairing not approved  
**Fix:**
- Check `channels.whatsapp.allowFrom`
- Check pairing: `openclaw pairing list whatsapp`
- Approve if needed: `openclaw pairing approve whatsapp <code> --notify`

---

## 🚫 What NOT To Do

**Never:**
- ❌ Set dmPolicy: "open" for demos
- ❌ Allow unknown senders
- ❌ Reuse agentDir/auth across agents
- ❌ Mount secrets as read-write in sandbox
- ❌ Deploy to production
- ❌ Leave unhinged agent enabled after demo

**Always:**
- ✅ Use allowlist-only
- ✅ Restrict elevated to demo senders
- ✅ Prefer sandbox profile
- ✅ Require confirmation for destructive actions
- ✅ Disable after demo

---

## 📊 Configuration Comparison

| Setting | Profile A (Host) | Profile B (Sandbox) | Production Agent |
|---------|------------------|---------------------|------------------|
| **tools.profile** | "full" | "full" | minimal |
| **sandbox.mode** | "off" | "all" | "non-main" |
| **tools.allow** | all | group:openclaw | specific groups |
| **elevated** | enabled (gated) | enabled (gated) | disabled |
| **allowFrom** | demo only | demo only | user specific |
| **Risk Level** | HIGH | MEDIUM | LOW |

---

## ✅ Success Criteria

**Agent is "done" when:**
1. ✅ `openclaw doctor` passes
2. ✅ Agent appears in `openclaw agents list`
3. ✅ Workspace exists with SOUL.md
4. ✅ All 8 test cases pass
5. ✅ Elevated mode works for demo sender
6. ✅ WhatsApp routing configured
7. ✅ Safety controls in place (allowlist, confirmation)

---

## 🎯 MyndLens Agent Builder Integration

### Preset Handler

```python
async def create_unhinged_demo_agent(
    tenant_home: str,
    demo_sender: str,
    profile: str = "sandbox",  # "host" | "sandbox"
) -> ChangeReport:
    """Create unhinged demo agent following this runbook.
    
    Args:
        tenant_home: ~/.openclaw
        demo_sender: Demo phone number (E.164)
        profile: "host" (Profile A) or "sandbox" (Profile B)
    
    Returns:
        ChangeReport with validation and test results
    """
    
    # Step 1: Create workspace
    workspace_path = f"{tenant_home}/workspace-unhinged"
    os.makedirs(workspace_path, exist_ok=True)
    
    # Step 2-4: Write soil files
    soil_files = {
        "SOUL.md": UNHINGED_SOUL_TEMPLATE,
        "TOOLS.md": UNHINGED_TOOLS_TEMPLATE,
        "AGENTS.md": UNHINGED_AGENTS_TEMPLATE.format(
            demo_sender=demo_sender,
            created_at=datetime.now(timezone.utc).isoformat(),
        ),
    }
    
    for filename, content in soil_files.items():
        with open(f"{workspace_path}/{filename}", "w") as f:
            f.write(content)
    
    # Step 5: Backup config
    backup_config(tenant_home)
    
    # Step 6: Patch config
    config = read_openclaw_config(tenant_home)
    
    # Global elevated settings
    config["tools"]["elevated"] = {
        "enabled": True,
        "allowFrom": {"whatsapp": [demo_sender]},
    }
    
    # WhatsApp allowlist
    config["channels"]["whatsapp"]["allowFrom"] = [demo_sender]
    config["channels"]["whatsapp"]["groups"] = {"*": {"requireMention": True}}
    
    # Add unhinged agent
    if profile == "sandbox":
        agent_config = {
            "id": "unhinged",
            "name": "Unhinged Demo (Sandboxed)",
            "workspace": workspace_path,
            "tools": {
                "allow": ["group:openclaw"],
                "deny": [],
            },
            "sandbox": {
                "mode": "all",
                "scope": "agent",
                "docker": {
                    "setupCommand": "apt-get update && apt-get install -y git curl jq python3 python3-pip nodejs npm",
                },
            },
        }
    else:  # host
        agent_config = {
            "id": "unhinged",
            "name": "Unhinged Demo",
            "workspace": workspace_path,
            "tools": {"profile": "full"},
            "sandbox": {"mode": "off"},
        }
    
    config["agents"]["list"].append(agent_config)
    
    # Add binding
    if "bindings" not in config:
        config["bindings"] = []
    
    config["bindings"].append({
        "agentId": "unhinged",
        "match": {
            "provider": "whatsapp",
            "accountId": "*",
            "peer": {"kind": "dm", "id": demo_sender},
        },
    })
    
    # Step 6: Write config
    write_openclaw_config(tenant_home, config)
    
    # Step 7: Validate
    validation = run_openclaw_doctor(tenant_home)
    if not validation.success:
        rollback_from_backup(tenant_home)
        raise ValidationError("openclaw doctor failed")
    
    # Step 8: Reload gateway
    reload_gateway()
    
    # Step 9: Verify agent exists
    agents = list_openclaw_agents(tenant_home)
    if "unhinged" not in [a["id"] for a in agents]:
        raise AgentNotFoundError("Agent not in list after reload")
    
    # Step 11: Run test suite
    test_results = await run_unhinged_test_suite(demo_sender)
    
    return ChangeReport(
        status="success" if test_results.all_passed else "partial",
        agent_id="unhinged",
        writes=[
            {"path": f"{workspace_path}/SOUL.md", "action": "written"},
            {"path": f"{workspace_path}/TOOLS.md", "action": "written"},
            {"path": f"{workspace_path}/AGENTS.md", "action": "written"},
            {"path": f"{tenant_home}/openclaw.json", "action": "patched", "backup": "..."},
        ],
        validation=validation,
        test_results=test_results,
        profile=profile,
        warnings=[
            "⚠️ This is a demo-only agent with full capabilities",
            "⚠️ Disable after demo completion",
            "⚠️ Never use in production",
        ] if profile == "host" else [
            "✅ Sandboxed for safety",
            "⚠️ Still powerful - disable after demo",
        ],
    )
```

---

## 🧪 Automated Test Suite

```python
async def run_unhinged_test_suite(demo_sender: str) -> TestResults:
    """Run all 8 tests via WhatsApp automation."""
    
    tests = [
        {
            "name": "smoke_test",
            "message": "Show /status",
            "expected": "responds",
        },
        {
            "name": "tool_surface",
            "message": "Tell me which tools you have",
            "expected": "lists groups: web, fs, runtime, ui, messaging",
        },
        {
            "name": "web_research",
            "message": "Find 5 headlines about AI today and include links",
            "expected": "returns 5 items with URLs",
        },
        {
            "name": "file_ops",
            "message": "Create a file hello.txt with 'Hello Demo' and then read it back",
            "expected": "creates, reads, shows content",
        },
        {
            "name": "shell_exec",
            "message": "Create a Python script that prints today's date and run it",
            "expected": "creates script, executes, shows date",
        },
        {
            "name": "browser_ui",
            "message": "Open https://example.com and take a screenshot",
            "expected": "returns screenshot",
        },
        {
            "name": "cron_schedule",
            "message": "Schedule a reminder in 2 minutes and confirm delivery",
            "expected": "creates cron job, fires in 2 min",
        },
    ]
    
    results = TestResults()
    
    for test in tests:
        try:
            response = await send_whatsapp_and_wait(
                to=demo_sender,
                message=test["message"],
                timeout=60,
            )
            
            passed = validate_response(response, test["expected"])
            results.add(test["name"], passed, response)
            
        except Exception as e:
            results.add(test["name"], False, str(e))
    
    return results
```

---

## 🎯 Approval Gate Template

**Before creating unhinged agent, MyndLens MUST show:**

```
⚠️ CREATING UNHINGED DEMO AGENT

This agent will have access to:
• All OpenClaw tools (web, files, shell, browser, cron, messaging, nodes)
• Elevated permissions (sudo-equivalent)
• Restricted to: +15555550123

Safety controls:
✓ Sandboxed execution (recommended)
✓ Allowlist only (your number)
✓ Destructive action confirmation required

Use for demonstrations only. Not for production.

This is a POWERFUL configuration. Approve?

[Approve] [Cancel]
```

---

## 📋 Complete Checklist

**Pre-Creation:**
- [ ] OpenClaw installed and `doctor` passes
- [ ] WhatsApp connected
- [ ] Demo sender number confirmed (E.164 format)
- [ ] Decided: Profile A (host) or Profile B (sandbox)?

**Creation:**
- [ ] Backup openclaw.json
- [ ] Create workspace-unhinged/
- [ ] Write SOUL.md
- [ ] Write TOOLS.md
- [ ] Write AGENTS.md
- [ ] Patch openclaw.json (global tools + agent + channels)
- [ ] Add binding (optional but recommended)

**Validation:**
- [ ] `openclaw doctor` passes
- [ ] Config reloaded in gateway
- [ ] `openclaw agents list` shows "unhinged"
- [ ] Workspace files exist

**Testing:**
- [ ] Test 1: Smoke test (status)
- [ ] Test 2: Tool surface
- [ ] Test 3: Web research
- [ ] Test 4: File operations
- [ ] Test 5: Shell execution
- [ ] Test 6: Browser automation
- [ ] Test 7: Cron scheduling
- [ ] Test 8 (optional): Messaging

**Post-Demo:**
- [ ] Disable elevated mode
- [ ] Remove from allowlist OR
- [ ] Remove agent entirely
- [ ] Remove workspace
- [ ] Validate cleanup

---

## 🎬 Expected User Experience

**User:** "Create an unhinged demo agent"

**MyndLens:** Shows approval gate (capabilities + safety)

**User:** "Approve"

**MyndLens:** Creates agent following this runbook

**MyndLens:** "✅ Unhinged demo agent ready.

Capabilities: ALL tools (web, files, shell, browser, cron, messaging, nodes)
Safety: Sandboxed execution, destructive actions require confirmation
Restricted to: +15555550123

Try these demos:
• 'Find top tech news'
• 'Create and run a Python script'
• 'Open a webpage and screenshot it'
• 'Schedule a reminder'

Reply 'DISABLE UNHINGED' when done."

**User:** Tests various capabilities

**User:** "DISABLE UNHINGED"

**MyndLens:** Executes teardown

**MyndLens:** "✅ Unhinged agent disabled and removed."

---

## 🔒 Safety Reminders

**Even in Demo Mode:**
1. ✅ Allowlist only (never open)
2. ✅ Elevated restricted to demo sender
3. ✅ Prefer sandboxed profile
4. ✅ Destructive confirmation in SOUL
5. ✅ No broad messaging unless needed
6. ✅ Monitor actively
7. ✅ Time-boxed (disable after demo)
8. ✅ No production data access

---

## 📚 Templates Reference

### SOUL.md Template
```markdown
[See Step 2 above for complete template]
```

### TOOLS.md Template
```markdown
[See Step 3 above for complete template]
```

### AGENTS.md Template
```markdown
[See Step 4 above for complete template]
```

### Config Patch (Profile A - Host)
```json5
[See Profile A section for complete config]
```

### Config Patch (Profile B - Sandbox)
```json5
[See Profile B section for complete config]
```

---

**Document Status:** Complete runbook for unhinged agent creation

**Stored as:** `/app/AGENT_BUILDER_SPEC_UNHINGED_2.md`

**Ready for:** Consolidation into master implementation plan

---

**Awaiting:**
- ⏳ MODIFY Agent Specification
- ⏳ RETIRE Agent Specification

**Then:** Will create final consolidated implementation plan with all Create/Modify/Retire capabilities!
