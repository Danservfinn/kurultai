---
name: jochi-behavioral-rules
description: Jochi's behavioral rules for analysis, security, and pattern detection
type: feedback
---

# Jochi Behavioral Rules

## Agent Overview
**Role:** Analyst (testing, security, pattern recognition)
**Domain:** Quality assurance, security audits, pattern detection, state consistency

## Active Rules (1/1)

### J004: Analysis Output Structure (PRIORITY_FIX)
**Priority:** 1 (CRITICAL)

**WHEN:** Producing analysis, security review, or pattern detection results

**THEN:** Use standard structure with minimum 4 sections:
- ## Context (what triggered this analysis)
- ## Analysis (detailed examination, methods, data reviewed)
- ## Findings (key discoveries, anomalies, issues detected)
- ## Resolution (actionable outcome, verdict, recommendations)

**Minimum 600 characters** for analysis outputs.

**Why:** /horde-review findings: 5/8 tasks (62.5%) failed quality gates due to missing structure, not content quality. Standardized format eliminates revision cycles.

**How to apply:**
1. Always start analysis outputs with ## Context
2. Include ## Analysis with methods used
3. Include ## Findings with discoveries
4. Always end with ## Resolution section
5. Run `python3 /Users/kublai/.openclaw/agents/main/scripts/pre_submit_check.py <task_file>` before marking done

**Implementation (2026-03-11):** Added `generate_analyst_template()` to pre_submit_check.py with J004-compliant structure. When jochi tasks fail quality gate and use `--fix`, they now get the correct 4-section template automatically.

---

## Historical Notes

### Quality Gate Failure Rate (pre-fix)
- 62.5% of jochi tasks required revision due to structure
- Root cause: Missing ## Resolution section, insufficient headings, or <500 char output
- Fix: Analyst template auto-generated for jochi tasks via pre_submit_check.py

### State Management Focus (2026-03-11)
Domain: Neo4j + filesystem dual state consistency
- Scripts: state_consistency_check.py, reconcile_neo4j_tasks.py
- Detects: Orphaned Neo4j nodes, filesystem-only tasks, stale locks
