#!/bin/bash
# hermes-resume.sh — Staged resume of Hermes capabilities.
#
# Removes kill-switch flags tier-by-tier with a confirmation prompt at
# each step. Matches the natural safety ordering: T0 first, then
# autonomous content, then autonomous code, then scheduled sweeps.
#
# Answer 'yes' to each prompt to proceed; anything else skips that tier.

set -e
FLAGS_DIR="$HOME/.openclaw/flags"

confirm() {
    # Read a yes/no from terminal. Returns 0 on 'yes', 1 otherwise.
    local prompt="$1"
    local answer
    read -rp "$prompt (type 'yes' to proceed): " answer
    [[ "$answer" == "yes" ]]
}

echo "Hermes staged resume."
echo ""

if confirm "Tier 1 — resume T0 auto-fix + daemon normal operation?"; then
    rm -f "$FLAGS_DIR/hermes-disabled.flag" "$FLAGS_DIR/hermes-risky-disabled.flag"
    echo "  Tier 1 resumed."
else
    echo "  Tier 1 skipped."
fi
echo ""

if confirm "Tier 2 — resume autonomous master + content fixes?"; then
    rm -f "$FLAGS_DIR/hermes-autonomous-disabled.flag" \
          "$FLAGS_DIR/hermes-autonomous-fix-content-disabled.flag"
    echo "  Tier 2 resumed."
else
    echo "  Tier 2 skipped."
fi
echo ""

if confirm "Tier 3 — resume autonomous code fixes?"; then
    rm -f "$FLAGS_DIR/hermes-autonomous-fix-code-disabled.flag"
    echo "  Tier 3 resumed."
else
    echo "  Tier 3 skipped."
fi
echo ""

if confirm "Tier 4 — resume scheduled sweeps?"; then
    rm -f "$FLAGS_DIR/hermes-autonomous-sweep-disabled.flag"
    echo "  Tier 4 resumed."
else
    echo "  Tier 4 skipped."
fi

echo ""
echo "Resume sequence complete. Remaining flags (if any):"
remaining=$(ls "$FLAGS_DIR"/hermes-*.flag 2>/dev/null)
if [[ -z "$remaining" ]]; then
    echo "  (none — all Hermes capability active)"
else
    echo "$remaining" | awk '{print "  " $0}'
fi
