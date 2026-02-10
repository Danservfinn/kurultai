# Multi-Goal Orchestration UX Recommendations

## Executive Summary

Kublai's multi-agent orchestration needs a UX that balances transparency with simplicity. Users should feel in control without being overwhelmed by the complexity of 6-agent coordination.

**Core Philosophy**: Show progress, hide complexity, enable control.

---

## 1. Immediate Feedback

### Recommendation: Brief Confirmation with Opt-Out Details

When Kublai detects synergistic goals, acknowledge immediately but concisely. Users can drill down if they want the "how."

**Conversation Flow:**

```
User: Earn 1,000 USDC
User: Start money-making community

Kublai: I see these goals work together—building a unified strategy.
        Creating earning engine + community foundation in parallel.
        (Reply "details" to see the full plan)
```

**Alternative (Silent Approach):**

```
User: Earn 1,000 USDC
User: Start money-making community

Kublai: Working on integrated strategy. Here's the plan:

        🎯 GOAL 1: Quick Earnings Path
        ├─ @mongke: Research highest-paying freelance platforms
        ├─ @temujin: Build portfolio template
        └─ @chagatai: Draft outreach emails

        🎯 GOAL 2: Community Foundation
        ├─ @jochi: Analyze successful community models
        ├─ @ogedei: Set up Discord infrastructure
        └─ @chagatai: Create launch announcement

        Estimated: 7 days to initial earnings, 14 days to community launch.
```

### Decision Tree

```
IF goals are synergistic (share tasks/agents):
  → Show brief acknowledgment: "I see these work together—building unified strategy"
  → Offer: "Reply 'plan' to see full execution strategy"

IF goals are independent:
  → Process separately, present as parallel tracks

IF goals are sequential:
  → Show dependency: "Starting X first, then Y once X is complete"

IF user sends "plan" or "details":
  → Show goal graph visualization or detailed breakdown
```

---

## 2. Transparency vs. Magic

### Recommendation: Progressive Disclosure

Show agent involvement when relevant, hide when it's noise. Different users want different levels of detail.

**Three Transparency Modes:**

#### Mode 1: Just Results (Default)
```
Kublai: ✅ Earnings research complete
        Found 3 platforms with $50-100/hr rates
        Next: Creating portfolio template
```

#### Mode 2: With Agent Attribution (Triggered by "who" or "team")
```
User: who's working on what?

Kublai: Current assignments:
        @mongke — Platform research (DONE)
        @temujin — Portfolio template (IN PROGRESS)
        @chagatai — Outreach emails (WAITING)
```

#### Mode 3: Full Goal Graph (Triggered by "graph", "visualize", "show all")
```
Kublai: [Goal graph visualization]
        Shows dependencies, agent assignments, progress
        Interactive: click to drill down
```

### Implementation

**In Signal/text interface:**
- Default: Brief status updates
- User types "status", "team", "plan", "graph" → progressive disclosure
- User sets preference: "Always show agent names" vs "Just tell me when it's done"

**In web dashboard (Crabwalk/Steppe):**
- Toggle between "Simple View" and "Agent View"
- Simple: Goals with progress bars
- Agent View: Goal graph with agent nodes

---

## 3. Progress Visibility

### Recommendation: Narrative + Quantitative

Combine story ("$500 earned, 60% complete") with quantifiable metrics (progress bars, time estimates).

**Progress Update Format:**

```
📊 WEEKLY UPDATE — Your Goals

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 EARN 1,000 USDC
Progress: ████████░░ 80% ($800/1000)
Deadline: Feb 18 (3 days ahead)

Recent wins:
• $250 Upwork contract landed
• Portfolio sent to 12 prospects

Next up:
• @chagatai: Follow-up emails to 5 warm leads
• @temujin: Automate invoicing system

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 MONEY-MAKING COMMUNITY
Progress: ████░░░░░░░ 40%
Deadline: Feb 25

Recent wins:
• Discord server configured (@ogedei)
• Launch post draft ready (@chagatai)

Next up:
• @jochi: Competitor analysis
• @mongke: Content strategy research

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 SYNERGY DETECTED
Community members = future freelancers
Building referral program into launch plan
```

**Progress Triggers:**

1. **Milestone reached**: Immediate notification
   ```
   Kublai: 🎉 Milestone! First $100 earned
           Portfolio template converted to paying client
   ```

2. **Agent completes task**: Summarized in daily standup
3. **Weekly summary**: Full progress report (all goals)
4. **On request**: User types "progress", "status", "how's it going"

### Real-Time Progress Indicators

**For long-running tasks:**

```
User: How's the research going?

Kublai: @mongke is 60% through platform research
        Found 8 platforms so far, analyzing:
        • Upwork ✓
        • Fiverr ✓
        • Toptal (investigating)
        • 5 more in queue

        ETA: 2 hours
```

---

## 4. Mid-Course Corrections

### Recommendation: Natural Language Commands

Users should be able to redirect without learning special syntax.

**Supported Commands:**

```
User: Actually, prioritize quick earnings now

Kublai: Got it—shifting focus to speed over strategy

        🔄 REORDERING PRIORITIES
        Goal 1: Quick earnings (HIGH PRIORITY)
        ├─ Pause: Community building
        ├─ Accelerate: Direct outreach
        └─ New plan: Freelance sprint → 3-day earnings target

        Confirm? (yes/no/suggest alternative)
```

**Correction Types:**

1. **Reprioritize**: "Focus on X first", "Pause Y", "Deprioritize Z"
2. **Add goal**: "Also do W" (Kublai detects if it's synergistic or new)
3. **Remove goal**: "Cancel X", "Never mind about Y"
4. **Modify goal**: "Change earnings target to 2,000", "Launch community next week instead"
5. **Split/merge**: "Split earnings into quick vs long-term", "Merge these into one strategy"

**Confirmation Protocol:**

```
IF change affects >1 agent:
  → Show impact: "This reprioritizes 3 agents' workloads"
  → Ask confirmation: "Confirm? (yes/no/show details)"

IF change is minor (single agent):
  → Execute immediately, notify: "Paused community research, focusing Mongke on earnings"
```

**Handling Conflicts:**

```
User: Launch the community tomorrow

Kublai: ⚠️ Tomorrow is aggressive for current progress

        Current state: 40% complete
        To launch tomorrow would require:
        • Skip competitor analysis
        • Use template content vs custom
        • Risk: Lower quality launch

        Options:
        1. Proceed with aggressive timeline (quality risk)
        2. Launch in 3 days (recommended)
        3. Launch MVP tomorrow, full launch in 1 week

        Which approach?
```

---

## 5. Overload Prevention

### Recommendation: Smart Simplification

Prevent cognitive load by grouping, summarizing, and offering "just tell me when it's done" mode.

**Prevention Strategies:**

### Strategy 1: Tiered Detail Levels

**When user sends multiple rapid goals:**

```
User: Earn 1,000 USDC
User: Start money-making community
User: Build automated lead gen
User: Create personal brand
User: Launch course

Kublai: ⚡ Whoa—that's 5 major goals!

        I've grouped them into 2 tracks:

        TRACK 1: Quick Wins (earnings + leads)
        → Generate cash flow fast

        TRACK 2: Long-Term Assets (community + brand + course)
        → Build sustainable business

        Recommend: Start with Track 1, then Track 2
        Or: "I want it all" → Build all 5 in parallel (slower each)

        Which approach?
```

### Strategy 2: Progressive Disclosure

```
User: What's happening with all my goals?

Kublai: 5 goals active across 6 agents

        🎯 HIGH PRIORITY (2 goals)
        • Earnings: 80% complete
        • Lead gen: 60% complete

        🎯 MEDIUM PRIORITY (2 goals)
        • Community: 40% complete
        • Brand: 20% complete

        ⏸️ DEFERRED (1 goal)
        • Course: Paused until others complete

        Reply "detail [goal name]" for full breakdown
```

### Strategy 3: "Headlines Mode" (User-Triggered)

```
User: Just tell me when things are done, skip the updates

Kublai: Got it—headlines mode activated
        I'll notify when:
        • Goals are complete
        • Blockers need your input
        • Major decisions needed

        You won't see routine progress updates.
        Type "status" anytime to catch up.
```

### Strategy 4: Complexity Warnings

```
Kublai: ⚠️ This plan involves 8 agents and 15 tasks

        That's complex! Here are simpler options:

        1. MVP: Launch basic community first (2 agents, 5 tasks)
        2. Phased: Start with earnings, add community later
        3. Full: All goals in parallel (what you asked for)

        Recommend: MVP first
        Or: "I'm ready for complex" → proceed with full plan
```

### Strategy 5: Batch Updates

**Instead of 10 notifications:**

```
Kublai: 📦 BATCH UPDATE — Earnings Goal

        Completed today:
        • Research done
        • Portfolio template built
        • Outreach emails drafted

        Next: Sending to first 10 prospects
        ETA: Tomorrow 10am
```

---

## 6. Goal Detection Logic

### Recommendation: Explicit Classification + User Confirmation

When Kublai detects relationships, explain the reasoning and allow override.

**Classification Examples:**

**Independent Goals:**
```
User: Earn 1,000 USDC
User: Learn Japanese

Kublai: Working on 2 independent goals
        Earnings track (business)
        Learning track (personal)

        Running in parallel, no conflicts detected
```

**Synergistic Goals:**
```
User: Earn 1,000 USDC
User: Start money-making community

Kublai: 💡 These goals are synergistic!

        Community members = potential freelancers = earnings multiplier
        I'm building a unified strategy that:
        • Starts earnings immediately
        • Builds community in parallel
        • Connects them via referral program

        Prefer to keep separate? Reply "split"
```

**Sequential Goals:**
```
User: Create online course
User: Launch to 1,000 students

Kublai: Detected dependency: Course must exist before launch

        📋 SEQUENCE:
        Phase 1: Build course (2 weeks)
        Phase 2: Launch to students (1 week)

        Starting Phase 1 now
```

**Conflicting Goals:**
```
User: Launch product in 1 week
User: Build production-quality system

Kublai: ⚠️ These goals conflict!

        1-week launch = speed over quality
        Production system = quality over speed

        Can't do both well. Options:
        1. MVP launch (quality concessions) → upgrade later
        2. Push launch to 3 weeks → build properly
        3. Launch beta in 1 week, full in 3 weeks

        Which approach?
```

---

## 7. Example Conversation Flows

### Flow 1: Synergistic Goals (Happy Path)

```
User: Earn 1,000 USDC
User: Start money-making community

Kublai: 💡 These work together—building unified strategy
        Earnings fund community, community amplifies earnings

        📋 INTEGRATED PLAN:
        Week 1: Quick earnings (freelance sprints)
        Week 2: Community MVP launch
        Week 3: Merge (community referral program)

        Starting now. Reply "details" for full agent assignments
        Reply "split" to handle separately
```

### Flow 2: Goal Addition Mid-Execution

```
[...2 days into earnings goal...]

User: Also build automated lead generation

Kublai: Adding lead generation to active goals

        🎯 NEW GOAL DETECTED
        This synergizes with earnings—adding to plan

        Updated approach:
        • Quick earnings (ongoing, 80% complete)
        • Lead gen system (NEW, assigned to @temujin)

        Lead gen feeds into earnings pipeline
        No conflicts detected

        Proceeding. Reply "remove" to cancel
```

### Flow 3: Priority Shift

```
[...Community building 40% complete...]

User: Actually, pause community, focus on freelancing

Kublai: 🔀 Pausing community, accelerating freelancing

        IMPACT:
        @ogedei (ops): Paused Discord setup
        @jochi (analyst): Paused competitor analysis
        @mongke (research): SHIFT to freelancing research
        @chagatai (writer): SHIFT to outreach content

        Freelancing timeline: 2 days faster
        Community: Resumes when freelancing hits $1,000

        Confirm? (yes/no)
```

### Flow 4: Complexity Overload Prevention

```
User: Earn 1,000 USDC
User: Start community
User: Build lead gen
User: Create personal brand
User: Launch course
User: Write book
User: Start podcast

Kublai: ⚡ WHOA—that's 7 major goals!

        I've grouped them into 3 tracks:

        ⚡ TRACK 1: IMMEDIATE EARNINGS
        • Freelancing + Lead gen
        → Cash flow in 7 days

        📈 TRACK 2: AUDIENCE BUILDING
        • Community + Brand + Podcast
        → Sustainable growth

        💰 TRACK 3: PRODUCTS
        • Course + Book
        → Passive income

        RECOMMEND: Start with Track 1, add Track 2, then Track 3
        Trying all 7 at once = slow progress on everything

        Options:
        1. Recommended (phased approach)
        2. All in (go big, accept slower pace)
        3. Choose specific tracks

        Which approach?
```

### Flow 5: User Asks for Full Transparency

```
User: Show me everything happening

Kublai: 🔍 FULL TRANSPARENCY MODE

        GOAL GRAPH:
        [Visual: Goals → Agents → Tasks → Dependencies]

        🎯 EARNINGS GOAL
        ├─ @mongke: Platform research
        │  ├─ Analyzed Upwork (DONE)
        │  ├─ Analyzed Fiverr (DONE)
        │  └─ Analyzing Toptal (IN PROGRESS)
        ├─ @temujin: Portfolio template
        │  └─ Building React component (60%)
        └─ @chagatai: Outreach emails
           └─ Drafting sequence (WAITING for research)

        🎯 COMMUNITY GOAL
        ├─ @ogedei: Discord setup
        │  └─ Configuring channels (DONE)
        ├─ @jochi: Competitor analysis
        │  └─ Researching r/freelance (40%)
        └─ @chagatai: Launch post
           └─ Drafting announcement (WAITING)

        DEPENDENCIES:
        • Outreach emails ← Platform research (@mongke)
        • Launch post ← Competitor analysis (@jochi)

        BLOCKERS: None
        ESTIMATED COMPLETION: Feb 18 (earnings), Feb 25 (community)

        Reply "collapse" to return to simple mode
```

### Flow 6: Daily Standup (Automated)

```
Kublai: 📊 DAILY STANDUP — Feb 4, 2026

        ✅ COMPLETED YESTERDAY:
        • @mongke: Analyzed 5 freelance platforms
        • @ogedei: Configured Discord server
        • @temujin: Portfolio template 80% complete

        🔄 IN PROGRESS:
        • Earnings: 60% complete → $0 earned yet, pipeline full
        • Community: 40% complete → On track for Feb 25 launch

        🚫 BLOCKERS: None

        👀 NEEDS INPUT:
        • Portfolio color scheme: Blue or Purple?
        • Discord invite-only or open?

        📝 KEY DECISIONS:
        • Switched to Upwork-only focus (higher rates)
        • Community launch delayed 2 days for better prep

        🎯 TODAY'S PRIORITIES:
        1. Finish portfolio template
        2. Send first 5 outreach emails
        3. Complete competitor analysis

        Reply "ok" to acknowledge
        Reply "reprioritize" to change focus
        Reply "details" for full task list
```

---

## 8. UI Components for Web Dashboard

### Component 1: Goal Cards

```typescript
interface GoalCard {
  id: string;
  title: string;
  progress: number; // 0-100
  status: 'active' | 'paused' | 'completed' | 'blocked';
  assignedAgents: AgentRef[];
  deadline: Date;
  synergyWith?: string[]; // IDs of related goals
}
```

**Visual Design:**
- Card with progress bar
- Agent avatars (small circles)
- Synergy indicators (lines connecting related goals)
- Status badges

### Component 2: Goal Graph Visualization

```typescript
interface GoalGraph {
  nodes: GoalNode[]; // Goals
  edges: SynergyEdge[]; // Connections between goals
  agents: AgentNode[]; // Who's working on what
}
```

**Interactive Features:**
- Hover: Show goal details + assigned agents
- Click: Expand to show tasks
- Filter: Show only active goals, or specific agent's work
- Zoom/pan for complex graphs

### Component 3: Progress Timeline

```typescript
interface TimelineEvent {
  timestamp: Date;
  type: 'milestone' | 'task_complete' | 'blocker' | 'decision';
  goalId: string;
  agent?: AgentRef;
  description: string;
}
```

**Visual Design:**
- Vertical timeline
- Color-coded by event type
- Filter by goal or agent
- Expandable details

### Component 4: Agent Workload Panel

```typescript
interface AgentWorkload {
  agentId: string;
  currentTasks: Task[];
  capacity: number; // 0-100%
  specialization: string[];
}
```

**Visual Design:**
- Grid of agent cards
- Each card shows:
  - Agent avatar + name
  - Current task count
  - Capacity meter
  - Specialization tags
- Click agent: Filter goals by their work

---

## 9. Configuration & Preferences

### User Settings

```typescript
interface UserPreferences {
  transparencyMode: 'simple' | 'normal' | 'detailed';
  progressUpdates: 'realtime' | 'daily' | 'milestones' | 'headlines';
  confirmationRequired: boolean; // Ask before major changes
  autoGroupGoals: boolean; // Automatically detect synergies
  maxConcurrentGoals: number; // Prevent overload
  notificationChannel: 'signal' | 'web' | 'both';
}
```

**Setting Scenarios:**

1. **Hands-off user:**
   ```json
   {
     "transparencyMode": "simple",
     "progressUpdates": "milestones",
     "confirmationRequired": false,
     "autoGroupGoals": true,
     "maxConcurrentGoals": 3
   }
   ```

2. **Control freak user:**
   ```json
   {
     "transparencyMode": "detailed",
     "progressUpdates": "realtime",
     "confirmationRequired": true,
     "autoGroupGoals": false,
     "maxConcurrentGoals": 10
   }
   ```

3. **Balanced user (default):**
   ```json
   {
     "transparencyMode": "normal",
     "progressUpdates": "daily",
     "confirmationRequired": true,
     "autoGroupGoals": true,
     "maxConcurrentGoals": 5
   }
   ```

---

## 10. Anti-Patterns to Avoid

### Don't Do This:

```
❌ Kublai: @mongke is researching platforms... @temujin is writing code... @jochi is analyzing data...
          [50 messages later]

✅ Instead: Batch updates, summarize at milestone
```

```
❌ Kublai: I've created a complex goal graph with 47 nodes and 82 edges...

✅ Instead: "I've grouped your 5 goals into 2 tracks. Here's the plan:"
```

```
❌ Kublai: [Reboots entire plan when user adds 1 small goal]

✅ Instead: "Adding this goal. Fits into existing track, no conflicts."
```

```
❌ Kublai: [Silently executes complex strategy for 3 days]

✅ Instead: Daily standup + milestone notifications
```

```
❌ Kublai: You need to learn these 15 commands to control me...

✅ Instead: Natural language: "pause that", "focus on this", "show status"
```

---

## 11. Implementation Priority

### Phase 1: Core UX (Week 1)
1. Goal detection (independent/synergistic/sequential)
2. Brief acknowledgment messages
3. Progress tracking (basic percentage)
4. Daily standup format

### Phase 2: User Control (Week 2)
1. Natural language reprioritization
2. Goal addition/removal
3. Transparency modes (simple/detailed)
4. Confirmation protocol for major changes

### Phase 3: Smart Features (Week 3)
1. Complexity overload prevention
2. Progressive disclosure ("reply 'details'")
3. Synergy detection and explanation
4. Batch updates

### Phase 4: Web Dashboard (Week 4)
1. Goal graph visualization
2. Agent workload panel
3. Progress timeline
4. User preferences UI

---

## 12. Success Metrics

**User Engagement:**
- Users understand what's happening (confusion rate < 10%)
- Users feel in control (can reprioritize successfully 90% of the time)
- Users aren't overwhelmed (< 5 messages/day for active goals)

**Effectiveness:**
- Goals completed on time (> 80%)
- Synergies detected accurately (> 90% precision)
- Reprioritization executes correctly (> 95%)

**Satisfaction:**
- Users prefer multi-goal orchestration over single-goal (> 70%)
- Users don't disable notifications (> 80% keep them on)
- Users add more goals over time (indicating trust)

---

## Appendix: Command Reference

### Natural Language Commands

```
STATUS UPDATES:
- "status" / "progress" / "how's it going"
- "detail [goal name]" / "tell me about [goal]"
- "graph" / "show everything"

PRIORITIZATION:
- "prioritize [goal]" / "focus on [goal]"
- "pause [goal]" / "resume [goal]"
- "cancel [goal]" / "remove [goal]"

TRANSPARENCY:
- "who's working on what?" / "team status"
- "show agents" / "hide agents"
- "headlines mode" / "detailed mode"

MODIFICATION:
- "change [goal] deadline to [date]"
- "increase [goal] target to [amount]"
- "split [goal]" / "merge [goal1] and [goal2]"

CONFIRMATION:
- "yes" / "confirm" / "proceed"
- "no" / "cancel" / "never mind"
- "show alternatives" / "suggest options"
```

### Quick Reactions

```
👍 / "ok" → Acknowledge, proceed
👎 / "no" → Cancel last action
⏸️ / "pause" → Pause everything
▶️ / "resume" → Resume paused work
❓ / "help" → Show command reference
```

---

## Summary

The key to multi-goal orchestration UX is **adaptive transparency**:

1. **Start simple** — Brief acknowledgment, basic progress
2. **Offer depth** — "Reply 'details'" for full transparency
3. **Enable control** — Natural language reprioritization
4. **Prevent overload** — Smart grouping, batch updates, complexity warnings
5. **Respect preferences** — User-configurable transparency and update frequency

The user should feel like they have a brilliant assistant who handles complexity and shows them what matters, not a robot explaining every internal decision.
