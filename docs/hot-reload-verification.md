# Moltbot Hot-Reload Verification Guide

## Overview
This guide explains how to verify that moltbot's skill watcher correctly detects and reloads skills when skill-sync-service writes new skill files to the shared `/data/skills/` directory.

## Architecture Overview

```
┌─────────────────────────┐         ┌──────────────────────────┐
│  kurultai-skills repo   │ ──push─>│  skill-sync-service      │
│  (GitHub)               │         │  (Railway service)        │
└─────────────────────────┘         └──────────────────────────┘
                                             │
                                             │ webhook/poll
                                             ▼
                                    ┌──────────────────────────┐
                                    │  clawdbot-data volume    │
                                    │  (shared /data)          │
                                    │  └── /data/skills/       │
                                    └──────────────────────────┘
                                             │
                                             │ chokidar watch
                                             ▼
                                    ┌──────────────────────────┐
                                    │  moltbot service         │
                                    │  └── SkillWatcher        │
                                    └──────────────────────────┘
```

## Prerequisites
- Railway deployment active
- skill-sync-service running
- moltbot running
- Railway CLI installed

## Component Files

### skill-sync-service
- **Main**: `/skill-sync-service/src/index.js`
- **Webhook Handler**: `/skill-sync-service/src/webhook/handler.js`
- **Deployer**: `/skill-sync-service/src/deployer/deployer.js`
- **Lock Utility**: `/skill-sync-service/src/utils/lock.js`

### moltbot
- **Skill Watcher**: `/moltbot-railway-template/src/skills/watcher.js`
- **Entry Point**: `/moltbot-railway-template/src/index.js`

## Verification Steps

### Step 1: Check Moltbot Logs for Skill Watcher

```bash
# View moltbot logs
railway logs --service moltbot --lines 100

# Look for these messages:
# - "Skills directory: /data/skills"
# - "[SkillWatcher] Watching /data/skills"
# - "Initial skills loaded: ..."
```

**Expected Output:**
```
Skills directory: /data/skills
[SkillWatcher] Watching /data/skills
Initial skills loaded: (none or list of skills)
```

### Step 2: Trigger a Skill Update

Option A: Via GitHub webhook (production flow)
```bash
cd /tmp
git clone git@github.com:Danservfinn/kurultai-skills.git
cd kurultai-skills

# Make a change
echo "# Test change $(date)" >> horde-prompt/SKILL.md
git add horde-prompt/SKILL.md
git commit -m "test: verify hot-reload"
git push origin main
```

Option B: Via manual sync endpoint
```bash
# Get API key from Railway variables
API_KEY=$(railway variable get MANUAL_SYNC_API_KEY --service skill-sync-service)

# Get service URL
SERVICE_URL=$(railway domain --service skill-sync-service | grep -o 'https://[^ ]*')

# Trigger manual sync
curl -X POST \
  -H "x-api-key: $API_KEY" \
  "$SERVICE_URL/api/sync"
```

Option C: Direct file write (for testing)
```bash
# Write a test skill directly to the shared volume
railway exec --service moltbot -- bash -c 'echo "# Test Skill

Test content" > /data/skills/test-skill.md'
```

### Step 3: Verify Hot-Reload Occurred

```bash
# Watch moltbot logs in real-time
railway logs --service moltbot --tail
```

**Expected Log Messages:**
```
[SkillWatcher] Skill changed: horde-prompt
[SkillWatcher] Skill added: new-skill
[SkillWatcher] Skill removed: deleted-skill
```

### Step 4: Verify No Gateway Restart

**Check that the gateway process did NOT restart:**

```bash
# Look for restart messages in logs
railway logs --service moltbot --lines 200 | grep -i restart

# Expected: No restart messages
# If you see "Starting OpenClaw Gateway" again, the gateway restarted
```

**Key Indicator:** The uptime of the gateway process should continue through the skill update.

### Step 5: Verify Skill is Available

```bash
# Check that the skill file exists
railway exec --service moltbot -- ls -la /data/skills/

# Expected: You should see the updated skill file
```

### Step 6: Test Reload Signal File

The deployer creates a `.reload` signal file after deployment:

```bash
# Check for reload signal
railway exec --service moltbot -- cat /data/skills/.reload 2>/dev/null || echo "No reload signal"

# The watcher should detect this and trigger a full reload
```

## Local Testing Without Railway

To test the skill watcher locally:

```bash
# Create test skills directory
mkdir -p /tmp/test-skills

# Create a simple watcher test script
cat > /tmp/test-watcher.js << 'EOF'
const { SkillWatcher } = require('./moltbot-railway-template/src/skills/watcher');

const watcher = new SkillWatcher({
  skillsDir: '/tmp/test-skills',
  logger: console
});

watcher.onSkillChange = ({ action, skillName, filePath }) => {
  console.log(`[${new Date().toISOString()}] ${action}: ${skillName}`);
};

watcher.start().then(() => {
  console.log('Watcher started. Press Ctrl+C to exit.');
});
EOF

# Run the watcher
node /tmp/test-watcher.js

# In another terminal, make changes to /tmp/test-skills/
echo "# Test" > /tmp/test-skills/test.md
```

## Troubleshooting

### Issue: No SkillWatcher messages in logs

**Cause:** Skill watcher not started

**Solution:**
1. Check entrypoint.sh for SKILLS_DIR configuration
2. Verify chokidar is installed in package.json
3. Check for errors during gateway startup

### Issue: Skills not detected

**Cause:** File permissions or directory mount issue

**Solution:**
```bash
# Check directory permissions
railway exec --service moltbot -- ls -la /data/

# Fix if needed (ensure both services use same UID/GID)
railway exec --service moltbot -- chown -R 1001:1001 /data/skills
```

### Issue: Gateway restarts on skill change

**Cause:** Watcher not properly isolated from gateway process

**Solution:** Verify the watcher runs as a separate process or handles errors gracefully without crashing.

### Issue: Stale skills still loaded

**Cause:** Cache not invalidated

**Solution:** The watcher should notify the OpenClaw gateway to reload. This may require additional implementation.

## Integration Test Script

Run the automated test script:

```bash
# From the molt directory
bash scripts/test-skill-sync.sh
```

This will verify:
- All required files exist
- Security fixes are applied
- Volume mounts are configured
- Deployer features are implemented

## Success Criteria

**Hot-Reload Working:**
- [ ] Skill files detected within 5 seconds of write
- [ ] No gateway restart occurs
- [ ] New skills available for agent use
- [ ] Active agents continue running during reload

**Zero Downtime Confirmed:**
- [ ] Agent conversations not interrupted
- [ ] WebSocket connections maintained
- [ ] No 503 errors during deployment

## Health Check Verification

Both services expose health endpoints:

```bash
# skill-sync-service health
curl https://<skill-sync-service-url>/health

# moltbot health (via OpenClaw)
curl https://<moltbot-url>/health
```

## Monitoring the Flow

End-to-end monitoring flow:

1. **GitHub webhook received** → Check skill-sync-service logs
2. **Skill validated** → Check for "Validating skill..." messages
3. **Skill deployed** → Check for "Deployed skill: ..." messages
4. **Reload triggered** → Check for "Reload signal created"
5. **Watcher detects** → Check moltbot logs for skill change messages
