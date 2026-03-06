# Kublai Heartbeat Checklist

**Schedule:** Every 30 minutes  
**Deep Reflection Hours:** 0, 6, 12, 18 (every 6 hours)

---

## Quick Check (Every 30m)

### Infrastructure
- [ ] **Gateway:** `openclaw gateway status` → running?
- [ ] **Sessions:** Recent activity in last 30 min?
- [ ] **Parse:** `curl -s -o /dev/null -w "%{http_code}" https://www.parsethe.media` → 200?
- [ ] **LLM Survivor:** `curl -s -o /dev/null -w "%{http_code}" https://llmsurvivor.kurult.ai/` → 200?

### Agent Health
- [ ] Any CRITICAL escalations from Ögedei?
- [ ] Any agents blocked >4 hours?
- [ ] `subagents list` → any stuck?

### Kanban Dispatch Protocol (Every Heartbeat)
- [ ] **Check Notion kanban:** Query board for "Pending" tasks
- [ ] **Dispatch tasks:** For each pending task:
  - Read task details from Notion
  - Create task file for assigned agent (use task_intake.py)
  - Update Notion status to "Executing"
- [ ] **Verify dispatch:** Confirm task files created and agents picked up tasks
- [ ] **Note:** Use `notion_tasks.py list --status Pending` and `notion_tasks.py update <id> --status Executing`

### Kanban Execution Verification (Every Heartbeat)
- [ ] **Check executing tasks:** Query Notion for "Executing" status tasks
- [ ] **Verify execution:** For each executing task:
  - Check if task file exists in agent workspace
  - Check if agent process is running
  - If task not truly executing: Re-create task file and dispatch to agent
- [ ] **Activate agents:** If assigned agent is idle, create task file to activate them
- [ ] **Use local LLM:** Leverage ollama/qwen3.5:9b to verify task execution status

### Self-Direction (Every Heartbeat)
- [ ] **Review results:** What happened since last heartbeat? Any new signals/tasks/escalations?
- [ ] Ask: **"What do I want to do?"**
- [ ] Review current goals/missions from MEMORY.md
- [ ] Identify any proactive action I could take
- [ ] If something calls to me -> route it to the right specialist (NEVER self-execute specialist work)
- [ ] If nothing urgent → respond `HEARTBEAT_OK`

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
