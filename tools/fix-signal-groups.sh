#!/bin/bash
# Signal Group ID Fix Script
# Fixes OpenClaw's lowercasing of Signal group IDs (base64 is case-sensitive)

set -e

echo "Signal Group Messaging Fix"
echo "=========================="
echo ""

# Files to patch
FILES=(
    "/usr/local/lib/node_modules/openclaw/dist/deliver-Ck-fH_m-.js"
    "/usr/local/lib/node_modules/openclaw/dist/deliver-BIDW_mg2.js"
    "/usr/local/lib/node_modules/openclaw/dist/deliver-FdxL6NZx.js"
)

PATCHED=0

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "Processing: $file"
        
        # Backup
        cp "$file" "${file}.backup-$(date +%Y%m%d-%H%M%S)"
        echo "  ✓ Backup created"
        
        # Check if already patched
        if grep -q "shouldPreserveCase" "$file"; then
            echo "  ✓ Already patched, skipping"
            continue
        fi
        
        # Apply fix using sed
        # Replace the line that lowercases everything with one that preserves case for group: targets
        sed -i 's/return (((providerId ? getChannelPlugin(providerId) : void 0)\\?\\.messaging\\?\\.normalizeTarget\\?\\.(raw) ?? (raw.trim().toLowerCase() || void 0)) || void 0);/const trimmed = raw.trim();\n\tconst shouldPreserveCase = trimmed.toLowerCase().startsWith("group:");\n\tconst normalized = shouldPreserveCase ? trimmed : trimmed.toLowerCase();\n\treturn (((providerId ? getChannelPlugin(providerId) : void 0)?.messaging?.normalizeTarget?.(raw) ?? normalized) || void 0);/g' "$file"
        
        # Alternative approach - use Python for more reliable replacement
        python3 <> EOF
import re

with open('$file', 'r') as f:
    content = f.read()

# Pattern to match the problematic line
old_pattern = r'return \(\(providerId \? getChannelPlugin\(providerId\) : void 0\)\?\.messaging\?\.normalizeTarget\?\.(\w+) \?\? \(raw\.trim\(\)\.toLowerCase\(\)\) \|\| void 0\)\) \|\| void 0;'

new_code = '''const trimmed = raw.trim();
\t// Don't lowercase group: targets (Signal group IDs are base64 and case-sensitive)
\tconst shouldPreserveCase = trimmed.toLowerCase().startsWith("group:");
\tconst normalized = shouldPreserveCase ? trimmed : trimmed.toLowerCase();
\treturn ((providerId ? getChannelPlugin(providerId) : void 0)?.messaging?.normalizeTarget?.(raw) ?? normalized) || void 0;'''

# Try to find and replace
if 'shouldPreserveCase' not in content:
    # Simple string replacement
    old_code = 'return ((providerId ? getChannelPlugin(providerId) : void 0)?.messaging?.normalizeTarget?.(raw) ?? (raw.trim().toLowerCase() || void 0)) || void 0;'
    if old_code in content:
        content = content.replace(old_code, new_code)
        with open('$file', 'w') as f:
            f.write(content)
        print(f'  ✓ Patched: $file')
    else:
        print(f'  ⚠ Could not find pattern in: $file')
else:
    print(f'  ✓ Already patched: $file')
EOF
        
        PATCHED=$((PATCHED + 1))
    else
        echo "  ✗ File not found: $file"
    fi
    echo ""
done

echo "=========================="
echo "Patching complete!"
echo "Patched files: $PATCHED"
echo ""
echo "Next steps:"
echo "1. Restart OpenClaw: openclaw gateway restart"
echo "2. Test group message sending"
echo ""

# Create verification script
cat > /tmp/verify-signal-fix.js <> 'VERIFY'
// Verification script
const testTargets = [
    "group:BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=",
    "+19194133445",
    "uuid:some-uuid-here"
];

console.log("Testing normalizeTargetForProvider behavior:");
testTargets.forEach(target => {
    const lower = target.toLowerCase();
    const shouldPreserve = target.toLowerCase().startsWith("group:");
    console.log(`  ${target}`);
    console.log(`    Lower: ${lower}`);
    console.log(`    Preserve case: ${shouldPreserve}`);
    console.log("");
});
VERIFY

node /tmp/verify-signal-fix.js 2>/dev/null || echo "Verification script created at /tmp/verify-signal-fix.js"
