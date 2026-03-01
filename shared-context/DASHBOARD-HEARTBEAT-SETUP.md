# OpenClaw Dashboard — Enable 6-Agent Heartbeats

**Purpose:** Enable heartbeats for all 6 Kurultai agents to enable multi-agent subagent spawning

**URL:** http://10.200.136.34:18789/

**Time Required:** 30-45 minutes

---

## 📋 Step-by-Step Instructions

### Step 1: Open Dashboard

```
URL: http://10.200.136.34:18789/
```

You should see the OpenClaw Gateway dashboard.

---

### Step 2: Navigate to Agents

1. Click **"Agents"** in the left sidebar
2. You should see 6 agents listed:
   - Kublai (main)
   - Möngke (mongke)
   - Chagatai (chagatai)
   - Temüjin (temujin)
   - Jochi (jochi)
   - Ögedei (ogedei)

---

### Step 3: Enable Heartbeat for Each Agent

**For EACH of the 5 non-main agents:**

1. Click on the agent name (e.g., "Möngke")
2. Find **"Heartbeat"** or **"Schedule"** section
3. Click **"Enable Heartbeat"**
4. Set interval: **30 minutes** (or `*/30 * * * *`)
5. Click **"Save"** or **"Apply"**

**Repeat for:**
- [ ] Möngke
- [ ] Chagatai
- [ ] Temüjin
- [ ] Jochi
- [ ] Ögedei

**Note:** Kublai (main) already has heartbeat enabled.

---

### Step 4: Verify Heartbeats

After enabling all 5 agents, verify via CLI:

```bash
openclaw status
```

**Expected output:**
```
│ Heartbeat       │ 30m (main), 30m (mongke), 30m (chagatai), 30m (temujin), 30m (jochi), 30m (ogedei) │
```

**If you see:**
- `disabled` for any agent → Go back to Step 3 for that agent
- All show `30m` → ✅ Success!

---

### Step 5: Restart Gateway (Optional)

To ensure all changes take effect:

```bash
openclaw gateway restart
```

Wait 30 seconds for gateway to restart.

---

### Step 6: Verify All Agents Active

```bash
openclaw status
```

**Check:**
- All 6 agents show in "Agents" section
- All 6 show heartbeat times
- No errors

---

## 🎯 After Heartbeats Enabled

### Test Subagent Spawning for Each Agent

**Temüjin Test:**
```
Temüjin should now be able to:
- Spawn subagent 1: Parse prompt injection detector
- Spawn subagent 2: Parse ad detector
- Spawn subagent 3: LLM Survivor features
- All running in parallel
```

**Expected:** Each agent can spawn subagents independently.

---

## ⚠️ Troubleshooting

### Issue: "Agent not found"

**Cause:** Agent workspace path incorrect

**Fix:**
1. Check agent config in dashboard
2. Verify workspace path:
   - Möngke: `/Users/kublai/.openclaw/agents/mongke`
   - Chagatai: `/Users/kublai/.openclaw/agents/chagatai`
   - Temüjin: `/Users/kublai/.openclaw/agents/temujin`
   - Jochi: `/Users/kublai/.openclaw/agents/jochi`
   - Ögedei: `/Users/kublai/.openclaw/agents/ogedei`

---

### Issue: "Heartbeat won't enable"

**Cause:** Gateway may need restart

**Fix:**
```bash
openclaw gateway restart
```
Then try enabling heartbeat again.

---

### Issue: Dashboard won't load

**Cause:** Gateway may be stopped

**Fix:**
```bash
openclaw gateway start
```
Then refresh dashboard.

---

## ✅ Success Criteria

After completing this setup:

- [ ] All 6 agents show heartbeat in `openclaw status`
- [ ] Each agent can spawn subagents independently
- [ ] Kurultai Sync meetings include all 6 agents
- [ ] Subagent budgets enforced (31 total max)

---

## 📊 Expected Outcome

**Before:**
```
Kublai spawns ALL subagents (sequential)
- 3 subagents, 45-60 min each
- Total: 2-3 hours
```

**After:**
```
Each agent spawns THEIR OWN subagents (parallel)
- Temüjin: 10 subagents, 45-60 min each
- Möngke: 5 subagents, 30 min each
- Chagatai: 5 subagents, 30 min each
- Total wall time: 60 min
- Speedup: 10x for Temüjin
```

---

*This unlocks the full multi-agent architecture.*
