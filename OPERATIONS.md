# Kurultai v4.0 Operations Guide
**Version:** 4.0  
**Last Updated:** 2026-02-25  
**Purpose:** Runbook for system maintenance, troubleshooting, and monitoring

---

## Quick Reference

### Service Status Check
```bash
cd ~/kurultai/kublai-repo

# All services
launchctl list | grep kurultai

# Individual checks
curl http://localhost:8082/health          # FastAPI
redis-cli ping                             # Redis
python -c "from neo4j import GraphDatabase; GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','myStrongPassword123')).verify_connectivity()"
```

### Service Control

**Restart Heartbeat:**
```bash
launchctl kickstart -k gui/$UID/com.kurultai.heartbeat
```

**Restart Worker:**
```bash
launchctl kickstart -k gui/$UID/com.kurultai.worker
```

**Restart API:**
```bash
launchctl kickstart -k gui/$UID/com.kurultai.api
```

**View Logs:**
```bash
tail -f logs/heartbeat.log              # Heartbeat
tail -f logs/worker.stdout.log          # Worker
tail -f logs/api.stdout.log             # API
tail -f logs/worker.stderr.log          # Worker errors
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  User Layer (Signal, Web UI, HTTP API)                      │
└─────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  OpenClaw Gateway (Port 18789)                              │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  FastAPI (Port 8082) - Unified Python Backend               │
│  Endpoints: /health, /api/architecture/*, /api/agents       │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  Unified Heartbeat (5-min cron via LaunchAgent)             │
│  - Dispatches tasks to Redis queue (~50ms)                  │
│  - Logs to stdout (JSON structured)                         │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  Redis Queue (localhost:6379)                               │
│  Queue: kurultai-tasks                                      │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  RQ Worker (via LaunchAgent)                                │
│  - Executes tasks with 15-minute timeout                    │
│  - Can scale horizontally                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Common Operations

### 1. Check System Health

**Full Health Check:**
```bash
cd ~/kurultai/kublai-repo
source venv/bin/activate

# Run comprehensive tests
python <<'PYEOF'
from redis import Redis
from neo4j import GraphDatabase
import requests

checks = []

# Redis
r = Redis()
checks.append(("Redis", r.ping() == True))

# Neo4j
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'myStrongPassword123'))
try:
    driver.verify_connectivity()
    checks.append(("Neo4j", True))
except:
    checks.append(("Neo4j", False))

# FastAPI
try:
    resp = requests.get('http://localhost:8082/health', timeout=5)
    checks.append(("FastAPI", resp.status_code == 200))
except:
    checks.append(("FastAPI", False))

# RQ Queue
from rq import Queue
q = Queue('kurultai-tasks', connection=r)
checks.append(("RQ Queue", q is not None))

print("System Health:")
for name, status in checks:
    print(f"  {'✅' if status else '❌'} {name}")
PYEOF
```

### 2. Monitor Queue Status

```bash
cd ~/kurultai/kublai-repo
source venv/bin/activate

python -c "
from redis import Redis
from rq import Queue
from rq.job import Job

r = Redis()
q = Queue('kurultai-tasks', r)

print(f'Queue: kurultai-tasks')
print(f'  Pending jobs: {q.count}')
print(f'  Started jobs: {len(q.started_job_registry)}')
print(f'  Failed jobs: {len(q.failed_job_registry)}')
print(f'  Finished jobs: {len(q.finished_job_registry)}')
"
```

### 3. Retry Failed Jobs

```bash
cd ~/kurultai/kublai-repo
source venv/bin/activate

python <<'PYEOF'
from redis import Redis
from rq import Queue

r = Redis()
q = Queue('kurultai-tasks', r)

failed = q.failed_job_registry
print(f"Failed jobs: {len(failed)}")

for job_id in failed.get_job_ids()[:5]:  # Retry first 5
    job = q.fetch_job(job_id)
    if job:
        print(f"Retrying {job_id}...")
        job.requeue()
PYEOF
```

### 4. Check Worker Status

```bash
# See if worker process is running
ps aux | grep "kurultai.worker" | grep -v grep

# Check worker logs
tail -50 logs/worker.stdout.log
tail -50 logs/worker.stderr.log
```

### 5. Manual Task Execution

If you need to run a task manually:

```bash
cd ~/kurultai/kublai-repo
source venv/bin/activate

# Run specific task
python -c "
import asyncio
from neo4j import GraphDatabase
from tools.kurultai.agent_tasks import ogedei_health_check

driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'myStrongPassword123'))
result = asyncio.run(ogedei_health_check(driver))
print(result)
driver.close()
"
```

---

## Troubleshooting

### Problem: Heartbeat not running

**Symptoms:** No new log entries in `logs/heartbeat.log`

**Diagnosis:**
```bash
launchctl list | grep heartbeat
# Should show: 15628	0	com.kurultai.heartbeat

# Check logs
tail -20 logs/heartbeat.launchd.log
tail -20 logs/heartbeat.launchd.err
```

**Solution:**
```bash
# Restart
launchctl kickstart -k gui/$UID/com.kurultai.heartbeat

# Or unload/reload
launchctl unload ~/Library/LaunchAgents/com.kurultai.heartbeat.plist
launchctl load ~/Library/LaunchAgents/com.kurultai.heartbeat.plist
```

### Problem: Tasks not executing (queue growing)

**Symptoms:** `rq.count` increasing, no tasks completing

**Diagnosis:**
```bash
# Check if worker is running
ps aux | grep "rq worker" | grep -v grep

# Check worker logs
tail -50 logs/worker.stderr.log
```

**Solution:**
```bash
# Restart worker
launchctl kickstart -k gui/$UID/com.kurultai.worker
```

### Problem: Neo4j connection errors

**Symptoms:** Tasks failing with Neo4j errors

**Diagnosis:**
```bash
# Check Neo4j status
brew services list | grep neo4j

# Check Neo4j logs
tail -20 /opt/homebrew/var/log/neo4j.log
```

**Solution:**
```bash
# Restart Neo4j
brew services restart neo4j

# Or manually
/opt/homebrew/opt/neo4j/bin/neo4j restart
```

### Problem: FastAPI not responding

**Symptoms:** `curl http://localhost:8082/health` hangs or fails

**Diagnosis:**
```bash
# Check if port is in use
lsof -i :8082

# Check API logs
tail -50 logs/api.stderr.log
```

**Solution:**
```bash
# Restart API
launchctl kickstart -k gui/$UID/com.kurultai.api
```

### Problem: Redis connection errors

**Symptoms:** RQ or heartbeat can't connect to Redis

**Diagnosis:**
```bash
redis-cli ping
# Should return: PONG

# Check Redis logs
redis-cli INFO stats
```

**Solution:**
```bash
# Restart Redis
brew services restart redis
```

---

## Performance Tuning

### Redis Memory

Check Redis memory usage:
```bash
redis-cli INFO memory | grep used_memory_human
```

If high, clear old data:
```bash
redis-cli FLUSHDB  # WARNING: Clears all queue data
```

### Neo4j Memory

Monitor Neo4j heap:
```bash
tail -5 /opt/homebrew/var/log/neo4j.log | grep heap
```

Adjust in `/opt/homebrew/Cellar/neo4j/*/conf/neo4j.conf`:
```
dbms.memory.heap.max_size=2G
```

### Log Rotation

Logs are configured to rotate but check sizes:
```bash
du -sh logs/
ls -lh logs/*.log | tail -5
```

Manual cleanup:
```bash
# Archive old logs
mkdir -p logs/archive
cp logs/*.log logs/archive/
gzip logs/archive/*.log

# Clear current logs
> logs/heartbeat.log
> logs/worker.stdout.log
> logs/api.stdout.log
```

---

## Backup Procedures

### Neo4j Backup

```bash
# Create backup
neo4j-admin database dump neo4j --to=~/kurultai/backups/neo4j-$(date +%Y%m%d).dump

# Or script
~/kurultai/kublai-repo/scripts/backup_neo4j.sh
```

### Configuration Backup

```bash
# Backup critical files
tar czf ~/kurultai/backups/config-$(date +%Y%m%d).tar.gz \
  ~/.openclaw/openclaw.json \
  ~/kurultai/kublai-repo/.env \
  ~/kurultai/kublai-repo/railway.yml
```

### Full System Backup

```bash
# All of Kurultai
tar czf ~/kurultai/backups/kurultai-full-$(date +%Y%m%d).tar.gz \
  ~/kurultai/kublai-repo/ \
  --exclude='*.log' \
  --exclude='venv' \
  --exclude='node_modules'
```

---

## Security Notes

- Credentials stored in: `~/.openclaw/agents/main/.credentials.env`
- File permissions: 600 (owner read/write only)
- SSH key for GitHub: `~/.ssh/id_ed25519.pub`
- Never commit credentials to git
- Rotate tokens periodically

---

## Monitoring Checklist

**Daily:**
- [ ] Check `logs/heartbeat.log` for errors
- [ ] Verify all 3 services running: `launchctl list | grep kurultai`
- [ ] Review failed jobs: `python -c "from rq import Queue; q=Queue('kurultai-tasks'); print(len(q.failed_job_registry))"`

**Weekly:**
- [ ] Archive old logs
- [ ] Check disk space: `df -h`
- [ ] Review Neo4j memory usage
- [ ] Backup critical data

**Monthly:**
- [ ] Rotate API tokens
- [ ] Review and update documentation
- [ ] Test disaster recovery procedure

---

## Emergency Contacts

- **Kublai (Squad Lead):** That's me! Ask me anything about the system.
- **Temüjin (Developer):** For code/deployment issues
- **Ögedei (Ops):** For infrastructure emergencies

---

*Document Version: 4.0*  
*Last Tested: 2026-02-25*  
*All systems operational*
