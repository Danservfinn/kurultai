# Gap Analysis: Implementation Plan vs ARCHITECTURE.md
**Analysis Date:** 2026-02-24
**Status:** Post-Plan Review

---

## Executive Summary

The **Implementation Plan** addresses **CRITICAL survival issues** (data loss prevention, core functionality). After execution, the system will be **operational but incomplete** - several architectural features will remain as documented debt.

**Analogy:** The plan builds a working house with working electricity and plumbing, but some rooms are unfurnished.

---

## ✅ What the Plan FULLY Addresses

| Component | Architecture Location | Plan Coverage | Status After Plan |
|-----------|----------------------|---------------|-------------------|
| 6-Agent System | Agent Layer | Complete | ✅ Fully operational |
| Neo4j Schema | Memory Layer | Complete | ✅ Migrated v3 |
| Unified Heartbeat | Application Layer | Complete | ✅ Running via systemd |
| Self-Awareness System | Kublai Self-Awareness section | Complete | ✅ src/kublai/ installed |
| Basic CBAC Seeding | Security Architecture | Partial | ⚠️ Capabilities exist, not enforced |
| Signal Integration | User Interface Layer | Already working | ✅ +15165643945 active |
| Model Configuration | Runtime | Complete | ✅ 3.1-pro-preview configured |
| Process Persistence | Deployment | Complete | ✅ systemd + PM2 |

---

## 🟡 REMAINING GAPS (Functional Debt)

### 1. Notion Integration - **MISSING API TOKEN**
**Architecture:** Hourly bidirectional Notion↔Neo4j sync (60 min task)
**Plan Status:** ❌ NOT CONFIGURED
**Gap:** `NOTION_API_TOKEN` and `NOTION_DATABASE_ID` not in .env
**Impact:** notion_sync task will fail silently
**Fix:** Add to Phase 2.2 if you have Notion API access

```bash
# Add to .env
NOTION_API_TOKEN=secret_xxx
NOTION_DATABASE_ID=xxx
```

---

### 2. Agent Authentication (HMAC) - **KEYS NOT WIRED**
**Architecture:** 9-Layer Security → Layer 9 (HMAC-SHA256 signing)
**Plan Status:** ⚠️ PARTIAL
**Gap:** 
- Keys generated (Phase 2.1) but not stored in Neo4j
- Agent-to-agent messaging not using signatures
- No 90-day rotation implemented
**Impact:** Agent messages could theoretically be impersonated
**Fix:** Requires additional implementation in agent messaging layer

---

### 3. Test Runner Orchestrator - **NOT SCHEDULED**
**Architecture:** Jochi's smoke_tests (15 min), full_tests (60 min), nightly tests
**Plan Status:** ⚠️ PARTIAL
**Gap:** 
- Test runner exists at `tools/kurultai/test_runner_orchestrator.py`
- Not integrated with Railway cron schedule
- No actual test execution configured
**Impact:** Tests documented but not automated
**Fix:** Add to railway.yml or systemd timers

---

### 4. Ticket Manager - **NOT INITIALIZED**
**Architecture:** Automatic ticket creation for critical test failures
**Plan Status:** ❌ NOT CONFIGURED
**Gap:** `tools/kurultai/ticket_manager.py` exists but no ticket backend configured
**Impact:** Critical failures won't create trackable tickets
**Fix:** Choose ticket backend (GitHub Issues, Linear, etc.) and configure

---

### 5. Skill Sync Service - **PRESENT BUT UNWIRED**
**Architecture:** Not explicitly documented but exists in codebase
**Plan Status:** ❌ NOT ADDRESSED
**Gap:** `skill-sync-service/` has its own Node.js app - not started
**Impact:** Skill deployment automation not running
**Fix:** Add to PM2 ecosystem or evaluate if needed

---

## 🔴 DELIBERATE EXCLUSIONS (Architecture Sections Removed)

You asked to remove these from ARCHITECTURE.md - they still exist in codebase:

### 6. Authentication Layer (Caddy + Authentik)
**Status:** ❌ REMOVED FROM ARCHITECTURE, FILES STILL EXIST
**Directories:** `authentik-proxy/`, `authentik-server/`, `authentik-worker/`
**Recommendation:** Clean up these directories to reduce confusion

```bash
# Remove if not using
rm -rf ~/kurultai/kublai-repo/authentik-*
```

---

### 7. Steppe Visualization Dashboard
**Status:** ❌ REMOVED FROM ARCHITECTURE, FILES STILL EXIST
**Directory:** `steppe-visualization/` (Next.js app)
**Recommendation:** Either:
- Remove entirely (`rm -rf steppe-visualization/`)
- OR keep and start if you want the 3D mission control UI

```bash
# If keeping:
cd steppe-visualization && npm install && npm run dev
```

---

## 📊 Gap Severity Matrix

| Gap | Severity | User Action Required | Effort |
|-----|----------|---------------------|--------|
| Notion Integration | Low | Add API token if needed | 5 min |
| Agent Auth (HMAC) | Medium | Decide if needed | 2-4 hours |
| Test Runner Schedule | Medium | Add to systemd/PM2 | 30 min |
| Ticket Manager | Low | Choose ticket backend | 1-2 hours |
| Skill Sync Service | Low | Evaluate if needed | 30 min |
| Authentik Cleanup | Low | Delete directories | 5 min |
| Steppe Viz Cleanup | Low | Delete or start | 5 min |

---

## 🎯 Recommended Extended Plan

### Phase 6: Cleanup (30 minutes)
```bash
cd ~/kurultai/kublai-repo

# Remove unused components
rm -rf authentik-proxy/ authentik-server/ authentik-worker/

# Decide on Steppe Visualization
# Option A: Remove
rm -rf steppe-visualization/

# Option B: Start it
cd steppe-visualization && npm install && npm run build
pm2 start --name steppe-viz "npm start"
```

### Phase 7: Optional Integrations (If Needed)

**If using Notion:**
```bash
# Add to .env
echo "NOTION_API_TOKEN=secret_xxx" >> .env
echo "NOTION_DATABASE_ID=xxx" >> .env
```

**If using Ticket Manager:**
```bash
# Configure ticket backend in tools/kurultai/ticket_manager.py
# Currently uses local JSON - could integrate with GitHub API
```

**If running automated tests:**
```bash
# Add to systemd or PM2
python tools/kurultai/test_runner_orchestrator.py --phase smoke --dry-run
```

---

## 📋 Final Checklist

After completing the **Implementation Plan** + **Extended Plan**:

- [x] 6 agents operational
- [x] Neo4j populated with data
- [x] Heartbeat running
- [x] Self-awareness system active
- [ ] Notion sync (only if you add token)
- [ ] Agent HMAC auth (only if you implement)
- [ ] Automated tests (only if you schedule)
- [ ] Ticket creation (only if you configure backend)
- [x] Authentik removed (cleanup)
- [x] Steppe Visualization handled (cleanup or started)

---

## Conclusion

**The Implementation Plan closes all CRITICAL gaps.** The remaining gaps are:
1. **Optional integrations** (Notion, tickets) - only needed if you use those services
2. **Security hardening** (HMAC auth) - adds security but system works without it
3. **Cleanup** (Authentik, Steppe) - housekeeping from removed architecture sections

**Bottom line:** After Phase 1-3, you'll have a functional Kurultai system matching the core architecture. Phases 6-7 are polish and optional features.
