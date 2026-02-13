#!/usr/bin/env python3
"""
Infrastructure heartbeat sidecar for Kurultai multi-agent system.

Writes Agent.infra_heartbeat every 30 seconds for all 6 agents,
proving the gateway process is alive. Read by Ogedei's failover
detection (infra_heartbeat stale >120s = gateway dead).

Also runs a passive WebSocket listener (ChatMonitor) that captures
agent responses from the OpenClaw gateway. Every 10th heartbeat tick
(~5 min), buffered agent responses are PII-sanitized and flushed as
ChatSummary nodes to Neo4j.

Uses a single batched UNWIND query per cycle. Includes circuit
breaker: 3 consecutive failures -> 60s cooldown.
"""

import json
import os
import re
import signal
import sys
import threading
import time
import uuid
import logging
from datetime import datetime, timezone, timedelta
from enum import Enum

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.pii_sanitizer import sanitize, contains_sensitive_content

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [heartbeat-sidecar] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# All 6 Kurultai agents
AGENT_NAMES = ["main", "researcher", "writer", "developer", "analyst", "ops"]

# Agent configuration with heartbeat task definitions
AGENT_CONFIG = {
    "main": {
        "name": "kublai",
        "neo4j_name": "kublai",
        "tier": "critical",
        "interval_minutes": 5,
        "tasks": ["routing_optimization", "delegation_effectiveness"],
    },
    "researcher": {
        "name": "möngke",
        "neo4j_name": "möngke",
        "tier": "standard",
        "interval_minutes": 15,
        "tasks": ["knowledge_gap_analysis", "finding_consolidation"],
    },
    "writer": {
        "name": "chagatai",
        "neo4j_name": "chagatai",
        "tier": "light",
        "interval_minutes": 60,
        "tasks": ["content_creation_moltbook", "content_creation_4claw"],
    },
    "developer": {
        "name": "temüjin",
        "neo4j_name": "temüjin",
        "tier": "standard",
        "interval_minutes": 15,
        "tasks": ["pattern_learning", "debt_assessment"],
    },
    "analyst": {
        "name": "jochi",
        "neo4j_name": "jochi",
        "tier": "critical",
        "interval_minutes": 5,
        "tasks": ["performance_analysis", "efficiency_report"],
    },
    "ops": {
        "name": "ögedei",
        "neo4j_name": "ögedei",
        "tier": "critical",
        "interval_minutes": 5,
        "tasks": ["failover_readiness", "health_aggregation"],
    },
}


class TaskTier(Enum):
    """Task tier determines execution frequency and priority."""
    CRITICAL = "critical"
    STANDARD = "standard"
    LIGHT = "light"


# Tick intervals for each tier (30-second ticks)
# 5 min = 10 ticks, 15 min = 30 ticks, 60 min = 120 ticks
TIER_TICK_INTERVALS = {
    "critical": 10,
    "standard": 30,
    "light": 120,
}


def check_and_execute_tasks(driver, tick: int):
    """
    Check if any agent tasks should execute based on their intervals.
    tick represents 30-second intervals.
    """
    for agent_id, config in AGENT_CONFIG.items():
        tier = config.get("tier", "standard")
        interval_ticks = TIER_TICK_INTERVALS.get(tier, 30)

        # Check if this agent's interval has elapsed
        if tick % interval_ticks == 0:
            # Execute primary task
            primary_task = config["tasks"][0]
            execute_agent_task(agent_id, primary_task, driver)

            # Execute secondary task every other cycle
            if (tick // interval_ticks) % 2 == 0 and len(config["tasks"]) > 1:
                secondary_task = config["tasks"][1]
                execute_agent_task(agent_id, secondary_task, driver)

HEARTBEAT_INTERVAL = 30  # seconds
CIRCUIT_BREAKER_THRESHOLD = 3  # consecutive failures before cooldown
CIRCUIT_BREAKER_COOLDOWN = 60  # seconds
SUMMARY_INTERVAL_TICKS = 10  # every 10 heartbeats = ~5 minutes

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum}, shutting down...")
    _shutdown = True


class ChatMonitor(threading.Thread):
    """Passive WebSocket listener that buffers agent responses."""

    MAX_BACKOFF = 120  # max reconnect delay in seconds
    INITIAL_BACKOFF = 5  # initial reconnect delay in seconds

    def __init__(self, ws_url, token):
        super().__init__(daemon=True)
        self.ws_url = ws_url
        self.token = token
        self.buffer = {}  # agent_id -> [response_chunks]
        self.lock = threading.Lock()
        self._stop_event = threading.Event()

    def run(self):
        """Connect to WebSocket, handle events. Reconnect with exponential backoff."""
        try:
            import websocket
        except ImportError:
            logger.warning("websocket-client not installed, ChatMonitor disabled")
            return

        backoff = self.INITIAL_BACKOFF

        while not self._stop_event.is_set():
            ws = None
            try:
                ws = websocket.WebSocket()
                ws.settimeout(60)
                ws.connect(self.ws_url)
                self._handle_handshake(ws)
                logger.info("ChatMonitor connected to gateway WebSocket")
                was_stable = self._listen(ws)
                if was_stable:
                    backoff = self.INITIAL_BACKOFF  # reset backoff after stable connection
                # _listen() returned — connection was lost
                logger.info("ChatMonitor disconnected, will reconnect")
            except Exception as e:
                logger.warning(f"ChatMonitor connection error: {e}")
            finally:
                if ws:
                    try:
                        ws.close()
                    except Exception:
                        pass

            # Always backoff before reconnecting (whether normal return or exception)
            if self._stop_event.is_set():
                break
            logger.info(f"ChatMonitor reconnecting in {backoff}s")
            self._stop_event.wait(backoff)
            backoff = min(backoff * 2, self.MAX_BACKOFF)

    def _handle_handshake(self, ws):
        """Complete OpenClaw connect.challenge -> connect handshake."""
        challenge = json.loads(ws.recv())
        nonce = challenge.get('params', {}).get('nonce', '')

        ws.send(json.dumps({
            "type": "req",
            "id": str(uuid.uuid4()),
            "method": "connect",
            "params": {
                "minProtocol": 3,
                "maxProtocol": 3,
                "role": "operator",
                "scopes": ["operator.admin"],
                "auth": {"token": self.token},
                "client": {
                    "id": "cli",
                    "version": "1.0.0",
                    "platform": "linux",
                    "mode": "backend",
                },
                "challenge": {"nonce": nonce},
            },
        }))
        resp = json.loads(ws.recv())
        if resp.get('error'):
            raise ConnectionError(f"Connect rejected: {resp['error']}")

    def _listen(self, ws):
        """Listen for agent events, buffer response text. Returns True if ran >60s (stable)."""
        started = time.monotonic()
        while not self._stop_event.is_set():
            try:
                raw = ws.recv()
            except Exception:
                break  # will reconnect in run()

            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            if data.get('type') != 'evt' or data.get('event') != 'agent':
                continue

            payload = data.get('payload', {})
            stream = payload.get('stream')

            if stream == 'assistant':
                delta = payload.get('data', {}).get('delta', '')
                agent_id = payload.get('agentId', 'unknown')
                if delta:
                    with self.lock:
                        self.buffer.setdefault(agent_id, []).append(delta)

            elif stream == 'lifecycle':
                phase = payload.get('data', {}).get('phase', '')
                if phase == 'end':
                    agent_id = payload.get('agentId', 'unknown')
                    with self.lock:
                        self.buffer.setdefault(agent_id, []).append('\n---TURN_END---\n')

        return (time.monotonic() - started) > 60  # stable if listened >60s

    def flush(self):
        """Return and clear buffered responses per agent. Thread-safe."""
        with self.lock:
            result = dict(self.buffer)
            self.buffer.clear()
            return result

    def stop(self):
        self._stop_event.set()


# Simple topic extraction from sanitized text
_TOPIC_PATTERNS = [
    (r'\b(?:deploy|deployment|deploying)\b', 'deployment'),
    (r'\b(?:signal|messaging)\b', 'signal'),
    (r'\b(?:neo4j|database|migration)\b', 'database'),
    (r'\b(?:heartbeat|health|monitor)\b', 'monitoring'),
    (r'\b(?:research|search|find)\b', 'research'),
    (r'\b(?:code|implement|develop|build)\b', 'development'),
    (r'\b(?:write|document|content)\b', 'writing'),
    (r'\b(?:security|audit|vulnerab)\b', 'security'),
    (r'\b(?:error|bug|fix|debug)\b', 'debugging'),
    (r'\b(?:config|setting|environment)\b', 'configuration'),
    (r'\b(?:delegat|route|assign)\b', 'delegation'),
]


def extract_topics(text):
    """Extract topic tags from sanitized text."""
    topics = set()
    lower = text.lower()
    for pattern, topic in _TOPIC_PATTERNS:
        if re.search(pattern, lower):
            topics.add(topic)
    return list(topics)[:10]  # cap at 10 topics


def extract_delegations(text):
    """Extract agent-to-agent delegation mentions."""
    delegations = []
    for name in AGENT_NAMES:
        if name in text.lower():
            delegations.append(name)
    return delegations


def write_heartbeats(driver):
    """Write infra_heartbeat for all agents in a single transaction."""
    cypher = """
    UNWIND $agents AS agent_name
    MERGE (a:Agent {name: agent_name})
    SET a.infra_heartbeat = datetime($now)
    RETURN count(a) AS updated
    """
    now = datetime.now(timezone.utc).isoformat()

    with driver.session() as session:
        result = session.run(cypher, agents=AGENT_NAMES, now=now)
        record = result.single()
        return record["updated"] if record else 0


def write_chat_summary(driver, agent_id, response_text):
    """Write a sanitized ChatSummary node to Neo4j."""
    if contains_sensitive_content(response_text):
        logger.info(f"Skipping summary for {agent_id}: sensitive content detected")
        return

    sanitized = sanitize(response_text)
    turn_count = sanitized.count('---TURN_END---')
    if turn_count == 0:
        return  # No complete turns

    # Clean turn markers from summary text
    summary_text = sanitized.replace('\n---TURN_END---\n', '\n').strip()
    # Truncate to 5000 chars to avoid huge nodes
    if len(summary_text) > 5000:
        summary_text = summary_text[:5000] + '...[truncated]'

    topics = extract_topics(sanitized)
    delegations = extract_delegations(sanitized)
    now = datetime.now(timezone.utc).isoformat()

    cypher = """
    MATCH (a:Agent {name: $agent_id})
    CREATE (cs:ChatSummary {
        id: $id,
        agent_id: $agent_id,
        session_key: 'main',
        turn_count: $turn_count,
        topics: $topics,
        summary: $summary,
        tools_used: [],
        delegations: $delegations,
        created_at: datetime($now),
        window_start: datetime($now),
        window_end: datetime($now),
        pii_stripped: true
    })
    CREATE (a)-[:HAS_SUMMARY]->(cs)
    RETURN cs.id AS summary_id
    """

    with driver.session() as session:
        result = session.run(
            cypher,
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            turn_count=turn_count,
            topics=topics,
            summary=summary_text,
            delegations=delegations,
            now=now,
        )
        record = result.single()
        if record:
            logger.info(f"ChatSummary written for {agent_id}: {turn_count} turns, topics={topics}")


# ============ Agent-Specific Heartbeat Task Implementations ============

def task_content_creation_moltbook(driver) -> dict:
    """
    Chagatai: Generate content ideas and drafts for Moltbook platform.
    Analyzes recent system activity to create engaging posts.
    """
    # Query recent interesting activity across all agents
    cypher = """
    MATCH (cs:ChatSummary)
    WHERE cs.created_at > datetime() - duration('PT4H')
    WITH cs.topics AS topics, cs.summary AS summary
    LIMIT 20
    RETURN topics, summary
    """

    with driver.session() as session:
        result = session.run(cypher)
        recent_activity = [dict(r) for r in result]

    # Extract trending topics
    topic_counts = {}
    for activity in recent_activity:
        for topic in activity.get("topics", []):
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

    trending = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:3]

    # Create content brief for Moltbook post
    content_brief = {
        "platform": "moltbook",
        "trending_topics": [t[0] for t in trending],
        "activity_count": len(recent_activity),
        "suggested_angle": f"Behind the scenes: How Kurultai handles {trending[0][0] if trending else 'multi-agent coordination'}",
        "draft_status": "pending",
    }

    # Write content brief to Neo4j
    cypher2 = """
    CREATE (cb:ContentBrief {
        id: $id,
        platform: $platform,
        topics: $topics,
        angle: $angle,
        created_at: datetime($now),
        status: 'draft_pending',
        assigned_to: 'chagatai'
    })
    RETURN cb.id
    """

    with driver.session() as session:
        session.run(cypher2,
            id=str(uuid.uuid4()),
            platform="moltbook",
            topics=content_brief["trending_topics"],
            angle=content_brief["suggested_angle"],
            now=datetime.now(timezone.utc).isoformat(),
        )

    summary = f"Moltbook content brief created: {content_brief['suggested_angle'][:60]}..."
    return {"summary": summary, "tokens": 350, "data": content_brief}


def task_content_creation_4claw(driver) -> dict:
    """
    Chagatai: Generate technical insights and tips for 4Claw platform.
    Focuses on OpenClaw gateway usage, agent patterns, and tooling.
    """
    # Query technical patterns and tool usage
    cypher = """
    MATCH (cs:ChatSummary)
    WHERE cs.created_at > datetime() - duration('PT4H')
      AND ANY(topic IN cs.topics WHERE topic IN ['deployment', 'signal', 'database', 'configuration'])
    RETURN cs.topics AS topics, cs.summary AS summary
    LIMIT 10
    """

    with driver.session() as session:
        result = session.run(cypher)
        tech_activity = [dict(r) for r in result]

    # Identify common technical challenges
    challenge_patterns = {
        "deployment": "Deploying OpenClaw agents at scale",
        "signal": "Signal messaging integration patterns",
        "database": "Neo4j operational memory optimization",
        "configuration": "Multi-agent configuration management",
        "monitoring": "Heartbeat and health check strategies",
    }

    detected_challenges = []
    for activity in tech_activity:
        for topic in activity.get("topics", []):
            if topic in challenge_patterns:
                detected_challenges.append(challenge_patterns[topic])

    # Create 4Claw technical tip brief
    tip_topic = detected_challenges[0] if detected_challenges else "Multi-agent orchestration best practices"

    content_brief = {
        "platform": "4claw",
        "tip_topic": tip_topic,
        "technical_depth": "intermediate",
        "code_examples": True,
        "suggested_title": f"Tip: {tip_topic[:50]}",
    }

    # Write to Neo4j
    cypher2 = """
    CREATE (cb:ContentBrief {
        id: $id,
        platform: $platform,
        tip_topic: $tip_topic,
        technical_depth: $technical_depth,
        created_at: datetime($now),
        status: 'draft_pending',
        assigned_to: 'chagatai'
    })
    RETURN cb.id
    """

    with driver.session() as session:
        session.run(cypher2,
            id=str(uuid.uuid4()),
            platform="4claw",
            tip_topic=tip_topic,
            technical_depth="intermediate",
            now=datetime.now(timezone.utc).isoformat(),
        )

    summary = f"4Claw technical tip brief created: {tip_topic[:60]}..."
    return {"summary": summary, "tokens": 320, "data": content_brief}


def execute_agent_task(agent_id: str, task_name: str, driver) -> dict:
    """
    Execute a specific heartbeat task for an agent.
    Returns task result metadata.
    """
    config = AGENT_CONFIG.get(agent_id, {})
    agent_name = config.get("neo4j_name", agent_id)
    executed_at = datetime.now(timezone.utc).isoformat()

    try:
        # Route to appropriate task implementation
        if task_name == "content_creation_moltbook":
            result = task_content_creation_moltbook(driver)
        elif task_name == "content_creation_4claw":
            result = task_content_creation_4claw(driver)
        else:
            # Task not yet implemented - log and return empty
            logger.debug(f"Task {task_name} for {agent_name} not implemented yet")
            return {"summary": "Task not implemented", "tokens": 0, "data": {}}

        # Write HeartbeatTask node for tracking
        cypher = """
        CREATE (ht:HeartbeatTask {
            id: $id,
            agent: $agent,
            agent_id: $agent_id,
            task_name: $task_name,
            executed_at: datetime($executed_at),
            result_summary: $summary,
            tokens_used: $tokens,
            status: 'completed'
        })
        RETURN ht.id
        """

        with driver.session() as session:
            session.run(cypher,
                id=str(uuid.uuid4()),
                agent=agent_name,
                agent_id=agent_id,
                task_name=task_name,
                executed_at=executed_at,
                summary=result.get("summary", "")[:200],
                tokens=result.get("tokens", 0)
            )

        logger.info(f"Task {task_name} completed for {agent_name}")
        return result

    except Exception as e:
        logger.error(f"Task {task_name} failed for {agent_name}: {e}")
        return {"summary": f"Error: {str(e)[:100]}", "tokens": 0, "data": {}}


def main():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")

    if not password:
        logger.error("NEO4J_PASSWORD not set, exiting")
        sys.exit(1)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(uri, auth=(user, password))

    logger.info(f"Starting infra heartbeat sidecar (interval={HEARTBEAT_INTERVAL}s, agents={len(AGENT_NAMES)})")

    # Start chat monitor if gateway token is available
    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    monitor = None
    if token:
        monitor = ChatMonitor("ws://127.0.0.1:18789/ws", token)
        monitor.start()
        logger.info("Chat monitor started")
    else:
        logger.info("OPENCLAW_GATEWAY_TOKEN not set, chat monitor disabled")

    consecutive_failures = 0
    tick = 0

    try:
        while not _shutdown:
            try:
                count = write_heartbeats(driver)
                logger.info(f"Heartbeat written for {count} agents")
                consecutive_failures = 0
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"Heartbeat write failed ({consecutive_failures}/{CIRCUIT_BREAKER_THRESHOLD}): {e}")

                if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                    logger.warning(f"Circuit breaker open, cooling down {CIRCUIT_BREAKER_COOLDOWN}s")
                    for _ in range(CIRCUIT_BREAKER_COOLDOWN):
                        if _shutdown:
                            break
                        time.sleep(1)
                    consecutive_failures = 0
                    continue

            tick += 1

            # Execute agent-specific tasks based on their intervals
            try:
                check_and_execute_tasks(driver, tick)
            except Exception as e:
                logger.error(f"Task execution failed: {e}")
                # Don't let task failures affect heartbeats

            # Flush chat summaries every SUMMARY_INTERVAL_TICKS heartbeats (~5 min)
            if monitor and tick % SUMMARY_INTERVAL_TICKS == 0:
                try:
                    buffers = monitor.flush()
                    for agent_id, chunks in buffers.items():
                        text = ''.join(chunks)
                        if text.strip():
                            write_chat_summary(driver, agent_id, text)
                except Exception as e:
                    logger.error(f"Summary write failed: {e}")
                    # Never let summary failure affect heartbeats

            for _ in range(HEARTBEAT_INTERVAL):
                if _shutdown:
                    break
                time.sleep(1)
    finally:
        if monitor:
            monitor.stop()
        driver.close()
        logger.info("Heartbeat sidecar stopped")


if __name__ == "__main__":
    main()
