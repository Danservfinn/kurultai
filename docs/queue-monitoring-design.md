# Queue Monitoring & Redesign Design Document

**Date:** 2026-03-08
**Author:** Kublai Agent
**Status:** Draft
**Version:** 1.0

## 1. Executive Summary

This document provides detailed design specifications for implementing a comprehensive queue monitoring and redistribution system for the Kurultai multi-agent system. The design focuses on solving critical queue imbalance issues where agents like ogedei become overwhelmed while others like kublai remain idle.

### Problem Statement
- **Current Issue**: ogedei reached 11 pending tasks while kublai had 0
- **Root Cause**: Lack of proactive queue monitoring and redistribution
- **Impact**: System throughput bottlenecks, poor resource utilization
- **Scale**: 7 agents with shared filesystem-based task queues

### Solution Overview
Implement enhanced file-based monitoring with intelligent redistribution capabilities. The solution maintains compatibility with existing task_intake.py routing logic while adding:

- Continuous queue monitoring (60-second intervals)
- Automatic redistribution when imbalance exceeds thresholds
- Skill-based task matching during redistribution
- Robust error handling and recovery mechanisms

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     KUBLAI AGENT                          │
│  ┌─────────────────┐    ┌─────────────────┐             │
│  │ Queue Monitor   │    │ Redistribution  │             │
│  │ (60s intervals) │◄──►│     Engine       │             │
│  └─────────────────┘    └─────────────────┘             │
│           │                      │                      │
│  ┌─────────────────┐    ┌─────────────────┐             │
│  │ Metrics         │    │ Alerting        │             │
│  │ Collector       │    │ System          │             │
│  └─────────────────┘    └─────────────────┘             │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                Integration Layer                     │  │
│  │ • Hook into task_intake.py                           │  │
│  │ • Preserve existing routing logic                     │  │
│  │ • Maintain capability matching                        │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                   AGENT QUEUE FILES                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │  temujin/   │  │  mongke/    │  │  chagatai/  │      │
│  │  tasks/     │  │  tasks/     │  │  tasks/     │      │
│  └─────────────┘  └─────────────┘  └─────────────┘      │
│                                                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │   jochi/    │  │  ogedei/    │  │   tolui/    │      │
│  │  tasks/     │  │  tasks/     │  │  tasks/     │      │
│  └─────────────┘  └─────────────┘  └─────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Core Components

#### 2.2.1 QueueMonitor Class

```python
class QueueMonitor:
    """Continuous monitoring of agent queue depths"""

    def __init__(self, config=None):
        self.config = config or QueueMonitorConfig()
        self.last_check = None
        self.cached_depths = {}
        self.lock = threading.Lock()

    def start_monitoring(self):
        """Start continuous monitoring loop"""
        while True:
            try:
                depths = self.check_all_queues()
                self.analyze_imbalances(depths)
                time.sleep(self.config.interval)
            except Exception as e:
                self.handle_monitoring_error(e)

    def check_all_queues(self):
        """Get current queue depths for all agents"""
        depths = {}
        for agent in VALID_AGENTS:
            depths[agent] = self.get_queue_depth(agent)
        return depths
```

#### 2.2.2 RedistributionEngine Class

```python
class RedistributionEngine:
    """Handles task redistribution between agents"""

    def __init__(self, monitor):
        self.monitor = monitor
        self.redistribution_cooldown = 300  # 5 minutes
        self.last_redistribution = None
        self.max_tasks_per_cycle = 10

    def should_redistribute(self, depths):
        """Check if redistribution is needed"""
        if self._in_cooldown():
            return False

        max_depth = max(depths.values())
        min_depth = min(depths.values())

        # Trigger if max > 3 and min < 2 (existing thresholds)
        return (max_depth > self.config.high_threshold and
                min_depth < self.config.low_threshold)

    def redistribute_tasks(self):
        """Execute redistribution"""
        try:
            # Identify overloaded and underutilized agents
            overloaded = self._find_overloaded_agents()
            underutilized = self._find_underutilized_agents()

            # Match and move tasks
            moves = self._plan_task_moves(overloaded, underutilized)
            moved = self._execute_moves(moves)

            self._record_redistribution(moved)
            return moved

        except Exception as e:
            self._handle_redistribution_failure(e)
```

#### 2.2.3 MetricsCollector Class

```python
class MetricsCollector:
    """Collects and reports system metrics"""

    def __init__(self):
        self.metrics_history = []
        self.alert_thresholds = {
            'queue_imbalance': 0.8,
            'stuck_tasks': 600,
            'failure_rate': 0.3
        }

    def collect_metrics(self):
        """Collect current system metrics"""
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'queue_depths': get_all_agent_queue_depths(),
            'active_tasks': count_active_tasks(),
            'system_load': get_system_load(),
            'agent_status': self._check_agent_health()
        }

        self.metrics_history.append(metrics)
        self._check_alerts(metrics)

        return metrics
```

## 3. Detailed Design Specifications

### 3.1 Monitoring Configuration

```python
class QueueMonitorConfig:
    """Configuration for queue monitoring"""

    def __init__(self):
        # Thresholds (maintain existing values for compatibility)
        self.high_threshold = 3      # Route to alternate if primary > this
        self.low_threshold = 2       # Consider underutilized if < this
        self.critical_threshold = 8   # Broadcast to all capable if primary > this

        # Monitoring behavior
        self.monitoring_interval = 60  # seconds
        self.redistribution_cooldown = 300  # seconds
        self.max_tasks_per_redistribution = 10
        self.enable_auto_redistribution = True

        # Performance settings
        self.cache_ttl = 30  # seconds
        self.concurrent_checks = 4
```

### 3.2 Queue State Tracking

```python
def get_queue_depth(agent):
    """Get current queue depth for an agent with caching"""
    cache_key = f"queue_depth_{agent}"

    # Check cache first
    if cache_key in cache and not cache_expired(cache[cache_key]):
        return cache[cache_key]['value']

    # Calculate from filesystem
    task_dir = AGENTS_DIR / agent / "tasks"
    depth = count_pending_tasks(task_dir)

    # Update cache
    cache[cache_key] = {
        'value': depth,
        'timestamp': time.time()
    }

    return depth

def count_pending_tasks(task_dir):
    """Count pending tasks in directory"""
    if not task_dir.exists():
        return 0

    count = 0
    for pattern in ['high-*.md', 'normal-*.md', 'low-*.md']:
        for task_file in task_dir.glob(pattern):
            if ('.executing' not in task_file and
                '.done' not in task_file and
                not task_file.name.startswith('.')):
                count += 1

    return count
```

### 3.3 Redistribution Logic

```python
def plan_task_moves(overloaded_agents, underutilized_agents):
    """Plan which tasks to move from which agents"""
    moves = []

    for overloaded_agent, depth in overloaded_agents.items():
        if depth <= self.config.high_threshold:
            continue

        # Find movable tasks
        movable_tasks = self._find_movable_tasks(overloaded_agent)

        # Find best destination
        for task in movable_tasks[:3]:  # Max 3 tasks per overloaded agent
            dest_agent = self._find_best_destination(
                task,
                underutilized_agents,
                overloaded_agent
            )

            if dest_agent:
                moves.append({
                    'source': overloaded_agent,
                    'destination': dest_agent,
                    'task': task,
                    'priority': task['priority']
                })

        # Limit total moves per cycle
        if len(moves) >= self.config.max_tasks_per_redistribution:
            break

    return moves

def execute_task_moves(moves):
    """Execute planned task moves with error handling"""
    results = []

    for move in moves:
        try:
            # Acquire locks
            with self._get_agent_lock(move['source']), \
                 self._get_agent_lock(move['destination']):

                # Validate task still exists and movable
                if self._is_task_movable(move):
                    # Execute move
                    dest_path = self._move_task(move)
                    results.append({
                        'success': True,
                        'move': move,
                        'destination': str(dest_path)
                    })
                else:
                    results.append({
                        'success': False,
                        'move': move,
                        'error': 'Task no longer movable'
                    })

        except Exception as e:
            results.append({
                'success': False,
                'move': move,
                'error': str(e)
            })

    return results
```

### 3.4 Integration with task_intake.py

```python
def create_task_with_monitoring(title, body, agent=None, **kwargs):
    """Create task with queue-aware routing"""

    # Get original routing decision
    primary_agent, routing_reason = route_task(title, body, agent)

    # Check if we should consider queue balancing
    if kwargs.get('enable_queue_balancing', True):
        current_depths = get_all_agent_queue_depths()

        # If primary agent is overloaded, find alternatives
        if current_depths.get(primary_agent, 0) > QUEUE_HIGH_THRESHOLD:
            alternative = find_best_alternative(primary_agent, body, current_depths)
            if alternative:
                return create_task(title, body, agent=alternative,
                                 routing_reason=f"Queue balancing: {routing_reason}")

    # Fall back to original routing
    return create_task(title, body, agent=primary_agent,
                     routing_reason=routing_reason)
```

### 3.5 Error Handling and Recovery

```python
class RedistributionErrorHandler:
    """Handles errors during redistribution"""

    def __init__(self):
        self.retry_count = {}
        self.max_retries = 3
        self.backoff_base = 60

    def handle_redistribution_error(self, error, task_move):
        """Handle redistribution errors with retry logic"""
        move_key = f"{task_move['source']}_{task_move['task']['id']}"

        if move_key not in self.retry_count:
            self.retry_count[move_key] = 0

        if self.retry_count[move_key] < self.max_retries:
            # Schedule retry with backoff
            delay = self.backoff_base * (2 ** self.retry_count[move_key])
            self.retry_count[move_key] += 1

            log(f"Retrying redistribution in {delay}s: {error}")
            schedule_redistribution_retry(task_move, delay)
        else:
            # Permanent failure - move to dead letter queue
            log(f"Redistribution failed permanently: {error}")
            self._send_to_dlq(task_move, error)

    def _send_to_dlq(self, task_move, error):
        """Send failed move to dead letter queue"""
        dlq_entry = {
            'timestamp': datetime.now().isoformat(),
            'task_move': task_move,
            'error': str(error),
            'retry_count': self.retry_count.get(
                f"{task_move['source']}_{task_move['task']['id']}", 0
            )
        }

        dlq_file = DLQ_DIR / f"dlq_{int(time.time())}_{uuid.uuid4().hex[:8]}.json"
        with open(dlq_file, 'w') as f:
            json.dump(dlq_entry, f, indent=2)
```

## 4. Security Considerations

### 4.1 File System Security

```python
def secure_task_directories():
    """Set secure permissions on task directories"""
    for agent in VALID_AGENTS:
        task_dir = AGENTS_DIR / agent / "tasks"

        # Set directory permissions (700: owner only)
        os.chmod(task_dir, 0o700)

        # Ensure all files are readable/writable by owner only
        for task_file in task_dir.rglob("*.md"):
            os.chmod(task_file, 0o600)

        # Remove world-readable files
        for task_file in task_dir.rglob("*"):
            if task_file.is_file() and os.stat(task_file).st_mode & 0o004:
                os.chmod(task_file, 0o600)
```

### 4.2 Race Condition Prevention

```python
import fcntl

class RedistributionLock:
    """File-based lock for redistribution operations"""

    def __init__(self, lock_file="/tmp/kublai-redistribution.lock"):
        self.lock_file = lock_file

    def acquire(self):
        """Acquire exclusive lock"""
        try:
            with open(self.lock_file, 'w') as f:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._lock_file = f
                return True
        except (IOError, BlockingIOError):
            return False

    def release(self):
        """Release lock"""
        if hasattr(self, '_lock_file'):
            self._lock_file.close()
            if os.path.exists(self.lock_file):
                os.unlink(self.lock_file)
```

## 5. Performance Optimization

### 5.1 Caching Strategy

```python
from functools import lru_cache
from datetime import datetime, timedelta

@lru_cache(maxsize=128)
def get_cached_queue_depth(agent, timestamp=None):
    """Get cached queue depth with TTL"""
    if timestamp is None:
        timestamp = datetime.now()

    # Check cache freshness
    cached = cache.get(f"depth_{agent}")
    if cached and (timestamp - cached['timestamp']) < timedelta(seconds=30):
        return cached['value']

    # Calculate and cache
    depth = calculate_queue_depth(agent)
    cache[f"depth_{agent}"] = {
        'value': depth,
        'timestamp': timestamp
    }

    return depth
```

### 5.2 Batch Operations

```python
async def batch_redistribution(moves):
    """Execute multiple task moves in parallel"""
    semaphore = asyncio.Semaphore(4)  # Limit concurrent operations

    async def move_with_semaphore(move):
        async with semaphore:
            return await execute_single_move(move)

    # Execute all moves in parallel
    results = await asyncio.gather(*[
        move_with_semaphore(move) for move in moves
    ], return_exceptions=True)

    return results
```

## 6. Monitoring and Alerting

### 6.1 Metrics Collection

```python
class SystemMetrics:
    """Comprehensive system metrics"""

    def collect_metrics(self):
        return {
            'timestamp': datetime.now().isoformat(),
            'queue_depths': get_all_agent_queue_depths(),
            'agent_status': self._check_agent_health(),
            'system_performance': {
                'cpu_percent': psutil.cpu_percent(),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent
            },
            'redistribution_stats': self._get_redistribution_stats(),
            'error_rates': self._calculate_error_rates()
        }
```

### 6.2 Alert Configuration

```python
class AlertConfig:
    """Alert configuration and thresholds"""

    def __init__(self):
        self.alerts = {
            'queue_imbalance': {
                'threshold': 0.8,  # 80% variance
                'severity': 'HIGH',
                'channels': ['slack', 'email']
            },
            'stuck_tasks': {
                'threshold': 1800,  # 30 minutes
                'severity': 'CRITICAL',
                'channels': ['slack', 'pagerduty']
            },
            'system_overload': {
                'threshold': 0.9,  # 90% CPU
                'severity': 'CRITICAL',
                'channels': ['slack']
            }
        }
```

## 7. Testing Strategy

### 7.1 Unit Tests

```python
def test_queue_monitoring():
    """Test queue monitoring functionality"""
    monitor = QueueMonitor()

    # Test queue depth calculation
    depths = monitor.check_all_queues()
    assert all(isinstance(d, int) for d in depths.values())

    # Test imbalance detection
    assert monitor.detect_imbalance({'temujin': 5, 'mongke': 1}) == True
    assert monitor.detect_imbalance({'temujin': 2, 'mongke': 1}) == False

def test_redistribution_logic():
    """Test redistribution planning"""
    engine = RedistributionEngine()

    # Test task movement planning
    overloaded = {'temujin': 4}
    underutilized = {'mongke': 1}
    moves = engine.plan_task_moves(overloaded, underutilized)

    assert len(moves) > 0
    assert all(move['source'] == 'temujin' for move in moves)
```

### 7.2 Integration Tests

```python
def test_redistribution_integration():
    """Test redistribution with real filesystem"""
    # Setup test environment
    setup_test_agents()

    # Create test tasks
    create_test_task('temujin', 'high-priority task')
    create_test_task('temujin', 'normal-priority task')

    # Execute redistribution
    monitor = QueueMonitor()
    engine = RedistributionEngine(monitor)

    moves = engine.redistribute_tasks()

    # Verify results
    assert len(moves) > 0
    assert tasks_moved('temujin', 'mongke') > 0
```

## 8. Deployment Strategy

### 8.1 Phase Deployment

```python
class DeploymentPlan:
    """Multi-phase deployment plan"""

    def __init__(self):
        self.phases = {
            'phase1': {
                'duration': '1-2 weeks',
                'features': ['Basic monitoring', 'Simple redistribution'],
                'risks': ['Low'],
                'rollback': 'Easy'
            },
            'phase2': {
                'duration': '3-4 weeks',
                'features': ['Advanced metrics', 'Alerting'],
                'risks': ['Medium'],
                'rollback': 'Medium'
            },
            'phase3': {
                'duration': '5-6 weeks',
                'features': ['Performance optimization', 'Advanced features'],
                'risks': ['Medium'],
                'rollback': 'Hard'
            }
        }
```

### 8.2 Rollback Procedures

```python
class RollbackManager:
    """Manages rollback operations"""

    def create_backup(self):
        """Create pre-deployment backup"""
        backup = {
            'timestamp': datetime.now().isoformat(),
            'queue_states': self._backup_queue_states(),
            'config': self._backup_config(),
            'version': get_current_version()
        }

        backup_file = BACKUP_DIR / f"pre_deploy_{int(time.time())}.json"
        with open(backup_file, 'w') as f:
            json.dump(backup, f, indent=2)

        return backup_file

    def rollback(self, backup_file):
        """Execute rollback from backup"""
        with open(backup_file, 'r') as f:
            backup = json.load(f)

        # Restore queue states
        self._restore_queue_states(backup['queue_states'])

        # Restore configuration
        self._restore_config(backup['config'])

        log(f"Rollback completed from {backup['timestamp']}")
```

## 9. Conclusion

This design provides a comprehensive solution for queue monitoring and redistribution in the Kurultai system. The enhanced file-based approach offers the best balance of immediate impact, minimal risk, and clear benefits.

### Key Benefits
1. **Solves Critical Issue**: Addresses queue imbalance causing throughput bottlenecks
2. **Maintains Compatibility**: Works with existing task_intake.py and routing logic
3. **Quick Implementation**: Deployable in 1-2 weeks with immediate benefits
4. **Extensible Foundation**: Can be enhanced with Redis and advanced features later

### Success Criteria
- Queue variance < 20% between agents
- Redistribution latency < 5 seconds
- 40% improvement in system throughput
- Zero data loss during redistribution

The design is ready for implementation and will significantly improve the reliability and performance of the Kurultai multi-agent system.