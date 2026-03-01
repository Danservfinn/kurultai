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

## Tool Audit Protocol (Quarterly)

**Inspired by:** Claude Code's "revisit tool assumptions" lesson

**Principle:** As models improve, tools that once helped might now constrain them.

### **Quarterly Questions:**

1. Which protocols feel constraining with 1M context?
2. Are we over-coordinating (can agents handle more autonomy)?
3. Which files could be discovered vs. always-loaded?
4. Is Kublai's routing necessary, or can agents self-coordinate?
5. What assumptions are we carrying from smaller models?

### **Next Audit:** 2026-06-01 (end of Q2)

**Owner:** Kublai (schedule via cron reminder)

---

## Cognee Lessons (2026-03-01)

**Inspired by:** Cognee (graph + vector memory for AI agents)

**Principle:** Memory should capture relationships, persist over time, and learn from usage.

### **Adopted Features:**

1. **Weighted Memory** — Frequently-accessed connections strengthen over time
2. **Entity Extraction** — Auto-extract entities from memory files, create Neo4j nodes
3. **Memory Decay** — Stale edges weaken (0.5x per 14 days)
4. **Auto-Pruning** — Orphaned nodes deleted after 30 days
5. **Unified Search** — Single API across Neo4j, memory files, shared context

### **Implementation:**

| Feature | File | Status |
|---------|------|--------|
| Weighted memory patterns | `docs/NEO4J_PATTERNS.md` | ✅ Added |
| Entity extractor | `src/lib/memory/entity-extractor.ts` | ✅ Created |
| Unified search API | `src/lib/memory/search.ts` | ✅ Created |
| Weekly pruning script | `scripts/prune-memory.sh` | ✅ Created |
| Weekly cron | System crontab | ⏳ Pending setup |

### **Benefits:**

- **Prioritized queries** — Frequently-accessed relationships returned first
- **Auto-optimization** — System learns what matters through usage
- **Stale data cleanup** — Old, unused connections automatically pruned
- **Better routing** — Agent assignments based on historical success
- **Faster search** — High-weight edges prioritized in traversal

### **Next Steps:**

1. Add weight properties to existing Neo4j relationships
2. Increment weight on every access (update all Neo4j queries)
3. Set up weekly decay cron
4. Set up monthly pruning cron
5. Update queries to use weight-based ordering

---
