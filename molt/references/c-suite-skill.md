# C-Suite Skill Reference

Reference for the unified C-Suite executive team skill for Moltbot.

---

## Overview

The C-Suite skill consolidates four C-level executive roles into a single unified skill that operates as an autonomous executive team for Kurultai LLC and Parse SaaS.

**Location**: `~/.claude/skills/c-suite/` (local) or `/data/workspace/c-suite/` (Railway)
**Archive**: `~/.claude/skills/c-suite.zip`

---

## Commands

| Command | Agent | Model | Description |
|---------|-------|-------|-------------|
| `/coo` | COO | Sonnet | Business operations, compliance, Notion tracking |
| `/cfo` | CFO | Sonnet | Financial reporting, MRR/ARR, Stripe/Mercury |
| `/cto` | CTO | **Opus** | Technical operations, deployments, database, queues |
| `/ceo` | CEO | Sonnet | Business intelligence, revenue analytics, growth |
| `/csuite` | All | Parallel | Full executive team report from all four roles |

---

## Architecture

```
c-suite/
├── SKILL.md                      # Main skill definition
├── moltbot-config.json           # Moltbot integration config
├── agents/
│   ├── coo.md                    # COO agent definition
│   ├── cfo.md                    # CFO agent definition
│   ├── cto.md                    # CTO agent (Opus, orchestrates subagents)
│   ├── ceo.md                    # CEO/BI agent definition
│   └── subagents/
│       ├── backend-ops.md        # Backend Operations Engineer
│       ├── database-eng.md       # Database Engineer
│       └── queue-eng.md          # Queue Engineer
├── scripts/
│   ├── shared/                   # Reusable API clients
│   │   ├── stripe-client.ts
│   │   ├── mercury-client.ts
│   │   └── prisma-client.ts
│   ├── finance/                  # CFO financial scripts
│   │   ├── stripe-balance.ts
│   │   ├── mercury-balance.ts
│   │   ├── revenue-metrics.ts
│   │   ├── payout-tracking.ts
│   │   └── financial-export.ts
│   ├── operations/               # COO operations scripts
│   │   ├── setup-stripe-products.ts
│   │   ├── create-webhook.js
│   │   └── link-mercury-account.ts
│   └── health/
│       └── full-health-check.ts
├── runbooks/
│   ├── rate-limit-recovery.md
│   ├── queue-backup.md
│   ├── database-issues.md
│   ├── failed-analysis-jobs.md
│   ├── payment-failures.md
│   └── churn-investigation.md
├── references/
│   ├── business-context.md
│   ├── payment-integration.md
│   ├── pricing-config.md
│   └── financial-schema.md
└── notion/
    ├── database-ids.json
    └── setup_notion.py
```

---

## Role Responsibilities

### COO (Chief Operating Officer)
- Business operations and administration
- Compliance tracking (Montana LLC, registered agent, tax filing)
- Document management via Notion
- Vendor and contract management
- Payment infrastructure setup

**Tools**: Notion MCP (write access)

### CFO (Chief Financial Officer)
- Revenue monitoring (MRR, ARR, churn)
- Cash position tracking (Stripe + Mercury)
- Financial reporting and export
- Payment failure alerts
- Unit economics analysis

**Tools**: PostgreSQL MCP (read-only), Stripe API, Mercury API

### CTO (Chief Technology Officer)
- Technical operations and incident response
- Deployment management (Railway)
- Database administration
- Queue management (BullMQ/Redis)
- Orchestrates subagents for specialized tasks

**Tools**: Railway MCP, PostgreSQL MCP (full), BullMQ MCP, Bash

### CEO (Chief Executive Officer / Business Intelligence)
- Business state classification (GROWING/STABLE/DECLINING/CRITICAL)
- Growth metrics and conversion analysis
- Strategic recommendations
- Executive dashboard generation

**Tools**: PostgreSQL MCP (read-only)

---

## MCP Server Access

| MCP Server | CTO | CFO | CEO | COO |
|------------|-----|-----|-----|-----|
| Railway | ✓ | - | - | - |
| PostgreSQL | Full | Read | Read | - |
| BullMQ | ✓ | - | - | - |
| Notion | - | - | - | ✓ |

---

## Environment Variables

The c-suite skill requires these environment variables:

```bash
# Payment Integration
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
MERCURY_API_KEY=...

# Database & Queue
DATABASE_URL=postgresql://...
REDIS_URL=redis://...

# Notion Integration (COO)
NOTION_API_KEY=secret_...
NOTION_COMPLIANCE_DB=...
NOTION_DECISIONS_DB=...
NOTION_MEETINGS_DB=...
NOTION_TASKS_DB=...
NOTION_DOCUMENTS_DB=...
NOTION_VENDORS_DB=...
```

---

## Moltbot Configuration

Add to Railway's moltbot.json:

```json
{
  "skills": {
    "entries": {
      "c-suite": {
        "enabled": true,
        "path": "/data/workspace/c-suite",
        "commands": {
          "coo": { "agent": "coo", "description": "Business ops & compliance" },
          "cfo": { "agent": "cfo", "description": "Financial reporting" },
          "cto": { "agent": "cto", "model": "opus", "description": "Technical ops" },
          "ceo": { "agent": "ceo", "description": "Business intelligence" },
          "csuite": { "agents": ["cto", "cfo", "ceo", "coo"], "parallel": true }
        }
      }
    }
  }
}
```

---

## Deployment Steps

1. **Copy skill to Railway volume**:
   ```bash
   # Upload c-suite.zip to Railway
   unzip c-suite.zip -d /data/workspace/
   ```

2. **Set environment variables** in Railway dashboard

3. **Update moltbot.json** with c-suite skill entry

4. **Configure channel allowlists** for executive access

5. **Verify each command**:
   - `/coo` - Returns compliance status
   - `/cfo` - Returns MRR and cash position
   - `/cto health` - Returns system health
   - `/ceo` - Returns business state

---

## Cross-References

- [Configuration Reference](configuration.md) - Moltbot config schema
- [Environment Variables](environment-variables.md) - Variable reference
- [Channel Setup](channel-setup.md) - Messaging integration
- [Security Checklist](security-checklist.md) - Security hardening
