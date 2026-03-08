#!/usr/bin/env python3
"""One-shot: Update model-specific rules to be model-agnostic."""
import sys, os, json, shutil
from datetime import datetime
sys.path.insert(0, os.path.expanduser("~/.openclaw/agents/main/scripts"))
from rule_registry import load_rules, save_rules, deprecate_rule, add_rule

REPLACEMENTS = {
    ("ogedei", "r007"): "WHEN task-handler spawns ogedei session AND session model does not match resolved config model THEN log MODEL_MISMATCH and request config audit from jochi INSTEAD OF silently running on wrong model",
    ("ogedei", "r011"): "WHEN task fails with execution_time < 120s THEN read full error output, verify config resolution in settings.json, and check auth credentials before retrying INSTEAD OF blind retry",
}

# Task 7.3: Track results for proper exit code and summary
updated_count = 0
failed_count = 0
agents_updated = set()
missing_files = []

for (agent, rule_id), new_text in REPLACEMENTS.items():
    rules_path = os.path.expanduser(f"~/.openclaw/agents/{agent}/memory/rules.json")
    if os.path.exists(rules_path):
        # Task 2.2: Idempotency check - skip if already deprecated with matching reason
        data = load_rules(agent)
        already_deprecated = False
        for r in data.get("rules", []):
            if r["id"] == rule_id and r["status"] == "deprecated":
                reason = r.get("deprecated_reason", "")
                if "superseded" in reason.lower() and "model-agnostic" in reason.lower():
                    already_deprecated = True
                    print(f"  SKIP {agent}/{rule_id}: already deprecated with matching reason")
                    break
        
        if already_deprecated:
            continue
        
        # Task 2.3: Create backup before modification
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = f"{rules_path}.bak.{timestamp}"
        shutil.copy2(rules_path, backup_path)
        print(f"  Backup created: {backup_path}")
        
        deprecate_rule(agent, rule_id, "superseded: model-agnostic replacement (pipeline fix 2026-03-07)")
        add_rule(agent, new_text, source="fix_model_rules.py")
        print(f"  Updated {agent}/{rule_id}")
        updated_count += 1
        agents_updated.add(agent)
    else:
        # Task 7.3: Log error for missing files instead of silent continue
        print(f"  ERROR: {rules_path} not found - cannot update {agent}/{rule_id}")
        missing_files.append(f"{agent}/{rule_id}")
        failed_count += 1

# Task 7.3: Print summary and return proper exit code
print(f"\n=== SUMMARY ===")
print(f"Updated {updated_count} rules across {len(agents_updated)} agent(s)")
if missing_files:
    print(f"Failed: {failed_count} (missing files: {', '.join(missing_files)})")
    print("Done with errors.")
    sys.exit(1)
else:
    print("Done. All model-specific rules replaced with model-agnostic versions.")
    sys.exit(0)
