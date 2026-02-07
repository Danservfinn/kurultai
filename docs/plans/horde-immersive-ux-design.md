# Horde Immersive UX Design: The Khan's Command Experience

> **Design Document**: Creating an immersive "commanding overwhelming force" experience
> **Date**: 2026-02-06
> **Status**: Design Phase

---

## Executive Summary

This document defines UX patterns that transform the horde skills system into an immersive experience where the user feels like a Mongol Khan commanding their forces. The design emphasizes **authority**, **strategic control**, and **overwhelming power** while maintaining clarity and usability.

**Core Design Principle**: The user should feel like they're directing a vast, capable force—not micromanaging workers, but commanding skilled lieutenants who execute their will.

---

## 1. Progression Psychology

### 1.1 The Three-Act Emotional Arc

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE KHAN'S COMMAND EMOTIONAL JOURNEY                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ACT I: ASSEMBLING FORCES              ACT II: BATTLE                   ACT III: VICTORY     │
│  ┌──────────────────────┐            ┌──────────────────┐           ┌──────────────────┐ │
│  │                      │            │                  │           │                  │ │
│  │  ANTICIPATION        │──────►     │  POWER           │───────►  │  TRIUMPH         │ │
│  │  "Who answers my     │            │  "My will is      │           │  "The horde has   │ │
│  │   call?"             │            │   being done"     │           │   delivered"     │ │
│  │                      │            │                  │           │                  │ │
│  │  • Tension builds    │            │  • Momentum      │           │  • Satisfaction  │ │
│  │  • Forces gather     │            │  • Coordination   │           │  • Magnitude     │ │
│  │  • Strategy forms    │            │  • Dominance      │           │  • Legacy        │ │
│  │                      │            │                  │           │                  │ │
│  └──────────────────────┘            └──────────────────┘           └──────────────────┘ │
│           ▲                                ▲                            ▲                │
│           │                                │                            │                │
│     HORDE_GATHERING                   HORDE_EXECUTING              HORDE_CONQUERING      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Act I: Assembling Forces (The Gathering)

**Emotional Goal**: Build anticipation, establish authority

| Phase | User Action | System Response | Emotional Beat |
|-------|-------------|-----------------|----------------|
| **Declaration** | Issues command (`/horde task...`) | "The Khan has spoken. Gathering forces..." | Purpose |
| **Rallying** | Watch agents assemble | Forces arrive one by one with status | Accumulation |
| **Briefing** | Review plan with option to adjust | Strategy visualization | Control |
| **Deployment** | Final command ("Begin") | Forces fan out to objectives | Commitment |

**Anti-Patterns to Avoid**:
- Don't show "empty" states - always imply forces are ready
- Don't use passive language ("waiting for agents") - use active ("forces gathering")
- Don't emphasize limitations - emphasize capability

**Implementation Guidance**:
```
# Good: Forces Gathering
"The tumens assemble. 4 specialist units answer your call."
"Scouts report: Task complexity requires a 3-agent vanguard."

# Avoid: Weak Language
"Finding available agents..."
"Waiting for agents to spawn..."
```

### 1.3 Act II: Battle (The Execution)

**Emotional Goal**: Feel the power of coordinated action

| Progression | Visual Indicator | Emotional State |
|-------------|------------------|-----------------|
| **Initial Clash** | First agents make contact | Momentum |
| **Coordinated Advance** | Multiple fronts moving simultaneously | Dominance |
| ** tactical Adjustments** | Agents adapt, coordinate | Intelligence |
| **Breakthrough** | Major sub-objectives complete | Inevitability |

**Feedback Rhythm**:
```
Opening:         ████████████ 100% forces deployed
Early Action:    █████████░░░░ 80% initial objectives contested
Mid-Battle:      ██████░░░░░░░ 60% convergence achieved
Breakthrough:    ████░░░░░░░░░ 40% final push
Victory:         ░░░░░░░░░░░░░ 0% remaining - COMPLETE
```

### 1.4 Act III: Victory (The Delivery)

**Emotional Goal**: Triumph, satisfaction, reinforced authority

| Element | Design | Psychological Effect |
|---------|--------|---------------------|
| **Arrival** | Result presented as tribute | Subordinates serving |
| **Magnitude** | Emphasize what was accomplished | Scale of achievement |
| **Provenance** | Show which agents contributed | Attribution without labor |
| **Legacy** | Option to save as template | Building empire |

---

## 2. Feedback Design

### 2.1 Signal Hierarchy

The system uses a tiered feedback language matching military command structures:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SIGNAL HIERARCHY                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  TIER 1: IMPERIAL (User-level announcements)                                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ "The Khan commands" │ "Victory is ours" │ "The horde awaits"         │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│           │                                                                   │
│           ▼                                                                   │
│  TIER 2: TUMEN (Agent group status - 10 agents)                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ "First Tumen deployed" │ "Vanguard converging" │ "Reserve ready"      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│           │                                                                   │
│           ▼                                                                   │
│  TIER 3: ARBAN (Individual agent/unit status)                                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ "Temüjin's wing advancing" │ "Jochi reports findings"                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│           │                                                                   │
│           ▼                                                                   │
│  TIER 4: DETAIL (Expandable technical status)                                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Technical logs, error messages, raw output (collapsed by default)      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Force Gathering Signals

**Pattern**: The language of mobilization, not instantiation

```
# Agent Spawning → Forces Assembling
[BEFORE]
"Spawning researcher agent..."
"Creating writer agent..."

[AFTER]
"From the steppes: MÖNGKE arrives, bearing wisdom"
"CHAGATAI answers the call, quill in hand"
"TEMÜJIN rides forth, sword at the ready"

# Multiple Agents
"The tumens assemble:"
"  → Möngke (Research Vanguard)"
"  → Chagatai (Wordsmith Wing)"
"  → Temüjin (Iron Horde)"
"  → Jochi (Truth Seekers)"
"Four wings. One purpose."
```

**Visual Pattern**: Progressive arrival, not parallel instantiation

```
t=0s:   /horde deploy "Analyze competitor landscape"
        └─> "Your command echoes across the steppes..."

t=2s:   "MÖNGKE: First scout reports. Gathering intelligence..."

t=4s:   "CHAGATAI: Scribe battalion mobilized."

t=5s:   "JÖCHI: Analysis contingent formed."

t=6s:   "Four wings assembled. Strategy synchronized."
        "Awaiting your command to begin. [Press Enter or type 'march']"
```

### 2.3 Maneuver In Progress Signals

**Pattern**: Language of coordinated advance, not "work happening"

```
# Progress Updates → Battle Reports
[BEFORE]
"Agent 1: Processing..."
"Agent 2: Processing..."

[AFTER]
"Vanguard engages: First findings emerging"
"Left flank advances: Analysis taking shape"
"Reserve mobilizes: Preparing synthesis"

# Coordination Signals
"Möngke shares intelligence with Chagatai..."
"Temüjin fortifies the approach..."
"Jochi validates the findings..."
"The wings coordinate their advance."
```

**Progress Visualization**: Military map aesthetic

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BATTLEFIELD MAP                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  OBJECTIVE                              FORCES                               │
│  ┌─────────────────────────────────┐    ┌─────────────────────────────┐    │
│  │      ANALYZE COMPETITORS       │    │  ████ MÖNGKE [ADVANCING]     │    │
│  │                                 │    │  ████ CHAGATAI [POSITIONED] │    │
│  │         ████████░░ 80%         │    │  ████ TEMÜJIN [ENGAGED]     │    │
│  │                                 │    │  ███JÖCHI [CONVERGING]       │    │
│  └─────────────────────────────────┘    └─────────────────────────────┘    │
│                                                                              │
│  INTELLIGENCE REPORT:                                                       │
│  > Möngke's scouts have mapped 3 competitor territories                     │
│  > Chagatai is drafting the imperial proclamation                            │
│  > Jochi cross-references Möngke's findings                                 │
│  > Temüjin prepares infrastructure recommendations                            │
│                                                                              │
│  "The coordinated advance continues..."                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.4 Victory Signals

**Pattern**: The language of triumph and tribute

```
# Task Complete → Victory Achieved
[BEFORE]
"All agents completed successfully. Here's the result:"

[AFTER]
╔═══════════════════════════════════════════════════════════════════════════════╗
║                         VICTORY IS OURS                                       ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  The four wings return, bearing the spoils of conquest:                      ║
║                                                                              ║
║  From MÖNGKE'S Vanguard:                                                     ║
║  > Intelligence gathered from 7 competitor strongholds                       ║
║  > 3 critical weaknesses identified in their defenses                        ║
║                                                                              ║
║  From CHAGATAI'S Scribes:                                                    ║
║  > Strategic analysis prepared for your review                               ║
║  > 12-page imperial report complete                                          ║
║                                                                              ║
║  The horde has served you well.                                              ║
║                                                                              ║
║  [View Full Report] [Save to Archives] [Command Another Campaign]            ║
║                                                                              ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

### 2.5 Setback Signals

**Pattern**: The language of adaptation, not failure

```
# Error Handling → Tactical Adjustments
[BEFORE]
"Error: Agent failed. Retrying..."

[AFTER]
"Tempest encountered! Temüjin's wing adapts..."
"Scouting party repelled. Möngke regroups..."
"The horde adjusts its approach."

# Partial Failure
"Chagatai's scribes face resistance. Temüjin reinforces..."
"Three wings advance. One contingent holds position."

# Recovery
"Adaptation successful. The advance continues."
"Alternative route found. All wings converging."
```

---

## 3. Control Metaphor: Khan vs. Micromanager

### 3.1 The Authority-Autonomy Balance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CONTROL SPECTRUM                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  MICROMANAGER                │                KHAN                          │
│  (Avoid)                     │                (Target)                      │
│                              │                                              │
│  "Do step 1, then step 2"    │    "Capture this territory"                 │
│  "Use exactly these params"  │    "Bring me intelligence"                   │
│  "I'll watch your progress"  │    "Report when victorious"                  │
│                              │                                              │
│  └─ User feels like         │    └─ User feels strategic                   │
│     a task manager            │       and powerful                          │
│                              │                                              │
│  AGENTS ARE TOOLS            │    AGENTS ARE LIEUTENANTS                    │
│                              │                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Command Language Patterns

**Declarative, Not Imperative (at micro level)**

```
# Micromanagement Style (Avoid)
"I want you to research competitors A, B, and C.
 Then compile a table comparing their features.
 Then write a summary highlighting differences.
 Then format it as a markdown document."

# Khan Style (Target)
"Bring me a comprehensive analysis of our competitors' weaknesses.
 I need strategic intelligence, not raw data.
 Present your findings as a imperial directive."
```

**Outcome-Focused, Not Process-Focused**

```
# Process Focus (Avoid)
"Run tests, then fix bugs, then run tests again,
 then deploy to staging, then verify, then..."

# Khan Style (Outcome)
"Secure the production deployment.
 Show me only what requires my attention."
```

### 3.3 Intervention Levels

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INTERVENTION CONTINUUM                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  "REIGN"                    "COMMAND"                   "ADVISE"            │
│  (Full autonomy)            (Strategic direction)       (Light guidance)     │
│  │                          │                           │                   │
│  │                          │                           │                   │
│  ▼                          ▼                           ▼                   │
│                                                                              │
│  /horde: "Handle it"      /horde: "Analyze X,     /horde: "Focus on Y,     │
│                            report to me in          but consider Z too"      │
│                            this format"                                     │
│                                                                              │
│  Lieutenants have         Khan provides           Khan suggests            │
│  full discretion          objective and           preference               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.4 Feedback Elicitation

**Smart Prompting for Ambiguity Resolution**

```
# When User Intent is Unclear
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║  Khan, your wish is broad. How shall the horde proceed?                      ║
║                                                                              ║
║  [SCOUTING] "Gather intelligence first, then I'll decide the next blow"      ║
║  [RAID] "Strike quickly. Bring me immediate results"                         ║
║  [CAMPAIGN] "Plan a full conquest. I'll review the strategy"                 ║
║  [CUSTOM] "I'll specify my exact intentions..."                              ║
║                                                                              ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

---

## 4. Epic Moments

### 4.1 Epic Moment 1: The Arrival of the Horde

**Trigger**: First use of `/horde` or a particularly complex task

**Pattern**: Cinematic reveal of assembled forces

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║                              THE HORDE GATHERS                                ║
║                                                                              ║
║  From across the steppe, they answer your call...                            ║
║                                                                              ║
║         ___
║        /   \         ___           ___           ___                          ║
║       | R █|       | W █|         | D █|         | A █|                        ║
║       |___/        |___/          |___/          |___/                         ║
║      MÖNGKE       CHAGATAI        TEMÜJIN        JÖCHI                         ║
║    Research      Wordsmith      Developer      Analyst                         ║
║                                                                              ║
║  Four specialist wings. One Khan. Unlimited potential.                       ║
║                                                                              ║
║  They await your command.                                                    ║
║                                                                              ║
╚═══════════════════════════════════════════════════════════════════════════════╝

[Press any key to issue your command]
```

**Psychological Impact**: Immediate sense of scale and capability

### 4.2 Epic Moment 2: The Coordinated Strike

**Trigger**: Multiple agents working in parallel on subtasks

**Pattern**: Visualizing the swarm in action

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                           COORDINATED STRIKE                                  ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  OBJECTIVE: "Audit authentication security across all services"              ║
║                                                                              ║
║                      ┌──THE TARGET──┐                                       ║
║                      │              │                                       ║
║                      │  AUTH-SVC    │                                       ║
║                      │              │                                       ║
║                      └──────┬───────┘                                       ║
║                             │                                               ║
║         ╱───────────────────┼───────────────────╲                           ║
║        ▼                    ▼                    ▼                           ║
║   ┌─────────┐          ┌─────────┐          ┌─────────┐                      ║
║   │MÖNGKE   │          │TEMÜJIN  │          │JÖCHI   │                       ║
║   │Scanning │          │Probing  │          │Testing  │                       ║
║   │ docs    │          │ code    │          │exploits│                       ║
║   └────┬────┘          └────┬────┘          └────┬────┘                      ║
║        │                    │                    │                           ║
║        └────────────────────┼────────────────────┘                           ║
║                             │                                               ║
║                             ▼                                               ║
║                      ┌─────────────┐                                         ║
║                      │  CHAGATAI   │                                         ║
║                      │ Synthesizes │                                         ║
║                      │  findings   │                                         ║
║                      └─────────────┘                                         ║
║                                                                              ║
║  "From four directions, the horde strikes as one."                           ║
║                                                                              ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

**Psychological Impact**: Seeing the swarm coordinate creates feeling of commanding intelligent force, not just running tools

### 4.3 Epic Moment 3: The Tribute Presentation

**Trigger**: Task completion with multi-agent contribution

**Pattern**: Results presented as tribute from subordinate commanders

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║                         THE TRIBUTE ARRIVES                                   ║
║                                                                              ║
║  Your lieutenants kneel before you, bearing the fruits of conquest:          ║
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
║  │ From the Vanguard of MÖNGKE:                                           │ ║
║  │                                                                         │ ║
║  │   "Khan, we have mapped the enemy territories:"                        │ ║
║  │    • 7 API endpoints documented                                       │ ║
║  │    • 3 critical vulnerabilities discovered                            │ ║
║  │    • 2 unpatched dependencies identified                              │ ║
║  │                                                                         │ ║
║  │   The enemy's defenses are known to us now."                           │ ║
║  └─────────────────────────────────────────────────────────────────────────┘ ║
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
║  │ From the Iron Forges of TEMÜJIN:                                       │ ║
║  │                                                                         │ ║
║  │   "Khan, the steel has been tempered:"                                 │ ║
║  │    • Secure authentication flow implemented                           │ ║
║  │    • Rate limiting deployed                                            │ ║
║  │    • Input validation fortified                                       │ ║
║  │                                                                         │ ║
║  │   The gates are barred against intruders."                             │ ║
║  └─────────────────────────────────────────────────────────────────────────┘ ║
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
║  │ From the Scrolls of CHAGATAI:                                          │ ║
║  │                                                                         │ ║
║  │   "Khan, the decree has been drafted:"                                 │ ║
║  │    • Security audit report (12 pages)                                  │ ║
║  │    • Remediation roadmap with priorities                               │ ║
║  │    • Team training recommendations                                     │ ║
║  │                                                                         │ ║
║  │   Your will is made manifest."                                         │ ║
║  └─────────────────────────────────────────────────────────────────────────┘ ║
║                                                                              ║
║  [Accept the Tribute] [Review Details] [Issue New Command]                  ║
║                                                                              ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

**Psychological Impact**: Reinforces the user's authority and the capability of their forces

---

## 5. Anti-Patterns: What Breaks Immersion

### 5.1 Language Anti-Patterns

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| "Spawning agent..." | Feels technical/robotic | "Forces gathering..." |
| "Waiting for response..." | Passive, boring | "The horde advances..." |
| "Error: timeout" | Breaks immersion | "Storms delay the vanguard..." |
| "Processing..." | Generic | Specific agent activity |
| "Done!" | Too casual | "Victory is ours" |
| "Retry attempt 3/5" | Feels like machinery | "The horde regroups..." |

### 5.2 UI Anti-Patterns

```
# AVOID: Technical Progress Bars
[████████████░░] 80% complete

# USE: Military/Achievement Context
Vanguard: SECURE
Main Force: ADVANCING
Reserve: READY

"The objective is within reach."
```

```
# AVOID: Generic Error Messages
Error: Agent 'researcher' failed to connect

# USE: In-Universe Messaging
Möngke's scouts have lost the trail.
Rerouting through alternate passes...
```

### 5.3 Interaction Anti-Patterns

| Anti-Pattern | Problem | Solution |
|--------------|---------|----------|
| Requiring user to select agents | Breaks Khan fantasy | Auto-select with option to override |
| Showing raw agent logs | Too much detail | Summary with "expand for details" |
| Technical error codes | Breaks immersion | In-universe language for errors |
| Silent failures | User doesn't know what's happening | Always communicate status |
| Manual retry required | Feels broken | Automatic adaptation |

### 5.4 Tone Anti-Patterns

**Avoid: Over-the-Top Roleplay**

``# DON'T GO THIS FAR
"GREETINGS, GREAT KHAN! YOUR HUMBLE SERVANTS ARE HONOURED TO..."
"*bows deeply* Yes, my liege! At once, my liese!"
```

**Reasoning**: This breaks immersion by being cartoonish. The fantasy should be subtle and atmospheric, not a Renaissance Faire.

**Do: Subtle Atmospheric Language**

```
"The forces assemble. Four wings answer your call."
"Your command echoes across the steppe."
"The vanguard returns with intelligence."
```

### 5.5 Cringe Factors to Avoid

1. **Forced Mongolian terminology**: Don't overuse Mongol words. English is fine. "Tumen" for agent groups is enough.
2. **Obsequious language**: Agents should be capable subordinates, not groveling servants
3. **Over-dramatization**: Not every task is an "epic conquest". Match tone to task complexity
4. **Fake accents or speech patterns**: Agent personalities come through expertise, not caricature
5. **Excessive length**: Keep communications concise. A Khan doesn't read novels.

---

## 6. Implementation Framework

### 6.1 Message Template System

```python
class HordeMessenger:
    """
    Generates in-universe messages for horde operations.
    """

    # Message categories
    IMPERIAL = "imperial"      # User-facing announcements
    TUMEN = "tumen"           # Agent group status
    ARBAN = "arban"           # Individual agent status
    DETAIL = "detail"         # Technical details

    # Phase-based messaging
    GATHERING = {
        IMPERIAL: [
            "Your command echoes across the steppes...",
            "The tumens assemble at your call.",
            "Forces gather from all directions.",
        ],
        TUMEN: [
            "{agent_name} answers the call.",
            "The {role} wing mobilizes.",
            "{agent_name} rides forth.",
        ]
    }

    EXECUTING = {
        IMPERIAL: [
            "The horde advances.",
            "Coordinated strike in progress.",
            "Multiple wings converge on the objective.",
        ],
        ARBAN: [
            "{agent_name} reports progress.",
            "{agent_name} continues the advance.",
            "{agent_name} adapts to terrain.",
        ]
    }

    VICTORY = {
        IMPERIAL: [
            "Victory is ours!",
            "The objective is secured.",
            "The horde has delivered.",
        ],
        ARBAN: [
            "{agent_name} returns with tribute.",
            "{agent_name} has completed the mission.",
        ]
    }

    SETBACK = {
        IMPERIAL: [
            "The horde adapts.",
            "Alternative routes found.",
            "The advance continues by another path.",
        ],
        ARBAN: [
            "{agent_name} regroups.",
            "{agent_name} finds another way.",
            "{agent_name} fortifies their position.",
        ]
    }
```

### 6.2 Task-to-Tone Mapping

```python
# Match language intensity to task characteristics
TONE_MAPPING = {
    "complexity": {
        "simple": {
            "style": "routine",
            "prefix": "Scout party",
            "verb": "investigates"
        },
        "moderate": {
            "style": "campaign",
            "prefix": "Vanguard",
            "verb": "advances"
        },
        "complex": {
            "style": "invasion",
            "prefix": "Grand army",
            "verb": "conquers"
        }
    },
    "risk": {
        "low": {
            "adjective": "routine"
        },
        "medium": {
            "adjective": "strategic"
        },
        "high": {
            "adjective": "critical"
        },
        "critical": {
            "adjective": "imperial"
        }
    }
}
```

### 6.3 Progress Visualization

```python
class BattleMap:
    """
    Visualizes horde progress as military campaign.
    """

    def render_progress(self, agents, status):
        """
        Generate visual battlefield representation.
        """
        template = """
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BATTLEFIELD MAP                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  OBJECTIVE: {objective}                                                      │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  {progress_bar} {percentage}%                                         │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  FORCES DEPLOYED:                                                            │
│  {agent_rows}                                                                │
│                                                                              │
│  INTELLIGENCE:                                                               │
│  {intelligence}                                                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
        """.strip()

        # Agent rows show individual status
        agent_rows = []
        for agent in agents:
            status_icon = {
                "active": "⚔",
                "waiting": "○",
                "complete": "✓",
                "error": "!"
            }[agent.status]

            agent_rows.append(
                f"  [{status_icon}] {agent.name.upper():12} {agent.status_text}"
            )

        # Intelligence shows recent activity
        intelligence = self._format_intelligence(agents)

        return template.format(
            objective=self.objective,
            progress_bar=self._progress_bar(status.percentage),
            percentage=status.percentage,
            agent_rows="\n".join(agent_rows),
            intelligence=intelligence
        )
```

---

## 7. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Immersion Score** | >4.0/5 | User survey on "felt like commanding" |
| **Clarity** | >4.5/5 | User understanding of status |
| **Efficiency** | <3 clicks | Commands to execute typical task |
| **Recovery Rate** | >95% | Automatic recovery from setbacks |
| **Satisfaction** | >4.0/5 | Post-task satisfaction rating |

---

## 8. Conclusion

The Khan Command UX transforms technical multi-agent coordination into an immersive experience of commanding overwhelming force. Key principles:

1. **Authority**: User commands, agents execute
2. **Strategic Control**: Khan sets objectives, lieutenants determine tactics
3. **Overwhelming Force**: Emphasize capability, not constraints
4. **Subtlety**: Atmospheric language, not cartoonish roleplay
5. **Clarity**: Immersive but never confusing

The user should feel powerful, strategic, and in control of a capable force that executes their will—not like a task manager herding cats.

---

*Document Version: 1.0*
*Date: 2026-02-06*
*Author: Horde UX Design Team*
