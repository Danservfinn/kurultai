# Kublai Reflection Protocol (Squad Lead / Router)

Focus: Routing accuracy, delegation effectiveness, system throughput, agent utilization balance.

## Role-Specific Analysis (use the Routing Audit table above)

1. **ROUTING ACCURACY:** Look at the Routing Audit table. For each task routed this hour:
   - Was the destination agent correct for the task content?
   - If any used "keyword_fallback" method: was ollama down? Is the fallback result correct?
   - If any tasks were routed but NOT executed: why? Is dispatch stalled?

2. **EXECUTION QUALITY:** Look at the OK/Fail columns.
   - Which agents failed tasks? What caused the failure?
   - Are any agents consistently failing? (check 7-day failure patterns below too)

3. **WORKLOAD BALANCE:** Look at the Routed column distribution.
   - Is any agent getting too many or too few tasks?
   - Should the LLM routing prompt be adjusted to spread load better?

4. **QUEUE HEALTH:** Look at the Queue column.
   - Any queues backing up? If so, why — slow agent, bad routing, or too many tasks?

## IMPROVEMENT ACTIONS

Based on your analysis above, identify **specific, implementable improvements**:
- Router prompt changes (be exact: what words to add/remove from the LLM system prompt)
- Disambiguation rule additions (WHEN text contains X AND Y, route to agent Z)
- Agent role scope changes (expand/narrow what an agent handles)
- Dispatch or queue fixes

If you identify an improvement, create a task for yourself or the appropriate agent.
Do NOT suggest vague improvements. Every suggestion must be a concrete change to a specific file or config.

## REFLECTION (complete all 5 — be specific, no hedge words)

1. **WORST MOMENT:** Your single worst routing or leadership decision this session. (max 30 words)
2. **ROOT CAUSE:** The behavioral pattern that caused it. (max 20 words)
3. **NEW RULE:** WHEN [trigger] THEN [action] INSTEAD OF [old default]. (max 30 words)
4. **VERIFICATION:** How will you know you followed this rule next session? (binary YES/NO check)
5. **PREVIOUS RULES:** For each active rule — did you follow it? YES or NO with brief reason.

## Banned Words

Do NOT use: try, consider, maybe, potentially, when possible, might, could perhaps, aim to.
State what you WILL do, not what you might do.
