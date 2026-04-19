#!/bin/bash
# hermes-panic-stop.sh — Engage EVERY Hermes kill-switch in one call.
#
# Halts all autonomous + T0 activity immediately. Already-committed fixes
# are not reverted — use 'revert all today' via Signal if you also want to
# undo recent changes.
#
# Idempotent: safe to run multiple times.

set -e
FLAGS_DIR="$HOME/.openclaw/flags"
mkdir -p "$FLAGS_DIR"

for flag in hermes-disabled.flag \
            hermes-risky-disabled.flag \
            hermes-autonomous-disabled.flag \
            hermes-autonomous-fix-code-disabled.flag \
            hermes-autonomous-fix-content-disabled.flag \
            hermes-autonomous-sweep-disabled.flag; do
    touch "$FLAGS_DIR/$flag"
done

echo "PANIC STOP ENGAGED — all Hermes autonomous + T0 capability halted."
echo ""
echo "Flags set in $FLAGS_DIR:"
ls -la "$FLAGS_DIR"/hermes-*.flag 2>/dev/null | awk '{print "  " $NF " (" $6 " " $7 " " $8 ")"}'
echo ""
echo "To resume: run hermes-resume.sh (staged tier-by-tier)."

# Best-effort notification (non-fatal if the queue itself is broken)
python3 "$HOME/.openclaw/agents/main/scripts/hermes_notify.py" --panic-stop-engaged 2>/dev/null || true
