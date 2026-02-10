# Signal Group Messaging Fix

## Issue Summary
Signal group messages fail with error:
```
Group not found: broemhvnclgsz8treukbz6v3bedhdb0exajd+srp6oY=
```

## Root Cause
OpenClaw's `normalizeTargetForProvider` function in the deliver module lowercases all targets when the channel plugin doesn't define its own `normalizeTarget` function. Signal group IDs are base64-encoded and case-sensitive, so lowercasing corrupts them.

**Original code** (line 2150 in deliver-Ck-fH_m-.js):
```javascript
return ((providerId ? getChannelPlugin(providerId) : void 0)?.messaging?.normalizeTarget?.(raw) ?? (raw.trim().toLowerCase() || void 0)) || void 0;
```

**Problem**: 
- Input: `group:BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=`
- After lowercase: `group:broemhvnclgsz8treukbz6v3bedhdb0exajd+srp6oy=`
- The `A=` becomes `y=` (base64 padding corruption)

## Fix

### Option 1: Direct File Edit (Recommended)

Run these commands as root to patch OpenClaw:

```bash
# Backup the files
cp /usr/local/lib/node_modules/openclaw/dist/deliver-Ck-fH_m-.js \
   /usr/local/lib/node_modules/openclaw/dist/deliver-Ck-fH_m-.js.backup

# Apply the fix using sed
sed -i 's/(raw.trim().toLowerCase() || void 0)/(() => { const t = raw.trim(); return t.toLowerCase().startsWith("group:") ? t : t.toLowerCase(); })() || void 0/g' \
    /usr/local/lib/node_modules/openclaw/dist/deliver-Ck-fH_m-.js
```

### Option 2: Patch Script

Save this as `fix-signal-groups.sh` and run as root:

```bash
#!/bin/bash
set -e

FILES=(
    "/usr/local/lib/node_modules/openclaw/dist/deliver-Ck-fH_m-.js"
    "/usr/local/lib/node_modules/openclaw/dist/deliver-BIDW_mg2.js"
    "/usr/local/lib/node_modules/openclaw/dist/deliver-FdxL6NZx.js"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "Patching $file..."
        # Backup
        cp "$file" "${file}.backup-$(date +%Y%m%d-%H%M%S)"
        
        # Apply fix - preserve case for group: targets
        sed -i 's/(raw.trim().toLowerCase() || void 0)/(() => { const t = raw.trim(); return t.toLowerCase().startsWith("group:") ? t : t.toLowerCase(); })() || void 0/g' "$file"
        
        echo "Patched $file"
    fi
done

echo "Fix applied. Restart OpenClaw to take effect."
```

### Option 3: Manual Node Module Fix

1. Stop OpenClaw:
   ```bash
   openclaw gateway stop
   ```

2. Edit the file:
   ```bash
   nano /usr/local/lib/node_modules/openclaw/dist/deliver-Ck-fH_m-.js
   ```

3. Find line 2150 and replace:
   ```javascript
   // OLD:
   return ((providerId ? getChannelPlugin(providerId) : void 0)?.messaging?.normalizeTarget?.(raw) ?? (raw.trim().toLowerCase() || void 0)) || void 0;
   
   // NEW:
   const trimmed = raw.trim();
   const shouldPreserveCase = trimmed.toLowerCase().startsWith("group:");
   const normalized = shouldPreserveCase ? trimmed : trimmed.toLowerCase();
   return ((providerId ? getChannelPlugin(providerId) : void 0)?.messaging?.normalizeTarget?.(raw) ?? normalized) || void 0;
   ```

4. Start OpenClaw:
   ```bash
   openclaw gateway start
   ```

## Verification

After applying the fix, test with:

```javascript
// Test group message
message({
  action: "send",
  channel: "signal",
  target: "group:BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=",
  message: "Test message after fix"
})
```

## Group Details

**Kublai Klub Group:**
- Name: Kublai Klub
- ID: `BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=`
- Members: 6 (+16624580725, +15165643945, +19195384976, +19194133445, +19193375833, +19196125574)

## References

- Signal daemon HTTP API: http://127.0.0.1:8080/api/v1/rpc
- OpenClaw config: /app/openclaw.json
- This fix file: /data/workspace/souls/main/SIGNAL_GROUP_FIX.md
