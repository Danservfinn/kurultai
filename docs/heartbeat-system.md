# Heartbeat System — Kurultai Monitoring Architecture

## Overview

The Kurultai heartbeat system is a **three-phase monitoring cycle** that maintains system health, drives task execution, and enables continuous self-improvement. All phases run via cron jobs on the Mac Mini host.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HEARTBEAT CYCLE                               │
├─────────────────────┬───────────────────────┬───────────────────────┤
│  TICK (5 min)       │  TOCK (30 min)        │  KURULTAI (60 min)    │
│  watchdog-gather.sh │  tock-gather.sh       │  hourly_reflection.sh │
├─────────────────────┼───────────────────────┼───────────────────────┤
│  • Infrastructure   │  • Agent metrics      │  • Self-reflection    │
│  • Health status    │  • Completion rates   │  • Behavioral rules   │
│  • Task queues      │  • Queue depths       │  • Voting cycle       │
│  • Auth heartbeat   │  • Velocity data      │  • Proposal system    │
└─────────────────────┴───────────────────────┴───────────────────────┘
```

## Phase 1: TICK — Health Monitor & Task Driver

**Script:** `scripts/watchdog-gather.sh`
**Frequency:** Every 5 minutes
**Timeout:** 180s default
**Exit Codes:** 0=healthy, 1=degraded, 2=down(restarted), 3=down(restart failed)

### Responsibilities

1. **Infrastructure Health Check**
   - Neo4j connectivity and query latency
   - Redis availability and key counts
   - Cron job execution (last tick time)
   - Agent process status (PID checks)

2. **Task Queue Management**
   - Detect stalled tasks (timeout thresholds by agent)
   - Escalate stale tasks to ogedei for triage
   - Push tasks through routing pipeline
   - Track task transitions in Neo4j

3. **Auth Heartbeat** (SECTION 4c)
   - Tests each agent's API credentials
   - Caches results in `logs/auth-heartbeat.json`
   - 5-minute stale threshold reduces overhead
   - See: `docs/auth-heartbeat-reference.md`

### Outputs

| File | Format | Purpose |
|------|--------|---------|
| `logs/ticks.jsonl` | Append JSON | Machine-readable history |
| `logs/tick-summary.txt` | Overwrite text | Compact summary for LLM context |
| `logs/watchdog.log` | Append log | One-liner per tick |
| `logs/auth-heartbeat.json` | Update | Credential status cache |

### Exit Code Mapping

```bash
0 = healthy     # All systems operational
1 = degraded    # Minor issues (Neo4j slow, one agent down)
2 = down        # Major failure (Redis down, all agents stopped) + restart attempted
3 = fatal       # Down + restart failed (human intervention needed)
```

### Stale Task Detection

The watchdog includes a **pre-filter** to prevent false-positive escalations:

- Tasks with `.verified.done.md` suffix (already verified)
- Tasks with `grade: [A-F]` in frontmatter (graded completion)
- Tasks with `resolved: true` in frontmatter (escalations resolved)

Implementation: `is_task_already_completed()` in `ogedei-watchdog.py`

### Circuit Breaker Health Monitor

**Script:** `scripts/circuit_breaker_health.py`
**Frequency:** Every 5 minutes (via cron)
**Purpose:** Prevents circuit breaker deadlock by forcing timed state transitions

**Problem Solved:** The circuit breaker has a deadlock condition — OPEN agents need `check_agent()` to transition to HALF_OPEN, but OPEN agents aren't routed to, so `check_agent()` never gets called.

**Features:**
1. **Proactive State Transitions:** Forces OPEN → HALF_OPEN after RECOVERY_TIMEOUT (30min normal, 10min urgent)
2. **Urgent Mode:** When fleet failure rate ≥80%, uses 10min timeout instead of 30min
3. **Fleet Failure Rate Calculation:** Reads ledger from last 2 hours to determine system health
4. **State Logging:** Writes to `logs/circuit-breaker-health.log`

**Cron Configuration:**
```bash
*/5 * * * * cd ~/.openclaw/agents/main && python3 scripts/circuit_breaker_health.py >> logs/circuit-breaker-health.log 2>&1
```

**Exit Codes:** 0 = success, 1 = import error

**State Machine:**
```
CLOSED --(failure_threshold)--> OPEN --(recovery_timeout)--> HALF_OPEN --(success)--> CLOSED
                                                              |
                                                            (failure)
                                                              |
                                                              v
                                                           OPEN
```

**Related Documentation:** `docs/architecture.md` — Circuit breaker design reference

---

## Phase 2: TOCK — Agent Effectiveness Metrics

**Script:** `scripts/tock-gather.sh`
**Frequency:** Every 30 minutes
**Timeout:** 30s (Python alarm)

### Responsibilities

1. **Per-Agent Metrics**
   - Tasks completed, failed, pending
   - Average completion time
   - Delegation counts
   - Error rates

2. **System-Level Metrics**
   - Queue depth trends
   - Throughput velocity
   - Bottleneck identification
   - Model performance data

3. **Workload Assessment**
   - Brief LLM call to classify system state
   - Identifies anomalies requiring attention

### Outputs

| File | Format | Purpose |
|------|--------|---------|
| `logs/tock/<date>/<time>.json` | JSON | Full snapshot |
| `logs/tock/latest.json` | Symlink | Latest data reference |
| `logs/tock.log` | Append log | One-liner per tock |

### Data Flow

```
tock-gather.sh → Neo4j queries → JSON snapshot → kurultai reflection input
```

---

## Phase 3: KURULTAI — Reflection & Self-Improvement

**Script:** `scripts/hourly_reflection.sh`
**Frequency:** Every 60 minutes (4-hour cycle in production)
**Timeout:** 7200s (2 hours) with checkpoints

### Responsibilities

1. **Agent Reflection** (protocol mode, ~800 tokens/agent)
   - Analyze recent performance
   - Review behavioral rules compliance
   - Generate improvement proposals
   - Commitment tracking across sessions

2. **Voting Cycle**
   - All agents review each other's proposals
   - 24-hour voting window
   - Consensus-based approval

3. **Content Generation**
   - Hourly reports
   - Behavioral rule updates
   - Documentation improvements

### Concurrency Control

```bash
MAX_CONCURRENT=3           # Reflection spawns
MAX_CONCURRENT_REVIEW=3    # Review spawns
MAX_LOAD=4.0              # System load threshold
```

### Batching Strategy

| Batch | Agents | Timeout (per batch) |
|-------|--------|---------------------|
| 1 | kublai, temujin, mongke | 180s |
| 2 | chagatai, tolui | 120s |
| 3 | jochi, ogedei | 600s (extended) |

### Outputs

| File | Purpose |
|------|---------|
| `logs/reflection-status.json` | Checkpoint after core reflections |
| `logs/reflection-step-timing.json` | Performance telemetry |
| `proposals/<agent>-<timestamp>.md` | Agent proposals |
| `proposals/voting/<id>-votes.json` | Vote tallies |

---

## Timing Dependencies

```
TICK (5m)  ──┐
             ├──> TOCK (30m) ──> KURULTAI (60m)
TICK (5m)  ──┘

Critical Path:
1. Tick generates health data
2. Tock consumes tick data + adds agent metrics
3. Kurultai consumes tock data + generates proposals
```

### Failure Cascades

| Phase Fails | Impact | Recovery |
|-------------|--------|----------|
| TICK | No health data, tasks stall | Auto-restart on next cron |
| TOCK | Kurultai lacks metrics | Use cached `latest.json` |
| KURULTAI | No self-improvement | Continue normal ops |

---

## Cron Configuration

**Location:** `~/Library/LaunchAgents/` (launchd on macOS)

```xml
<!-- Tick (5 min) -->
<key>StartInterval</key>
<integer>300</integer>

<!-- Tock (30 min) -->
<key>StartInterval</key>
<integer>1800</integer>

<!-- Kurultai (60 min) -->
<key>StartInterval</key>
<integer>3600</integer>
```

---

## Troubleshooting

### TICK: Gap Detected

**Symptom:** `gap_minutes > 8` in tick output

**Diagnosis:**
1. Check cron/launchd: `launchctl list | grep openclaw`
2. Check lock file: `ls -la /tmp/watchdog-gather.lock`
3. Check watchdog log: `tail -50 logs/watchdog.log`

**Recovery:**
```bash
# Remove stale lock
rm -rf /tmp/watchdog-gather.lock
# Restart cron job
launchctl start com.openclaw.watchdog
```

### TOCK: Neo4j Timeout

**Symptom:** `logs/tock.log` shows "SKIP: already running"

**Diagnosis:**
1. Check Neo4j: `systemctl status neo4j`
2. Test connectivity: `cypher-shell -u neo4j -p password "RETURN 1"`

**Recovery:**
```bash
# Restart Neo4j if down
brew services restart neo4j
```

### KURULTAI: Reflection Timeout

**Symptom:** `logs/reflection-status.json` missing after 20 min

**Diagnosis:**
1. Check concurrent agents: `ps aux | grep claude-agent`
2. Check system load: `uptime`

**Recovery:**
```bash
# Kill stuck reflection processes
pkill -9 -f "claude-agent.*reflection"
# Remove checkpoint
rm -f logs/reflection-status.json
# Restart on next cycle
```

---

## Data Freshness Thresholds

| Metric | Fresh Window | Stale Action |
|--------|--------------|--------------|
| Tick data | 10 min | Alert + retry |
| Tock snapshot | 45 min | Use cache |
| Auth heartbeat | 5 min | Skip recheck |
| Reflection data | 90 min | Warning |

---

## Related Documentation

- `docs/heartbeat-quickref.md` — **Quick-reference card for incidents** (one-page diagnostics)
- `docs/auth-heartbeat-reference.md` — Credential monitoring details
- `docs/heartbeat-troubleshooting.md` — Tick gap diagnosis guide
- `docs/reflection-pipeline-reference.md` — Kurultai cycle details
- `docs/architecture.md` — System architecture overview

---

## Implementation History

| Date | Change |
|------|--------|
| 2026-03-12 | Added heartbeat-quickref.md — one-page diagnostic card for incident response |
| 2026-03-12 | Added circuit breaker health monitor documentation (deadlock prevention) |
| 2026-03-12 | Created unified heartbeat system documentation |
| 2026-03-11 | Added auth heartbeat pre-filter for completed tasks |
| 2026-03-08 | Extended kurultai timeout to 600s for jochi/ogedei |
| 2026-03-07 | Implemented 4-hour reflection cycle (reduced from 1-hour) |
