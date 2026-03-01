Loaded cached credentials.
Here is the detailed implementation plan for activating the `heartbeat_master.py` daemon mode for the Kurultai AI agent system.

# Implementation Plan: Kurultai Heartbeat Master Daemon

## 1. Overview
This document outlines the phased approach to configuring, testing, and deploying the `heartbeat_master.py` script in daemon mode. This will enable continuous and concurrent operation for the 6 core Kurultai agents (Kublai, Möngke, Chagatai, Temüjin, Jochi, Ögedei) backed by a Neo4j knowledge graph.

## 2. Phase-by-Phase Implementation Plan

### Phase 1: Environment Preparation & Neo4j Configuration
- **Objective:** Ensure the environment is ready and the connection to the local Neo4j instance is secure and functional.
- **Tasks:**
  - Verify Python virtual environment dependencies.
  - Set up necessary environment variables for Neo4j authentication and OpenAI/LLM API keys.
  - Test the Neo4j connection independently before starting the daemon.

### Phase 2: Agent Task Registration
- **Objective:** Define and register the specific operational loops and token budgets for each of the 6 Kurultai agents in the system or database.
- **Tasks:**
  - Map out specific system tasks for each agent based on their architectural role.
  - Configure token budgets to prevent runaway costs during continuous operation.
  - Register task intervals (cron-like schedules or continuous loops with sleep intervals).

### Phase 3: Daemon Mode Activation & Local Testing
- **Objective:** Run the script in daemon mode locally to monitor concurrent agent operations and database interactions.
- **Tasks:**
  - Launch `heartbeat_master.py` in daemon mode.
  - Monitor logs for concurrent execution overlaps and database lock issues.
  - Validate that task frequencies align with expectations.

### Phase 4: Production Deployment
- **Objective:** Move the daemon from a manual local process to a persistent, background-managed service.
- **Tasks:**
  - Implement a process manager (e.g., systemd, PM2) or deploy to a cloud service (e.g., Railway).
  - Set up log rotation and error alerting.

---

## 3. Agent Task Definitions

The following table defines the proposed operational parameters for each agent in the Kurultai system.

| Agent Name | Role / Task Description | Execution Frequency | Token Budget (Daily) |
| :--- | :--- | :--- | :--- |
| **Temüjin** | **System Overseer:** Global goal alignment, resource allocation, and priority shifting. | Every 4 hours | 50,000 |
| **Kublai** | **Development & Admin:** Codebase implementation, infrastructure management, and deployment checks. | Every 30 minutes | 150,000 |
| **Möngke** | **Strategy & Analytics:** Data analysis, performance metrics review, and long-term planning. | Every 6 hours | 40,000 |
| **Chagatai** | **Validation & Rules:** Code review, testing validation, and constraint enforcement (Yassa). | Every 1 hour | 80,000 |
| **Jochi** | **Research & Exploration:** External data gathering, web searching, and competitive analysis. | Every 2 hours | 60,000 |
| **Ögedei** | **Integration & Expansion:** Cross-agent communication sync, memory pruning, and Neo4j graph maintenance. | Every 12 hours | 30,000 |

---

## 4. Specific Commands

### Step 1: Environment Setup
```bash
cd /Users/kublai/moltbot
# Activate virtual environment if applicable
source venv/bin/activate 

# Export required environment variables
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_secure_password" # Replace with actual password
```

### Step 2: Database Connection Test
*(Assuming the script has a dry-run or ping feature)*
```bash
python tools/kurultai/heartbeat_master.py --test-connection
```

### Step 3: Local Daemon Activation (Testing Phase)
```bash
# Run in the foreground to monitor initial logs and stdout
python tools/kurultai/heartbeat_master.py --daemon --verbose
```

### Step 4: Background Execution (Local Detached)
```bash
nohup python tools/kurultai/heartbeat_master.py --daemon > logs/heartbeat_daemon.log 2>&1 &
# Get the Process ID
echo $! > run/heartbeat.pid
```

---

## 5. Testing Plan

- [ ] **Unit Validation:** Ensure `heartbeat_master.py` can parse the provided Neo4j URI and authenticate successfully.
- [ ] **Concurrency Test:** Verify that multiple agents (e.g., Kublai and Chagatai) can write to the Neo4j graph simultaneously without transaction deadlocks.
- [ ] **Budget Enforcement Test:** Artificially exhaust an agent's token budget and verify that the daemon pauses that specific agent's tasks without crashing the entire system.
- [ ] **Recovery Test:** Manually stop the Neo4j database service while the daemon is running. Verify the daemon catches the exception, pauses operations, and successfully reconnects when Neo4j is restored.
- [ ] **Memory Leak Test:** Run the daemon locally for 24 hours while monitoring RAM usage to ensure the continuous loop doesn't leak memory.

---

## 6. Deployment Options

### Option A: Local Background Process (Simplest)
Using `nohup` or `tmux` on the local macOS machine.
- **Pros:** Zero configuration, direct access to local Neo4j.
- **Cons:** Will stop if the machine restarts; harder to monitor remotely.

### Option B: systemd / macOS launchd (Recommended for Persistent Local)
Create a macOS `launchd` plist file (since OS is Darwin) to keep the daemon alive.
- **Path:** `~/Library/LaunchAgents/com.kurultai.heartbeat.plist`
- **Pros:** Automatically starts on boot, native to macOS, restarts on failure.
- **Cons:** Tied to local hardware.

### Option C: Cloud Deployment (Railway / Render)
Containerize the application and deploy alongside a hosted Neo4j instance (AuraDB).
- **Pros:** High availability, built-in log management, uncoupled from local hardware.
- **Cons:** Requires migrating Neo4j from localhost to the cloud; potential latency increases.

---

## 7. Success Criteria

- [ ] The `heartbeat_master.py` process runs continuously for 48 hours without fatal crashes.
- [ ] All 6 agents successfully execute their assigned tasks at the configured frequencies.
- [ ] Neo4j graph reflects continuous updates, new memories, and state changes driven by the agents.
- [ ] Token usage remains within the defined budgets (totaling < 410k tokens/day).
- [ ] Logs show clear, concurrent asynchronous execution without database write locks.

---

## 8. Rollback Plan

If the daemon causes system instability, token runaway, or database corruption:
1. **Kill the Process:**
   ```bash
   kill $(cat /Users/kublai/moltbot/run/heartbeat.pid)
   # or
   pkill -f heartbeat_master.py
   ```
2. **Revert Database:** 
   Restore Neo4j from the last known good backup prior to daemon activation.
   ```bash
   # Assuming local Neo4j dump
   neo4j-admin database load --from-path=/backups neo4j
   ```
3. **Revoke Keys:** If a token runaway occurs, immediately cycle the LLM API keys.
4. **Analyze:** Review `logs/heartbeat_daemon.log` to identify the root cause of the failure before attempting a restart.

---

## 9. Timeline Estimate

| Phase | Duration | Owner |
| :--- | :--- | :--- |
| Phase 1: Config & Connection Test | 1 hour | Kublai |
| Phase 2: Task Registration & Budgets | 2 hours | Kublai |
| Phase 3: Local Daemon Testing | 24 hours (Passive) | Kublai |
| Phase 4: Production Deployment (`launchd`) | 2 hours | Kublai |
| **Total Estimated Time** | **~29 Hours** (5 hrs active) | |
