# Enable Heartbeats — Step-by-Step Guide

**You're authenticated and have the dashboard open.**

Follow these exact steps:

---

## Step 1: Find the Agents Page

**Look for one of these in the left sidebar:**
- "Agents"
- "Sessions"  
- "Agent Sessions"

**Click it.**

You should see a list of 6 agents:
- Kublai (main)
- Möngke (mongke)
- Chagatai (chagatai)
- Temüjin (temujin)
- Jochi (jochi)
- Ögedei (ogedei)

---

## Step 2: Enable Heartbeat for Möngke

1. **Click on "Möngke"** or "mongke" in the list
2. **Look for "Heartbeat"**, "Schedule", or "Cron" section
3. **Click "Enable"** or toggle the switch to ON
4. **Set interval to:** `30 minutes` (or cron expression: `*/30 * * * *`)
5. **Click "Save"** or "Apply"

**Verify:** You should see "30m" or "Every 30 minutes" next to Möngke

---

## Step 3: Repeat for Remaining 4 Agents

**Do the same for:**

### Chagatai
- [ ] Click Chagatai
- [ ] Enable heartbeat
- [ ] Set: 30 minutes
- [ ] Save

### Temüjin
- [ ] Click Temüjin
- [ ] Enable heartbeat
- [ ] Set: 30 minutes
- [ ] Save

### Jochi
- [ ] Click Jochi
- [ ] Enable heartbeat
- [ ] Set: 30 minutes
- [ ] Save

### Ögedei
- [ ] Click Ögedei
- [ ] Enable heartbeat
- [ ] Set: 30 minutes
- [ ] Save

---

## Step 4: Verify All Heartbeats

**In terminal, run:**

```bash
openclaw status
```

**Look for this line:**

```
│ Heartbeat │ 30m (main), 30m (mongke), 30m (chagatai), 
│           │ 30m (temujin), 30m (jochi), 30m (ogedei) │
```

**If you see `disabled` for any agent:**
- Go back to the dashboard
- Find that agent
- Make sure heartbeat is enabled and saved

---

## ✅ Done!

Once all 6 show `30m`, the multi-agent architecture is unlocked:

- Temüjin can spawn 10 coding subagents
- Möngke can spawn 5 research subagents
- Chagatai can spawn 5 content subagents
- Jochi can spawn 5 analysis subagents
- Ögedei can spawn 3 ops subagents
- Kublai can spawn 3 coordination subagents

**Total: 31 concurrent subagents**

---

*This enables 10x parallel development velocity.*
