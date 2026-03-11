#!/usr/bin/env python3
"""
Hypothesis Generator for Autoresearch

Generates testable hypotheses from:
- KublaiLearning nodes (learned patterns from weekly analysis)
- Task failure patterns (what keeps failing)
- Duration outliers (what's unusually slow)
- Agent reflection feedback (what agents complain about)

Each hypothesis is:
- One variable change
- Measurable impact
- Priority-ranked by confidence * expected_impact

Usage:
    python3 hypothesis_generator.py --agent temujin
    python3 hypothesis_generator.py --all
    python3 hypothesis_generator.py --from-learning kl-abc123

Example hypotheses:
    "Using skill hint /horde-implement for Temujin implementation tasks will improve success rate by 8%"
    "Increasing router_scorer learning rate from 0.001 to 0.01 will improve routing quality by 5%"
    "Setting timeout to 3600s for Mongke research tasks will reduce no_output completions by 15%"
"""

import os
import sys
import json
import argparse
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver
from kublai_learning_queries import LearningQueries


@dataclass
class Hypothesis:
    """A testable hypothesis for autoresearch experimentation."""
    id: str
    agent: str
    description: str  # Human-readable hypothesis statement
    target_files: List[str]  # Files this hypothesis would modify
    expected_impact: str  # "success_rate:+5%", "duration:-10%", etc.
    baseline_metric: float  # Current baseline value
    confidence: float  # 0.0-1.0 based on sample size and evidence strength
    learning_id: Optional[str] = None  # Source KublaiLearning node, if applicable
    variable_type: str = "unknown"  # model, prompt_template, skill_hint, timeout, config
    control_value: str = ""  # Current value
    treatment_value: str = ""  # Proposed new value
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "pending"  # pending, testing, validated, rejected

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        # Convert sets to lists if any
        return d

    @property
    def priority_score(self) -> float:
        """Calculate priority as confidence * expected_impact_magnitude."""
        # Parse expected_impact to get magnitude
        try:
            impact_str = self.expected_impact.split(":")[1]  # e.g., "+5%"
            magnitude = abs(float(impact_str.replace("%", "").replace("+", "")))
        except (IndexError, ValueError):
            magnitude = 5.0  # Default assumption

        return self.confidence * magnitude


@dataclass
class FailurePattern:
    """Pattern identified from task failures."""
    agent: str
    failure_type: str  # timeout, no_output, error, etc.
    frequency: int
    sample_size: int
    failure_rate: float
    common_context: Dict[str, Any]


@dataclass
class DurationOutlier:
    """Task duration outlier analysis."""
    agent: str
    task_type: str
    p50_duration: float
    p95_duration: float
    outlier_count: int
    outlier_threshold: float


class HypothesisGenerator:
    """
    Generate testable hypotheses from Kurultai data.

    Sources:
    1. KublaiLearning nodes - learned patterns from weekly analysis
    2. Task failure patterns - what keeps failing
    3. Duration outliers - what's unusually slow
    4. Agent reflection feedback - what agents complain about
    """

    def __init__(self, driver):
        """Initialize with Neo4j driver."""
        self.driver = driver
        self.queries = LearningQueries(driver)

        # Common file locations for hypothesis targeting
        self.file_map = {
            "model": ["openclaw.json", "config.json"],
            "timeout": ["scripts/task_intake.py", "openclaw.json"],
            "skill_hint": ["scripts/task_intake.py", "scripts/kublai_task_router.py"],
            "prompt_template": ["scripts/task_intake.py", "scripts/kublai_task_optimizer.py"],
            "router_scorer": ["scripts/kublai_task_router.py"],
            "learning_rate": ["scripts/kublai_task_router.py"],
            "context": ["scripts/task_intake.py"],
        }

    def generate_for_agent(self, agent: str, limit: int = 5) -> List[Hypothesis]:
        """
        Generate top N hypotheses for a specific agent.

        Combines hypotheses from all sources and prioritizes them.

        Args:
            agent: Agent name (temujin, mongke, ogedei, etc.)
            limit: Maximum number of hypotheses to return

        Returns:
            List of Hypothesis objects sorted by priority
        """
        all_hypotheses = []

        # 1. Generate from KublaiLearning nodes
        learning_hypotheses = self._generate_from_learnings(agent)
        all_hypotheses.extend(learning_hypotheses)

        # 2. Generate from failure patterns
        failure_hypotheses = self._generate_from_failures(agent)
        all_hypotheses.extend(failure_hypotheses)

        # 3. Generate from duration outliers
        duration_hypotheses = self._generate_from_durations(agent)
        all_hypotheses.extend(duration_hypotheses)

        # 4. Generate from reflection feedback
        reflection_hypotheses = self._generate_from_reflections(agent)
        all_hypotheses.extend(reflection_hypotheses)

        # Prioritize and limit
        prioritized = self.prioritize(all_hypotheses)

        return prioritized[:limit]

    def generate_from_learning(self, learning_id: str) -> Optional[Hypothesis]:
        """
        Convert a specific KublaiLearning node into a testable hypothesis.

        Args:
            learning_id: The learning_id of a KublaiLearning node

        Returns:
            Hypothesis object or None if learning not found
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (l:KublaiLearning {learning_id: $learning_id})
                RETURN l
            """, learning_id=learning_id)

            record = result.single()
            if not record:
                return None

            learning = dict(record["l"])

        return self._convert_learning_to_hypothesis(learning)

    def prioritize(self, hypotheses: List[Hypothesis]) -> List[Hypothesis]:
        """
        Sort hypotheses by confidence * expected_impact.

        Args:
            hypotheses: List of Hypothesis objects

        Returns:
            Sorted list with highest priority first
        """
        return sorted(hypotheses, key=lambda h: h.priority_score, reverse=True)

    def _generate_from_learnings(self, agent: str) -> List[Hypothesis]:
        """Generate hypotheses from active KublaiLearning nodes."""
        hypotheses = []

        with self.driver.session() as session:
            where_clause = "WHERE l.agent_filter = $agent" if agent else "WHERE l.agent_filter IS NULL OR l.agent_filter = '*'"

            result = session.run(f"""
                MATCH (l:KublaiLearning)
                {where_clause}
                  AND l.status = 'active'
                  AND l.valid_until > datetime()
                  AND l.confidence > 0.5
                RETURN l
                ORDER BY l.confidence DESC, l.sample_size DESC
                LIMIT 20
            """, agent=agent or "")

            for record in result:
                learning = dict(record["l"])
                hypothesis = self._convert_learning_to_hypothesis(learning)
                if hypothesis:
                    hypotheses.append(hypothesis)

        return hypotheses

    def _convert_learning_to_hypothesis(self, learning: Dict[str, Any]) -> Optional[Hypothesis]:
        """Convert a KublaiLearning node to a Hypothesis object."""
        try:
            recommendation = json.loads(learning.get("recommendation", "{}"))
            evidence = json.loads(learning.get("evidence", "{}"))

            learning_type = learning.get("learning_type", "unknown")
            agent_filter = learning.get("agent_filter", "all")
            confidence = learning.get("confidence", 0.5)
            pattern_key = learning.get("pattern_key", "")

            # Generate hypothesis based on learning type
            if learning_type == "skill_hint":
                skill = recommendation.get("skill_hint", pattern_key)
                # Normalize skill hint (remove leading/trailing slashes)
                if skill:
                    skill = skill.strip().lstrip("/")
                if not skill:
                    skill = pattern_key or "unknown"
                success_rate = recommendation.get("expected_success_rate", "0.6")
                return Hypothesis(
                    id=f"hyp-{uuid.uuid4().hex[:8]}",
                    agent=agent_filter,
                    description=f"Using skill hint /{skill} for {agent_filter} tasks will improve success rate",
                    target_files=self.file_map.get("skill_hint", []),
                    expected_impact=f"success_rate:+{self._estimate_improvement(success_rate)}%",
                    baseline_metric=float(success_rate) if success_rate else 0.6,
                    confidence=confidence,
                    learning_id=learning.get("learning_id"),
                    variable_type="skill_hint",
                    control_value="none",
                    treatment_value=skill
                )

            elif learning_type == "timeout":
                bucket = recommendation.get("timeout_bucket", pattern_key.split(":")[-1])
                timeout_sec = recommendation.get("timeout_seconds", 3600)
                return Hypothesis(
                    id=f"hyp-{uuid.uuid4().hex[:8]}",
                    agent=agent_filter,
                    description=f"Setting timeout to {timeout_sec}s for {agent_filter} {bucket} tasks will improve completion rate",
                    target_files=self.file_map.get("timeout", []),
                    expected_impact=f"completion_rate:+5%",
                    baseline_metric=0.8,
                    confidence=confidence,
                    learning_id=learning.get("learning_id"),
                    variable_type="timeout",
                    control_value="default",
                    treatment_value=str(timeout_sec)
                )

            elif learning_type == "prompt_pattern":
                template = pattern_key
                quality = recommendation.get("expected_quality", "0.7")
                quality_lift = evidence.get("quality_lift", "10")
                return Hypothesis(
                    id=f"hyp-{uuid.uuid4().hex[:8]}",
                    agent=agent_filter,
                    description=f"Using prompt template '{template}' for {agent_filter} tasks will improve output quality",
                    target_files=self.file_map.get("prompt_template", []),
                    expected_impact=f"quality:+{quality_lift}%",
                    baseline_metric=float(quality) if quality else 0.7,
                    confidence=confidence,
                    learning_id=learning.get("learning_id"),
                    variable_type="prompt_template",
                    control_value="default",
                    treatment_value=template
                )

            elif learning_type == "model":
                provider = recommendation.get("model_provider", "unknown")
                model_id = recommendation.get("model_id", pattern_key)
                quality = recommendation.get("expected_quality", "0.7")
                return Hypothesis(
                    id=f"hyp-{uuid.uuid4().hex[:8]}",
                    agent=agent_filter,
                    description=f"Using model {provider}:{model_id} for {agent_filter} tasks will improve output quality",
                    target_files=self.file_map.get("model", []),
                    expected_impact=f"quality:+{self._estimate_improvement(quality)}%",
                    baseline_metric=float(quality) if quality else 0.7,
                    confidence=confidence,
                    learning_id=learning.get("learning_id"),
                    variable_type="model",
                    control_value="current",
                    treatment_value=f"{provider}:{model_id}"
                )

            elif learning_type == "domain":
                domain = pattern_key
                target_agent = recommendation.get("agent", agent_filter)
                success_rate = recommendation.get("expected_success_rate", "0.7")
                return Hypothesis(
                    id=f"hyp-{uuid.uuid4().hex[:8]}",
                    agent=target_agent,
                    description=f"Routing {domain} tasks to {target_agent} will improve success rate",
                    target_files=self.file_map.get("router_scorer", []),
                    expected_impact=f"success_rate:+{self._estimate_improvement(success_rate)}%",
                    baseline_metric=float(success_rate) if success_rate else 0.7,
                    confidence=confidence,
                    learning_id=learning.get("learning_id"),
                    variable_type="router_scorer",
                    control_value="current_routing",
                    treatment_value=f"route_{domain}_to_{target_agent}"
                )

            elif learning_type == "context":
                source = pattern_key
                priority = recommendation.get("priority", "medium")
                return Hypothesis(
                    id=f"hyp-{uuid.uuid4().hex[:8]}",
                    agent="all",
                    description=f"Including context source '{source}' in prompt construction will improve task quality",
                    target_files=self.file_map.get("context", []),
                    expected_impact=f"quality:+3%" if priority == "medium" else f"quality:+5%",
                    baseline_metric=0.7,
                    confidence=confidence,
                    learning_id=learning.get("learning_id"),
                    variable_type="context",
                    control_value="excluded",
                    treatment_value=f"include_{source}"
                )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Warning: Could not convert learning to hypothesis: {e}")
            return None

    def _generate_from_failures(self, agent: str) -> List[Hypothesis]:
        """Generate hypotheses from analyzing task failure patterns."""
        hypotheses = []

        with self.driver.session() as session:
            # Get failure patterns by agent and error type
            result = session.run("""
                MATCH (t:Task {agent: $agent})
                WHERE t.created > datetime() - duration('P7D')
                  AND toUpper(t.status) IN ['FAILED', 'failed', 'TIMEOUT', 'timeout', 'NO_OUTPUT', 'no_output']
                WITH t.agent as agent,
                     coalesce(t.error_type, 'unknown') as error_type,
                     coalesce(t.outcome, 'failed') as outcome,
                     count(*) as failure_count,
                     sum(CASE WHEN toUpper(t.status) IN ['FAILED', 'failed', 'TIMEOUT', 'timeout', 'NO_OUTPUT', 'no_output'] THEN 1 ELSE 0 END) as total_failures
                WITH agent, error_type, failure_count, total_failures
                RETURN agent, error_type, failure_count, total_failures
                ORDER BY total_failures DESC
                LIMIT 10
            """, agent=agent)

            patterns = [dict(r) for r in result]

            for pattern in patterns:
                error_type = pattern.get("error_type", "unknown")
                failure_count = pattern.get("total_failures", 0)

                if failure_count < 3:  # Skip rare failures
                    continue

                # Generate hypothesis based on error type
                if "timeout" in error_type.lower():
                    hypotheses.append(Hypothesis(
                        id=f"hyp-{uuid.uuid4().hex[:8]}",
                        agent=agent,
                        description=f"Increasing timeout for {agent} tasks will reduce timeout failures",
                        target_files=self.file_map.get("timeout", []),
                        expected_impact=f"timeout_rate:-20%",
                        baseline_metric=float(failure_count),
                        confidence=0.7,
                        variable_type="timeout",
                        control_value="current_timeout",
                        treatment_value="increased_timeout"
                    ))

                elif "no_output" in error_type.lower():
                    hypotheses.append(Hypothesis(
                        id=f"hyp-{uuid.uuid4().hex[:8]}",
                        agent=agent,
                        description=f"Adding fallback prompts for {agent} tasks will reduce no_output failures",
                        target_files=["scripts/task_intake.py"],
                        expected_impact=f"no_output_rate:-15%",
                        baseline_metric=float(failure_count),
                        confidence=0.6,
                        variable_type="prompt_template",
                        control_value="single_prompt",
                        treatment_value="prompt_with_fallback"
                    ))

                elif "context" in error_type.lower() or "memory" in error_type.lower():
                    hypotheses.append(Hypothesis(
                        id=f"hyp-{uuid.uuid4().hex[:8]}",
                        agent=agent,
                        description=f"Improving context loading for {agent} will reduce context-related failures",
                        target_files=["scripts/task_intake.py"],
                        expected_impact=f"failure_rate:-10%",
                        baseline_metric=float(failure_count),
                        confidence=0.65,
                        variable_type="context",
                        control_value="current_context",
                        treatment_value="improved_context_loading"
                    ))

        return hypotheses

    def _generate_from_durations(self, agent: str) -> List[Hypothesis]:
        """Generate hypotheses from duration outlier analysis."""
        hypotheses = []

        with self.driver.session() as session:
            # Find tasks with unusually high durations
            result = session.run("""
                MATCH (t:Task {agent: $agent})
                WHERE t.created > datetime() - duration('P7D')
                  AND t.duration_seconds IS NOT NULL
                  AND toUpper(t.status) IN ['COMPLETED', 'completed']
                WITH t.agent as agent,
                     t.domain as domain,
                     t.duration_seconds as duration
                WITH agent, domain,
                     count(*) as task_count,
                     percentileCont(duration, 0.5) as p50,
                     percentileCont(duration, 0.95) as p95,
                     avg(duration) as avg_duration
                WHERE task_count >= 5
                RETURN agent, domain, task_count, p50, p95, avg_duration
                ORDER BY p95 DESC
                LIMIT 10
            """, agent=agent)

            for record in result:
                domain = record.get("domain", "unknown")
                p50 = record.get("p50", 0)
                p95 = record.get("p95", 0)
                avg_duration = record.get("avg_duration", 0)

                # Check if p95 is significantly higher than p50 (high variance)
                if p95 > 3 * p50 and p95 > 3600:  # p95 > 3x p50 and > 1 hour
                    hypotheses.append(Hypothesis(
                        id=f"hyp-{uuid.uuid4().hex[:8]}",
                        agent=agent,
                        description=f"Implementing progress checkpoints for {agent} {domain} tasks will reduce duration variance",
                        target_files=["scripts/task_intake.py"],
                        expected_impact=f"duration_variance:-30%",
                        baseline_metric=round(p95 / p50, 1),
                        confidence=0.6,
                        variable_type="config",
                        control_value="no_checkpoints",
                        treatment_value="add_progress_checkpoints"
                    ))

                # Check for consistently slow tasks
                if avg_duration > 7200:  # > 2 hours average
                    hypotheses.append(Hypothesis(
                        id=f"hyp-{uuid.uuid4().hex[:8]}",
                        agent=agent,
                        description=f"Using faster model for {agent} {domain} tasks will reduce average duration",
                        target_files=self.file_map.get("model", []),
                        expected_impact=f"duration:-25%",
                        baseline_metric=round(avg_duration / 60, 1),  # in minutes
                        confidence=0.55,
                        variable_type="model",
                        control_value="current_model",
                        treatment_value="faster_model"
                    ))

        return hypotheses

    def _generate_from_reflections(self, agent: str) -> List[Hypothesis]:
        """Generate hypotheses from agent reflection feedback."""
        hypotheses = []

        # Look for reflection patterns in recent task outcomes
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {agent: $agent})
                WHERE t.created > datetime() - duration('P7D')
                  AND t.reflection_summary IS NOT NULL
                RETURN t.reflection_summary as reflection,
                       t.outcome as outcome,
                       t.domain as domain
                LIMIT 50
            """, agent=agent)

            reflections = [dict(r) for r in result]

            # Common complaint patterns
            complaint_keywords = {
                "context": ["missing context", "insufficient context", "need more context"],
                "tools": ["wrong tool", "better tool", "use different tool"],
                "instructions": ["unclear", "ambiguous", "confusing"],
                "timeout": ["ran out of time", "timeout", "too long"],
            }

            complaint_counts = defaultdict(int)

            for r in reflections:
                reflection = r.get("reflection", "").lower()
                for issue, keywords in complaint_keywords.items():
                    if any(kw in reflection for kw in keywords):
                        complaint_counts[issue] += 1

            # Generate hypotheses for common complaints
            for issue, count in complaint_counts.items():
                if count >= 3:  # Minimum threshold
                    if issue == "context":
                        hypotheses.append(Hypothesis(
                            id=f"hyp-{uuid.uuid4().hex[:8]}",
                            agent=agent,
                            description=f"Increasing context window size for {agent} will reduce context-related complaints",
                            target_files=self.file_map.get("context", []),
                            expected_impact=f"quality:+5%",
                            baseline_metric=float(count),
                            confidence=0.6,
                            variable_type="context",
                            control_value="current_context_size",
                            treatment_value="increased_context_size"
                        ))

                    elif issue == "tools":
                        hypotheses.append(Hypothesis(
                            id=f"hyp-{uuid.uuid4().hex[:8]}",
                            agent=agent,
                            description=f"Improving tool selection for {agent} will reduce tool-related issues",
                            target_files=["scripts/task_intake.py"],
                            expected_impact=f"success_rate:+8%",
                            baseline_metric=float(count),
                            confidence=0.65,
                            variable_type="config",
                            control_value="current_tool_selection",
                            treatment_value="improved_tool_selection"
                        ))

                    elif issue == "timeout":
                        hypotheses.append(Hypothesis(
                            id=f"hyp-{uuid.uuid4().hex[:8]}",
                            agent=agent,
                            description=f"Increasing timeout for {agent} will reduce timeout-related reflections",
                            target_files=self.file_map.get("timeout", []),
                            expected_impact=f"timeout_rate:-15%",
                            baseline_metric=float(count),
                            confidence=0.7,
                            variable_type="timeout",
                            control_value="current_timeout",
                            treatment_value="increased_timeout"
                        ))

        return hypotheses

    def _estimate_improvement(self, value_str: str) -> str:
        """Estimate improvement percentage from a value string."""
        try:
            val = float(value_str)
            # Conservative estimate: 5-15% improvement range
            if val > 0.8:
                return "5"
            elif val > 0.6:
                return "8"
            else:
                return "12"
        except (ValueError, TypeError):
            return "5"


def main():
    parser = argparse.ArgumentParser(
        description='Generate hypotheses for autoresearch experimentation'
    )
    parser.add_argument('--agent', type=str,
                       help='Filter to specific agent (temujin, mongke, etc.)')
    parser.add_argument('--all', action='store_true',
                       help='Generate hypotheses for all agents')
    parser.add_argument('--limit', type=int, default=5,
                       help='Maximum hypotheses per agent (default: 5)')
    parser.add_argument('--from-learning', type=str,
                       help='Generate hypothesis from specific KublaiLearning ID')
    parser.add_argument('--output', type=str,
                       help='Output file path (JSON format)')
    parser.add_argument('--format', type=str, choices=['json', 'tsv', 'table'],
                       default='table', help='Output format')

    args = parser.parse_args()

    driver = get_driver()
    generator = HypothesisGenerator(driver)

    try:
        if args.from_learning:
            # Single hypothesis from learning
            hypothesis = generator.generate_from_learning(args.from_learning)
            if hypothesis:
                hypotheses = [hypothesis]
            else:
                print(f"Error: Learning '{args.from_learning}' not found")
                return 1
        elif args.all:
            # Generate for all agents
            agents = ["temujin", "mongke", "ogedei", "chagatai", "jochi", "tolui"]
            hypotheses = []
            for agent in agents:
                hypotheses.extend(generator.generate_for_agent(agent, args.limit))
        else:
            # Generate for specific agent or default to all
            agent = args.agent or "temujin"
            hypotheses = generator.generate_for_agent(agent, args.limit)

        # Output results
        if not hypotheses:
            print("No hypotheses generated. Possible reasons:")
            print("  - No active KublaiLearning nodes (run kublai_learning_generator.py first)")
            print("  - Insufficient task data for analysis")
            print("  - Agent has no failure patterns or outliers")
            return 0

        if args.format == 'json':
            output = json.dumps([h.to_dict() for h in hypotheses], indent=2)
            if args.output:
                with open(args.output, 'w') as f:
                    f.write(output)
                print(f"Wrote {len(hypotheses)} hypotheses to {args.output}")
            else:
                print(output)

        elif args.format == 'tsv':
            lines = ["id\tagent\tdescription\texpected_impact\tconfidence\tpriority_score"]
            for h in hypotheses:
                lines.append(f"{h.id}\t{h.agent}\t{h.description}\t{h.expected_impact}\t{h.confidence:.2f}\t{h.priority_score:.1f}")
            output = "\n".join(lines)
            if args.output:
                with open(args.output, 'w') as f:
                    f.write(output)
                print(f"Wrote {len(hypotheses)} hypotheses to {args.output}")
            else:
                print(output)

        else:  # table format
            print(f"\n{'='*100}")
            print(f"Generated {len(hypotheses)} hypotheses")
            print(f"{'='*100}\n")

            for i, h in enumerate(hypotheses, 1):
                print(f"[{i}] {h.id}")
                print(f"    Agent:       {h.agent}")
                print(f"    Description: {h.description}")
                print(f"    Impact:      {h.expected_impact} (baseline: {h.baseline_metric})")
                print(f"    Confidence:  {h.confidence:.2f}")
                print(f"    Priority:    {h.priority_score:.1f}")
                print(f"    Type:        {h.variable_type} ({h.control_value} → {h.treatment_value})")
                print(f"    Files:       {', '.join(h.target_files) if h.target_files else 'N/A'}")
                if h.learning_id:
                    print(f"    Source:      KublaiLearning/{h.learning_id}")
                print()

        if args.output and args.format == 'table':
            # Also save as JSON for programmatic use
            json_path = args.output.replace('.txt', '.json') if args.output.endswith('.txt') else f"{args.output}.json"
            with open(json_path, 'w') as f:
                json.dump([h.to_dict() for h in hypotheses], f, indent=2)
            print(f"Also saved JSON to {json_path}")

    finally:
        driver.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
