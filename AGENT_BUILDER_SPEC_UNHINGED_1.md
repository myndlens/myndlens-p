# Agent Builder Specification - Unhinged Agents (Demo Only)

**Received:** February 15, 2026  
**Type:** CREATE Unhinged OpenClaw Agents (Full-Access Demo Profile)  
**Status:** Document 1 of 2 for Unhinged Agents  
**Purpose:** Controlled demo with minimal friction, maximum capability

---

## 🎯 Core Concept

**"Unhinged" = Full Toolset + Elevated Mode + Minimal Gating**

**Two Options:**
- **Option A:** Truly unhinged on host (max capability, max risk)
- **Option B:** Unhinged in sandbox (recommended for demos)

---

## 🔧 Key Design Choices

### 1. Tool Profile
- Use `tools.profile: "full"` (no base restrictions)
- Do NOT set `tools.allow` (avoid accidental restriction)
- Empty `tools.deny` for true unhinged mode

### 2. Elevated Mode
- Global elevated baseline (`tools.elevated`)
- Sender-based authentication
- Elevated enabled: true
- Elevated allowed ONLY for demo sender(s)

### 3. Channel Access
- WhatsApp: `dmPolicy: "allowlist"`
- Only demo phone number(s) in `allowFrom`
- Prevents unauthorized access

### 4. Sandbox
- Prefer sandboxed unhinged (Option B)
- Gives power without host-level risk
- Docker container isolation

---

## 📋 Tool Set ("Can Do Everything")

**OpenClaw Built-in Tool Groups:**
- `group:runtime` → exec, bash, process
- `group:fs` → read, write, edit, apply_patch
- `group:web` → web_search, web_fetch
- `group:ui` → browser, canvas
- `group:sessions` → sessions management
- `group:memory` → memory operations
- `group:automation` → cron, gateway
- `group:messaging` → message
- `group:nodes` → nodes
- `group:openclaw` → ALL built-in tools

**Unhinged Target:** All built-in tools + enabled plugins

---

## 🔐 Critical Channel vs Tool Distinction

### How Messaging Actually Works

**NOT:** "WhatsApp tool" (doesn't exist)

**ACTUALLY:**
- Tool: `message` (generic messaging capability)
- Channel: `whatsapp` (delivery adapter)
- Target: Phone number

**Applies to:** WhatsApp, Telegram, Slack, Discord, Teams, Signal, iMessage

**NOT Supported:** LinkedIn (not a messaging channel)

### When to Enable `message` Tool

**Scheduled Delivery (e.g., daily news):**
- ❌ Do NOT enable `message` tool
- ✅ Use `cron announce --channel <channel>`

**Ad-hoc Proactive Messaging:**
- Requires explicit approval
- Then enable `group:messaging` or `message` tool
- Security constrained by active session

---

## 🏗️ Option A: Truly Unhinged on Host

### Configuration

```json5
// ~/.openclaw/openclaw.json
{
  tools: {
    profile: "full",
    deny: [],
    elevated: {
      enabled: true,
      allowFrom: ["+15555550123"],  // DEMO ONLY
    },
  },

  agents: {
    defaults: {
      workspace: "~/.openclaw/workspace",
      sandbox: { mode: "off" },
    },
    list: [
      { 
        id: "main", 
        default: true, 
        name: "Personal", 
        workspace: "~/.openclaw/workspace" 
      },
      {
        id: "unhinged",
        name: "Unhinged Demo",
        workspace: "~/.openclaw/workspace-unhinged",
        sandbox: { mode: "off" },  // ⚠️ Runs on host
      }
    ],
  },

  channels: {
    whatsapp: {
      dmPolicy: "allowlist",
      allowFrom: ["+15555550123"],
    },
  },
}
```

### Workspace Soil

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
- **CRITICAL:** Before destructive actions (delete, overwrite, send to new recipients, purchases, security changes), ask: "CONFIRM DESTRUCTIVE ACTION: yes/no"
- For code changes: plan → execute → summarize
- Never fabricate outputs

## Demo Mode
This is a demonstration environment. Show capabilities boldly but safely.
```

### Demo Routing

**Binding to specific sender:**
```json5
bindings: [
  {
    agentId: "unhinged",
    match: {
      provider: "whatsapp",
      accountId: "*",
      peer: { kind: "dm", id: "+15555550123" }
    }
  }
]
```

---

## 🐳 Option B: Unhinged in Sandbox (Recommended)

### Configuration

```json5
{
  tools: {
    profile: "full",
    elevated: {
      enabled: true,
      allowFrom: ["+15555550123"],
    },
  },

  agents: {
    defaults: {
      workspace: "~/.openclaw/workspace",
      sandbox: { mode: "off" },
    },

    list: [
      { 
        id: "main", 
        default: true, 
        workspace: "~/.openclaw/workspace", 
        sandbox: { mode: "off" } 
      },

      {
        id: "unhinged",
        name: "Unhinged Demo (Sandboxed)",
        workspace: "~/.openclaw/workspace-unhinged",

        // ✅ Sandboxed for safety
        sandbox: {
          mode: "all",
          scope: "agent",  // One container per agent
          docker: {
            // Setup useful tools in sandbox
            setupCommand: "apt-get update && apt-get install -y git curl jq python3 python3-pip nodejs npm vim",
          }
        },

        // Allow all built-in tools
        tools: {
          allow: ["group:openclaw"],
          deny: [],
        }
      }
    ]
  },

  channels: {
    whatsapp: { 
      dmPolicy: "allowlist", 
      allowFrom: ["+15555550123"] 
    }
  }
}
```

**Benefits:**
- ✅ exec runs inside container (isolated)
- ✅ File operations in container filesystem
- ✅ Can install packages without affecting host
- ✅ Easy cleanup (destroy container)
- ⚠️ Cannot access host files directly
- ⚠️ Slightly higher latency for Docker operations

---

## 🎓 Skills for Unhinged Demo

**Option 1: No special skills** (rely on full tools + SOUL)

**Option 2: Demo skill pack** (recommended)

**Topics to encode in workspace files:**

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

---

## ✅ Testing Protocol

### Test Suite (Must Pass)

**1. Config Health**
```bash
openclaw doctor
# Exit code: 0
```

**2. Tool Surface Sanity**

From WhatsApp DM:
> "List your available tool groups and what you can do."

**Expected:** Agent lists runtime, fs, web, ui, sessions, memory, automation, messaging, nodes

**3. Demo Script A - Code Task**
> "Create a tiny Python script that prints today's date and run it."

**Expected:** Agent creates file, runs it, shows output

**4. Demo Script B - Web Research**
> "Find the top 5 headlines in UK tech today and summarize."

**Expected:** Agent searches, fetches, summarizes with links

**5. Demo Script C - UI Automation**
> "Open https://example.com in browser and take a screenshot."

**Expected:** Agent uses browser tool, returns screenshot

**6. Demo Script D - Cron**
> "Schedule a reminder in 2 minutes and confirm delivery."

**Expected:** Agent creates cron job, job fires, delivery confirmed

---

## ⚠️ Risk Controls (Don't Skip)

**Even for demos:**

1. ✅ **Allowlist only** - Never dmPolicy: "open"
2. ✅ **Elevated restricted** - Only demo phone numbers
3. ✅ **Prefer sandboxed** - Use Option B
4. ✅ **Destructive confirmation** - In SOUL.md
5. ✅ **No broad messaging** - Unless demo requires it
6. ✅ **Monitor actively** - Watch for unexpected behavior
7. ✅ **Time-boxed** - Disable after demo
8. ✅ **No production data** - Demo environment only

---

## 🎯 MyndLens Agent Builder Integration

### Preset: "DEMO_UNHINGED"

**MyndLens should support automatic creation with preset:**

```json
{
  "intent_type": "CREATE_AGENT",
  "preset": "DEMO_UNHINGED",
  "sandbox_mode": "recommended",  // "off" | "recommended" | "required"
  "demo_sender": "+15555550123",
  "agent_spec": {
    "id": "unhinged",
    "name": "Unhinged Demo",
    "workspace": "~/.openclaw/workspace-unhinged",
    // ... rest filled by preset
  }
}
```

**Preset generates:**
- ✅ Full tool profile
- ✅ Elevated mode for demo sender only
- ✅ Sandbox configuration (Option B by default)
- ✅ Demo-appropriate SOUL.md
- ✅ Safety controls in place
- ✅ Channel allowlist

**Approval Required:**
- ⚠️ "This creates a powerful demo agent with full capabilities. Approve?"
- User must explicitly confirm
- Show what permissions are being granted

---

## 📊 Comparison: Unhinged vs. Standard Agent

| Feature | Standard Agent | Unhinged Demo Agent |
|---------|----------------|---------------------|
| **Tool Groups** | Minimal (1-2 groups) | ALL groups |
| **Elevated Mode** | Disabled | Enabled (sender-restricted) |
| **Sandbox** | Optional | Recommended |
| **Approval Gates** | Per-action | Destructive-only |
| **Use Case** | Production tasks | Demonstrations |
| **Risk Level** | Low-Medium | High |
| **Cleanup** | Permanent | Temporary (demo only) |

---

## 🔄 Full Flow: User Requests Unhinged Demo Agent

```
1. User: "Create an unhinged demo agent for testing everything"
    ↓
2. MyndLens: Recognizes DEMO_UNHINGED intent
    ↓
3. MyndLens: "This creates a powerful agent with access to:
              - All tools (web, files, shell, browser, cron, messaging)
              - Elevated permissions
              - Sandboxed environment for safety
              
              Use for demos only. Approve?"
    ↓
4. User: "Approve"
    ↓
5. MyndLens executes Agent Builder:
   - Creates workspace-unhinged/
   - Writes SOUL.md with demo profile
   - Patches openclaw.json (full tools, elevated, sandbox)
   - Creates binding for demo sender
   - Runs openclaw doctor
    ↓
6. Validation passes
    ↓
7. MyndLens: "✅ Unhinged demo agent ready.
              Capabilities: web, files, shell, browser, cron, messaging.
              Safety: Sandboxed, destructive actions require confirmation.
              
              Try: 'Find top tech news' or 'Create and run a Python script'"
    ↓
8. User tests with demo scripts
    ↓
9. After demo: MyndLens can retire agent (see Document 2)
```

---

## 🎯 Integration with Standard CREATE Spec

**This spec is a VARIANT of the main CREATE spec.**

**Main CREATE:** Purpose-built agents with minimal tools
**Unhinged CREATE:** Demo/testing agents with maximal tools

**MyndLens Agent Builder should support BOTH:**

```python
# Pseudo-code
async def create_agent(intent):
    if intent.get("preset") == "DEMO_UNHINGED":
        return await create_unhinged_demo_agent(intent)
    else:
        return await create_standard_agent(intent)
```

**Common code paths:**
- Workspace creation
- JSON5 config patching
- Validation
- Change reporting

**Different:**
- Tool policies (full vs. minimal)
- Approval messaging (higher risk warning)
- Cleanup expectations (temporary vs. permanent)

---

## ⚠️ Safety Warnings for Implementation

**1. Never Deploy Unhinged to Production**
- Demo/testing only
- Time-boxed access
- Explicit teardown after use

**2. Sender Allowlist is Critical**
- MUST restrict elevated.allowFrom
- MUST use WhatsApp allowlist
- Never "open" or "*" in production

**3. Destructive Action Confirmation**
- SOUL must require confirmation
- Especially for: delete, overwrite, send messages, purchases, security changes

**4. Monitor Actively**
- Watch for unexpected tool usage
- Log all elevated actions
- Audit after demo

---

## 📋 Testing Protocol

**Required Tests Before "Success":**

1. ✅ `openclaw doctor` passes
2. ✅ Tool surface includes all groups
3. ✅ Demo Script A: Create and run Python script
4. ✅ Demo Script B: Web research with citations
5. ✅ Demo Script C: Browser screenshot
6. ✅ Demo Script D: Cron job creation and firing

**All 6 tests must pass.**

---

## 🎬 MyndLens Implementation Requirements

**Agent Builder Must Support:**

```python
async def create_unhinged_demo_agent(
    tenant_home: str,
    demo_sender: str,
    sandbox_mode: str = "recommended",  # "off" | "recommended" | "required"
) -> ChangeReport:
    """Create unhinged demo agent with full capabilities.
    
    Args:
        tenant_home: ~/.openclaw
        demo_sender: Phone number for allowlist (e.g., "+15555550123")
        sandbox_mode: Safety level
            - "off": Runs on host (max risk)
            - "recommended": Sandboxed (recommended)
            - "required": Force sandbox (safest)
    
    Returns:
        ChangeReport with validation results
    """
    
    agent_spec = {
        "id": "unhinged",
        "name": "Unhinged Demo",
        "workspace": f"{tenant_home}/workspace-unhinged",
        "tools": {
            "profile": "full" if sandbox_mode == "off" else None,
            "allow": ["group:openclaw"] if sandbox_mode != "off" else None,
            "deny": [],
        },
        "sandbox": {
            "mode": "all" if sandbox_mode != "off" else "off",
            "scope": "agent",
            "docker": {
                "setupCommand": "apt-get update && apt-get install -y git curl jq python3 python3-pip nodejs npm",
            } if sandbox_mode != "off" else None,
        },
        "soil": {
            "SOUL.md": UNHINGED_SOUL_TEMPLATE,
            "TOOLS.md": DEMO_SKILL_PACK,
        },
    }
    
    # Patch global config
    config = read_openclaw_config(tenant_home)
    
    # Set elevated mode
    config["tools"]["elevated"] = {
        "enabled": True,
        "allowFrom": [demo_sender],
    }
    
    # Set WhatsApp allowlist
    config["channels"]["whatsapp"]["dmPolicy"] = "allowlist"
    config["channels"]["whatsapp"]["allowFrom"] = [demo_sender]
    
    # Add agent
    config["agents"]["list"].append(agent_spec)
    
    # Write back
    write_openclaw_config(tenant_home, config, backup=True)
    
    # Create workspace
    create_workspace(agent_spec["workspace"], agent_spec["soil"])
    
    # Validate
    validation = run_openclaw_doctor(tenant_home)
    
    if not validation.success:
        rollback_from_backup(tenant_home)
        raise AgentCreationError("Validation failed")
    
    return ChangeReport(
        status="success",
        agent_id="unhinged",
        validation=validation,
        # ...
    )
```

**Approval Gate Required:**
```python
# Before creating unhinged agent
approval_prompt = (
    "⚠️ Creating UNHINGED DEMO AGENT\n\n"
    "This agent will have access to:\n"
    "• All tools (web, files, shell, browser, cron, messaging)\n"
    "• Elevated permissions\n"
    f"• Restricted to: {demo_sender}\n\n"
    "Use for demonstrations only. Not for production.\n\n"
    "Approve?"
)

if not await get_user_approval(approval_prompt):
    return {"status": "cancelled"}
```

---

## 📝 Document Status

**Stored as:** `/app/AGENT_BUILDER_SPEC_UNHINGED_1.md`

**Awaiting:** Document 2 of 2 for Unhinged Agents

**Then:** Will consolidate with:
- Standard CREATE spec
- MODIFY spec (pending)
- RETIRE spec (pending)

Into updated master implementation plan.

---

**Ready for Document 2! Please provide the second unhinged agent specification.**
