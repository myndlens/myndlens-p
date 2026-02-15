# Agent Builder Specification - Document 1 of 3

**Received:** February 15, 2026  
**Type:** CREATE OpenClaw Agents  
**Status:** Pending consolidation with Documents 2 & 3

---

## Key Capabilities Defined

### Core Functionality
- ✅ Create new OpenClaw agents from structured intent
- ✅ Define agent workspace with "soil" files (SOUL/USER/AGENTS/TOOLS/IDENTITY)
- ✅ Set tool policies (allow/deny) per agent
- ✅ Enable skills when applicable
- ✅ Register agent in `~/.openclaw/openclaw.json`
- ✅ Create cron jobs for scheduled execution
- ✅ Validate with `openclaw doctor`
- ✅ Produce deterministic change reports

### Critical Constraints
1. **Strict schema safety** - Never write unknown keys
2. **Idempotency** - Same intent twice = no duplicates
3. **Least privilege tools** - Minimal tool exposure by default
4. **No blind assumptions** - Discover CLI at runtime
5. **Proof logs** - Machine-readable change reports

### Important Discovery

**Capability Matching MUST Come First:**
- Before creating new agent, check if existing agent can handle intent
- Only create if NO eligible agent exists
- Prevents agent proliferation

### Channel Clarification

**Critical Distinction:**
- Channels (WhatsApp, Telegram, etc.) are delivery adapters
- Tools are LLM capabilities (web, fs, runtime, etc.)
- No "WhatsApp tool" - messaging uses generic `message` tool + channel routing
- Scheduled delivery uses `cron announce` NOT `message` tool

---

## Implementation Components Required

### 7 Core Modules

1. **OpenClawEnv** - CLI discovery and execution
2. **OpenClawConfigManager** - JSON5 read/write/merge
3. **WorkspaceWriter** - Soil file creation
4. **ToolPolicyResolver** - Minimal allow/deny by intent
5. **CronManager** - Job creation/update/validation
6. **Validator** - `openclaw doctor` runner
7. **AgentBuilder** - Orchestrator for full flow

### Input Schema
```json
{
  "intent_type": "CREATE_AGENT",
  "tenant": {...},
  "agent_spec": {
    "id": "...",
    "name": "...",
    "workspace": "...",
    "soil": {...},
    "tools": {...},
    "skills": {...},
    "cron": {...}
  },
  "change_policy": {...}
}
```

### Output Schema
```json
{
  "status": "success|failure",
  "agent_id": "...",
  "writes": [...],
  "cron": {...},
  "validation": {...},
  "diff_summary": {...}
}
```

---

## Critical Flow

**User Intent → Agent Built → Tested → Confirmed:**

1. User communicates capability need
2. MyndLens extracts intent + dimensions
3. **Capability check FIRST** (use existing vs. create new)
4. User approval gate (mandatory)
5. Execute agent creation (idempotent)
6. Validate with test suite (6 tests minimum)
7. Inform user (mission accomplished)

---

## Safety Gates

**Builder MUST refuse if:**
- `openclaw doctor` fails after patch
- Sensitive tools requested without explicit approval
- WhatsApp delivery requested but channel not enabled
- Schedule timezone missing

---

**This document is stored and ready for consolidation with Documents 2 & 3.**

**Please provide Document 2 (MODIFY) and Document 3 (RETIRE) to complete the specification.**
