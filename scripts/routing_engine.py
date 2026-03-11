#!/usr/bin/env python3
"""
Routing Engine for Kurultai agents.

Single entry point for all routing decisions.
Consolidates routing logic from task_intake, agent handlers.

Usage:
    from routing_engine import RoutingEngine, RoutingDecision

    engine = RoutingEngine()
    decision = engine.route(
        "Write a Python script to analyze my GitHub PR",
        skill_hint="/senior-backend"
    )
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict, Any
from pathlib import Path
import json

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    """Result of a routing decision."""
    agent: str
    skill_hint: Optional[str]
    reason: str
    load_balance_factor: float = 0.0


class RoutingEngine:
    """
    Single entry point for all routing decisions.

    Consolidates routing logic from:
    - Load balancing
    - Circuit breaker integration
    - Skill hint detection
    """

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize routing engine."""
        self.config_path = config_path or Path('/Users/kublai/.openclaw/config/routing.json')
        self.agents = self._load_agents()
        self.skill_patterns = self._load_skill_patterns()
        self._load_balancer = LoadBalancer()

        # Circuit breaker integration
        from circuit_breaker import CircuitBreaker
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

    def _load_agents(self) -> Dict[str, Any]:
        """Load agent configuration from config file."""
        if self.config_path and exists():
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                return config.get('agents', {})
        return {}

    def _load_skill_patterns(self) -> Dict[str, str]:
        """Load skill detection patterns."""
        return {
            "design": "/horde-brainstorming",
            "architect": "/senior-architect",
            "research": "/lead-research-assistant",
            "implement": "/horde-implement",
            "review": "/horde-review",
            "debug": "/horde-debug",
            "plan": "/horde-plan",
            "learn": "/horde-learn",
            "deploy": "/senior-devops",
            "frontend": "/senior-frontend",
            "backend": "/senior-backend",
            "data": "/senior-data-engineer",
            "ml": "/senior-ml-engineer",
            "write": "/content-research-writer",
            "brainstorm": "/horde-brainstorming",
        }

    def route(
        self,
        task_text: str,
        source: Optional[str] = None
    ) -> RoutingDecision:
        """
        Route a task to the appropriate agent.

        Args:
            task_text: The task description
            source: Optional source of the task

        Returns:
            RoutingDecision with agent, skill hint, and reason
        """
        # Extract keywords
        task_lower = task_text.lower()
        keywords = set(re.findall(r'\b\w+', task_lower))

        # Check for skill hints first
        skill_hint = None
        for pattern, hint in self.skill_patterns.items():
            if pattern in keywords:
                skill_hint = hint
                break

        # Try keyword matching for agents
        agent_scores: Dict[str, float] = {}
        for agent_name, agent_config in self.agents.items():
            agent_keywords = agent_config.get('keywords', [])
            score = sum(1 for kw in keywords if kw in agent_keywords)
            score += 1
            agent_scores[agent_name] = score

        # Apply load balancing
        if agent_scores:
            # Check circuit breakers
            for agent in agent_scores:
                if self._is_circuit_open(agent):
                    agent_scores[agent] *= 0.1  # Reduce score if circuit half-open

            # Sort by score
            sorted_agents = sorted(
                agent_scores.items(),
                key=lambda x: x[1],
                reverse=True
            )

            if sorted_agents:
                best_agent = sorted_agents[0][0]
                best_score = sorted_agents[0][1]
                return RoutingDecision(
                    agent=best_agent,
                    skill_hint=skill_hint,
                    reason=f"Keyword match (score: {best_score:.2f})"
                )

        # Default to kublai (router)
        return RoutingDecision(
            agent='kublai',
            skill_hint=skill_hint,
            reason='Default routing agent'
        )

    def _is_circuit_open(self, service: str) -> bool:
        """Check if circuit breaker is open for a service."""
        cb = self._circuit_breakers.get(service)
        return cb is not None and cb.is_open()


if __name__ == "__main__":
    print("Testing Routing Engine...")

    engine = RoutingEngine()

    # Test 1: Normal routing
    decision = engine.route("Write a Python script to analyze my GitHub PR")
    print(f"Test 1 - Agent: {decision.agent}")
    assert decision.agent in ['kublai', 'temujin', 'jochi', 'ogedei']

    # Test 2: Skill hint detection
    decision = engine.route("Design a new API architecture for our platform")
    print(f"Test 2 - Agent: {decision.agent}, Skill hint: {decision.skill_hint}")
    assert decision.skill_hint == "/senior-architect"
    # Test 3: Load balancing
    for _ in range(5):
        engine.route("Debug the test case")
    print("\nDone!")
