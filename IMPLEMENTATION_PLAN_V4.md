# Kurultai v4.0 Implementation Plan
**Generated:** 2026-02-25 00:10 EST
**Objective:** Modernize Kurultai architecture per modernization roadmap
**Timeline:** Execute autonomously overnight (12+ hours available)

---

## Critical Path Analysis

### Must Complete Tonight (Foundation)
1. ✅ Phase 1: Stabilization & Observability
   - Centralize scheduling (remove railway.yml cron jobs)
   - Stop Neo4j bloat (structured logging)
   - Database cleanup

2. ⚠️ Phase 2: Async Execution Engine (MVP)
   - Redis provisioning
   - Basic RQ queue implementation
   - Worker process setup

### Can Start / Partial Completion
3. 🔄 Phase 3: FastAPI Migration (Begin)
   - Express→FastAPI port (core endpoints)
   - API structure setup

4. 📋 Phase 4: Documentation & Testing
   - Update docs
   - Validation tests

---

## Phase 1: Stabilization (0-3 hours)

### Task 1.1: Remove Railway Cron Jobs
**File:** `railway.yml`
**Action:** Delete redundant cron jobs, keep only 5-minute heartbeat
```yaml
# BEFORE: Multiple cron jobs
# AFTER: Single unified heartbeat
```

### Task 1.2: Centralize Scheduling
**File:** `tools/kurultai/agent_tasks.py`
**Add:** HeartbeatTask dataclasses for:
- jochi_smoke_tests (15 min)
- jochi_hourly_tests (60 min)
- jochi_nightly_tests (daily)
- kublai_weekly_reflection (weekly)

### Task 1.3: Offload Telemetry
**File:** `tools/kurultai/heartbeat_master.py`
**Modify:** `_log_cycle()` method
- Remove Neo4j CREATE queries
- Add structured JSON logging
- Install python-json-logger

### Task 1.4: Database Cleanup
**One-time Cypher:**
```cypher
MATCH (h:HeartbeatCycle) DETACH DELETE h;
MATCH (t:TaskResult) DETACH DELETE t;
DROP INDEX heartbeat_cycle_number IF EXISTS;
```

---

## Phase 2: Async Execution (3-6 hours)

### Task 2.1: Provision Redis
**Action:** Add Redis to stack
**Options:**
- Local: `brew install redis && brew services start redis`
- Docker: `docker run -d -p 6379:6379 redis:alpine`

### Task 2.2: Install Dependencies
```bash
pip install redis rq rq-scheduler
```

### Task 2.3: Refactor Heartbeat Master
**File:** `tools/kurultai/heartbeat_master.py`
**Modify:** `run_cycle()` to enqueue tasks instead of executing
```python
from rq import Queue
from redis import Redis

redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
q = Queue("kurultai-tasks", connection=redis_conn)

# Instead of await handler:
q.enqueue('tools.kurultai.agent_tasks.execute_task', 
          task_name, 
          job_timeout='15m')
```

### Task 2.4: Create Worker Service
**File:** `tools/kurultai/worker.py`
**New file:** RQ worker that processes queue

**File:** `railway.yml` (or systemd/LaunchAgent)
**Add:** Worker service configuration

### Task 2.5: Task Execution Handler
**File:** `tools/kurultai/agent_tasks.py`
**Add:** `execute_task()` function that RQ calls

---

## Phase 3: FastAPI Migration (6-10 hours)

### Task 3.1: Setup FastAPI Structure
**New Directory:** `tools/kurultai/api/`
```
tools/kurultai/api/
├── __init__.py
├── main.py              # FastAPI app
├── routes/
│   ├── __init__.py
│   ├── health.py
│   ├── architecture.py
│   ├── proposals.py
│   └── workflow.py
├── models.py
└── dependencies.py
```

### Task 3.2: Install FastAPI Dependencies
```bash
pip install fastapi uvicorn python-multipart
```

### Task 3.3: Port Core Endpoints
**From:** `src/kublai/architecture-introspection.js`
**To:** `tools/kurultai/api/routes/architecture.py`

**From:** `src/kublai/proactive-reflection.js`
**To:** `tools/kurultai/api/routes/proposals.py`

**From:** `src/kublai/delegation-protocol.js`
**To:** `tools/kurultai/api/routes/workflow.py`

### Task 3.4: Update Server Startup
**File:** `src/server.py` → `tools/kurultai/api/main.py`
**Port:** 8082 (keep same)

---

## Phase 4: Testing & Validation (10-12 hours)

### Task 4.1: Integration Tests
**File:** `tests/test_v4_migration.py`
- Test Redis connectivity
- Test queue enqueue/dequeue
- Test FastAPI endpoints

### Task 4.2: Smoke Tests
- Verify heartbeat still runs
- Verify Signal integration works
- Verify all 6 agents can receive tasks

### Task 4.3: Documentation Update
**Files:**
- Update `ARCHITECTURE.md`
- Update `IMPLEMENTATION_PLAN.md`
- Create `MIGRATION_GUIDE.md`

---

## Execution Order (Tonight)

### Hour 0-2: Phase 1 Foundation
- [ ] 1.1 Remove railway.yml cron jobs
- [ ] 1.2 Centralize scheduling in agent_tasks.py
- [ ] 1.3 Modify heartbeat_master.py for structured logging
- [ ] 1.4 Run database cleanup

### Hour 2-4: Phase 2 Redis Setup
- [ ] 2.1 Install and start Redis locally
- [ ] 2.2 Install RQ dependencies
- [ ] 2.3 Create worker.py

### Hour 4-6: Phase 2 Integration
- [ ] 2.4 Refactor heartbeat_master.py for queuing
- [ ] 2.5 Create LaunchAgent for worker
- [ ] 2.6 Test basic enqueue/dequeue

### Hour 6-9: Phase 3 FastAPI
- [ ] 3.1 Setup FastAPI directory structure
- [ ] 3.2 Port architecture endpoints
- [ ] 3.3 Port proposals endpoints
- [ ] 3.4 Port workflow endpoints

### Hour 9-11: Integration
- [ ] 3.5 Update server startup
- [ ] 3.6 Test API endpoints
- [ ] 4.1 Integration tests

### Hour 11-12: Documentation
- [ ] 4.3 Update all docs
- [ ] Create summary report

---

## Risk Mitigation

### If Redis Fails
- Fallback: Keep synchronous execution temporarily
- Log warning, continue with Phase 1 benefits

### If FastAPI Port Blocked
- Keep Express running on 8082
- Mount FastAPI on 8083
- Nginx reverse proxy if needed

### If Tests Fail
- Feature flags for new code
- Keep old implementation as backup

---

## Success Criteria (Morning Check)

✅ Heartbeat runs every 5 minutes without Neo4j bloat
✅ Redis queue processing tasks asynchronously
✅ FastAPI serving requests (even if alongside Express)
✅ All 6 agents operational
✅ Signal integration working
✅ Documentation updated

---

## Morning Report Location
`/Users/kublai/kurultai/kublai-repo/MORNING_REPORT.md`

Will contain:
- What was completed
- What's partially done
- What's blocked/needs your input
- Next steps
