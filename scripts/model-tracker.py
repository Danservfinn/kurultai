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
from neo4j_task_tracker import get_driver, close_driver

LOG_DIR = Path("/Users/kublai/.openclaw/agents/main/logs")
JSONL_FILE = LOG_DIR / "model-usage.jsonl"

# Model provider mapping
PROVIDER_MAPPING = {
    # Anthropic models
    "claude-opus-4-6": "anthropic",
    "claude-sonnet-4-6": "anthropic",
    "claude-haiku-4-5": "anthropic",
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
        if self.driver:
            close_driver()
            self.driver = None

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


def compare_models(model1: str, model2: str, days: int = 7):
    """Compare two models side-by-side."""
    tracker = get_tracker()

    # Get stats for each model
    stats1_all = tracker.get_model_stats(days=days)
    stats2_all = tracker.get_model_stats(days=days)

    # Find matching models
    stats1 = next((s for s in stats1_all if s['model'] == model1), None)
    stats2 = next((s for s in stats2_all if s['model'] == model2), None)

    if not stats1:
        print(f"Model '{model1}' not found in data")
        tracker.close()
        return

    if not stats2:
        print(f"Model '{model2}' not found in data")
        tracker.close()
        return

    print(f"\n# Model Comparison ({days} days)")
    print(f"\n## {model1}")
    print(f"  Tasks: {stats1['total']}")
    print(f"  Success: {stats1['success']}/{stats1['total']} ({stats1['success_rate']}%)")
    print(f"  Failed: {stats1['failed']}")
    print(f"  Avg Duration: {stats1['avg_duration_seconds']}s")
    print(f"  Input Tokens: {stats1.get('total_input_tokens', 0)}")
    print(f"  Output Tokens: {stats1.get('total_output_tokens', 0)}")

    print(f"\n## {model2}")
    print(f"  Tasks: {stats2['total']}")
    print(f"  Success: {stats2['success']}/{stats2['total']} ({stats2['success_rate']}%)")
    print(f"  Failed: {stats2['failed']}")
    print(f"  Avg Duration: {stats2['avg_duration_seconds']}s")
    print(f"  Input Tokens: {stats2.get('total_input_tokens', 0)}")
    print(f"  Output Tokens: {stats2.get('total_output_tokens', 0)}")

    # Calculate improvement
    print(f"\n## Improvement ({model2} vs {model1})")
    if stats1['total'] > 0 and stats2['total'] > 0:
        sr_diff = stats2['success_rate'] - stats1['success_rate']
        print(f"  Success Rate: {sr_diff:+.1f}%")

        dur_diff = stats1['avg_duration_seconds'] - stats2['avg_duration_seconds']
        if stats1['avg_duration_seconds'] > 0:
            dur_pct = (dur_diff / stats1['avg_duration_seconds']) * 100
            print(f"  Duration: {dur_diff:+.1f}s ({dur_pct:+.1f}%)")

    tracker.close()


def export_jsonl(output_path: str, days: int = 7):
    """Export model usage data to JSONL."""
    import json as _json

    tracker = get_tracker()
    entries = tracker.get_recent_model_usage(limit=10000)

    # Filter by date if needed
    if days > 0:
        cutoff = datetime.now().timestamp() - (days * 86400)
        from datetime import datetime as _dt
        filtered = []
        for e in entries:
            try:
                ts = _dt.fromisoformat(e['ts'].replace('Z', '+00:00')).timestamp()
                if ts >= cutoff:
                    filtered.append(e)
            except:
                filtered.append(e)
        entries = filtered

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        for e in entries:
            f.write(_json.dumps(e) + '\n')

    print(f"Exported {len(entries)} entries to {output_path}")
    tracker.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='LLM Model Performance Tracker')
    parser.add_argument('--summary', action='store_true', help='Show overall model summary')
    parser.add_argument('--by-agent', action='store_true', help='Show per-agent breakdown')
    parser.add_argument('--by-provider', action='store_true', help='Show per-provider breakdown')
    parser.add_argument('--compare', nargs=2, metavar=('MODEL1', 'MODEL2'), help='Compare two models')
    parser.add_argument('--export', metavar='PATH', help='Export to JSONL file')
    parser.add_argument('--days', type=int, default=7, help='Days to look back (default: 7)')
    parser.add_argument('--agent', metavar='NAME', help='Filter by agent name')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--errors', action='store_true', help='Show error breakdown')

    args = parser.parse_args()

    tracker = get_tracker()

    if args.summary:
        stats = tracker.get_model_stats(days=args.days, agent=args.agent)
        if args.json:
            import json as _json
            print(_json.dumps(stats, indent=2, default=str))
        else:
            print(f"\n# Model Performance Summary ({args.days} days)")
            if args.agent:
                print(f"Agent: {args.agent}")
            print(f"\n{'Model':<30} {'Tasks':>8} {'Success':>8} {'Failed':>8} {'Rate':>7} {'AvgDur':>8}")
            print("-" * 77)
            for s in stats:
                print(f"{s['model']:<30} {s['total']:>8} {s['success']:>8} {s['failed']:>8} {s['success_rate']:>6.1f}% {s['avg_duration_seconds']:>8.1f}s")

    elif args.by_agent:
        by_agent = tracker.get_agent_model_stats(days=args.days)
        if args.json:
            import json as _json
            print(_json.dumps(by_agent, indent=2, default=str))
        else:
            print(f"\n# Per-Agent Model Breakdown ({args.days} days)")
            for agent, models in sorted(by_agent.items()):
                print(f"\n## {agent}")
                print(f"{'Model':<30} {'Tasks':>8} {'Success':>8} {'Rate':>7}")
                print("-" * 59)
                for m in models[:10]:
                    print(f"{m['model']:<30} {m['total']:>8} {m['success']:>8} {m['success_rate']:>6.1f}%")

    elif args.by_provider:
        stats = tracker.get_provider_stats(days=args.days)
        if args.json:
            import json as _json
            print(_json.dumps(stats, indent=2, default=str))
        else:
            print(f"\n# Provider Performance ({args.days} days)")
            print(f"\n{'Provider':<15} {'Tasks':>8} {'Success':>8} {'Failed':>8} {'Rate':>7} {'AvgDur':>8}")
            print("-" * 62)
            for s in stats:
                print(f"{s['provider']:<15} {s['total']:>8} {s['success']:>8} {s['failed']:>8} {s['success_rate']:>6.1f}% {s['avg_duration_seconds']:>8.1f}s")

    elif args.compare:
        tracker.close()
        compare_models(args.compare[0], args.compare[1], days=args.days)
        exit(0)

    elif args.export:
        tracker.close()
        export_jsonl(args.export, days=args.days)
        exit(0)

    elif args.errors:
        by_model = tracker.get_model_error_breakdown(days=args.days)
        if args.json:
            import json as _json
            print(_json.dumps(by_model, indent=2, default=str))
        else:
            print(f"\n# Error Breakdown by Model ({args.days} days)")
            for model, errors in sorted(by_model.items()):
                print(f"\n## {model}")
                for e in errors[:10]:
                    print(f"  {e['error_type']}: {e['count']}")

    else:
        # Default: show summary
        stats = tracker.get_model_stats(days=args.days)
        print(f"\n# Model Performance Summary ({args.days} days)")
        print(f"\n{'Model':<30} {'Tasks':>8} {'Success':>8} {'Failed':>8} {'Rate':>7} {'AvgDur':>8}")
        print("-" * 77)
        for s in stats[:20]:
            print(f"{s['model']:<30} {s['total']:>8} {s['success']:>8} {s['failed']:>8} {s['success_rate']:>6.1f}% {s['avg_duration_seconds']:>8.1f}s")

    tracker.close()
