"""
Chat Session Recorder - Records and analyzes chat sessions with Kublai.

This module provides the ChatSessionRecorder class for:
- Recording messages and timing events during chat sessions
- Tracking Neo4j queries with performance metrics
- Validating observed behavior against architecture specifications
- Saving/loading sessions for regression testing

Usage:
    recorder = ChatSessionRecorder(
        session_name="test_session",
        architecture_spec_path="ARCHITECTURE.md"
    )
    await recorder.start_session()
    await recorder.record_message("user", "Test message")
    await recorder.record_event("delegation_start", "kublai", {})
    await recorder.end_session()
    findings = await recorder.validate_against_architecture()
    recorder.save_session("output.json")
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TimingEvent:
    """Represents a timing event in the workflow."""

    event_type: str  # e.g., "delegation_start", "agent_response", "synthesis_complete"
    timestamp: float
    agent: str
    metadata: Dict[str, Any]


@dataclass
class MessageTrace:
    """Represents a message in the conversation."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: float
    agent_responding: Optional[str] = None  # Which agent handled this
    message_id: Optional[str] = None


@dataclass
class Neo4jQueryTrace:
    """Represents a Neo4j query execution."""

    query: str
    params: Dict[str, Any]
    duration_ms: float
    timestamp: float
    result_count: Optional[int] = None


class ChatSessionRecorder:
    """Records and analyzes chat sessions with Kublai for workflow validation.

    This recorder captures:
    - All messages with timestamps
    - Timing events for workflow milestones
    - Neo4j queries with performance metrics
    - Architecture validation results

    The recorder can save sessions to disk for later comparison (regression testing).
    """

    def __init__(
        self,
        session_name: str,
        architecture_spec_path: Optional[str] = None,
        output_dir: str = "tests/interactive/sessions",
    ):
        self.session_name = session_name
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.messages: List[MessageTrace] = []
        self.timing_events: List[TimingEvent] = []
        self.neo4j_queries: List[Neo4jQueryTrace] = []

        # Load architecture specification for validation
        self.architecture_spec = self._load_architecture_spec(
            architecture_spec_path
        )

        # Track agents observed during session
        self.agents_observed: List[str] = []

    def _load_architecture_spec(self, path: Optional[str]) -> Dict[str, Any]:
        """Load architecture specification for validation.

        Parses ARCHITECTURE.md, neo4j.md, kurultai_0.2.md to extract
        expected behavior patterns.
        """
        if path is None:
            path = "ARCHITECTURE.md"

        spec_path = Path(path)
        if not spec_path.exists():
            logger.warning(f"Architecture spec not found at {path}, using defaults")
            return self._default_architecture_spec()

        try:
            with open(spec_path, "r") as f:
                content = f.read()

            # Extract key expectations from the architecture doc
            return {
                "expected_agents": self._extract_agents(content),
                "expected_delegation_pattern": self._extract_delegation_pattern(content),
                "expected_communication_protocol": self._extract_protocol(content),
                "expected_memory_operations": self._extract_memory_operations(content),
                "timing_expectations": {
                    "delegation_latency_p95": 2.0,  # seconds
                    "agent_response_p95": 30.0,
                    "synthesis_complete_p95": 60.0,
                },
            }
        except Exception as e:
            logger.warning(f"Error loading architecture spec: {e}, using defaults")
            return self._default_architecture_spec()

    def _default_architecture_spec(self) -> Dict[str, Any]:
        """Return default architecture specification."""
        return {
            "expected_agents": [
                "kublai",
                "mongke",
                "chagatai",
                "temujin",
                "jochi",
                "ogedei",
            ],
            "expected_delegation_pattern": (
                "kublai receives -> classifies -> delegates to specialist"
            ),
            "expected_communication_protocol": "OpenClaw WebSocket on port 18789",
            "expected_memory_operations": [
                "task_create",
                "task_claim",
                "task_update",
                "reflection_store",
            ],
            "timing_expectations": {
                "delegation_latency_p95": 2.0,
                "agent_response_p95": 30.0,
                "synthesis_complete_p95": 60.0,
            },
        }

    def _extract_agents(self, content: str) -> List[str]:
        """Extract expected agent names from architecture doc."""
        # Look for agent mentions
        agents = set()
        agent_patterns = [
            r"\b(?:Kublai|kublai|main)\b",
            r"\b(?:Möngke|mongke|researcher)\b",
            r"\b(?:Chagatai|chagatai|writer)\b",
            r"\b(?:Temüjin|temujin|developer)\b",
            r"\b(?:Jochi|jochi|analyst)\b",
            r"\b(?:Ögedei|ogedei|operations)\b",
        ]
        for pattern in agent_patterns:
            if re.search(pattern, content):
                name = pattern.split(r"\|")[0].lower().replace(r"\b", "")
                if "kublai" in name or "main" in name:
                    agents.add("kublai")
                elif "mongke" in name or "researcher" in name:
                    agents.add("mongke")
                elif "chagatai" in name or "writer" in name:
                    agents.add("chagatai")
                elif "temujin" in name or "developer" in name:
                    agents.add("temujin")
                elif "jochi" in name or "analyst" in name:
                    agents.add("jochi")
                elif "ogedei" in name or "operations" in name:
                    agents.add("ogedei")
        return list(agents) or ["kublai", "mongke", "chagatai", "temujin", "jochi", "ogedei"]

    def _extract_delegation_pattern(self, content: str) -> str:
        """Extract delegation pattern from architecture doc."""
        if "delegation" in content.lower():
            return "kublai receives -> classifies -> delegates to specialist"
        return "unknown"

    def _extract_protocol(self, content: str) -> str:
        """Extract communication protocol from architecture doc."""
        if "websocket" in content.lower() or "openclaw" in content.lower():
            return "OpenClaw WebSocket"
        return "unknown"

    def _extract_memory_operations(self, content: str) -> List[str]:
        """Extract memory operations from architecture doc."""
        operations = []
        for op in ["task_create", "task_claim", "task_update", "reflection_store"]:
            if op.replace("_", " ") in content.lower():
                operations.append(op)
        return operations or ["task_create", "task_claim"]

    async def start_session(self):
        """Start recording a chat session."""
        self.start_time = time.time()
        await self.record_event(
            "session_start",
            "system",
            {"timestamp": datetime.now(timezone.utc).isoformat()},
        )
        logger.info(f"Started recording session: {self.session_name}")

    async def record_message(
        self,
        role: str,
        content: str,
        agent_responding: Optional[str] = None,
        message_id: Optional[str] = None,
    ):
        """Record a message in the conversation.

        Args:
            role: "user" or "assistant"
            content: Message content
            agent_responding: Which agent handled this (if assistant)
            message_id: Optional message ID for tracking
        """
        trace = MessageTrace(
            role=role,
            content=content,
            timestamp=time.time(),
            agent_responding=agent_responding,
            message_id=message_id or str(len(self.messages)),
        )
        self.messages.append(trace)
        logger.debug(f"Recorded {role} message: {len(content)} chars")

    async def record_event(
        self, event_type: str, agent: str, metadata: Dict[str, Any]
    ):
        """Record a timing event.

        Args:
            event_type: Type of event (delegation_start, agent_response, etc.)
            agent: Agent associated with event
            metadata: Additional event data
        """
        event = TimingEvent(
            event_type=event_type, timestamp=time.time(), agent=agent, metadata=metadata
        )
        self.timing_events.append(event)

        # Track agents seen
        if agent != "system" and agent not in self.agents_observed:
            self.agents_observed.append(agent)

        logger.debug(f"Recorded event: {event_type} by {agent}")

    async def record_neo4j_query(
        self,
        query: str,
        params: Dict[str, Any],
        duration_ms: float,
        result_count: Optional[int] = None,
    ):
        """Record a Neo4j query for analysis.

        Args:
            query: Cypher query string
            params: Query parameters
            duration_ms: Query execution time
            result_count: Number of results returned
        """
        trace = Neo4jQueryTrace(
            query=query,
            params=params,
            duration_ms=duration_ms,
            timestamp=time.time(),
            result_count=result_count,
        )
        self.neo4j_queries.append(trace)
        logger.debug(f"Recorded Neo4j query: {duration_ms}ms")

    async def end_session(self):
        """End the recording session."""
        self.end_time = time.time()
        duration = self.end_time - self.start_time if self.start_time else 0
        await self.record_event(
            "session_end",
            "system",
            {"duration_seconds": duration, "timestamp": datetime.now(timezone.utc).isoformat()},
        )
        logger.info(
            f"Ended recording session: {self.session_name} ({duration:.2f}s)"
        )

    async def validate_against_architecture(self) -> Dict[str, Any]:
        """Compare observed behavior against architecture specification.

        Returns:
            Dictionary with validations, violations, warnings, and metrics
        """
        findings: Dict[str, Any] = {
            "validations": [],
            "violations": [],
            "warnings": [],
            "metrics": {},
        }

        # Validate agent communication pattern
        expected_agents = set(self.architecture_spec.get("expected_agents", []))
        if self.agents_observed:
            observed_agents = set(self.agents_observed)

            if observed_agents.issuperset(expected_agents):
                findings["validations"].append(
                    f"All expected agents were observed: {', '.join(observed_agents)}"
                )
            else:
                missing = expected_agents - observed_agents
                if missing:
                    findings["warnings"].append(
                        f"Agents not observed: {', '.join(missing)}"
                    )

            findings["metrics"]["agents_observed"] = list(observed_agents)
            findings["metrics"]["agent_count"] = len(observed_agents)

        # Validate delegation pattern
        delegation_events = [e for e in self.timing_events if "delegation" in e.event_type]
        if delegation_events:
            findings["validations"].append(
                f"Delegation pattern observed: {len(delegation_events)} events"
            )
            findings["metrics"]["delegation_events"] = len(delegation_events)

        # Calculate timing metrics
        if len(self.timing_events) >= 2:
            for event_name, expected_p95 in self.architecture_spec.get(
                "timing_expectations", {}
            ).items():
                observed_latencies = self._calculate_latencies(event_name)
                if observed_latencies:
                    p95_index = int(len(observed_latencies) * 0.95)
                    p95 = sorted(observed_latencies)[min(p95_index, len(observed_latencies) - 1)]
                    findings["metrics"][event_name] = {
                        "p95_seconds": p95,
                        "expected_p95": expected_p95,
                        "count": len(observed_latencies),
                    }
                    if p95 > expected_p95 * 1.5:
                        findings["violations"].append(
                            f"{event_name} P95 ({p95:.2f}s) exceeds 150% of expected ({expected_p95}s)"
                        )

        # Validate Neo4j usage
        if self.neo4j_queries:
            findings["validations"].append(
                f"Neo4j operations recorded: {len(self.neo4j_queries)} queries"
            )

            query_types = {}
            total_duration = 0
            for q in self.neo4j_queries:
                first_word = q.query.strip().split()[0].upper() if q.query.strip() else "UNKNOWN"
                query_types[first_word] = query_types.get(first_word, 0) + 1
                total_duration += q.duration_ms

            findings["metrics"]["neo4j_query_types"] = query_types
            findings["metrics"]["neo4j_total_queries"] = len(self.neo4j_queries)
            findings["metrics"]["neo4j_avg_duration_ms"] = (
                total_duration / len(self.neo4j_queries) if self.neo4j_queries else 0
            )

        # Message metrics
        if self.messages:
            user_messages = [m for m in self.messages if m.role == "user"]
            assistant_messages = [m for m in self.messages if m.role == "assistant"]
            findings["metrics"]["user_messages"] = len(user_messages)
            findings["metrics"]["assistant_messages"] = len(assistant_messages)
            findings["metrics"]["total_messages"] = len(self.messages)

        return findings

    def _calculate_latencies(self, event_name: str) -> List[float]:
        """Calculate latencies between events of a given type."""
        latencies = []
        for i, event in enumerate(self.timing_events[1:], 1):
            if event_name in event.event_type:
                latency = event.timestamp - self.timing_events[i - 1].timestamp
                latencies.append(latency)
        return latencies

    def save_session(self, output_path: Optional[str] = None) -> str:
        """Save the recorded session to disk for regression testing.

        Args:
            output_path: Optional custom output path

        Returns:
            Path to saved session file
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.session_name}_{timestamp}.json"
            output_path = str(self.output_dir / filename)

        session_data = {
            "session_name": self.session_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": (self.end_time - self.start_time)
            if self.start_time and self.end_time
            else 0,
            "messages": [asdict(m) for m in self.messages],
            "timing_events": [asdict(e) for e in self.timing_events],
            "neo4j_queries": [asdict(q) for q in self.neo4j_queries],
            "agents_observed": self.agents_observed,
            "architecture_spec": self.architecture_spec,
        }

        with open(output_path, "w") as f:
            json.dump(session_data, f, indent=2)

        logger.info(f"Session saved to {output_path}")
        return output_path

    @classmethod
    def load_session(cls, path: str) -> "ChatSessionRecorder":
        """Load a previously recorded session for comparison.

        Args:
            path: Path to saved session file

        Returns:
            ChatSessionRecorder instance with loaded data
        """
        with open(path, "r") as f:
            data = json.load(f)

        recorder = cls(data["session_name"], output_dir=str(Path(path).parent))
        recorder.start_time = data.get("start_time")
        recorder.end_time = data.get("end_time")
        recorder.messages = [MessageTrace(**m) for m in data.get("messages", [])]
        recorder.timing_events = [TimingEvent(**e) for e in data.get("timing_events", [])]
        recorder.neo4j_queries = [
            Neo4jQueryTrace(**q) for q in data.get("neo4j_queries", [])
        ]
        recorder.agents_observed = data.get("agents_observed", [])
        recorder.architecture_spec = data.get("architecture_spec", {})

        return recorder

    def compare_with(self, other: "ChatSessionRecorder") -> Dict[str, Any]:
        """Compare this session with another for regression detection.

        Args:
            other: Another ChatSessionRecorder instance

        Returns:
            Comparison results
        """
        comparison = {
            "duration_diff": 0,
            "agent_participation_changed": False,
            "message_count_diff": 0,
            "neo4j_query_count_diff": 0,
        }

        if self.start_time and self.end_time and other.start_time and other.end_time:
            duration_self = self.end_time - self.start_time
            duration_other = other.end_time - other.start_time
            comparison["duration_diff"] = duration_other - duration_self
            comparison["duration_self"] = duration_self
            comparison["duration_other"] = duration_other

        agents_self = set(self.agents_observed)
        agents_other = set(other.agents_observed)
        comparison["agent_participation_changed"] = agents_self != agents_other
        comparison["agents_self"] = list(agents_self)
        comparison["agents_other"] = list(agents_other)

        comparison["message_count_diff"] = len(other.messages) - len(self.messages)
        comparison["neo4j_query_count_diff"] = (
            len(other.neo4j_queries) - len(self.neo4j_queries)
        )

        return comparison


__all__ = ["ChatSessionRecorder", "MessageTrace", "TimingEvent", "Neo4jQueryTrace"]
