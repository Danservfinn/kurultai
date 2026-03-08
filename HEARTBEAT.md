# Kublai Heartbeat Checklist

**Schedule:** Every 30 minutes
**Deep Reflection Hours:** 0, 6, 12, 18 (every 6 hours)

---

## Quick Check (Every 30m) — Miller's Law: 7 Items Max

### 1. Critical Alerts
- [ ] Any CRITICAL escalations from Ögedei or Jochi?

### 2. Infrastructure Pulse
- [ ] Gateway running? Parse/LLM Survivor responding 200?

### 3. Agent Health
- [ ] Any agents blocked >4 hours? Any stuck subagents?

### 4. Task Queue
- [ ] Pending tasks in `~/.openclaw/agents/*/tasks/`? Any fake `.executing.md` files?

### 5. Blocked Items
- [ ] Anything in MEMORY.md blocked >24 hours?

### 6. Self-Direction
- [ ] Review: What changed since last heartbeat? What do I want to do?

### 7. Action or OK
- [ ] If something calls → route to specialist. If nothing → `HEARTBEAT_OK`

<details>
<summary><b>Quick Check Details (Expand for commands)</b></summary>

**Infrastructure Commands:**
```bash
openclaw gateway status
curl -s -o /dev/null -w "%{http_code}" https://www.parsethe.media
curl -s -o /dev/null -w "%{http_code}" https://llmsurvivor.kurult.ai/
```

**Agent Health:**
```bash
# Check for blocked agents
python3 ~/.openclaw/agents/main/scripts/task_intake.py --list-blocked
# Check subagents
subagents list
```

**Task Queue:**
```bash
# Scan for pending tasks
ls ~/.openclaw/agents/*/tasks/*.md 2>/dev/null | grep -v ".executing.md" | wc -l
# Check executing tasks
ls ~/.openclaw/agents/*/tasks/*.executing.md 2>/dev/null
```

**Blocked Items:**
- Check `MEMORY.md` blocked section
- Run: `python3 ~/.openclaw/agents/main/scripts/task_intake.py --stats`
</details>

---

## Deep Reflection (Every 6 Hours — Hours 0,6,12,18)

**Complete these during your deep reflection hours:**

### Self-Awareness
- [ ] Review ARCHITECTURE.md for accuracy
- [ ] Check Change Log is up to date
- [ ] Verify all agent workspaces are correct

### Git & Version Control
- [ ] Commit any uncommitted changes
- [ ] Push to GitHub if needed
- [ ] Update Change Log with major changes

### Coordination
- [ ] Check all agent statuses
- [ ] Resolve any blockers
- [ ] Reprioritize task queue if needed

### Strategic
- [ ] Review progress toward goals
- [ ] Identify opportunities
- [ ] Plan next 6 hours

---

## If Nothing Urgent (Quick Check)

**Reply:** `HEARTBEAT_OK`

---

## If Something Needs Attention

**Report:**
1. What's blocked
2. Which agent is affected
3. What decision/action is needed

---

## Notes

- Quick checks: Every 30 minutes
- Deep reflection: Every 6 hours (hours 0,6,12,18)
- Don't duplicate work between quick and deep checks
