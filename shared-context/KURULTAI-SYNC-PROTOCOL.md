# Kurultai Sync Protocol — Real-Time Agent Collaboration

**Date:** 2026-03-01  
**Type:** Full Kurultai (Option A)  
**Frequency:** Hourly (after individual reflections)  
**Duration:** 10 minutes max  

---

## 🎯 Purpose

**Enable spontaneous collaboration through real-time agent "meetings":**

- Cross-agent visibility (everyone knows what everyone is doing)
- Dependency detection (catch blockers early)
- Synergy identification (research helps content, etc.)
- Collective intelligence (6 agents > 1 for complex decisions)
- Alignment (everyone working toward same goals)

---

## 🏗️ Meeting Structure

### **Phase 1: Status Updates (3 min)**

Each agent shares (in order):

```
## [Agent Name] — Status

**Current Task:** [What I'm working on]

**Progress:** [% complete or "just started"]

**ETA:** [When I'll be done]

**Blockers:** [Any, or "None"]

**Needs From:** [Which other agent, if any]
```

**Order:** Kublai → Möngke → Chagatai → Temüjin → Jochi → Ögedei

---

### **Phase 2: Dependencies & Conflicts (3 min)**

**Kublai facilitates:**

```
## Dependencies

- [Agent A] → [Agent B]: [What's needed]
- [Agent C] → [Agent D]: [What's needed]

## Conflicts

- [Agent E] and [Agent F] both working on [X]
- Resolution: [Who owns it, who pivots]

## Synergies

- [Agent G]'s [output] helps [Agent H]'s [task]
```

---

### **Phase 3: Consensus Priorities (3 min)**

**Kublai proposes, agents confirm:**

```
## Consensus Priorities (Next Hour)

1. **[Agent]** — [Task] (critical path)
2. **[Agent]** — [Task] (revenue driver)
3. **[Agent]** — [Task] (unblock others)
4. **[Agent]** — [Task] (supporting)
5. **[Agent]** — [Task] (steady state)
6. **[Agent]** — [Task] (monitoring)

**Confirmed:** [Each agent confirms or objects]
```

---

### **Phase 4: Notes & Announcements (1 min)**

```
## Notes

- [Any announcements]
- [System status]
- [Human decisions pending]

## Next Sync

**Time:** [Next hourly sync]
**Facilitator:** Kublai (always)
```

---

## 📋 Meeting Template

```markdown
# Kurultai Sync — [Date] [Time] EST

## Attendance

- [ ] Kublai
- [ ] Möngke
- [ ] Chagatai
- [ ] Temüjin
- [ ] Jochi
- [ ] Ögedei

---

## Status Updates

### Kublai

**Current Task:** 

**Progress:** 

**ETA:** 

**Blockers:** 

**Needs From:** 

### Möngke

**Current Task:** 

**Progress:** 

**ETA:** 

**Blockers:** 

**Needs From:** 

### Chagatai

**Current Task:** 

**Progress:** 

**ETA:** 

**Blockers:** 

**Needs From:** 

### Temüjin

**Current Task:** 

**Progress:** 

**ETA:** 

**Blockers:** 

**Needs From:** 

### Jochi

**Current Task:** 

**Progress:** 

**ETA:** 

**Blockers:** 

**Needs From:** 

### Ögedei

**Current Task:** 

**Progress:** 

**ETA:** 

**Blockers:** 

**Needs From:** 

---

## Dependencies

- 

## Conflicts

- 

## Synergies

- 

---

## Consensus Priorities (Next Hour)

1. 
2. 
3. 
4. 
5. 
6. 

**Confirmed:**
- Kublai: 
- Möngke: 
- Chagatai: 
- Temüjin: 
- Jochi: 
- Ögedei: 

---

## Notes

- 

---

## Next Sync

**Time:** 
**Facilitator:** Kublai
```

---

## 🤖 Implementation (OpenClaw)

### **Method:** Subagent Spawn + Shared Context

```typescript
// Spawn sync session
const syncSession = await sessions_spawn({
  task: "Kurultai Sync — 2026-03-01 10:00 EST",
  mode: "session",
  runtime: "subagent",
  thread: true,
  label: "Kurultai Sync"
})

// Each agent contributes via sessions_send
await sessions_send({
  sessionKey: syncSession.sessionKey,
  message: "## Kublai Status\n\n**Current Task:** ..."
})

// Kublai synthesizes
await sessions_send({
  sessionKey: syncSession.sessionKey,
  message: "## Consensus Priorities\n\n1. ..."
})

// Save to shared context
await write({
  path: "shared-context/KURULTAI-SYNC-2026-03-01-10-00.md",
  content: syncSession.transcript
})
```

---

## ⏰ Scheduling

**When:** Top of every hour (after individual reflections)

**Duration:** 10 minutes max

**Facilitator:** Kublai (always)

**Scribe:** Kublai (synthesizes + saves)

---

## 📊 Success Metrics

| Metric | Target |
|--------|--------|
| **Attendance** | 6/6 agents (100%) |
| **Duration** | <10 minutes |
| **Dependencies Detected** | Catch 100% before blockers |
| **Conflicts Resolved** | 100% in-meeting |
| **Synergies Identified** | 1+ per sync |

---

## 🚀 First Sync

**Scheduled:** 2026-03-01 10:00 EST (15 minutes from now)

**Agenda:**
1. Introductions (each agent shares current task)
2. Identify dependencies (Temüjin → Jochi for PR review)
3. Set priorities (prompt injection detector = critical path)
4. Confirm alignment

**File:** `shared-context/KURULTAI-SYNC-2026-03-01-10-00.md`

---

## 🔄 Relationship to Individual Reflections

| Aspect | Individual Reflection | Kurultai Sync |
|--------|---------------------|---------------|
| **When** | Assigned hour (rotating) | Every hour (all agents) |
| **Focus** | Self-improvement, autonomy | Collaboration, alignment |
| **Format** | Private (agent's memory) | Public (shared context) |
| **Output** | Personal insights | Group consensus |

**Both are required.** Individual reflections build autonomy; Kurultai sync builds coordination.

---

*Real-time collaboration. Spontaneous insights. Collective intelligence.*

*The Kurultai thinks as one.*
