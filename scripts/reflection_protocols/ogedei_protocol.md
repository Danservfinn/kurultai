# Ogedei Reflection Protocol (Ops)

Focus: System uptime, incident response time, monitoring gaps, cron reliability.

## Role-Specific Questions

1. **INCIDENTS:** What system issues occurred? How fast did you detect and respond?
2. **MONITORING GAPS:** What issue would have been caught sooner with better monitoring?
3. **CRON HEALTH:** Are all cron jobs healthy? Any recurring failures you haven't root-caused?
4. **PROACTIVE:** What preventive action did you take before a problem occurred?

## REFLECTION (complete all 6 — be specific, no hedge words)

1. **WORST MOMENT:** Your biggest ops miss or slowest response this session. (max 30 words)
2. **ROOT CAUSE:** The behavioral pattern that caused it. (max 20 words)
3. **NEW RULE:** WHEN [trigger] THEN [action] INSTEAD OF [old default]. (max 30 words)
4. **VERIFICATION:** How will you know you followed this rule next session? (binary YES/NO check)
5. **PREVIOUS RULES:** For each active rule — did you follow it? YES or NO with brief reason.
6. **THROUGHPUT:** Check Pipeline Health above. Your contribution: N completed, N generated for others.
   Is the system getting faster? What is YOUR specific action to reduce pending time?

## Performance Review (horde-review step)

Before brainstorming, /horde-review runs a critical analysis of your performance.
The review evaluates your Ops output across these dimensions:

- **Incident response time:** Detection-to-resolution latency.
- **Monitoring coverage:** Issues that would have been caught with better checks.
- **Cron reliability:** Job success rate, recurring failures root-caused.
- **Proactive actions:** Preventive work done before problems surfaced.

Review output is written to `logs/reviews/ogedei-latest.md` and fed into brainstorming.

## Brainstorming Focus (for horde-brainstorming step)

After review analysis, brainstorm improvements in YOUR domain:
- **Incident response:** Faster detection-to-resolution, automated remediation steps
- **Monitoring gaps:** New health checks, better alerting thresholds
- **Cron reliability:** Preventing recurring cron failures, better error recovery
- **Proactive ops:** Predictive maintenance, capacity planning, preventive automation

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
