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

## Implementation Order

| Priority | Task | Estimated Effort |
|----------|------|------------------|
| 1 | Task consumer | 2-3 hours |
| 2 | Schedule clarity | 30 min |
| 3 | Git noise reduction | 1 hour |
| 4 | Signals.md locking | 1 hour |
| 5 | Daemon resilience | 2 hours |
| 6 | Parse monitoring | 1 hour |

**Start with:** Priority 6 (quick win), then 1 (high impact).