# Agent Lifecycle: MODIFY & RETIRE Specification

**Received:** February 15, 2026  
**Type:** Agent modification and retirement operations  
**Status:** Complete specification for lifecycle management

---

## 📋 Overview

### New Intent Types

**MODIFY_AGENT:** Update configuration, soil, tools, skills, bindings, cron  
**RETIRE_AGENT:** Disable agent safely without breaking tenant  
**DELETE_AGENT:** Hard removal + teardown (admin-only, optional)

**Core Principle:** All operations are idempotent, drift-proof, schema-safe, and produce deterministic change reports.

---

## 🎯 Definitions

### Modify vs. Retire vs. Delete

**MODIFY:**
- Change how agent behaves or what it can do
- Keep agent active
- Update tools, soil, cron, bindings

**RETIRE:**
- Remove from runtime selection
- Stop automations
- Prevent new invocations
- Preserve artifacts for audit/restore
- **Reversible**

**DELETE:**
- Remove from config
- Optionally remove workspace/state
- **Irreversible** (unless backups exist)
- Admin-only

### Registry

**Source of Truth:** `~/.openclaw/openclaw.json`
- `agents.list[]` array
- `agents.defaults`
- `bindings` (if used)

---

## 📝 Intent Schemas

### MODIFY_AGENT Intent

```json
{
  "intent_type": "MODIFY_AGENT",
  "tenant": {
    "home": "~/.openclaw",
    "timezone": "Europe/London"
  },
  "agent_ref": {"id": "news"},
  "patch": {
    "name": "News Digest (UK + World)",
    "workspace": "~/.openclaw/workspace-news",
    "soil": {
      "SOUL.md": "<replace or patch content>",
      "TOOLS.md": "<optional>",
      "AGENTS.md": "<optional>"
    },
    "tools": {
      "allow": ["group:web"],
      "deny": ["group:runtime", "group:fs", "group:ui", "group:nodes"]
    },
    "skills": {
      "enabled": ["<skill>"],
      "disabled": ["<skill>"]
    },
    "bindings": {
      "mode": "MERGE_BY_ID",
      "items": []
    },
    "cron": {
      "mode": "ENSURE",
      "job_id": "<optional known>",
      "enabled": true,
      "schedule": {
        "kind": "cron",
        "cron": "0 8 * * *",
        "tz": "Europe/London"
      },
      "message": "<updated prompt>",
      "delivery": {
        "mode": "announce",
        "channel": "whatsapp",
        "to": "+15555550123"
      }
    }
  },
  "change_policy": {
    "mode": "SAFE_MERGE",
    "backup": true,
    "validate": true,
    "require_approval": true
  }
}
```

### RETIRE_AGENT Intent

```json
{
  "intent_type": "RETIRE_AGENT",
  "tenant": {"home": "~/.openclaw"},
  "agent_ref": {"id": "news"},
  "retire_policy": {
    "mode": "SOFT_RETIRE",
    "stop_cron": true,
    "remove_bindings": true,
    "tool_lockdown": true,
    "preserve_workspace": true,
    "preserve_state": true
  },
  "change_policy": {
    "backup": true,
    "validate": true,
    "require_approval": true
  }
}
```

### DELETE_AGENT Intent (Admin-Only)

```json
{
  "intent_type": "DELETE_AGENT",
  "tenant": {"home": "~/.openclaw"},
  "agent_ref": {"id": "news"},
  "delete_policy": {
    "remove_from_registry": true,
    "stop_cron": true,
    "remove_bindings": true,
    "delete_workspace": false,
    "delete_state": false
  },
  "change_policy": {
    "backup": true,
    "validate": true,
    "require_approval": true,
    "admin_only": true
  }
}
```

---

## 🔍 Mandatory Preflight (All Operations)

**Before ANY lifecycle operation:**

### 1. Parse + Snapshot
```python
config = read_openclaw_config(tenant_home)
backup_path = create_backup(tenant_home)
```

### 2. Discovery
```python
help_cache = {
    "main": run_command(["openclaw", "--help"]),
    "cron": run_command(["openclaw", "cron", "--help"]),
    "agents": run_command(["openclaw", "agents", "--help"]),
}

# Determine capabilities
supports_cron_update = "update" in help_cache["cron"]
supports_agent_disable = "disable" in help_cache["agents"]
```

### 3. Agent Existence Check
```python
agent = find_agent_by_id(config, agent_id)

if not agent:
    if operation == "MODIFY":
        return {"status": "not_found", "action": "no-op"}
    elif operation == "RETIRE":
        return {"status": "already_retired", "action": "no-op"}
    elif operation == "DELETE":
        return {"status": "already_deleted", "action": "no-op"}
```

### 4. Impact Analysis (For User Approval)
```python
impact = {
    "files_changed": ["openclaw.json", "workspace/SOUL.md"],
    "cron_jobs_stopped": ["job_abc123"],
    "bindings_removed": 2,
    "tool_policy_change": {
        "before": {"allow": ["group:web"]},
        "after": {"allow": ["group:web", "group:fs"]},
        "expansion": true,  # Requires approval
    },
}

# Show to user before proceeding
```

---

## 🔧 MODIFY_AGENT Implementation

### Modification Types Supported

**1. Soil Updates**
```python
async def modify_soil(workspace: str, soil_updates: dict):
    """Update workspace soil files."""
    
    for filename, content in soil_updates.items():
        filepath = f"{workspace}/{filename}"
        
        # Content hashing - skip if unchanged
        if file_exists(filepath):
            current_hash = hash_file(filepath)
            new_hash = hash_content(content)
            
            if current_hash == new_hash:
                logger.info(f"Skipping {filename} - unchanged")
                continue
        
        # Write new content
        with open(filepath, 'w') as f:
            f.write(content)
        
        logger.info(f"Updated {filename}")
```

**2. Tool Policy Updates**
```python
async def modify_tool_policy(
    agent: dict,
    new_allow: list,
    new_deny: list,
) -> dict:
    """Update agent tool policy."""
    
    # Check for tool expansion
    current_allow = set(agent.get("tools", {}).get("allow", []))
    requested_allow = set(new_allow)
    
    expansion = requested_allow - current_allow
    
    # Sensitive tool groups require approval
    sensitive = {"group:runtime", "group:fs", "group:messaging", "group:nodes"}
    sensitive_expansion = expansion & sensitive
    
    if sensitive_expansion:
        approval_required = True
        approval_reason = f"Adding sensitive tools: {sensitive_expansion}"
    else:
        approval_required = False
    
    # Update agent config
    agent["tools"] = {
        "allow": new_allow,
        "deny": new_deny,
    }
    
    return {
        "updated": True,
        "approval_required": approval_required,
        "approval_reason": approval_reason if approval_required else None,
    }
```

**3. Skills Updates**
```python
async def modify_skills(agent_id: str, enabled: list, disabled: list):
    """Update agent skills."""
    
    # Check if OpenClaw supports skill toggles
    if supports_skill_config():
        # Update via config
        agent["skills"] = {
            "enabled": enabled,
            "disabled": disabled,
        }
    else:
        # Encode as workspace guidance
        skills_doc = generate_skills_document(enabled, disabled)
        write_workspace_file(
            f"{agent['workspace']}/SKILLS.md",
            skills_doc
        )
```

**4. Bindings Updates**
```python
async def modify_bindings(config: dict, agent_id: str, new_bindings: list):
    """Update routing bindings for agent."""
    
    if "bindings" not in config:
        config["bindings"] = []
    
    # Remove old bindings for this agent
    config["bindings"] = [
        b for b in config["bindings"]
        if b.get("agentId") != agent_id
    ]
    
    # Add new bindings
    for binding in new_bindings:
        binding["agentId"] = agent_id
        config["bindings"].append(binding)
    
    return {"bindings_updated": len(new_bindings)}
```

**5. Cron Updates**
```python
async def modify_cron(
    agent_id: str,
    cron_spec: dict,
    stored_job_id: str = None,
):
    """Update or recreate cron job."""
    
    if cron_spec.get("mode") == "ENSURE":
        # Check if job exists
        existing_jobs = list_cron_jobs()
        
        job = find_job_by_id(existing_jobs, stored_job_id) \
              or find_job_by_agent(existing_jobs, agent_id)
        
        if job and supports_cron_update():
            # Update existing job
            result = update_cron_job(
                job_id=job["id"],
                schedule=cron_spec["schedule"],
                message=cron_spec["message"],
                delivery=cron_spec["delivery"],
            )
            action = "updated"
        else:
            # Recreate job
            if job:
                delete_cron_job(job["id"])
            
            new_job_id = create_cron_job(
                agent_id=agent_id,
                schedule=cron_spec["schedule"],
                message=cron_spec["message"],
                delivery=cron_spec["delivery"],
            )
            action = "recreated"
            result = {"job_id": new_job_id}
        
        return {"action": action, "job_id": result.get("job_id")}
```

### Safe Merge Rules

**What to Preserve:**
- ✅ Agent order (don't reorder unrelated agents)
- ✅ Default agent (don't modify unless explicitly targeted)
- ✅ Unknown-but-valid schema fields
- ✅ Comments in JSON5 (best effort)

**Merge Algorithm:**
```python
def merge_agent_config(existing: dict, patch: dict) -> dict:
    """Safely merge agent configuration."""
    
    merged = existing.copy()
    
    # Update known fields
    if "name" in patch:
        merged["name"] = patch["name"]
    
    if "workspace" in patch:
        merged["workspace"] = patch["workspace"]
    
    if "tools" in patch:
        merged["tools"] = patch["tools"]  # Replace entirely
    
    if "sandbox" in patch:
        merged["sandbox"] = patch["sandbox"]
    
    # Preserve unknown fields from existing
    for key in existing:
        if key not in patch and key not in merged:
            merged[key] = existing[key]
    
    return merged
```

### Post-Modification Tests

**Minimum tests for MODIFY_AGENT:**
1. ✅ `openclaw doctor` passes
2. ✅ Agent exists exactly once
3. ✅ Tool boundary matches requested allow/deny
4. ✅ If cron enabled: job exists and runs successfully
5. ✅ Output contract validation passes

---

## 🛑 RETIRE_AGENT Implementation

### Soft-Retire Strategy (Recommended Default)

**Execute in order:**

**1. Stop Scheduled Automations**
```python
async def stop_agent_cron_jobs(agent_id: str):
    """Stop all cron jobs for agent."""
    
    # Find jobs associated with agent
    jobs = await find_agent_cron_jobs(agent_id)
    
    for job in jobs:
        if supports_cron_disable():
            await disable_cron_job(job["id"])
        else:
            await delete_cron_job(job["id"])
        
        logger.info(f"Stopped cron job: {job['id']} for agent {agent_id}")
    
    return {"jobs_stopped": len(jobs)}
```

**2. Remove Routing/Bindings**
```python
async def remove_agent_bindings(config: dict, agent_id: str):
    """Remove all bindings routing to this agent."""
    
    if "bindings" not in config:
        return {"bindings_removed": 0}
    
    original_count = len(config["bindings"])
    
    config["bindings"] = [
        b for b in config["bindings"]
        if b.get("agentId") != agent_id
    ]
    
    removed = original_count - len(config["bindings"])
    
    return {"bindings_removed": removed}
```

**3. Tool Lockdown**
```python
async def lockdown_agent_tools(agent: dict):
    """Lock down agent tools to prevent execution."""
    
    agent["tools"] = {
        "allow": [],
        "deny": ["group:openclaw"],  # Deny all
    }
    
    return {"lockdown": True}
```

**4. Mark Retired**
```python
async def mark_agent_retired(
    workspace: str,
    agent_id: str,
    reason: str,
    approved_by: str,
):
    """Write retirement marker."""
    
    # Find associated cron jobs for documentation
    jobs = await find_agent_cron_jobs(agent_id)
    job_ids = [j["id"] for j in jobs]
    
    retirement_doc = f"""# RETIREMENT NOTICE

**Agent ID:** {agent_id}  
**Retired At:** {datetime.now(timezone.utc).isoformat()}  
**Reason:** {reason}  
**Approved By:** {approved_by}  

## Prior Configuration

**Cron Jobs Stopped:**
{chr(10).join(f'- {jid}' for jid in job_ids)}

**Status:** RETIRED (preserving workspace for audit)

## Restoration

To restore this agent, use UNRETIRE_AGENT operation.
"""
    
    with open(f"{workspace}/RETIREMENT.md", "w") as f:
        f.write(retirement_doc)
    
    # Update MyndLens internal catalog
    await db.agents.update_one(
        {"agent_id": agent_id},
        {"$set": {
            "status": "RETIRED",
            "retired_at": datetime.now(timezone.utc),
            "retired_reason": reason,
        }}
    )
```

**5. Preserve Workspace + State**
- Do NOT delete workspace (default)
- Workspace remains in place for audit/restore

### Hard-Retire Option

**If policy requests "HARD_RETIRE":**
```python
if retire_policy.get("mode") == "HARD_RETIRE":
    # Remove agent from agents.list[]
    config["agents"]["list"] = [
        a for a in config["agents"]["list"]
        if a["id"] != agent_id
    ]
    
    # Still preserve workspace (unless delete policy says otherwise)
```

### Retirement Tests

**Must pass:**
1. ✅ `openclaw doctor` passes
2. ✅ Agent not selected by capability matcher
3. ✅ No active cron jobs for agent
4. ✅ If invoked directly: fails closed OR unreachable

---

## 🗑️ DELETE_AGENT Implementation (Admin-Only)

### Delete Sequencing

**Execute in strict order:**

```python
async def delete_agent(
    tenant_home: str,
    agent_id: str,
    delete_policy: dict,
    admin_approval: bool = False,
):
    """Delete agent (irreversible operation)."""
    
    if not admin_approval:
        raise PermissionError("DELETE_AGENT requires admin approval")
    
    # 1. Stop cron jobs
    jobs_stopped = await stop_agent_cron_jobs(agent_id)
    
    # 2. Remove bindings
    config = read_openclaw_config(tenant_home)
    bindings_removed = await remove_agent_bindings(config, agent_id)
    
    # 3. Remove agent from registry
    agent = find_agent_by_id(config, agent_id)
    if not agent:
        return {"status": "already_deleted"}
    
    workspace = agent.get("workspace")
    
    config["agents"]["list"] = [
        a for a in config["agents"]["list"]
        if a["id"] != agent_id
    ]
    
    # 4. Archive workspace (default)
    archive_path = None
    if delete_policy.get("delete_workspace") == False:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        archive_path = f"{tenant_home}/archived-workspaces/{agent_id}-{timestamp}"
        
        os.makedirs(os.path.dirname(archive_path), exist_ok=True)
        shutil.move(workspace, archive_path)
        
        logger.info(f"Workspace archived to: {archive_path}")
    
    # 5. Delete workspace (if requested)
    elif delete_policy.get("delete_workspace") == True:
        if os.path.exists(workspace):
            shutil.rmtree(workspace)
            logger.info(f"Workspace deleted: {workspace}")
    
    # 6. Write config
    write_openclaw_config(tenant_home, config)
    
    # 7. Validate
    validation = run_openclaw_doctor(tenant_home)
    if not validation.success:
        rollback_from_backup(tenant_home)
        raise ValidationError("Post-delete validation failed")
    
    # 8. Update MyndLens catalog
    await db.agents.update_one(
        {"agent_id": agent_id},
        {"$set": {
            "status": "DELETED",
            "deleted_at": datetime.now(timezone.utc),
            "workspace_archived": archive_path,
        }}
    )
    
    return {
        "status": "deleted",
        "agent_id": agent_id,
        "workspace_archived": archive_path,
        "jobs_stopped": jobs_stopped,
        "bindings_removed": bindings_removed,
    }
```

### Default Delete Policy (Conservative)

```python
DEFAULT_DELETE_POLICY = {
    "remove_from_registry": True,
    "stop_cron": True,
    "remove_bindings": True,
    "delete_workspace": False,  # Archive, don't delete
    "delete_state": False,
    "archive_location": "~/.openclaw/archived-workspaces/",
}
```

### Delete Tests

**Must pass:**
1. ✅ `openclaw doctor` passes
2. ✅ Agent ID not in `agents.list[]`
3. ✅ No cron jobs reference agent
4. ✅ Capability matcher doesn't return deleted agent
5. ✅ Workspace archived (if policy says preserve)

---

## 🔄 Cron Lifecycle Management

### Canonical Cron Association

**MyndLens must maintain:**
```python
# Internal DB
{
  "agent_id": "news",
  "cron_jobs": [
    {"job_id": "cron_abc123", "schedule": "0 8 * * *", "status": "active"},
  ]
}

# Workspace trace
# workspace-news/AGENTS.md:
# Cron Job: cron_abc123 (daily 08:00)
```

### Update vs. Recreate

```python
async def ensure_cron_job(agent_id: str, spec: dict) -> dict:
    """Ensure cron job exists with current spec."""
    
    # Find existing job
    existing = await find_agent_cron_job(agent_id, spec.get("job_id"))
    
    if existing and supports_cron_update():
        # Update in place
        result = await run_command([
            "openclaw", "cron", "update",
            existing["id"],
            "--schedule", spec["schedule"]["cron"],
            "--message", spec["message"],
            # ... other flags
        ])
        action = "updated"
        job_id = existing["id"]
    
    else:
        # Recreate
        if existing:
            await run_command(["openclaw", "cron", "delete", existing["id"]])
        
        result = await run_command([
            "openclaw", "cron", "add",
            "--agent", agent_id,
            "--schedule", spec["schedule"]["cron"],
            "--message", spec["message"],
            "--announce",
            "--channel", spec["delivery"]["channel"],
            "--to", spec["delivery"]["to"],
        ])
        
        job_id = extract_job_id_from_output(result.stdout)
        action = "created" if not existing else "recreated"
    
    # Store job_id association
    await update_agent_cron_mapping(agent_id, job_id)
    
    return {"action": action, "job_id": job_id}
```

### Retire Cron Behavior

```python
if retire_policy.get("stop_cron") == True:
    jobs = await find_agent_cron_jobs(agent_id)
    
    for job in jobs:
        await run_command(["openclaw", "cron", "delete", job["id"]])
        logger.info(f"Stopped cron job: {job['id']}")
```

---

## 🔐 Safety Gates

### Modify Gates

**Refuse unless explicit approval if:**
- Tool expansion to sensitive groups (runtime, fs, messaging, nodes)
- Changing delivery targets (new phone numbers/channels)
- Changing bindings to route additional peers

```python
def requires_approval_for_modify(current: dict, patch: dict) -> tuple[bool, str]:
    """Check if modification requires explicit approval."""
    
    # Tool expansion?
    current_tools = set(current.get("tools", {}).get("allow", []))
    new_tools = set(patch.get("tools", {}).get("allow", []))
    expansion = new_tools - current_tools
    
    sensitive = {"group:runtime", "group:fs", "group:messaging", "group:nodes"}
    if expansion & sensitive:
        return True, f"Adding sensitive tools: {expansion & sensitive}"
    
    # Delivery target change?
    current_delivery = current.get("cron", {}).get("delivery", {})
    new_delivery = patch.get("cron", {}).get("delivery", {})
    
    if current_delivery.get("to") != new_delivery.get("to"):
        return True, "Changing delivery target"
    
    return False, ""
```

### Retire Gates

**Must not retire default agent unless:**
- Explicitly approved
- Alternate default exists

```python
def can_retire_agent(config: dict, agent_id: str) -> tuple[bool, str]:
    """Check if agent can be retired."""
    
    agent = find_agent_by_id(config, agent_id)
    
    if agent.get("default") == True:
        # Check if other default exists
        other_defaults = [
            a for a in config["agents"]["list"]
            if a.get("default") == True and a["id"] != agent_id
        ]
        
        if not other_defaults:
            return False, "Cannot retire default agent without alternate default"
    
    return True, ""
```

### Delete Gates

**Requirements:**
- Admin-only permission
- Explicit irreversible acknowledgment
- Backups created (unless explicitly disabled)

```python
async def validate_delete_permission(
    user_id: str,
    agent_id: str,
    acknowledged_irreversible: bool,
) -> bool:
    """Validate delete is authorized."""
    
    # Check admin permission
    if not await is_admin(user_id):
        raise PermissionError("DELETE_AGENT requires admin privileges")
    
    # Check explicit acknowledgment
    if not acknowledged_irreversible:
        raise ApprovalError("Must acknowledge operation is irreversible")
    
    return True
```

---

## 📊 Extended Change Report

```json
{
  "status": "success|failure|partial",
  "operation": "MODIFY_AGENT|RETIRE_AGENT|DELETE_AGENT",
  "agent_id": "news",
  
  "writes": [
    {"path": "~/.openclaw/openclaw.json", "action": "patched", "backup": "...bak..."},
    {"path": "~/.openclaw/workspace-news/SOUL.md", "action": "updated"},
    {"path": "~/.openclaw/workspace-news/RETIREMENT.md", "action": "written"}
  ],
  
  "cron": {
    "action": "updated|disabled|deleted|recreated",
    "job_ids": ["cron_abc123"]
  },
  
  "bindings": {
    "action": "updated|removed",
    "count": 2
  },
  
  "retirement": {
    "status": "active|retired|deleted",
    "marker_written": true,
    "workspace_preserved": true,
    "workspace_archived": null
  },
  
  "validation": {
    "doctor": {"ran": true, "exit_code": 0, "output": "..."}
  },
  
  "rollback": {
    "performed": false,
    "reason": ""
  },
  
  "diff_summary": {
    "agents_added": [],
    "agents_updated": ["news"],
    "agents_removed": [],
    "agents_retired": [],
    "workspaces_archived": [],
    "tools_expanded": false,
    "tools_restricted": true
  },
  
  "warnings": [],
  "info": []
}
```

---

## 🔄 Capability Matcher Integration

**After any lifecycle operation, update internal catalog:**

```python
async def update_agent_catalog_status(agent_id: str, new_status: str):
    """Update agent availability in capability matcher."""
    
    await db.agents.update_one(
        {"agent_id": agent_id},
        {"$set": {"status": new_status}}
    )
    
    # Status values:
    # - ACTIVE: Eligible for selection
    # - RETIRED: Never selected; restorable
    # - DELETED: Removed; restore via backup only
```

**Capability matching must respect status:**
```python
async def find_agent_for_capability(required_capabilities: list) -> str:
    """Find eligible agent."""
    
    agents = await db.agents.find({
        "status": "ACTIVE",  # ← Only active agents
        "capabilities": {"$all": required_capabilities},
    }).to_list(100)
    
    # RETIRED and DELETED agents never returned
    return agents[0]["agent_id"] if agents else None
```

---

## ♻️ UNRETIRE_AGENT (Optional but Recommended)

### Implementation

```python
async def unretire_agent(
    tenant_home: str,
    agent_id: str,
    restore_cron: bool = False,
    restore_bindings: bool = False,
) -> ChangeReport:
    """Restore retired agent to active status."""
    
    # 1. Find agent
    config = read_openclaw_config(tenant_home)
    agent = find_agent_by_id(config, agent_id)
    
    if not agent:
        raise AgentNotFoundError(f"Agent {agent_id} not found")
    
    # 2. Check retirement marker
    workspace = agent.get("workspace")
    retirement_file = f"{workspace}/RETIREMENT.md"
    
    if not os.path.exists(retirement_file):
        return {"status": "not_retired", "agent_id": agent_id}
    
    # 3. Re-enable tools
    # Remove tool lockdown, restore from pre-retirement backup
    # (requires storing original tool policy in RETIREMENT.md)
    
    agent["tools"] = parse_original_tools_from_retirement(retirement_file)
    
    # 4. Optionally restore cron
    if restore_cron:
        job_ids = parse_job_ids_from_retirement(retirement_file)
        # Recreate jobs (original specs needed)
    
    # 5. Optionally restore bindings
    if restore_bindings:
        # Restore from backup or user-specified
        pass
    
    # 6. Remove retirement marker
    os.remove(retirement_file)
    
    # 7. Write config
    write_openclaw_config(tenant_home, config)
    
    # 8. Validate
    validation = run_openclaw_doctor(tenant_home)
    
    # 9. Update status
    await db.agents.update_one(
        {"agent_id": agent_id},
        {"$set": {"status": "ACTIVE"}}
    )
    
    return ChangeReport(
        status="success",
        operation="UNRETIRE_AGENT",
        agent_id=agent_id,
        # ...
    )
```

---

## 📋 Complete Lifecycle State Machine

```
[DOES NOT EXIST]
    ↓ CREATE_AGENT
[ACTIVE]
    ↓ MODIFY_AGENT (loop)
[ACTIVE]
    ↓ RETIRE_AGENT
[RETIRED]
    ↓ UNRETIRE_AGENT
[ACTIVE]
    ↓ RETIRE_AGENT
[RETIRED]
    ↓ DELETE_AGENT
[DELETED] (terminal state)
```

**State Transitions:**
- CREATE: NONE → ACTIVE
- MODIFY: ACTIVE → ACTIVE (configuration changed)
- RETIRE: ACTIVE → RETIRED (reversible)
- UNRETIRE: RETIRED → ACTIVE (restoration)
- DELETE: RETIRED → DELETED (irreversible)

**Note:** DELETE can only be called on RETIRED agents (recommended practice)

---

## ✅ Complete Specification Summary

**Operations Defined:**
1. ✅ CREATE_AGENT (standard + unhinged variants)
2. ✅ MODIFY_AGENT (soil, tools, skills, bindings, cron)
3. ✅ RETIRE_AGENT (soft + hard modes)
4. ✅ DELETE_AGENT (admin-only, with archiving)
5. ✅ UNRETIRE_AGENT (restoration)

**Safety Mechanisms:**
- Preflight checks (existence, impact analysis)
- Approval gates (tool expansion, sensitive changes)
- Validation (openclaw doctor)
- Backups (before every operation)
- Rollback (on validation failure)
- Audit trails (change reports, retirement markers)

**Testing Requirements:**
- Post-creation tests (8 tests for unhinged)
- Post-modification tests (5 minimum)
- Post-retirement tests (4 minimum)
- Post-delete tests (4 minimum)

---

**All specifications received and documented!**

**Ready to consolidate into final master implementation plan.**