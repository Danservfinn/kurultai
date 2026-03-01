# Kurultai Architecture Gap — Agent Sessions

**Date:** 2026-03-01  
**Issue:** Only Kublai (main) is running as an OpenClaw agent session

---

## 🎯 Current State

| Agent | Directory | Memory Files | OpenClaw Session |
|-------|-----------|--------------|------------------|
| **Kublai** | ✅ `/agents/main` | ✅ Yes | ✅ Running |
| **Möngke** | ✅ `/agents/mongke` | ✅ Yes | ❌ Not running |
| **Chagatai** | ✅ `/agents/chagatai` | ✅ Yes | ❌ Not running |
| **Temüjin** | ✅ `/agents/temujin` | ✅ Yes | ❌ Not running |
| **Jochi** | ✅ `/agents/jochi` | ✅ Yes | ❌ Not running |
| **Ögedei** | ✅ `/agents/ogedei` | ✅ Yes | ❌ Not running |

---

## 📋 How "6 Agents" Currently Works

The Kurultai operates through **simulation**, not separate sessions:

| Mechanism | How It Works |
|-----------|--------------|
| **Hourly Reflections** | Rotating schedule (Kublai 0:00, Möngke 1:00, etc.) |
| **Memory Separation** | Each agent has own `memory/YYYY-MM-DD.md` |
| **Kurultai Sync** | Hourly meeting (all agents "attend" via shared file) |
| **Subagents** | Specialized workers spawned for specific tasks |

**This works** for coordination, but lacks true agent autonomy.

---

## 🔧 Current Workaround: Subagents as "Temüjin Proxies"

When Temüjin needs to build something:

```
Kublai → Spawns subagent → Subagent does Temüjin's work → Reports to Kublai
```

**Pros:**
- ✅ Work gets done
- ✅ Specialized focus
- ✅ No session management overhead

**Cons:**
- ❌ Not true agent autonomy
- ❌ Subagent dies after task (no continuity)
- ❌ Temüjin's "personality" not preserved
- ❌ Can't build long-term expertise

---

## 📊 Options for True Multi-Agent Architecture

### Option A: Continue with Subagents (Current)

**Status:** Working now

| Pro | Con |
|-----|-----|
| Simple | Not true agents |
| Work gets done | No continuity |
| Low overhead | Temüjin "simulated" |

**Best for:** Early stage, <10 paying users

---

### Option B: Persistent Subagent Sessions

Spawn each agent as a persistent subagent session:

```
Kublai (main)
├── Möngke (persistent subagent)
├── Chagatai (persistent subagent)
├── Temüjin (persistent subagent)
├── Jochi (persistent subagent)
└── Ögedei (persistent subagent)
```

| Pro | Con |
|-----|-----|
| True agent sessions | More complex |
| Continuity between tasks | Higher token usage |
| Each agent builds expertise | Need session management |

**Best for:** 10-100 paying users

---

### Option C: Reconfigure OpenClaw for 6 Agents

Add all 6 agents to `openclaw.json`:

```json
{
  "agents": {
    "list": [
      {"id": "main", "name": "Kublai", ...},
      {"id": "mongke", "name": "Möngke", ...},
      {"id": "chagatai", "name": "Chagatai", ...},
      {"id": "temujin", "name": "Temüjin", ...},
      {"id": "jochi", "name": "Jochi", ...},
      {"id": "ogedei", "name": "Ögedei", ...}
    ]
  }
}
```

| Pro | Con |
|-----|-----|
| Cleanest architecture | Config changes needed |
| Each agent is "real" | 6x gateway overhead |
| True autonomy | Complex routing |

**Best for:** 100+ paying users

---

## 🎯 Recommendation

**Now (0 paying users):** Option A — Subagents work fine
- Focus on revenue, not architecture
- Subagents build Parse services
- Upgrade when we have paying users

**At 10 paying users:** Option B — Persistent subagent sessions
- Each agent has continuity
- Better expertise building
- Manageable complexity

**At 100 paying users:** Option C — Full 6-agent OpenClaw config
- True autonomy
- Justifies overhead
- Enterprise-grade architecture

---

## 📝 Current Task Status (Subagents as Temüjin)

| Task | Subagent | Status | ETA |
|------|----------|--------|-----|
| **Prompt Injection Detector** | `c1373ede...` | 🔄 Running (10m) | EOD |
| **Ad Detector** | `011ade48...` | 🔄 Running (9m) | Tomorrow EOD |
| **x402 Payments** | `b540dacc...` | 🔄 Running (6m) | Day 3 EOD |

**Work IS getting done.** The architecture gap doesn't block progress.

---

## 🚀 Upgrade Path

```
Now (Option A)
  ↓ [10 paying users]
Persistent Sessions (Option B)
  ↓ [100 paying users]
Full 6-Agent Config (Option C)
```

**Document this. Upgrade when revenue justifies it.**

---

*The Kurultai thinks as one — whether through simulation or true separation.*

---

## ⚠️ Why Not Full 6-Agent Sessions? (2026-03-01 Investigation)

**Attempted:** Enable heartbeats via CLI

**Commands tried:**
```bash
openclaw agent heartbeat -m "message" --agent mongke
# Error: too many arguments

openclaw agent heartbeat enable --agent mongke
# Error: required option '-m' not specified
```

**Result:** Heartbeats can ONLY be enabled via OpenClaw Dashboard (web UI)
- Navigate to: http://10.200.136.34:18789/
- Go to: Agents → [Agent Name] → Enable Heartbeat
- CLI doesn't support heartbeat enablement

**Decision:** Continue with subagents until revenue justifies dashboard setup time

**Current subagents building Parse services:**
- Prompt Injection Detector (running)
- Ad Detector (running)
- x402 Payments (running)

**Work IS getting done.** Architecture upgrade when we have 10+ paying users.

---

*The Kurultai thinks as one — whether through simulation or true separation.*
