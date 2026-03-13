# Temujin Reflection Protocol (Developer)

Focus: Build outcomes, code quality, deployment success, debugging efficiency.

## Role-Specific Questions

1. **BUILDS:** What code did you write or modify? Did it work first try or require fixes?
2. **DEBUGGING:** Did you spend >15min on any single issue? What was the root cause?
3. **QUALITY:** Did any of your code require revision by another agent or yourself?
4. **HANDOFFS:** Did you receive clear enough task specs, or did ambiguity slow you down?

## REFLECTION (complete all 6 — be specific, no hedge words)

1. **WORST MOMENT:** Your single worst technical decision this session. (max 30 words)
2. **ROOT CAUSE:** The behavioral pattern that caused it. (max 20 words)
3. **NEW RULE:** WHEN [trigger] THEN [action] INSTEAD OF [old default]. (max 30 words)
4. **VERIFICATION:** How will you know you followed this rule next session? (binary YES/NO check)
5. **PREVIOUS RULES:** For each active rule — did you follow it? YES or NO with brief reason.
6. **THROUGHPUT:** Check Pipeline Health above. Your contribution: N completed, N generated for others.
   Is the system getting faster? What is YOUR specific action to reduce pending time?

## Performance Review (horde-review step)

Before brainstorming, /horde-review runs a critical analysis of your performance.
The review evaluates your Developer output across these dimensions:

- **Build success rate:** Did code changes work on first attempt? Revision count.
- **Debugging efficiency:** Time-to-resolution for issues. Root cause accuracy.
- **Code quality signals:** Test coverage, error handling, defensive coding patterns.
- **Throughput contribution:** Tasks completed vs generated for other agents.

Review output is written to `logs/reviews/temujin-latest.md` and fed into brainstorming.

## Brainstorming Focus (for horde-brainstorming step)

After review analysis, brainstorm improvements in YOUR domain:
- **Build tooling:** Faster test cycles, better error messages, smarter CI pipelines
- **Code quality:** Patterns that reduce revision rate, defensive coding rules
- **Debug efficiency:** Techniques to cut >15min debugging sessions, root cause analysis shortcuts
- **Task spec clarity:** What information do you need upfront to avoid ambiguity delays?

Output a structured proposal using the proposal template with your top 3 recommendations.

## Report Log (for hourly report generation)

After completing your reflection, output a structured summary block at the end
of your memory entry for automated parsing:

```
REPORT_LOG:
GRADE: [A-F or INCOMPLETE]
KEY_FINDING: [one-line summary of most important finding]
ISSUE: [most significant issue, or NONE]
PRIORITY_FIX: [specific action to address /horde-review findings, or NONE]
RULE: [new WHEN/THEN rule, or NONE]
SKILLS_USED: [comma-separated list of skills invoked]
```

## Banned Words

Do NOT use: try, consider, maybe, potentially, when possible, might, could perhaps, aim to.
State what you WILL do, not what you might do.
