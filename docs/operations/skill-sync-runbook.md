# Skill Sync Service Operations Runbook

## Overview
Automatic skill synchronization from kurultai-skills GitHub repository to kublai gateway with zero downtime.

## Architecture

```
GitHub Push --> Webhook --> skill-sync-service --> /data/skills/ --> chokidar --> Moltbot hot-reload
              |
              Polling (every 5 min - fallback)
```

### Services

| Service | Type | Purpose |
|---------|------|---------|
| skill-sync-service | Railway Worker | Receives webhooks, writes skills |
| moltbot | Railway Service | OpenClaw gateway with file watcher |

### Shared Volume

- **Name:** `clawdbot-data`
- **Mount Path:** `/data` (both services)
- **Skills Directory:** `/data/skills/`
- **Backups:** `/data/backups/skills/<deployment-id>/`

## Environment Variables

### skill-sync-service

| Variable | Description | Example |
|----------|-------------|---------|
| SKILLS_DIR | Target directory | /data/skills |
| BACKUP_DIR | Backup location | /data/backups/skills |
| GITHUB_WEBHOOK_SECRET | HMAC verification | 64-char hex |
| GITHUB_TOKEN | GitHub API token | ghp_... |
| GITHUB_OWNER | Repository owner | Danservfinn |
| GITHUB_REPO | Repository name | kurultai-skills |
| POLLING_INTERVAL_MIN | Fallback polling | 5 |
| NEO4J_URI | Audit logging | bolt://neo4j.railway.internal:7687 |
| NEO4J_USER | Neo4j username | neo4j |
| NEO4J_PASSWORD | Neo4j password | from Railway |
| MANUAL_SYNC_API_KEY | Manual sync auth | generate-secret |

### moltbot

| Variable | Description | Example |
|----------|-------------|---------|
| SKILLS_DIR | Skills directory | /data/skills |
| OPENCLAW_GATEWAY_PORT | Gateway port | 18789 |

## Health Checks

### skill-sync-service

```bash
# Check health endpoint
curl https://<skill-sync-service-url>.railway.app/health

# Expected response:
{
  "status": "healthy",
  "timestamp": "2026-02-07T12:00:00Z",
  "services": {
    "poller": { "status": "running", "lastCheck": "abc123" },
    "webhook": { "status": "enabled", "configured": true },
    "audit": { "status": "connected" }
  },
  "skills": {
    "count": 5,
    "lastUpdated": ["golden-horde", "horde-implement", ...]
  },
  "recentDeployments": [...]
}
```

### moltbot

```bash
# Check gateway health
curl https://kublai.kurult.ai/health

# Or via Railway internal
railway exec --service moltbot -- curl -f http://localhost:18789/health
```

## Troubleshooting

### Skills Not Updating

**Symptoms:** Changes pushed to GitHub not appearing in gateway

**Diagnosis:**
```bash
# 1. Check skill-sync-service logs
railway logs --service skill-sync-service --lines 100

# Look for:
# - "Webhook received: push"
# - "Processing N changed skill files"
# - Error messages

# 2. Check webhook delivery in GitHub
# Go to: https://github.com/Danservfinn/kurultai-skills/settings/hooks
# Look for recent deliveries with status codes

# 3. Verify GITHUB_WEBHOOK_SECRET matches
railway variable get GITHUB_WEBHOOK_SECRET --service skill-sync-service
# Compare with GitHub webhook secret

# 4. Test manual sync
API_KEY=$(railway variable get MANUAL_SYNC_API_KEY --service skill-sync-service)
curl -X POST -H "x-api-key: $API_KEY" \
  https://<skill-sync-service-url>/api/sync
```

**Solutions:**
- Webhook not delivering: Check GitHub webhook status, regenerate secret
- Signature verification failing: Update secret in both GitHub and Railway
- Poller not working: Check GITHUB_TOKEN is valid and has repo access
- Validation failing: Check skill YAML frontmatter, ensure required fields present

### Moltbot Not Reloading

**Symptoms:** Skills written to `/data/skills/` but not loaded by gateway

**Diagnosis:**
```bash
# 1. Check moltbot logs for SkillWatcher messages
railway logs --service moltbot --lines 100 | grep -i skill

# Should see:
# - "[SkillWatcher] Watching /data/skills"
# - "[SkillWatcher] Skill changed: <name>"

# 2. Verify shared volume is mounted on both services
railway exec --service skill-sync-service -- ls -la /data/skills/
railway exec --service moltbot -- ls -la /data/skills/

# Both should show the same files

# 3. Check file permissions
railway exec --service moltbot -- ls -la /data/skills/
# Files should be readable (r--r--r--)
```

**Solutions:**
- Volume not mounted: Check railway.yml volume configuration
- Permission denied: Ensure both services run with compatible UID/GID
- Watcher not started: Check entrypoint.sh for SKILLS_DIR setup
- chokidar not installed: Verify package.json includes chokidar

### Validation Failures

**Symptoms:** Skills rejected during deployment

**Common Issues:**
- Missing YAML frontmatter
- Invalid YAML syntax
- Missing required fields (name, version, description)
- Secret patterns detected (API keys, passwords)

**Diagnosis:**
```bash
# Check skill-sync-service logs for validation errors
railway logs --service skill-sync-service --lines 100 | grep -i error
```

**Solution:** Fix the skill file in kurultai-skills repository and push again.

### Gateway Restarting

**Symptoms:** Gateway restarts when skills change (should hot-reload)

**Diagnosis:**
```bash
# Check for restart messages
railway logs --service moltbot --lines 200 | grep -i restart

# Look for "Starting OpenClaw Gateway" appearing multiple times
```

**Solution:** Verify file watcher is running as separate process, not causing gateway crashes on file events.

## Rollback Procedure

If a bad skill is deployed:

### Option 1: Revert Commit in GitHub

```bash
cd kurultai-skills
git revert HEAD
git push origin main
```

Webhook triggers automatic redeploy of previous version.

### Option 2: Manual Restore from Backup

```bash
# List available backups
railway exec --service skill-sync-service -- ls -la /data/backups/skills/

# Restore from backup
railway exec --service skill-sync-service -- bash -c \
  'cp -r /data/backups/skills/<deployment-id>/* /data/skills/'

# Trigger reload
railway exec --service skill-sync-service -- touch /data/skills/.reload
```

## Maintenance Tasks

### Daily
- Monitor Railway logs for errors
- Check deployment success rate

### Weekly
- Review recent deployments in Neo4j audit log
- Verify webhook delivery rate

### Monthly
- Rotate GITHUB_WEBHOOK_SECRET
- Review and update skill validation rules
- Clean up old backups (keep last 30 days)

## Incident Response

### Severity Levels

| Level | Description | Response Time |
|-------|-------------|---------------|
| P1 | Gateway completely down | 15 minutes |
| P2 | Skills not deploying | 1 hour |
| P3 | Individual skill failure | 4 hours |
| P4 | Documentation update | 1 week |

### Escalation

1. Check runbook troubleshooting
2. Check GitHub issues for known problems
3. Escalate to on-call engineer

## Metrics

### Key Performance Indicators

| Metric | Target | Current |
|--------|--------|---------|
| Webhook success rate | >99% | - |
| Deployment latency | <10s | - |
| Hot-reload success rate | 100% | - |
| Gateway uptime | >99.9% | - |

### Monitoring

```bash
# Get deployment stats from health endpoint
curl https://<skill-sync-service-url>/health | jq .

# Check recent deployments
railway logs --service skill-sync-service --lines 1000 | grep "Successfully deployed"
```

## Related Documentation

- [GitHub Webhook Setup](../github-webhook-setup.md)
- [Hot-Reload Verification](../hot-reload-verification.md)
- [Architecture](../../ARCHITECTURE.md)
