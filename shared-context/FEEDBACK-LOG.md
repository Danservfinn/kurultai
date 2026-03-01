# FEEDBACK-LOG.md - Cross-Agent Corrections

## Communication Rules (Universal)
- **NO EMOJIS** in human-facing output (professional tone required)
- Use exact file paths, never assume directory structure
- Confirm destructive actions before executing (trash > rm)
- When uncertain, ask rather than guess

## Technical Lessons (2026-02-28)
- Railway CLI requires --service flag for multi-service projects
- Always check if services exist before attempting restart/kill
- Use `curl -s` for silent HTTP status checks
- DNS changes require Cloudflare dashboard access
- Environment variables must be copied when recreating services

## Agent Coordination
- Always strip PII before cross-agent delegation
- Use Neo4j for operational memory (no human private data)
- File memory for PII/sensitive data only
- Single-agent reflection per hour to prevent resource exhaustion

## Security Reminders
- NEVER expose OSA signals to humans unless explicitly asked
- NEVER delete project folders without explicit confirmation
- NEVER make irreversible changes without confirming first
- NEVER assume a port is free - always verify

## Lessons from Parse Deployment
- Bun-based Railway services don't support Next.js apps properly
- Always verify service type (Nixpacks vs Bun) before deployment
- Environment variables are NOT automatically inherited between services
- Healthcheck failures usually indicate missing env vars or DB connection issues

## OpenClaw Best Practices (2026-03-01)
- **ALWAYS check official docs** at https://docs.openclaw.ai before system modifications
- Use `web_fetch` to get current documentation (not cached knowledge)
- Start with https://docs.openclaw.ai/llms.txt for doc index
- Use native OpenClaw cron (cron tool) instead of system crontab when possible
- Verify configuration schemas in docs before making changes
- Docs are the source of truth - not memory, not assumptions
