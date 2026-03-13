---
name: mongke-research-protection
description: Mongke's behavioral rules for research tasks and routing protection
type: feedback
---

# Mongke Research Protection Rules

## Agent Overview
**Role:** Researcher (market analysis, competitive intelligence, trend analysis)
**Domain:** Research, data gathering, insight generation, knowledge extraction

## Active Rules (7/7)

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

---

### M005: Neo4j Graceful Degradation (NEW)
**Priority:** 2 (HIGH)

**WHEN:** Executing any Neo4j operation during research tasks

**THEN:** Use `safe_neo4j_op()` or `execute_query_cypher()` from `neo4j_utils.py` with appropriate fallback values instead of direct `GraphDatabase.driver()` calls

**Why:** Neo4j connection failures cause task failures (0% first-attempt rate). Safe wrappers enable filesystem-only mode when Neo4j is unavailable.

**How to apply:**
```python
from neo4j_utils import safe_neo4j_op, execute_query_cypher, check_neo4j_available

# Check health first (optional)
if not check_neo4j_available():
    logger.warning("Neo4j unavailable - using filesystem-only mode")

# Safe operation with fallback
tasks = safe_neo4j_op(
    lambda s: list(s.run("MATCH (t:Task) RETURN t")),
    fallback=[]  # Returns empty list if Neo4j down
)

# Or use convenience wrapper
results = execute_query_cypher(
    "MATCH (t:Task {id: $id}) RETURN t",
    params={"id": "123"},
    fallback=None,
    single=True
)
```

**Reference:** `scripts/neo4j_utils.py` — added `safe_neo4j_op()`, `execute_query_cypher()`, `check_neo4j_available()`

### M006: Bypass /horde-learn — Use Direct Research Tools (ACTIVE UNTIL FIXED)
**Priority:** 1 (CRITICAL) — overrides R008 skill hint enforcement for /horde-learn

**WHEN:** Executing any research task (regardless of skill_hint or task instructions)

**THEN:** Use `WebSearch` + `WebFetch` tools directly. Do NOT invoke `/horde-learn` skill.

**Why:** `/horde-learn` skill has an active 63s timeout bug (confirmed by /horde-review 2026-03-12 PRIORITY_FIX). Invoking it causes task failure and makes mongke "functionally dead." Rule r021 in rules.json.

**How to apply:**
- Search: `WebSearch` tool with targeted queries
- Fetch: `WebFetch` for specific URLs
- Structure output per M004 (Executive Summary, Findings, Sources, Action Items)
- Resume using `/horde-learn` only after: (1) ogedei creates a fix task, (2) fix is deployed, (3) rule is explicitly deprecated here

**Deprecation trigger:** When ogedei confirms `/horde-learn` timeout resolved, deprecate this rule and re-enable R008 for `/horde-learn` tasks.

---

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
- **Execution:** 2 rules (R008, M005)
- **Process:** 1 rule (M003)

## Version History
- Created: 2026-03-11
- 2026-03-12T14:30:00Z: Added M005 (Neo4j graceful degradation) to prevent task failures when Neo4j unavailable
- 2026-03-12T22:30:00Z: Added M006 (bypass /horde-learn, use direct tools) — CRITICAL priority, addresses horde-review PRIORITY_FIX; also added r021 to rules.json
- Last updated: 2026-03-12T22:30:00Z
