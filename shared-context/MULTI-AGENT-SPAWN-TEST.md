# Multi-Agent Spawning Test Guide

**Purpose:** Verify all 6 agents can spawn subagents independently

**Prerequisites:**
- ✅ Heartbeats enabled (30m for all agents)
- ✅ HEARTBEAT.md files created
- ✅ Agent core files complete

---

## Test 1: Temüjin Spawns 3 Coding Subagents

**Goal:** Verify Temüjin can spawn multiple subagents in parallel

**Command:**
```bash
# From /Users/kublai/.openclaw/agents/main

# Spawn 3 subagents for Temüjin
sessions_spawn --agent temujin --label "Temüjin — Test Subagent 1" --task "BUILD: Test feature 1" --mode run
sessions_spawn --agent temujin --label "Temüjin — Test Subagent 2" --task "BUILD: Test feature 2" --mode run
sessions_spawn --agent temujin --label "Temüjin — Test Subagent 3" --task "BUILD: Test feature 3" --mode run

# Check status
subagents list --recent-minutes 5
```

**Expected:**
- All 3 subagents spawn successfully
- Each runs independently
- All complete within ~5 minutes

---

## Test 2: Möngke Spawns 2 Research Subagents

**Command:**
```bash
# Spawn 2 research subagents for Möngke
sessions_spawn --agent mongke --label "Möngke — Research 1" --task "RESEARCH: Topic A" --mode run
sessions_spawn --agent mongke --label "Möngke — Research 2" --task "RESEARCH: Topic B" --mode run

# Check status
subagents list --recent-minutes 5
```

**Expected:**
- Both subagents spawn successfully
- Each researches independently
- Results reported to Möngke

---

## Test 3: Chagatai Spawns 2 Content Subagents

**Command:**
```bash
# Spawn 2 content subagents for Chagatai
sessions_spawn --agent chagatai --label "Chagatai — Content 1" --task "WRITE: Article A" --mode run
sessions_spawn --agent chagatai --label "Chagatai — Content 2" --task "WRITE: Article B" --mode run

# Check status
subagents list --recent-minutes 5
```

**Expected:**
- Both subagents spawn successfully
- Each writes independently
- Drafts reported to Chagatai

---

## Verify All Subagents

**Command:**
```bash
# List all active subagents
subagents list --recent-minutes 10

# Should show:
# - 3 Temüjin subagents
# - 2 Möngke subagents
# - 2 Chagatai subagents
# Total: 7 concurrent subagents
```

---

## Success Criteria

| Metric | Target |
|--------|--------|
| **Subagents Spawned** | 7+ |
| **All Complete** | Yes |
| **No Errors** | Yes |
| **Reports to Parent** | Yes |

---

## If Tests Fail

**Issue:** "Agent not found"
**Fix:** Verify agent workspace exists:
```bash
ls -la /Users/kublai/.openclaw/agents/temujin/
```

**Issue:** "Heartbeat disabled"
**Fix:** Check heartbeat config:
```bash
openclaw status | grep Heartbeat
```

**Issue:** Subagents timeout
**Fix:** Increase timeout:
```bash
sessions_spawn --timeout-seconds 600 ...
```

---

## Next Steps After Success

1. **Document successful test** in ARCHITECTURE.md
2. **Increase subagent budgets** (if needed)
3. **Start real parallel projects** (not just tests)

---

*This validates the multi-agent architecture is operational.*
