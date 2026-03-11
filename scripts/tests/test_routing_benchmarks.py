#!/usr/bin/env python3
"""
Performance Benchmarks for Kurultai Task Routing

Benchmarks task classification, routing decisions, and queue operations.
"""

import os
import sys
import time
import json
import tempfile
import unittest
from datetime import datetime
from typing import Dict, List, Any
from dataclasses import dataclass

# Add scripts directory to path
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    name: str
    iterations: int
    total_ms: float
    avg_ms: float
    min_ms: float
    max_ms: float

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "iterations": self.iterations,
            "total_ms": round(self.total_ms, 3),
            "avg_ms": round(self.avg_ms, 6),
            "min_ms": round(self.min_ms, 6),
            "max_ms": round(self.max_ms, 6)
        }


class BenchmarkSuite:
    """Suite for running performance benchmarks."""

    def __init__(self):
        self.results: List[BenchmarkResult] = []

    def benchmark(self, name: str, func: callable, iterations: int = 1000) -> BenchmarkResult:
        """Run a benchmark function multiple times."""
        times = []

        for _ in range(iterations):
            start = time.perf_counter()
            func()
            elapsed = (time.perf_counter() - start) * 1000  # Convert to ms
            times.append(elapsed)

        result = BenchmarkResult(
            name=name,
            iterations=iterations,
            total_ms=sum(times),
            avg_ms=sum(times) / len(times),
            min_ms=min(times),
            max_ms=max(times)
        )
        self.results.append(result)
        return result

    def report(self) -> str:
        """Generate benchmark report."""
        lines = ["=" * 60]
        lines.append("PERFORMANCE BENCHMARK REPORT")
        lines.append("=" * 60)

        for r in self.results:
            lines.append(f"\n{r.name}:")
            lines.append(f"  Iterations: {r.iterations}")
            lines.append(f"  Average: {r.avg_ms:.6f} ms")
            lines.append(f"  Min: {r.min_ms:.6f} ms")
            lines.append(f"  Max: {r.max_ms:.6f} ms")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


class TestTaskRoutingBenchmarks(unittest.TestCase):
    """Performance benchmarks for task routing."""

    def setUp(self):
        """Set up benchmark suite."""
        self.suite = BenchmarkSuite()
        self.agents = ['kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei']

    def test_agent_classification_benchmark(self):
        """Benchmark task classification by agent domain."""
        # Define classification rules (simplified)
        classification_rules = {
            'temujin': ['code', 'api', 'bug', 'deploy', 'script', 'infrastructure', 'architecture'],
            'mongke': ['research', 'market', 'competitor', 'data', 'analysis'],
            'chagatai': ['docs', 'blog', 'content', 'marketing', 'changelog'],
            'jochi': ['test', 'security', 'error', 'review', 'investigation'],
            'ogedei': ['monitor', 'health', 'restart', 'incident', 'ops'],
        }

        test_tasks = [
            "Fix the login bug",
            "Research competitor pricing",
            "Write documentation for API",
            "Run security audit",
            "Monitor system health",
            "Deploy to production",
            "Analyze market trends",
            "Create marketing content",
            "Review pull request",
            "Restart crashed service",
            "Implement new feature",
            "Find data sources",
            "Update README",
            "Investigate error logs",
            "Check cron jobs",
        ]

        def classify_task(task: str) -> str:
            task_lower = task.lower()
            for agent, keywords in classification_rules.items():
                for keyword in keywords:
                    if keyword in task_lower:
                        return agent
            return 'kublai'  # Default to squad lead

        # Benchmark classification
        def run_classification():
            for task in test_tasks:
                classify_task(task)

        result = self.suite.benchmark("Agent Classification (15 tasks)", run_classification, 1000)

        # Verify performance
        self.assertLess(result.avg_ms, 1.0, f"Classification should average < 1ms per 15 tasks, got {result.avg_ms:.4f}ms")

    def test_task_priority_sorting_benchmark(self):
        """Benchmark task priority sorting."""
        def generate_tasks(count: int) -> List[Dict]:
            import random
            priorities = ['high', 'normal', 'low']
            return [
                {'task_id': f'task-{i}', 'priority': random.choice(priorities)}
                for i in range(count)
            ]

        def sort_by_priority(tasks: List[Dict]) -> List[Dict]:
            priority_order = {'high': 0, 'normal': 1, 'low': 2}
            return sorted(tasks, key=lambda x: priority_order.get(x['priority'], 1))

        # Benchmark with 100 tasks
        tasks_100 = generate_tasks(100)
        result_100 = self.suite.benchmark("Priority Sort (100 tasks)", lambda: sort_by_priority(tasks_100), 1000)

        # Benchmark with 1000 tasks
        tasks_1000 = generate_tasks(1000)
        result_1000 = self.suite.benchmark("Priority Sort (1000 tasks)", lambda: sort_by_priority(tasks_1000), 100)

        # Verify performance scales reasonably
        self.assertLess(result_100.avg_ms, 1.0, "100-task sort should be < 1ms")
        self.assertLess(result_1000.avg_ms, 20.0, "1000-task sort should be < 20ms")

    def test_task_file_parsing_benchmark(self):
        """Benchmark parsing task file frontmatter."""
        sample_task = """---
task_id: abc123
agent: temujin
priority: high
created: 2026-03-08T12:00:00
source: human
skill_hint: /horde-brainstorming
---

# Task: Implement authentication

This is a complex task that requires:
- OAuth integration
- Session management
- Token refresh
"""

        def parse_frontmatter(content: str) -> Dict:
            metadata = {}
            in_frontmatter = False

            for line in content.split('\n'):
                if line == '---':
                    in_frontmatter = not in_frontmatter
                    continue

                if in_frontmatter and ':' in line:
                    key, value = line.split(':', 1)
                    metadata[key.strip()] = value.strip()

            return metadata

        result = self.suite.benchmark("Task File Parsing", lambda: parse_frontmatter(sample_task), 10000)

        # Verify parsing is fast
        self.assertLess(result.avg_ms, 0.1, f"Parsing should be < 0.1ms, got {result.avg_ms:.6f}ms")

    def test_queue_depth_calculation_benchmark(self):
        """Benchmark calculating queue depths across all agents."""
        def calculate_queue_depths(task_counts: Dict[str, int]) -> Dict[str, Dict]:
            total = sum(task_counts.values())
            return {
                "total": total,
                "agents": {
                    agent: {
                        "count": count,
                        "percentage": round(count / total * 100, 1) if total > 0 else 0
                    }
                    for agent, count in task_counts.items()
                }
            }

        test_counts = {
            'kublai': 5,
            'temujin': 12,
            'mongke': 3,
            'chagatai': 8,
            'jochi': 6,
            'ogedei': 2
        }

        result = self.suite.benchmark("Queue Depth Calculation", lambda: calculate_queue_depths(test_counts), 10000)

        self.assertLess(result.avg_ms, 0.05, f"Queue calculation should be < 0.05ms")

    def test_json_serialization_benchmark(self):
        """Benchmark JSON serialization of task data."""
        task_data = {
            "task_id": "abc123",
            "agent": "temujin",
            "priority": "high",
            "created": "2026-03-08T12:00:00",
            "source": "human",
            "skill_hint": "/horde-brainstorming",
            "description": "Implement authentication system",
            "metadata": {
                "estimated_hours": 8,
                "tags": ["auth", "security", "api"],
                "dependencies": ["task-001", "task-002"]
            }
        }

        result = self.suite.benchmark("JSON Serialization", lambda: json.dumps(task_data), 10000)

        self.assertLess(result.avg_ms, 0.01, f"JSON serialization should be < 0.01ms")

    def test_agent_selection_rules_benchmark(self):
        """Benchmark agent selection based on routing rules."""
        routing_rules = [
            {'keywords': ['code', 'implement', 'fix bug', 'deploy'], 'agent': 'temujin'},
            {'keywords': ['research', 'find', 'analyze', 'market'], 'agent': 'mongke'},
            {'keywords': ['write', 'document', 'blog', 'content'], 'agent': 'chagatai'},
            {'keywords': ['test', 'review', 'security', 'audit'], 'agent': 'jochi'},
            {'keywords': ['monitor', 'restart', 'health', 'ops'], 'agent': 'ogedei'},
        ]

        def select_agent(task_description: str) -> str:
            desc_lower = task_description.lower()
            for rule in routing_rules:
                for keyword in rule['keywords']:
                    if keyword in desc_lower:
                        return rule['agent']
            return 'kublai'

        test_descriptions = [
            "Fix the authentication bug in the login flow",
            "Research competitor pricing strategies",
            "Write documentation for the new API",
            "Run security audit on payment system",
            "Monitor system health and restart services",
            "Implement new feature for user dashboard",
            "Analyze market trends for Q2",
            "Create blog post about product launch",
            "Review code for pull request #123",
            "Check cron job status",
        ]

        def run_selection():
            for desc in test_descriptions:
                select_agent(desc)

        result = self.suite.benchmark("Agent Selection (10 tasks)", run_selection, 1000)

        self.assertLess(result.avg_ms, 0.5, f"Agent selection should be < 0.5ms for 10 tasks")


class TestRoutingPerformance(unittest.TestCase):
    """End-to-end routing performance tests."""

    def test_full_routing_pipeline_performance(self):
        """Test full routing pipeline from task creation to assignment."""
        # Simulate full pipeline
        def pipeline():
            # 1. Parse task
            task = {
                "description": "Fix the login bug in authentication module",
                "source": "human",
                "priority": "high"
            }

            # 2. Classify
            classification_rules = {
                'temujin': ['code', 'bug', 'implement', 'deploy', 'api', 'fix'],
                'mongke': ['research', 'analyze', 'find'],
                'chagatai': ['write', 'document', 'blog'],
                'jochi': ['test', 'review', 'security', 'audit'],
                'ogedei': ['monitor', 'restart', 'health', 'ops'],
            }

            selected_agent = 'kublai'
            desc_lower = task['description'].lower()
            for agent, keywords in classification_rules.items():
                for keyword in keywords:
                    if keyword in desc_lower:
                        selected_agent = agent
                        break
                if selected_agent != 'kublai':
                    break

            # 3. Create task ID
            import uuid
            task_id = str(uuid.uuid4())[:8]

            # 4. Generate task file content
            content = f"""---
task_id: {task_id}
agent: {selected_agent}
priority: {task['priority']}
created: {datetime.now().isoformat()}
---

# Task: {task['description']}
"""

            # 5. Serialize
            metadata = {
                "task_id": task_id,
                "agent": selected_agent,
                "priority": task['priority'],
                "content_length": len(content)
            }

            return metadata

        # Run benchmark
        times = []
        for _ in range(100):
            start = time.perf_counter()
            result = pipeline()
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg_ms = sum(times) / len(times)

        # Verify
        self.assertLess(avg_ms, 5.0, f"Full pipeline should average < 5ms, got {avg_ms:.4f}ms")


def run_benchmarks():
    """Run all benchmarks and print report."""
    suite = BenchmarkSuite()

    print("\n" + "=" * 60)
    print("KURULTAI PERFORMANCE BENCHMARK SUITE")
    print("=" * 60 + "\n")

    # Run unit tests
    unittest.main(argv=[''], verbosity=2, exit=False)

    # Print benchmark report
    print("\n" + suite.report())


if __name__ == '__main__':
    run_benchmarks()