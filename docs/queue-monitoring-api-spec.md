# Queue Monitoring API Specification

**Date:** 2026-03-08
**Author:** Kublai Agent
**Status:** Draft
**Version:** 1.0

## 1. Overview

This document specifies the API interfaces for the queue monitoring and redistribution system. The APIs are designed to integrate seamlessly with the existing task_intake.py routing logic while providing extensibility for future enhancements.

## 2. Core API Interfaces

### 2.1 Queue Monitoring API

#### `get_agent_queue_depth(agent: str) -> int`

**Description**: Get current queue depth for a specific agent

**Parameters**:
- `agent` (str): Agent name ('temujin', 'mongke', 'chagatai', 'jochi', 'ogedei', 'kublai', 'tolui')

**Returns**:
- `int`: Number of pending tasks in agent's queue

**Example**:
```python
depth = get_agent_queue_depth('ogedei')
# Returns: 11
```

#### `get_all_agent_queue_depths() -> Dict[str, int]`

**Description**: Get queue depths for all agents

**Returns**:
- `Dict[str, int]`: Mapping of agent names to queue depths

**Example**:
```python
depths = get_all_agent_queue_depths()
# Returns: {'temujin': 3, 'mongke': 1, 'chagatai': 0, 'jochi': 2, 'ogedei': 11, 'kublai': 0}
```

#### `get_agent_status(agent: str) -> Dict`

**Description**: Get comprehensive status for an agent

**Returns**:
- `Dict`: Agent status including queue depth, last activity, health metrics

**Example**:
```python
status = get_agent_status('ogedei')
# Returns: {
#     'queue_depth': 11,
#     'last_activity': '2026-03-08T01:00:00Z',
#     'health': 'OVERLOADED',
#     'oldest_task_age': 1800,
#     'active_tasks': 2
# }
```

### 2.2 Redistribution API

#### `redistribute_tasks(max_tasks: int = 10) -> List[Dict]`

**Description**: Execute task redistribution across agents

**Parameters**:
- `max_tasks` (int, optional): Maximum tasks to move per cycle (default: 10)

**Returns**:
- `List[Dict]`: List of executed redistribution operations

**Example**:
```python
moves = redistribute_tasks(max_tasks=5)
# Returns: [
#     {
#         'success': True,
#         'source_agent': 'ogedei',
#         'destination_agent': 'mongke',
#         'task_id': 'normal-1234567890-abcdef',
#         'task_title': 'Research competitor analysis',
#         'timestamp': '2026-03-08T01:00:00Z'
#     }
# ]
```

#### `get_redistribution_history(limit: int = 100) -> List[Dict]`

**Description**: Get redistribution history

**Parameters**:
- `limit` (int, optional): Maximum number of records to return (default: 100)

**Returns**:
- `List[Dict]`: Redistribution history with metadata

**Example**:
```python
history = get_redistribution_history(limit=10)
# Returns: [
#     {
#         'timestamp': '2026-03-08T01:00:00Z',
#         'moves_count': 3,
#         'agents_affected': ['ogedei', 'mongke'],
#         'success_rate': 1.0,
#         'trigger_reason': 'QUEUE_IMBALANCE'
#     }
# ]
```

#### `get_redistribution_stats() -> Dict`

**Description**: Get redistribution performance statistics

**Returns**:
- `Dict`: Statistics about redistribution operations

**Example**:
```python
stats = get_redistribution_stats()
# Returns: {
#     'total_moves': 150,
#     'success_rate': 0.95,
#     'average_latency': 3.2,
#     'last_redistribution': '2026-03-08T01:00:00Z',
#     'redistribution_count_24h': 24,
#     'tasks_moved_24h': 45
# }
```

### 2.3 Configuration API

#### `get_monitoring_config() -> Dict`

**Description**: Get current monitoring configuration

**Returns**:
- `Dict`: Monitoring configuration settings

**Example**:
```python
config = get_monitoring_config()
# Returns: {
#     'high_threshold': 3,
#     'low_threshold': 2,
#     'critical_threshold': 8,
#     'monitoring_interval': 60,
#     'redistribution_cooldown': 300,
#     'max_tasks_per_redistribution': 10,
#     'enable_auto_redistribution': True
# }
```

#### `update_monitoring_config(config: Dict) -> bool`

**Description**: Update monitoring configuration

**Parameters**:
- `config` (Dict): New configuration settings

**Returns**:
- `bool`: True if update successful, False otherwise

**Example**:
```python
new_config = {
    'high_threshold': 4,
    'redistribution_cooldown': 180
}
success = update_monitoring_config(new_config)
```

### 2.4 Metrics API

#### `get_system_metrics() -> Dict`

**Description**: Get comprehensive system metrics

**Returns**:
- `Dict`: Current system metrics

**Example**:
```python
metrics = get_system_metrics()
# Returns: {
#     'timestamp': '2026-03-08T01:00:00Z',
#     'queue_depths': {...},
#     'agent_status': {...},
#     'system_performance': {
#         'cpu_percent': 15.2,
#         'memory_percent': 45.6,
#         'disk_percent': 67.8
#     },
#     'redistribution_stats': {...},
#     'error_rates': {...}
# }
```

#### `get_metrics_history(hours: int = 24) -> List[Dict]`

**Description**: Get historical metrics

**Parameters**:
- `hours` (int): Number of hours of history to retrieve (default: 24)

**Returns**:
- `List[Dict]**: Historical metrics records

**Example**:
```python
history = get_metrics_history(hours=1)
# Returns: [
#     {
#         'timestamp': '2026-03-08T00:59:00Z',
#         'queue_depths': {...},
#         'system_performance': {...}
#     },
#     {
#         'timestamp': '2026-03-08T00:58:00Z',
#         'queue_depths': {...},
#         'system_performance': {...}
#     }
# ]
```

### 2.5 Alerting API

#### `get_active_alerts() -> List[Dict]`

**Description**: Get currently active alerts

**Returns**:
- `List[Dict]`: List of active alerts

**Example**:
```python
alerts = get_active_alerts()
# Returns: [
#     {
#         'id': 'alert_123',
#         'type': 'QUEUE_IMBALANCE',
#         'severity': 'HIGH',
#         'message': 'ogedei has 11 tasks while mongke has 1',
#         'timestamp': '2026-03-08T01:00:00Z',
#         'agents_affected': ['ogedei', 'mongke']
#     }
# ]
```

#### `acknowledge_alert(alert_id: str) -> bool`

**Description**: Acknowledge and close an alert

**Parameters**:
- `alert_id` (str): Alert identifier

**Returns**:
- `bool`: True if acknowledgment successful

**Example**:
```python
success = acknowledge_alert('alert_123')
```

#### `test_alert_configuration() -> Dict`

**Description**: Test alert configuration

**Returns**:
- `Dict**: Test results for all alert channels

**Example**:
```python
test_results = test_alert_configuration()
# Returns: {
#     'slack': {'success': True, 'response_time': 0.5},
#     'email': {'success': True, 'response_time': 2.1},
#     'pagerduty': {'success': False, 'error': 'Authentication failed'}
# }
```

## 3. Integration Interfaces

### 3.1 Task Intake Integration

#### `create_task_with_monitoring(title: str, body: str, agent: str = None, **kwargs) -> str`

**Description**: Create task with queue-aware routing

**Parameters**:
- `title` (str): Task title
- `body` (str): Task description
- `agent` (str, optional): Target agent (if None, auto-route)
- `kwargs**: Additional options (enable_queue_balancing=True, etc.)

**Returns**:
- `str**: Task ID

**Example**:
```python
task_id = create_task_with_monitoring(
    title="Research market trends",
    body="Analyze competitor landscape for Q1 2026",
    enable_queue_balancing=True
)
```

#### `route_task_with_queue_awareness(title: str, body: str) -> Tuple[str, str]`

**Description**: Route task considering queue depths

**Parameters**:
- `title` (str): Task title
- `body` (str): Task description

**Returns**:
- `Tuple[str, str]`: (agent_name, routing_reason)

**Example**:
```python
agent, reason = route_task_with_queue_awareness(
    title="Fix authentication bug",
    body="Users cannot login, investigate and fix"
)
# Returns: ('jochi', 'Queue balancing: jochi has capability for debugging and current queue depth=2 < threshold=3')
```

### 3.2 Event Callback Interface

#### `register_queue_callback(callback: Callable) -> str`

**Description**: Register callback for queue state changes

**Parameters**:
- `callback` (Callable): Callback function

**Returns**:
- `str`: Callback registration ID

**Callback Signature**:
```python
def queue_state_changed(depths: Dict[str, int], changes: Dict[str, int]):
    """
    Called when queue state changes

    Args:
        depths: Current queue depths
        changes: Changes since last callback (agent -> delta)
    """
    pass
```

#### `unregister_queue_callback(callback_id: str) -> bool`

**Description**: Unregister queue callback

**Parameters**:
- `callback_id` (str): Registration ID from register_queue_callback

**Returns**:
- `bool`: True if successful

## 4. Data Structures

### 4.1 Task Move Structure

```python
{
    'task_id': 'string',
    'source_agent': 'string',
    'destination_agent': 'string',
    'task_title': 'string',
    'task_priority': 'high|normal|low',
    'timestamp': 'ISO 8601 timestamp',
    'success': boolean,
    'error': 'string|null'
}
```

### 4.2 Agent Status Structure

```python
{
    'agent': 'string',
    'queue_depth': int,
    'health': 'HEALTHY|OVERLOADED|UNDERUTILIZED|CRITICAL',
    'last_activity': 'ISO 8601 timestamp',
    'oldest_task_age': int,  # seconds
    'active_tasks': int,
    'success_rate': float,  # 0.0 to 1.0
    'error_count': int
}
```

### 4.3 Alert Structure

```python
{
    'id': 'string',
    'type': 'QUEUE_IMBALANCE|AGENT_DOWN|SYSTEM_OVERLOAD|STUCK_TASK',
    'severity': 'LOW|MEDIUM|HIGH|CRITICAL',
    'message': 'string',
    'timestamp': 'ISO 8601 timestamp',
    'agents_affected': ['string'],
    'metrics': {},
    'acknowledged': boolean,
    'acknowledged_by': 'string|null',
    'acknowledged_at': 'ISO 8601 timestamp|null'
}
```

## 5. Error Handling

### 5.1 Error Codes

| Code | Description |
|------|-------------|
| AGENT_NOT_FOUND | Specified agent does not exist |
| QUEUE_ACCESS_ERROR | Cannot access agent queue directory |
| REDISTRIBUTION_FAILED | Redistribution operation failed |
| CONFIG_UPDATE_FAILED | Configuration update failed |
| METRICS_UNAVAILABLE | Metrics service unavailable |
| ALERT_DELIVERY_FAILED | Alert delivery failed |

### 5.2 Error Response Format

```python
{
    'error': {
        'code': 'AGENT_NOT_FOUND',
        'message': 'Agent xyz not found in valid agents list',
        'details': {},
        'timestamp': 'ISO 8601 timestamp'
    }
}
```

## 6. Authentication and Authorization

### 6.1 API Access

All APIs require authentication via:
- API key in headers
- Service-to-service token validation

### 6.2 Authorization Levels

1. **Monitor Level**: Read-only access to metrics and status
2. **Operator Level**: Read/write access to monitoring and redistribution
3. **Admin Level**: Full access including configuration changes

## 7. Rate Limiting

### 7.1 API Rate Limits

| Endpoint | Requests/minute | Burst |
|----------|----------------|-------|
| Queue depth APIs | 60 | 10 |
| Red APIs | 30 | 5 |
| Config APIs | 10 | 3 |
| Alert APIs | 100 | 20 |

### 7.2 Rate Limit Response

```http
HTTP 429 Too Many Requests
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1642700000
```

## 8. Webhook Integration

### 8.1 Webhook Payload Format

```json
{
    "event": "queue_imbalance",
    "timestamp": "2026-03-08T01:00:00Z",
    "data": {
        "overloaded_agents": ["ogedei"],
        "underutilized_agents": ["mongke"],
        "max_depth": 11,
        "min_depth": 1,
        "variance": 0.9
    }
}
```

### 8.2 Webhook Registration

```python
register_webhook(
    url="https://your-service.com/webhooks",
    events=["queue_imbalance", "redistribution", "alert"],
    filters={"severity": ["HIGH", "CRITICAL"]}
)
```

## 9. Testing API

### 9.1 Mock Data API

For testing purposes:

```python
# Generate mock queue state
generate_mock_queue_state({
    'temujin': 3,
    'ogedei': 10,
    'mongke': 1
})

# Test redistribution with mock data
test_redistribution_scenario('overloaded_scenario')
```

### 9.2 Performance Testing API

```python
# Benchmark queue depth calculation
benchmark_queue_depth_calculation(iterations=1000)

# Benchmark redistribution performance
benchmark_redistribution(task_counts=[10, 50, 100, 500])
```

## 10. Versioning

### 10.1 API Versioning

All endpoints support versioning via:
- URL path: `/api/v1/queue/depth`
- Accept header: `Accept: application/vnd.kurultai.v1+json`

### 10.2 Version Compatibility

- Current version: v1
- Supported versions: v1
- Deprecation policy: 6 months notice for major version changes

## 11. Documentation

### 11.1 OpenAPI Specification

The complete API specification is available in OpenAPI 3.0 format at:
`/docs/api/queue-monitoring.yaml`

### 11.2 Interactive Documentation

Interactive API documentation available at:
`/docs/api/queue-monitoring`

## 12. Support

For API support or questions:
- Email: ops@kurultai.ai
- Slack: #queue-monitoring channel
- Issue tracker: GitHub repository issues