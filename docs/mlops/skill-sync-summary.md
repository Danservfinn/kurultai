# Skill Sync: Executive Summary

## Problem

Skills in the `kurultai-skills` GitHub repository must be manually synchronized to the Railway-deployed `kublai.kurult.ai` system. This creates a gap between skill development and deployment.

## Recommended Solution: Hybrid Webhook + Polling

### Architecture Choice

**Hybrid Approach** combining:
1. **GitHub Webhook** for real-time deployment (~5-10 second latency)
2. **Polling fallback** for reliability (catches missed events within 5 minutes)

### Why This Approach?

| Consideration | Rationale |
|---------------|-----------|
| **Speed** | Webhook provides near-instant deployment |
| **Reliability** | Polling catches anything webhook misses |
| **Complexity** | Manageable - single new Railway service |
| **Cost** | ~$5-10/month (Railway worker) |
| **Observability** | Full audit trail in Neo4j |

## Implementation Overview

```
GitHub Push Event
       |
       +-- Webhook --> skill-sync-service --> Deploy
       |
       +-- 5 min later --> Poller checks --> Skip if already deployed
```

## Key Components

### 1. skill-sync-service (New Railway Service)

| Component | Purpose |
|-----------|---------|
| Webhook Handler | Receives GitHub push events |
| Skill Validator | YAML parsing, security scan |
| Skill Deployer | Atomic writes + rollback |
| Poller | Fallback sync every 5 minutes |
| Audit Logger | Neo4j deployment tracking |

### 2. moltbot Integration

| Component | Purpose |
|-----------|---------|
| SkillReloader | Hot-reload on file change (chokidar) |
| Skill Registry | In-memory skill cache |

## Deployment Flow

1. Developer pushes skill update to GitHub
2. Webhook triggers skill-sync-service
3. Service validates, backs up, deploys
4. Moltbot hot-reloads new skill
5. Health check confirms success
6. Audit logged to Neo4j

## Safety Features

| Feature | Implementation |
|---------|----------------|
| **Rollback** | Automatic on health check failure |
| **Validation** | YAML schema + secret scanning |
| **Atomic writes** | Temp file + rename pattern |
| **Audit trail** | Neo4j SkillDeployment nodes |
| **Locking** | Prevents concurrent deployments |

## Timeline Estimate

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Phase 1 | 1-2 days | Base infrastructure (validator, deployer) |
| Phase 2 | 1 day | Polling implementation |
| Phase 3 | 1-2 days | Webhook implementation |
| Phase 4 | 1 day | Integration & testing |
| **Total** | **4-6 days** | Production-ready skill sync |

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Webhook not delivered | Polling fallback |
| Validation failure | Reject + alert |
| Health check fail | Auto-rollback |
| GitHub rate limit | Conditional requests |
| Concurrent deploys | Deployment lock |

## Next Actions

1. [ ] Review architecture with team
2. [ ] Create implementation GitHub issue
3. [ ] Set up `skill-sync-service` in Railway project
4. [ ] Implement Phase 1 (Base Infrastructure)
5. [ ] Deploy to staging for testing

---

**Document**: `/Users/kurultai/molt/docs/mlops/skill-sync-architecture-analysis.md`
**Status**: Ready for Implementation
