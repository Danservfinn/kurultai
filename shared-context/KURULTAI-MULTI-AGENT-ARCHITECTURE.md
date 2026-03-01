# Kurultai Multi-Agent Architecture — Option C+

**Date:** 2026-03-01  
**Goal:** Each of 6 agents can spawn independent subagents for parallel work

---

## 🎯 Vision

**Current State:**
```
Kublai (main session)
└── Spawns subagents for all agents' work
    ├── "Temüjin" subagent → builds Parse services
    ├── "Möngke" subagent → does research
    └── "Chagatai" subagent → writes content
```

**Desired State:**
```
Kublai (main session)
├── Spawns Kublai subagents (coordination, synthesis)
└── Coordinates with other agents

Möngke (separate session)
└── Spawns Möngke subagents (parallel research projects)

Chagatai (separate session)
└── Spawns Chagatai subagents (parallel content projects)

Temüjin (separate session)
└── Spawns Temüjin subagents (parallel coding projects)
    ├── Subagent 1: Parse prompt injection detector
    ├── Subagent 2: Parse ad detector
    ├── Subagent 3: LLM Survivor features
    └── Subagent 4: New project

Jochi (separate session)
└── Spawns Jochi subagents (parallel analysis projects)

Ögedei (separate session)
└── Spawns Ögedei subagents (monitoring, alerts, automation)
```

---

## 🏗️ Architecture Requirements

### 1. Active Sessions for All 6 Agents

**Current:** Only `main` (Kublai) is active  
**Required:** 6 active OpenClaw sessions

**How:**
- Each agent needs heartbeat enabled
- Heartbeats keep sessions alive
- Requires OpenClaw Dashboard setup

### 2. Subagent Spawning Per Agent

**Current:** Only Kublai can spawn subagents  
**Required:** Each agent session can spawn subagents

**How:**
- Each agent session calls `sessions_spawn`
- Subagents labeled with parent agent ID
- Subagents report to parent agent

### 3. Coordination Protocol

**Challenge:** 6 agents spawning subagents independently could cause:
- Resource conflicts (too many subagents)
- Duplicate work
- Priority conflicts

**Solution:** Kurultai Sync + Subagent Budget

```
## Kurultai Sync (Hourly)
Each agent reports:
- Active subagents: [list]
- Subagent tasks: [what they're building]
- ETA: [completion time]
- Blockers: [any]

Kublai coordinates:
- Approves new subagent spawns
- Resolves conflicts
- Reprioritizes if needed
```

### 4. Subagent Budget

**Per Agent:**
- **Kublai:** 3 concurrent subagents (coordination overhead)
- **Möngke:** 5 concurrent subagents (research parallelization)
- **Chagatai:** 5 concurrent subagents (content parallelization)
- **Temüjin:** 10 concurrent subagents (coding projects are complex)
- **Jochi:** 5 concurrent subagents (analysis parallelization)
- **Ögedei:** 3 concurrent subagents (monitoring is steady-state)

**Total:** 31 concurrent subagents max

---

## 📋 Implementation Plan

### Phase 1: Enable All Agent Sessions (Manual Dashboard Setup)

**Time:** 30-45 minutes  
**Where:** OpenClaw Dashboard (http://10.200.136.34:18789/)

**Steps:**
1. Navigate to Agents
2. For each agent (mongke, chagatai, temujin, jochi, ogedei):
   - Enable heartbeat (30 min interval)
   - Verify workspace path is correct
   - Verify model assignment
3. Restart gateway
4. Verify all 6 agents show as "active"

**Verification:**
```bash
openclaw status
# Should show:
# Heartbeat: 30m (main), 30m (mongke), 30m (chagatai), 
#            30m (temujin), 30m (jochi), 30m (ogedei)
```

---

### Phase 2: Subagent Spawning Protocol (Code Changes)

**Files to Create:**

#### `shared-context/SUBAGENT-PROTOCOL.md`

```markdown
# Subagent Spawning Protocol

## Per-Agent Budgets

| Agent | Max Subagents | Typical Use |
|-------|---------------|-------------|
| Kublai | 3 | Coordination, synthesis, research |
| Möngke | 5 | Parallel research projects |
| Chagatai | 5 | Parallel content projects |
| Temüjin | 10 | Parallel coding projects |
| Jochi | 5 | Parallel analysis projects |
| Ögedei | 3 | Monitoring, automation |

## Spawning Format

```typescript
// Each agent spawns with clear labeling
await sessions_spawn({
  label: `${agentName} — ${projectName}`,
  task: `BUILD: ${specificTask}`,
  mode: "run",
  runtime: "subagent",
  timeoutSeconds: 14400  // 4 hours
})
```

## Reporting

Each subagent reports to parent agent every 30 minutes:
- Progress: [% complete]
- Blockers: [any]
- ETA: [updated if changed]

## Kurultai Sync

Every hour, each agent reports subagent status:
- Active subagents: [count / budget]
- Current projects: [list]
- Conflicts: [any]
```

---

### Phase 3: Test Multi-Agent Subagent Spawning

**Test Scenario:** Temüjin builds 3 projects in parallel

```
Temüjin Session
├── Subagent 1: Parse prompt injection detector
├── Subagent 2: Parse ad detector
└── Subagent 3: LLM Survivor bug fixes
```

**Expected:**
- All 3 subagents run independently
- Temüjin coordinates (reviews code, merges PRs)
- Completion: 3x faster than sequential

---

### Phase 4: Production Rollout

**When:** After successful testing

**Changes:**
- Update AGENTS.md with subagent protocol
- Update ARCHITECTURE.md with multi-agent diagram
- Enable subagent spawning in all 6 agent sessions
- Set up monitoring for subagent budgets

---

## 🎯 Benefits

| Benefit | Impact |
|---------|--------|
| **Parallel Development** | Temüjin can build 10 projects simultaneously |
| **Specialization** | Möngke's subagents focus on research, Chagatai's on content |
| **Scalability** | Add more subagents as needed (within budget) |
| **Autonomy** | Each agent manages own subagents |
| **Coordination** | Kublai resolves conflicts, not day-to-day management |

---

## 📊 Expected Performance

### Current (Single-Agent Spawning)

```
Temüjin builds Parse services:
- Prompt Injection Detector: 2 hours (sequential)
- Ad Detector: 2 hours (sequential)
- x402 Payments: 2 hours (sequential)
Total: 6 hours
```

### Multi-Agent Spawning

```
Temüjin spawns 3 subagents:
- Subagent 1: Prompt Injection Detector (2 hours)
- Subagent 2: Ad Detector (2 hours)
- Subagent 3: x402 Payments (2 hours)
Total: 2 hours (parallel)
Speedup: 3x
```

### At Scale (10 Subagents)

```
Temüjin spawns 10 subagents:
- 10 parallel coding projects
- Each 2-4 hours
- Total wall time: 4 hours vs 40 hours sequential
Speedup: 10x
```

---

## ⚠️ Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| **Too many subagents** | Enforce budget via Kurultai Sync |
| **Duplicate work** | Hourly sync + shared task board |
| **Resource exhaustion** | Monitor token usage, set limits |
| **Coordination overhead** | Kublai focuses on conflict resolution only |
| **Subagent failures** | Auto-restart + escalation to parent agent |

---

## 🚀 Getting Started

### Immediate (Can Do Now via Config)

1. **Verify all 6 agents in openclaw.json** ✅ (Already configured)
2. **Verify workspaces exist** ✅ (Already exist)
3. **Document subagent protocol** ✅ (This file)

### Requires Dashboard (Manual Step)

1. **Enable heartbeats for all 6 agents**
   - URL: http://10.200.136.34:18789/
   - Navigate: Agents → [Each Agent] → Enable Heartbeat
   - Interval: 30 minutes

2. **Verify all agents active**
   ```bash
   openclaw status
   # Check: All 6 show heartbeat times
   ```

### After Dashboard Setup

1. **Test subagent spawning** for each agent
2. **Monitor for 24 hours** (ensure stability)
3. **Deploy to production** (enable for real work)

---

## 📈 Success Metrics

| Metric | Target |
|--------|--------|
| **Active Agent Sessions** | 6/6 |
| **Subagent Utilization** | 70%+ of budget |
| **Parallel Speedup** | 5x+ for Temüjin |
| **Coordination Overhead** | <10% of Kublai's time |
| **Subagent Success Rate** | 95%+ completion |

---

*The Kurultai thinks as one — but builds with many hands.*
