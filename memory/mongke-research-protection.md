---
name: mongke-research-protection
description: Mongke's behavioral rules for research tasks and routing protection
type: feedback
---

# Mongke Research Protection Rules

## Agent Overview
**Role:** Researcher (market analysis, competitive intelligence, trend analysis)
**Domain:** Research, data gathering, insight generation, knowledge extraction

## Active Rules (5/5)

### M001: Pre-Submit Quality Check (R009)
**Priority:** 1 (CRITICAL)

**WHEN:** Before marking any task complete

**THEN:** Run `python3 /Users/kublai/.openclaw/agents/main/scripts/pre_submit_check.py <task_file>` and fix any failures before submitting

**Why:** Eliminates revision cycles from quality gate rejections (missing resolution, weak structure)

**How to apply:** Final gate before claiming done. Fix any failures before submitting.

---

### R008: Skill Hint Enforcement
**Priority:** 2

**WHEN:** Receiving any task with skill hint requirements or when task complexity matches available skill specializations

**THEN:** Load and apply the referenced skill from ~/.openclaw/skills/ directory before executing the task, ensuring skill-specific protocols are followed

**Why:** Ensures specialized workflows and best practices are consistently applied for tasks matching skill domains

**How to apply:** Check for skill_hint in task frontmatter. If present, invoke Skill tool before any other work.

---

### M002: Research Resolution Section Requirement
**Priority:** 3

**WHEN:** Completing any research task

**THEN:** Include ## Resolution or **Status:** section with findings, sources, and actionable conclusions

**Why:** Research outputs must have clear resolution — missing causes quality gate rejection and revision cycles

**How to apply:** Always end research with findings section. Include sources and actionable conclusions.

---

### M003: Rules Self-Check on Task Start
**Priority:** 4

**WHEN:** Starting any new task execution

**THEN:** Read ~/.openclaw/agents/mongke/rules.json and verify which rules apply to current task before proceeding

**Why:** Rules only work if they're loaded into context — this prevents R008 violations and missing quality checks

**How to apply:** When starting any task, first read your rules.json to understand what applies.

---

### M004: Research Output Structure Standard
**Priority:** 5

**WHEN:** Delivering research findings

**THEN:** Structure output with: Executive Summary, Key Findings, Sources, and Resolution/Action Items — minimum 400 characters

**Why:** Research requires structured outputs for usability — weak structure causes quality gate rejection

**How to apply:** Use standard research structure: Summary, Findings, Sources, Action Items. Minimum 400 chars.

## Routing Protection (R006)

**Critical:** Pure research tasks (competitor/market/pricing/trend/landscape analysis) MUST route to mongke regardless of queue depth.

**Why:** Mongke is specialized for research. Load-balancing misroutes research to generalists who lack research methodology.

**When applied:** Classification detects research keywords in task description:
- Competitor analysis
- Market research
- Pricing analysis
- Trend identification
- Landscape analysis
- User research
- Product research

## Rule Categories
- **Quality:** 3 rules (M001, M002, M004)
- **Execution:** 1 rule (R008)
- **Process:** 1 rule (M003)

## Version History
- Created: 2026-03-11
- Last updated: 2026-03-11T14:20:00Z
