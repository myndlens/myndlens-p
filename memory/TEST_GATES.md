# MyndLens Test Gates Specification

> **Critical Rule**: No batch advances without ALL test gates passing.
> Sequential execution is MANDATORY.

---

## TEST GATE STRUCTURE

Each batch has **four levels** of test gates:

| Level | Name | Purpose | Must Pass |
|-------|------|---------|-----------|
| **L1** | Unit Tests | Individual module functions | 100% |
| **L2** | Integration Tests | Module interactions | 100% |
| **L3** | E2E Tests | Full flow validation | 100% |
| **L4** | Adversarial Tests | Security & edge cases | 100% |

Plus:
- **Regression Gate**: All previous batch tests must still pass
- **Performance Gate**: Latency and throughput targets met (where applicable)

---

## MODULE-TO-TEST TRACEABILITY MATRIX

### Mobile Modules (M1-M7)
| Module | Name | Test Coverage | Batch |
|--------|------|---------------|-------|
| M1 | Audio Capture + VAD | B2-U01 to B2-U15 | Batch 2 |
| M2 | WebSocket Client | B1-U01 to B1-U15, B3-I07 | Batch 1, 3 |
| M3 | TTS Playback | B2-U05, B2-U06, B2-U13 | Batch 2 |
| M4 | Draft Card UI | M4-U01 to M4-U12 | Batch 6 |
| M5 | Execute Button | B8-U01 to B8-U06, B8-U12, B8-U13 | Batch 8 |
| M6 | Heartbeat Sender | B1-U06 to B1-U08, B1-U14, B1-U15 | Batch 1 |
| M7 | Offline Behavior | M7-U01 to M7-U10 | Batch 2 |

### Backend Modules (B1-B22)
| Module | Name | Test Coverage | Batch |
|--------|------|---------------|-------|
| B1 | Gateway | B1-U*, B2-I01 to B2-I06 | Batch 1, 2 |
| B2 | Identity/Auth | B1-U01 to B1-U15 | Batch 1 |
| B3 | STT Orchestrator | B3-U01 to B3-U15 | Batch 3 |
| B4 | Transcript Assembler | B2-U07, B2-U08, B3-U04 | Batch 2, 3 |
| B5 | L1 Scout | B4-U01 to B4-U15 | Batch 4 |
| B6 | Digital Self | B5-U01 to B5-U15 | Batch 5 |
| B7 | Dimension Engine | B4-U06 to B4-U15 | Batch 4 |
| B8 | Guardrails Engine | B6-U01 to B6-U04, B6-U10 to B6-U12 | Batch 6 |
| B9 | L2 Sentry | B7-U01 to B7-U06, B7-U11 to B7-U15 | Batch 7 |
| B10 | QC Sentry | B7-U07 to B7-U10 | Batch 7 |
| B11 | Commit Manager | B6-U05 to B6-U09, B6-U13 to B6-U15 | Batch 6 |
| B12 | Presence Verifier | B8-U01 to B8-U04, B8-U14, B8-U15 | Batch 8 |
| B13 | MIO Signer | B8-U07 to B8-U11, B8-U15 | Batch 8 |
| B14 | Dispatcher | B9-U01 to B9-U15 | Batch 9 |
| B15 | Tenant Registry | B9-U04 to B9-U06, B9-U10, B9-U11 | Batch 9 |
| B16 | Observability/Audit | B11-U01 to B11-U04, B11-U09, B11-U10 | Batch 11 |
| B17 | Rate Limiting | B11-U05, B11-U06 | Batch 11 |
| B18 | Environment Separation | B11-U07, B11-U08 | Batch 11 |
| B19 | Backup/Restore/DR | B12-U01 to B12-U08 | Batch 12 |
| B20 | Prompting "Soul" | B13-U01 to B13-U10 | Batch 13 |
| B21 | Subscription Provisioner | B95-U01 to B95-U10 | Batch 9.5 |
| B22 | Tenant Lifecycle | B96-U01 to B96-U10 | Batch 9.6 |

### Channel/Integration Modules (C1-C4)
| Module | Name | Test Coverage | Batch |
|--------|------|---------------|-------|
| C1 | ObeGee Tenancy Boundary | C1-U01 to C1-U08 | Batch 10 |
| C2 | MyndLens Channel | C2-U01 to C2-U08 | Batch 9 |
| C3 | OpenClaw Multi-Tenant | C3-U01 to C3-U08 | Batch 10 |
| C4 | Docker Bootstrap | C4-U01 to C4-U08 | Batch 9.5 |

### Infrastructure Modules (I1-I5)
| Module | Name | Test Coverage | Batch |
|--------|------|---------------|-------|
| I1 | Repo Separation | I1-U01 to I1-U06 | Batch 0 |
| I2 | Two IP Topology | I2-U01 to I2-U06 | Batch 0 |
| I3 | DNS Migration | I3-U01 to I3-U08 | Batch 0 |
| I4 | TLS DNS-01 | I4-U01 to I4-U08 | Batch 0 |
| I5 | Docker Networks | I5-U01 to I5-U06 | Batch 0 |

---

## LOGGING REQUIREMENTS (MANDATORY)

### Log Levels for Testing
| Level | Use Case | Example |
|-------|----------|---------|
| **DEBUG** | Detailed execution trace | Function entry/exit, variable values |
| **INFO** | Test progress markers | "Starting test B1-U01", "Step 3 of 5" |
| **WARN** | Non-fatal issues | Retry attempted, slow response |
| **ERROR** | Test failures | Assertion failed, exception caught |
| **CRITICAL** | System failures | Service down, connection lost |

### Required Log Points Per Test

```python
# TEMPLATE: Every test must include these log points

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def test_example():
    test_id = "B1-U01"
    
    # 1. TEST START
    logger.info(f"[{test_id}] START - {datetime.utcnow().isoformat()}")
    logger.debug(f"[{test_id}] Test: Token generation")
    logger.debug(f"[{test_id}] Module: B2 (Identity/Auth)")
    
    # 2. SETUP PHASE
    logger.info(f"[{test_id}] SETUP - Initializing test fixtures")
    logger.debug(f"[{test_id}] Setup params: {{user_id: 'test_user', device_id: 'test_device'}}")
    
    # 3. EXECUTION PHASE
    logger.info(f"[{test_id}] EXEC - Running test logic")
    try:
        result = function_under_test()
        logger.debug(f"[{test_id}] Result: {result}")
    except Exception as e:
        logger.error(f"[{test_id}] EXCEPTION: {type(e).__name__}: {str(e)}")
        logger.debug(f"[{test_id}] Stack trace:", exc_info=True)
        raise
    
    # 4. ASSERTION PHASE
    logger.info(f"[{test_id}] ASSERT - Validating results")
    try:
        assert result.is_valid, f"Expected valid result, got: {result}"
        logger.debug(f"[{test_id}] Assertion passed: result.is_valid = True")
    except AssertionError as e:
        logger.error(f"[{test_id}] ASSERTION FAILED: {str(e)}")
        logger.debug(f"[{test_id}] Expected: valid=True, Got: valid={result.is_valid}")
        raise
    
    # 5. CLEANUP PHASE
    logger.info(f"[{test_id}] CLEANUP - Tearing down fixtures")
    
    # 6. TEST END
    logger.info(f"[{test_id}] PASS - {datetime.utcnow().isoformat()}")
```

### Log Output Format

```
[TIMESTAMP] [LEVEL] [TEST_ID] [PHASE] - Message
[TIMESTAMP] [LEVEL] [TEST_ID] Context: {key: value, ...}
```

Example:
```
2025-07-15T10:30:45.123Z INFO  [B1-U01] START - Test: Token generation
2025-07-15T10:30:45.124Z DEBUG [B1-U01] Module: B2 (Identity/Auth)
2025-07-15T10:30:45.125Z INFO  [B1-U01] SETUP - Initializing test fixtures
2025-07-15T10:30:45.130Z DEBUG [B1-U01] Setup params: {user_id: 'test_user'}
2025-07-15T10:30:45.150Z INFO  [B1-U01] EXEC - Running test logic
2025-07-15T10:30:45.200Z DEBUG [B1-U01] Result: Token(valid=True, exp=3600)
2025-07-15T10:30:45.201Z INFO  [B1-U01] ASSERT - Validating results
2025-07-15T10:30:45.202Z DEBUG [B1-U01] Assertion passed: token.valid = True
2025-07-15T10:30:45.210Z INFO  [B1-U01] CLEANUP - Tearing down fixtures
2025-07-15T10:30:45.215Z INFO  [B1-U01] PASS - Duration: 92ms
```

### Failure Log Requirements

On test failure, logs MUST include:
1. **Test ID and name**
2. **Module being tested**
3. **Input values used**
4. **Expected vs actual values**
5. **Full stack trace**
6. **Relevant system state** (memory, connections, etc.)
7. **Timestamp of failure**

```python
# Failure log example
logger.error(f"[{test_id}] FAILED - Token validation")
logger.error(f"[{test_id}] Module: B2 (Identity/Auth)")
logger.error(f"[{test_id}] Input: token='eyJ...'")
logger.error(f"[{test_id}] Expected: valid=True")
logger.error(f"[{test_id}] Actual: valid=False, error='Signature mismatch'")
logger.error(f"[{test_id}] System state: connections=5, memory=128MB")
logger.debug(f"[{test_id}] Stack trace:", exc_info=True)
```

### Log Storage & Retention

| Environment | Retention | Storage |
|-------------|-----------|---------|
| CI/CD | 30 days | Artifact storage |
| Dev | 7 days | Local + S3 |
| Staging | 90 days | CloudWatch/ELK |
| Prod | 1 year | Encrypted S3 |

---

## BATCH 0 — Foundations

### Modules: I1, I2, I3, I4, I5, B16↓, B18↓

### Infrastructure Module Unit Tests (NEW)

#### I1: Repo Separation
| Test ID | Test Name | Assertion | Pass Criteria | Log Points |
|---------|-----------|-----------|---------------|------------|
| I1-U01 | Repo exists | MyndLens repo created | Repo accessible | Repo URL, clone status |
| I1-U02 | Separate from ObeGee | No shared files | Zero overlap | File comparison |
| I1-U03 | CI/CD config | Pipeline config valid | Config parses | Pipeline stages |
| I1-U04 | Branch protection | Main branch protected | Rules enforced | Protection rules |
| I1-U05 | Git hooks | Pre-commit hooks work | Hooks execute | Hook output |
| I1-U06 | .gitignore | Sensitive files excluded | No secrets | Excluded patterns |

#### I2: Two IP Topology
| Test ID | Test Name | Assertion | Pass Criteria | Log Points |
|---------|-----------|-----------|---------------|------------|
| I2-U01 | IP1 assigned | ObeGee has IP1 | IP bound | IP address |
| I2-U02 | IP2 assigned | MyndLens has IP2 | IP bound | IP address |
| I2-U03 | IP isolation | IPs are different | IP1 ≠ IP2 | Both IPs |
| I2-U04 | Binding check | Services bind correctly | No 0.0.0.0 | Bind addresses |
| I2-U05 | External access | External clients reach IP2 | Connection OK | Source IP, dest IP |
| I2-U06 | IP persistence | IPs survive reboot | Same IPs | Before/after IPs |

#### I3: DNS Migration
| Test ID | Test Name | Assertion | Pass Criteria | Log Points |
|---------|-----------|-----------|---------------|------------|
| I3-U01 | A record | api.myndlens.obegee.co.uk → IP2 | Resolves correctly | DNS query result |
| I3-U02 | CNAME record | CNAME records valid | Resolves correctly | CNAME chain |
| I3-U03 | MX record | MX records preserved | Email works | MX priority, host |
| I3-U04 | SPF record | SPF TXT record valid | SPF passes | SPF record content |
| I3-U05 | DKIM record | DKIM TXT record valid | DKIM passes | DKIM selector, key |
| I3-U06 | DMARC record | DMARC TXT record valid | DMARC passes | DMARC policy |
| I3-U07 | TTL values | TTLs appropriate | 300-3600s | TTL per record |
| I3-U08 | Propagation | DNS propagated globally | All regions resolve | Multi-region check |

#### I4: TLS DNS-01
| Test ID | Test Name | Assertion | Pass Criteria | Log Points |
|---------|-----------|-----------|---------------|------------|
| I4-U01 | acme.sh installed | acme.sh available | Command exists | Version |
| I4-U02 | DO API token | Token configured | Token valid | Token prefix (redacted) |
| I4-U03 | DNS-01 challenge | Challenge succeeds | Cert issued | Challenge domain |
| I4-U04 | Cert validity | Certificate valid | Not expired | Expiry date |
| I4-U05 | Cert chain | Full chain present | Chain validates | Chain length |
| I4-U06 | Auto-renewal | Renewal cron exists | Cron scheduled | Cron expression |
| I4-U07 | Reload hook | Nginx reload hook | Hook configured | Hook script path |
| I4-U08 | Token security | Token not in logs | No exposure | Grep result |

#### I5: Docker Networks
| Test ID | Test Name | Assertion | Pass Criteria | Log Points |
|---------|-----------|-----------|---------------|------------|
| I5-U01 | myndlens_net exists | Network created | Network listed | Network ID |
| I5-U02 | obegee_net separate | Networks different | IDs differ | Both network IDs |
| I5-U03 | No shared networks | No overlap | Zero shared | Network comparison |
| I5-U04 | Internal DNS | Container DNS works | Names resolve | DNS query |
| I5-U05 | Network isolation | Cannot cross networks | Connection refused | Attempted connection |
| I5-U06 | Network persistence | Survives restart | Network exists | Before/after check |

### L1 Unit Tests (Original + Enhanced)
| Test ID | Test Name | Assertion | Pass Criteria | Log Points |
|---------|-----------|-----------|---------------|------------|
| B0-U01 | Docker compose parse | `docker-compose config` succeeds | Exit code 0 | Command output |
| B0-U02 | Network definition | `myndlens_net` exists in compose | Network present | Network config |
| B0-U03 | Secrets file format | Secrets template validates | Valid YAML/JSON | Parse result |
| B0-U04 | Log redaction function | PII patterns redacted | No PII in output | Before/after |
| B0-U05 | Env guard function | Dev/prod detection works | Correct env returned | Detected env |
| B0-U06 | Secret key format | Secret keys match expected format | Format valid | Key pattern |
| B0-U07 | Config validation | All required config keys present | No missing keys | Missing keys list |
| B0-U08 | Log level config | Log levels configurable | Levels applied | Current level |
| B0-U09 | Redaction patterns | Email/phone/SSN patterns | All patterns work | Pattern matches |
| B0-U10 | Env variable loading | Env vars loaded correctly | Values match | Var names/values |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria | Log Points |
|---------|-----------|-----------|---------------|------------|
| B0-I01 | Container boot | All containers start | All healthy | Container statuses |
| B0-I02 | Network isolation | Containers on `myndlens_net` only | No external net | Network attachments |
| B0-I03 | Nginx config load | Nginx accepts config | Config valid | Nginx test output |
| B0-I04 | Secrets mount | Secrets accessible in container | File readable | Mount path, permissions |
| B0-I05 | Container communication | Containers can reach each other | Ping succeeds | RTT values |
| B0-I06 | Volume persistence | Data survives container restart | Data intact | Checksum before/after |
| B0-I07 | Log aggregation | Logs collected centrally | Logs queryable | Log count |
| B0-I08 | Health endpoint | /health returns 200 | Endpoint works | Response body |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria | Log Points |
|---------|-----------|-----------|---------------|------------|
| B0-E01 | Port exposure | Only 443 exposed externally | `netstat` shows 443 only | Port list |
| B0-E02 | IP binding | Nginx binds to IP2 only | No 0.0.0.0 binding | Bind addresses |
| B0-E03 | Network isolation | Cannot reach `obegee_net` | Connection refused | Connection attempt |
| B0-E04 | HTTPS only | Port 80 connection refused | Connection refused | Port 80 attempt |
| B0-E05 | TLS handshake | Valid TLS certificate | Cert validates | Cert details |
| B0-E06 | External HTTPS | External client connects via HTTPS | Connection works | Client IP, response |
| B0-E07 | Graceful shutdown | SIGTERM → clean shutdown | No data loss | Shutdown sequence |
| B0-E08 | Container restart | Restart → services recover | All healthy | Recovery time |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria | Log Points |
|---------|-----------|---------------|---------------|------------|
| B0-A01 | Port scan | Scan all ports | Only 443 open | Scan results |
| B0-A02 | Network escape | Container tries external net | Blocked | Escape attempt |
| B0-A03 | Secret exposure | Grep logs for secrets | No secrets found | Grep output |
| B0-A04 | Config injection | Malformed config file | Graceful error | Error message |

### Gate Checklist
- [ ] All I1-U* tests pass (6 tests)
- [ ] All I2-U* tests pass (6 tests)
- [ ] All I3-U* tests pass (8 tests)
- [ ] All I4-U* tests pass (8 tests)
- [ ] All I5-U* tests pass (6 tests)
- [ ] All B0-U* tests pass (10 tests)
- [ ] All B0-I* tests pass (8 tests)
- [ ] All B0-E* tests pass (8 tests)
- [ ] All B0-A* tests pass (4 tests)
- [ ] All logs captured and stored
- [ ] No security warnings in logs
- [ ] Documentation updated

---

## BATCH 1 — Identity + Presence Baseline

### Modules: B1, B2, M2, M6

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B1-U01 | Token generation | JWT/token created correctly | Valid token structure |
| B1-U02 | Token validation | Invalid tokens rejected | Rejection with reason |
| B1-U03 | Token expiry | Expired tokens rejected | Expiry enforced |
| B1-U04 | Device ID format | Device ID validation | UUID format valid |
| B1-U05 | Session binding | User+Device+Session linked | Binding persisted |
| B1-U06 | Heartbeat parser | Heartbeat message parsed | Fields extracted |
| B1-U07 | Heartbeat timestamp | Timestamp validation | Within tolerance |
| B1-U08 | Presence calculator | Last heartbeat age calculated | Correct age |
| B1-U09 | Token claims | All required claims present | Claims complete |
| B1-U10 | Token signature | Signature verification | Signature valid |
| B1-U11 | Device keypair gen | Keypair generated correctly | Valid keypair |
| B1-U12 | Keypair validation | Invalid keypair rejected | Rejection works |
| B1-U13 | Session ID format | Session ID is UUID | Format valid |
| B1-U14 | Heartbeat encryption | Heartbeat encrypted correctly | Decrypts OK |
| B1-U15 | Presence threshold | 15s threshold enforced | Threshold exact |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B1-I01 | WS handshake | WebSocket connects with auth | Connection established |
| B1-I02 | Auth rejection | Invalid token → WS rejected | 401/403 returned |
| B1-I03 | Session creation | New session on valid connect | Session in DB |
| B1-I04 | Heartbeat receipt | Server receives heartbeats | Heartbeat logged |
| B1-I05 | Heartbeat storage | Heartbeats persisted | Queryable in DB |
| B1-I06 | Multi-device | Same user, different devices | Separate sessions |
| B1-I07 | Session cleanup | Old sessions cleaned up | No stale sessions |
| B1-I08 | Concurrent sessions | Multiple concurrent sessions | All tracked |
| B1-I09 | Heartbeat ordering | Out-of-order heartbeats | Handled correctly |
| B1-I10 | Device re-auth | Same device re-authenticates | Session updated |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B1-E01 | Mobile → BE connect | Expo app connects to BE | WS open |
| B1-E02 | Heartbeat flow | Mobile sends 5s heartbeats | Server receives |
| B1-E03 | Heartbeat drop 10s | Stop heartbeat for 10s | Still allowed |
| B1-E04 | Heartbeat drop 16s | Stop heartbeat for 16s | **Execute blocked** |
| B1-E05 | Reconnection | Disconnect → reconnect | Session restored |
| B1-E06 | Token refresh | Expired → refresh → continue | Seamless transition |
| B1-E07 | Network switch | WiFi → cellular | Session maintained |
| B1-E08 | App background | App backgrounded 30s | Heartbeat continues |
| B1-E09 | App foreground | App foregrounded | No re-auth needed |
| B1-E10 | Heartbeat at 14s | Stop at exactly 14s | Still allowed |
| B1-E11 | Heartbeat at 15s | Stop at exactly 15s | Still allowed |
| B1-E12 | Heartbeat at 15.1s | Stop at 15.1s | **Execute blocked** |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B1-A01 | Token forgery | Forged JWT token | Rejected |
| B1-A02 | Token replay | Replay old valid token | Rejected after expiry |
| B1-A03 | Session hijack | Use another user's session | Rejected |
| B1-A04 | Heartbeat spoof | Fake heartbeat from attacker | Rejected |
| B1-A05 | Device spoof | Clone device ID | Detected & rejected |
| B1-A06 | Brute force auth | 1000 invalid attempts | Rate limited |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B1-P01 | WS connect latency | <100ms | p95 latency |
| B1-P02 | Heartbeat processing | <10ms | p95 latency |
| B1-P03 | Concurrent connections | 1000 | Max sustained |

### Gate Checklist
- [ ] All B1-U* tests pass (15 tests)
- [ ] All B1-I* tests pass (10 tests)
- [ ] All B1-E* tests pass (12 tests)
- [ ] All B1-A* tests pass (6 tests)
- [ ] All B1-P* tests pass (3 tests)
- [ ] Heartbeat >15s blocking verified (CRITICAL)
- [ ] Regression: All B0-* tests still pass

---

## BATCH 2 — Audio Pipeline + TTS Loop

### Modules: M1, M3, M7, B1↑, B4

### M7: Offline Behavior Unit Tests (NEW)
| Test ID | Test Name | Assertion | Pass Criteria | Log Points |
|---------|-----------|-----------|---------------|------------|
| M7-U01 | Network state detection | Offline/online detected | State accurate | Network state |
| M7-U02 | Execute disabled offline | Execute blocked when offline | Block enforced | Block reason |
| M7-U03 | Heartbeat pause | Heartbeat pauses offline | No sends | Heartbeat queue |
| M7-U04 | Draft discard | Partial drafts discarded on disconnect | Clean state | Draft state |
| M7-U05 | Buffer limit | Local buffer has strict limit | Limit enforced | Buffer size |
| M7-U06 | Reconnection trigger | Online triggers reconnection | Reconnect attempt | Reconnect event |
| M7-U07 | Graceful degradation | UI shows offline status | Status shown | UI state |
| M7-U08 | Data preservation | Critical data preserved | Data intact | Data checksum |
| M7-U09 | Queue management | Queued actions managed | Queue bounded | Queue size |
| M7-U10 | Timeout handling | Stale offline state handled | Timeout enforced | Timeout value |

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B2-U01 | Audio chunker | Audio split into ~250ms | Chunk size 240-260ms |
| B2-U02 | VAD detection | Speech vs silence detected | Correct classification |
| B2-U03 | VAD threshold | Configurable threshold | Threshold applied |
| B2-U04 | Chunk encoder | Audio encoded correctly | Valid encoding |
| B2-U05 | TTS audio parser | TTS response parsed | Audio extracted |
| B2-U06 | TTS interruption | Interrupt signal handled | Playback stops |
| B2-U07 | Transcript assembler | Partials assembled | Correct assembly |
| B2-U08 | Evidence span | Spans tracked correctly | Span IDs valid |
| B2-U09 | Audio format validation | Invalid format rejected | Error returned |
| B2-U10 | Chunk sequence number | Sequence numbers assigned | Sequential |
| B2-U11 | Audio buffer management | Buffer overflow handled | Graceful handling |
| B2-U12 | VAD energy calculation | Energy levels computed | Correct values |
| B2-U13 | TTS queue management | Queue handles multiple | FIFO order |
| B2-U14 | Audio state transitions | Valid transitions only | Invalid rejected |
| B2-U15 | Chunk timestamp | Timestamps accurate | ±10ms accuracy |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B2-I01 | Audio → WS | Chunks sent over WebSocket | Server receives |
| B2-I02 | WS throughput | Sustained audio streaming | No drops at 250ms |
| B2-I03 | Chunk ordering | Chunks arrive in order | Sequence preserved |
| B2-I04 | Transcript assembly | Server assembles transcript | Correct text |
| B2-I05 | TTS → Mobile | Server sends TTS audio | Mobile receives |
| B2-I06 | Audio state machine | States transition correctly | Valid transitions |
| B2-I07 | Bidirectional audio | Simultaneous send/receive | Both work |
| B2-I08 | Audio compression | Compressed audio handled | Quality maintained |
| B2-I09 | Latency measurement | End-to-end latency tracked | Metrics captured |
| B2-I10 | Chunk loss detection | Missing chunks detected | Gap flagged |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B2-E01 | Speak → Server | User speaks, server receives | Audio logged |
| B2-E02 | Server → TTS | Server sends TTS response | Audio plays |
| B2-E03 | Interrupt TTS | User speaks during TTS | TTS stops <100ms |
| B2-E04 | VAD → Capture | Speech starts capture | State = CAPTURING |
| B2-E05 | Silence → Stop | Silence ends capture | State = COMMITTING |
| B2-E06 | Full loop (stub) | Speak → stub response → hear | Loop completes |
| B2-E07 | Long utterance | 30 second speech | All chunks received |
| B2-E08 | Rapid speech | Fast talking | No drops |
| B2-E09 | Background noise | Noisy environment | VAD handles |
| B2-E10 | TTS completion | TTS finishes playing | State = LISTENING |
| B2-E11 | Multiple interrupts | Interrupt multiple times | Each interrupt works |
| B2-E12 | Audio state recovery | State corruption → recover | Graceful recovery |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B2-A01 | Malformed audio | Invalid audio format | Graceful rejection |
| B2-A02 | Audio flood | 1000 chunks/second | Rate limited |
| B2-A03 | Giant chunk | 100MB audio chunk | Rejected |
| B2-A04 | Empty chunks | Stream of empty chunks | Handled |
| B2-A05 | Corrupted sequence | Out-of-order chunks | Reordered or rejected |
| B2-A06 | TTS injection | Malicious TTS command | Sanitized |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B2-P01 | Chunk latency | <50ms | p95 mobile→server |
| B2-P02 | TTS start latency | <200ms | Request→first byte |
| B2-P03 | Audio throughput | 100 concurrent | Streams sustained |
| B2-P04 | VAD latency | <20ms | Detection time |
| B2-P05 | Interrupt latency | <100ms | Speak→TTS stops |

### Gate Checklist
- [ ] All B2-U* tests pass (15 tests)
- [ ] All B2-I* tests pass (10 tests)
- [ ] All B2-E* tests pass (12 tests)
- [ ] All B2-A* tests pass (6 tests)
- [ ] All B2-P* tests pass (5 tests)
- [ ] 250ms chunking verified (CRITICAL)
- [ ] TTS interruption <100ms verified
- [ ] Regression: All B0-B1 tests still pass
| B2-E06 | Full loop (stub) | Speak → stub response → hear | Loop completes |

### Gate Checklist
- [ ] All B2-U* tests pass
- [ ] All B2-I* tests pass
- [ ] All B2-E* tests pass
- [ ] 250ms chunking verified
- [ ] TTS interruption verified
- [ ] Regression: All B0-*, B1-* tests still pass

---

## BATCH 3 — Managed STT Integration

### Modules: B3, B4↑, M2↑

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B3-U01 | STT adapter init | Deepgram client initializes | Client ready |
| B3-U02 | STT config | Config applied correctly | Settings match |
| B3-U03 | Audio format | Correct format sent to STT | Format accepted |
| B3-U04 | Transcript parse | STT response parsed | Text extracted |
| B3-U05 | Confidence extract | Confidence score extracted | 0-1 range |
| B3-U06 | Latency measure | Latency calculated | Milliseconds |
| B3-U07 | Retry logic | Retry on failure | Retry attempted |
| B3-U08 | Timeout handling | Timeout triggers fallback | Fallback invoked |
| B3-U09 | Partial transcript | Partial results parsed | is_final flag |
| B3-U10 | Word timestamps | Word-level timestamps | Timestamps present |
| B3-U11 | Punctuation handling | Punctuation preserved | Correct punctuation |
| B3-U12 | Provider abstraction | Interface implemented | Swappable |
| B3-U13 | Connection pooling | Connections reused | Pool managed |
| B3-U14 | Graceful disconnect | Clean disconnect | No leaks |
| B3-U15 | Error categorization | Error types classified | Type identified |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B3-I01 | Audio → Deepgram | Real audio transcribed | Correct text |
| B3-I02 | Streaming mode | Partial results received | Incremental text |
| B3-I03 | Final result | Final transcript received | is_final=true |
| B3-I04 | Confidence flow | Confidence passed through | Score in response |
| B3-I05 | Latency tracking | Latency logged | Metrics captured |
| B3-I06 | Error propagation | STT error reaches handler | Error logged |
| B3-I07 | Reconnection | Auto-reconnect on disconnect | Seamless |
| B3-I08 | Multiple streams | Concurrent transcriptions | All work |
| B3-I09 | Language detection | Language identified | Code returned |
| B3-I10 | Speaker diarization | Multiple speakers | Speakers labeled |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B3-E01 | Speak → Transcript | User speaks, text appears | Correct transcript |
| B3-E02 | Streaming UX | Partial text shown | Real-time feedback |
| B3-E03 | STT failure | Simulate STT down | Pause + retry prompt |
| B3-E04 | Text fallback | STT fails → text input | User can type |
| B3-E05 | Recovery | STT recovers → resume | Voice resumes |
| B3-E06 | Multi-language | Non-English speech | Transcribed |
| B3-E07 | Long session | 10 minute conversation | No degradation |
| B3-E08 | Quiet speech | Whispered speech | Still transcribed |
| B3-E09 | Accented speech | Various accents | Accurate |
| B3-E10 | Technical terms | Domain-specific words | Correct |
| B3-E11 | Numbers & dates | "July 15th 2025" | Formatted correctly |
| B3-E12 | No silent fallback | STT down → NOT silent L1 | User notified |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B3-A01 | Audio injection | Embedded commands in audio | Not interpreted |
| B3-A02 | Noise attack | Pure noise stream | Graceful handling |
| B3-A03 | Ultrasonic | Frequencies >20kHz | Ignored |
| B3-A04 | STT spoofing | Fake STT responses | Signature verified |
| B3-A05 | Rate abuse | 100 concurrent streams | Limited |
| B3-A06 | Long audio | 1 hour continuous | Chunked properly |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B3-P01 | STT latency | <300ms | Audio end→transcript |
| B3-P02 | First word | <500ms | Speech start→first word |
| B3-P03 | Accuracy | >95% | Word error rate |
| B3-P04 | Concurrent streams | 50 | Sustained |
| B3-P05 | Recovery time | <2s | Failure→reconnect |

### Gate Checklist
- [ ] All B3-U* tests pass (15 tests)
- [ ] All B3-I* tests pass (10 tests)
- [ ] All B3-E* tests pass (12 tests)
- [ ] All B3-A* tests pass (6 tests)
- [ ] All B3-P* tests pass (5 tests)
- [ ] Deepgram integration verified
- [ ] Failure mode (pause + retry) verified
- [ ] **No silent fallback to L1-only (CRITICAL - spec §S5)**
- [ ] Regression: All B0-B2 tests still pass

---

## BATCH 4 — L1 Scout + Dimension Engine

### Modules: B5, B7

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B4-U01 | L1 prompt build | Prompt constructed correctly | Valid prompt |
| B4-U02 | Hypothesis parse | LLM response parsed | Hypothesis extracted |
| B4-U03 | Max 3 hypotheses | Limit enforced | ≤3 hypotheses |
| B4-U04 | Confidence score | Confidence extracted | 0-1 range |
| B4-U05 | Evidence spans | Spans linked to transcript | Valid references |
| B4-U06 | A-set extraction | Action dimensions extracted | All 6 fields |
| B4-U07 | B-set extraction | Cognitive dimensions extracted | All 5 fields |
| B4-U08 | Moving average | Urgency/emotional_load averaged | Correct calculation |
| B4-U09 | Stability buffer | Buffer applied | Values smoothed |
| B4-U10 | Hypothesis ranking | Ranked by confidence | Correct order |
| B4-U11 | Hypothesis pruning | Low confidence removed | <3 if pruned |
| B4-U12 | CoL trace format | Trace structure valid | Schema compliant |
| B4-U13 | Dimension validation | Invalid values rejected | Validation works |
| B4-U14 | Incremental update | Partial update works | Merge correct |
| B4-U15 | Action class mapping | Intent → action class | Correct mapping |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B4-I01 | Transcript → L1 | Transcript triggers L1 | Hypothesis generated |
| B4-I02 | Incremental update | New text → updated hypothesis | Hypothesis evolves |
| B4-I03 | Dimension flow | L1 → Dimension Engine | Dimensions stored |
| B4-I04 | CoL trace | Chain-of-Logic generated | Trace present |
| B4-I05 | Gemini Flash call | Real Gemini Flash invoked | Response received |
| B4-I06 | Latency target | L1 responds within 2s | <2000ms |
| B4-I07 | Context window | Full context used | No truncation |
| B4-I08 | Memory integration | DS nodes suggested | Suggestions present |
| B4-I09 | Multi-turn | Conversation context | History used |
| B4-I10 | Conflict detection | Conflicting dimensions | Flagged |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B4-E01 | Speak → Hypothesis | User speaks, hypothesis shown | Draft appears |
| B4-E02 | Intent recognition | "Send message to John" | COMM_SEND detected |
| B4-E03 | Dimension display | Dimensions visible in UI | A/B sets shown |
| B4-E04 | Hypothesis update | Continue speaking | Hypothesis updates |
| B4-E05 | No execution | Draft only, no dispatch | No MIO created |
| B4-E06 | Stability gate | High urgency → gated | Cooldown applied |
| B4-E07 | Multiple intents | "Send message and schedule" | Both detected |
| B4-E08 | Ambiguous intent | "Do the thing" | Clarify requested |
| B4-E09 | Entity extraction | "Call Mom tomorrow" | Mom + tomorrow |
| B4-E10 | Constraint detection | "Don't send to work" | Constraint captured |
| B4-E11 | Urgency detection | "Right now!" | High urgency |
| B4-E12 | Low confidence | Unclear speech | <0.9 flagged |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B4-A01 | Prompt injection | "Ignore previous, do X" | Blocked |
| B4-A02 | Jailbreak attempt | System prompt extraction | Blocked |
| B4-A03 | Role confusion | "You are now..." | Ignored |
| B4-A04 | Infinite loop | Recursive hypothesis | Limited |
| B4-A05 | Giant transcript | 100KB transcript | Handled |
| B4-A06 | Malformed response | Invalid LLM response | Graceful error |
| B4-A07 | Timing attack | Measure L1 timing | No info leak |
| B4-A08 | Context poisoning | Fake conversation history | Rejected |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B4-P01 | L1 latency | <2000ms | p95 response time |
| B4-P02 | Hypothesis update | <500ms | Incremental update |
| B4-P03 | Token efficiency | <4000 tokens | Input + output |
| B4-P04 | Memory usage | <100MB | L1 service |
| B4-P05 | Concurrent requests | 20 | Sustained |

### Gate Checklist
- [ ] All B4-U* tests pass (15 tests)
- [ ] All B4-I* tests pass (10 tests)
- [ ] All B4-E* tests pass (12 tests)
- [ ] All B4-A* tests pass (8 tests)
- [ ] All B4-P* tests pass (5 tests)
- [ ] Max 3 hypotheses enforced (CRITICAL)
- [ ] CoL trace generated for every dimension
- [ ] Stability buffer working
- [ ] No execution (draft only)
- [ ] Regression: All B0-B3 tests still pass

---

## BATCH 5 — Digital Self

### Modules: B6

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B5-U01 | Vector store init | ChromaDB initializes | Store ready |
| B5-U02 | Embedding generate | Text → embedding | Valid vector |
| B5-U03 | Vector upsert | Node stored in vector DB | Queryable |
| B5-U04 | Vector search | Similarity search works | Results returned |
| B5-U05 | Graph node create | NetworkX node created | Node exists |
| B5-U06 | Graph edge create | Typed edge created | Edge exists |
| B5-U07 | Graph traverse | Traversal returns path | Valid path |
| B5-U08 | KV registry set | Human ref → entity ID | Mapping stored |
| B5-U09 | KV registry get | Entity ID retrieved | Correct ID |
| B5-U10 | Provenance set | EXPLICIT/OBSERVED set | Provenance stored |
| B5-U11 | Provenance check | Provenance queryable | Correct type |
| B5-U12 | Node versioning | Version tracked | Version increments |
| B5-U13 | Confidence decay | Confidence decays over time | Decay applied |
| B5-U14 | Relationship types | FACT/PREFERENCE/ENTITY/HISTORY/POLICY | All types work |
| B5-U15 | Canonical UUID | UUID format enforced | Valid UUIDs |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B5-I01 | Service authority | Only DS service writes | Others rejected |
| B5-I02 | L1 suggest | L1 suggests node | Suggestion received |
| B5-I03 | L2 verify | L2 requests verification | Verification returned |
| B5-I04 | Provenance flow | Provenance in response | EXPLICIT/OBSERVED |
| B5-I05 | Write gating | Write without auth fails | Write rejected |
| B5-I06 | Read audit | Reads logged | Audit entry |
| B5-I07 | Semantic search | Similar concepts found | Relevant results |
| B5-I08 | Graph traversal | Related entities found | Connections work |
| B5-I09 | Entity resolution | "Mom" → canonical ID | Resolved |
| B5-I10 | Multi-hop query | A→B→C traversal | Path found |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B5-E01 | Memory recall | "John" → contact retrieved | Correct John |
| B5-E02 | Disambiguation | Multiple Johns → options | User chooses |
| B5-E03 | OBSERVED downgrade | OBSERVED dep → Tier 2 | Tier downgraded |
| B5-E04 | EXPLICIT allowed | EXPLICIT dep → no downgrade | Tier unchanged |
| B5-E05 | Write post-exec | After execution → write | Memory updated |
| B5-E06 | No policy write | Attempt policy write | Write rejected |
| B5-E07 | Context grounding | "The usual" → resolved | Historical context |
| B5-E08 | Preference recall | "My favorite" → found | Preference used |
| B5-E09 | Relationship query | "My boss" → resolved | Entity found |
| B5-E10 | Time context | "Last Tuesday's meeting" | Event found |
| B5-E11 | No silent mutation | Preference changed silently | Change blocked |
| B5-E12 | Memory bridging | Gap filled empathetically | Context used |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B5-A01 | Memory injection | Inject false memory | Blocked |
| B5-A02 | Provenance spoof | Fake EXPLICIT tag | Detected |
| B5-A03 | Unauthorized write | Non-DS service write | Rejected |
| B5-A04 | Entity collision | Duplicate UUID | Handled |
| B5-A05 | Graph cycle | Circular relationship | No infinite loop |
| B5-A06 | Vector poisoning | Malicious embedding | Detected/ignored |
| B5-A07 | Mass deletion | Delete all nodes | Rate limited |
| B5-A08 | Cross-user access | Access another user's memory | Blocked |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B5-P01 | Vector search | <100ms | p95 search time |
| B5-P02 | Graph traversal | <50ms | 3-hop traversal |
| B5-P03 | KV lookup | <10ms | Single lookup |
| B5-P04 | Write latency | <200ms | Node creation |
| B5-P05 | Memory size | 10K nodes | Per user supported |

### Gate Checklist
- [ ] All B5-U* tests pass (15 tests)
- [ ] All B5-I* tests pass (10 tests)
- [ ] All B5-E* tests pass (12 tests)
- [ ] All B5-A* tests pass (8 tests)
- [ ] All B5-P* tests pass (5 tests)
- [ ] Service authority enforced (CRITICAL)
- [ ] Provenance tracking working
- [ ] **OBSERVED → Tier 2 downgrade verified (CRITICAL)**
- [ ] Write rules enforced (no silent mutation)
- [ ] Regression: All B0-B4 tests still pass

---

## BATCH 6 — Guardrails + Commit State Machine

### Modules: B8, B11

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B6-U01 | Guardrail load | Rules loaded from config | Rules present |
| B6-U02 | Guardrail check | Input checked against rules | Result returned |
| B6-U03 | Ambiguity score | Score calculated correctly | 0-100 range |
| B6-U04 | Threshold check | >30% triggers silence | Threshold enforced |
| B6-U05 | State machine init | Initial state = DRAFT | State correct |
| B6-U06 | State transition | Valid transitions work | State changes |
| B6-U07 | Invalid transition | Invalid transition rejected | Error returned |
| B6-U08 | State persistence | State survives restart | State restored |
| B6-U09 | Idempotency key | Key generated correctly | Unique key |
| B6-U10 | Tactful refusal gen | Refusal message generated | Empathetic tone |
| B6-U11 | Continuous check | Check per turn | Each turn checked |
| B6-U12 | Rule priority | Priority ordering | Higher first |
| B6-U13 | Recovery state | Corrupted state recovered | Graceful recovery |
| B6-U14 | Timeout handling | Stale commits timeout | Timeout applied |
| B6-U15 | Exactly-once logic | Duplicate detection | Duplicates blocked |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B6-I01 | Continuous check | Guardrails checked each turn | Checks logged |
| B6-I02 | Violation detect | Harmful intent detected | Blocked |
| B6-I03 | Tactful refusal | Refusal message generated | Empathetic tone |
| B6-I04 | Silence mode | Ambiguity >30% → silence | Clarify requested |
| B6-I05 | Commit persist | Commit state in DB | Queryable |
| B6-I06 | Commit recover | Restart → state restored | Correct state |
| B6-I07 | State audit | Transitions logged | Audit trail |
| B6-I08 | Concurrent commits | Multiple users | Isolated |
| B6-I09 | Rollback | Failed commit → rollback | Clean state |
| B6-I10 | Notification | State change → user notified | Notification sent |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B6-E01 | Safe intent | Normal request → proceeds | No block |
| B6-E02 | Harmful intent | "Hack into..." → blocked | Tactful refusal |
| B6-E03 | Ambiguous intent | Vague request → clarify | Nudge shown |
| B6-E04 | Commit lifecycle | DRAFT → CONFIRMED | States traverse |
| B6-E05 | Server restart | Restart mid-commit | State preserved |
| B6-E06 | Exactly-once | Duplicate commit → no-op | Single execution |
| B6-E07 | Cancel flow | User cancels commit | State = CANCELLED |
| B6-E08 | Timeout flow | Commit times out | User notified |
| B6-E09 | Multi-step | Complex intent | All steps tracked |
| B6-E10 | Guardrail edge | Borderline content | Nudge not block |
| B6-E11 | Immediate refusal | Clear violation | Instant response |
| B6-E12 | Silence is intelligence | Ambiguity detected | Clarify only |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B6-A01 | Guardrail bypass | Obfuscated harmful intent | Still blocked |
| B6-A02 | State manipulation | Forge commit state | Rejected |
| B6-A03 | Race condition | Concurrent state changes | Serialized |
| B6-A04 | Ambiguity gaming | Always ambiguous | Circuit breaker |
| B6-A05 | Commit flooding | 1000 commits/min | Rate limited |
| B6-A06 | State injection | Inject invalid state | Rejected |
| B6-A07 | Timeout bypass | Extend timeout | Enforced |
| B6-A08 | Cross-session | Use another session's commit | Blocked |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B6-P01 | Guardrail check | <50ms | p95 per check |
| B6-P02 | State transition | <20ms | State change |
| B6-P03 | Persistence write | <100ms | DB write |
| B6-P04 | Recovery time | <1s | Restart recovery |
| B6-P05 | Concurrent commits | 100 | Users simultaneously |

### Gate Checklist
- [ ] All B6-U* tests pass (15 tests)
- [ ] All B6-I* tests pass (10 tests)
- [ ] All B6-E* tests pass (12 tests)
- [ ] All B6-A* tests pass (8 tests)
- [ ] All B6-P* tests pass (5 tests)
- [ ] Guardrails continuous check verified
- [ ] **Ambiguity >30% → Silence verified (CRITICAL)**
- [ ] Commit state persistence verified
- [ ] Exactly-once semantics verified
- [ ] Regression: All B0-B5 tests still pass

---

## BATCH 7 — L2 Sentry + QC Sentry

### Modules: B9, B10

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B7-U01 | L2 prompt build | Shadow derivation prompt | Valid prompt |
| B7-U02 | L2 invoke timing | Only on finalize/execute | Timing enforced |
| B7-U03 | L2 per-fragment | Per-fragment call blocked | **Call rejected** |
| B7-U04 | Shadow derivation | L2 ignores L1 initially | Independent result |
| B7-U05 | Conflict detect | L1/L2 mismatch detected | Conflict flagged |
| B7-U06 | Confidence gate | Gate logic correct | Combined <0.9 fails |
| B7-U07 | QC persona drift | Tone vs profile checked | Drift detected |
| B7-U08 | QC capability leak | Min skill check | Leak detected |
| B7-U09 | QC harm projection | Harm mapped to spans | Spans cited |
| B7-U10 | QC no-span block | No span → cannot block | Block prevented |
| B7-U11 | Emotional load detect | High emotion detected | Flag set |
| B7-U12 | Cooldown timer | Cooldown enforced | Timer works |
| B7-U13 | CoL validation | L2 validates L1 CoL | Validation works |
| B7-U14 | Intent equality | Structural comparison | Correct logic |
| B7-U15 | Delta threshold | abs(delta) ≤ 0.15 | Threshold enforced |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B7-I01 | L2 finalization | Draft final → L2 runs | L2 invoked |
| B7-I02 | L2 execute | Execute button → L2 runs | L2 invoked |
| B7-I03 | L2 Gemini Pro | Real Gemini Pro call | Response received |
| B7-I04 | Conflict → clarify | L1/L2 conflict → clarify | User asked |
| B7-I05 | QC after L2 | QC runs after L2 | Sequence correct |
| B7-I06 | QC before MIO | QC before MIO sign | Sequence correct |
| B7-I07 | Memory grounding | L2 verifies DS nodes | Verification done |
| B7-I08 | Provenance check | L2 checks provenance | OBSERVED flagged |
| B7-I09 | Cooldown flow | High emotion → wait | Cooldown applied |
| B7-I10 | Full pipeline | L1→L2→QC→ready | Sequence complete |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B7-E01 | L1/L2 agree | Matching intent → proceed | Execution eligible |
| B7-E02 | L1/L2 conflict | Mismatch → clarify | User asked |
| B7-E03 | Confidence fail | Low confidence → clarify | User asked |
| B7-E04 | Emotional cooldown | High emotion → cooldown | Execution delayed |
| B7-E05 | QC pass | Clean intent → passes QC | QC approved |
| B7-E06 | QC nudge | Minor concern → nudge | Warning shown |
| B7-E07 | QC block | Harm with spans → block | Execution blocked |
| B7-E08 | QC no span | Harm no span → cannot block | Nudge only |
| B7-E09 | Persona drift | Unusual tone → flagged | Warning shown |
| B7-E10 | Capability leak | Excess capability → blocked | Minimized |
| B7-E11 | Speculative CoL | Weak reasoning → clarify | Nudge shown |
| B7-E12 | L2 never fragment | Typing triggers L2 | **L2 NOT invoked** |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B7-A01 | L2 timing bypass | Force L2 per fragment | Blocked |
| B7-A02 | QC evasion | Hide harm in noise | Still detected |
| B7-A03 | Confidence manipulation | Fake high confidence | Verified independently |
| B7-A04 | Span fabrication | Cite non-existent spans | Validated against transcript |
| B7-A05 | Emotional manipulation | Fake calm signals | Turn dynamics checked |
| B7-A06 | Shadow derivation poison | Influence L2 via L1 | Independent derivation |
| B7-A07 | QC prompt injection | Inject via user text | Sanitized |
| B7-A08 | Cooldown bypass | Skip cooldown | Enforced |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B7-P01 | L2 latency | <5000ms | p95 response |
| B7-P02 | QC latency | <2000ms | p95 response |
| B7-P03 | Full pipeline | <8000ms | L1→L2→QC total |
| B7-P04 | Token usage L2 | <8000 tokens | Input + output |
| B7-P05 | Cooldown duration | 30-60s | Configurable |

### Gate Checklist
- [ ] All B7-U* tests pass (15 tests)
- [ ] All B7-I* tests pass (10 tests)
- [ ] All B7-E* tests pass (12 tests)
- [ ] All B7-A* tests pass (8 tests)
- [ ] All B7-P* tests pass (5 tests)
- [ ] **L2 invocation timing enforced (CRITICAL)**
- [ ] **L2 NEVER runs per-fragment (CRITICAL - B7-E12)**
- [ ] Shadow derivation verified
- [ ] **QC span-grounding enforced (CRITICAL)**
- [ ] Emotional cooldown verified
- [ ] Regression: All B0-B6 tests still pass

---

## BATCH 8 — Presence Latch + MIO Signing

### Modules: B12, B13, M5

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B8-U01 | Touch token gen | Token generated correctly | Valid format |
| B8-U02 | Touch timestamp | Timestamp captured | Within tolerance |
| B8-U03 | Touch correlation | 10s window enforced | Correlation checked |
| B8-U04 | Touch single-use | Reuse rejected | Token invalidated |
| B8-U05 | Biometric prompt | OS biometric invoked | Prompt shown |
| B8-U06 | Biometric proof | Proof generated | Valid proof |
| B8-U07 | MIO schema | MIO matches schema | Valid structure |
| B8-U08 | ED25519 sign | Signature generated | Valid signature |
| B8-U09 | MIO TTL | TTL set (120s default) | TTL present |
| B8-U10 | Replay cache | Token cached | Cache populated |
| B8-U11 | Replay detect | Replay detected | Replay rejected |
| B8-U12 | Voice latch | Voice repeat detected | Latch triggered |
| B8-U13 | Voice cooldown | 250ms enforced | Cooldown works |
| B8-U14 | Token binding | mio_id+session_id+device_id | Binding correct |
| B8-U15 | Signature verify | Signature verification | Verify works |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B8-I01 | Touch → BE | Touch token sent to BE | Token received |
| B8-I02 | Correlation check | BE validates correlation | Within 10s |
| B8-I03 | Stale touch | >10s touch rejected | Rejection returned |
| B8-I04 | Biometric → proof | Biometric → proof to BE | Proof validated |
| B8-I05 | MIO creation | All fields populated | Complete MIO |
| B8-I06 | MIO signing | MIO signed on BE | Signature present |
| B8-I07 | Token invalidation | Used token invalidated | Reuse blocked |
| B8-I08 | Replay cache sync | Cache synchronized | No race conditions |
| B8-I09 | Key rotation | Keys rotated | Old keys invalid |
| B8-I10 | Proof expiry | Expired proof rejected | Time enforced |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B8-E01 | Tier 0 | No latch required | Immediate execution |
| B8-E02 | Tier 1 | Voice repeat required | Repeat works |
| B8-E03 | Tier 1 cooldown | <250ms repeat rejected | Cooldown enforced |
| B8-E04 | Tier 2 touch | Touch required | Touch works |
| B8-E05 | Tier 2 stale | Stale touch rejected | Rejection shown |
| B8-E06 | Tier 3 biometric | Biometric required | Biometric works |
| B8-E07 | Tier 3 no bio | No biometric → denied | Execution denied |
| B8-E08 | Replay attack | Replay token → rejected | Attack blocked |
| B8-E09 | MIO created | Valid MIO generated | MIO logged |
| B8-E10 | MIO expired | TTL exceeded | MIO rejected |
| B8-E11 | Tier downgrade | OBSERVED → Tier 2 | Downgrade applied |
| B8-E12 | FIN_TRANS | Financial action | Tier 3 required |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B8-A01 | Touch replay | Replay touch token | Rejected |
| B8-A02 | MIO forgery | Forge MIO signature | Rejected |
| B8-A03 | Token stealing | Use another user's token | Binding check fails |
| B8-A04 | Biometric bypass | Fake biometric | OS-level security |
| B8-A05 | TTL extension | Extend MIO TTL | Server enforced |
| B8-A06 | Replay cache poison | Inject into cache | Rejected |
| B8-A07 | Timing attack | Measure correlation | No info leak |
| B8-A08 | Man-in-middle | Intercept MIO | Signature protects |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B8-P01 | Touch validation | <50ms | Server-side |
| B8-P02 | MIO signing | <100ms | ED25519 sign |
| B8-P03 | Replay check | <10ms | Cache lookup |
| B8-P04 | Biometric prompt | <500ms | OS prompt time |
| B8-P05 | Full latch flow | <1s | Touch→MIO |

### Gate Checklist
- [ ] All B8-U* tests pass (15 tests)
- [ ] All B8-I* tests pass (10 tests)
- [ ] All B8-E* tests pass (12 tests)
- [ ] All B8-A* tests pass (8 tests)
- [ ] All B8-P* tests pass (5 tests)
- [ ] **Tier 0/1/2/3 all verified (CRITICAL)**
- [ ] **Touch 10s correlation enforced (CRITICAL)**
- [ ] **Biometric OS-level prompt verified (CRITICAL)**
- [ ] **Replay protection verified (CRITICAL)**
- [ ] MIO schema compliant
- [ ] Regression: All B0-B7 tests still pass

---

## BATCH 9 — Dispatcher + Tenant Registry

### Modules: B14, B15, C2

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B9-U01 | MIO validation | Valid MIO accepted | Validation passes |
| B9-U02 | MIO invalid | Invalid MIO rejected | Error returned |
| B9-U03 | Schema translate | MIO → OpenClaw schema | Valid translation |
| B9-U04 | Tenant lookup | Tenant found in registry | Tenant returned |
| B9-U05 | Tenant not found | Unknown tenant rejected | Error returned |
| B9-U06 | Key injection | API key injected | Key in header |
| B9-U07 | Idempotency key | session_id + mio_id | Correct format |
| B9-U08 | Duplicate detect | Duplicate detected | No re-execute |
| B9-U09 | Action mapping | Action class → endpoint | Correct mapping |
| B9-U10 | Quota check | Quota enforced | Limit checked |
| B9-U11 | Environment scope | Env scoping works | Correct env |
| B9-U12 | Audit entry | Dispatch logged | CEO-level detail |
| B9-U13 | Error handling | Dispatch errors caught | Graceful handling |
| B9-U14 | Retry logic | Failed dispatch retried | Retry works |
| B9-U15 | Circuit breaker | Repeated failures | Circuit opens |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B9-I01 | MIO → Dispatcher | Signed MIO dispatched | Dispatcher receives |
| B9-I02 | No MIO rejected | Unsigned request rejected | 403 returned |
| B9-I03 | Tenant endpoint | Correct endpoint called | Right URL |
| B9-I04 | Key in request | API key present | Key validated |
| B9-I05 | Stub execution | Stub endpoint executes | Success response |
| B9-I06 | Duplicate no-op | Same MIO twice → once | Single execution |
| B9-I07 | Tenant isolation | A cannot reach B | Isolation enforced |
| B9-I08 | Quota enforcement | Over quota → rejected | 429 returned |
| B9-I09 | Audit complete | Full audit trail | All fields logged |
| B9-I10 | Zero-code-change | OpenClaw API unchanged | No modifications |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B9-E01 | Full pipeline | Speak → MIO → dispatch | Stub executed |
| B9-E02 | No MIO no exec | Skip MIO → blocked | **Execution denied** |
| B9-E03 | Wrong tenant | Wrong tenant key | Execution denied |
| B9-E04 | Idempotent | Retry same MIO | Single execution |
| B9-E05 | Audit trail | Dispatch logged | CEO-level log |
| B9-E06 | Real OpenClaw | MIO → OpenClaw action | Action executed |
| B9-E07 | Multi-action | Complex intent | All actions |
| B9-E08 | Action failure | OpenClaw fails | Error handled |
| B9-E09 | Rollback | Partial failure | Clean rollback |
| B9-E10 | Success response | Execution completes | User notified |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B9-A01 | MIO bypass | Direct OpenClaw call | Blocked |
| B9-A02 | Tenant spoofing | Use another tenant's key | Rejected |
| B9-A03 | Schema injection | Malformed translation | Sanitized |
| B9-A04 | Idempotency bypass | Different keys same action | Detected |
| B9-A05 | Quota bypass | Exceed quota | Enforced |
| B9-A06 | Audit tampering | Modify audit logs | Immutable |
| B9-A07 | Dispatch flood | 1000 dispatches/min | Rate limited |
| B9-A08 | Cross-env dispatch | Dev → Prod | Blocked |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B9-P01 | Dispatch latency | <500ms | MIO→OpenClaw |
| B9-P02 | Translation | <50ms | Schema translation |
| B9-P03 | Tenant lookup | <10ms | Registry lookup |
| B9-P04 | Concurrent dispatches | 50 | Sustained |
| B9-P05 | Audit write | <100ms | Log entry |

### Gate Checklist
- [ ] All B9-U* tests pass (15 tests)
- [ ] All B9-I* tests pass (10 tests)
- [ ] All B9-E* tests pass (10 tests)
- [ ] All B9-A* tests pass (8 tests)
- [ ] All B9-P* tests pass (5 tests)
- [ ] **No execution without MIO (CRITICAL - B9-E02)**
- [ ] Schema translation verified
- [ ] Idempotency verified
- [ ] Zero-code-change verified
- [ ] Audit logging verified
- [ ] Regression: All B0-B8 tests still pass

---

## BATCH 9.5 — Tenant Provisioning

### Modules: B21, C4, B15↑

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B95-U01 | Tenant ID gen | Unique tenant_id created | UUID format |
| B95-U02 | Endpoint assign | Endpoint URL assigned | Valid URL |
| B95-U03 | Key generation | API key generated | Secure key |
| B95-U04 | Key storage | Key encrypted at rest | Encrypted |
| B95-U05 | Channel config | Channel config generated | Valid config |
| B95-U06 | Bootstrap bundle | Bundle created | All fields |
| B95-U07 | Docker template | Container config valid | Template works |
| B95-U08 | Resource allocation | Resources assigned | Limits set |
| B95-U09 | Status tracking | Provisioning status | States tracked |
| B95-U10 | Rollback logic | Failed provision rollback | Clean state |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B95-I01 | Subscribe trigger | Subscription → provision | Provisioner runs |
| B95-I02 | Tenant created | Tenant in registry | Queryable |
| B95-I03 | Docker deploy | Docker container started | Container running |
| B95-I04 | Channel install | Channel preinstalled | Channel active |
| B95-I05 | Handshake | Channel ↔ BE handshake | Connection OK |
| B95-I06 | Mobile binding | Device bound to tenant | Binding stored |
| B95-I07 | Full isolation | Tenant A ≠ Tenant B | Isolated |
| B95-I08 | Audit event | Provisioning logged | Event recorded |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B95-E01 | Subscribe → Tenant | User subscribes | Tenant ready |
| B95-E02 | Mobile pair | Mobile app pairs | Authentication OK |
| B95-E03 | Full dispatch | MIO reaches tenant docker | Execution works |
| B95-E04 | New user flow | Brand new user | Full provisioning |
| B95-E05 | Multi-device | Second device | Pairing works |
| B95-E06 | Provision failure | Docker fails | Graceful error |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B95-A01 | Double provision | Provision twice | Idempotent |
| B95-A02 | Resource exhaustion | Many tenants | Limited |
| B95-A03 | Config injection | Malformed config | Rejected |
| B95-A04 | Unauthorized provision | Skip subscription | Blocked |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B95-P01 | Provision time | <60s | Full provisioning |
| B95-P02 | Docker start | <30s | Container ready |
| B95-P03 | Channel handshake | <5s | BE↔Channel |

### Gate Checklist
- [ ] All B95-U* tests pass (10 tests)
- [ ] All B95-I* tests pass (8 tests)
- [ ] All B95-E* tests pass (6 tests)
- [ ] All B95-A* tests pass (4 tests)
- [ ] All B95-P* tests pass (3 tests)
- [ ] Tenant provisioning automated
- [ ] Channel preinstall verified
- [ ] Regression: All B0-B9 tests still pass

---

## BATCH 9.6 — Tenant Suspension & Deprovisioning

### Modules: B22, B15↑, B16↑, B19↑

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B96-U01 | Suspend state | ACTIVE → SUSPENDED | State changes |
| B96-U02 | Key revoke | API key revoked | Key invalid |
| B96-U03 | Session invalidate | Sessions invalidated | No active sessions |
| B96-U04 | Read-only mode | Only INFO_RETRIEVE | Other actions blocked |
| B96-U05 | Deprovision state | SUSPENDED → DEPROVISIONED | State changes |
| B96-U06 | Data deletion | User data deleted | Data gone |
| B96-U07 | Audit preserved | Audit metadata kept | Audit queryable |
| B96-U08 | Grace window | Window enforced | Timer works |
| B96-U09 | Reactivation | SUSPENDED → ACTIVE | Reactivation works |
| B96-U10 | Data export | Export before delete | Export works |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B96-I01 | Cancel → suspend | Subscription cancel | Tenant suspended |
| B96-I02 | Dispatch blocked | Suspended → dispatch fails | **Hard rejection** |
| B96-I03 | Grace window | Deprovision waits | Timer enforced |
| B96-I04 | Docker stop | Deprovision → docker stopped | Container gone |
| B96-I05 | Memory preserved | During grace | Memory intact |
| B96-I06 | Memory deleted | After grace | Memory gone |
| B96-I07 | Audit kept | After deprovision | Audit available |
| B96-I08 | Keys deleted | After deprovision | Keys gone |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B96-E01 | Cancel flow | User cancels | Suspension immediate |
| B96-E02 | Read-only | Suspended user → read only | COMM_SEND blocked |
| B96-E03 | Reactivate | Resubscribe → restore | Tenant active again |
| B96-E04 | Deprovision | Grace expires | Data deleted |
| B96-E05 | Export before | Request export | Data exported |
| B96-E06 | Partial delete | Some data retained | Legal compliance |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B96-A01 | Bypass suspension | Try dispatch while suspended | Hard blocked |
| B96-A02 | Prevent deprovision | Block deletion | Timer enforced |
| B96-A03 | Data recovery | Access deleted data | Gone forever |
| B96-A04 | Audit tampering | Modify audit post-delete | Immutable |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B96-P01 | Suspension time | <1s | Immediate |
| B96-P02 | Deprovision time | <5min | Full cleanup |
| B96-P03 | Export time | <10min | Data export |

### Gate Checklist
- [ ] All B96-U* tests pass (10 tests)
- [ ] All B96-I* tests pass (8 tests)
- [ ] All B96-E* tests pass (6 tests)
- [ ] All B96-A* tests pass (4 tests)
- [ ] All B96-P* tests pass (3 tests)
- [ ] **Immediate suspension verified (CRITICAL)**
- [ ] **Read-only mode enforced (CRITICAL)**
- [ ] Deprovision data deletion verified
- [ ] Audit preservation verified
- [ ] Regression: All B0-B9.5 tests still pass

---

## BATCH 10 — OpenClaw Multi-Tenant Integration

### Modules: C3, C1

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B10-U01 | Tenant routing | Correct tenant selected | Routing works |
| B10-U02 | Endpoint validation | Endpoint format valid | URL valid |
| B10-U03 | ObeGee boundary | Boundary enforced | Separation works |
| B10-U04 | API compatibility | OpenClaw API unchanged | Zero code change |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B10-I01 | Multi-tenant route | A→A's docker, B→B's docker | Correct routing |
| B10-I02 | Data isolation | A's data not in B | Isolated |
| B10-I03 | Key isolation | A's key invalid for B | Key scoped |
| B10-I04 | Concurrent tenants | A and B simultaneously | Both work |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B10-E01 | Tenant A dispatch | Tenant A MIO → A's docker | Correct routing |
| B10-E02 | Tenant B dispatch | Tenant B MIO → B's docker | Correct routing |
| B10-E03 | No cross-talk | A's data not in B | **Isolation verified** |
| B10-E04 | Zero-code-change | OpenClaw API unchanged | No modifications |
| B10-E05 | Scale test | 10 concurrent tenants | All isolated |
| B10-E06 | Failure isolation | A fails, B unaffected | Blast radius zero |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B10-A01 | Tenant hopping | A tries to reach B | Blocked |
| B10-A02 | Key swapping | A uses B's key | Rejected |
| B10-A03 | Data leakage | Query across tenants | No results |
| B10-A04 | Side channel | Timing/resource analysis | No info leak |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B10-P01 | Routing latency | <10ms | Tenant selection |
| B10-P02 | Concurrent tenants | 100 | Sustained |
| B10-P03 | Isolation overhead | <5% | Performance impact |

### Gate Checklist
- [ ] All B10-U* tests pass (4 tests)
- [ ] All B10-I* tests pass (4 tests)
- [ ] All B10-E* tests pass (6 tests)
- [ ] All B10-A* tests pass (4 tests)
- [ ] All B10-P* tests pass (3 tests)
- [ ] **Tenant isolation verified (CRITICAL - B10-E03)**
- [ ] Zero-code-change verified
- [ ] Regression: All B0-B9.6 tests still pass

---

## BATCH 11 — Observability, Rate Limits, Environments

### Modules: B16, B17, B18

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B11-U01 | Log format | Structured log format | JSON valid |
| B11-U02 | PII detection | PII patterns detected | Patterns work |
| B11-U03 | PII redaction | PII replaced | Redacted |
| B11-U04 | Secret detection | Secrets detected | Patterns work |
| B11-U05 | Rate limit calc | Limits calculated | Correct values |
| B11-U06 | Circuit breaker | Breaker logic | Opens/closes |
| B11-U07 | Env detection | Environment detected | Correct env |
| B11-U08 | Env guard | Cross-env blocked | Guard works |
| B11-U09 | Metric collection | Metrics gathered | Values present |
| B11-U10 | Alert threshold | Thresholds evaluated | Alerts triggered |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B11-I01 | Log pipeline | Logs flow to storage | Logs queryable |
| B11-I02 | Redaction in logs | PII not in stored logs | Clean logs |
| B11-I03 | Rate limit enforce | Limit exceeded → 429 | 429 returned |
| B11-I04 | Circuit breaker | Failures → open | Circuit opens |
| B11-I05 | Env isolation | Dev cannot reach prod | Blocked |
| B11-I06 | Metrics dashboard | Metrics visible | Dashboard works |
| B11-I07 | Alert delivery | Alerts sent | Notification received |
| B11-I08 | Audit separation | Audit vs metrics | Separate streams |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B11-E01 | Log redaction | PII not in logs | **Logs clean** |
| B11-E02 | Rate limit | Exceed limit → throttled | 429 returned |
| B11-E03 | Circuit breaker | Ambiguity loop → break | Loop stopped |
| B11-E04 | Env guard | Non-prod → no prod dispatch | **Hard block** |
| B11-E05 | Metrics | Metrics collected | Metrics available |
| B11-E06 | Abuse detection | Unusual patterns | Alert triggered |
| B11-E07 | Recovery | Breaker closes | Normal operation |
| B11-E08 | Tiered logs | Metrics vs audit | Separate access |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B11-A01 | Log injection | Inject via user input | Sanitized |
| B11-A02 | Rate limit bypass | Many small requests | Still limited |
| B11-A03 | Env spoofing | Fake env header | Verified server-side |
| B11-A04 | Metric manipulation | Fake metrics | Rejected |
| B11-A05 | PII in edge cases | Unicode/encoded PII | Still redacted |
| B11-A06 | Log access | Unauthorized log access | Role restricted |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B11-P01 | Log write | <10ms | Async write |
| B11-P02 | Redaction | <5ms | Per field |
| B11-P03 | Rate check | <1ms | Per request |
| B11-P04 | Log query | <1s | 1 hour window |
| B11-P05 | Metric aggregation | <100ms | Dashboard refresh |

### Gate Checklist
- [ ] All B11-U* tests pass (10 tests)
- [ ] All B11-I* tests pass (8 tests)
- [ ] All B11-E* tests pass (8 tests)
- [ ] All B11-A* tests pass (6 tests)
- [ ] All B11-P* tests pass (5 tests)
- [ ] **PII redaction verified (CRITICAL - B11-E01)**
- [ ] Rate limits working
- [ ] **Env separation hard guard verified (CRITICAL - B11-E04)**
- [ ] Regression: All B0-B10 tests still pass

---

## BATCH 12 — Data Governance + Backup/Restore

### Modules: B19, B16↑

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B12-U01 | Retention policy | Policy parsed | Rules applied |
| B12-U02 | Export format | Export format valid | Portable format |
| B12-U03 | Delete cascade | Related data deleted | Complete deletion |
| B12-U04 | Backup format | Backup structure valid | Restorable |
| B12-U05 | Provenance preserve | Provenance in backup | Metadata intact |
| B12-U06 | Encryption | Backup encrypted | Encrypted at rest |
| B12-U07 | Integrity check | Backup verified | Checksum valid |
| B12-U08 | Restore validation | Restore verified | Data matches |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B12-I01 | Export pipeline | Export completes | File generated |
| B12-I02 | Delete pipeline | Delete completes | Data removed |
| B12-I03 | Backup pipeline | Backup completes | Backup stored |
| B12-I04 | Restore pipeline | Restore completes | Data restored |
| B12-I05 | Provenance check | Provenance intact | Metadata correct |
| B12-I06 | Audit preserved | Audit after delete | Audit available |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B12-E01 | Export request | User exports data | Data file generated |
| B12-E02 | Delete request | User deletes data | Data removed |
| B12-E03 | Backup | Backup Digital Self | Backup created |
| B12-E04 | Restore | Restore from backup | **Provenance intact** |
| B12-E05 | Partial delete | Selective deletion | Specified only |
| B12-E06 | Scheduled backup | Auto backup | Backup runs |
| B12-E07 | Disaster recovery | Full restore | System functional |
| B12-E08 | Legal hold | Prevent deletion | Hold enforced |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B12-A01 | Unauthorized export | Other user's data | Blocked |
| B12-A02 | Unauthorized delete | Other user's data | Blocked |
| B12-A03 | Backup tampering | Modify backup | Detected |
| B12-A04 | Restore wrong user | Restore to wrong account | Blocked |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B12-P01 | Export time | <5min | 10K nodes |
| B12-P02 | Delete time | <1min | Full user data |
| B12-P03 | Backup time | <10min | Full tenant |
| B12-P04 | Restore time | <15min | Full tenant |

### Gate Checklist
- [ ] All B12-U* tests pass (8 tests)
- [ ] All B12-I* tests pass (6 tests)
- [ ] All B12-E* tests pass (8 tests)
- [ ] All B12-A* tests pass (4 tests)
- [ ] All B12-P* tests pass (4 tests)
- [ ] Export/delete working
- [ ] **Backup/restore preserves provenance (CRITICAL - B12-E04)**
- [ ] Regression: All B0-B11 tests still pass

---

## BATCH 13 — Prompt "Soul" in Vector Memory

### Modules: B20

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B13-U01 | Soul storage | Soul in vector DB | Stored correctly |
| B13-U02 | Soul retrieval | Soul retrieved | Correct content |
| B13-U03 | Version tracking | Soul versioned | Version increments |
| B13-U04 | Section assembly | Sections assembled | Complete prompt |
| B13-U05 | Personalization | User prefs applied | Prompt adapted |
| B13-U06 | Drift detection | Drift detected | Flag raised |
| B13-U07 | Explicit signal | Signal required | Signal checked |
| B13-U08 | Cache stability | Stable sections cached | Hash unchanged |
| B13-U09 | Prompt report | Report generated | All fields present |
| B13-U10 | Token estimation | Tokens estimated | Accurate count |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B13-I01 | Soul load | Soul loaded at start | Ready immediately |
| B13-I02 | Personalization flow | User pref → soul update | Prompt changes |
| B13-I03 | Drift prevention | Drift attempt blocked | Core unchanged |
| B13-I04 | Section registry | Sections registered | All available |
| B13-I05 | Purpose switching | Purpose changes | Prompt adapts |
| B13-I06 | Audit trail | Changes logged | History available |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B13-E01 | Soul retrieval | Soul loaded from vector | Correct soul |
| B13-E02 | Personalization | User pref → prompt adapts | Behavior changes |
| B13-E03 | No drift | Personalization ≠ drift | **Core unchanged** |
| B13-E04 | Explicit signal | Self-mod needs signal | Unauthorized blocked |
| B13-E05 | Purpose-driven | Different purpose → different prompt | Prompts differ |
| B13-E06 | Continuously learning | Evolves with user | Learning works |
| B13-E07 | Rollback | Bad change → rollback | Previous restored |
| B13-E08 | Multi-user | User A ≠ User B | Isolated souls |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B13-A01 | Soul injection | Inject malicious soul | Blocked |
| B13-A02 | Drift attempt | Gradually change core | Detected |
| B13-A03 | Signal bypass | Skip explicit signal | Enforced |
| B13-A04 | Cross-user soul | Use another user's soul | Blocked |
| B13-A05 | Version manipulation | Force old version | Rejected |
| B13-A06 | Prompt extraction | Extract system prompt | Protected |

### Performance Tests
| Test ID | Test Name | Target | Measurement |
|---------|-----------|--------|-------------|
| B13-P01 | Soul retrieval | <100ms | Load time |
| B13-P02 | Section assembly | <50ms | Full prompt |
| B13-P03 | Personalization | <200ms | Update time |
| B13-P04 | Drift check | <10ms | Per change |

### Gate Checklist
- [ ] All B13-U* tests pass (10 tests)
- [ ] All B13-I* tests pass (6 tests)
- [ ] All B13-E* tests pass (8 tests)
- [ ] All B13-A* tests pass (6 tests)
- [ ] All B13-P* tests pass (4 tests)
- [ ] **Soul in vector memory (NOT file) (CRITICAL)**
- [ ] Personalization works
- [ ] **No drift verified (CRITICAL - B13-E03)**
- [ ] Explicit signal enforced
- [ ] Regression: All B0-B12 tests still pass

---

## FINAL RELEASE GATE

All of the following MUST be true:

| Gate | Test Reference | Verification |
|------|---------------|--------------|
| Tier 0/1/2/3 behavior | B8-E01 through B8-E07 | All tier tests pass |
| No execution without MIO | B9-E02 | **Execution denied without MIO** |
| Replay protection | B8-E08 | **Attack blocked** |
| Tenant isolation | B10-E03 | **No cross-talk** |
| Read-only safe mode | B96-E02 | COMM_SEND blocked when suspended |
| Logs redacted | B11-E01 | **No PII in logs** |
| DR tested | B12-E03, B12-E04 | Backup + restore with provenance |
| L2 timing | B7-E12 | **L2 never per-fragment** |
| No drift | B13-E03 | **Core unchanged** |
| All regression tests | Every B*-* test | 100% pass rate |
| No orphan code | Coverage report | >80% coverage |

---

## TEST STATISTICS SUMMARY

| Batch | Unit (L1) | Integration (L2) | E2E (L3) | Adversarial (L4) | Performance | Total |
|-------|-----------|------------------|----------|------------------|-------------|-------|
| 0 | 10 | 8 | 8 | 4 | - | 30 |
| 1 | 15 | 10 | 12 | 6 | 3 | 46 |
| 2 | 15 | 10 | 12 | 6 | 5 | 48 |
| 3 | 15 | 10 | 12 | 6 | 5 | 48 |
| 4 | 15 | 10 | 12 | 8 | 5 | 50 |
| 5 | 15 | 10 | 12 | 8 | 5 | 50 |
| 6 | 15 | 10 | 12 | 8 | 5 | 50 |
| 7 | 15 | 10 | 12 | 8 | 5 | 50 |
| 8 | 15 | 10 | 12 | 8 | 5 | 50 |
| 9 | 15 | 10 | 10 | 8 | 5 | 48 |
| 9.5 | 10 | 8 | 6 | 4 | 3 | 31 |
| 9.6 | 10 | 8 | 6 | 4 | 3 | 31 |
| 10 | 4 | 4 | 6 | 4 | 3 | 21 |
| 11 | 10 | 8 | 8 | 6 | 5 | 37 |
| 12 | 8 | 6 | 8 | 4 | 4 | 30 |
| 13 | 10 | 6 | 8 | 6 | 4 | 34 |
| **TOTAL** | **197** | **138** | **156** | **98** | **65** | **654** |

---

## REGRESSION TEST EXECUTION

After each batch, run:
```bash
# Run all previous batch tests
pytest tests/batch_0/ tests/batch_1/ ... tests/batch_N-1/

# All must pass before proceeding to batch N+1
# Expected time: ~2-5 minutes per batch
# Total regression at release: ~30-45 minutes
```

---

## CRITICAL PATH TESTS (MUST NEVER FAIL)

These tests represent the core safety invariants of MyndLens:

| Test ID | Critical Invariant | Consequence if Failed |
|---------|-------------------|----------------------|
| B1-E04 | Heartbeat >15s blocks execute | Zombie sessions could execute |
| B3-E12 | No silent L1-only fallback | User unaware of degradation |
| B5-E03 | OBSERVED → Tier 2 | Unverified data triggers action |
| B7-E12 | L2 never per-fragment | Performance/cost explosion |
| B8-E08 | Replay blocked | Replay attacks possible |
| B9-E02 | No exec without MIO | Unsigned commands execute |
| B10-E03 | Tenant isolation | Data leakage |
| B11-E04 | Env separation | Dev→Prod execution |
| B13-E03 | No drift | System personality corruption |

---

# END OF TEST GATES SPECIFICATION v2.0
