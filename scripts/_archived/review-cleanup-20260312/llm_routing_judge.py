#!/usr/bin/env python3
"""
llm_routing_judge.py — Predict optimal agent for task routing accuracy measurement.

Uses an LLM to rank which agent is best suited for a task, providing ground truth
for routing accuracy metrics.

Usage:
    from llm_routing_judge import predict_optimal_agent

    prediction = predict_optimal_agent("Fix bug in payment API", agents=["temujin", "jochi"])
    # Returns: {"optimal_agent": "temujin", "confidence": 0.9, "rankings": {...}}

    # CLI usage
    python3 llm_routing_judge.py --task "Research competitor pricing" --show
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from kurultai_paths import LOGS_DIR, VALID_AGENTS as _VALID_AGENTS
    from kurultai_ledger import append_ledger
except ImportError:
    LOGS_DIR = Path("/Users/kublai/.openclaw/agents/main/logs")
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    _VALID_AGENTS = ["temujin", "mongke", "chagatai", "jochi", "ogedei", "kublai", "tolui"]

    def append_ledger(entry):
        # Fallback for standalone testing
        pass

# Cache file for predictions (reduces API calls for similar tasks)
PREDICTION_CACHE_FILE = LOGS_DIR / "routing-prediction-cache.json"
PREDICTION_CACHE_TTL_S = 3600  # 1 hour

# Valid agents (imported from kurultai_paths, converted to list)
VALID_AGENTS = list(_VALID_AGENTS)

# Agent domain descriptions for prompt
AGENT_DESCRIPTIONS = {
    "temujin": "Full-stack development, coding, debugging, deployment, API design, system architecture, bug fixes, feature implementation, scripts, database schemas",
    "mongke": "Research, investigation, market analysis, information gathering, competitor analysis, benchmarking, trend discovery, source collection",
    "chagatai": "Content writing, documentation, blog posts, communication, changelogs, social media, marketing copy, tutorials, guides, summaries",
    "jochi": "Testing, security audit, code review, anomaly detection, performance analysis, vulnerability scanning, error investigation, compliance, triage",
    "ogedei": "Operations, monitoring, infrastructure, deployment pipelines, health checks, backups, incident response, cron jobs, resource management",
    "kublai": "Coordination, triage, prioritization, system-wide assessment, backlog management, routing decisions, workload balancing, status reports",
    "tolui": "Truth verification, honest assessment, quality gates, scope creep detection, calling out unrealistic expectations, completion verification"
}

# Judge prompt template
ROUTING_JUDGE_PROMPT = """You are a task routing expert for a multi-agent AI system.

Given a task description, rank which agent would be BEST suited to handle it.

Agents:
{agent_descriptions}

Task: {task_summary}

Rate each agent 0-10 on how well they fit this task.
Consider:
1. Domain expertise match (primary factor)
2. Task complexity appropriateness
3. Typical task type for this agent

Output ONLY valid JSON, no other text:
{{"rankings": {{"agent_name": score, ...}}, "optimal_agent": "agent_name", "confidence": 0.0-1.0, "reasoning": "Brief explanation"}}"""


def _get_cache_key(task_text: str, agents: list[str]) -> str:
    """Generate cache key from task text and agent list."""
    content = f"{task_text}|{','.join(sorted(agents))}"
    return hashlib.md5(content.encode()).hexdigest()


def _load_cache() -> dict:
    """Load prediction cache from disk."""
    if not PREDICTION_CACHE_FILE.exists():
        return {}
    try:
        with open(PREDICTION_CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    """Save prediction cache to disk."""
    try:
        with open(PREDICTION_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def _call_llm_judge(task_text: str, agents: list[str], model: str = None) -> Optional[dict]:
    """Call LLM to get routing prediction.

    Attempts to use OpenRouter API if configured, otherwise returns None
    (caller should use fallback heuristics).
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None

    # Build agent descriptions for prompt
    agent_descriptions = "\n".join(
        f"- {agent}: {AGENT_DESCRIPTIONS.get(agent, 'General purpose')}"
        for agent in agents
    )

    prompt = ROUTING_JUDGE_PROMPT.format(
        agent_descriptions=agent_descriptions,
        task_summary=task_text
    )

    # Use Haiku for fast/cheap routing predictions
    model = model or "anthropic/claude-haiku-4-5-20251001"

    try:
        import requests

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,  # Low temperature for consistency
                "max_tokens": 500,
            },
            timeout=10,
        )

        if response.status_code != 200:
            return None

        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse JSON from response
        # Handle potential markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        prediction = json.loads(content.strip())

        # Validate structure
        if "rankings" not in prediction or "optimal_agent" not in prediction:
            return None

        # Normalize confidence to 0-1 range
        confidence = prediction.get("confidence", 0.5)
        if confidence > 1:
            confidence = confidence / 10  # Handle 0-10 scale
        prediction["confidence"] = min(1.0, max(0.0, confidence))

        # Add metadata
        prediction["model"] = model
        prediction["predicted_at"] = datetime.now().isoformat()

        return prediction

    except Exception as e:
        print(f"[routing_judge] LLM call failed: {e}", file=sys.stderr)
        return None


def _fallback_heuristic(task_text: str, agents: list[str]) -> dict:
    """Fallback routing prediction using keyword matching.

    Used when LLM is unavailable. Less accurate but always works.
    """
    from task_intake import AGENT_KEYWORDS, route_by_text

    # Get keyword-based routing
    routed_agent = route_by_text(task_text)

    # Build rankings based on keyword overlap
    text_lower = task_text.lower()
    rankings = {}
    for agent in agents:
        keywords = AGENT_KEYWORDS.get(agent, [])
        score = sum(2 for kw in keywords if kw in text_lower)
        rankings[agent] = min(10, score)

    # Ensure optimal agent is highest
    if routed_agent in agents:
        rankings[routed_agent] = max(rankings.values()) + 2

    optimal = max(rankings.keys(), key=lambda a: rankings[a])

    return {
        "rankings": rankings,
        "optimal_agent": optimal,
        "confidence": 0.5,  # Lower confidence for heuristic
        "reasoning": "Keyword-based fallback (LLM unavailable)",
        "model": "heuristic",
        "predicted_at": datetime.now().isoformat()
    }


def predict_optimal_agent(
    task_text: str,
    agents: list[str] = None,
    use_cache: bool = True,
    task_id: str = None,
) -> Optional[dict]:
    """Predict which agent is best suited for a task.

    Args:
        task_text: Task description/title
        agents: List of agents to consider (default: all)
        use_cache: Whether to use cached predictions
        task_id: Optional task_id for event emission

    Returns:
        Dict with:
        - optimal_agent: Best agent for this task
        - confidence: 0.0-1.0 confidence in prediction
        - rankings: Dict of {agent: score} for all agents
        - reasoning: Brief explanation
        - model: Model used for prediction
        - predicted_at: Timestamp
    """
    agents = agents or VALID_AGENTS
    agents = [a for a in agents if a in VALID_AGENTS]

    if not agents:
        return None

    # Check cache
    if use_cache:
        cache = _load_cache()
        cache_key = _get_cache_key(task_text, agents)
        cached = cache.get(cache_key)

        if cached:
            # Check TTL
            try:
                predicted_at = datetime.fromisoformat(cached.get("predicted_at", ""))
                age_s = (datetime.now() - predicted_at).total_seconds()
                if age_s < PREDICTION_CACHE_TTL_S:
                    return cached
            except (ValueError, TypeError):
                pass

    # Try LLM judge
    prediction = _call_llm_judge(task_text, agents)

    # Fallback to heuristic if LLM unavailable
    if not prediction:
        prediction = _fallback_heuristic(task_text, agents)

    # Update cache
    if use_cache and prediction:
        cache = _load_cache()
        cache_key = _get_cache_key(task_text, agents)
        cache[cache_key] = prediction

        # Prune old entries (keep last 1000)
        if len(cache) > 1000:
            cache = dict(sorted(
                cache.items(),
                key=lambda x: x[1].get("predicted_at", ""),
                reverse=True
            )[:1000])

        _save_cache(cache)

    # Emit event to ledger
    if prediction and task_id:
        try:
            append_ledger({
                "event": "ROUTING_PREDICTED",
                "task_id": task_id,
                "ts": prediction["predicted_at"],
                "optimal_agent": prediction["optimal_agent"],
                "confidence": prediction["confidence"],
                "agent_rankings": prediction["rankings"],
                "model_version": prediction.get("model", "unknown"),
            })
        except Exception:
            pass

    return prediction


def compute_routing_accuracy_score(
    assigned_agent: str,
    prediction: dict,
) -> tuple[int, bool]:
    """Compute routing accuracy score based on prediction.

    Args:
        assigned_agent: Agent that was assigned the task
        prediction: Prediction dict from predict_optimal_agent

    Returns:
        (score, was_optimal):
        - score: 0-3 scale (3=optimal, 2=2nd, 1=3rd+, 0=unknown)
        - was_optimal: True if assigned_agent == optimal_agent
    """
    if not prediction:
        return 0, False

    rankings = prediction.get("rankings", {})
    if not rankings:
        return 0, False

    optimal_agent = prediction.get("optimal_agent")
    was_optimal = (assigned_agent == optimal_agent)

    # Sort agents by score descending
    sorted_agents = sorted(
        rankings.keys(),
        key=lambda a: rankings.get(a, 0),
        reverse=True
    )

    try:
        rank = sorted_agents.index(assigned_agent) + 1
    except ValueError:
        return 0, False

    # Score mapping
    if rank == 1:
        return 3, was_optimal
    elif rank == 2:
        return 2, was_optimal
    else:
        return 1, was_optimal


def main():
    parser = argparse.ArgumentParser(description="LLM routing judge for task accuracy")
    parser.add_argument("--task", required=True, help="Task description to analyze")
    parser.add_argument("--agents", default=",".join(VALID_AGENTS),
                        help="Comma-separated list of agents")
    parser.add_argument("--show", action="store_true", help="Print detailed output")
    parser.add_argument("--assigned", help="Assigned agent (to compute accuracy)")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache")
    args = parser.parse_args()

    agents = [a.strip() for a in args.agents.split(",") if a.strip() in VALID_AGENTS]

    prediction = predict_optimal_agent(
        args.task,
        agents=agents,
        use_cache=not args.no_cache,
    )

    if not prediction:
        print("Failed to generate prediction")
        return 1

    if args.show:
        print(f"\nTask: {args.task}")
        print(f"\nOptimal Agent: {prediction['optimal_agent']}")
        print(f"Confidence: {prediction['confidence']:.0%}")
        print(f"Model: {prediction.get('model', 'unknown')}")
        print(f"Reasoning: {prediction.get('reasoning', 'N/A')}")

        print("\nAgent Rankings:")
        sorted_rankings = sorted(
            prediction["rankings"].items(),
            key=lambda x: x[1],
            reverse=True
        )
        for agent, score in sorted_rankings:
            marker = " <-- OPTIMAL" if agent == prediction["optimal_agent"] else ""
            print(f"  {agent}: {score}/10{marker}")

        if args.assigned:
            score, was_optimal = compute_routing_accuracy_score(args.assigned, prediction)
            print(f"\nAssigned Agent: {args.assigned}")
            print(f"Routing Accuracy Score: {score}/3")
            print(f"Was Optimal: {was_optimal}")
    else:
        # JSON output
        print(json.dumps(prediction, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
