# Kurultai Monthly Railway Cost Projection

**Date:** 2026-02-10  
**Project:** Kurultai AI Infrastructure  
**Environment:** Production (Railway)

---

## Services Inventory

### Core Infrastructure
| Service | Purpose | Resource Needs |
|---------|---------|----------------|
| **Main App** | Kurultai core, heartbeat, task scheduler | 1 vCPU, 1GB RAM |
| **Neo4j Database** | Graph database for tasks, agents, memory | 1 vCPU, 2GB RAM, 10GB storage |
| **OpenClaw Gateway** | Agent communication, messaging | 0.5 vCPU, 512MB RAM |
| **Signal Daemon** | Signal messaging integration | 0.5 vCPU, 512MB RAM |
| **Authentik** | Authentication/SSO (optional) | 1 vCPU, 1GB RAM |

### Scheduled Cron Jobs (9 schedules)
- `ogedei-weekly-reflection` - Weekly
- `kurultai-heartbeat` - Continuous
- `jochi-smoke-tests` - Every 15 min
- `jochi-hourly-tests` - Hourly
- `jochi-nightly-tests` - Nightly
- `kublai-weekly-reflection` - Weekly
- `spawn-mongke` - Periodic
- `spawn-chagatai` - Periodic
- `spawn-temujin` - Periodic

---

## Cost Breakdown

### Option 1: Minimal (Development)
| Component | Tier | Cost/Month |
|-----------|------|------------|
| Main App | Starter ($5) | $5 |
| Neo4j | Hobby (shared) | $0* |
| OpenClaw Gateway | Starter ($5) | $5 |
| Signal Daemon | Local (no cost) | $0 |
| Cron Jobs | Included in main | $0 |
| **Subtotal** | | **$10** |
| Network Egress (~5GB) | $0.10/GB | $0.50 |
| **TOTAL** | | **~$10.50** |

*Neo4j Aura has free tier up to 200k nodes/relationships

### Option 2: Production (Recommended)
| Component | Tier | Cost/Month |
|-----------|------|------------|
| Main App | Starter Pro ($10) | $10 |
| Neo4j | Production (2GB) | $15 |
| OpenClaw Gateway | Starter ($5) | $5 |
| Signal Daemon | Local | $0 |
| Authentik | Starter ($5) | $5 |
| **Subtotal** | | **$35** |
| Network Egress (~20GB) | $0.10/GB | $2 |
| Backups (Neo4j) | Included | $0 |
| **TOTAL** | | **~$37** |

### Option 3: High Availability (Scale)
| Component | Tier | Cost/Month |
|-----------|------|------------|
| Main App | Pro (2x instances) | $40 |
| Neo4j | HA Cluster | $50 |
| OpenClaw Gateway | Pro ($20) | $20 |
| Signal Daemon | Starter ($5) | $5 |
| Authentik | Pro ($20) | $20 |
| Redis Cache | Starter ($5) | $5 |
| **Subtotal** | | **$140** |
| Network Egress (~100GB) | $0.10/GB | $10 |
| **TOTAL** | | **~$150** |

---

## Cost Drivers

### 1. Compute ($10-140)
- **Starter**: $5/service (1GB RAM, shared CPU)
- **Pro**: $20/service (2GB RAM, dedicated CPU)
- **Scheduled jobs**: Included in main service cost

### 2. Database ($0-50)
- **Neo4j Aura Free**: 200k nodes (sufficient for MVP)
- **Neo4j Aura Pro**: $15/month (2GB RAM, 10GB storage)
- **Neo4j Aura Enterprise**: $50/month (HA, backup, monitoring)

### 3. Network Egress ($0.50-10)
- Web traffic, API calls, Signal messages
- Current: ~5-20 GB/month
- At scale: ~100 GB/month

### 4. Additional Services
- **Authentik**: $5-20 (authentication)
- **Redis**: $5 (caching, if needed)
- **Monitoring**: $5-10 (Datadog integration)

---

## Projections by Phase

| Phase | Services | Est. Monthly Cost |
|-------|----------|-------------------|
| **MVP** (Current) | Main + Neo4j (free) + Gateway | **$10-15** |
| **Production** | Main + Neo4j (pro) + Gateway + Authentik | **$35-40** |
| **Scale** | HA + Clustered Neo4j + Caching + Monitoring | **$100-150** |
| **Enterprise** | Multi-region + Dedicated infra | **$300-500** |

---

## Optimization Strategies

### Immediate (No Cost)
1. **Use Neo4j Aura Free tier** - 200k nodes limit
2. **Run Signal daemon locally** - Not on Railway
3. **Compress task scheduler** - Run in main app process
4. **Bundle cron jobs** - Fewer scheduled triggers

### Short-term ($5-10 savings)
1. **Monitor egress** - Set up alerts at 10GB
2. **Optimize DB queries** - Reduce compute cycles
3. **Cache frequently accessed data** - Redis free tier
4. **Use Railway's volume pricing** - Commit to annual

### Long-term (Scale prep)
1. **Separate read replicas** - Neo4j read scaling
2. **CDN for static assets** - Reduce egress
3. **Reserved instances** - 30% discount for annual commitment
4. **Custom domain** - Avoid Railway domain limits

---

## Current Status Checklist

- [x] Main app deployed to Railway
- [x] Neo4j database connected (external/Railway)
- [x] OpenClaw Gateway running
- [x] Scheduled jobs configured
- [ ] Cost monitoring alerts set up
- [ ] Monthly budget cap configured
- [ ] Authentik deployed (optional)

---

## Recommendations

### Current State (MVP)
**Estimated: $10-15/month**
- Start with Railway Starter tier
- Use Neo4j Aura free tier
- Monitor usage for 30 days

### When to Scale
- **>$20/month**: Move to Railway Pro for better performance
- **>$50/month**: Add monitoring and alerting
- **>$100/month**: Implement caching and optimization
- **>$200/month**: Consider dedicated VPS alternative

### Budget Alert Thresholds
- **Warning**: $25/month (75% of Starter budget)
- **Critical**: $40/month (production tier threshold)
- **Emergency**: $100/month (requires optimization review)

---

## Summary

| Scenario | Monthly Cost | Annual Cost |
|----------|-------------|-------------|
| **MVP (Current)** | ~$12 | ~$144 |
| **Production** | ~$37 | ~$444 |
| **Scale** | ~$150 | ~$1,800 |

**Next Steps:**
1. Monitor actual usage for 30 days
2. Set up cost alerts at $20/month
3. Optimize based on real traffic patterns
4. Consider annual commitment for 30% savings

---

*Per ignotam portam. Testa frangitur.*
