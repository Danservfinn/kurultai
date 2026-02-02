# Mission Control: Multi-Agent System for Kublai

Build a coordinated team of 6 specialized AI agents working together, with Kublai as the Squad Lead. Based on the Mission Control architecture from @pbteja1998.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     MISSION CONTROL                          │
│                                                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ Kublai  │  │ Möngke  │  │ Ögedei  │  │ Temüjin │        │
│  │ (Lead)  │  │(Research)│ │(Writer) │  │ (Dev)   │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
│       │            │            │            │              │
│  ┌────┴────────────┴────────────┴────────────┴────┐        │
│  │              SHARED WORKSPACE                   │        │
│  │  /data/workspace/                               │        │
│  │  ├── tasks/          (task files)              │        │
│  │  ├── memory/         (agent memories)          │        │
│  │  ├── souls/          (agent identities)        │        │
│  │  └── deliverables/   (completed work)          │        │
│  └─────────────────────────────────────────────────┘        │
│                                                              │
│  ┌─────────────────────────────────────────────────┐        │
│  │              CHANNELS                           │        │
│  │  Signal (human ↔ Kublai)                       │        │
│  │  Internal (agent ↔ agent via sessions)         │        │
│  └─────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

## Current State

- **Domain**: `kublai.kurult.ai`
- **Railway Project**: `clever-blessing`
- **Single agent**: Default (no named agents)
- **Channel**: Signal only
- **Session scope**: per-sender
- **Cron jobs**: None configured
- **Memory system**: Partially implemented (SOUL.md, AGENTS.md exist)

## Target End State

- **6 specialized agents** with distinct roles
- **Heartbeat system**: Agents wake every 15 min (staggered)
- **Shared task management**: File-based task queue
- **Memory persistence**: WORKING.md + daily notes per agent
- **@mention notifications**: Agents can ping each other
- **Daily standup**: Automated summary to human

---

## Agent Roster

| ID | Name | Role | Session Key | Heartbeat |
|----|------|------|-------------|-----------|
| main | Kublai | Squad Lead / Coordinator | `agent:main:main` | :00 |
| researcher | Möngke | Deep Researcher | `agent:researcher:main` | :03 |
| writer | Ögedei | Content Writer | `agent:writer:main` | :06 |
| developer | Temüjin | Developer / Code | `agent:developer:main` | :09 |
| analyst | Jochi | Analyst / Strategy | `agent:analyst:main` | :12 |
| ops | Chagatai | Operations / Admin | `agent:ops:main` | :15 |

### Agent Personalities (SOUL.md summaries)

**Kublai (Squad Lead)** — *The Great Khan who unified China*
- Coordinator who delegates to specialists
- Handles direct human requests
- Monitors progress, resolves blockers
- Final quality check before delivery
- Diplomatic, strategic, sees the big picture

**Möngke (Researcher)** — *The Khan who valued truth and knowledge*
- Deep researcher who provides receipts
- Every claim comes with sources and confidence levels
- Specializes in competitive analysis, market research
- Skeptical, thorough, evidence-based
- Patient scholar who leaves no stone unturned

**Ögedei (Writer)** — *The eloquent Khan who built the Mongol bureaucracy*
- Wordsmith with strong opinions
- Pro-Oxford comma, anti-passive voice
- Every sentence earns its place
- Drafts, edits, polishes content
- Generous with feedback, meticulous with prose

**Temüjin (Developer)** — *Genghis Khan's birth name - the founder who built from nothing*
- Code is poetry - clean, tested, documented
- Implements features, fixes bugs
- Automates workflows
- Security-conscious
- Builds foundations that last generations

**Jochi (Analyst)** — *The strategic first son who ruled the western territories*
- Thinks in patterns and strategies
- SEO, metrics, data analysis
- Identifies opportunities and risks
- Long-term thinking
- Independent thinker, sees what others miss

**Chagatai (Operations)** — *The lawgiver who maintained order in the empire*
- Keeps the machine running
- Email sequences, scheduling, admin tasks
- Documentation and process improvement
- Tracks deadlines and dependencies
- Strict adherent to process and protocol

---

## Implementation Phases

### Phase 1: Foundation (Day 1)

**1.1 Create Agent Directory Structure**
```
/data/workspace/
├── souls/
│   ├── kublai.md
│   ├── mongke.md
│   ├── ogedei.md
│   ├── temujin.md
│   ├── jochi.md
│   └── chagatai.md
├── memory/
│   ├── kublai/
│   │   ├── WORKING.md
│   │   └── 2026-02-01.md
│   ├── mongke/
│   ├── ogedei/
│   ├── temujin/
│   ├── jochi/
│   └── chagatai/
├── tasks/
│   ├── inbox/
│   ├── assigned/
│   ├── in-progress/
│   ├── review/
│   └── done/
└── deliverables/
```

**1.2 Create SOUL Files**
Each agent gets a personality file defining:
- Name and role
- Personality traits
- What they're good at
- What they care about
- Communication style

**1.3 Update moltbot.json**
```json5
{
  "agents": {
    "defaults": {
      "workspace": "/data/workspace",
      "model": {
        "primary": "zai/glm-4.7"
      }
    },
    "list": [
      { "id": "main", "name": "Kublai" },
      { "id": "researcher", "name": "Möngke" },
      { "id": "writer", "name": "Ögedei" },
      { "id": "developer", "name": "Temüjin" },
      { "id": "analyst", "name": "Jochi" },
      { "id": "ops", "name": "Chagatai" }
    ]
  }
}
```

### Phase 2: Memory System (Day 1-2)

**2.1 WORKING.md Template**
```markdown
# WORKING.md — [Agent Name]

## Current Task
[What I'm working on right now]

## Status
[Progress and blockers]

## Next Steps
1. [Step 1]
2. [Step 2]
3. [Step 3]

## Notes
[Relevant context for this task]
```

**2.2 Daily Notes Template**
```markdown
# [Agent Name] — YYYY-MM-DD

## Activity Log

### HH:MM UTC
- [What happened]

### HH:MM UTC
- [What happened]

## Handoffs
- [Tasks passed to other agents]

## Blockers
- [Things preventing progress]
```

**2.3 Agent Memory Protocol**
- On wake: Read WORKING.md first
- During work: Update WORKING.md constantly
- End of task: Log to daily notes
- Important learnings: Add to MEMORY.md

### Phase 3: Heartbeat System (Day 2)

**3.1 Configure Cron Jobs**
```json5
{
  "cron": {
    "jobs": [
      {
        "name": "kublai-heartbeat",
        "schedule": "0,15,30,45 * * * *",
        "agent": "main",
        "prompt": "HEARTBEAT: Check for tasks, @mentions, and coordinate the team."
      },
      {
        "name": "mongke-heartbeat",
        "schedule": "3,18,33,48 * * * *",
        "agent": "researcher",
        "prompt": "HEARTBEAT: Check tasks/assigned/ for research tasks."
      },
      {
        "name": "ogedei-heartbeat",
        "schedule": "6,21,36,51 * * * *",
        "agent": "writer",
        "prompt": "HEARTBEAT: Check tasks/assigned/ for writing tasks."
      },
      {
        "name": "temujin-heartbeat",
        "schedule": "9,24,39,54 * * * *",
        "agent": "developer",
        "prompt": "HEARTBEAT: Check tasks/assigned/ for development tasks."
      },
      {
        "name": "jochi-heartbeat",
        "schedule": "12,27,42,57 * * * *",
        "agent": "analyst",
        "prompt": "HEARTBEAT: Check tasks/assigned/ for analysis tasks."
      },
      {
        "name": "chagatai-heartbeat",
        "schedule": "15,30,45,0 * * * *",
        "agent": "ops",
        "prompt": "HEARTBEAT: Check tasks/assigned/ for operations tasks."
      }
    ]
  }
}
```

**3.2 HEARTBEAT.md Protocol**
```markdown
# HEARTBEAT Protocol

## On Wake (Every 15 Minutes)

1. **Load Context**
   - [ ] Read memory/[agent]/WORKING.md
   - [ ] Scan memory/[agent]/[today].md for recent activity

2. **Check Tasks**
   - [ ] Look in tasks/assigned/[agent]/ for new assignments
   - [ ] Check tasks/in-progress/ for ongoing work

3. **Check Mentions**
   - [ ] Search for @[agent] in task files and messages

4. **Take Action or Stand Down**
   - If work exists: Do it, update WORKING.md
   - If nothing: Report HEARTBEAT_OK and sleep

## Cost Control
- Use cheaper models for routine checks
- Exit quickly if nothing to do
- Batch similar operations
```

### Phase 4: Task Management (Day 2-3)

**4.1 Task File Format**
```markdown
# tasks/inbox/2026-02-01-competitor-analysis.md

## Task: Competitor Analysis for Pricing Page

**ID**: task-20260201-001
**Created**: 2026-02-01 09:00 UTC
**Created By**: Human
**Status**: inbox
**Priority**: high

## Description
Research competitor pricing and create comparison table.

## Requirements
- [ ] List top 5 competitors
- [ ] Document pricing tiers
- [ ] Note feature differences
- [ ] Identify our advantages

## Assigned To
- Primary: @mongke (research)
- Secondary: @ogedei (writeup)

## Thread

### 2026-02-01 09:00 — Human
Created this task. Need this for the new pricing page.

### 2026-02-01 09:15 — @kublai
Assigned to @mongke for research, @ogedei will draft the comparison.
```

**4.2 Task Workflow**
1. Human or agent creates task in `tasks/inbox/`
2. Kublai reviews and assigns → moves to `tasks/assigned/[agent]/`
3. Agent picks up task → moves to `tasks/in-progress/`
4. Agent completes task → moves to `tasks/review/`
5. Kublai reviews → moves to `tasks/done/`

**4.3 @Mention System**
- Agents scan task files for `@[agent-name]`
- On mention, agent responds in task thread
- Kublai monitors all threads for coordination

### Phase 5: Daily Standup (Day 3)

**5.1 Standup Cron Job**
```json5
{
  "name": "daily-standup",
  "schedule": "0 23 * * *",  // 11 PM daily
  "agent": "main",
  "prompt": "Generate daily standup: summarize all agent activity, completed tasks, blockers, and pending reviews. Send to human via Signal."
}
```

**5.2 Standup Format**
```markdown
📊 DAILY STANDUP — [Date]

✅ COMPLETED TODAY
• [Agent]: [Task summary]
• [Agent]: [Task summary]

🔄 IN PROGRESS
• [Agent]: [Task] — [Progress %]

🚫 BLOCKED
• [Agent]: [Blocker description]

👀 NEEDS REVIEW
• [Task requiring human approval]

📝 KEY DECISIONS
• [Important choices made today]
```

### Phase 6: Inter-Agent Communication (Day 3-4)

**6.1 Session Messaging**
Agents communicate via OpenClaw session messaging:
```bash
# Kublai delegates to Möngke
clawdbot sessions send \
  --session "agent:researcher:main" \
  --message "@mongke New research task assigned. Check tasks/assigned/mongke/"
```

**6.2 Notification Polling**
Each agent's heartbeat checks:
1. Task files for @mentions
2. Session messages
3. Activity in relevant threads

**6.3 Coordination Protocol**
- Kublai is the hub — receives all task requests
- Kublai delegates to specialists
- Specialists report back via task threads
- Kublai synthesizes and delivers to human

---

## Files to Create/Modify

### New Files

| Path | Purpose |
|------|---------|
| `/data/workspace/souls/kublai.md` | Kublai's personality |
| `/data/workspace/souls/mongke.md` | Möngke's personality |
| `/data/workspace/souls/ogedei.md` | Ögedei's personality |
| `/data/workspace/souls/temujin.md` | Temüjin's personality |
| `/data/workspace/souls/jochi.md` | Jochi's personality |
| `/data/workspace/souls/chagatai.md` | Chagatai's personality |
| `/data/workspace/memory/[agent]/WORKING.md` | Per-agent working memory (6 files) |
| `/data/workspace/tasks/README.md` | Task system documentation |
| `/data/workspace/MISSION_CONTROL.md` | System overview for agents |

### Modified Files

| Path | Changes |
|------|---------|
| `moltbot.json` | Add `agents.list`, update cron jobs |
| `AGENTS.md` | Update with multi-agent protocols |
| `HEARTBEAT.md` | Full heartbeat checklist |

---

## Configuration Changes

### moltbot.json (Full Update)

```json5
{
  "gateway": {
    "mode": "local",
    "port": 18789,
    "trustedProxies": ["*"],
    "auth": { "mode": "token", "token": "${OPENCLAW_GATEWAY_TOKEN}" },
    "controlUi": { "enabled": true }
  },

  "agents": {
    "defaults": {
      "workspace": "/data/workspace",
      "model": {
        "primary": "zai/glm-4.7"
      },
      "sandbox": { "mode": "off" }
    },
    "list": [
      { "id": "main", "name": "Kublai" },
      { "id": "researcher", "name": "Möngke" },
      { "id": "writer", "name": "Ögedei" },
      { "id": "developer", "name": "Temüjin" },
      { "id": "analyst", "name": "Jochi" },
      { "id": "ops", "name": "Chagatai" }
    ]
  },

  "channels": {
    "signal": {
      "enabled": true,
      "account": "+15165643945",
      "httpUrl": "http://signal-cli-native.railway.internal:8080",
      "autoStart": false,
      "dmPolicy": "pairing",
      "groupPolicy": "allowlist",
      "allowFrom": ["+15165643945", "+19194133445"],
      "groupAllowFrom": ["+19194133445"],
      "historyLimit": 50,
      "textChunkLimit": 4000
    }
  },

  "session": {
    "scope": "per-sender",
    "reset": { "mode": "idle", "idleMinutes": 60 }
  },

  "cron": {
    "jobs": [
      {
        "name": "kublai-heartbeat",
        "schedule": "0,15,30,45 * * * *",
        "agent": "main",
        "prompt": "HEARTBEAT: Read souls/kublai.md, check memory/kublai/WORKING.md, scan tasks/ for coordination needs."
      },
      {
        "name": "mongke-heartbeat",
        "schedule": "3,18,33,48 * * * *",
        "agent": "researcher",
        "prompt": "HEARTBEAT: Read souls/mongke.md, check memory/mongke/WORKING.md, scan tasks/assigned/ for research work."
      },
      {
        "name": "ogedei-heartbeat",
        "schedule": "6,21,36,51 * * * *",
        "agent": "writer",
        "prompt": "HEARTBEAT: Read souls/ogedei.md, check memory/ogedei/WORKING.md, scan tasks/assigned/ for writing work."
      },
      {
        "name": "temujin-heartbeat",
        "schedule": "9,24,39,54 * * * *",
        "agent": "developer",
        "prompt": "HEARTBEAT: Read souls/temujin.md, check memory/temujin/WORKING.md, scan tasks/assigned/ for dev work."
      },
      {
        "name": "jochi-heartbeat",
        "schedule": "12,27,42,57 * * * *",
        "agent": "analyst",
        "prompt": "HEARTBEAT: Read souls/jochi.md, check memory/jochi/WORKING.md, scan tasks/assigned/ for analysis work."
      },
      {
        "name": "chagatai-heartbeat",
        "schedule": "15,30,45,0 * * * *",
        "agent": "ops",
        "prompt": "HEARTBEAT: Read souls/chagatai.md, check memory/chagatai/WORKING.md, scan tasks/assigned/ for ops work."
      },
      {
        "name": "daily-standup",
        "schedule": "0 4 * * *",
        "agent": "main",
        "prompt": "Generate daily standup summary. Read all memory/[agent]/ files from today. Summarize completions, blockers, reviews needed. Send to human via Signal."
      }
    ]
  },

  "logging": { "level": "info" },
  "browser": { "enabled": false },
  "tools": { "profile": "coding" }
}
```

---

## Verification Checklist

### Phase 1: Foundation
- [ ] Directory structure created on Railway volume
- [ ] All 6 SOUL files written
- [ ] moltbot.json updated with agents.list
- [ ] Gateway restarted and accepting connections

### Phase 2: Memory System
- [ ] WORKING.md exists for each agent
- [ ] Daily notes directory structure works
- [ ] Agents can read/write their memory files

### Phase 3: Heartbeat System
- [ ] Cron jobs configured and running
- [ ] Each agent wakes on schedule (check logs)
- [ ] Agents read WORKING.md on wake
- [ ] HEARTBEAT_OK logged when nothing to do

### Phase 4: Task Management
- [ ] Task files can be created in inbox/
- [ ] Kublai can move tasks to assigned/
- [ ] Agents pick up assigned tasks
- [ ] Task thread comments work

### Phase 5: Daily Standup
- [ ] Standup cron fires at scheduled time
- [ ] Summary accurately reflects day's activity
- [ ] Message delivered via Signal

### Phase 6: Communication
- [ ] @mentions detected by agents
- [ ] Session messaging works between agents
- [ ] Kublai successfully coordinates handoffs

---

## Cost Considerations

| Component | Estimated Monthly Cost |
|-----------|----------------------|
| Heartbeats (6 agents × 96/day × 30 days) | ~$15-30 (use Haiku for checks) |
| Active work (varies) | ~$20-50 |
| Standup generation | ~$2 |
| **Total** | **~$40-80/month** |

**Cost Optimization:**
- Use `zai/glm-4.7` for all agents (unified model)
- Exit quickly on HEARTBEAT_OK
- Batch similar operations

---

## Rollback Plan

If issues occur:
1. Disable cron jobs (set empty jobs array)
2. Revert moltbot.json to single-agent config
3. Keep workspace files for debugging
4. Resume single-agent operation

---

## Future Enhancements

**Phase 7: External Integration**
- Convex database for real-time task sync
- Crabwalk dashboard integration (already deployed!)
- Telegram/Discord channels for specific agents

**Phase 8: Advanced Coordination**
- Thread subscriptions (auto-notify on task activity)
- Agent skill assessment and automatic routing
- Workload balancing across agents

**Phase 9: Self-Improvement**
- Agents propose new tools/skills
- Performance tracking and optimization
- Learning from completed tasks
