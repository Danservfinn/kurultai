---
name: rule-registry-keyerror-fix
description: KeyError fix in rule_registry.py that was crashing memory_audit.py --fix and blocking all memory maintenance
type: project
---

## rule_registry.py KeyError Bug Fix (2026-03-12)

**Fact:** `memory_audit.py --fix` was crashing with `KeyError: 'text'` when processing rule entries that lacked the "text" field. This blocked ALL memory maintenance operations.

**Why:** Rule entries in `rules.json` can be created with missing fields (e.g., from failed or partial writes). Two locations in `rule_registry.py` accessed `r["text"]` without `.get()` safety.

**Fixed locations:**
- `scripts/rule_registry.py` line ~139 in `add_rule()`: `r["text"]` → `r.get("text", "")`
- `scripts/rule_registry.py` line ~281 in `_extract_and_add_rules()`: `r["text"]` → `r.get("text", "")`

**How to apply:** If `memory_audit.py --fix` crashes with KeyError on "text", check rule_registry.py for unsafe dict access on rule objects.

**Impact of the bug:** Before fix, every `memory_audit.py --fix` run would crash after loading, preventing:
- Rule sync (96 rules pending across 6 agents)
- Dead rule deprecation
- Stale log deletion (32 files, 252+ KB)
- Context compaction
- Duplicate rule detection
