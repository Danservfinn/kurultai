# Agent Teams Integration with Horde Skills: Architectural Analysis

## Executive Summary

This document explores architectural approaches for integrating Claude Code Agent SDK "agent teams" (peer-to-peer messaging between specialized agents) into the existing horde skill ecosystem (horde-test, horde-implement, horde-plan, horde-brainstorm, horde-swarm).

**Current State**: Horde skills use Task() subagent dispatch with a controller agent orchestrating everything through centralized coordination.

**Proposed Evolution**: Enable peer-to-peer communication between subagents while maintaining controller oversight for coordination, error handling, and final synthesis.

---

## 1. Current Architecture: Controller-Centric Pattern

### 1.1 Existing Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     CURRENT HORDE ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐                                                            │
│  │   User       │                                                            │
│  │   Request    │                                                            │
│  └──────┬───────┘                                                            │
│         │                                                                    │
│         ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    CONTROLLER AGENT (Kublai)                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │   │
│  │  │ Task Queue  │  │  Scheduler  │  │  Monitor    │  │  Synthesizer│  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │   │
│  └────────┬─────────────────────────────────────────────────────────────┘   │
│           │                                                                  │
│           │  Task() dispatch                                                  │
│           ▼                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    SUBAGENT POOL (via Task SDK)                       │   │
│  │                                                                       │   │
│  │   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌────────┐ │   │
│  │   │Agent 1  │   │Agent 2  │   │Agent 3  │   │Agent 4  │   │Agent N │ │   │
│  │   │(Research│   │ (Code)  │   │(Analyze)│   │ (Test)  │   │  ...   │ │   │
│  │   └────┬────┘   └────┬────┘   └────┬────┘   └────┬────┘   └───┬────┘ │   │
│  │        │             │             │             │            │      │   │
│  │        └─────────────┴─────────────┴─────────────┴────────────┘      │   │
│  │                              NO DIRECT MESSAGING                      │   │
│  │                        (All communication via Controller)             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Current Implementation Pattern

```python
# Current horde-swarm pattern (from horde-test-architecture.md)
class TestDispatcher:
    """Dispatches tests to horde-swarm for parallel execution."""

    async def dispatch_wave(self, wave: TestWave, test_plan: ParsedTestPlan) -> List[TestResult]:
        tasks = []
        for test_id in wave.tests:
            test = self._get_test_by_id(test_plan, test_id)
            agent_type = self.AGENT_MAPPING.get(test.type, "testing:general-tester")

            # Create Task for horde-swarm - CONTROLLER DISPATCHES
            task = Task(
                subagent_type=agent_type,
                prompt=self._build_test_prompt(test, test_plan),
                timeout=test.timeout or 300,
                metadata={"test_id": test_id, "test_type": test.type}
            )
            tasks.append(task)

        # Execute in parallel via horde-swarm - CONTROLLER ORCHESTRATES
        results = await asyncio.gather(
            *[self._execute_with_retry(t) for t in tasks],
            return_exceptions=True
        )
        return results
```

### 1.3 Current Strengths

| Aspect | Benefit |
|--------|---------|
| **Simplicity** | Single point of coordination, easier to debug |
| **Control** | Controller has full visibility into all agent states |
| **Error Handling** | Centralized retry, fallback, and failure management |
| **Cost Tracking** | Easy to aggregate token usage across all agents |
| **State Management** | Single source of truth in controller memory/Neo4j |

### 1.4 Current Limitations

| Aspect | Limitation |
|--------|------------|
| **Latency** | All inter-agent communication routes through controller |
| **Scalability** | Controller becomes bottleneck with 10+ agents |
| **Flexibility** | Agents cannot adapt to peer outputs mid-execution |
| **Emergence** | No opportunity for peer-to-peer collaboration |
| **Bandwidth** | Controller context window limits information flow |

---

## 2. Proposed Architectures: Agent Team Integration

### 2.1 Pattern A: Hybrid Hub-and-Spoke with Peer Channels

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           PATTERN A: HYBRID HUB-AND-SPOKE WITH PEER CHANNELS                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    CONTROLLER AGENT (Orchestrator)                    │   │
│  │                                                                       │   │
│  │   Responsibilities:                                                   │   │
│  │   - High-level task decomposition                                     │   │
│  │   - Agent team composition                                            │   │
│  │   - Lifecycle management (start/stop/pause)                           │   │
│  │   - Final synthesis and user communication                            │   │
│  │   - Error escalation and recovery                                     │   │
│  │                                                                       │   │
│  └──────────────┬────────────────────────────────────────────────────────┘   │
│                 │                                                            │
│      ┌──────────┴──────────┐                                                 │
│      │   Control Plane     │  (Task assignment, status, heartbeats)         │
│      └──────────┬──────────┘                                                 │
│                 │                                                            │
│  ┌──────────────┼──────────────────────────────────────────────────────┐     │
│  │              ▼                                                       │     │
│  │  ┌────────────────────────────────────────────────────────────────┐  │     │
│  │  │              AGENT TEAM (Peer-to-Peer Enabled)                  │  │     │
│  │  │                                                                │  │     │
│  │  │   ┌─────────┐      ┌─────────┐      ┌─────────┐               │  │     │
│  │  │   │Agent A  │◄────►│Agent B  │◄────►│Agent C  │               │  │     │
│  │  │   │(Research│      │ (Code)  │      │(Analyze)│               │  │     │
│  │  │   └────┬────┘      └────┬────┘      └────┬────┘               │  │     │
│  │  │        │                │                │                     │  │     │
│  │  │        └────────────────┼────────────────┘                     │  │     │
│  │  │                         │                                      │  │     │
│  │  │        ┌────────────────┼────────────────┐                     │  │     │
│  │  │        ▼                ▼                ▼                     │  │     │
│  │  │   ┌─────────┐      ┌─────────┐      ┌─────────┐               │  │     │
│  │  │   │Agent D  │◄────►│Agent E  │◄────►│Agent F  │               │  │     │
│  │  │   │ (Test)  │      │(Review) │      │(Deploy) │               │  │     │
│  │  │   └─────────┘      └─────────┘      └─────────┘               │  │     │
│  │  │                                                                │  │     │
│  │  │   PEER MESSAGING: Direct agent-to-agent communication          │  │     │
│  │  │   - Shared context via message bus                              │  │     │
│  │  │   - Collaborative refinement                                    │  │     │
│  │  │   - Dynamic task handoff                                        │  │     │
│  │  └────────────────────────────────────────────────────────────────┘  │     │
│  │                                                                      │     │
│  └──────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Pattern A: Implementation Approach

```python
class HybridAgentTeam:
    """
    Hybrid architecture: Controller orchestrates, agents communicate peer-to-peer.
    """

    def __init__(self, controller: ControllerAgent, shared_bus: MessageBus):
        self.controller = controller
        self.bus = shared_bus
        self.agents: Dict[str, Agent] = {}

    async def execute_task(self, task: TaskSpecification) -> TaskResult:
        # Phase 1: Controller decomposes and assigns
        assignments = await self.controller.decompose_task(task)

        # Phase 2: Create shared context space
        shared_context = SharedContext(
            task_id=task.id,
            message_bus=self.bus,
            initial_state=assignments.initial_context
        )

        # Phase 3: Spawn agents with peer messaging capability
        agent_handles = []
        for assignment in assignments.agent_tasks:
            agent = await self._spawn_agent(
                agent_type=assignment.agent_type,
                initial_task=assignment.task,
                shared_context=shared_context,
                peer_addresses=self._get_peer_addresses(assignment.agent_id)
            )
            self.agents[assignment.agent_id] = agent
            agent_handles.append(agent)

        # Phase 4: Let agents collaborate (controller monitors)
        collaboration_result = await self._run_collaboration(
            agents=agent_handles,
            shared_context=shared_context,
            timeout=task.timeout
        )

        # Phase 5: Controller synthesizes final result
        return await self.controller.synthesize_result(
            task_id=task.id,
            agent_outputs=collaboration_result.outputs,
            shared_state=shared_context.final_state
        )

    async def _run_collaboration(
        self,
        agents: List[Agent],
        shared_context: SharedContext,
        timeout: int
    ) -> CollaborationResult:
        """Allow agents to collaborate with minimal controller involvement."""

        # Start all agents
        agent_tasks = [
            asyncio.create_task(agent.run_with_peers(shared_context))
            for agent in agents
        ]

        # Monitor for completion or escalation
        done, pending = await asyncio.wait(
            agent_tasks,
            timeout=timeout,
            return_when=asyncio.ALL_COMPLETED
        )

        # Cancel any pending tasks
        for task in pending:
            task.cancel()

        return CollaborationResult(
            outputs=[t.result() for t in done if not t.exception()],
            errors=[t.exception() for t in done if t.exception()],
            shared_state=shared_context.get_state()
        )
```

#### Pattern A: Trade-offs

| Pros | Cons |
|------|------|
| **Faster iteration** - Agents communicate directly without controller latency | **Complexity** - Two communication patterns to manage |
| **Emergent collaboration** - Agents can discover synergies dynamically | **Debugging** - Harder to trace message flows |
| **Controller offload** - Frees controller context window for synthesis | **Consistency** - Risk of divergent state across agents |
| **Backward compatible** - Can fall back to controller-only mode | **Coordination overhead** - Need consensus mechanisms |

---

### 2.2 Pattern B: Federated Agent Teams with Local Leaders

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           PATTERN B: FEDERATED TEAMS WITH LOCAL LEADERS                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    MASTER CONTROLLER (Kublai)                         │   │
│  │                    - Task decomposition                               │   │
│  │                    - Team composition                                 │   │
│  │                    - Cross-team coordination                          │   │
│  │                    - Final synthesis                                  │   │
│  └──────────────┬──────────────────────────────┬─────────────────────────┘   │
│                 │                              │                             │
│      ┌──────────┴──────────┐        ┌──────────┴──────────┐                 │
│      │   Team Alpha        │        │   Team Beta         │                 │
│      │   (Implementation)  │        │   (Testing)         │                 │
│      └──────────┬──────────┘        └──────────┬──────────┘                 │
│                 │                              │                             │
│  ┌──────────────┼────────────────┐  ┌──────────┼────────────────┐            │
│  │              ▼                │  │          ▼                │            │
│  │  ┌─────────────────────────┐  │  │  ┌─────────────────────────┐           │
│  │  │    LOCAL LEADER         │  │  │  │    LOCAL LEADER         │           │
│  │  │    (Senior Dev)         │  │  │  │    (Test Lead)          │           │
│  │  │                         │  │  │  │                         │           │
│  │  │  - Subtask assignment   │  │  │  │  - Test orchestration   │           │
│  │  │  - Peer coordination    │  │  │  │  - Result aggregation   │           │
│  │  │  - Local synthesis      │  │  │  │  - Quality gating       │           │
│  │  │  - Escalation to Master │  │  │  │  - Escalation to Master │           │
│  │  └───────────┬─────────────┘  │  │  └───────────┬─────────────┘           │
│  │              │                 │  │              │                         │
│  │  ┌───────────┼───────────┐    │  │  ┌───────────┼───────────┐             │
│  │  ▼           ▼           ▼    │  │  ▼           ▼           ▼             │
│  │ ┌────┐    ┌────┐    ┌────┐   │  │ ┌────┐    ┌────┐    ┌────┐            │
│  │ │Dev1│◄──►│Dev2│◄──►│Dev3│   │  │ │Test│◄──►│Perf│◄──►│Sec │            │
│  │ └────┘    └────┘    └────┘   │  │ │ 1  │    │Eng │    │Aud │            │
│  │                              │  │ └────┘    └────┘    └────┘            │
│  │  PEER MESSAGING WITHIN TEAM  │  │                                       │
│  └──────────────────────────────┘  └───────────────────────────────────────┘
│                                                                              │
│  COMMUNICATION PATTERNS:                                                     │
│  - Master ↔ Local Leaders: Control plane (task assignment, escalation)       │
│  - Local Leader ↔ Team Members: Command + peer messaging                     │
│  - Team Members ↔ Team Members: Peer-to-peer collaboration                   │
│  - Team Alpha ↔ Team Beta: Via Master Controller (or direct with permission) │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Pattern B: Implementation Approach

```python
class FederatedAgentTeam:
    """
    Federated architecture with local team leaders and peer messaging within teams.
    """

    def __init__(self, master_controller: MasterController):
        self.master = master_controller
        self.teams: Dict[str, AgentTeam] = {}

    async def execute_complex_task(self, task: ComplexTask) -> TaskResult:
        # Phase 1: Master decomposes into sub-team tasks
        team_assignments = await self.master.decompose_to_teams(task)

        # Phase 2: Create teams with local leaders
        for team_spec in team_assignments:
            team = await self._create_team(
                team_id=team_spec.team_id,
                leader_type=team_spec.leader_type,
                member_types=team_spec.member_types,
                shared_bus=MessageBus(namespace=team_spec.team_id)
            )
            self.teams[team_spec.team_id] = team

        # Phase 3: Execute teams (can be sequential or parallel)
        if team_assignments.has_dependencies:
            results = await self._execute_sequential_teams(team_assignments)
        else:
            results = await self._execute_parallel_teams(team_assignments)

        # Phase 4: Master synthesizes across teams
        return await self.master.synthesize_cross_team(results)

    async def _execute_parallel_teams(
        self,
        assignments: List[TeamAssignment]
    ) -> Dict[str, TeamResult]:
        """Execute multiple teams in parallel with cross-team messaging."""

        # Create inter-team message bridge for authorized communication
        bridge = InterTeamBridge(self.teams)

        # Start all teams
        team_tasks = [
            asyncio.create_task(
                self.teams[assignment.team_id].execute(
                    assignment.task,
                    cross_team_bridge=bridge
                )
            )
            for assignment in assignments
        ]

        # Wait for all teams to complete
        results = await asyncio.gather(*team_tasks, return_exceptions=True)

        return {
            assignment.team_id: result
            for assignment, result in zip(assignments, results)
        }


class AgentTeam:
    """A team of agents with a local leader and peer messaging."""

    def __init__(
        self,
        team_id: str,
        leader: LocalLeaderAgent,
        members: List[Agent],
        message_bus: MessageBus
    ):
        self.team_id = team_id
        self.leader = leader
        self.members = {m.agent_id: m for m in members}
        self.bus = message_bus

    async def execute(
        self,
        task: TeamTask,
        cross_team_bridge: Optional[InterTeamBridge] = None
    ) -> TeamResult:
        """Execute team task with local coordination and peer messaging."""

        # Leader decomposes into member assignments
        member_tasks = await self.leader.decompose_for_team(task)

        # Create shared team context
        team_context = TeamContext(
            task_id=task.id,
            message_bus=self.bus,
            cross_team_bridge=cross_team_bridge
        )

        # Leader coordinates member execution with peer messaging
        member_results = await self.leader.coordinate_members(
            member_tasks=member_tasks,
            members=self.members,
            context=team_context
        )

        # Leader synthesizes team output
        return await self.leader.synthesize_team_result(member_results)
```

#### Pattern B: Trade-offs

| Pros | Cons |
|------|------|
| **Hierarchical clarity** - Clear escalation paths | **More layers** - Additional latency through local leaders |
| **Scalable** - Master controller not overloaded | **Coordination complexity** - Inter-team dependencies |
| **Domain expertise** - Leaders specialize in team function | **Potential silos** - Teams may not share information well |
| **Fault isolation** - Team failures don't cascade | **Resource overhead** - More agents (leaders) involved |

---

### 2.3 Pattern C: Event-Driven Agent Mesh

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           PATTERN C: EVENT-DRIVEN AGENT MESH                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    EVENT BUS (Centralized but Lightweight)            │   │
│  │                                                                       │   │
│  │   Topics:                                                             │   │
│  │   - task.assigned        - result.completed                           │   │
│  │   - context.updated      - error.occurred                             │   │
│  │   - agent.discovered     - collaboration.requested                    │   │
│  │   - consensus.needed     - escalation.required                        │   │
│  │                                                                       │   │
│  └──────────────┬────────────────────────────────────────────────────────┘   │
│                 │                                                            │
│                 │ Pub/Sub                                                    │
│                 ▼                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    AGENT MESH (Decentralized)                         │   │
│  │                                                                       │   │
│  │   ┌─────────┐         ┌─────────┐         ┌─────────┐                │   │
│  │   │Agent A  │◄───────►│Agent B  │◄───────►│Agent C  │                │   │
│  │   │         │         │         │         │         │                │   │
│  │   │Subscribes:        │Subscribes:        │Subscribes:               │   │
│  │   │- task.research    │- task.code       │- task.test               │   │
│  │   │- context.data     │- context.schema  │- context.coverage        │   │
│  │   └────┬────┘         └────┬────┘         └────┬────┘                │   │
│  │        │                   │                   │                      │   │
│  │        │    Publishes:     │    Publishes:     │    Publishes:        │   │
│  │        │    research.done  │    code.complete  │    test.results      │   │
│  │        └───────────────────┼───────────────────┘                      │   │
│  │                            │                                          │   │
│  │   ┌─────────┐         ┌────┴────┐         ┌─────────┐                │   │
│  │   │Agent D  │◄───────►│Agent E  │◄───────►│Agent F  │                │   │
│  │   │(Synthesizer)      │(Monitor)│         │(Fallback)│               │   │
│  │   │         │         │         │         │         │                │   │
│  │   │Subscribes:        │Subscribes:        │Subscribes:               │   │
│  │   │- *.completed      │- *.heartbeat     │- error.*                 │   │
│  │   │- consensus.*      │- escalation.*    │- escalation.*            │   │
│  │   └────────────────────┴────────────────────┘                         │   │
│  │                                                                       │   │
│  │   AGENTS ARE AUTONOMOUS:                                              │   │
│  │   - React to events they care about                                   │   │
│  │   - Publish results when complete                                     │   │
│  │   - Request collaboration via events                                  │   │
│  │   - Self-organize based on task needs                                 │   │
│  │                                                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  CONTROLLER ROLE:                                                            │
│  - Initializes the event bus and agent mesh                                 │
│  - Injects initial task event                                               │
│  - Monitors for completion/error events                                     │
│  - Provides final synthesis (Agent D role or separate)                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Pattern C: Implementation Approach

```python
class EventDrivenAgentMesh:
    """
    Event-driven architecture where agents react to events and self-organize.
    """

    def __init__(self, event_bus: EventBus):
        self.bus = event_bus
        self.agents: Dict[str, EventDrivenAgent] = {}
        self.controller: Optional[MeshController] = None

    async def initialize_mesh(
        self,
        agent_specs: List[AgentSpec],
        controller_spec: ControllerSpec
    ):
        """Initialize the agent mesh with event subscriptions."""

        # Create controller
        self.controller = MeshController(
            agent_id="controller",
            event_bus=self.bus
        )
        await self.controller.subscribe_to([
            "task.completed",
            "task.failed",
            "escalation.required",
            "mesh.stabilize"
        ])

        # Create agents with their subscriptions
        for spec in agent_specs:
            agent = EventDrivenAgent(
                agent_id=spec.agent_id,
                agent_type=spec.agent_type,
                event_bus=self.bus,
                capabilities=spec.capabilities
            )

            # Subscribe to relevant events based on capabilities
            subscriptions = self._derive_subscriptions(spec)
            await agent.subscribe_to(subscriptions)

            self.agents[spec.agent_id] = agent

    async def execute_task(self, task: Task) -> TaskResult:
        """Execute by publishing initial task event and waiting for completion."""

        # Publish task to mesh
        await self.bus.publish(Event(
            topic="task.assigned",
            payload={
                "task_id": task.id,
                "description": task.description,
                "requirements": task.requirements,
                "priority": task.priority
            },
            sender="controller"
        ))

        # Wait for completion event
        completion = await self.bus.wait_for(
            topic="task.completed",
            filter=lambda e: e.payload["task_id"] == task.id,
            timeout=task.timeout
        )

        return TaskResult(
            task_id=task.id,
            output=completion.payload["result"],
            agent_path=completion.payload.get("agent_path", []),
            events=await self.bus.get_event_log(task.id)
        )


class EventDrivenAgent:
    """An agent that reacts to events and publishes results."""

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        event_bus: EventBus,
        capabilities: List[str]
    ):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.bus = event_bus
        self.capabilities = capabilities
        self.subscriptions: List[str] = []

    async def subscribe_to(self, topics: List[str]):
        """Subscribe to event topics."""
        self.subscriptions = topics
        for topic in topics:
            await self.bus.subscribe(topic, self._handle_event)

    async def _handle_event(self, event: Event):
        """Handle incoming events."""

        # Check if this agent can handle this event
        if not self._can_handle(event):
            return

        # Process the event
        if event.topic == "task.assigned":
            await self._handle_task_assignment(event)
        elif event.topic == "collaboration.requested":
            await self._handle_collaboration_request(event)
        elif event.topic == "context.updated":
            await self._handle_context_update(event)
        # ... etc

    async def _handle_task_assignment(self, event: Event):
        """Handle a task assignment event."""
        task = Task.from_event(event)

        # Check if we have the capabilities
        if not self._has_capabilities_for(task):
            # Decline by publishing unavailable event
            await self.bus.publish(Event(
                topic="agent.unavailable",
                payload={
                    "task_id": task.id,
                    "agent_id": self.agent_id,
                    "reason": "insufficient_capabilities"
                },
                sender=self.agent_id
            ))
            return

        # Execute task
        result = await self._execute_task(task)

        # Publish result
        await self.bus.publish(Event(
            topic="task.completed" if result.success else "task.failed",
            payload={
                "task_id": task.id,
                "agent_id": self.agent_id,
                "result": result.output,
                "agent_path": result.agent_path + [self.agent_id]
            },
            sender=self.agent_id
        ))

    async def request_collaboration(
        self,
        task_id: str,
        collaboration_type: str,
        context: Dict
    ):
        """Request collaboration from other agents."""
        await self.bus.publish(Event(
            topic="collaboration.requested",
            payload={
                "task_id": task_id,
                "requesting_agent": self.agent_id,
                "collaboration_type": collaboration_type,
                "context": context
            },
            sender=self.agent_id
        ))
```

#### Pattern C: Trade-offs

| Pros | Cons |
|------|------|
| **Maximum flexibility** - Agents self-organize | **Unpredictability** - Hard to predict execution paths |
| **Loose coupling** - Agents don't know about each other directly | **Debugging difficulty** - Event tracing is complex |
| **Highly scalable** - Easy to add new agents | **Potential for loops** - Event cycles possible |
| **Resilient** - Agent failures don't stop the mesh | **Event storm** - Can overwhelm with many events |
| **Natural load balancing** - Agents pick up work they can do | **Consensus challenges** - Harder to reach agreement |

---

## 3. Comparative Analysis

### 3.1 Architecture Comparison Matrix

| Criteria | Pattern A: Hybrid | Pattern B: Federated | Pattern C: Event Mesh |
|----------|-------------------|----------------------|----------------------|
| **Complexity** | Medium | High | Medium-High |
| **Latency** | Low (direct peer) | Medium (via leaders) | Low (async events) |
| **Scalability** | Good (10-20 agents) | Excellent (50+ agents) | Excellent (100+ agents) |
| **Debuggability** | Good | Good | Poor |
| **Fault Tolerance** | Good | Excellent | Excellent |
| **Cost Efficiency** | Good | Medium (more agents) | Good |
| **Implementation Effort** | Medium | High | Medium |
| **Integration with Existing** | Easy | Medium | Hard |

### 3.2 Use Case Fit Analysis

| Use Case | Best Pattern | Reasoning |
|----------|--------------|-----------|
| **horde-test** (testing workflows) | Pattern B | Clear team boundaries (unit, integration, e2e teams) |
| **horde-implement** (code generation) | Pattern A | Tight collaboration needed between dev agents |
| **horde-plan** (architecture planning) | Pattern C | Exploratory, many possible paths |
| **horde-brainstorm** (ideation) | Pattern C | Maximum creativity through emergent collaboration |
| **horde-swarm** (consensus) | Pattern A | Need controller for final synthesis |
| **horde-gate** (quality gates) | Pattern B | Sequential teams with clear handoffs |

---

## 4. Integration with Existing Horde Skills

### 4.1 Integration Strategy: Gradual Evolution

```
Phase 1: Controller Enhancement (Week 1-2)
├── Add peer messaging capability to existing Task() dispatch
├── Implement shared context store (Neo4j-backed)
└── Create agent discovery mechanism

Phase 2: Hybrid Mode (Week 3-4)
├── Enable peer channels for specific agent pairs
├── Controller still orchestrates but allows direct collaboration
└── Fallback to controller-only on errors

Phase 3: Full Peer Mode (Week 5-6)
├── Agents can self-organize within task boundaries
├── Controller monitors and intervenes only when needed
└── Synthesis still centralized

Phase 4: Optimization (Week 7-8)
├── Dynamic team formation
├── Cost-based routing decisions
└── Learning from collaboration patterns
```

### 4.2 Code Integration Example

```python
# Enhanced Task with peer messaging capability
class PeerEnabledTask(Task):
    """Task that supports peer-to-peer agent messaging."""

    def __init__(
        self,
        subagent_type: str,
        prompt: str,
        enable_peer_messaging: bool = True,
        peer_context_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(subagent_type=subagent_type, prompt=prompt, **kwargs)
        self.enable_peer_messaging = enable_peer_messaging
        self.peer_context_id = peer_context_id or str(uuid.uuid4())

# Enhanced dispatcher with peer support
class PeerEnabledDispatcher(TestDispatcher):
    """Dispatcher that enables peer messaging between test agents."""

    async def dispatch_wave_with_peers(
        self,
        wave: TestWave,
        test_plan: ParsedTestPlan,
        enable_collaboration: bool = True
    ) -> List[TestResult]:

        if not enable_collaboration:
            # Fall back to standard controller-only dispatch
            return await self.dispatch_wave(wave, test_plan)

        # Create shared context for this wave
        shared_context = await self._create_shared_context(
            wave_id=wave.id,
            test_plan=test_plan
        )

        # Create peer-enabled tasks
        tasks = []
        for test_id in wave.tests:
            test = self._get_test_by_id(test_plan, test_id)

            task = PeerEnabledTask(
                subagent_type=self.AGENT_MAPPING.get(test.type),
                prompt=self._build_peer_aware_prompt(test, shared_context),
                enable_peer_messaging=True,
                peer_context_id=shared_context.id,
                metadata={
                    "test_id": test_id,
                    "shared_context_url": shared_context.url,
                    "peer_discovery_endpoint": shared_context.discovery_url
                }
            )
            tasks.append(task)

        # Execute with peer collaboration window
        return await self._execute_with_peer_window(tasks, shared_context)

    async def _execute_with_peer_window(
        self,
        tasks: List[PeerEnabledTask],
        shared_context: SharedContext
    ) -> List[TestResult]:
        """
        Execute tasks with a window for peer collaboration.

        Agents can communicate via shared context during execution,
        but controller still manages lifecycle.
        """

        # Start collaboration window
        async with CollaborationWindow(shared_context) as window:
            # Execute all tasks
            futures = [
                self._execute_task_with_peer_access(task, window)
                for task in tasks
            ]

            # Wait for completion with timeout
            results = await asyncio.wait_for(
                asyncio.gather(*futures, return_exceptions=True),
                timeout=window.timeout
            )

            # Allow brief period for final peer sync
            await window.final_sync(duration_seconds=10)

        return results
```

---

## 5. Risk Analysis and Mitigation

### 5.1 Risk Matrix

| Risk | Likelihood | Impact | Mitigation Strategy |
|------|------------|--------|---------------------|
| **Message storms** | Medium | High | Rate limiting, backpressure, circuit breakers |
| **State divergence** | High | Medium | Event sourcing, periodic state reconciliation |
| **Agent loops** | Medium | High | Cycle detection, max message limits per agent |
| **Context overflow** | High | Medium | Context window management, compression, summarization |
| **Cost explosion** | Medium | High | Token budgets, cost-based routing, early termination |
| **Debugging complexity** | High | Medium | Structured logging, message tracing, replay capability |
| **Security/isolation** | Low | High | Message validation, sandboxing, authentication |
| **Controller bottleneck** | Medium | Medium | Load balancing, controller sharding |

### 5.2 Mitigation Implementation

```python
class AgentTeamSafetyLayer:
    """Safety mechanisms for agent team execution."""

    def __init__(self):
        self.rate_limiter = TokenBucketRateLimiter(
            requests_per_minute=100,
            burst_size=20
        )
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60
        )
        self.token_budget = TokenBudget(
            max_tokens_per_task=100000,
            warning_threshold=0.8
        )

    async def send_message(
        self,
        from_agent: str,
        to_agent: str,
        message: Message
    ) -> bool:
        """Send message with safety checks."""

        # Rate limiting
        if not await self.rate_limiter.allow(from_agent):
            logger.warning(f"Rate limit exceeded for {from_agent}")
            return False

        # Token budget check
        if not self.token_budget.can_accommodate(message.estimated_tokens):
            logger.warning("Token budget exhausted")
            return False

        # Circuit breaker
        if not self.circuit_breaker.can_execute():
            logger.error("Circuit breaker open - messaging suspended")
            return False

        try:
            # Send message
            await self._deliver_message(from_agent, to_agent, message)
            self.circuit_breaker.record_success()
            return True

        except Exception as e:
            self.circuit_breaker.record_failure()
            raise

    def detect_cycles(self, message_log: List[Message]) -> Optional[List[str]]:
        """Detect circular message patterns."""

        # Build message graph
        graph = nx.DiGraph()
        for msg in message_log:
            graph.add_edge(msg.from_agent, msg.to_agent, message_id=msg.id)

        # Detect cycles
        try:
            cycle = nx.find_cycle(graph)
            return [graph.nodes[n]['agent_id'] for n in cycle]
        except nx.NetworkXNoCycle:
            return None
```

---

## 6. Cost Analysis

### 6.1 Cost Model

```
COST COMPONENTS:

1. Controller Overhead (Fixed)
   - Task decomposition: ~2K tokens
   - Result synthesis: ~5K tokens per agent output
   - Monitoring/heartbeat: ~500 tokens per check

2. Agent Execution (Variable)
   - Base task execution: Varies by task complexity
   - Peer messaging overhead: ~500-1000 tokens per message
   - Context synchronization: ~1K tokens per sync

3. Infrastructure (Fixed)
   - Message bus: Negligible for in-process, ~$0.01/hour for managed
   - State store (Neo4j): ~$0.05/hour for small instance

COST COMPARISON (per 10-agent task):

| Pattern | Controller Tokens | Agent Tokens | Messaging Tokens | Total Est. |
|---------|-------------------|--------------|------------------|------------|
| Current (No peers) | 50K | 100K | 0 | 150K |
| Pattern A (Hybrid) | 30K | 100K | 20K | 150K |
| Pattern B (Federated) | 20K | 100K | 30K + leader 15K | 165K |
| Pattern C (Event Mesh) | 15K | 100K | 40K | 155K |

Note: Peer messaging can REDUCE total tokens if it prevents redundant work.
```

### 6.2 Cost Optimization Strategies

```python
class CostOptimizedAgentTeam:
    """Agent team with cost-aware routing and execution."""

    def __init__(self, budget: TokenBudget):
        self.budget = budget
        self.cost_tracker = CostTracker()

    async def should_use_peer_messaging(
        self,
        task: Task,
        agents: List[Agent]
    ) -> bool:
        """Decide whether peer messaging is cost-effective for this task."""

        # Estimate costs
        controller_only_cost = self._estimate_controller_only(task, agents)
        peer_messaging_cost = self._estimate_peer_messaging(task, agents)

        # Factor in expected quality improvement
        quality_boost = self._estimate_quality_boost(task, agents)

        # Decision: use peers if cost increase < 20% or quality boost > 30%
        cost_increase = (peer_messaging_cost - controller_only_cost) / controller_only_cost

        return cost_increase < 0.2 or quality_boost > 0.3

    def _estimate_peer_messaging(
        self,
        task: Task,
        agents: List[Agent]
    ) -> int:
        """Estimate token cost with peer messaging."""

        base_cost = sum(a.estimated_tokens for a in agents)

        # Peer messaging overhead
        expected_messages = len(agents) * 3  # Assume 3 messages per agent
        messaging_cost = expected_messages * 800  # 800 tokens per message avg

        # Reduced controller synthesis (agents pre-synthesize)
        reduced_synthesis = -10000  # Save ~10K tokens

        return base_cost + messaging_cost + reduced_synthesis
```

---

## 7. State Management Architecture

### 7.1 Shared State Patterns

```python
class AgentTeamStateManager:
    """Manages shared state across agent teams."""

    def __init__(self, backend: StateBackend):
        self.backend = backend

    async def create_shared_context(
        self,
        task_id: str,
        agents: List[str],
        initial_state: Dict
    ) -> SharedContext:
        """Create a shared context space for agent collaboration."""

        context = SharedContext(
            id=f"ctx-{task_id}",
            task_id=task_id,
            agents=agents,
            created_at=datetime.utcnow()
        )

        # Store initial state with conflict-free replicated data type (CRDT)
        await self.backend.store(
            key=context.id,
            value=CRDTDocument(initial_state),
            agents=agents
        )

        return context

    async def update_state(
        self,
        context_id: str,
        agent_id: str,
        updates: Dict
    ) -> StateUpdate:
        """
        Update shared state with automatic conflict resolution.

        Uses CRDTs to ensure all agents see consistent state eventually.
        """

        # Get current CRDT
        crdt = await self.backend.get(context_id)

        # Apply updates
        crdt.merge(agent_id, updates)

        # Store updated CRDT
        await self.backend.store(context_id, crdt)

        return StateUpdate(
            context_id=context_id,
            agent_id=agent_id,
            timestamp=datetime.utcnow(),
            changes=updates
        )

    async def subscribe_to_state(
        self,
        context_id: str,
        agent_id: str,
        callback: Callable
    ) -> Subscription:
        """Subscribe to state changes for real-time collaboration."""

        return await self.backend.subscribe(
            key=context_id,
            subscriber=agent_id,
            callback=callback
        )
```

### 7.2 State Consistency Model

```
CONSISTENCY LEVELS:

1. Eventual Consistency (Default)
   - Agents may see slightly different state temporarily
   - CRDTs ensure convergence
   - Best for: Brainstorming, exploratory tasks

2. Strong Consistency (Optional)
   - All agents see same state before proceeding
   - Requires consensus protocol
   - Best for: Critical decisions, financial calculations

3. Session Consistency
   - Each agent sees their own writes immediately
   - Other agents see writes eventually
   - Best for: Most collaborative tasks
```

---

## 8. Error Handling and Recovery

### 8.1 Failure Modes

```python
class AgentTeamFailureHandler:
    """Handles failures in agent teams."""

    FAILURE_MODES = {
        "agent_crash": {
            "description": "Agent process crashed or timed out",
            "recovery": "restart_agent",
            "impact": "local"
        },
        "message_loss": {
            "description": "Message not delivered to peer",
            "recovery": "retry_with_backoff",
            "impact": "local"
        },
        "state_divergence": {
            "description": "Agents have inconsistent state",
            "recovery": "state_reconciliation",
            "impact": "team"
        },
        "cascading_failure": {
            "description": "One failure causes others",
            "recovery": "circuit_breaker",
            "impact": "system"
        },
        "consensus_failure": {
            "description": "Agents cannot agree",
            "recovery": "escalate_to_controller",
            "impact": "team"
        }
    }

    async def handle_failure(
        self,
        failure: Failure,
        team: AgentTeam
    ) -> RecoveryResult:
        """Handle agent team failure with appropriate recovery."""

        mode = self.FAILURE_MODES.get(failure.type)

        if not mode:
            # Unknown failure type - escalate
            return await self._escalate_to_controller(failure, team)

        # Execute recovery strategy
        recovery_method = getattr(self, mode["recovery"])
        return await recovery_method(failure, team)

    async def restart_agent(
        self,
        failure: Failure,
        team: AgentTeam
    ) -> RecoveryResult:
        """Restart failed agent with state recovery."""

        # Get last known state
        last_state = await self.state_manager.get_agent_state(
            team.id,
            failure.agent_id
        )

        # Create new agent instance
        new_agent = await team.spawn_replacement(
            failed_agent_id=failure.agent_id,
            initial_state=last_state
        )

        # Notify peers of replacement
        await team.broadcast_agent_change(
            old_agent=failure.agent_id,
            new_agent=new_agent.id
        )

        return RecoveryResult(
            success=True,
            action="agent_replaced",
            new_agent_id=new_agent.id
        )

    async def escalate_to_controller(
        self,
        failure: Failure,
        team: AgentTeam
    ) -> RecoveryResult:
        """Escalate failure to controller for human decision."""

        # Capture full context
        context = await self._capture_team_context(team)

        # Notify controller
        await self.controller.escalate(
            failure=failure,
            team_context=context,
            options=[
                "restart_team",
                "continue_without_failed_agent",
                "abort_task",
                "manual_intervention"
            ]
        )

        return RecoveryResult(
            success=False,
            action="escalated",
            requires_human=True
        )
```

---

## 9. Recommended Approach

### 9.1 Recommendation: Pattern A (Hybrid Hub-and-Spoke) with Evolution Path

**Primary Recommendation**: Start with **Pattern A (Hybrid Hub-and-Spoke)** for the following reasons:

1. **Incremental adoption** - Can be added to existing horde skills without major refactoring
2. **Backward compatibility** - Easy fallback to controller-only mode
3. **Controlled complexity** - Peer messaging is optional and scoped
4. **Proven patterns** - Similar to successful multi-agent systems (Kubernetes, microservices)

### 9.2 Implementation Roadmap

```
MILESTONE 1: Foundation (2 weeks)
├── Implement shared context store (Neo4j-backed)
├── Add peer messaging capability to Task SDK wrapper
├── Create agent discovery service
└── Build basic safety layer (rate limiting, cycle detection)

MILESTONE 2: horde-test Integration (2 weeks)
├── Enable peer messaging for test agents within same suite
├── Implement test result sharing between related tests
├── Add collaborative failure analysis
└── Measure cost/quality impact

MILESTONE 3: horde-implement Integration (2 weeks)
├── Enable code review collaboration between dev agents
├── Implement shared code context
├── Add architectural decision consensus
└── Measure development velocity impact

MILESTONE 4: Generalization (2 weeks)
├── Extract reusable agent team framework
├── Add dynamic team formation
├── Implement cost-based routing
└── Documentation and examples

MILESTONE 5: Advanced Patterns (Optional, 4 weeks)
├── Evaluate Pattern B (Federated) for large-scale deployments
├── Evaluate Pattern C (Event Mesh) for exploratory tasks
├── Implement hybrid pattern selection
└── Performance optimization
```

### 9.3 Technology Recommendations

| Component | Recommendation | Rationale |
|-----------|----------------|-----------|
| **Message Bus** | Redis Pub/Sub or NATS | Fast, reliable, supports patterns A and B |
| **State Store** | Neo4j (existing) + Redis (cache) | Graph relationships, fast reads |
| **Serialization** | Protocol Buffers or MessagePack | Efficient, schema evolution |
| **Observability** | OpenTelemetry + Jaeger | Distributed tracing for debugging |
| **Safety** | Custom (rate limiting, circuit breakers) | Domain-specific requirements |

### 9.4 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Latency reduction** | 20-30% faster completion | Compare peer-enabled vs controller-only |
| **Quality improvement** | 15% better results | Human evaluation of outputs |
| **Cost increase** | <25% | Token usage comparison |
| **Adoption rate** | 80% of eligible tasks | Usage metrics |
| **Error rate** | <5% failure rate | Error tracking |
| **Debuggability** | <2 min to trace issue | Developer experience surveys |

---

## 10. Conclusion

Agent teams represent a natural evolution of the horde skill architecture, enabling more efficient and emergent collaboration between specialized agents. The recommended **Pattern A (Hybrid Hub-and-Spoke)** provides the best balance of:

- **Incremental adoption** - Works with existing horde skills
- **Flexibility** - Optional peer messaging where beneficial
- **Control** - Controller maintains oversight and can intervene
- **Safety** - Well-understood patterns with proven mitigation strategies

The key insight is that peer-to-peer messaging should be an **optimization**, not a fundamental architectural shift. The controller-centric pattern remains valid and preferred for many use cases, while agent teams provide enhanced capabilities for collaborative tasks.

---

## Appendix A: Code Examples

### A.1 Minimal Peer Messaging Implementation

```python
# Minimal implementation for quick experimentation

class SimplePeerChannel:
    """Simple in-memory peer messaging channel."""

    def __init__(self):
        self._queues: Dict[str, asyncio.Queue] = {}
        self._subscribers: Dict[str, List[str]] = {}

    async def register(self, agent_id: str):
        """Register an agent for peer messaging."""
        self._queues[agent_id] = asyncio.Queue()

    async def send(
        self,
        from_agent: str,
        to_agent: str,
        message: Dict
    ):
        """Send message to specific agent."""
        if to_agent not in self._queues:
            raise ValueError(f"Agent {to_agent} not registered")

        await self._queues[to_agent].put({
            "from": from_agent,
            "to": to_agent,
            "payload": message,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def broadcast(
        self,
        from_agent: str,
        topic: str,
        message: Dict
    ):
        """Broadcast message to topic subscribers."""
        subscribers = self._subscribers.get(topic, [])
        for agent_id in subscribers:
            await self.send(from_agent, agent_id, message)

    async def receive(
        self,
        agent_id: str,
        timeout: Optional[float] = None
    ) -> Optional[Dict]:
        """Receive message for agent."""
        if agent_id not in self._queues:
            return None

        try:
            return await asyncio.wait_for(
                self._queues[agent_id].get(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return None
```

### A.2 Integration with Existing DelegationProtocol

```python
# Integration with existing tools/delegation_protocol.py

class PeerEnabledDelegationProtocol(DelegationProtocol):
    """Delegation protocol with peer messaging support."""

    def __init__(
        self,
        memory: OperationalMemory,
        enable_peer_messaging: bool = True,
        **kwargs
    ):
        super().__init__(memory=memory, **kwargs)
        self.enable_peer_messaging = enable_peer_messaging
        self.peer_channels: Dict[str, SimplePeerChannel] = {}

    async def delegate_to_team(
        self,
        task_description: str,
        agent_types: List[str],
        context: Dict[str, Any]
    ) -> TeamDelegationResult:
        """Delegate to a team of agents with peer messaging."""

        # Create shared channel for this team
        channel_id = str(uuid.uuid4())
        channel = SimplePeerChannel()
        self.peer_channels[channel_id] = channel

        # Register all agents
        for agent_type in agent_types:
            await channel.register(agent_type)

        # Create peer-enabled delegations
        delegations = []
        for agent_type in agent_types:
            result = await self.delegate_task(
                task_description=task_description,
                context={
                    **context,
                    "peer_channel_id": channel_id,
                    "peer_agents": [a for a in agent_types if a != agent_type]
                },
                suggested_agent=agent_type
            )
            delegations.append(result)

        return TeamDelegationResult(
            channel_id=channel_id,
            delegations=delegations
        )
```

---

*Document Version: 1.0*
*Date: 2026-02-05*
*Author: Backend System Architect*
