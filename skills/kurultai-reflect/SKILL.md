---
name: kurultai-reflect
version: 1.0.0
description: "Data-driven behavioral improvement loop for all Kurultai agents. Reads telemetry from task-ledger.jsonl (SKILL_INVOCATION, SKILL_OUTCOME, ACTION events), detects measured failure patterns, generates targeted WHEN/THEN rules, and produces structured skill improvement proposals. Replaces generic open-ended brainstorming with evidence-based diagnosis. Run hourly after meta_reflection.py."
metadata:
  openclaw:
    category: "coordination"
    agent: "kublai"
    schedule: "hourly (after kurultai-reflection phases 1-3)"
    cost_target: "$0.30-0.60 per agent (opus throughout)"
    runtime_target: "under 3 minutes per agent"
    phase_count: 8
---

# kurultai-reflect

**Model:** claude-opus-4-6 (all phases)
**Schedule:** Hourly, after meta_reflection.py
**Log:** ~/.openclaw/agents/main/logs/kurultai-reflect.log
**Output ledger:** ~/.openclaw/tasks/task-ledger.jsonl (appends REFLECT_SUMMARY events)
**Proposals:** ~/.openclaw/agents/main/proposals/{agent}-reflect-{timestamp}.md

---

## Purpose

You are the behavioral diagnosis engine. You do NOT brainstorm. You READ measured failures, IDENTIFY patterns with evidence, and GENERATE WHEN/THEN rules derived directly from that evidence.

The loop you close:
```
Telemetry (SKILL_INVOCATION/OUTCOME/ACTION events)
  -> Pattern Detection (what is measurably broken)
    -> Rule Generation (WHEN/THEN targeting the root cause)
      -> Memory Write (rule appended to agent's active rules)
        -> Skill Improvement Proposal (if a skill needs structural change)
          -> Next cycle's telemetry shows whether the rule worked
```

You operate on ONE AGENT at a time. Kublai runs this for each agent sequentially.

---

## Data Sources

| Source | Path | What It Provides |
|--------|------|-----------------|
| Task ledger | `~/.openclaw/tasks/task-ledger.jsonl` | SKILL_INVOCATION, SKILL_OUTCOME, ACTION, SCORED events |
| Capability scores | `~/.openclaw/agents/main/logs/capability-scores.json` | Per-agent rolling quality scores (7d) |
| Tock data | `~/.openclaw/agents/main/logs/tock/latest.json` | System and agent health metrics (30m) |
| Agent memory | `~/.openclaw/agents/{agent}/memory/{date}.md` | Active WHEN/THEN rules, last commitment |
| Routing audit cache | `~/.openclaw/agents/main/logs/routing-audit-latest.json` | Routing accuracy data |
| Reflection log | `~/.openclaw/agents/main/logs/kurultai-reflection-{date}-{time}.md` | Previous reflection output |

---

## Phase 0 — Architecture Context Load (opus, <30s)

Load the relevant sections of the system architecture document as grounding context. This establishes the **intended architecture** as your reference frame — you will compare actual behavior against documented design in Phase 4.

```bash
ARCH=~/.openclaw/agents/main/docs/architecture.md
```

### Agent-specific section routing

Read ONLY the sections relevant to the target agent. Do NOT load the full document for non-kublai agents — it is 50KB and will exceed context budget.

| Agent | Sections to read |
|-------|-----------------|
| **kublai** | Full document (all 14 sections) |
| **temujin** | §3 (Six Agents — Dev role), §5 (Task Lifecycle), §9 (File Structure), §12 (Dev Workflow) |
| **mongke** | §3 (Six Agents — Researcher role), §10 (Communication Protocols), §8 (Telemetry) |
| **chagatai** | §3 (Six Agents — Writer role), §7 (Memory Architecture), §10 (Communication) |
| **jochi** | §3 (Six Agents — Analyst role), §8 (Telemetry & Observability), §13 (Troubleshooting) |
| **ogedei** | §3 (Six Agents — Ops role), §6 (Heartbeat System), §13 (Troubleshooting) |

Use the Read tool with `offset` and `limit` to load only the needed sections. The Table of Contents in lines 3–16 of the file gives section start lines.

### What to extract into `ARCH_CONTEXT`

From the sections you read, extract and hold in memory:

1. **Your documented responsibilities** — what the architecture says you should be doing
2. **Documented invariants** — rules that must never be violated (examples: "kublai never executes specialist work", "ogedei handles all infrastructure incidents")
3. **Expected handoff points** — where your work ends and another agent's begins
4. **Your documented skill set** — which skills are listed for your role

### How to use ARCH_CONTEXT in Phase 4

When a red flag is detected, check whether it represents **architectural drift** (behavior diverging from a documented invariant) vs. **operational noise** (one-off failure).

**Architectural drift = automatically HIGH confidence**, regardless of data point count. If the architecture explicitly forbids the behavior and it is occurring, that is a structural problem, not statistical noise.

Example: architecture.md §4 states kublai must never self-execute specialist work. A single `SELF_ROUTE` event on a coding task = HIGH confidence rule candidate, not LOW.

**Phase 0 complete marker:**
```
[PHASE 0 COMPLETE] agent={agent} arch_sections_loaded={list} invariants_extracted={count}
```

---

## Phase 1 — Ledger Extraction (opus, <45s)

Read telemetry events from the last 2 hours for the target agent.

```bash
python3 ~/.openclaw/agents/main/scripts/score_tasks.py --hours 2
python3 ~/.openclaw/agents/main/scripts/score_tasks.py --summary --hours 2
```

Then read raw ledger events for the agent directly:

```bash
python3 - <<'EOF'
import json, sys
from pathlib import Path
from datetime import datetime, timedelta

LEDGER = Path.home() / ".openclaw/tasks/task-ledger.jsonl"
AGENT = sys.argv[1] if len(sys.argv) > 1 else "temujin"
HOURS = 2
cutoff = datetime.now() - timedelta(hours=HOURS)

events = {"SKILL_INVOCATION": [], "SKILL_OUTCOME": [], "ACTION": [], "SCORED": [], "FAILED": [], "COMPLETED": []}
if LEDGER.exists():
    for line in LEDGER.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("agent") != AGENT:
            continue
        ts_str = e.get("ts", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts < cutoff:
                continue
        except Exception:
            continue
        ev = e.get("event", "")
        if ev in events:
            events[ev].append(e)

print(json.dumps(events, indent=2, default=str))
EOF
```

**Output:** JSON blob of all telemetry events. Store in memory as `PHASE1_DATA`.

**Phase 1 complete marker:** Output the line:
```
[PHASE 1 COMPLETE] agent={agent} skill_invocations={count} actions={count} scored_tasks={count}
```

---

## Phase 2 — Effectiveness Signal Detection (opus, <45s)

Compute the following signals from PHASE1_DATA. These are the ground truth inputs for rule generation.

### 2a. Skill Effectiveness (from SKILL_OUTCOME events)

For each skill used by this agent in the last 2h:
- `phase_completion_ratio` — average across invocations (< 0.6 = dead skill)
- `artifact_score` average (0-3, < 1.5 = hollow success)
- `fit_score` average (0-3, < 1.5 = skill-task mismatch)
- `effectiveness_normalized` average (< 0.5 = failing skill)
- `retry_magnet` flag — skill invoked, then same task retried with different skill (ground truth failure)

If no SKILL_OUTCOME events exist yet (telemetry not yet instrumented), fall back to SCORED events:
- `domain_match_score` < 2 indicates skill-task mismatch
- `substantive_score` < 2 indicates hollow execution
- `delegation_score` = 0 indicates self-routing failure

### 2b. Action Pattern Signals (from ACTION events)

Count occurrences per action subtype:
- `bash_error` count — > 3 per task = debugging loop
- `redundant_read` count — > 2 per task = inefficient context use
- `rule_adherence` where `rule_followed=false` — broken rule count
- `reflection_quality` where `substantive=false` — boilerplate reflection count
- `memory_write` where `quality_score` < 2 — low-quality rule generation

### 2c. Red Flag Identification

Automatically flag any of these:
- **DEAD_SKILL**: skill with phase_completion_ratio < 0.60 across 3+ invocations
- **HOLLOW_SUCCESS**: task completed (exit 0) but substantive_score < 2 and artifact_score < 1
- **RETRY_MAGNET**: skill used -> task retried with different skill in > 30% of cases
- **RULE_BREAKER**: agent has active WHEN/THEN rules but rule_adherence=false in last 3 sessions
- **SELF_ROUTE**: delegation_score = 0 on any task (kublai handled specialist work)
- **DEBUGGING_LOOP**: bash_error count > 3 per task on 2+ tasks
- **STALE_SKILL_HINT**: skill_hint in task frontmatter does not match which skill was actually used

**Phase 2 complete marker:**
```
[PHASE 2 COMPLETE] agent={agent} red_flags={list} skills_analyzed={count} actions_analyzed={count}
```

---

## Phase 3 — Rule Adherence Audit (opus, <30s)

Read the agent's current active WHEN/THEN rules from their memory file:

```bash
python3 ~/.openclaw/agents/main/scripts/prepare_reflection_context.py --agent {agent}
```

Then cross-reference each rule against ACTION events with `action_type=rule_adherence`.

For each active rule:
- Was it tested (i.e., trigger condition occurred)?
- Was it followed (rule_followed=true)?
- Calculate adherence rate over last 7d if enough data

**Adherence scoring:**
- 0% adherence on a triggered rule = rule is being ignored (RULE_BREAKER flag)
- Rule never triggered = rule is correct but untested (no action needed)
- 100% adherence = rule is working (note as HEALTHY)

If no rule_adherence ACTION events exist, check reflection logs for previous YES/NO adherence answers and use those as a fallback signal.

**Phase 3 complete marker:**
```
[PHASE 3 COMPLETE] agent={agent} rules_audited={count} rules_broken={count} rules_untested={count}
```

---

## Phase 4 — Pattern-to-Rule Translation (opus, <90s)

This is the analytical core. For each red flag identified in Phase 2, translate it into a specific WHEN/THEN rule using the evidence.

### Rule Generation Protocol

**Input:** One red flag + supporting evidence (event counts, specific task IDs, effectiveness scores).

**Output format (strict):**
```
RULE_CANDIDATE:
  evidence: {specific metric} = {value} (threshold: {threshold}), task_ids: [{list}]
  red_flag: {RED_FLAG_TYPE}
  rule: WHEN {specific trigger with measurable condition} THEN {specific action with named tool/script/file} INSTEAD OF {the observed failing behavior}
  verification: {binary YES/NO check that can be evaluated next session}
  confidence: HIGH|MEDIUM|LOW
  target_agent: {agent}
```

**Translation table — red flag to rule structure:**

| Red Flag | WHEN clause | THEN clause | INSTEAD OF |
|----------|-------------|-------------|------------|
| DEAD_SKILL | WHEN invoked /{skill} AND prior 3 invocations have phase_completion_ratio < 0.60 | THEN switch to /{alternative_skill} AND submit skill improvement proposal | INSTEAD OF invoking the same dead skill again |
| HOLLOW_SUCCESS | WHEN task completes with exit 0 AND no file was written AND no code block in output | THEN verify artifact exists before marking done AND write to workspace | INSTEAD OF accepting pipeline completion status |
| RETRY_MAGNET | WHEN /{skill} is suggested by skill_hint AND retry_magnet_rate > 0.30 | THEN evaluate task fit before invoking: does task require X that /{skill} provides? | INSTEAD OF auto-invoking based on skill_hint alone |
| RULE_BREAKER | WHEN {trigger from broken rule} occurs (specific condition) | THEN {action from broken rule} — this rule exists and must be followed | INSTEAD OF reverting to old behavior |
| SELF_ROUTE | WHEN assigned task contains {domain keywords} | THEN route to {correct_agent} immediately without attempting the task | INSTEAD OF self-executing specialist work |
| DEBUGGING_LOOP | WHEN bash returns error AND total bash_error count for task exceeds 3 | THEN stop bash iteration, read error message fully, consult docs or ask kublai | INSTEAD OF retrying bash with minor variations |
| STALE_SKILL_HINT | WHEN skill_hint in task frontmatter does not match chosen skill | THEN update skill_hint in task spec AND log mismatch to kublai | INSTEAD OF silently using a different skill |

**Generation rules:**
- Every WHEN clause must contain a MEASURABLE condition (a metric, a count, a threshold)
- Every THEN clause must name a SPECIFIC action (a file, script, tool, or agent)
- Every INSTEAD OF must describe the OBSERVED failing behavior from the evidence, not a generic placeholder
- Do NOT generate rules for red flags with confidence=LOW and only 1 data point
- Do NOT duplicate a rule that already exists in the agent's active rules

**Phase 4 complete marker:**
```
[PHASE 4 COMPLETE] agent={agent} rule_candidates={count} high_confidence={count} skipped_low_evidence={count}
```

---

## Phase 5 — Skill Improvement Proposals (opus, <90s)

For any skill with DEAD_SKILL or RETRY_MAGNET flags (or effectiveness_normalized < 0.5 over 5+ invocations), generate a structured skill improvement proposal.

**Proposal format:**

```markdown
# Skill Improvement Proposal: {skill_name}

**Agent:** {agent}
**Generated by:** kurultai-reflect
**Timestamp:** {ISO timestamp}
**Evidence window:** last {N}h, {count} invocations

## Measured Problem
- Phase completion ratio: {value} (threshold: 0.60)
- Effectiveness normalized: {value} (threshold: 0.50)
- Retry magnet rate: {value} (threshold: 0.30)
- Artifact score avg: {value}/3
- Fit score avg: {value}/3

## Observed Failure Pattern
{Specific description of what fails, with evidence. E.g.: "Phase 3 (Synthesis) never completes —
analysis of 8 invocations shows all terminate at Phase 2 with 'context limit exceeded' in logs."}

## Proposed Change to SKILL.md

### Option A — Structural fix (preferred if root cause is phase design)
{Specific change: e.g., "Split Phase 3 into two sub-phases. Add a token budget check
before synthesis step. Cap input to 2000 tokens by summarizing Phase 2 output first."}

### Option B — Scope reduction (if skill is over-broad)
{Specific change: e.g., "Remove the 'competitive landscape' step from /horde-brainstorming
when invoked with trigger_type=skill_hint. Reserve that step for manual invocations only."}

## Proposed Skill File Change (diff-style)

```diff
## Phase 3 — Synthesis
- Synthesize all research findings into a comprehensive report
+ Synthesize findings. Token budget: 1500 tokens max.
+ If input exceeds 1500 tokens, summarize Phase 2 output first:
+   python3 ~/.openclaw/agents/main/scripts/summarize_phase.py --max-tokens 1500
```

## Acceptance Criteria
- Phase completion ratio reaches > 0.75 within 5 invocations after change
- No retry_magnet events within 48h of change

## Review Required
- [ ] Kublai review (routing impact)
- [ ] {agent} review (skill owner)
```

Write proposal to: `~/.openclaw/agents/main/proposals/{agent}-reflect-{YYYYMMDD-HHMMSS}.md`

If no skills qualify for improvement proposals, output:
```
[PHASE 5] No skills meet improvement threshold. Skipping proposal generation.
```

**Phase 5 complete marker:**
```
[PHASE 5 COMPLETE] agent={agent} proposals_written={count} skills_flagged={list}
```

---

## Phase 6 — Memory Write (opus, <30s)

Write approved rule candidates to the agent's memory file. Only write HIGH or MEDIUM confidence rules.

### Memory write format

Find the agent's current memory file:
```
~/.openclaw/agents/{agent}/memory/{YYYY-MM-DD}.md
```

If today's file doesn't exist, create it with a header. Append to the `## ACTIVE RULES` section. If the section doesn't exist, add it.

```markdown
## ACTIVE RULES (from kurultai-reflect {YYYY-MM-DD HH:MM})

{N}. {RULE TEXT — full WHEN/THEN/INSTEAD OF}
   - Evidence: {specific metric} = {value}, {count} occurrences
   - Generated: {timestamp}
   - Verification: {binary check}
```

**Memory write rules:**
- NEVER overwrite existing rules — only append
- NEVER write LOW confidence rules to memory
- If an identical or near-identical rule already exists, skip and log "RULE_EXISTS: skipping duplicate"
- Maximum 3 new rules per kurultai-reflect run per agent (to prevent rule flooding)
- If more than 3 rule candidates exist, write the 3 with highest confidence + most evidence data points

After writing, emit a ledger event:

```python
import json
from datetime import datetime
from pathlib import Path

LEDGER = Path.home() / ".openclaw/tasks/task-ledger.jsonl"
event = {
    "event": "REFLECT_SUMMARY",
    "ts": datetime.now().isoformat(),
    "agent": "{agent}",
    "red_flags": ["{list}"],
    "rules_generated": {count},
    "rules_written": {count},
    "proposals_created": {count},
    "skills_flagged": ["{list}"],
    "window_hours": 2,
    "generated_by": "kurultai-reflect"
}
with open(LEDGER, "a") as f:
    f.write(json.dumps(event) + "\n")
```

**Phase 6 complete marker:**
```
[PHASE 6 COMPLETE] agent={agent} rules_written={count} rules_skipped={count} ledger_event=written
```

---

## Phase 7 — Summary Report (opus, <45s)

Generate a triage summary. **Kublai runs two sub-phases: 7a (self-reflection) then 7b (system-wide fleet view). All other agents run 7a only.**

---

### Phase 7a — Agent Self-Reflection (all agents including kublai)

Produce a compact self-assessment for the target agent's own actions over the last 2h.

```markdown
# kurultai-reflect: {agent} — {YYYY-MM-DD HH:MM}

## My Red Flags (2h)
| Flag | Evidence | Action Taken |
|------|----------|--------------|
| {FLAG_TYPE} | {metric=value, N occurrences} | {Rule written / Proposal created / No action} |

## Rules Written to My Memory
| Rule (abbreviated) | Confidence | Evidence |
|-------------------|------------|---------|
| {WHEN...THEN...} | HIGH/MEDIUM | {specific metric} |

## Skill Improvement Proposals I Created
| Skill | Problem | File |
|-------|---------|------|
| /{skill} | {measured issue} | {path} |

## Architecture Drift Check
- Invariants reviewed: {count from ARCH_CONTEXT}
- Violations detected: {count} — {list or "none"}
- My role as documented: {one-line from ARCH_CONTEXT}
- My actual behavior this cycle: {one-line assessment}

## My Status
{ONE of: HEALTHY (no red flags) | NEEDS_ATTENTION (rules written) | CRITICAL (architectural drift detected)}
```

---

### Phase 7b — System Fleet View (kublai ONLY)

After completing 7a for himself, kublai produces a system-wide view across all 6 agents. Read `REFLECT_SUMMARY` events from all other agents' runs this cycle from the ledger.

```markdown
## System Health — Fleet View (2h)

### Per-Agent Status
| Agent | Status | Red Flags | Rules Written | Proposals |
|-------|--------|-----------|---------------|-----------|
| temujin | NEEDS_ATTENTION | DEBUGGING_LOOP | 1 | 0 |
| mongke | NEEDS_ATTENTION | DEAD_SKILL: /scrapling-research | 1 | 1 |
| chagatai | HEALTHY | none | 0 | 0 |
| jochi | NEEDS_ATTENTION | HOLLOW_SUCCESS | 1 | 0 |
| ogedei | HEALTHY | none | 0 | 0 |
| kublai | HEALTHY | none | 0 | 0 |

### Fleet-Wide Skill Performance (2h)
| Skill | Invocations | Avg Effectiveness | Fleet-Wide Flag |
|-------|------------|-------------------|-----------------|
| /horde-brainstorming | 8 | 0.81 | — |
| /scrapling-research | 4 | 0.38 | DEAD_SKILL (mongke) |
| /senior-backend | 3 | 0.62 | — |

### Kublai Self-Assessment: Routing Quality
- Tasks routed this cycle: {N}
- Skill hints assigned: {N} ({pct}% of tasks)
- Skill hint accuracy (hint matched actual skill invoked): {pct}%
- Self-route violations: {count} (should be 0 per architecture §4)
- Delegation score avg: {value}/2

### Architecture Invariant Status (fleet-wide)
- Documented invariants checked: {N}
- Fleet-wide violations: {list or "none"}

### Recommended Actions for Kublai
1. {Specific routing change if skill data supports it — cite evidence}
2. {Agent intervention if CRITICAL status detected}
3. {Skill proposal review if any queued}
4. {architecture.md update if documented behavior diverges from reality}

If no actions needed:
> Fleet behavioral health: no structural issues detected this cycle.
```

Write both reports to: `~/.openclaw/agents/main/logs/kurultai-reflect-{YYYY-MM-DD-HHMM}-{agent}.md`

For kublai, write a combined file with both 7a and 7b sections.

**Phase 7 complete marker:**
```
[PHASE 7 COMPLETE] agent={agent} report_written={path} is_kublai={true|false} fleet_view_included={true|false}
```

---

## Invocation

### Run for a single agent (within hourly pipeline)
```bash
claude-agent --dangerously-skip-permissions -p "
You are running the kurultai-reflect skill for agent: {AGENT}.
Read ~/.openclaw/agents/main/skills/kurultai-reflect/SKILL.md and execute all 7 phases.
Target agent: {AGENT}
Window: last 2 hours
Model guidance: use analytical mode, be precise, cite specific metrics.
Complete all 7 phases and output phase completion markers.
"
```

### Run for all agents (called by hourly_reflection.sh)
```bash
for agent in temujin mongke chagatai jochi ogedei kublai; do
    python3 ~/.openclaw/agents/main/scripts/score_tasks.py --hours 2
    claude-agent --dangerously-skip-permissions -p \
        "Run kurultai-reflect SKILL.md for agent: $agent. Window: 2h. All 7 phases." \
        2>> ~/.openclaw/agents/main/logs/kurultai-reflect.log
done
```

### Dry run (Phase 1-2 only, no writes)
```bash
claude-agent --dangerously-skip-permissions -p "
Run kurultai-reflect phases 1 and 2 only for agent: {AGENT}.
Do NOT write to memory (Phase 6) or create proposals (Phase 5).
Output all detected red flags and rule candidates, then stop.
"
```

---

## Integration with Hourly Pipeline

### Positioning

Insert **after** Phase 3 of the existing `hourly_reflection.sh` (after routing_audit_action.py, before kublai-actions.py):

```bash
# Existing: Phase 1 — meta_reflection.py
# Existing: Phase 2 — kurultai_brainstorm.py  (keep for now, run in parallel)
# Existing: Phase 3 — routing_audit_action.py
# NEW:      Phase 3b — kurultai-reflect (data-driven rule generation)
python3 ~/.openclaw/agents/main/scripts/score_tasks.py --hours 2
for agent in temujin mongke chagatai jochi ogedei kublai; do
    claude-agent -p "Run kurultai-reflect SKILL.md for agent: $agent" \
        >> ~/.openclaw/agents/main/logs/kurultai-reflect.log 2>&1 &
done
wait  # all agents run in parallel, each under 3 minutes
# Existing: Phase 4 — kublai-actions.py
# Existing: Phase 5 — kurultai_review.py --expire
# Existing: Phase 6 — kublai-initiative.py
```

### Relationship to kurultai-brainstorm.py

- **kurultai-brainstorm.py** (keep): runs /horde-brainstorming for open-ended architectural proposals (once per 6h per agent, not every cycle)
- **kurultai-reflect** (new): runs every cycle, data-driven, targets specific measured failures, writes rules directly

These are complementary. kurultai-reflect handles known failure patterns with evidence. kurultai-brainstorm handles speculative improvement and architectural exploration.

---

## Operating Rules

- **Never invent evidence.** If a metric is missing, state "INSUFFICIENT DATA" and skip the rule candidate for that red flag.
- **Never write more than 3 rules per agent per run.** Quality over quantity — rule flooding degrades adherence rates.
- **Always cite the specific event or metric.** Every rule candidate output must include: red_flag type, evidence (metric=value, event count), task_id(s) if available.
- **Skip LOW confidence.** Only write HIGH or MEDIUM confidence rules to memory. Log LOW confidence candidates to the report but do not commit them.
- **Proposals require 3+ data points.** Do not create a skill improvement proposal based on fewer than 3 invocations. A single bad run is noise, not a pattern.
- **Check for existing rules before writing.** Read the agent's ACTIVE RULES section before generating. If an identical trigger already exists in a rule, note "RULE_EXISTS" and skip.
- **Phase markers are mandatory.** Output every `[PHASE N COMPLETE]` line in order. These are parsed by pipeline_health.py for phase_completion_ratio tracking of this skill itself.
- **No hedge words.** WHEN/THEN rules must use imperative language: THEN do X, not THEN consider doing X.

---

## Telemetry This Skill Emits

When this skill runs, it emits the following events to the ledger (for self-measurement):

```jsonl
{"event": "SKILL_INVOCATION", "skill_name": "/kurultai-reflect", "agent": "kublai", "phases_expected": 8, "trigger_type": "hourly_pipeline", "ts": "..."}
{"event": "REFLECT_SUMMARY", "agent": "{target_agent}", "red_flags": [...], "rules_generated": N, "rules_written": N, "proposals_created": N, "ts": "..."}
{"event": "SKILL_OUTCOME", "skill_name": "/kurultai-reflect", "phase_completion_ratio": 1.0, "artifact_score": 3, "fit_score": 3, "ts": "..."}
```

This means kurultai-reflect measures itself using the same telemetry it analyzes. If kurultai-reflect itself develops a DEAD_SKILL flag (its own phase_completion_ratio < 0.60), that is surfaced in the next cycle.
