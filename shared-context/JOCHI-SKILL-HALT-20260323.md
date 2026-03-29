# SKILL_HALT: /horde-review (R-JOCHI-10)

**Agent:** jochi
**Date:** 2026-03-23
**Task:** normal-fix-resolution-normal-1773979337-bf765e33-5b91257d
**Rule triggered:** R-JOCHI-10

## What Happened

The last 5 consecutive `/horde-review` invocations for jochi all failed (`success=False` in skill-invocations.jsonl). Per R-JOCHI-10, jochi halted the skill invocation and logged this SKILL_HALT event.

## Evidence

From `~/.openclaw/tasks/skill-invocations.jsonl`:
- 2026-03-23T00:30:06 — success: false
- 2026-03-23T00:31:33 — success: false
- 2026-03-23T00:38:32 — success: false
- 2026-03-23T00:38:46 — success: false
- 2026-03-23T00:41:16 — success: false

## Action Required

The `/horde-review` skill is consistently failing. Ogedei or kublai should investigate why. Possible causes:
1. Skill configuration broken
2. Dependency missing
3. Skill file corrupted
