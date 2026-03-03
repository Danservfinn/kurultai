# System Improvement Plan

## Priority 1: Fix Code Path for LLM-Generated Tasks

**Problem:** `context_review` writes tasks to `temujin/tasks/llm-review-*.md` but nothing consumes/executes them.

**Solution:**
1. Create a `temujin/task-consumer.sh` that runs every 15 min
2. Scans `temujin/tasks/` for new `.md` files
3. Parses for `code_needed` flag
4. Spawns isolated ACP session to execute via `sessions_spawn(runtime="acp")`
5. Marks task complete or escalates on failure

---

## Priority 2: Kurultai Redundancy Review

**Problem:** Kublai runs hours 0, 6, 12... but also appears in 6-agent rotation.

**Current Schedule (from description):**
- Hour 0: Kublai
- Hour 1: Möngke
- Hour 2: Chagatai
- Hour 3: Temüjin
- Hour 4: Jochi
- Hour 5: Ögedei
- Hour 6: Kublai ← duplicate?

**Solution:** Clarify intent:
- If Kublai = "top agent" → run every hour
- If 6-agent rotation intentional → remove Kublai from rotation, keep separate schedule
- Update CRON jobs accordingly

---

## Priority 3: Git Commit Noise Reduction

**Problem:** 6 agents × hourly commits = up to 6 commits/hour even with no changes.

**Solution:**
1. Modify `hourly_reflection.sh` to:
   ```bash
   if git diff --quiet && git diff --cached --quiet; then
     echo "No changes to commit"
     exit 0
   fi
   ```
2. Only commit if actual diff exists
3. Consider grouping: agents report to single "daily digest" commit

---

## Priority 4: Signals.md Concurrency

**Problem:** Multiple agents writing to `SIGNALS.md` simultaneously = race conditions.

**Solution Options:**
- **Option A:** Use `flock` on writes: `flock -n /path/to/SIGNALS.md -c "echo >> file"`
- **Option B:** Split by agent: `SIGNALS.kublai.md`, `SIGNALS.jochi.md`, etc.
- **Option C:** Use Neo4j instead of flat file (recommended)

**Recommended:** Option C - migrate to Neo4j Decision/Escalation nodes.

---

## Priority 5: Heartbeat Daemon Resilience

**Problem:** If `jochi/memory_curation_rapid` hangs, daemon doesn't recover.

**Solution:**
1. Add watchdog in heartbeat daemon:
   ```python
   # Pseudocode
   for child in children:
       if child.running > 10 * cycle_time:
           child.kill()
           child.restart()
   ```
2. Add `/proc` or `ps` health check in daemon
3. Restart whole daemon if >2 children fail

---

## Priority 6: Parse Deployment Monitoring

**Problem:** No alert when Parse goes down.

**Solution:**
1. Add to HEARTBEAT.md quick check:
   - `curl -s -o /dev/null -w "%{http_code}" https://parsethe.media/parse`
   - If != 200 → flag as blocked
2. Add Railway health check cron (every 15 min)
3. Store deployment status in Neo4j

---

## Priority 7: Agent Harness Monitoring

**Problem:** No visibility into whether the 6-agent Kurultai harness is actually working — agents could be failing silently.

**Solution:** Add to HEARTBEAT.md quick check:

### 7.1 Gateway Status
```bash
openclaw gateway status
# Verify: status = running, uptime > 0
```

### 7.2 Active Sessions Check
```bash
# Check sessions/ for recent activity
ls -lt sessions/*.jsonl | head -3
# Flag if most recent > 30 min old
```

### 7.3 Cron Jobs Health
```bash
# Verify Kurultai cron jobs exist and are enabled
cron list --includeDisabled=false
# Expected: hourly_reflection for each agent
```

### 7.4 Sub-agent Health
```bash
subagents list
# Check for stuck/stalled sub-agents
```

### 7.5 Session Success Rate
- Parse recent session JSONLs for error patterns
- Track: success vs. failed agent turns per hour
- Store in Neo4j: `SessionMetrics` node

### 7.6 Alerting
| Condition | Action |
|-----------|--------|
| Gateway down | Signal Kublai immediately |
| No sessions > 1 hour | Flag as blocked |
| >50% failed turns | Escalate to Kublai |
| Cron jobs disabled | Alert + auto-reenable |

---

## Implementation Status

| Priority | Task | Status | Notes |
|----------|------|--------|-------|
| 1 | Task consumer | ✅ Done | Script + cron job added (every 15 min) |
| 2 | Schedule clarity | ⏳ Pending | Needs human clarification |
| 3 | Git noise reduction | ✅ Done | Already in hourly_reflection.sh |
| 4 | Signals.md locking | ⏳ Pending | Neo4j migration needed |
| 5 | Daemon resilience | ⏳ Pending | Requires Python daemon update |
| 6 | Parse monitoring | ✅ Done | Added to HEARTBEAT.md |
| 7 | Agent harness monitoring | ✅ Done | Added to HEARTBEAT.md + Self-Direction |

**Completed:** 4/7 priorities
**Remaining:** 3 (require design decisions or deeper work)