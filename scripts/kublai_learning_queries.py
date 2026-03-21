#!/usr/bin/env python3
"""
Kublai Learning Queries

Analysis query library for extracting success patterns from Neo4j task data.
Each query returns metrics that power the learning engine's recommendations.

Usage:
    from kublai_learning_queries import LearningQueries

    queries = LearningQueries()

    # Get agent-specific prompt patterns
    patterns = queries.get_agent_prompt_patterns('temujin')
    print(patterns)
"""

import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional


class LearningQueries:
    """Neo4j analysis queries for Kublai learning engine."""

    # Minimum sample sizes (from design spec)
    MIN_SAMPLE_AGENT = 5
    MIN_SAMPLE_SYSTEM = 10
    MIN_SAMPLE_HIGH_CONFIDENCE = 15

    # Learning validity period
    LEARNING_TTL_DAYS = 14

    def __init__(self):
        """Initialize learning queries."""
        from neo4j_task_tracker import neo4j_session
        self._neo4j_session = neo4j_session

    def get_agent_prompt_patterns(self, agent: Optional[str] = None,
                                   days: int = 30) -> List[Dict[str, Any]]:
        """
        Query: Which prompt templates work best for each agent?

        Returns templates ranked by:
        - High-quality task count (quality >= 0.7)
        - Average quality score
        - Average duration

        Args:
            agent: Filter to specific agent, or None for all agents
            days: Lookback period in days (default 30)

        Returns:
            List of dicts: {agent, template, high_quality_count, avg_quality, avg_duration, sample_size}
        """
        with self._neo4j_session() as session:
            where_clause = "AND t.agent = $agent" if agent else ""

            # Fetch raw data and parse prompt_construction JSON in Python
            result = session.run(f"""
                MATCH (t:Task)
                WHERE toUpper(t.status) IN ['COMPLETED', 'completed']
                  AND t.completed > datetime() - duration('P{days}D')
                  {where_clause}
                RETURN t.agent as agent,
                       t.prompt_construction as prompt_construction,
                       t.prompt_template as prompt_template,
                       t.data_quality_score as data_quality_score,
                       t.duration_seconds as duration_seconds
            """, agent=agent or "")

            # Group by template in Python
            template_stats = {}

            for record in result:
                agent_name = record.get('agent', 'unknown')
                pc_str = record.get('prompt_construction')
                pt = record.get('prompt_template')
                quality = record.get('data_quality_score', 0.5) or 0.5
                duration = record.get('duration_seconds', 600) or 600

                # Parse template from prompt_construction JSON string
                template = None
                if pc_str:
                    try:
                        pc = json.loads(pc_str) if isinstance(pc_str, str) else pc_str
                        template = pc.get('template_used') or pc.get('template_name')
                    except (json.JSONDecodeError, TypeError):
                        # Try regex fallback
                        match = re.search(r'"template_used":\s*"([^"]+)"', str(pc_str))
                        if match:
                            template = match.group(1)

                if not template and pt:
                    template = pt

                if not template:
                    continue

                key = (agent_name, template)
                if key not in template_stats:
                    template_stats[key] = {
                        'agent': agent_name,
                        'template': template,
                        'sample_size': 0,
                        'high_quality_count': 0,
                        'total_quality': 0.0,
                        'total_duration': 0.0
                    }

                stats = template_stats[key]
                stats['sample_size'] += 1
                stats['total_quality'] += quality
                stats['total_duration'] += duration
                if quality >= 0.7:
                    stats['high_quality_count'] += 1

            # Calculate averages and filter by minimum sample size
            results = []
            for stats in template_stats.values():
                if stats['sample_size'] >= self.MIN_SAMPLE_AGENT:
                    results.append({
                        'agent': stats['agent'],
                        'template': stats['template'],
                        'sample_size': stats['sample_size'],
                        'high_quality_count': stats['high_quality_count'],
                        'avg_quality': stats['total_quality'] / stats['sample_size'],
                        'avg_duration': stats['total_duration'] / stats['sample_size']
                    })

            # Sort by agent then high_quality_count
            results.sort(key=lambda x: (x['agent'], -x['high_quality_count']))
            return results

    def get_skill_hint_effectiveness(self, agent: Optional[str] = None,
                                      days: int = 30) -> List[Dict[str, Any]]:
        """
        Query: Which skill hints produce best results?

        Returns skill hints ranked by success rate and quality.

        Args:
            agent: Filter to specific agent, or None for all agents
            days: Lookback period in days (default 30)

        Returns:
            List of dicts: {agent, hint, total, successes, success_rate, avg_quality}
        """
        with self._neo4j_session() as session:
            where_clause = "AND t.agent = $agent" if agent else ""

            result = session.run(f"""
                MATCH (t:Task)
                WHERE t.skill_hint IS NOT NULL
                  AND t.created > datetime() - duration('P{days}D')
                  {where_clause}
                WITH t.agent as agent,
                     t.skill_hint as hint,
                     count(t) as total,
                     sum(CASE WHEN toUpper(t.status) IN ['COMPLETED', 'completed'] THEN 1 ELSE 0 END) as successes,
                     avg(coalesce(t.data_quality_score, 0.5)) as avg_quality
                WHERE total >= $min_sample
                WITH agent, hint, total, successes, avg_quality,
                     (successes * 1.0 / total) as success_rate
                RETURN agent, hint, total, successes,
                       toFloat(success_rate) as success_rate,
                       toFloat(avg_quality) as avg_quality
                ORDER BY agent, success_rate DESC, total DESC
            """, agent=agent or "", min_sample=self.MIN_SAMPLE_AGENT)

            return [dict(r) for r in result]

    def get_timeout_analysis(self, agent: Optional[str] = None,
                             days: int = 30) -> List[Dict[str, Any]]:
        """
        Query: How do timeouts affect completion quality and efficiency?

        Groups tasks into timeout buckets (short/medium/long/very_long) and analyzes:
        - Average quality per bucket
        - Timeout utilization (actual_duration / timeout)
        - Success rate per bucket

        Args:
            agent: Filter to specific agent, or None for all agents
            days: Lookback period in days (default 30)

        Returns:
            List of dicts: {agent, timeout_bucket, tasks, avg_quality, avg_utilization, success_rate}
        """
        with self._neo4j_session() as session:
            where_clause = "AND t.agent = $agent" if agent else ""

            # Fetch raw data and parse task_params JSON in Python
            result = session.run(f"""
                MATCH (t:Task)
                WHERE toUpper(t.status) IN ['COMPLETED', 'completed', 'FAILED', 'failed']
                  AND t.task_params IS NOT NULL
                  AND t.created > datetime() - duration('P{days}D')
                  {where_clause}
                RETURN t.agent as agent,
                       t.task_params as task_params,
                       t.data_quality_score as data_quality_score,
                       t.duration_seconds as duration_seconds,
                       t.status as status
            """, agent=agent or "")

            # Group by (agent, timeout_bucket) in Python
            bucket_stats = {}

            for record in result:
                agent_name = record.get('agent', 'unknown')
                tp_str = record.get('task_params')
                quality = record.get('data_quality_score', 0.5) or 0.5
                duration = record.get('duration_seconds', 300) or 300
                status = record.get('status', '')

                # Parse timeout_seconds from task_params JSON
                timeout_seconds = None
                if tp_str:
                    try:
                        tp = json.loads(tp_str) if isinstance(tp_str, str) else tp_str
                        timeout_seconds = tp.get('timeout_seconds')
                    except (json.JSONDecodeError, TypeError):
                        # Try regex fallback
                        match = re.search(r'"timeout_seconds":\s*(\d+)', str(tp_str))
                        if match:
                            timeout_seconds = int(match.group(1))

                if not timeout_seconds:
                    continue

                # Determine bucket
                if timeout_seconds < 1800:
                    bucket = 'short'
                elif timeout_seconds < 3600:
                    bucket = 'medium'
                elif timeout_seconds < 7200:
                    bucket = 'long'
                else:
                    bucket = 'very_long'

                key = (agent_name, bucket)
                if key not in bucket_stats:
                    bucket_stats[key] = {
                        'agent': agent_name,
                        'timeout_bucket': bucket,
                        'tasks': 0,
                        'total_quality': 0.0,
                        'total_utilization': 0.0,
                        'successes': 0
                    }

                stats = bucket_stats[key]
                stats['tasks'] += 1
                stats['total_quality'] += quality
                stats['total_utilization'] += (duration / max(timeout_seconds, 1))
                if status.upper() in ['COMPLETED', 'completed']:
                    stats['successes'] += 1

            # Calculate averages and filter
            results = []
            for stats in bucket_stats.values():
                if stats['tasks'] >= self.MIN_SAMPLE_AGENT:
                    results.append({
                        'agent': stats['agent'],
                        'timeout_bucket': stats['timeout_bucket'],
                        'tasks': stats['tasks'],
                        'avg_quality': stats['total_quality'] / stats['tasks'],
                        'avg_utilization': stats['total_utilization'] / stats['tasks'],
                        'success_rate': stats['successes'] / stats['tasks']
                    })

            results.sort(key=lambda x: (x['agent'], -x['tasks']))
            return results

    def get_context_source_value(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Query: Which context sources contribute most to success?

        Analyzes which context sources (memory, recent_tasks, peer_context, etc.)
        are associated with high-quality outcomes.

        Args:
            days: Lookback period in days (default 30)

        Returns:
            List of dicts: {source, frequency, avg_quality, high_quality_rate}
        """
        with self._neo4j_session() as session:
            result = session.run(f"""
                MATCH (t:Task)
                WHERE toUpper(t.status) IN ['COMPLETED', 'completed']
                  AND t.prompt_construction IS NOT NULL
                  AND t.created > datetime() - duration('P{days}D')
                RETURN t.prompt_construction as prompt_construction,
                       t.data_quality_score as data_quality_score
            """)

            # Parse in Python and aggregate
            source_stats = {}

            for record in result:
                pc_str = record.get('prompt_construction')
                quality = record.get('data_quality_score', 0.5) or 0.5

                if not pc_str:
                    continue

                try:
                    pc = json.loads(pc_str) if isinstance(pc_str, str) else pc_str
                    sources = pc.get('context_sources', [])

                    if not isinstance(sources, list):
                        continue

                    for source in sources:
                        if not source:
                            continue

                        if source not in source_stats:
                            source_stats[source] = {
                                'frequency': 0,
                                'total_quality': 0.0,
                                'high_quality_count': 0
                            }

                        source_stats[source]['frequency'] += 1
                        source_stats[source]['total_quality'] += quality
                        if quality >= 0.7:
                            source_stats[source]['high_quality_count'] += 1

                except (json.JSONDecodeError, TypeError):
                    continue

            # Calculate averages and filter
            results = []
            for source, stats in source_stats.items():
                if stats['frequency'] >= self.MIN_SAMPLE_SYSTEM:
                    results.append({
                        'source': source,
                        'frequency': stats['frequency'],
                        'avg_quality': stats['total_quality'] / stats['frequency'],
                        'high_quality_rate': stats['high_quality_count'] / stats['frequency']
                    })

            results.sort(key=lambda x: (-x['avg_quality'], -x['frequency']))
            return results

    def get_model_performance(self, agent: Optional[str] = None,
                              days: int = 30) -> List[Dict[str, Any]]:
        """
        Query: Best model for each agent/task combination?

        Analyzes model performance by:
        - Average quality score
        - Token efficiency (tokens per second)
        - Sample size

        Args:
            agent: Filter to specific agent, or None for all agents
            days: Lookback period in days (default 30)

        Returns:
            List of dicts: {agent, provider, model, avg_quality, token_efficiency, sample_size}
        """
        with self._neo4j_session() as session:
            where_clause = "AND t.agent = $agent" if agent else ""

            result = session.run(f"""
                MATCH (t:Task)
                WHERE toUpper(t.status) IN ['COMPLETED', 'completed']
                  AND t.model_id IS NOT NULL
                  AND t.created > datetime() - duration('P{days}D')
                  {where_clause}
                WITH t.agent as agent,
                     coalesce(t.model_provider, 'unknown') as provider,
                     t.model_id as model,
                     count(*) as sample_size,
                     avg(coalesce(t.data_quality_score, 0.5)) as avg_quality,
                     avg(coalesce(t.total_tokens, 1000) * 1.0 / NULLIF(coalesce(t.duration_seconds, 600), 0)) as token_efficiency
                WHERE sample_size >= $min_sample
                RETURN agent, provider, model, sample_size,
                       toFloat(avg_quality) as avg_quality,
                       toFloat(token_efficiency) as token_efficiency
                ORDER BY agent, avg_quality DESC, sample_size DESC
            """, agent=agent or "", min_sample=self.MIN_SAMPLE_AGENT)

            return [dict(r) for r in result]

    def get_domain_performance(self, agent: Optional[str] = None,
                               days: int = 30) -> List[Dict[str, Any]]:
        """
        Query: Which task domains does each agent excel at?

        Analyzes success rates and quality by task domain.

        Args:
            agent: Filter to specific agent, or None for all agents
            days: Lookback period in days (default 30)

        Returns:
            List of dicts: {agent, domain, total, completed, success_rate, avg_quality}
        """
        with self._neo4j_session() as session:
            where_clause = "AND t.agent = $agent" if agent else ""

            result = session.run(f"""
                MATCH (t:Task)
                WHERE t.domain IS NOT NULL
                  AND t.created > datetime() - duration('P{days}D')
                  {where_clause}
                WITH t.agent as agent,
                     t.domain as domain,
                     count(*) as total,
                     sum(CASE WHEN toUpper(t.status) IN ['COMPLETED', 'completed'] THEN 1 ELSE 0 END) as completed,
                     avg(coalesce(t.data_quality_score, 0.5)) as avg_quality
                WHERE total >= $min_sample
                WITH agent, domain, total, completed, avg_quality,
                     (completed * 1.0 / total) as success_rate
                RETURN agent, domain, total, completed,
                       toFloat(success_rate) as success_rate,
                       toFloat(avg_quality) as avg_quality
                ORDER BY agent, success_rate DESC, total DESC
            """, agent=agent or "", min_sample=self.MIN_SAMPLE_AGENT)

            return [dict(r) for r in result]

    def calculate_confidence(self, sample_size: int, avg_quality: float,
                            is_agent_specific: bool = True) -> float:
        """
        Calculate confidence score for a learning based on sample size and quality.

        Confidence tiers:
        - High confidence (0.9): 15+ samples (agent) or 20+ (system)
        - Medium confidence (0.7): 10-14 samples (agent) or 15-19 (system)
        - Low confidence (0.5): 5-9 samples (agent) or 10-14 (system)

        Args:
            sample_size: Number of tasks in the sample
            avg_quality: Average quality score (0-1 or 0-10)
            is_agent_specific: True if agent-specific, False if system-wide

        Returns:
            Confidence score between 0.0 and 1.0
        """
        threshold = self.MIN_SAMPLE_HIGH_CONFIDENCE if is_agent_specific else 20
        if sample_size >= threshold:
            base_confidence = 0.9
        elif sample_size >= self.MIN_SAMPLE_SYSTEM:
            base_confidence = 0.7
        else:
            base_confidence = 0.5

        # Adjust based on quality - high quality increases confidence
        # Normalize quality to 0-1 range first
        normalized_quality = min(avg_quality / 10.0, avg_quality) if avg_quality > 1 else avg_quality
        quality_boost = (normalized_quality - 0.5) * 0.2  # +/- 0.1 adjustment

        return min(max(base_confidence + quality_boost, 0.3), 0.98)

    def get_baseline_quality(self, agent: Optional[str] = None,
                             days: int = 30) -> float:
        """
        Get baseline task quality for comparison.

        Args:
            agent: Specific agent or None for system-wide baseline
            days: Lookback period

        Returns:
            Baseline average quality score
        """
        with self._neo4j_session() as session:
            where_clause = "AND t.agent = $agent" if agent else ""

            result = session.run(f"""
                MATCH (t:Task)
                WHERE toUpper(t.status) IN ['COMPLETED', 'completed']
                  AND t.data_quality_score IS NOT NULL
                  AND t.created > datetime() - duration('P{days}D')
                  {where_clause}
                RETURN avg(t.data_quality_score) as baseline
            """, agent=agent or "")

            record = result.single()
            return float(record["baseline"]) if record and record["baseline"] else 0.5


if __name__ == "__main__":
    # Test queries
    queries = LearningQueries()

    print("=== Agent Prompt Patterns ===")
    patterns = queries.get_agent_prompt_patterns('temujin')
    for p in patterns[:5]:
        print(f"  {p['agent']}: {p['template']} ({p['sample_size']} tasks, quality={p['avg_quality']:.2f})")

    print("\n=== Skill Hint Effectiveness ===")
    skills = queries.get_skill_hint_effectiveness('temujin')
    for s in skills[:5]:
        print(f"  {s['agent']}: {s['hint']} ({s['success_rate']:.1%} success, quality={s['avg_quality']:.2f})")

    print("\n=== Timeout Analysis ===")
    timeouts = queries.get_timeout_analysis()
    for t in timeouts[:5]:
        print(f"  {t['agent']}: {t['timeout_bucket']} ({t['tasks']} tasks, quality={t['avg_quality']:.2f})")

    print("\n=== Context Source Value ===")
    contexts = queries.get_context_source_value()
    for c in contexts[:5]:
        print(f"  {c['source']}: {c['frequency']}x, quality={c['avg_quality']:.2f}")

    print("\n=== Model Performance ===")
    models = queries.get_model_performance()
    for m in models[:5]:
        print(f"  {m['agent']}: {m['model']} ({m['sample_size']} tasks, quality={m['avg_quality']:.2f})")

    print(f"\n=== Baseline Quality ===")
    baseline = queries.get_baseline_quality()
    print(f"  System-wide: {baseline:.2f}")

    pass
