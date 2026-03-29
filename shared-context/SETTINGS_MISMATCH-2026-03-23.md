# SETTINGS_MISMATCH: Configuration Layer Drift

**Date:** 2026-03-23T20:17:00Z
**Agent:** mongke
**Rule:** R17

## Issue

`/Users/kublai/.openclaw/agents/mongke/settings.json` contains `ANTHROPIC_MODEL=claude-sonnet-4-6`, but the documented requirement (per CLAUDE.md §3) is `claude-opus-4-6`.

## Current Status

**Runtime:** CORRECT
- Active session uses `claude-opus-4-6` (verified via tock session_match=true)
- Override mechanism is functioning properly
- No operational impact

**Configuration Layer:** DIVERGENT
- settings.json ANTHROPIC_MODEL does not match required model
- This is a configuration cleanup issue, not an operational failure

## Action Required

Assign to **Temujin** as low-priority config cleanup:
- Update settings.json ANTHROPIC_MODEL to claude-opus-4-6
- Verify override mechanism still works after change
- No urgency - runtime is functioning correctly

## Context

This mismatch has persisted across 9+ reflection cycles. Escalation via Signal has not produced resolution. R17 specifies: do NOT re-escalate via Signal (alert fatigue). Instead, log to shared-context for Temujin to address during routine config maintenance.

---

*R17 requirement satisfied: shared-context note created*
