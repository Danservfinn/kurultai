# Routing Pipeline Overflow Gap Analysis

**Author:** chagatai (Writer agent)
**Date:** 2026-03-09 (Updated: 2026-03-09 13:40)
**Status:** ✅ RESOLVED — Overflow entries added to task_intake.py lines 857-863

## Executive Summary

**UPDATE:** The overflow configuration has been implemented. The skill overflow bypass mechanism now includes entries for:
- `/content-research-writer`: ["mongke", "tolui"] (line 857)
- `/changelog-generator`: ["mongke", "tolui"] (line 860)
- `/horde-learn`: ["jochi", "chagatai"] (line 863)

**NEW BLOCKER IDENTIFIED:** Fleet-wide credential crisis (DashScope tokens instead of sk-ant-) is blocking ALL agent task execution. See MEMORY.md "⚠️ CRITICAL: Fleet Credential Crisis".

## The Overflow Mechanism

When a task arrives with a skill hint (e.g., `/content-research-writer`), the routing system:

1. **Locks the task to the skill's primary agent** (skill-locked routing)
2. **Checks if overflow is needed** via `should_bypass_skill_lock()`
3. **Looks up the skill in `_SKILL_CAPABLE_ALTERNATES`**
4. **If NOT found**: Returns `"skill_not_in_alternates"` — NO OVERFLOW OCCURS
5. **If found**: Routes to the lowest-depth alternate agent

## Configuration Status (2026-03-09 13:40)

### ✅ `/content-research-writer` — IMPLEMENTED

- **Primary agent:** chagatai
- **Task types:** blog posts, articles, content, documentation
- **Overflow config:** ✅ ["mongke", "tolui"] (line 857)
- **Impact:** When chagatai has 3+ queued tasks, content tasks can overflow to mongke/tolui

### ✅ `/horde-learn` — IMPLEMENTED

- **Primary agent:** mongke
- **Task types:** research tasks
- **Overflow config:** ✅ ["jochi", "chagatai"] (line 863)
- **Impact:** Research tasks overflow to jochi/chagatai when mongke is overloaded

### ✅ `/changelog-generator` — IMPLEMENTED

- **Primary agent:** chagatai
- **Task types:** changelogs, release notes
- **Overflow config:** ✅ ["mongke", "tolui"] (line 860)
- **Impact:** Changelog tasks can overflow to mongke/tolui

## Current Alternates Map

```python
_SKILL_CAPABLE_ALTERNATES = {
    "/horde-brainstorming": ["mongke", "jochi", "chagatai"],
    "/horde-implement": ["ogedei"],
    "/horde-debug": ["jochi", "ogedei"],
    "/horde-review": ["jochi"],
    "/horde-plan": ["mongke", "chagatai"],
}
```

**Notice:** None of chagatai's primary skills (`/content-research-writer`, `/changelog-generator`) are listed.

## Recommended Fix (✅ COMPLETED 2026-03-09)

The three overflow entries were added to `_SKILL_CAPABLE_ALTERNATES`:

```python
# Content writing overflow (line 856-857)
"/content-research-writer": ["mongke", "tolui"],

# Changelog generation overflow (line 859-860)
"/changelog-generator": ["mongke", "tolui"],

# Research overflow (line 862-863)
"/horde-learn": ["jochi", "chagatai"],
```

**Verification:** Run `grep -A1 "content-research-writer\|changelog-generator\|horde-learn" task_intake.py | grep ":"`

## Domain Compatibility Verification

All proposed alternates are pre-validated in `DOMAIN_AGENT_COMPATIBILITY`:

```python
"documentation": ["chagatai", "mongke", "tolui"]  # Line 88
```

This ensures overflow routes respect domain boundaries.

## Metrics Impact

### Before Fix
- **chagatai completion rate:** 0% (no throughput)
- **Queue behavior:** Tasks accumulate without overflow
- **System impact:** Content work effectively blocked

### After Fix (Expected)
- **chagatai completion rate:** Measurable throughput
- **Overflow path:** chagatai → mongke/tolui when overloaded
- **System impact:** Content work unblocked

## Related Files

- `scripts/task_intake.py` (lines 791-806, 1228-1268)
- `scripts/llm_routing_judge.py` (LLM fallback routing)
- `docs/routing-idle-agent-bypass-diagnostic.md` (related diagnostic)

## Implementation Task

See: `temujin/tasks/enable-chagatai-content-skill-overflow-1773074000.md` (✅ COMPLETED)

---

## Changelog

| Date | Change | Status |
|------|--------|--------|
| 2026-03-09 13:40 | Updated status to RESOLVED — overflow config verified in lines 857-863 | ✅ Complete |
| 2026-03-09 12:32 | Initial diagnostic created, temujin task filed | 📝 Proposed |
| 2026-03-09 | Overflow entries added to task_intake.py | ✅ Implemented |
