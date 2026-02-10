#!/bin/bash
# Fix Signal group ID corruption in OpenClaw
# The issue: normalizeTargetForProvider falls back to toLowerCase() 
# which corrupts base64-encoded Signal group IDs
#
# Root cause in /usr/local/lib/node_modules/openclaw/dist/deliver-Ck-fH_m-.js:2150
# return ((providerId ? getChannelPlugin(providerId) : void 0)?.messaging?.normalizeTarget?.(raw) ?? (raw.trim().toLowerCase() || void 0)) || void 0;
#
# The Signal plugin doesn't define normalizeTarget, so group IDs get lowercased.
# This changes "BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=" to 
# "broemhvnclgsz8treukbz6v3bedhdb0exajd+srp6oy=" which is invalid.

# Create a backup
BACKUP_DIR="/data/.openclaw/backups"
mkdir -p "$BACKUP_DIR"

# Backup the original files
for file in /usr/local/lib/node_modules/openclaw/dist/deliver-Ck-fH_m-.js /usr/local/lib/node_modules/openclaw/dist/deliver-BIDW_mg2.js /usr/local/lib/node_modules/openclaw/dist/deliver-FdxL6NZx.js; do
    if [ -f "$file" ]; then
        cp "$file" "$BACKUP_DIR/$(basename $file).backup-$(date +%Y%m%d-%H%M%S)"
    fi
done

# The fix requires modifying the normalizeTargetForProvider function
# to check if the target looks like a Signal group ID (starts with group:)
# and preserve the case for the actual group ID

echo "Signal group ID corruption fix"
echo "==============================="
echo ""
echo "The issue is in normalizeTargetForProvider function which lowercases"
echo "all targets when the channel plugin doesn't define normalizeTarget."
echo ""
echo "For Signal, this corrupts base64 group IDs."
echo ""
echo "To fix, we need to patch the function to preserve case for group: targets"
echo ""
echo "Files to patch:"
echo "  - /usr/local/lib/node_modules/openclaw/dist/deliver-Ck-fH_m-.js"
echo "  - /usr/local/lib/node_modules/openclaw/dist/deliver-BIDW_mg2.js"  
echo "  - /usr/local/lib/node_modules/openclaw/dist/deliver-FdxL6NZx.js"

# Note: A proper fix would be to add a normalizeTarget function to the Signal plugin
# or modify normalizeTargetForProvider to handle group: prefixes specially.
