#!/usr/bin/env python3
"""
Model Tracker - Track LLM model usage and success rates per agent.

Storage:
- Neo4j: model_id, model_provider properties on Task nodes
- JSONL: /Users/kublai/.openclaw/agents/main/logs/model-usage.jsonl

Usage:
    from model_tracker import ModelTracker
    tracker = ModelTracker()
    tracker.log_model_usage(task_id, agent, model, provider, success, duration, error_type)
    stats = tracker.get_model_stats(days=7)
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver

LOG_DIR = Path("/Users/kublai/.openclaw/agents/main/logs")
JSONL_FILE = LOG_DIR / "model-usage.jsonl"

# Model provider mapping
PROVIDER_MAPPING = {
    # Anthropic models
    "claude-opus-4-6": "anthropic",
    "claude-sonnet-4-6": "anthropic",
    "claude-haiku-4-5-20251001": "anthropic",
    # Bailian (Alibaba) models
    "qwen3.5-plus": "bailian",
    "qwen3-coder-next": "bailian",
    "kimi-k2.5": "bailian",
    # ZAI models
    "zai-coding/glm-5": "zai-coding",
    # MiniMax models
    "MiniMax-M2.5": "minimax",
    # Local models
    "ollama/lukey03/qwen3.5-9b-abliterated-vision": "ollama",
}


def get_provider_for_model(model_name: str) -> str:
    """Get provider name for a model."""
    if not model_name:
        return "unknown"
    # Check direct mapping first
    if model_name in PROVIDER_MAPPING:
        return PROVIDER_MAPPING[model_name]
    # Check prefixes
    if model_name.startswith("claude-"):
        return "anthropic"
    if model_name.startswith("qwen"):
        return "bailian"
    if model_name.startswith("zai-"):
        return "zai-coding"
    if model_name.startswith("ollama"):
        return "ollama"
    return "unknown"


class ModelTracker:
    def __init__(self):
        self.driver = get_driver()

    def close(self):
        self.driver.close()

    def log_model_usage(
        self,
        task_id: str,
        agent: str,
        model: str,
        success: bool,
        duration_seconds: float = None,
        error_type: str = None,
        input_tokens: int = None,
        output_tokens: int = None,
    ):
        """Log model usage for a task.

        Updates the Task node in Neo4j and appends to JSONL log.
        """
        provider = get_provider_for_model(model)

        # Update Neo4j Task node
        with self.driver.session() as session:
            session.run(
                """
                MATCH (t:Task {task_id: $task_id})
                SET t.model_id = $model_id,
                    t.model_provider = $provider,
                    t.model_success = $success,
                    t.model_duration_seconds = $duration,
                    t.model_error_type = $error_type,
                    t.model_input_tokens = $input_tokens,
                    t.model_output_tokens = $output_tokens,
                    t.model_updated = datetime()
                """,
                task_id=task_id,
                model_id=model,
                provider=provider,
                success=success,
                duration=duration_seconds,
                error_type=error_type,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        # Append to JSONL log
        self._append_jsonl(
            task_id=task_id,
            agent=agent,
            model=model,
            provider=provider,
            success=success,
            duration_seconds=duration_seconds,
            error_type=error_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def _append_jsonl(
        self,
        task_id: str,
        agent: str,
        model: str,
        provider: str,
        success: bool,
        duration_seconds: float = None,
        error_type: str = None,
        input_tokens: int = None,
        output_tokens: int = None,
    ):
        """Append model usage event to JSONL log."""
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        entry = {
            "event": "MODEL_USAGE",
            "ts": datetime.now().isoformat(),
            "task_id": task_id,
            "agent": agent,
            "model": model,
            "provider": provider,
            "success": success,
            "duration_seconds": duration_seconds,
            "error_type": error_type,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

        with open(JSONL_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_model_stats(self, days: int = 7, agent: str = None):
        """Get model usage statistics.

        Returns per-model stats with success rate, avg duration, error breakdown.
        """
        with self.driver.session() as session:
            if agent:
                result = session.run(
                    """
                    MATCH (t:Task)
                    WHERE t.created > datetime() - duration({days: $days})
                      AND t.agent = $agent
                      AND t.model_id IS NOT NULL
                    WITH
                        t.model_id AS model,
                        t.model_provider AS provider,
                        count(t) AS total,
                        sum(CASE WHEN t.model_success = true THEN 1 ELSE 0 END) AS success,
                        coalesce(avg(t.model_duration_seconds), 0) AS avg_duration,
                        coalesce(sum(t.model_input_tokens), 0) AS total_input_tokens,
                        coalesce(sum(t.model_output_tokens), 0) AS total_output_tokens
                    WITH
                        model,
                        provider,
                        total,
                        success,
                        avg_duration,
                        total_input_tokens,
                        total_output_tokens,
                        CASE WHEN total > 0 THEN round(100.0 * success / total, 1) ELSE 0.0 END AS success_rate
                    RETURN
                        model,
                        provider,
                        total,
                        success,
                        total - success AS failed,
                        success_rate,
                        round(avg_duration, 1) AS avg_duration_seconds,
                        total_input_tokens,
                        total_output_tokens
                    ORDER BY total DESC
                """,
                    days=days,
                    agent=agent,
                )
            else:
                result = session.run(
                    """
                    MATCH (t:Task)
                    WHERE t.created > datetime() - duration({days: $days})
                      AND t.model_id IS NOT NULL
                    WITH
                        t.model_id AS model,
                        t.model_provider AS provider,
                        count(t) AS total,
                        sum(CASE WHEN t.model_success = true THEN 1 ELSE 0 END) AS success,
                        coalesce(avg(t.model_duration_seconds), 0) AS avg_duration,
                        coalesce(sum(t.model_input_tokens), 0) AS total_input_tokens,
                        coalesce(sum(t.model_output_tokens), 0) AS total_output_tokens
                    WITH
                        model,
                        provider,
                        total,
                        success,
                        avg_duration,
                        total_input_tokens,
                        total_output_tokens,
                        CASE WHEN total > 0 THEN round(100.0 * success / total, 1) ELSE 0.0 END AS success_rate
                    RETURN
                        model,
                        provider,
                        total,
                        success,
                        total - success AS failed,
                        success_rate,
                        round(avg_duration, 1) AS avg_duration_seconds,
                        total_input_tokens,
                        total_output_tokens
                    ORDER BY total DESC
                """,
                    days=days,
                )

            return [dict(r) for r in result]

    def get_agent_model_stats(self, days: int = 7):
        """Get per-agent model usage breakdown."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({days: $days})
                  AND t.model_id IS NOT NULL
                WITH
                    t.agent AS agent,
                    t.model_id AS model,
                    t.model_provider AS provider,
                    count(t) AS total,
                    sum(CASE WHEN t.model_success = true THEN 1 ELSE 0 END) AS success
                WITH
                    agent,
                    model,
                    provider,
                    total,
                    success,
                    CASE WHEN total > 0 THEN round(100.0 * success / total, 1) ELSE 0.0 END AS success_rate
                RETURN
                    agent,
                    model,
                    provider,
                    total,
                    success,
                    success_rate
                ORDER BY agent, total DESC
            """,
                days=days,
            )

            # Group by agent
            by_agent = {}
            for r in result:
                agent = r["agent"]
                if agent not in by_agent:
                    by_agent[agent] = []
                by_agent[agent].append(dict(r))

            return by_agent

    def get_model_error_breakdown(self, days: int = 7):
        """Get error type breakdown per model."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({days: $days})
                  AND t.model_id IS NOT NULL
                  AND t.model_success = false
                  AND t.model_error_type IS NOT NULL
                WITH
                    t.model_id AS model,
                    t.model_error_type AS error_type,
                    count(t) AS count
                RETURN
                    model,
                    error_type,
                    count
                ORDER BY model, count DESC
            """,
                days=days,
            )

            # Group by model
            by_model = {}
            for r in result:
                model = r["model"]
                if model not in by_model:
                    by_model[model] = []
                by_model[model].append({"error_type": r["error_type"], "count": r["count"]})

            return by_model

    def get_recent_model_usage(self, limit: int = 50):
        """Get recent model usage events from JSONL log."""
        if not JSONL_FILE.exists():
            return []

        entries = []
        with open(JSONL_FILE) as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))

        # Return most recent entries
        return entries[-limit:]

    def get_provider_stats(self, days: int = 7):
        """Aggregate stats by provider."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({days: $days})
                  AND t.model_provider IS NOT NULL
                WITH
                    t.model_provider AS provider,
                    count(t) AS total,
                    sum(CASE WHEN t.model_success = true THEN 1 ELSE 0 END) AS success,
                    coalesce(avg(t.model_duration_seconds), 0) AS avg_duration
                RETURN
                    provider,
                    total,
                    success,
                    total - success AS failed,
                    CASE WHEN total > 0 THEN round(100.0 * success / total, 1) ELSE 0.0 END AS success_rate,
                    round(avg_duration, 1) AS avg_duration_seconds
                ORDER BY total DESC
            """,
                days=days,
            )

            return [dict(r) for r in result]


# Singleton instance
_tracker = None


def get_tracker():
    """Get or create tracker instance"""
    global _tracker
    if _tracker is None:
        _tracker = ModelTracker()
    return _tracker


if __name__ == "__main__":
    # Test
    tracker = get_tracker()
    print("Model Tracker initialized")
    print("\n=== Model Stats (7 days) ===")
    stats = tracker.get_model_stats(days=7)
    for s in stats:
        print(f"  {s['model']}: {s['total']} tasks, {s['success_rate']}% success, {s['avg_duration_seconds']}s avg")

    print("\n=== Provider Stats ===")
    provider_stats = tracker.get_provider_stats(days=7)
    for p in provider_stats:
        print(f"  {p['provider']}: {p['total']} tasks, {p['success_rate']}% success")

    tracker.close()
