# Agent Teams Integration Analysis for Horde Skills

## Executive Summary

This document analyzes technical approaches for integrating Claude Code Agent SDK "agent teams" (peer-to-peer messaging between specialized agents) into the existing horde skills ecosystem (horde-test, horde-implement, horde-plan, horde-swarm, horde-brainstorming).

**Current State**: Horde skills use `Task()` subagent dispatch with a controller agent orchestrating everything through the `DelegationProtocol`.

**Proposed Enhancement**: Agent teams would allow subagents to communicate directly with each other, reducing controller bottleneck and enabling emergent collaboration patterns.

---

## 1. Architectural Patterns for Agent Team Integration

### Pattern 1: Hub-and-Spoke with Message Router (Recommended)

In this pattern, a lightweight message router facilitates peer-to-peer communication while maintaining oversight.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HUB-AND-SPOKE WITH MESSAGE ROUTER                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      MESSAGE ROUTER (Lightweight)                  │   │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│   │  │ Inbound Queue│  │  State Store │  │ Outbound     │              │   │
│   │  │ (per agent)  │  │  (Redis)     │  │ Dispatcher   │              │   │
│   │  └──────────────┘  └──────────────┘  └──────────────┘              │   │
│   └──────────┬──────────────────────────────────────────────────────────┘   │
│              │                                                               │
│       ┌──────┴──────┬──────────────┬──────────────┐                         │
│       │             │              │              │                         │
│       ▼             ▼              ▼              ▼                         │
│   ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐                        │
│   │ Agent  │◀─▶│ Agent  │◀─▶│ Agent  │◀─▶│ Agent  │                        │
│   │   A    │   │   B    │   │   C    │   │   D    │                        │
│   │(Tester)│   │(Tester)│   │(Fixer) │   │(Review)│                        │
│   └────┬───┘   └────┬───┘   └────┬───┘   └────┬───┘                        │
│        │            │            │            │                             │
│        └────────────┴────────────┴────────────┘                             │
│                     Peer-to-Peer Messages                                   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    CONTROLLER (Orchestrator)                       │   │
│   │  - Spawns teams                                                    │   │
│   │  - Monitors progress via router                                    │   │
│   │  - Handles failures/escalations                                    │   │
│   │  - Aggregates final results                                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Implementation Sketch**:

```python
class MessageRouter:
    """Lightweight message router for agent teams."""

    def __init__(self, state_store: Redis):
        self.state = state_store
        self.agent_queues: Dict[str, asyncio.Queue] = {}

    async def register_agent(self, agent_id: str, team_id: str):
        """Register an agent to the router."""
        self.agent_queues[agent_id] = asyncio.Queue()
        await self.state.hset(f"team:{team_id}:agents", agent_id, "active")

    async def send_message(
        self,
        from_agent: str,
        to_agent: str,
        message_type: str,
        payload: Dict[str, Any]
    ):
        """Route message between agents."""
        message = {
            "id": str(uuid.uuid4()),
            "from": from_agent,
            "to": to_agent,
            "type": message_type,  # "request", "response", "broadcast", "blocker"
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "team_id": self._get_team_id(from_agent)
        }

        # Store in state for persistence/durability
        await self.state.lpush(
            f"team:{message['team_id']}:messages",
            json.dumps(message)
        )

        # Deliver to recipient queue
        if to_agent in self.agent_queues:
            await self.agent_queues[to_agent].put(message)

    async def broadcast(
        self,
        from_agent: str,
        message_type: str,
        payload: Dict[str, Any]
    ):
        """Broadcast to all team members."""
        team_id = self._get_team_id(from_agent)
        agents = await self.state.hkeys(f"team:{team_id}:agents")

        for agent in agents:
            if agent != from_agent:
                await self.send_message(from_agent, agent, message_type, payload)


class TeamAgent:
    """Base class for agents participating in a team."""

    def __init__(self, agent_id: str, router: MessageRouter):
        self.agent_id = agent_id
        self.router = router
        self.message_handlers: Dict[str, Callable] = {}

    async def send_to_peer(
        self,
        peer_id: str,
        message_type: str,
        payload: Dict[str, Any]
    ):
        """Send message to peer agent."""
        await self.router.send_message(
            self.agent_id, peer_id, message_type, payload
        )

    async def broadcast(
        self,
        message_type: str,
        payload: Dict[str, Any]
    ):
        """Broadcast to all team members."""
        await self.router.broadcast(self.agent_id, message_type, payload)

    async def run(self):
        """Main message loop."""
        queue = self.router.agent_queues[self.agent_id]

        while True:
            message = await queue.get()

            handler = self.message_handlers.get(message["type"])
            if handler:
                await handler(message)
```

---

### Pattern 2: Shared State with Event Bus

In this pattern, agents communicate through a shared state store and event bus, enabling loose coupling and better observability.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SHARED STATE WITH EVENT BUS                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      SHARED STATE (Neo4j/Redis)                    │   │
│   │                                                                      │   │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│   │  │ Agent States │  │ Shared       │  │ Results      │              │   │
│   │  │ (progress)   │  │ Context      │  │ Cache        │              │   │
│   │  └──────────────┘  └──────────────┘  └──────────────┘              │   │
│   │                                                                      │   │
│   └───────────────────────────┬─────────────────────────────────────────┘   │
│                               │                                              │
│                               ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      EVENT BUS (Redis Pub/Sub)                     │   │
│   │                                                                      │   │
│   │   Topics:                                                            │   │
│   │   - team:{id}:blocker     (urgent issues)                           │   │
│   │   - team:{id}:progress    (status updates)                          │   │
│   │   - team:{id}:discovery   (new findings)                            │   │
│   │   - team:{id}:complete    (task finished)                           │   │
│   │                                                                      │   │
│   └──────────┬──────────────────────────────┬───────────────────────────┘   │
│              │                              │                                │
│       ┌──────┴──────┐                ┌──────┴──────┐                        │
│       │             │                │             │                        │
│       ▼             ▼                ▼             ▼                        │
│   ┌────────┐   ┌────────┐       ┌────────┐   ┌────────┐                    │
│   │ Agent  │   │ Agent  │       │ Agent  │   │ Agent  │                    │
│   │   A    │   │   B    │       │   C    │   │   D    │                    │
│   └────────┘   └────────┘       └────────┘   └────────┘                    │
│                                                                              │
│   Communication: Subscribe to topics, publish events                         │
│   Coordination: Shared state reads/writes                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Implementation Sketch**:

```python
class TeamEventBus:
    """Event bus for agent team communication."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)

    async def publish(
        self,
        team_id: str,
        event_type: str,
        payload: Dict[str, Any],
        from_agent: str
    ):
        """Publish event to team channel."""
        event = {
            "id": str(uuid.uuid4()),
            "team_id": team_id,
            "type": event_type,
            "from": from_agent,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        channel = f"team:{team_id}:{event_type}"
        await self.redis.publish(channel, json.dumps(event))

        # Also persist for late joiners
        await self.redis.lpush(
            f"team:{team_id}:events",
            json.dumps(event)
        )

    async def subscribe(
        self,
        team_id: str,
        event_types: List[str],
        handler: Callable
    ):
        """Subscribe to team events."""
        for event_type in event_types:
            channel = f"team:{team_id}:{event_type}"
            self.subscribers[channel].append(handler)

        # Start listener task
        asyncio.create_task(self._listener(team_id, event_types))

    async def _listener(self, team_id: str, event_types: List[str]):
        """Background listener for events."""
        pubsub = self.redis.pubsub()

        channels = [f"team:{team_id}:{et}" for et in event_types]
        await pubsub.subscribe(*channels)

        async for message in pubsub.listen():
            if message["type"] == "message":
                event = json.loads(message["data"])
                channel = message["channel"].decode()

                for handler in self.subscribers.get(channel, []):
                    asyncio.create_task(handler(event))


class SharedStateManager:
    """Manages shared state for agent teams."""

    def __init__(self, neo4j_client, redis_client):
        self.neo4j = neo4j_client
        self.redis = redis_client

    async def write_agent_state(
        self,
        team_id: str,
        agent_id: str,
        state: Dict[str, Any]
    ):
        """Write agent state to shared store."""
        # Write to Redis for speed
        await self.redis.hset(
            f"team:{team_id}:agent_states",
            agent_id,
            json.dumps(state)
        )

        # Persist to Neo4j for durability
        query = """
        MATCH (t:Team {id: $team_id})
        MERGE (a:AgentState {team_id: $team_id, agent_id: $agent_id})
        SET a.state = $state,
            a.updated_at = datetime()
        CREATE (t)-[:HAS_AGENT_STATE]->(a)
        """
        await self.neo4j.run(query, {
            "team_id": team_id,
            "agent_id": agent_id,
            "state": json.dumps(state)
        })

    async def read_team_state(self, team_id: str) -> Dict[str, Dict]:
        """Read all agent states for a team."""
        states = await self.redis.hgetall(f"team:{team_id}:agent_states")
        return {
            agent_id: json.loads(state)
            for agent_id, state in states.items()
        }
```

---

### Pattern 3: Direct WebSocket Mesh

In this pattern, agents establish direct WebSocket connections with each other, minimizing latency for real-time collaboration.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DIRECT WEBSOCKET MESH                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌────────┐         WebSocket          ┌────────┐                         │
│   │ Agent  │◀──────────────────────────▶│ Agent  │                         │
│   │   A    │         (direct)           │   B    │                         │
│   │(Tester)│                            │(Tester)│                         │
│   └───┬────┘                            └────┬───┘                         │
│       │                                       │                              │
│       │         ┌────────┐                    │                              │
│       └────────▶│ Agent  │◀───────────────────┘                              │
│       (mesh)    │   C    │    (mesh)                                        │
│                 │(Fixer) │                                                   │
│                 └───┬────┘                                                   │
│                     │                                                        │
│                     │  WebSocket                                             │
│                     ▼  (direct)                                              │
│                 ┌────────┐                                                   │
│                 │ Agent  │                                                   │
│                 │   D    │                                                   │
│                 │(Review)│                                                   │
│                 └────────┘                                                   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    SIGNALING SERVER (WebRTC-style)                 │   │
│   │  - Helps agents discover each other                                │   │
│   │  - Handles NAT traversal (if needed)                               │   │
│   │  - Not in message path                                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Implementation Sketch**:

```python
class MeshAgent:
    """Agent that participates in a WebSocket mesh."""

    def __init__(self, agent_id: str, signaling_server: str):
        self.agent_id = agent_id
        self.signaling = signaling_server
        self.peers: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.message_queue = asyncio.Queue()

    async def join_team(self, team_id: str):
        """Join a team mesh."""
        # Connect to signaling server
        async with websockets.connect(self.signaling) as ws:
            # Register with team
            await ws.send(json.dumps({
                "type": "join",
                "agent_id": self.agent_id,
                "team_id": team_id
            }))

            # Receive peer list
            response = await ws.recv()
            peers = json.loads(response)["peers"]

            # Connect to each peer
            for peer in peers:
                asyncio.create_task(self._connect_to_peer(peer))

            # Listen for new peers
            async for message in ws:
                data = json.loads(message)
                if data["type"] == "peer_joined":
                    asyncio.create_task(
                        self._connect_to_peer(data["peer_info"])
                    )

    async def _connect_to_peer(self, peer_info: Dict):
        """Establish direct WebSocket to peer."""
        ws = await websockets.connect(peer_info["endpoint"])
        self.peers[peer_info["agent_id"]] = ws

        # Start message handler
        asyncio.create_task(self._handle_peer_messages(peer_info["agent_id"], ws))

    async def send_to_peer(self, peer_id: str, message: Dict):
        """Send message directly to peer."""
        if peer_id in self.peers:
            await self.peers[peer_id].send(json.dumps(message))

    async def broadcast(self, message: Dict):
        """Broadcast to all peers."""
        for peer_id, ws in self.peers.items():
            await ws.send(json.dumps(message))
```

---

## 2. Trade-offs Analysis

### Pattern Comparison Matrix

| Dimension | Hub-and-Spoke Router | Shared State/Event Bus | Direct WebSocket Mesh |
|-----------|---------------------|------------------------|----------------------|
| **Complexity** | Medium | Medium-High | High |
| **Latency** | Low (1 hop) | Low-Medium | Very Low (direct) |
| **Reliability** | High (centralized) | High (persistent) | Medium (P2P) |
| **Scalability** | Good (to ~50 agents) | Excellent | Poor (mesh complexity) |
| **Observability** | Excellent | Excellent | Poor |
| **Cost** | Medium | Medium | Low (no router infra) |
| **Failure Recovery** | Easy | Easy | Hard |
| **Implementation Time** | 2-3 weeks | 3-4 weeks | 4-6 weeks |

### Detailed Trade-offs

#### Pattern 1: Hub-and-Spoke Router

**Pros**:
- Simple mental model - router is the single source of truth
- Easy to add monitoring, logging, and debugging
- Can enforce message schemas and validation
- Simple failure recovery - router can reassign work
- Works well with existing horde-swarm patterns

**Cons**:
- Router is a single point of failure (mitigated by clustering)
- Message latency includes router hop
- Router can become bottleneck at very high throughput
- Requires maintaining router infrastructure

**Best For**: Most horde skill use cases, especially when observability and reliability are priorities.

---

#### Pattern 2: Shared State/Event Bus

**Pros**:
- Loose coupling - agents don't need to know about each other
- Excellent for complex coordination patterns
- Natural fit with Neo4j/Redis already in use
- Easy to add new agents without reconfiguration
- Great audit trail via event log

**Cons**:
- Eventual consistency can cause race conditions
- More complex to debug (distributed state)
- Higher storage costs for event persistence
- Learning curve for event-driven programming

**Best For**: Complex multi-phase workflows where agents need to react to state changes (e.g., horde-implement with iterative refinement).

---

#### Pattern 3: Direct WebSocket Mesh

**Pros**:
- Lowest latency - direct agent-to-agent communication
- No infrastructure bottleneck
- Natural for real-time collaboration
- Maximum privacy (no intermediary)

**Cons**:
- Complex to implement and debug
- Does not scale well (O(n^2) connections)
- Hard to monitor and observe
- Difficult failure recovery
- NAT/firewall traversal complexity

**Best For**: Small teams (2-4 agents) with real-time collaboration needs, not recommended for general horde skills.

---

## 3. Integration with Existing Horde Skill Patterns

### Current Pattern (Controller-Centric)

```python
# Current horde-test pattern
class HordeTestSkill:
    async def execute(self, test_plan: TestPlan):
        # Controller dispatches all tasks
        tasks = []
        for test_type in test_plan.test_types:
            task = Task(
                subagent_type=f"testing:{test_type}-tester",
                prompt=build_prompt(test_type),
                expected_output={...}
            )
            tasks.append(task)

        # Wait for all results
        results = await self.swarm.dispatch_parallel(tasks)

        # Controller aggregates
        return self.aggregator.aggregate(results)
```

### Proposed Integration (Agent Teams)

```python
# Enhanced horde-test with agent teams
class HordeTestSkillWithTeams:
    def __init__(self):
        self.swarm = Swarm()
        self.router = MessageRouter()  # NEW
        self.team_factory = TeamFactory()  # NEW

    async def execute(self, test_plan: TestPlan):
        # Create team for this test run
        team = await self.team_factory.create_team(
            team_type="testing",
            size=len(test_plan.test_types) + 1,  # testers + coordinator
            router=self.router
        )

        # Spawn agents with peer communication capability
        agents = []
        for test_type in test_plan.test_types:
            agent = TestAgent(  # NEW: agents can talk to peers
                agent_id=f"{test_type}-tester",
                router=self.router,
                team_id=team.id
            )
            agents.append(agent)

        # Add coordinator agent
        coordinator = TestCoordinatorAgent(
            agent_id="test-coordinator",
            router=self.router,
            team_id=team.id
        )
        agents.append(coordinator)

        # Start all agents
        await team.start_agents(agents)

        # Agents communicate peer-to-peer during execution
        # Coordinator monitors and intervenes only when needed
        results = await team.wait_for_completion()

        return results
```

### Hybrid Approach (Recommended)

```python
class HybridHordeSkill:
    """
    Uses controller for orchestration but enables
    peer communication for specific collaboration patterns.
    """

    async def execute(self, test_plan: TestPlan):
        # Phase 1: Controller dispatches (existing pattern)
        teams = self.composer.compose_for_test_type(test_plan)

        # Phase 2: Enable peer communication within teams (new)
        for team in teams.values():
            await self.enable_team_collaboration(team)

        # Phase 3: Execute with peer communication
        results = await self.swarm.dispatch_with_teams(teams)

        # Phase 4: Controller aggregates (existing pattern)
        return self.aggregator.aggregate(results)

    async def enable_team_collaboration(self, team: AgentTeam):
        """Enable peer messaging for a team."""
        # Create message router for this team
        router = MessageRouter()

        # Inject router into each agent's context
        for agent in team.agents:
            agent.context["router"] = router
            agent.context["team_id"] = team.id
            agent.context["peers"] = [a.id for a in team.agents if a != agent]
```

---

## 4. Risks and Mitigation Strategies

### Risk 1: Message Storm / Cascade Failures

**Scenario**: One agent broadcasts a message that triggers responses from all peers, which trigger more responses...

**Mitigation**:
```python
class MessageThrottler:
    """Prevents message storms."""

    def __init__(self):
        self.message_counts: Dict[str, int] = defaultdict(int)
        self.last_reset = datetime.now()

    async def check_rate(self, agent_id: str, message_type: str) -> bool:
        key = f"{agent_id}:{message_type}"

        # Reset counters every minute
        if (datetime.now() - self.last_reset).seconds > 60:
            self.message_counts.clear()
            self.last_reset = datetime.now()

        self.message_counts[key] += 1

        # Limit: 30 messages per minute per message type
        if self.message_counts[key] > 30:
            logger.warning(f"Rate limit exceeded for {key}")
            return False

        return True
```

---

### Risk 2: State Inconsistency

**Scenario**: Two agents read shared state, both modify it, one overwrites the other's changes.

**Mitigation**:
```python
class OptimisticLocking:
    """Prevents lost updates."""

    async def update_state(
        self,
        team_id: str,
        agent_id: str,
        update_fn: Callable,
        expected_version: int
    ):
        """Update with optimistic locking."""
        async with self.redis.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(f"team:{team_id}:state_version")
                    current_version = int(await pipe.get(f"team:{team_id}:state_version") or 0)

                    if current_version != expected_version:
                        raise StateConflictError(
                            f"Expected version {expected_version}, got {current_version}"
                        )

                    pipe.multi()
                    new_state = update_fn()
                    pipe.set(f"team:{team_id}:state", json.dumps(new_state))
                    pipe.incr(f"team:{team_id}:state_version")
                    await pipe.execute()
                    break

                except redis.WatchError:
                    # Retry on conflict
                    continue
```

---

### Risk 3: Agent Failure During Collaboration

**Scenario**: Agent crashes while holding critical information or in the middle of a collaborative task.

**Mitigation**:
```python
class TeamFailureRecovery:
    """Handles agent failures in teams."""

    async def handle_agent_failure(self, team_id: str, failed_agent_id: str):
        """Recover from agent failure."""
        # 1. Get last known state
        state = await self.state_manager.get_agent_state(team_id, failed_agent_id)

        # 2. Check if work can be redistributed
        team = await self.get_team(team_id)
        remaining_agents = [a for a in team.agents if a.id != failed_agent_id]

        if state.get("work_in_progress"):
            # Redistribute incomplete work
            await self.redistribute_work(
                team_id=team_id,
                work=state["work_in_progress"],
                available_agents=remaining_agents
            )

        # 3. Spawn replacement if critical
        if state.get("role") == "critical":
            new_agent = await self.spawn_replacement(team_id, failed_agent_id)
            await new_agent.resume_from_state(state)

        # 4. Notify team
        await self.router.broadcast(
            team_id=team_id,
            from_agent="system",
            message_type="agent_replaced",
            payload={
                "failed_agent": failed_agent_id,
                "replacement": new_agent.id if state.get("role") == "critical" else None,
                "work_redistributed": bool(state.get("work_in_progress"))
            }
        )
```

---

### Risk 4: Cost Explosion

**Scenario**: Peer communication leads to excessive token usage as agents chat back and forth.

**Mitigation**:
```python
class CostGovernor:
    """Controls costs for agent teams."""

    def __init__(self, budget: float):
        self.budget = budget
        self.spent = 0.0
        self.message_costs: Dict[str, float] = {}

    async def approve_message(self, message: Dict) -> bool:
        """Check if message is within budget."""
        estimated_cost = self.estimate_message_cost(message)

        if self.spent + estimated_cost > self.budget:
            logger.error(f"Budget exceeded: {self.spent}/{self.budget}")
            return False

        # Check for expensive patterns
        if message["type"] == "broadcast" and len(message["payload"]) > 10000:
            logger.warning("Large broadcast detected, consider compression")

        return True

    def estimate_message_cost(self, message: Dict) -> float:
        """Estimate token cost of message."""
        # Rough estimate: 1 token per 4 characters
        payload_size = len(json.dumps(message["payload"]))
        return payload_size / 4 * 0.0001  # Approximate cost per token
```

---

## 5. When to Use Which Pattern

### Use Controller Pattern When:
- Task is simple (1-2 subagents)
- Strict ordering is required
- Full observability is critical
- Budget is tightly constrained
- Example: `horde-plan` for simple feature planning

### Use Agent Teams When:
- Multiple agents need to collaborate dynamically
- Problem benefits from emergent solutions
- Real-time coordination is needed
- Work can be parallelized with dependencies
- Example: `horde-test` with interdependent test types

### Decision Matrix

| Use Case | Controller | Agent Teams | Recommended |
|----------|-----------|-------------|-------------|
| Simple unit test generation | Low overhead | Unnecessary | **Controller** |
| Complex integration testing | Bottleneck | Enables parallel discovery | **Agent Teams** |
| Security audit | Sequential needed | Parallel exploration | **Hybrid** |
| Performance testing | Resource conflict | Coordination needed | **Agent Teams** |
| Documentation writing | Simple delegation | Overkill | **Controller** |
| Code review | Single reviewer | Multiple perspectives | **Agent Teams** |

---

## 6. Technology Recommendations

### Recommended Stack

```yaml
# Infrastructure
message_router: Redis Streams  # or RabbitMQ for higher scale
state_store: Neo4j + Redis     # Neo4j for graph, Redis for speed
observability: OpenTelemetry + Jaeger

# Libraries
python:
  - redis-py-cluster          # For message routing
  - websockets                # For real-time (if needed)
  - asyncio                   # Core concurrency
  - pydantic                  # Message schemas
  - structlog                 # Structured logging

monitoring:
  - prometheus                # Metrics
  - grafana                   # Dashboards
  - jaeger                    # Distributed tracing
```

### Implementation Phases

**Phase 1: Foundation (Week 1-2)**
- Implement MessageRouter with Redis
- Create TeamAgent base class
- Add basic message types (request, response, broadcast)

**Phase 2: Integration (Week 3-4)**
- Integrate with existing horde-swarm
- Add team composition logic
- Implement failure recovery

**Phase 3: Optimization (Week 5-6)**
- Add cost governance
- Implement observability
- Performance tuning

**Phase 4: Rollout (Week 7-8)**
- Migrate horde-test to use teams
- A/B test vs controller pattern
- Iterate based on results

---

## 7. Final Recommendation

### Recommended Approach: Hybrid Hub-and-Spoke

Use the **Hub-and-Spoke with Message Router** pattern with a hybrid execution model:

1. **Controller orchestrates** high-level phases (existing pattern)
2. **Agent teams collaborate** within phases (new capability)
3. **Message router** enables peer communication with oversight
4. **Fallback to controller** when teams fail

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary pattern | Hub-and-Spoke | Balance of simplicity and capability |
| State management | Redis + Neo4j | Speed + durability |
| Message format | JSON + Pydantic | Human-readable + validation |
| Failure handling | Controller fallback | Reliability |
| Cost control | Per-team budgets | Prevent runaway costs |
| Observability | Full message logging | Debuggability |

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Message latency | <50ms | Router hop time |
| Team formation time | <2s | From request to ready |
| Failure recovery | <5s | Detection to replacement |
| Cost overhead | <20% | vs controller pattern |
| Developer satisfaction | >4/5 | Ease of debugging |

---

## Appendix: Code Examples

### Example 1: Test Agent with Peer Communication

```python
class TestAgent(TeamAgent):
    """Agent that can run tests and collaborate with peers."""

    def __init__(self, agent_id: str, router: MessageRouter, test_type: str):
        super().__init__(agent_id, router)
        self.test_type = test_type
        self.results = []

        # Register message handlers
        self.message_handlers["request_help"] = self.handle_help_request
        self.message_handlers["share_finding"] = self.handle_shared_finding

    async def run_tests(self, test_plan: Dict):
        """Main test execution with peer collaboration."""
        for test in test_plan["tests"]:
            try:
                result = await self.execute_test(test)

                # If test fails, ask peers for help
                if result["status"] == "failed":
                    await self.broadcast(
                        message_type="share_finding",
                        payload={
                            "type": "test_failure",
                            "test": test["name"],
                            "error": result["error"],
                            "seeking_insights": True
                        }
                    )

                self.results.append(result)

            except Exception as e:
                # Request help from fixer agent
                await self.send_to_peer(
                    peer_id="fixer-agent",
                    message_type="request_help",
                    payload={
                        "test": test,
                        "error": str(e),
                        "requestor": self.agent_id
                    }
                )

    async def handle_shared_finding(self, message: Dict):
        """Handle findings shared by peers."""
        finding = message["payload"]

        if finding["type"] == "test_failure":
            # Check if we can provide insights
            if self.has_relevant_experience(finding["test"]):
                await self.send_to_peer(
                    peer_id=message["from"],
                    message_type="insight",
                    payload={
                        "original_failure": finding["test"],
                        "suggestion": self.generate_suggestion(finding)
                    }
                )
```

### Example 2: Integration with Existing horde-test

```python
async def run_tests_with_teams(test_plan: TestPlan) -> TestResults:
    """Run tests using agent teams for collaboration."""

    # Create message router
    router = MessageRouter(redis_client)

    # Create team of test agents
    team_id = f"test-team-{uuid.uuid4().hex[:8]}"

    agents = [
        TestAgent("unit-tester", router, "unit"),
        TestAgent("integration-tester", router, "integration"),
        TestAgent("security-tester", router, "security"),
        TestAgent("fixer", router, "fix"),  # Can fix failures
        TestAgent("coordinator", router, "coordination")
    ]

    # Register agents with router
    for agent in agents:
        await router.register_agent(agent.agent_id, team_id)

    # Start all agents
    tasks = [agent.run() for agent in agents]

    # Wait for completion with timeout
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks),
            timeout=test_plan.timeout_seconds
        )
    except asyncio.TimeoutError:
        logger.error("Test team timed out")
        # Trigger graceful shutdown
        await router.broadcast(
            from_agent="system",
            message_type="shutdown",
            payload={"reason": "timeout"}
        )

    # Collect results
    results = TestResults()
    for agent in agents:
        if hasattr(agent, 'results'):
            results.add_agent_results(agent.agent_id, agent.results)

    return results
```

---

*Document Version: 1.0*
*Date: 2026-02-05*
*Author: Backend System Architect*
