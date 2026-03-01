# Enable Heartbeats — UI Guide (Based on Your Screenshot)

**You're on the right page! I can see the dashboard.**

---

## Step 1: Click "Cron Jobs" Tab

In your screenshot, I see these tabs at the top:
- Overview ← you're here now
- Files
- Tools
- Skills
- Channels
- **Cron Jobs** ← **CLICK THIS ONE**

**Click on "Cron Jobs"**

---

## Step 2: Enable Heartbeat Cron Job

After clicking "Cron Jobs", you should see:

**A list of cron jobs for this agent, including:**
- "Heartbeat" or "Agent Heartbeat"
- Possibly other scheduled tasks

**For the Heartbeat job:**

1. **Find the "Heartbeat" row**
2. **Click "Enable"** button (or toggle switch)
3. **Set schedule to:** `*/30 * * * *` (every 30 minutes)
4. **Click "Save"** or "Apply"

---

## Step 3: Repeat for All 5 Agents

**In the left sidebar, click each agent and repeat:**

### Möngke
- [ ] Click "Möngke" in sidebar
- [ ] Click "Cron Jobs" tab
- [ ] Enable Heartbeat (30 min)
- [ ] Save

### Jochi
- [ ] Click "Jochi" in sidebar
- [ ] Click "Cron Jobs" tab
- [ ] Enable Heartbeat (30 min)
- [ ] Save

### Ögedei
- [ ] Click "Ögedei" in sidebar
- [ ] Click "Cron Jobs" tab
- [ ] Enable Heartbeat (30 min)
- [ ] Save

### Temüjin
- [ ] Click "Temüjin" in sidebar
- [ ] Click "Cron Jobs" tab
- [ ] Enable Heartbeat (30 min)
- [ ] Save

### Chagatai (you're already here!)
- [ ] Click "Cron Jobs" tab
- [ ] Enable Heartbeat (30 min)
- [ ] Save

---

## Step 4: Verify

**In terminal:**

```bash
openclaw status
```

**Look for:**

```
│ Heartbeat │ 30m (main), 30m (mongke), 30m (chagatai), 
│           │ 30m (temujin), 30m (jochi), 30m (ogedei) │
```

---

## If You Don't See a "Heartbeat" Cron Job

**You may need to CREATE it:**

1. Click "Add Cron Job" or "Create"
2. Fill in:
   - **Name:** `Agent Heartbeat`
   - **Schedule:** `*/30 * * * *`
   - **Command/Task:** `heartbeat` or leave default
3. Click "Save"

---

*The heartbeat keeps the agent session alive and enables subagent spawning.*
