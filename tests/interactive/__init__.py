"""
Interactive Workflow Observation Tests

This module provides tools for recording and analyzing chat sessions with Kublai
to observe real workflow processes and validate behavior against architecture
specifications.

Key components:
- ChatSessionRecorder: Records messages, timing events, and Neo4j queries
- TestScenario: Defines test scenarios with expected workflows
- ScenarioRunner: Executes scenarios and generates validation checklists
"""

from .chat_session_recorder import (
    ChatSessionRecorder,
    MessageTrace,
    TimingEvent,
)

from .test_scenarios import (
    INTERACTIVE_TEST_SCENARIOS,
    ScenarioRunner,
    TestScenario,
)

__all__ = [
    "ChatSessionRecorder",
    "MessageTrace",
    "TimingEvent",
    "INTERACTIVE_TEST_SCENARIOS",
    "ScenarioRunner",
    "TestScenario",
]
