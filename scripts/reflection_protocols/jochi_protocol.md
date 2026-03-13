# Jochi Reflection Protocol (Analyst)

Focus: Detection coverage, analysis accuracy, false positive rate, security posture.

## Role-Specific Questions

1. **DETECTION:** What anomalies or issues did you identify this session? Were they real?
2. **MISSES:** What anomalies did another agent or system catch that you should have found first?
3. **FALSE POSITIVES:** Did you raise any alarms that turned out to be non-issues?
4. **SECURITY:** Were there security-relevant events you should have flagged but didn't?

## REFLECTION (complete all 6 — be specific, no hedge words)

1. **WORST MOMENT:** Your biggest analytical miss or false alarm this session. (max 30 words)
2. **ROOT CAUSE:** The behavioral pattern that caused it. (max 20 words)
3. **NEW RULE:** WHEN [trigger] THEN [action] INSTEAD OF [old default]. (max 30 words)
4. **VERIFICATION:** How will you know you followed this rule next session? (binary YES/NO check)
5. **PREVIOUS RULES:** For each active rule — did you follow it? YES or NO with brief reason.
6. **THROUGHPUT:** Check Pipeline Health above. Your contribution: N completed, N generated for others.
   Is the system getting faster? What is YOUR specific action to reduce pending time?

## Performance Review (horde-review step)

Before brainstorming, /horde-review runs a critical analysis of your performance.
The review evaluates your Analyst output across these dimensions:

- **Detection accuracy:** True positives vs false positives ratio.
- **Coverage gaps:** Anomalies caught by others that you missed.
- **Security posture:** Proactive vs reactive security findings.
- **Analysis speed:** Time from alert to triage completion.

Review output is written to `logs/reviews/jochi-latest.md` and fed into brainstorming.

## Brainstorming Focus (for horde-brainstorming step)

After review analysis, brainstorm improvements in YOUR domain:
- **Detection coverage:** New signals or patterns to monitor for anomalies
- **False positive reduction:** Better thresholds, smarter baseline comparisons
- **Security posture:** Proactive security checks, vulnerability scanning improvements
- **Analysis speed:** Faster triage of alerts, automated pre-classification

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
