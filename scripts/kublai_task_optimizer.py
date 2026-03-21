#!/usr/bin/env python3
"""
Kublai Task Optimizer

Queries KublaiLearning nodes to recommend optimal configuration
for task creation. Called by Kublai's task router before creating
each task.

Usage:
    from kublai_task_optimizer import get_optimal_config, create_optimized_task
    config = get_optimal_config(agent='temujin', task_type='implementation')

Features:
- Query Neo4j for learned patterns (KublaiLearning nodes)
- Epsilon-greedy exploration (10% random for diversity)
- Confidence threshold fallback (<60% uses defaults)
- Graceful fallback when Neo4j unavailable
- Feature flag support (OPTIMIZATION_ENABLED env var)
"""

import os
import sys
import json
import random
from datetime import datetime
from typing import Dict, Any, Optional, List

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import neo4j_session

# Configuration
OPTIMIZATION_ENABLED = os.getenv("OPTIMIZATION_ENABLED", "true").lower() == "true"
EPSILON_GREEDY_RATE = 0.10  # 10% exploration
CONFIDENCE_THRESHOLD = 0.60  # 60% minimum confidence
DEFAULT_TEMPLATE = "agent-protocol-v2"
from kurultai_paths import CLAUDE_TIMEOUT as DEFAULT_TIMEOUT

# Path to prompt templates
TEMPLATES_PATH = os.path.expanduser("~/.openclaw/agents/main/data/prompt_templates.json")

# Task type to skill hint mapping (fallback when no learnings)
TASK_TYPE_SKILL_MAP = {
    "implementation": "/horde-implement",
    "research": "/horde-brainstorming",
    "debugging": "/systematic-debugging",
    "review": "/code-reviewer",
    "deployment": "/dev-deploy",
    "documentation": "/documentation-expert",
    "testing": "/generate-tests",
    "strategy": "/horde-plan",
    "analysis": "/data-scientist",
}

# Agent to default skill hint mapping
AGENT_SKILL_DEFAULTS = {
    "temujin": "/horde-implement",
    "mongke": "/horde-brainstorming",
    "chagatai": "/senior-fullstack",
    "jochi": "/code-reviewer",
    "ogedei": "/dev-deploy",
    "tolui": "/systematic-debugging",
    "kublai": "/horde-implement",
}

# Timeout by priority — imported from canonical source (kurultai_paths.py)
from kurultai_paths import TIMEOUT_BY_PRIORITY


def _load_templates() -> Dict[str, Any]:
    """Load prompt templates from JSON file."""
    try:
        with open(TEMPLATES_PATH) as f:
            return json.load(f)
    except Exception:
        return {"templates": {}, "metadata": {"default_template": DEFAULT_TEMPLATE}}


def _get_active_templates() -> List[str]:
    """Get list of active template names."""
    templates_data = _load_templates()
    templates = templates_data.get("templates", {})
    return [
        name for name, data in templates.items()
        if data.get("status") == "active"
    ]


def get_optimal_config(agent: str, task_type: str = None,
                       priority: str = "normal") -> Dict[str, Any]:
    """
    Query Neo4j for optimal task configuration based on historical patterns.

    Args:
        agent: Target agent (temujin, mongke, etc.)
        task_type: Optional task type classification
        priority: Task priority (critical/high/normal/low)

    Returns:
        Dict with:
            - template: Recommended template name
            - skill_hint: Recommended skill hint
            - timeout: Recommended timeout in seconds
            - context_sources: List of recommended context sources
            - confidence: Confidence score (0.0-1.0)
            - source: 'learned' | 'defaults' | 'exploration'
    """
    if not OPTIMIZATION_ENABLED:
        return _get_default_config(agent, task_type, priority)

    # Epsilon-greedy: 10% chance of exploration
    if random.random() < EPSILON_GREEDY_RATE:
        return _get_exploration_config(agent, task_type, priority)

    try:
        config = _query_learnings(agent, task_type, priority)

        # Check confidence threshold
        if config.get("confidence", 0) < CONFIDENCE_THRESHOLD:
            return _get_default_config(agent, task_type, priority)

        config["source"] = "learned"
        return config

    except Exception as e:
        # Graceful fallback on any error
        print(f"[optimizer] Neo4j query failed, using defaults: {e}")
        return _get_default_config(agent, task_type, priority)


def _query_learnings(agent: str, task_type: str, priority: str) -> Dict[str, Any]:
    """Query Neo4j for learned patterns."""
    config = {
        "template": DEFAULT_TEMPLATE,
        "skill_hint": None,
        "timeout": TIMEOUT_BY_PRIORITY.get(priority, DEFAULT_TIMEOUT),
        "context_sources": ["memory", "recent_tasks"],
        "confidence": 0.5,
    }

    try:
        with neo4j_session() as session:
            # 1. Get best template for this agent
            template_learning = _get_template_learning(session, agent)
            if template_learning:
                config["template"] = template_learning["template"]
                config["confidence"] = template_learning["confidence"]

            # 2. Get best skill hint for task type
            skill_learning = _get_skill_hint_learning(session, agent, task_type)
            if skill_learning:
                config["skill_hint"] = skill_learning["skill_hint"]
                # Use higher confidence between template and skill
                config["confidence"] = max(config["confidence"], skill_learning["confidence"])

            # 3. Get optimal timeout
            timeout_learning = _get_timeout_learning(session, agent, priority)
            if timeout_learning:
                config["timeout"] = timeout_learning

            # 4. Get recommended context sources
            context_sources = _get_context_sources(session, agent)
            if context_sources:
                config["context_sources"] = context_sources

    except Exception as e:
        print(f"[optimizer] Query error: {e}")

    return config


def _get_template_learning(session, agent: str) -> Optional[Dict[str, Any]]:
    """Query for best template recommendation."""
    try:
        result = session.run("""
            MATCH (l:KublaiLearning)
            WHERE l.learning_type = 'prompt_pattern'
              AND l.status = 'active'
              AND (l.agent_filter = $agent OR l.agent_filter = '*' OR l.agent_filter IS NULL)
              AND l.valid_until > datetime()
            RETURN l.pattern_key as template,
                   l.confidence as confidence
            ORDER BY l.confidence DESC, l.sample_size DESC
            LIMIT 1
        """, agent=agent)

        record = result.single()
        if record and record["template"]:
            return {
                "template": record["template"],
                "confidence": record["confidence"] or 0.5,
            }
    except Exception:
        pass
    return None


def _get_skill_hint_learning(session, agent: str, task_type: str) -> Optional[Dict[str, Any]]:
    """Query for best skill hint recommendation."""
    try:
        result = session.run("""
            MATCH (l:KublaiLearning)
            WHERE l.learning_type = 'skill_hint'
              AND l.status = 'active'
              AND (l.agent_filter = $agent OR l.agent_filter IS NULL)
              AND l.valid_until > datetime()
            RETURN l.pattern_key as skill_hint,
                   l.confidence as confidence
            ORDER BY l.confidence DESC, l.sample_size DESC
            LIMIT 1
        """, agent=agent)

        record = result.single()
        if record and record["skill_hint"]:
            return {
                "skill_hint": record["skill_hint"],
                "confidence": record["confidence"] or 0.5,
            }
    except Exception:
        pass
    return None


def _get_timeout_learning(session, agent: str, priority: str) -> Optional[int]:
    """Query for optimal timeout based on agent + priority."""
    try:
        result = session.run("""
            MATCH (l:KublaiLearning)
            WHERE l.learning_type = 'timeout'
              AND l.status = 'active'
              AND (l.agent_filter = $agent OR l.agent_filter IS NULL)
              AND l.valid_until > datetime()
            RETURN l.pattern_key as timeout_bucket
            ORDER BY l.confidence DESC
            LIMIT 1
        """, agent=agent)

        record = result.single()
        if record and record["timeout_bucket"]:
            return _map_timeout_bucket(record["timeout_bucket"])
    except Exception:
        pass
    return None


def _map_timeout_bucket(bucket: str) -> int:
    """Map timeout bucket name to seconds."""
    mapping = {
        "short": 1800,      # 30 min
        "medium": 3600,     # 1 hour
        "long": 7200,       # 2 hours
        "very_long": 14400  # 4 hours
    }
    return mapping.get(bucket, DEFAULT_TIMEOUT)


def _get_context_sources(session, agent: str) -> List[str]:
    """Query for recommended context sources."""
    try:
        result = session.run("""
            MATCH (l:KublaiLearning)
            WHERE l.learning_type = 'context'
              AND l.status = 'active'
              AND (l.agent_filter = $agent OR l.agent_filter IS NULL)
              AND l.valid_until > datetime()
            RETURN l.recommendation.context_sources as sources
            ORDER BY l.confidence DESC
            LIMIT 1
        """, agent=agent)

        record = result.single()
        if record and record["sources"]:
            sources = record["sources"]
            if isinstance(sources, list):
                return sources
            if isinstance(sources, str):
                return json.loads(sources)
    except Exception:
        pass
    return []


def _get_default_config(agent: str, task_type: str, priority: str) -> Dict[str, Any]:
    """Return default configuration when no learnings available."""
    # Determine skill hint
    skill_hint = None
    if task_type and task_type in TASK_TYPE_SKILL_MAP:
        skill_hint = TASK_TYPE_SKILL_MAP[task_type]
    elif agent in AGENT_SKILL_DEFAULTS:
        skill_hint = AGENT_SKILL_DEFAULTS[agent]

    return {
        "template": DEFAULT_TEMPLATE,
        "skill_hint": skill_hint,
        "timeout": TIMEOUT_BY_PRIORITY.get(priority, DEFAULT_TIMEOUT),
        "context_sources": ["memory", "recent_tasks"],
        "confidence": 0.5,
        "source": "defaults",
    }


def _get_exploration_config(agent: str, task_type: str, priority: str) -> Dict[str, Any]:
    """Return random configuration for exploration."""
    active_templates = _get_active_templates()
    if not active_templates:
        active_templates = [DEFAULT_TEMPLATE]

    template = random.choice(active_templates)
    skill_hint = AGENT_SKILL_DEFAULTS.get(agent)

    return {
        "template": template,
        "skill_hint": skill_hint,
        "timeout": TIMEOUT_BY_PRIORITY.get(priority, DEFAULT_TIMEOUT),
        "context_sources": ["memory", "recent_tasks"],
        "confidence": 0.3,  # Lower confidence for exploration
        "source": "exploration",
    }


def apply_template(task: Dict[str, Any], template_name: str) -> Dict[str, Any]:
    """
    Apply a prompt template to a task, enhancing it with proven structure.

    Args:
        task: Raw task dict with title, body, etc.
        template_name: Name of template to apply

    Returns:
        Enhanced task dict with template metadata
    """
    templates_data = _load_templates()
    templates = templates_data.get("templates", {})
    template = templates.get(template_name)

    if not template:
        return task

    # Apply template metadata
    enhanced = task.copy()
    enhanced["prompt_template"] = template_name
    enhanced["template_version"] = template.get("version", 1)
    enhanced["template_structure"] = template.get("structure", [])

    return enhanced


def create_optimized_task(agent: str, title: str, body: str, **kwargs) -> Dict[str, Any]:
    """
    High-level task creation with automatic optimization.

    This is the main entry point for Kublai to use. Queries learnings,
    applies templates, and returns an enhanced task dict.

    Args:
        agent: Target agent
        title: Task title
        body: Task body/description
        **kwargs: Additional task parameters (priority, task_type, etc.)

    Returns:
        Enhanced task dict with:
            - title, body, agent (possibly enhanced)
            - skill_hint (from learning or default)
            - timeout (from learning or default)
            - prompt_template (selected template)
            - prompt_optimization (tracking metadata)
    """
    # Get optimal config from learned patterns
    config = get_optimal_config(
        agent=agent,
        task_type=kwargs.get("task_type"),
        priority=kwargs.get("priority", "normal")
    )

    # Create base task
    task = {
        "title": title,
        "body": body,
        "agent": agent,
    }

    # Apply recommended template
    enhanced = apply_template(task, config.get("template", DEFAULT_TEMPLATE))

    # Add learned parameters (only if not already specified)
    if "skill_hint" not in kwargs and config.get("skill_hint"):
        enhanced["skill_hint"] = config["skill_hint"]
    if "timeout" not in kwargs and config.get("timeout"):
        enhanced["timeout"] = config["timeout"]
    if config.get("context_sources"):
        enhanced["context_sources"] = config["context_sources"]

    # Track what we used for later analysis
    enhanced["prompt_optimization"] = {
        "template": config.get("template"),
        "confidence": config.get("confidence"),
        "source": config.get("source"),
        "applied_at": datetime.now().isoformat(),
    }

    # Merge in any additional kwargs
    for key, value in kwargs.items():
        if key not in enhanced:
            enhanced[key] = value

    return enhanced


def get_optimizer_stats() -> Dict[str, Any]:
    """
    Get statistics about the optimizer for monitoring.

    Returns:
        Dict with optimizer configuration and template counts
    """
    templates_data = _load_templates()
    templates = templates_data.get("templates", {})

    active_count = sum(1 for t in templates.values() if t.get("status") == "active")
    deprecated_count = sum(1 for t in templates.values() if t.get("status") == "deprecated")

    return {
        "optimization_enabled": OPTIMIZATION_ENABLED,
        "epsilon_greedy_rate": EPSILON_GREEDY_RATE,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "templates_total": len(templates),
        "templates_active": active_count,
        "templates_deprecated": deprecated_count,
        "default_template": DEFAULT_TEMPLATE,
    }


# CLI interface for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Kublai Task Optimizer")
    parser.add_argument("--agent", default="temujin", help="Agent to optimize for")
    parser.add_argument("--task-type", help="Task type classification")
    parser.add_argument("--priority", default="normal", help="Task priority")
    parser.add_argument("--stats", action="store_true", help="Show optimizer stats")
    args = parser.parse_args()

    if args.stats:
        stats = get_optimizer_stats()
        print(json.dumps(stats, indent=2))
    else:
        config = get_optimal_config(
            agent=args.agent,
            task_type=args.task_type,
            priority=args.priority
        )
        print("Optimal config:")
        print(json.dumps(config, indent=2))

        print("\n--- Creating optimized task ---")
        task = create_optimized_task(
            agent=args.agent,
            title="Test Task",
            body="This is a test task body.",
            priority=args.priority,
            task_type=args.task_type,
        )
        print(json.dumps(task, indent=2))
