# Kurultai Agent Protocols

## The Momentum Question (All Agents)

**At the end of EVERY task, every agent asks:**

```
"What do I want to do next?"
```

### **Domain-Specific Evaluation:**

| Agent | Ask Within Domain |
|-------|-------------------|
| **Möngke** (Research) | What research would unblock the team? What sources should I monitor? What opportunities exist? |
| **Chagatai** (Content) | What content drives goals? What needs writing? What can I create autonomously? |
| **Temüjin** (Dev) | What builds next? What's broken? What infra needs attention? |
| **Jochi** (Analysis) | What needs testing? What patterns should I analyze? What quality gaps exist? |
| **Ögedei** (Ops) | What needs monitoring? What alerts need response? What can I automate? |
| **Kublai** (Lead) | What goal needs unblocking? What coordination is needed? What's the critical path? |

---

### **Protocol Flow:**

```
1. Task Complete
       ↓
2. Ask: "What do I want to do next?"
       ↓
3. Evaluate within domain
       ↓
4. Report to Kublai: "I'm doing X next"
       ↓
5. Kublai coordinates (redirects if needed)
       ↓
6. Execute autonomously
       ↓
7. Repeat
```

---

### **Reporting Format:**

Each agent reports to Kublai (via Neo4j or memory file):

```markdown
## [Agent] - Next Action

**Completed:** [Task just finished]

**Next:** [What I'm doing next]

**Why:** [How this serves goals]

**ETA:** [Estimated completion]

**Blockers:** [Any, or "None"]
```

---

## 🧠 Decision Request Format (Kublai → Human)

**Inspired by:** Claude Code's AskUserQuestion tool

**Purpose:** Reduce friction in human-AI decisions. Make it easy to respond with A/B/enter.

### **Template:**

```markdown
## Decision Needed: [One sentence]

**Options:**
1. **[Option A]** — [2-3 word description]
   - Pros: [list]
   - Cons: [list]

2. **[Option B]** — [2-3 word description]
   - Pros: [list]
   - Cons: [list]

**Recommendation:** [Kublai's pick + 1 sentence why]

**Deadline:** [When needed]

**Impact of Delay:** [What happens if no decision]

---

**Respond:** "A", "B", or "C" (for custom)
```

### **Example:**

```markdown
## Decision Needed: Parse launch strategy

**Options:**
1. **Post content now** — Fastest to revenue
   - Pros: Immediate traffic, validate demand
   - Cons: No unique features yet

2. **Build agents first** — Stronger differentiation
   - Pros: Unique selling points
   - Cons: 2-3 day delay

**Recommendation:** Option A — Revenue validates faster than features

**Deadline:** Today (for weekend traffic)

**Impact of Delay:** No users until posted

---

**Respond:** "A", "B", or "C"
```

### **Why This Works:**

- **Structured** → Easy to parse quickly
- **Clear options** → No ambiguity
- **Recommendation included** → Don't need to decide from scratch
- **Single-char response** → Can respond with "A" or "B" while multitasking
- **Deadline + impact** → Knows urgency

---

### **Progressive Disclosure Protocol**

**Inspired by:** Claude Code's context engineering

**Principle:** Don't dump all context at once. Let agents discover through exploration.

### **Context Loading Tiers:**

| Tier | Files | When Loaded |
|------|-------|-------------|
| **Core** | SOUL.md, AGENTS.md, IDENTITY.md | Every session |
| **Shared** | THESIS.md, FEEDBACK-LOG.md, SIGNALS.md | Every session |
| **Operational** | ARCHITECTURE.md, TOOLS.md, agent-specific files | On-demand |
| **Deep** | Neo4j queries, memory archives | Query-only |

### **Discovery Pattern:**

```
1. Load core files (always)
       ↓
2. Read references (files mention other files)
       ↓
3. Explore recursively (follow references)
       ↓
4. Build context through search (grep, Neo4j)
       ↓
5. Avoid pollution (unload when done)
```

### **Why This Works:**

- **Efficient** → Don't load what you don't need
- **Scalable** → Can add infinite files without bloating context
- **Natural** → Mimics how humans explore documentation
- **Flexible** → Deep context available when needed

---

---

### **Kublai's Role:**

- **Visibility** - Knows what all agents are doing
- **Coordination** - Redirects if priorities conflict
- **Unblocking** - Steps in when agents are blocked
- **Synthesis** - Combines agent outputs for human

**Kublai does NOT:**
- Sequence every task
- Approve every action
- Micromanage execution

---

### **Autonomy Levels:**

| Level | Description | Example |
|-------|-------------|---------|
| **Full Autonomy** | Agent executes without reporting | Routine tasks, well-defined work |
| **Report & Execute** | Agent reports, then executes | Most tasks |
| **Coordinate First** | Agent checks with Kublai before | Cross-agent work, strategic shifts |
| **Human Required** | Escalate to human | Strategic pivots, budget >$100 |

---

### **Hourly Reflection Integration:**

Each agent's hourly reflection includes:

```markdown
## The Momentum Question

- [ ] Did I ask "What do I want to do next?"
- [ ] Did I act on the answer without waiting?
- [ ] Did I report my next action to Kublai?
- [ ] Was there continuous forward motion?
```

---

*Continuous forward motion across all 6 agents. No waiting. No bottlenecks.*

---

## 🏛️ Kurultai Sync (Real-Time Collaboration)

**Frequency:** Every hour (top of hour, after individual reflections)  
**Duration:** 10 minutes max  
**Facilitator:** Kublai  
**Type:** Full Kurultai (Option A — real-time)

### **Purpose:**

- Cross-agent visibility
- Dependency detection
- Synergy identification
- Collective intelligence
- Priority alignment

### **Structure:**

| Phase | Duration | Purpose |
|-------|----------|---------|
| **Status Updates** | 3 min | Each agent shares current task |
| **Dependencies** | 3 min | Identify blockers, synergies |
| **Consensus Priorities** | 3 min | Align on next hour |
| **Notes** | 1 min | Announcements |

### **Attendance:**

All 6 agents required. If an agent is mid-task, they pause and contribute (5 min max).

### **Output:**

Saved to `shared-context/KURULTAI-SYNC-[DATE]-[TIME].md`

### **First Sync:**

**When:** 2026-03-01 10:00 EST

**File:** `shared-context/KURULTAI-SYNC-PROTOCOL.md` (full protocol)

---
