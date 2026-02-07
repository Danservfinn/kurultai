# Skill Sync Service

Automated synchronization of skills from GitHub `kurultai-skills` repository to Railway `kublai.kurult.ai` deployment.

## Architecture

**Hybrid Approach:**
- **Webhook**: Real-time deployment on GitHub push (~5-10s latency)
- **Polling**: Fallback every 5 minutes for reliability

## Quick Start

### Local Development

```bash
# Install dependencies
npm install

# Copy environment file
cp .env.example .env
# Edit .env with your values

# Start in development
npm run dev
```

### Railway Deployment

1. Create new service in Railway project
2. Set environment variables (see .env.example)
3. Deploy

## Environment Variables

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `PORT` | No | HTTP port | 3000 |
| `SKILLS_DIR` | No | Target directory for skills | /data/skills |
| `BACKUP_DIR` | No | Backup location | /data/backups/skills |
| `GITHUB_WEBHOOK_SECRET` | Yes | GitHub HMAC secret | - |
| `GITHUB_TOKEN` | Yes | GitHub PAT (repo scope) | - |
| `GITHUB_OWNER` | No | Repository owner | Danservfinn |
| `GITHUB_REPO` | No | Repository name | kurultai-skills |
| `POLLING_INTERVAL_MIN` | No | Polling interval | 5 |
| `NEO4J_URI` | Yes | Neo4j connection | - |
| `NEO4J_USER` | Yes | Neo4j username | neo4j |
| `NEO4J_PASSWORD` | Yes | Neo4j password | - |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Service health status |
| GET | /skills | List deployed skills |
| POST | /webhook/github | GitHub webhook endpoint |
| POST | /api/sync | Manual sync trigger |

## GitHub Webhook Setup

1. Go to repository Settings > Webhooks
2. Add webhook: `https://kublai.kurult.ai/webhook/github`
3. Content type: `application/json`
4. Secret: Match `GITHUB_WEBHOOK_SECRET`
5. Events: Push events

## Security

- Webhook signatures verified with HMAC-SHA256
- Secret scanning for API keys in skill files
- Atomic deployments with rollback
- Deployment lock prevents concurrent updates

## Monitoring

Health check response includes:
- Poller status and last check time
- Webhook configuration status
- Deployed skills count
- Recent deployments

## Troubleshooting

### Skills not updating

1. Check health endpoint: `curl /health`
2. Verify GitHub webhook is configured
3. Check logs for validation errors
4. Verify `GITHUB_TOKEN` has repo access

### Webhook failing

1. Verify signature matches `GITHUB_WEBHOOK_SECRET`
2. Check Railway logs for delivery
3. Test with `POST /api/sync` (polling fallback)

### Validation errors

Check for:
- Missing YAML frontmatter
- Missing required fields (name, version, description)
- Detected secrets in content
