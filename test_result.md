#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: "MyndLens - Voice-driven personal assistant with Sovereign Orchestrator architecture. Batch 0+1: Foundations + Identity/Presence baseline. Backend (FastAPI/Python + MongoDB), Frontend (Expo React Native)."

backend:
  - task: "Health endpoint /api/health"
    implemented: true
    working: true
    file: "server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "Health endpoint returns status ok, env, version, active_sessions count. Verified with curl."

  - task: "Auth/Pair endpoint POST /api/auth/pair"
    implemented: true
    working: true
    file: "server.py, auth/tokens.py, auth/device_binding.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "Device pairing creates JWT token with user_id, device_id, session_id, env. Verified via frontend flow."

  - task: "WebSocket Gateway /api/ws with auth"
    implemented: true
    working: true
    file: "gateway/ws_server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "WS accepts connection, authenticates via JWT, creates session, routes messages. Full flow verified via frontend."

  - task: "Heartbeat tracking and presence verification"
    implemented: true
    working: true
    file: "presence/heartbeat.py, presence/rules.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "Heartbeat recording, 15s threshold check, execute blocking when stale. Needs deeper testing."

  - task: "Execute gate - blocks when heartbeat stale"
    implemented: true
    working: "NA"
    file: "gateway/ws_server.py, presence/heartbeat.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Execute request handler checks presence before allowing execution. Returns EXECUTE_BLOCKED with PRESENCE_STALE code when heartbeat >15s. Needs end-to-end testing."

  - task: "PII/Secrets Redaction in logs"
    implemented: true
    working: true
    file: "observability/redaction.py, core/logging_config.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "Redaction patterns for email, phone, SSN, API keys, JWT, MongoDB URIs. Logging formatter applies redaction automatically."

  - task: "Env Guard - hard env separation"
    implemented: true
    working: "NA"
    file: "envguard/env_separation.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "assert_dispatch_allowed blocks prod dispatch from non-prod. Needs testing."

  - task: "Audit event logging"
    implemented: true
    working: true
    file: "observability/audit_log.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "Audit events persisted to MongoDB. Auth success/failure, session created/terminated, execute blocked events. Verified in backend logs."

  - task: "Session status endpoint GET /api/session/{id}"
    implemented: true
    working: "NA"
    file: "server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Returns session status with presence check. Needs testing."

  - task: "Pydantic schemas - WS messages, MIO, Session, Audit"
    implemented: true
    working: true
    file: "schemas/ws_messages.py, schemas/mio.py, schemas/session.py, schemas/audit.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "All canonical schemas defined as Pydantic models. MIO schema frozen for future batches."

frontend:
  - task: "Pairing screen with device binding"
    implemented: true
    working: true
    file: "app/pairing.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "User enters ID, device pairs, token stored. Verified working in browser."

  - task: "Talk screen with WS connection"
    implemented: true
    working: true
    file: "app/talk.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "Connects to WS, shows session info, presence status, execute button, activity log."

  - task: "Settings screen"
    implemented: true
    working: true
    file: "app/settings.tsx"
    stuck_count: 0
    priority: "low"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "Shows session info, connection details, disconnect button."

  - task: "WebSocket client with heartbeat"
    implemented: true
    working: true
    file: "src/ws/client.ts"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "WS client with auth, heartbeat, execute request, reconnect logic. Verified working."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 1
  run_ui: false

test_plan:
  current_focus:
    - "Health endpoint /api/health"
    - "Auth/Pair endpoint POST /api/auth/pair"
    - "WebSocket Gateway /api/ws with auth"
    - "Heartbeat tracking and presence verification"
    - "Execute gate - blocks when heartbeat stale"
    - "PII/Secrets Redaction in logs"
    - "Env Guard - hard env separation"
    - "Audit event logging"
    - "Session status endpoint GET /api/session/{id}"
  stuck_tasks: []
  test_all: true
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: "Batch 0+1 implementation complete. Backend has: health endpoint, auth/pair endpoint, WebSocket gateway with auth handshake, heartbeat tracking with 15s threshold, execute gate (blocks when presence stale), PII redaction in logs, env guard, audit logging. All Pydantic schemas defined (WS messages, MIO, Session, Audit). Frontend has: pairing screen, talk screen with WS connection + heartbeat + execute button, settings screen. Full flow verified: pair -> connect -> auth -> heartbeat -> execute request. Please test all backend endpoints including WS flow, especially the CRITICAL gate: execute blocked when heartbeat >15s."