# Kurultai Multi-Agent System Integration Patterns for Queue Monitoring and Redistribution

## Executive Summary

This document explores system integration patterns for queue monitoring and redistribution in the Kurultai multi-agent system, analyzing existing architecture and proposing enhanced integration strategies for real-time coordination, state consistency, and efficient load balancing.

## 1. Integration Points

### 1.1 task_intake.py Hook Points

**Current Architecture:**
- `get_queue_depth(agent)` - Total queue depth (executing + pending)
- `get_all_agent_queue_depths()` - Cross-agent queue state
- `find_underutilized_agents()` - Load balancing logic
- `get_capable_alternates()` - Capability-based routing
- `can_handle_task()` - Task-agent compatibility checks

**Key Integration Hook Points:**
```python
# Primary routing decision hooks
def route_by_text(text):  # Entry point for capability matching
def find_best_agent(task_text, agent=None):  # Queue-aware routing
def route_to_available_agent(task_text, original_agent=None):  # Overflow handling

# Queue monitoring hooks
def get_agent_load(agent):  # Returns {"executing": int, "pending": int}
def is_agent_failing(agent):  # Failure rate bypass logic
def get_agent_failure_rate(agent, hours=2):  # Neo4j ledger integration
```

### 1.2 task-watcher.py Integration Points

**Current Monitoring Architecture:**
- Polling-based task discovery (`watch_cycle()`)
- In-memory active execution tracking (`active_executions`)
- File-based execution state (`.executing.md` files)
- Spawn queue processing (`process_spawn_queue()`)

**Integration Opportunities:**
```python
# Queue state synchronization hooks
def watch_cycle(executor):  # Main monitoring loop
def process_spawn_queue():  # Subagent spawn routing
def _neo4j_reconcile():  # Neo4j state sync
def _append_ledger(entry):  # Task ledger updates
```

### 1.3 Neo4j Ledger Integration

**Current Schema:**
- `(:Task)` nodes with status, agent, retry_count
- `(:Agent)` nodes with execution relationships
- Atomic status updates and retry tracking

**Integration Patterns:**
- Task creation via `neo4j_task_tracker.create_task()`
- Status updates via `_neo4j_update_status()`
- Hourly summaries via `get_hourly_summary()`
- Reconciliation via `_neo4j_reconcile()`

### 1.4 Session Management Integration

**Current State Management:**
- File-based state (`WATCHER_STATE.json`)
- In-memory active execution tracking
- JSON ledger for task history

**Integration Requirements:**
- Cross-component session consistency
- Shared queue state synchronization
- Event-driven state notifications

## 2. Data Flow Architecture

### 2.1 Current Data Flow

```
Task Creation → task_intake.py → Neo4j → Filesystem → task-watcher.py → Agent Execution
       ↓
Queue Depth Check → Load Balancing → Capability Matching → Redirection
       ↓
Task Redistribution → task-redistribute.py → Filesystem Migration
```

### 2.2 Real-time Synchronization Patterns

**Option 1: Event-Driven Architecture**
```python
class QueueMonitor:
    def __init__(self):
        self.subscribers = []
        self.state_cache = {}

    def subscribe(self, callback):
        """Subscribe to queue state changes"""
        self.subscribers.append(callback)

    def notify_subscribers(self, event_type, data):
        """Notify all subscribers of state changes"""
        for callback in self.subscribers:
            callback(event_type, data)

    def update_queue_depth(self, agent, depth):
        """Update queue depth and notify subscribers"""
        old_depth = self.state_cache.get(agent, 0)
        self.state_cache[agent] = depth
        if old_depth != depth:
            self.notify_subscribers("queue_depth_changed", {
                "agent": agent,
                "old_depth": old_depth,
                "new_depth": depth
            })
```

**Option 2: Polling-Based Cache Synchronization**
```python
class QueueStateManager:
    def __init__(self, cache_ttl=30):
        self.cache = {}
        self.last_update = {}
        self.cache_ttl = cache_ttl

    def get_fresh_queue_depths(self):
        """Get current queue depths with cache refresh"""
        now = time.time()
        stale_agents = [
            agent for agent, last in self.last_update.items()
            if now - last > self.cache_ttl
        ]

        if stale_agents:
            fresh_depths = get_all_agent_queue_depths()
            for agent, depth in fresh_depths.items():
                self.cache[agent] = depth
                self.last_update[agent] = now
        return self.cache
```

### 2.3 Event-Driven vs Polling-Based Decision

**Current State:** Polling-based (task-watcher polls every cycle)
**Recommended Enhancement:** Hybrid approach

```python
class HybridQueueMonitor:
    def __init__(self):
        self.polling_enabled = True
        self.event_driven_callbacks = []
        self.last_poll_time = 0
        self.poll_interval = 30  # seconds

    def on_queue_change(self, callback):
        """Register for event-driven notifications"""
        self.event_driven_callbacks.append(callback)

    def get_queue_depths(self):
        """Get current queue state with hybrid refresh strategy"""
        now = time.time()

        # Force refresh if polling is enabled and interval passed
        if self.polling_enabled and (now - self.last_poll_time > self.poll_interval):
            self._refresh_cache()
            self.last_poll_time = now

        return self.cache

    def _refresh_cache(self):
        """Refresh queue state from filesystem"""
        fresh_depths = get_all_agent_queue_depths()
        # Compare with current cache and trigger events
        for agent, new_depth in fresh_depths.items():
            old_depth = self.cache.get(agent, 0)
            if old_depth != new_depth:
                self._notify_change(agent, old_depth, new_depth)
        self.cache.update(fresh_depths)
```

### 2.4 Conflict Resolution Patterns

**File Operation Race Conditions:**
```python
class TaskFileLock:
    def __init__(self, task_path):
        self.lock_path = Path(str(task_path) + ".lock")
        self.task_path = Path(task_path)

    def __enter__(self):
        # Non-blocking lock acquisition
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            self.lock_file = fd
            return self
        except FileExistsError:
            raise TaskFileConflict(f"Task {self.task_path} is being modified")

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'lock_file'):
            os.close(self.lock_file)
            self.lock_path.unlink()
```

**Redistribution Conflict Resolution:**
```python
class RedistributionCoordinator:
    def __init__(self):
        self.active_reallocations = {}
        self.lock = threading.Lock()

    def reallocate_task(self, src_agent, dest_agent, task_path):
        """Atomic task reallocation with conflict detection"""
        task_id = str(task_path)

        with self.lock:
            # Check if task is already being moved
            if task_id in self.active_reallocations:
                raise TaskReallocationConflict(
                    f"Task {task_id} already being moved"
                )

            # Mark task as being reallocated
            self.active_reallocations[task_id] = {
                "src": src_agent,
                "dest": dest_agent,
                "timestamp": time.time()
            }

        try:
            # Perform the actual move
            success, result = self._move_task_atomically(task_path, dest_agent)

            with self.lock:
                if task_id in self.active_reallocations:
                    del self.active_reallocations[task_id]

            return success, result

        except Exception as e:
            with self.lock:
                if task_id in self.active_reallocations:
                    del self.active_reallocations[task_id]
            raise e
```

## 3. Interface Design

### 3.1 API Contracts

**Queue Monitoring Service API:**
```python
class QueueMonitoringAPI:
    """Centralized queue monitoring service with REST-like interface"""

    def get_agent_status(self, agent_name: str) -> dict:
        """Get complete status for a single agent"""
        return {
            "agent": agent_name,
            "queue_depth": self.get_queue_depth(agent_name),
            "executing": self.get_executing_count(agent_name),
            "pending": self.get_pending_count(agent_name),
            "failure_rate": self.get_failure_rate(agent_name),
            "is_failing": self.is_agent_failing(agent_name)
        }

    def get_all_agent_status(self) -> dict:
        """Get status for all agents"""
        return {
            agent: self.get_agent_status(agent)
            for agent in VALID_AGENTS
        }

    def get_routing_recommendations(self, task_text: str) -> list:
        """Get routing recommendations for a task"""
        return self.analyze_routing_options(task_text)

    def register_callback(self, event_type: str, callback: callable):
        """Register for real-time event notifications"""
        pass
```

**Task Redistribution Service API:**
```python
class TaskRedistributionAPI:
    """High-level task redistribution service"""

    def redistribute_tasks(self,
                          strategy: str = "load_balance",
                          max_tasks: int = 10,
                          dry_run: bool = False) -> dict:
        """Execute redistribution with specified strategy"""

    def get_redistribution_plan(self, strategy: str = "load_balance") -> dict:
        """Preview redistribution without executing"""

    def trigger_redistribution(self, trigger: str, data: dict = None):
        """Trigger redistribution via external events"""
        # Possible triggers: "queue_threshold_exceeded", "agent_failure", "manual"

    def get_redistribution_history(self, hours: int = 24) -> list:
        """Get redistribution audit history"""
```

### 3.2 Callback Mechanisms

**Event Types:**
```python
QUEUE_EVENTS = {
    "QUEUE_DEPTH_EXCEEDED": {
        "threshold": QUEUE_HIGH_THRESHOLD,
        "callback": self._on_queue_exceeded
    },
    "AGENT_FAILURE_DETECTED": {
        "threshold": AGENT_FAILURE_BYPASS_THRESHOLD,
        "callback": self._on_agent_failure
    },
    "REDISTRIBUTION_COMPLETED": {
        "callback": self._on_redistribution_complete
    },
    "TASK_REASSIGNED": {
        "callback": self._on_task_reassigned
    }
}
```

**Callback Implementation:**
```python
class EventManager:
    def __init__(self):
        self.event_handlers = defaultdict(list)
        self.event_history = []

    def register_handler(self, event_type: str, handler: callable):
        """Register event handler"""
        self.event_handlers[event_type].append(handler)

    def emit_event(self, event_type: str, data: dict):
        """Emit event to all registered handlers"""
        event = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        self.event_history.append(event)

        for handler in self.event_handlers[event_type]:
            try:
                handler(event)
            except Exception as e:
                self._log_event_error(event, e)

    def _on_queue_exceeded(self, event):
        """Handle queue threshold exceeded"""
        agent = event["data"]["agent"]
        depth = event["data"]["depth"]

        if depth >= QUEUE_CRITICAL_THRESHOLD:
            self.emit_event("REDISTRIBUTION_TRIGGERED", {
                "reason": "critical_queue",
                "agent": agent,
                "depth": depth
            })
```

### 3.3 State Machine for Redistribution Workflow

```python
from enum import Enum
from dataclasses import dataclass

class RedistributionState(Enum):
    IDLE = "idle"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

@dataclass
class RedistributionContext:
    state: RedistributionState
    source_agent: str
    target_agent: str
    tasks_moved: list
    start_time: datetime
    end_time: datetime = None
    error: str = None

class RedistributionStateMachine:
    def __init__(self):
        self.current_state = RedistributionState.IDLE
        self.context = None
        self.state_transitions = {
            RedistributionState.IDLE: [RedistributionState.ANALYZING],
            RedistributionState.ANALYZING: [RedistributionState.PLANNING],
            RedistributionState.PLANNING: [RedistributionState.EXECUTING],
            RedistributionState.EXECUTING: [RedistributionState.COMPLETED, RedistributionState.FAILED],
            RedistributionState.FAILED: [RedistributionState.ROLLED_BACK],
            RedistributionState.ROLLED_BACK: [RedistributionState.COMPLETED]
        }

    def transition_to(self, new_state: RedistributionState, context: RedistributionContext = None):
        """State transition with validation"""
        if new_state not in self.state_transitions[self.current_state]:
            raise InvalidStateTransition(
                f"Cannot transition from {self.current_state} to {new_state}"
            )

        self.current_state = new_state
        self.context = context

        # Emit state change event
        self._emit_state_change(new_state, context)

    def _emit_state_change(self, new_state: RedistributionState, context: RedistributionContext):
        """Emit state change event"""
        event_data = {
            "from_state": self.current_state,
            "to_state": new_state,
            "context": context,
            "timestamp": datetime.now().isoformat()
        }

        # Notify monitoring systems
        self.emit_event("REDISTRIBUTION_STATE_CHANGE", event_data)
```

### 3.4 Configuration Management Integration

```python
class QueueConfiguration:
    """Centralized queue configuration management"""

    def __init__(self):
        self.config = self._load_config()
        self.watchers = []

    def _load_config(self) -> dict:
        """Load configuration from multiple sources"""
        return {
            "thresholds": {
                "high": QUEUE_HIGH_THRESHOLD,
                "critical": QUEUE_CRITICAL_THRESHOLD,
                "low": QUEUE_LOW_THRESHOLD
            },
            "retries": {
                "max_attempts": MAX_RETRY_COUNT,
                "backoff_multiplier": 2.0,
                "initial_delay": 60
            },
            "monitoring": {
                "poll_interval": 30,
                "cache_ttl": 30,
                "enable_events": True
            },
            "redistribution": {
                "max_tasks_per_cycle": 10,
                "enable_auto_redistribution": True,
                "strategies": ["load_balance", "capability_based", "failure_driven"]
            }
        }

    def update_thresholds(self, new_thresholds: dict):
        """Update queue thresholds and notify watchers"""
        old_config = self.config["thresholds"].copy()
        self.config["thresholds"].update(new_thresholds)

        # Notify configuration changes
        self._notify_config_change("thresholds", old_config, new_thresholds)

    def _notify_config_change(self, config_type: str, old_value: dict, new_value: dict):
        """Notify watchers of configuration changes"""
        for watcher in self.watchers:
            try:
                watcher(config_type, old_value, new_value)
            except Exception as e:
                log(f"Configuration watcher error: {e}")
```

## 4. Consistency Patterns

### 4.1 Queue State Consistency Across Components

**Multi-Layer Consistency Strategy:**
```python
class ConsistencyManager:
    def __init__(self):
        self.state_layers = {
            "memory": {},  # In-memory cache
            "filesystem": {},  # Filesystem state
            "neo4j": {}  # Graph database state
        }
        self.consistency_check_interval = 60  # seconds

    def ensure_consistency(self, agent: str = None):
        """Ensure consistency across all state layers"""
        if agent:
            agents = [agent]
        else:
            agents = VALID_AGENTS

        for agent_name in agents:
            self._sync_agent_state(agent_name)

    def _sync_agent_state(self, agent: str):
        """Synchronize state for a single agent across layers"""
        # Get current state from all layers
        memory_state = self.state_layers["memory"].get(agent)
        filesystem_state = self._get_filesystem_state(agent)
        neo4j_state = self._get_neo4j_state(agent)

        # Determine authoritative source (filesystem for truth)
        authoritative = filesystem_state

        # Resolve discrepancies
        if memory_state != authoritative:
            self._update_memory_state(agent, authoritative)

        if neo4j_state != authoritative:
            self._update_neo4j_state(agent, authoritative)
```

### 4.2 Race Condition Handling

**File Operation Atomicity:**
```python
class AtomicTaskOperations:
    @staticmethod
    def atomic_move(src_path: Path, dest_path: Path, agent: str):
        """Atomic task file move with rollback capability"""
        temp_path = dest_path.with_suffix(dest_path.suffix + ".tmp")

        try:
            # Phase 1: Create temporary file
            content = src_path.read_text()
            updated_content = AtomicTaskOperations._update_agent_metadata(content, agent)
            temp_path.write_text(updated_content)

            # Phase 2: Atomic rename
            dest_path.replace(temp_path)

            # Phase 3: Cleanup source
            src_path.unlink()

            return True, str(dest_path)

        except Exception as e:
            # Rollback: clean up temporary file
            if temp_path.exists():
                temp_path.unlink()
            return False, str(e)

    @staticmethod
    def _update_agent_metadata(content: str, agent: str) -> str:
        """Update agent metadata in task content"""
        import re
        updated = re.sub(r'^agent: \w+$', f'agent: {agent}', content, flags=re.MULTILINE)
        return updated
```

### 4.3 Neo4j Ledger Consistency

**Transaction Guarantees:**
```python
class Neo4jTransactionManager:
    def __init__(self, tracker: TaskTracker):
        self.tracker = tracker
        self.pending_transactions = []

    def execute_transaction(self, operation: callable, *args, **kwargs):
        """Execute Neo4j operation with transaction guarantees"""
        try:
            # Begin transaction
            with self.tracker.driver.session() as session:
                result = session.execute_write(
                    lambda tx: operation(tx, *args, **kwargs)
                )

                # Log successful transaction
                self._log_transaction(operation.__name__, args, kwargs, "SUCCESS")
                return result

        except Exception as e:
            # Handle transaction failure
            self._log_transaction(operation.__name__, args, kwargs, "FAILED", str(e))
            self._handle_transaction_failure(e)
            raise

    def _handle_transaction_failure(self, error: Exception):
        """Handle transaction failure and attempt recovery"""
        if "Connection" in str(error):
            # Attempt to reconnect
            self.tracker.driver = get_driver()
        elif "Timeout" in str(error):
            # Implement retry logic
            pass
        elif "Constraint" in str(error):
            # Handle constraint violations
            pass
```

### 4.4 Recovery Procedures for Partial Redistribution Failures

**Partial Failure Recovery:**
```python
class RedistributionRecoveryManager:
    def __init__(self):
        self.redistribution_log = []
        self.recovery_strategies = {
            "partial_move": self._recover_partial_move,
            "agent_unavailable": self._recover_agent_unavailable,
            "network_failure": self._recover_network_failure,
            "consistency_violation": self._recover_consistency_violation
        }

    def recover_redistribution(self, failed_redistribution: dict):
        """Recover from failed redistribution"""
        error_type = failed_redistribution["error_type"]
        strategy = self.recovery_strategies.get(error_type)

        if strategy:
            try:
                recovery_result = strategy(failed_redistribution)
                self._log_recovery_attempt(failed_redistribution, recovery_result)
                return recovery_result
            except Exception as e:
                self._log_recovery_failure(failed_redistribution, str(e))
                raise

    def _recover_partial_move(self, failed_redistribution: dict):
        """Recover from partial task move"""
        # Identify partially moved tasks
        moved_tasks = failed_redistribution.get("successfully_moved", [])
        failed_tasks = failed_redistribution.get("failed_moves", [])

        # Rollback successful moves
        rollback_results = []
        for task in moved_tasks:
            try:
                rollback_success = self._rollback_task_move(task)
                rollback_results.append({"task": task, "rollback_success": rollback_success})
            except Exception as e:
                rollback_results.append({"task": task, "rollback_error": str(e)})

        return {
            "recovery_type": "partial_move",
            "rollback_results": rollback_results,
            "recommendation": "Manual verification required"
        }

    def _rollback_task_move(self, task: dict):
        """Rollback a single task move"""
        src_agent = task["original_agent"]
        dest_agent = task["target_agent"]
        task_path = task["path"]

        # Move task back to original agent
        return self.atomic_move_back(task_path, src_agent)
```

## 5. Implementation Recommendations

### 5.1 Phase 1: Enhanced Monitoring (Immediate)
1. **Implement real-time queue state caching**
   - Add `QueueStateManager` class with TTL-based refresh
   - Integrate with existing `task_intake.py` queue depth functions
   - Add event notifications for significant state changes

2. **Enhanced failure detection**
   - Improve `is_agent_failing()` with Neo4j integration
   - Add predictive failure detection based on retry patterns
   - Implement health scoring for each agent

### 5.2 Phase 2: Event-Driven Architecture (Short-term)
1. **Implement event system**
   - Create `EventManager` for cross-component communication
   - Add event types for queue changes, agent failures, redistributions
   - Implement callback registration system

2. **State machine for redistribution**
   - Implement `RedistributionStateMachine`
   - Add rollback capabilities for failed redistributions
   - Create audit trail for all redistribution events

### 5.3 Phase 3: Advanced Coordination (Long-term)
1. **Distributed coordination service**
   - Implement `QueueCoordinator` for multi-agent coordination
   - Add leader election for redistribution decisions
   - Implement consensus protocols for conflicting operations

2. **Predictive load balancing**
   - Add machine learning for predictive task routing
   - Implement historical analysis for capacity planning
   - Add auto-scaling capabilities based on workload patterns

## 6. Conclusion

The Kurultai system already has a solid foundation for queue monitoring and redistribution with task_intake.py, task-watcher.py, and task-redistribute.py. The key opportunities for enhancement are:

1. **Real-time event-driven coordination** instead of polling-based state checking
2. **Enhanced consistency guarantees** across filesystem, Neo4j, and in-memory state
3. **Sophisticated recovery mechanisms** for partial operation failures
4. **Predictive capabilities** for proactive load balancing

The proposed integration patterns would enable more responsive, consistent, and reliable operation while maintaining backward compatibility with the existing task processing pipeline.