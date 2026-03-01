# CRITICAL GAP ASSESSMENT - 2026-02-24
## Status: Post-Implementation Review

---

## 🔴 CRITICAL (Will Cause Failures)

### 1. Process Persistence - NOT CONFIGURED
**Issue:** Using `nohup` instead of systemd/PM2
**Impact:** Processes will NOT survive system restart
**Evidence:**
```
❌ No systemd service installed
❌ PM2 not configured (just spawned fresh)
Current: nohup processes (PID 10912, 12654)
```

**Fix Required:**
```bash
sudo mv /tmp/kurultai-heartbeat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kurultai-heartbeat
sudo systemctl start kurultai-heartbeat
```

---

### 2. Neo4j Schema Incompatibility - RUNTIME WARNINGS
**Issue:** Migrations v1-v3 applied but missing expected nodes/properties
**Impact:** Heartbeat tasks failing silently, curation not working
**Evidence:**
```
WARNING: label does not exist: MemoryEntry
WARNING: property does not exist: tier
WARNING: property does not exist: last_heartbeat
ERROR: OgedeiFileMonitor missing 'scan_agent_workspace' method
```

**Affected Tasks:**
- `jochi/memory_curation_rapid` - Cannot find MemoryEntry nodes
- `ogedei/file_consistency` - Cannot scan workspaces (method missing)
- `kublai/status_synthesis` - Cannot read last_heartbeat from agents

**Fix Required:**
- Apply missing migrations or create MemoryEntry schema
- Fix OgedeiFileMonitor class bug
- Add last_heartbeat property to Agent nodes

---

### 3. API Errors - NOT RESPONDING CORRECTLY
**Issue:** Self-Awareness API returning HTML errors
**Impact:** Architecture introspection not accessible
**Evidence:**
```
curl http://localhost:8082/api/architecture/overview
# Returns HTML error page instead of JSON
```

**Status:** Port 8082 is responding but with errors (likely routing issue)

---

## 🟡 HIGH (Will Cause Problems Soon)

### 4. Log Rotation - NOT CONFIGURED
**Issue:** Logs growing indefinitely
**Current Size:**
- heartbeat.log: 19K (growing)
- self-awareness.log: 199B
**Impact:** Will fill disk over time

**Fix Required:**
```bash
# Create logrotate config
sudo tee /etc/logrotate.d/kurultai > /dev/null <<EOF
/Users/kublai/kurultai/kublai-repo/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 kublai kublai
}
EOF
```

---

### 5. No Backup Strategy
**Issue:** No automated Neo4j backups
**Impact:** Data loss if Neo4j fails
**Current:** No backup directory, no backup scripts

**Fix Required:**
```bash
mkdir -p ~/kurultai/backups
# Add cron job for daily backups
0 2 * * * neo4j-admin database dump neo4j --to=/Users/kublai/backups/neo4j-$(date +\%Y\%m\%d).dump
```

---

### 6. Security - API No Authentication
**Issue:** Self-Awareness API accessible without auth
**Impact:** Unauthorized access to architecture/proposals
**Endpoints Exposed:**
- GET /api/architecture/overview
- GET /api/architecture/search
- GET /api/proposals
- POST /api/workflow/process

**Risk Level:** MEDIUM (localhost only, but still vulnerable)

---

### 7. Stale Processes Running
**Issue:** Old processes from Monday still running
**Evidence:**
```
PID 29384: scripts/heartbeat_writer.py (from Mon)
PID 29383: bash wrapper (from Mon)
PID 14330: node src/index.js (from Mon)
PID 14058: node src/index.js (from Mon)
```
**Impact:** Resource waste, potential conflicts

---

## 🟢 MEDIUM (Should Fix Eventually)

### 8. Empty Node Types
These are expected to populate over time, but currently empty:
- ❌ Task: 0 (need task creation workflow)
- ❌ LearnedCapability: 0 (need capability learning)
- ❌ ArchitectureProposal: 0 (need proactive reflection)
- ❌ Notification: 0 (notification system not used yet)

---

### 9. Directories Not Cleaned Up
- ⚠️ steppe-visualization/ - Still exists (you removed from architecture but files remain)
- ⚠️ skill-sync-service/ - Running but not wired in

---

### 10. Hardcoded Credentials
**Issue:** Neo4j password in scripts
**Location:** Multiple Python/Node scripts
**Risk:** Password exposure in shell history

---

## 📊 SUMMARY

| Severity | Count | Categories |
|----------|-------|------------|
| 🔴 Critical | 3 | Process persistence, Schema bugs, API errors |
| 🟡 High | 4 | Logs, Backups, Security, Stale processes |
| 🟢 Medium | 3 | Empty nodes, Cleanup, Credentials |

**Verdict:** System is running but NOT production-ready. Will fail on reboot.

**Immediate Actions Required:**
1. Install systemd service (CRITICAL)
2. Fix Neo4j schema / OgedeiFileMonitor bug (CRITICAL)
3. Fix API routing error (CRITICAL)
4. Kill stale processes (HIGH)
5. Set up log rotation (HIGH)
