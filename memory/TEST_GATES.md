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

## BATCH 0 — Foundations

### Modules: I1, I2, I5, B16↓, B18↓

### L1 Unit Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B0-U01 | Docker compose parse | `docker-compose config` succeeds | Exit code 0 |
| B0-U02 | Network definition | `myndlens_net` exists in compose | Network present |
| B0-U03 | Secrets file format | Secrets template validates | Valid YAML/JSON |
| B0-U04 | Log redaction function | PII patterns redacted | No PII in output |
| B0-U05 | Env guard function | Dev/prod detection works | Correct env returned |
| B0-U06 | Secret key format | Secret keys match expected format | Format valid |
| B0-U07 | Config validation | All required config keys present | No missing keys |
| B0-U08 | Log level config | Log levels configurable | Levels applied |
| B0-U09 | Redaction patterns | Email/phone/SSN patterns | All patterns work |
| B0-U10 | Env variable loading | Env vars loaded correctly | Values match |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B0-I01 | Container boot | All containers start | All healthy |
| B0-I02 | Network isolation | Containers on `myndlens_net` only | No external net |
| B0-I03 | Nginx config load | Nginx accepts config | Config valid |
| B0-I04 | Secrets mount | Secrets accessible in container | File readable |
| B0-I05 | Container communication | Containers can reach each other | Ping succeeds |
| B0-I06 | Volume persistence | Data survives container restart | Data intact |
| B0-I07 | Log aggregation | Logs collected centrally | Logs queryable |
| B0-I08 | Health endpoint | /health returns 200 | Endpoint works |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B0-E01 | Port exposure | Only 443 exposed externally | `netstat` shows 443 only |
| B0-E02 | IP binding | Nginx binds to IP2 only | No 0.0.0.0 binding |
| B0-E03 | Network isolation | Cannot reach `obegee_net` | Connection refused |
| B0-E04 | HTTPS only | Port 80 connection refused | Connection refused |
| B0-E05 | TLS handshake | Valid TLS certificate | Cert validates |
| B0-E06 | External HTTPS | External client connects via HTTPS | Connection works |
| B0-E07 | Graceful shutdown | SIGTERM → clean shutdown | No data loss |
| B0-E08 | Container restart | Restart → services recover | All healthy |

### L4 Adversarial Tests
| Test ID | Test Name | Attack Vector | Pass Criteria |
|---------|-----------|---------------|---------------|
| B0-A01 | Port scan | Scan all ports | Only 443 open |
| B0-A02 | Network escape | Container tries external net | Blocked |
| B0-A03 | Secret exposure | Grep logs for secrets | No secrets found |
| B0-A04 | Config injection | Malformed config file | Graceful error |

### Gate Checklist
- [ ] All B0-U* tests pass (10 tests)
- [ ] All B0-I* tests pass (8 tests)
- [ ] All B0-E* tests pass (8 tests)
- [ ] All B0-A* tests pass (4 tests)
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

### Modules: M1, M3, B1↑, B4

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

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B3-I01 | Audio → Deepgram | Real audio transcribed | Correct text |
| B3-I02 | Streaming mode | Partial results received | Incremental text |
| B3-I03 | Final result | Final transcript received | is_final=true |
| B3-I04 | Confidence flow | Confidence passed through | Score in response |
| B3-I05 | Latency tracking | Latency logged | Metrics captured |
| B3-I06 | Error propagation | STT error reaches handler | Error logged |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B3-E01 | Speak → Transcript | User speaks, text appears | Correct transcript |
| B3-E02 | Streaming UX | Partial text shown | Real-time feedback |
| B3-E03 | STT failure | Simulate STT down | Pause + retry prompt |
| B3-E04 | Text fallback | STT fails → text input | User can type |
| B3-E05 | Recovery | STT recovers → resume | Voice resumes |
| B3-E06 | Multi-language | Non-English speech | Transcribed (if supported) |

### Gate Checklist
- [ ] All B3-U* tests pass
- [ ] All B3-I* tests pass
- [ ] All B3-E* tests pass
- [ ] Deepgram integration verified
- [ ] Failure mode (pause + retry) verified
- [ ] No silent fallback (spec §S5)
- [ ] Regression: All B0-*, B1-*, B2-* tests still pass

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

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B4-I01 | Transcript → L1 | Transcript triggers L1 | Hypothesis generated |
| B4-I02 | Incremental update | New text → updated hypothesis | Hypothesis evolves |
| B4-I03 | Dimension flow | L1 → Dimension Engine | Dimensions stored |
| B4-I04 | CoL trace | Chain-of-Logic generated | Trace present |
| B4-I05 | Gemini Flash call | Real Gemini Flash invoked | Response received |
| B4-I06 | Latency target | L1 responds within 2s | <2000ms |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B4-E01 | Speak → Hypothesis | User speaks, hypothesis shown | Draft appears |
| B4-E02 | Intent recognition | "Send message to John" | COMM_SEND detected |
| B4-E03 | Dimension display | Dimensions visible in UI | A/B sets shown |
| B4-E04 | Hypothesis update | Continue speaking | Hypothesis updates |
| B4-E05 | No execution | Draft only, no dispatch | No MIO created |
| B4-E06 | Stability gate | High urgency → gated | Cooldown applied |

### Gate Checklist
- [ ] All B4-U* tests pass
- [ ] All B4-I* tests pass
- [ ] All B4-E* tests pass
- [ ] Max 3 hypotheses enforced
- [ ] CoL trace generated
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

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B5-I01 | Service authority | Only DS service writes | Others rejected |
| B5-I02 | L1 suggest | L1 suggests node | Suggestion received |
| B5-I03 | L2 verify | L2 requests verification | Verification returned |
| B5-I04 | Provenance flow | Provenance in response | EXPLICIT/OBSERVED |
| B5-I05 | Write gating | Write without auth fails | Write rejected |
| B5-I06 | Read audit | Reads logged | Audit entry |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B5-E01 | Memory recall | "John" → contact retrieved | Correct John |
| B5-E02 | Disambiguation | Multiple Johns → options | User chooses |
| B5-E03 | OBSERVED downgrade | OBSERVED dep → Tier 2 | Tier downgraded |
| B5-E04 | EXPLICIT allowed | EXPLICIT dep → no downgrade | Tier unchanged |
| B5-E05 | Write post-exec | After execution → write | Memory updated |
| B5-E06 | No policy write | Attempt policy write | Write rejected |

### Gate Checklist
- [ ] All B5-U* tests pass
- [ ] All B5-I* tests pass
- [ ] All B5-E* tests pass
- [ ] Service authority enforced
- [ ] Provenance tracking working
- [ ] OBSERVED → Tier 2 downgrade verified
- [ ] Write rules enforced
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

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B6-I01 | Continuous check | Guardrails checked each turn | Checks logged |
| B6-I02 | Violation detect | Harmful intent detected | Blocked |
| B6-I03 | Tactful refusal | Refusal message generated | Empathetic tone |
| B6-I04 | Silence mode | Ambiguity >30% → silence | Clarify requested |
| B6-I05 | Commit persist | Commit state in DB | Queryable |
| B6-I06 | Commit recover | Restart → state restored | Correct state |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B6-E01 | Safe intent | Normal request → proceeds | No block |
| B6-E02 | Harmful intent | "Hack into..." → blocked | Tactful refusal |
| B6-E03 | Ambiguous intent | Vague request → clarify | Nudge shown |
| B6-E04 | Commit lifecycle | DRAFT → CONFIRMED | States traverse |
| B6-E05 | Server restart | Restart mid-commit | State preserved |
| B6-E06 | Exactly-once | Duplicate commit → no-op | Single execution |

### Gate Checklist
- [ ] All B6-U* tests pass
- [ ] All B6-I* tests pass
- [ ] All B6-E* tests pass
- [ ] Guardrails continuous check verified
- [ ] Ambiguity >30% → Silence verified
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
| B7-U03 | L2 per-fragment | Per-fragment call blocked | Call rejected |
| B7-U04 | Shadow derivation | L2 ignores L1 initially | Independent result |
| B7-U05 | Conflict detect | L1/L2 mismatch detected | Conflict flagged |
| B7-U06 | Confidence gate | Gate logic correct | Combined <0.9 fails |
| B7-U07 | QC persona drift | Tone vs profile checked | Drift detected |
| B7-U08 | QC capability leak | Min skill check | Leak detected |
| B7-U09 | QC harm projection | Harm mapped to spans | Spans cited |
| B7-U10 | QC no-span block | No span → cannot block | Block prevented |

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B7-I01 | L2 finalization | Draft final → L2 runs | L2 invoked |
| B7-I02 | L2 execute | Execute button → L2 runs | L2 invoked |
| B7-I03 | L2 Gemini Pro | Real Gemini Pro call | Response received |
| B7-I04 | Conflict → clarify | L1/L2 conflict → clarify | User asked |
| B7-I05 | QC after L2 | QC runs after L2 | Sequence correct |
| B7-I06 | QC before MIO | QC before MIO sign | Sequence correct |

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

### Gate Checklist
- [ ] All B7-U* tests pass
- [ ] All B7-I* tests pass
- [ ] All B7-E* tests pass
- [ ] L2 invocation timing enforced (CRITICAL)
- [ ] L2 never runs per-fragment (CRITICAL)
- [ ] Shadow derivation verified
- [ ] QC span-grounding enforced
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

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B8-I01 | Touch → BE | Touch token sent to BE | Token received |
| B8-I02 | Correlation check | BE validates correlation | Within 10s |
| B8-I03 | Stale touch | >10s touch rejected | Rejection returned |
| B8-I04 | Biometric → proof | Biometric → proof to BE | Proof validated |
| B8-I05 | MIO creation | All fields populated | Complete MIO |
| B8-I06 | MIO signing | MIO signed on BE | Signature present |

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

### Gate Checklist
- [ ] All B8-U* tests pass
- [ ] All B8-I* tests pass
- [ ] All B8-E* tests pass
- [ ] Tier 0/1/2/3 all verified
- [ ] Touch 10s correlation enforced
- [ ] Biometric OS-level prompt verified
- [ ] Replay protection verified
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

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B9-I01 | MIO → Dispatcher | Signed MIO dispatched | Dispatcher receives |
| B9-I02 | No MIO rejected | Unsigned request rejected | 403 returned |
| B9-I03 | Tenant endpoint | Correct endpoint called | Right URL |
| B9-I04 | Key in request | API key present | Key validated |
| B9-I05 | Stub execution | Stub endpoint executes | Success response |
| B9-I06 | Duplicate no-op | Same MIO twice → once | Single execution |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B9-E01 | Full pipeline | Speak → MIO → dispatch | Stub executed |
| B9-E02 | No MIO no exec | Skip MIO → blocked | Execution denied |
| B9-E03 | Wrong tenant | Wrong tenant key | Execution denied |
| B9-E04 | Idempotent | Retry same MIO | Single execution |
| B9-E05 | Audit trail | Dispatch logged | CEO-level log |

### Gate Checklist
- [ ] All B9-U* tests pass
- [ ] All B9-I* tests pass
- [ ] All B9-E* tests pass
- [ ] No execution without MIO (CRITICAL)
- [ ] Schema translation verified
- [ ] Idempotency verified
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

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B95-I01 | Subscribe trigger | Subscription → provision | Provisioner runs |
| B95-I02 | Tenant created | Tenant in registry | Queryable |
| B95-I03 | Docker deploy | Docker container started | Container running |
| B95-I04 | Channel install | Channel preinstalled | Channel active |
| B95-I05 | Handshake | Channel ↔ BE handshake | Connection OK |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B95-E01 | Subscribe → Tenant | User subscribes | Tenant ready |
| B95-E02 | Mobile pair | Mobile app pairs | Authentication OK |
| B95-E03 | Full dispatch | MIO reaches tenant docker | Execution works |

### Gate Checklist
- [ ] All B95-U* tests pass
- [ ] All B95-I* tests pass
- [ ] All B95-E* tests pass
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

### L2 Integration Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B96-I01 | Cancel → suspend | Subscription cancel | Tenant suspended |
| B96-I02 | Dispatch blocked | Suspended → dispatch fails | Hard rejection |
| B96-I03 | Grace window | Deprovision waits | Timer enforced |
| B96-I04 | Docker stop | Deprovision → docker stopped | Container gone |

### L3 E2E Tests
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B96-E01 | Cancel flow | User cancels | Suspension immediate |
| B96-E02 | Read-only | Suspended user → read only | COMM_SEND blocked |
| B96-E03 | Reactivate | Resubscribe → restore | Tenant active again |
| B96-E04 | Deprovision | Grace expires | Data deleted |

### Gate Checklist
- [ ] All B96-U* tests pass
- [ ] All B96-I* tests pass
- [ ] All B96-E* tests pass
- [ ] Immediate suspension verified
- [ ] Read-only mode enforced
- [ ] Deprovision data deletion verified
- [ ] Audit preservation verified
- [ ] Regression: All B0-B9.5 tests still pass

---

## BATCH 10 — OpenClaw Multi-Tenant Integration

### Modules: C3, C1

### L3 E2E Tests (Primary Focus)
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B10-E01 | Tenant A dispatch | Tenant A MIO → A's docker | Correct routing |
| B10-E02 | Tenant B dispatch | Tenant B MIO → B's docker | Correct routing |
| B10-E03 | No cross-talk | A's data not in B | Isolation verified |
| B10-E04 | Zero-code-change | OpenClaw API unchanged | No modifications |

### Gate Checklist
- [ ] All B10-E* tests pass
- [ ] Tenant isolation verified (CRITICAL)
- [ ] Zero-code-change verified
- [ ] Regression: All B0-B9.6 tests still pass

---

## BATCH 11 — Observability, Rate Limits, Environments

### Modules: B16, B17, B18

### L3 E2E Tests (Primary Focus)
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B11-E01 | Log redaction | PII not in logs | Logs clean |
| B11-E02 | Rate limit | Exceed limit → throttled | 429 returned |
| B11-E03 | Circuit breaker | Ambiguity loop → break | Loop stopped |
| B11-E04 | Env guard | Non-prod → no prod dispatch | Hard block |
| B11-E05 | Metrics | Metrics collected | Metrics available |

### Gate Checklist
- [ ] All B11-E* tests pass
- [ ] PII redaction verified
- [ ] Rate limits working
- [ ] Env separation hard guard verified
- [ ] Regression: All B0-B10 tests still pass

---

## BATCH 12 — Data Governance + Backup/Restore

### Modules: B19, B16↑

### L3 E2E Tests (Primary Focus)
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B12-E01 | Export request | User exports data | Data file generated |
| B12-E02 | Delete request | User deletes data | Data removed |
| B12-E03 | Backup | Backup Digital Self | Backup created |
| B12-E04 | Restore | Restore from backup | Provenance intact |

### Gate Checklist
- [ ] All B12-E* tests pass
- [ ] Export/delete working
- [ ] Backup/restore preserves provenance
- [ ] Regression: All B0-B11 tests still pass

---

## BATCH 13 — Prompt "Soul" in Vector Memory

### Modules: B20

### L3 E2E Tests (Primary Focus)
| Test ID | Test Name | Assertion | Pass Criteria |
|---------|-----------|-----------|---------------|
| B13-E01 | Soul retrieval | Soul loaded from vector | Correct soul |
| B13-E02 | Personalization | User pref → prompt adapts | Behavior changes |
| B13-E03 | No drift | Personalization ≠ drift | Core unchanged |
| B13-E04 | Explicit signal | Self-mod needs signal | Unauthorized blocked |

### Gate Checklist
- [ ] All B13-E* tests pass
- [ ] Soul in vector memory (not file)
- [ ] Personalization works
- [ ] No drift verified (CRITICAL)
- [ ] Regression: All B0-B12 tests still pass

---

## FINAL RELEASE GATE

All of the following MUST be true:

| Gate | Verification |
|------|--------------|
| Tier 0/1/2/3 behavior | All tier tests pass |
| No execution without MIO | B9-E02 passes |
| Replay protection | B8-E08 passes |
| Tenant isolation | B10-E03 passes |
| Read-only safe mode | B96-E02 passes (L2 offline scenario) |
| Logs redacted | B11-E01 passes |
| DR tested | B12-E03, B12-E04 pass |
| All regression tests | Every B*-* test passes |
| No orphan code | Code coverage >80% |

---

## REGRESSION TEST EXECUTION

After each batch, run:
```bash
# Run all previous batch tests
pytest tests/batch_0/ tests/batch_1/ ... tests/batch_N-1/

# All must pass before proceeding to batch N+1
```

---

# END OF TEST GATES SPECIFICATION
