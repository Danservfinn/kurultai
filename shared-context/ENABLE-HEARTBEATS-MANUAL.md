# Enable Heartbeats — Manual Guide

**The browser tool cannot access the local dashboard reliably.**

**You need to do this manually (5 minutes):**

---

## Step 1: Open Dashboard

**URL:** http://10.200.136.34:18789/

This opens in your local browser.

---

## Step 2: Navigate to Agents

1. Look for **"Agents"** or **"Sessions"** in the left sidebar
2. Click it
3. You should see 6 agents listed:
   - Kublai (main)
   - Möngke (mongke)
   - Chagatai (chagatai)
   - Temüjin (temujin)
   - Jochi (jochi)
   - Ögedei (ogedei)

---

## Step 3: Enable Heartbeat for Each Agent

**For EACH of the 5 agents (not Kublai - already enabled):**

1. Click on the agent name
2. Look for **"Heartbeat"**, **"Schedule"**, or **"Cron"** section
3. Click **"Enable"** or toggle the switch
4. Set interval: **30 minutes** (or cron: `*/30 * * * *`)
5. Click **"Save"** or **"Apply"**

**Checklist:**
- [ ] Möngke — Heartbeat enabled (30m)
- [ ] Chagatai — Heartbeat enabled (30m)
- [ ] Temüjin — Heartbeat enabled (30m)
- [ ] Jochi — Heartbeat enabled (30m)
- [ ] Ögedei — Heartbeat enabled (30m)

---

## Step 4: Verify

Open terminal and run:

```bash
openclaw status
```

**Expected output:**

```
│ Heartbeat │ 30m (main), 30m (mongke), 30m (chagatai), 
│           │ 30m (temujin), 30m (jochi), 30m (ogedei) │
```

**If you see `disabled` for any agent:**
- Go back to Step 3 for that agent
- Make sure you clicked "Save" or "Apply"

---

## Step 5: Test Subagent Spawning

After heartbeats are enabled, each agent can spawn subagents:

```bash
# Temüjin can now spawn 10 coding subagents
# Möngke can now spawn 5 research subagents
# Chagatai can now spawn 5 content subagents
# etc.
```

---

## Why This Matters

**Before:** Only Kublai can spawn subagents (sequential work)

**After:** All 6 agents spawn subagents (parallel work)
- Temüjin: 10x parallel coding
- Möngke: 5x parallel research
- Chagatai: 5x parallel content
- **Total: 31 concurrent subagents**

---

*This unlocks the full multi-agent architecture.*
