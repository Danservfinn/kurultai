#!/usr/bin/env python3
"""
Kublai Learning Generator

Runs weekly to analyze task outcomes and generate learned recommendations.
Stores findings as KublaiLearning nodes in Neo4j for Kublai to query
during task creation.

Usage:
    python3 kublai_learning_generator.py --weekly
    python3 kublai_learning_generator.py --agent temujin
    python3 kublai_learning_generator.py --type prompt_patterns
"""

import os
import sys
import argparse
import uuid
import json
from datetime import datetime, timedelta

# Add script directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import neo4j_session
from kublai_learning_queries import LearningQueries


class KublaiLearningGenerator:
    """Generate KublaiLearning nodes from task outcome analysis."""

    # Learning expiry: 14 days from creation
    LEARNING_TTL_DAYS = 14

    # Learning types
    LEARNING_TYPES = [
        'prompt_pattern',
        'skill_hint',
        'timeout',
        'context',
        'model',
        'domain'
    ]

    def __init__(self):
        """Initialize learning generator."""
        self.queries = LearningQueries()
        self.stats = {
            'created': 0,
            'deprecated': 0,
            'skipped': 0,
            'errors': []
        }

    def generate_learning_id(self) -> str:
        """Generate unique learning ID."""
        return f"kl-{uuid.uuid4().hex[:12]}"

    def calculate_valid_until(self) -> str:
        """Calculate expiry date for learnings."""
        valid_date = datetime.now() + timedelta(days=self.LEARNING_TTL_DAYS)
        return valid_date.isoformat()

    def deprecate_old_learnings(self, learning_type: str, pattern_key: str,
                               agent_filter: str = None):
        """
        Mark existing learnings as deprecated when a new one is created.

        Args:
            learning_type: Type of learning (prompt_pattern, skill_hint, etc.)
            pattern_key: The key identifying the pattern (template name, skill hint, etc.)
            agent_filter: Optional agent filter
        """
        with neo4j_session() as session:
            where_parts = [
                "l.learning_type = $learning_type",
                "l.pattern_key = $pattern_key",
                "l.status = 'active'",
                "l.valid_until > datetime()"
            ]
            params = {
                "learning_type": learning_type,
                "pattern_key": pattern_key
            }

            if agent_filter:
                where_parts.append("l.agent_filter = $agent_filter")
                params["agent_filter"] = agent_filter
            else:
                where_parts.append("(l.agent_filter IS NULL OR l.agent_filter = '*')")

            where_clause = " AND ".join(where_parts)

            result = session.run(f"""
                MATCH (l:KublaiLearning)
                WHERE {where_clause}
                SET l.status = 'deprecated',
                    l.deprecated_at = datetime(),
                    l.replaced_by = $new_learning_id
                RETURN count(l) as deprecated_count
            """, **params, new_learning_id=self.generate_learning_id())

            record = result.single()
            if record:
                self.stats['deprecated'] += record.get("deprecated_count", 0)

    def create_prompt_pattern_learnings(self, agent: str = None) -> list:
        """
        Generate learnings about effective prompt templates.

        Creates KublaiLearning nodes for templates that show:
        - High average quality scores
        - Significant sample size
        - Clear performance differences from baseline
        """
        results = []
        try:
            patterns = self.queries.get_agent_prompt_patterns(agent)
        except Exception as e:
            self.stats['errors'].append(f"prompt_pattern: {e}")
            return results

        for pattern in patterns:
            try:
                agent_filter = pattern.get('agent')
                template = pattern.get('template')
                sample_size = pattern.get('sample_size', 0)
                avg_quality = pattern.get('avg_quality', 0.5)

                # Skip if insufficient sample
                if sample_size < self.queries.MIN_SAMPLE_AGENT:
                    self.stats['skipped'] += 1
                    continue

                # Calculate confidence
                confidence = self.queries.calculate_confidence(
                    sample_size, avg_quality, is_agent_specific=True
                )

                # Get baseline for comparison
                baseline = self.queries.get_baseline_quality(agent_filter)
                quality_lift = ((avg_quality - baseline) / max(baseline, 0.1)) * 100

                # Only create learning if quality is above baseline
                if avg_quality <= baseline:
                    self.stats['skipped'] += 1
                    continue

                learning_id = self.generate_learning_id()

                # Deprecate old learnings for this template
                self.deprecate_old_learnings('prompt_pattern', template, agent_filter)

                # Create the learning node
                with neo4j_session() as session:
                    recommendation_json = json.dumps({
                        'action': 'use_template',
                        'template': template,
                        'expected_quality': str(avg_quality),
                        'quality_lift': str(quality_lift)
                    })
                    evidence_json = json.dumps({
                        'high_quality_count': pattern.get('high_quality_count', 0),
                        'avg_quality': str(avg_quality),
                        'avg_duration': str(pattern.get('avg_duration', 0)),
                        'baseline_quality': str(baseline),
                        'total_tasks': sample_size
                    })
                    session.run("""
                        CREATE (l:KublaiLearning {
                            learning_id: $learning_id,
                            learning_type: 'prompt_pattern',
                            agent_filter: $agent_filter,
                            pattern_key: $pattern_key,
                            confidence: $confidence,
                            sample_size: $sample_size,
                            created: datetime(),
                            valid_until: datetime() + duration('P14D'),
                            status: 'active',
                            recommendation: $recommendation,
                            evidence: $evidence
                        })
                    """,
                    learning_id=learning_id,
                    agent_filter=agent_filter,
                    pattern_key=template,
                    confidence=confidence,
                    sample_size=sample_size,
                    avg_quality=avg_quality,
                    quality_lift=round(quality_lift, 1),
                    high_quality_count=pattern.get('high_quality_count', 0),
                    avg_duration=pattern.get('avg_duration', 0),
                    baseline=baseline)

                self.stats['created'] += 1
                results.append({
                    'type': 'prompt_pattern',
                    'agent': agent_filter,
                    'template': template,
                    'confidence': confidence,
                    'sample_size': sample_size
                })

            except Exception as e:
                self.stats['errors'].append(f"prompt_pattern: {e}")

        return results

    def create_skill_hint_learnings(self, agent: str = None) -> list:
        """
        Generate learnings about effective skill hints.

        Creates KublaiLearning nodes for skill hints with high success rates.
        """
        results = []
        try:
            skills = self.queries.get_skill_hint_effectiveness(agent)
        except Exception as e:
            self.stats['errors'].append(f"skill_hint: {e}")
            return results

        for skill in skills:
            try:
                agent_filter = skill.get('agent')
                hint = skill.get('hint')
                total = skill.get('total', 0)
                success_rate = skill.get('success_rate', 0.0)
                avg_quality = skill.get('avg_quality', 0.5)

                # Skip if insufficient sample
                if total < self.queries.MIN_SAMPLE_AGENT:
                    self.stats['skipped'] += 1
                    continue

                # Only learn from high-performing hints
                if success_rate < 0.6:
                    self.stats['skipped'] += 1
                    continue

                confidence = self.queries.calculate_confidence(total, success_rate, is_agent_specific=True)
                learning_id = self.generate_learning_id()

                self.deprecate_old_learnings('skill_hint', hint, agent_filter)

                with neo4j_session() as session:
                    recommendation_json = json.dumps({
                        'action': 'use_skill_hint',
                        'skill_hint': hint,
                        'expected_success_rate': str(round(success_rate, 3)),
                        'expected_quality': str(round(avg_quality, 2))
                    })
                    evidence_json = json.dumps({
                        'success_rate': str(round(success_rate, 3)),
                        'avg_quality': str(round(avg_quality, 2)),
                        'total_tasks': total,
                        'successful_tasks': int(total * success_rate)
                    })
                    session.run("""
                        CREATE (l:KublaiLearning {
                            learning_id: $learning_id,
                            learning_type: 'skill_hint',
                            agent_filter: $agent_filter,
                            pattern_key: $pattern_key,
                            confidence: $confidence,
                            sample_size: $sample_size,
                            created: datetime(),
                            valid_until: datetime() + duration('P14D'),
                            status: 'active',
                            recommendation: $recommendation,
                            evidence: $evidence
                        })
                    """,
                    learning_id=learning_id,
                    agent_filter=agent_filter,
                    pattern_key=hint,
                    confidence=confidence,
                    sample_size=total,
                    recommendation=recommendation_json,
                    evidence=evidence_json)

                self.stats['created'] += 1
                results.append({
                    'type': 'skill_hint',
                    'agent': agent_filter,
                    'hint': hint,
                    'confidence': confidence,
                    'sample_size': total
                })

            except Exception as e:
                self.stats['errors'].append(f"skill_hint: {e}")

        return results

    def create_timeout_learnings(self, agent: str = None) -> list:
        """
        Generate learnings about optimal timeout settings.

        Creates KublaiLearning nodes for timeout buckets that balance
        quality and efficiency.
        """
        results = []
        try:
            timeouts = self.queries.get_timeout_analysis(agent)
        except Exception as e:
            self.stats['errors'].append(f"timeout: {e}")
            return results

        for timeout_data in timeouts:
            try:
                agent_filter = timeout_data.get('agent')
                bucket = timeout_data.get('timeout_bucket')
                tasks = timeout_data.get('tasks', 0)
                avg_quality = timeout_data.get('avg_quality', 0.5)
                avg_utilization = timeout_data.get('avg_utilization', 0.0)
                success_rate = timeout_data.get('success_rate', 0.0)

                # Skip if insufficient sample
                if tasks < self.queries.MIN_SAMPLE_AGENT:
                    self.stats['skipped'] += 1
                    continue

                # Prefer timeouts with good utilization (not too short, not too long)
                if avg_utilization < 0.3 or avg_utilization > 0.95:
                    self.stats['skipped'] += 1
                    continue

                confidence = min(0.8, self.queries.calculate_confidence(tasks, avg_quality))
                learning_id = self.generate_learning_id()

                # Map timeout bucket to actual seconds
                timeout_seconds = {
                    'short': 1800,
                    'medium': 3600,
                    'long': 7200,
                    'very_long': 14400
                }.get(bucket, 3600)

                with neo4j_session() as session:
                    recommendation_json = json.dumps({
                        'action': 'set_timeout',
                        'timeout_bucket': bucket,
                        'timeout_seconds': timeout_seconds,
                        'expected_utilization': str(round(avg_utilization, 2))
                    })
                    evidence_json = json.dumps({
                        'avg_quality': str(round(avg_quality, 2)),
                        'success_rate': str(round(success_rate, 3)),
                        'avg_utilization': str(round(avg_utilization, 2)),
                        'total_tasks': tasks
                    })
                    session.run("""
                        CREATE (l:KublaiLearning {
                            learning_id: $learning_id,
                            learning_type: 'timeout',
                            agent_filter: $agent_filter,
                            pattern_key: $pattern_key,
                            confidence: $confidence,
                            sample_size: $sample_size,
                            created: datetime(),
                            valid_until: datetime() + duration('P14D'),
                            status: 'active',
                            recommendation: $recommendation,
                            evidence: $evidence
                        })
                    """,
                    learning_id=learning_id,
                    agent_filter=agent_filter,
                    pattern_key=f"{agent_filter or 'all'}:{bucket}",
                    confidence=confidence,
                    sample_size=tasks,
                    recommendation=recommendation_json,
                    evidence=evidence_json)

                self.stats['created'] += 1
                results.append({
                    'type': 'timeout',
                    'agent': agent_filter,
                    'bucket': bucket,
                    'confidence': confidence,
                    'sample_size': tasks
                })

            except Exception as e:
                self.stats['errors'].append(f"timeout: {e}")

        return results

    def create_context_learnings(self) -> list:
        """
        Generate learnings about valuable context sources.

        Creates KublaiLearning nodes for context sources that correlate
        with high-quality outcomes.
        """
        results = []
        try:
            contexts = self.queries.get_context_source_value()
        except Exception as e:
            self.stats['errors'].append(f"context: {e}")
            return results

        for context in contexts:
            try:
                source = context.get('source')
                frequency = context.get('frequency', 0)
                avg_quality = context.get('avg_quality', 0.5)
                high_quality_rate = context.get('high_quality_rate', 0.0)

                # Skip if insufficient sample
                if frequency < self.queries.MIN_SAMPLE_SYSTEM:
                    self.stats['skipped'] += 1
                    continue

                # Only recommend high-value sources
                if avg_quality < 0.6:
                    self.stats['skipped'] += 1
                    continue

                confidence = self.queries.calculate_confidence(frequency, avg_quality, is_agent_specific=False)
                learning_id = self.generate_learning_id()

                with neo4j_session() as session:
                    priority = 'high' if avg_quality >= 0.8 else 'medium'
                    recommendation_json = json.dumps({
                        'action': 'include_context',
                        'context_source': source,
                        'priority': priority
                    })
                    evidence_json = json.dumps({
                        'frequency': frequency,
                        'avg_quality': str(round(avg_quality, 2)),
                        'high_quality_rate': str(round(high_quality_rate, 3))
                    })
                    session.run("""
                        CREATE (l:KublaiLearning {
                            learning_id: $learning_id,
                            learning_type: 'context',
                            agent_filter: null,
                            pattern_key: $pattern_key,
                            confidence: $confidence,
                            sample_size: $sample_size,
                            created: datetime(),
                            valid_until: datetime() + duration('P14D'),
                            status: 'active',
                            recommendation: $recommendation,
                            evidence: $evidence
                        })
                    """,
                    learning_id=learning_id,
                    pattern_key=source,
                    confidence=confidence,
                    sample_size=frequency,
                    recommendation=recommendation_json,
                    evidence=evidence_json)

                self.stats['created'] += 1
                results.append({
                    'type': 'context',
                    'source': source,
                    'confidence': confidence,
                    'sample_size': frequency
                })

            except Exception as e:
                self.stats['errors'].append(f"context: {e}")

        return results

    def create_model_learnings(self, agent: str = None) -> list:
        """
        Generate learnings about model performance.

        Creates KublaiLearning nodes for models that perform well
        for specific agents or task types.
        """
        results = []
        try:
            models = self.queries.get_model_performance(agent)
        except Exception as e:
            self.stats['errors'].append(f"model: {e}")
            return results

        for model_data in models:
            try:
                agent_filter = model_data.get('agent')
                provider = model_data.get('provider', 'unknown')
                model = model_data.get('model')
                sample_size = model_data.get('sample_size', 0)
                avg_quality = model_data.get('avg_quality', 0.5)

                # Skip if insufficient sample
                if sample_size < self.queries.MIN_SAMPLE_AGENT:
                    self.stats['skipped'] += 1
                    continue

                # Only recommend high-performing models
                if avg_quality < 0.65:
                    self.stats['skipped'] += 1
                    continue

                confidence = self.queries.calculate_confidence(sample_size, avg_quality)
                learning_id = self.generate_learning_id()

                pattern_key = f"{provider}:{model}"

                with neo4j_session() as session:
                    recommendation_json = json.dumps({
                        'action': 'use_model',
                        'model_provider': provider,
                        'model_id': model,
                        'expected_quality': str(round(avg_quality, 2))
                    })
                    evidence_json = json.dumps({
                        'avg_quality': str(round(avg_quality, 2)),
                        'token_efficiency': str(round(model_data.get('token_efficiency', 0), 2)),
                        'sample_size': sample_size
                    })
                    session.run("""
                        CREATE (l:KublaiLearning {
                            learning_id: $learning_id,
                            learning_type: 'model',
                            agent_filter: $agent_filter,
                            pattern_key: $pattern_key,
                            confidence: $confidence,
                            sample_size: $sample_size,
                            created: datetime(),
                            valid_until: datetime() + duration('P14D'),
                            status: 'active',
                            recommendation: $recommendation,
                            evidence: $evidence
                        })
                    """,
                    learning_id=learning_id,
                    agent_filter=agent_filter,
                    pattern_key=pattern_key,
                    confidence=confidence,
                    sample_size=sample_size,
                    recommendation=recommendation_json,
                    evidence=evidence_json)

                self.stats['created'] += 1
                results.append({
                    'type': 'model',
                    'agent': agent_filter,
                    'model': pattern_key,
                    'confidence': confidence,
                    'sample_size': sample_size
                })

            except Exception as e:
                self.stats['errors'].append(f"model: {e}")

        return results

    def create_domain_learnings(self, agent: str = None) -> list:
        """
        Generate learnings about domain specialization.

        Creates KublaiLearning nodes identifying which agents excel
        at specific task domains.
        """
        results = []
        try:
            domains = self.queries.get_domain_performance(agent)
        except Exception as e:
            self.stats['errors'].append(f"domain: {e}")
            return results

        for domain_data in domains:
            try:
                agent_filter = domain_data.get('agent')
                domain = domain_data.get('domain')
                total = domain_data.get('total', 0)
                success_rate = domain_data.get('success_rate', 0.0)
                avg_quality = domain_data.get('avg_quality', 0.5)

                # Skip if insufficient sample
                if total < self.queries.MIN_SAMPLE_AGENT:
                    self.stats['skipped'] += 1
                    continue

                # Only identify strong domain fits
                if success_rate < 0.7 or avg_quality < 0.6:
                    self.stats['skipped'] += 1
                    continue

                confidence = self.queries.calculate_confidence(total, avg_quality)
                learning_id = self.generate_learning_id()

                with neo4j_session() as session:
                    recommendation_json = json.dumps({
                        'action': 'route_to_agent',
                        'domain': domain,
                        'agent': agent_filter,
                        'expected_success_rate': str(round(success_rate, 3))
                    })
                    evidence_json = json.dumps({
                        'total_tasks': total,
                        'completed_tasks': domain_data.get('completed', 0),
                        'success_rate': str(round(success_rate, 3)),
                        'avg_quality': str(round(avg_quality, 2))
                    })
                    session.run("""
                        CREATE (l:KublaiLearning {
                            learning_id: $learning_id,
                            learning_type: 'domain',
                            agent_filter: $agent_filter,
                            pattern_key: $pattern_key,
                            confidence: $confidence,
                            sample_size: $sample_size,
                            created: datetime(),
                            valid_until: datetime() + duration('P14D'),
                            status: 'active',
                            recommendation: $recommendation,
                            evidence: $evidence
                        })
                    """,
                    learning_id=learning_id,
                    agent_filter=agent_filter,
                    pattern_key=domain,
                    confidence=confidence,
                    sample_size=total,
                    recommendation=recommendation_json,
                    evidence=evidence_json)

                self.stats['created'] += 1
                results.append({
                    'type': 'domain',
                    'agent': agent_filter,
                    'domain': domain,
                    'confidence': confidence,
                    'sample_size': total
                })

            except Exception as e:
                self.stats['errors'].append(f"domain: {e}")

        return results

    def generate_all(self, agent: str = None, learning_types: list = None) -> dict:
        """
        Generate all types of learnings.

        Args:
            agent: Optional agent filter for agent-specific learnings
            learning_types: List of learning types to generate, or None for all

        Returns:
            Summary dict with counts and any errors
        """
        if learning_types is None:
            learning_types = self.LEARNING_TYPES

        all_results = []

        print(f"\n{'='*60}")
        print(f"Kublai Learning Generator - {datetime.now().isoformat()}")
        if agent:
            print(f"Agent filter: {agent}")
        print(f"{'='*60}\n")

        if 'prompt_pattern' in learning_types:
            print("Generating prompt_pattern learnings...", end=" ")
            results = self.create_prompt_pattern_learnings(agent)
            print(f"✓ {len(results)} created")
            all_results.extend(results)

        if 'skill_hint' in learning_types:
            print("Generating skill_hint learnings...", end=" ")
            results = self.create_skill_hint_learnings(agent)
            print(f"✓ {len(results)} created")
            all_results.extend(results)

        if 'timeout' in learning_types:
            print("Generating timeout learnings...", end=" ")
            results = self.create_timeout_learnings(agent)
            print(f"✓ {len(results)} created")
            all_results.extend(results)

        if 'context' in learning_types:
            print("Generating context learnings...", end=" ")
            results = self.create_context_learnings()
            print(f"✓ {len(results)} created")
            all_results.extend(results)

        if 'model' in learning_types:
            print("Generating model learnings...", end=" ")
            results = self.create_model_learnings(agent)
            print(f"✓ {len(results)} created")
            all_results.extend(results)

        if 'domain' in learning_types:
            print("Generating domain learnings...", end=" ")
            results = self.create_domain_learnings(agent)
            print(f"✓ {len(results)} created")
            all_results.extend(results)

        # Print summary
        print(f"\n{'='*60}")
        print(f"Summary:")
        print(f"  Created:      {self.stats['created']} learnings")
        print(f"  Deprecated:   {self.stats['deprecated']} old learnings")
        print(f"  Skipped:      {self.stats['skipped']} (insufficient data)")
        if self.stats['errors']:
            print(f"  Errors:       {len(self.stats['errors'])}")
            for err in self.stats['errors'][:5]:
                print(f"    - {err}")
        print(f"{'='*60}\n")

        return {
            'created': self.stats['created'],
            'deprecated': self.stats['deprecated'],
            'skipped': self.stats['skipped'],
            'errors': self.stats['errors'],
            'learnings': all_results
        }

    def cleanup_expired_learnings(self) -> int:
        """
        Remove or archive learnings that have expired.

        Returns count of learnings cleaned up.
        """
        with neo4j_session() as session:
            result = session.run("""
                MATCH (l:KublaiLearning)
                WHERE l.valid_until < datetime()
                RETURN count(l) as expired_count
            """)
            record = result.single()
            expired = record.get("expired_count", 0) if record else 0

            if expired > 0:
                # Archive before deleting (optional - create Archive nodes)
                session.run("""
                    MATCH (l:KublaiLearning)
                    WHERE l.valid_until < datetime()
                    CREATE (a:KublaiLearningArchive {
                        learning_id: l.learning_id,
                        learning_type: l.learning_type,
                        agent_filter: l.agent_filter,
                        pattern_key: l.pattern_key,
                        confidence: l.confidence,
                        sample_size: l.sample_size,
                        created: l.created,
                        valid_until: l.valid_until,
                        status: 'expired',
                        recommendation: l.recommendation,
                        evidence: l.evidence,
                        archived_at: datetime()
                    })
                    WITH l
                    DELETE l
                """)
                print(f"Cleaned up {expired} expired learnings (archived)")

            return expired

    def get_active_learnings_summary(self) -> list:
        """Get summary of currently active learnings."""
        with neo4j_session() as session:
            result = session.run("""
                MATCH (l:KublaiLearning)
                WHERE l.status = 'active' AND l.valid_until > datetime()
                RETURN l.learning_type as type,
                       count(l) as count,
                       avg(l.confidence) as avg_confidence,
                       avg(l.sample_size) as avg_sample_size
                ORDER BY count DESC
            """)
            return [dict(r) for r in result]


def main():
    parser = argparse.ArgumentParser(
        description='Generate Kublai learnings from task outcomes'
    )
    parser.add_argument('--weekly', action='store_true',
                       help='Full weekly generation (all agents, all types)')
    parser.add_argument('--agent', type=str,
                       help='Filter to specific agent (temujin, mongke, etc.)')
    parser.add_argument('--type', type=str, action='append',
                       choices=['prompt_pattern', 'skill_hint', 'timeout',
                               'context', 'model', 'domain'],
                       help='Specific learning type(s) to generate')
    parser.add_argument('--cleanup', action='store_true',
                       help='Cleanup expired learnings before generating')
    parser.add_argument('--summary', action='store_true',
                       help='Show summary of active learnings and exit')
    parser.add_argument('--test', action='store_true',
                       help='Test mode: show what would be created without creating')

    args = parser.parse_args()

    generator = KublaiLearningGenerator()

    if args.summary:
        # Show current learning state
        print("\n=== Active KublaiLearnings Summary ===\n")
        learnings = generator.get_active_learnings_summary()

        if not learnings:
            print("No active learnings found.")
        else:
            for l in learnings:
                print(f"  {l['type']}: {l['count']} learnings "
                      f"(avg conf: {l.get('avg_confidence', 0):.2f}, "
                      f"avg sample: {l.get('avg_sample_size', 0):.0f})")

        print()
        return

        if args.cleanup:
            print("Cleaning up expired learnings...")
            generator.cleanup_expired_learnings()

        if args.test:
            print("\n=== TEST MODE - No learnings will be created ===\n")
            # Just run queries and show results
            queries = LearningQueries()

            if args.agent or not args.weekly:
                agent = args.agent
                print(f"Agent: {agent or 'all'}\n")

                patterns = queries.get_agent_prompt_patterns(agent)
                print(f"Prompt patterns: {len(patterns)} candidates")
                for p in patterns[:3]:
                    print(f"  - {p['template']}: {p['sample_size']} tasks, quality {p['avg_quality']:.2f}")

                skills = queries.get_skill_hint_effectiveness(agent)
                print(f"\nSkill hints: {len(skills)} candidates")
                for s in skills[:3]:
                    print(f"  - {s['hint']}: {s['success_rate']:.1%} success")

            print("\n=== Test complete ===\n")

        else:
            # Actual generation
            learning_types = args.type if args.type else None
            results = generator.generate_all(
                agent=args.agent if not args.weekly else None,
                learning_types=learning_types
            )

            # Write summary report
            report_path = os.path.expanduser(
                f"~/.openclaw/agents/main/logs/kublai-learning-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
            )
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            print(f"Report saved: {report_path}")


if __name__ == '__main__':
    main()
