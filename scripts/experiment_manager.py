#!/usr/bin/env python3
"""
Experiment Manager - Core experiment lifecycle management for Kurultai

Enables autonomous agents to run experiments with:
- Git branch automation (experiment/<agent>/<exp-id>/<slug>)
- Baseline metric recording
- Neo4j experiment tracking
- Automatic cleanup

Usage:
    from experiment_manager import ExperimentManager, Experiment

    em = ExperimentManager()
    exp = em.create_experiment(
        agent="temujin",
        hypothesis="Increase router scorer learning rate",
        target_files=["scripts/router_scorer.py"],
        timeout=600
    )
    print(f"Created: {exp.experiment_id}, branch: {exp.branch}")
"""

import os
import sys
import json
import subprocess
import hashlib
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import AGENTS_DIR as _AGENTS_DIR

# Import Neo4j connection from existing module
try:
    from neo4j_task_tracker import get_driver
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

OPENCLAW_DIR = Path.home() / ".openclaw"
EXPERIMENTS_DIR = OPENCLAW_DIR / "experiments"
LEDGER_FILE = EXPERIMENTS_DIR / "ledger.tsv"


@dataclass
class Experiment:
    """Represents an experiment instance."""
    experiment_id: str
    agent: str
    hypothesis: str
    branch: str
    base_commit: str
    target_files: list[str]
    timeout: int
    slug: str
    status: str = "pending"
    created: datetime = field(default_factory=datetime.now)
    started: Optional[datetime] = None
    completed: Optional[datetime] = None

    # Metrics
    quality_score_baseline: Optional[float] = None
    quality_score_result: Optional[float] = None
    error_rate_baseline: Optional[float] = None
    error_rate_result: Optional[float] = None
    duration_seconds: Optional[int] = None
    cost_usd: Optional[float] = None

    # Decision
    decision: Optional[str] = None
    decision_reason: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "experiment_id": self.experiment_id,
            "agent": self.agent,
            "hypothesis": self.hypothesis,
            "branch": self.branch,
            "base_commit": self.base_commit,
            "target_files": self.target_files,
            "timeout": self.timeout,
            "slug": self.slug,
            "status": self.status,
            "created": self.created.isoformat() if self.created else None,
            "started": self.started.isoformat() if self.started else None,
            "completed": self.completed.isoformat() if self.completed else None,
            "quality_score_baseline": self.quality_score_baseline,
            "quality_score_result": self.quality_score_result,
            "error_rate_baseline": self.error_rate_baseline,
            "error_rate_result": self.error_rate_result,
            "duration_seconds": self.duration_seconds,
            "cost_usd": self.cost_usd,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
        }


class ExperimentManager:
    """Manages experiment lifecycle for autonomous Kurultai experiments."""

    def __init__(self, repo_path: Optional[Path] = None):
        self.repo_path = repo_path or OPENCLAW_DIR
        self.driver = get_driver() if NEO4J_AVAILABLE else None
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure experiment directories exist."""
        EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
        if not LEDGER_FILE.exists():
            LEDGER_FILE.write_text("experiment_id\tagent\tcommit\tval_quality\tduration_s\tcost_usd\tstatus\tdescription\n")

    def _generate_experiment_id(self) -> str:
        """Generate unique experiment ID: exp-YYYYMMDD-NNN."""
        today = datetime.now().strftime("%Y%m%d")

        # Check existing experiments for today
        prefix = f"exp-{today}-"
        counter = 1

        if LEDGER_FILE.exists():
            with open(LEDGER_FILE) as f:
                for line in f:
                    if line.startswith(prefix):
                        try:
                            num = int(line.split("-")[-1].split("\t")[0])
                            counter = max(counter, num + 1)
                        except (ValueError, IndexError):
                            pass

        return f"exp-{today}-{counter:03d}"

    def _generate_slug(self, hypothesis: str, max_len: int = 30) -> str:
        """Generate URL-safe slug from hypothesis."""
        # Convert to lowercase, replace spaces with hyphens
        slug = re.sub(r'[^a-z0-9\s-]', '', hypothesis.lower())
        slug = re.sub(r'[\s_]+', '-', slug.strip())
        slug = re.sub(r'-+', '-', slug)

        # Truncate to max length
        if len(slug) > max_len:
            slug = slug[:max_len].rstrip('-')

        return slug or "experiment"

    def _get_current_commit(self) -> str:
        """Get current git commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return "no-git"

    def _create_branch(self, branch_name: str) -> bool:
        """Create and checkout experiment branch."""
        try:
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to create branch: {e.stderr}", file=sys.stderr)
            return False

    def _get_baseline_metrics(self, agent: str) -> dict:
        """Fetch baseline metrics from Neo4j for comparison."""
        if not self.driver:
            return {"quality_score": 0.72, "error_rate": 0.05}

        try:
            with self.driver.session() as session:
                # Get average metrics from recent completed tasks
                result = session.run("""
                    MATCH (a:Agent {name: $agent})-[:EXECUTED]->(t:Task)
                    WHERE t.status = 'completed'
                    AND t.completed > datetime() - duration('P7D')
                    WITH avg(t.quality_score) AS quality,
                         avg(t.error_rate) AS error_rate
                    RETURN
                        coalesce(quality, 0.72) AS quality_score,
                        coalesce(error_rate, 0.05) AS error_rate
                """, agent=agent)
                record = result.single()
                if record:
                    return dict(record)
        except Exception as e:
            print(f"Warning: Could not fetch baseline metrics: {e}", file=sys.stderr)

        return {"quality_score": 0.72, "error_rate": 0.05}

    def _record_experiment_neo4j(self, experiment: Experiment) -> bool:
        """Create Experiment node in Neo4j."""
        if not self.driver:
            return False

        try:
            with self.driver.session() as session:
                session.run("""
                    MERGE (a:Agent {name: $agent})
                    CREATE (e:Experiment {
                        experiment_id: $experiment_id,
                        agent: $agent,
                        hypothesis: $hypothesis,
                        branch: $branch,
                        base_commit: $base_commit,
                        status: $status,
                        created: datetime(),
                        timeout: $timeout,
                        quality_score_baseline: $quality_baseline,
                        error_rate_baseline: $error_baseline
                    })
                    CREATE (a)-[:CREATED_EXPERIMENT]->(e)

                    // Create file modification relationships
                    WITH e
                    UNWIND $target_files AS file_path
                    MERGE (f:File {path: file_path})
                    CREATE (e)-[:MODIFIED]->(f)
                """,
                agent=experiment.agent,
                experiment_id=experiment.experiment_id,
                hypothesis=experiment.hypothesis,
                branch=experiment.branch,
                base_commit=experiment.base_commit,
                status=experiment.status,
                timeout=experiment.timeout,
                quality_baseline=experiment.quality_score_baseline,
                error_baseline=experiment.error_rate_baseline,
                target_files=experiment.target_files)
            return True
        except Exception as e:
            print(f"Warning: Could not record experiment in Neo4j: {e}", file=sys.stderr)
            return False

    def _append_to_ledger(self, experiment: Experiment):
        """Append experiment to ledger file."""
        with open(LEDGER_FILE, "a") as f:
            quality = experiment.quality_score_result or 0.0
            duration = experiment.duration_seconds or 0
            cost = experiment.cost_usd or 0.0
            desc = f"{experiment.decision_reason or 'pending'}"
            f.write(f"{experiment.experiment_id}\t{experiment.agent}\t{experiment.base_commit}\t{quality:.4f}\t{duration}\t{cost:.2f}\t{experiment.status}\t{desc}\n")

    def create_experiment(
        self,
        agent: str,
        hypothesis: str,
        target_files: list[str],
        timeout: int = 600
    ) -> Experiment:
        """
        Create a new experiment.

        Args:
            agent: Agent name (temujin, ogedei, kublai, etc.)
            hypothesis: Description of what's being tested
            target_files: List of files the experiment will modify
            timeout: Maximum experiment duration in seconds

        Returns:
            Experiment instance with branch created
        """
        # Generate IDs
        experiment_id = self._generate_experiment_id()
        slug = self._generate_slug(hypothesis)
        branch = f"experiment/{agent}/{experiment_id}/{slug}"
        base_commit = self._get_current_commit()

        # Get baseline metrics
        baseline = self._get_baseline_metrics(agent)

        # Create experiment object
        experiment = Experiment(
            experiment_id=experiment_id,
            agent=agent,
            hypothesis=hypothesis,
            branch=branch,
            base_commit=base_commit,
            target_files=target_files,
            timeout=timeout,
            slug=slug,
            quality_score_baseline=baseline.get("quality_score", 0.72),
            error_rate_baseline=baseline.get("error_rate", 0.05),
        )

        # Create git branch
        if not self._create_branch(branch):
            raise RuntimeError(f"Failed to create experiment branch: {branch}")

        # Record in Neo4j
        self._record_experiment_neo4j(experiment)

        # Append to ledger
        self._append_to_ledger(experiment)

        return experiment

    def start_experiment(self, experiment_id: str) -> bool:
        """
        Mark experiment as started.

        Args:
            experiment_id: Experiment ID to start

        Returns:
            True if successful
        """
        if self.driver:
            try:
                with self.driver.session() as session:
                    session.run("""
                        MATCH (e:Experiment {experiment_id: $experiment_id})
                        SET e.status = 'running',
                            e.started = datetime()
                    """, experiment_id=experiment_id)
            except Exception as e:
                print(f"Warning: Could not update Neo4j: {e}", file=sys.stderr)

        return True

    def complete_experiment(
        self,
        experiment_id: str,
        metrics: dict,
        decision: Optional[str] = None,
        decision_reason: Optional[str] = None
    ) -> None:
        """
        Mark experiment as completed with results.

        Args:
            experiment_id: Experiment ID to complete
            metrics: Dict with quality_score, error_rate, duration_seconds, cost_usd
            decision: 'merge', 'discard', or 'crash'
            decision_reason: Human-readable reason for decision
        """
        if self.driver:
            try:
                with self.driver.session() as session:
                    session.run("""
                        MATCH (e:Experiment {experiment_id: $experiment_id})
                        SET e.status = 'completed',
                            e.completed = datetime(),
                            e.quality_score_result = $quality_score,
                            e.error_rate_result = $error_rate,
                            e.duration_seconds = $duration,
                            e.cost_usd = $cost,
                            e.decision = $decision,
                            e.decision_reason = $decision_reason
                    """,
                    experiment_id=experiment_id,
                    quality_score=metrics.get("quality_score"),
                    error_rate=metrics.get("error_rate"),
                    duration=metrics.get("duration_seconds"),
                    cost=metrics.get("cost_usd"),
                    decision=decision,
                    decision_reason=decision_reason)
            except Exception as e:
                print(f"Warning: Could not update Neo4j: {e}", file=sys.stderr)

    def cleanup_experiment(self, experiment_id: str, delete_branch: bool = True) -> None:
        """
        Clean up experiment resources.

        Args:
            experiment_id: Experiment ID to clean up
            delete_branch: Whether to delete the git branch
        """
        if delete_branch:
            try:
                # Get branch name
                branch = None
                if self.driver:
                    with self.driver.session() as session:
                        result = session.run("""
                            MATCH (e:Experiment {experiment_id: $experiment_id})
                            RETURN e.branch AS branch
                        """, experiment_id=experiment_id)
                        record = result.single()
                        if record:
                            branch = record["branch"]

                if branch:
                    # Switch to main and delete experiment branch
                    subprocess.run(
                        ["git", "checkout", "main"],
                        cwd=self.repo_path,
                        capture_output=True,
                        check=True
                    )
                    subprocess.run(
                        ["git", "branch", "-D", branch],
                        cwd=self.repo_path,
                        capture_output=True
                    )
            except subprocess.CalledProcessError:
                pass  # Branch may not exist

    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Get experiment by ID from Neo4j."""
        if not self.driver:
            return None

        try:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (e:Experiment {experiment_id: $experiment_id})
                    RETURN e
                """, experiment_id=experiment_id)
                record = result.single()
                if record:
                    data = dict(record["e"])
                    return Experiment(
                        experiment_id=data.get("experiment_id"),
                        agent=data.get("agent"),
                        hypothesis=data.get("hypothesis"),
                        branch=data.get("branch"),
                        base_commit=data.get("base_commit"),
                        target_files=[],  # Not stored directly
                        timeout=data.get("timeout", 600),
                        slug=data.get("branch", "").split("/")[-1] if data.get("branch") else "",
                        status=data.get("status"),
                        quality_score_baseline=data.get("quality_score_baseline"),
                        quality_score_result=data.get("quality_score_result"),
                        error_rate_baseline=data.get("error_rate_baseline"),
                        error_rate_result=data.get("error_rate_result"),
                        duration_seconds=data.get("duration_seconds"),
                        cost_usd=data.get("cost_usd"),
                        decision=data.get("decision"),
                        decision_reason=data.get("decision_reason"),
                    )
        except Exception as e:
            print(f"Warning: Could not fetch experiment: {e}", file=sys.stderr)

        return None

    def list_active_experiments(self, agent: Optional[str] = None) -> list[Experiment]:
        """List all running experiments, optionally filtered by agent."""
        if not self.driver:
            return []

        try:
            with self.driver.session() as session:
                if agent:
                    result = session.run("""
                        MATCH (a:Agent {name: $agent})-[:CREATED_EXPERIMENT]->(e:Experiment)
                        WHERE e.status IN ['pending', 'running']
                        RETURN e ORDER BY e.created DESC
                    """, agent=agent)
                else:
                    result = session.run("""
                        MATCH (e:Experiment)
                        WHERE e.status IN ['pending', 'running']
                        RETURN e ORDER BY e.created DESC
                    """)

                experiments = []
                for record in result:
                    data = dict(record["e"])
                    exp = Experiment(
                        experiment_id=data.get("experiment_id"),
                        agent=data.get("agent"),
                        hypothesis=data.get("hypothesis"),
                        branch=data.get("branch"),
                        base_commit=data.get("base_commit"),
                        target_files=[],
                        timeout=data.get("timeout", 600),
                        slug="",
                        status=data.get("status"),
                    )
                    experiments.append(exp)
                return experiments
        except Exception as e:
            print(f"Warning: Could not list experiments: {e}", file=sys.stderr)
            return []

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()


def main():
    """CLI interface for experiment management."""
    import argparse

    parser = argparse.ArgumentParser(description="Experiment Manager CLI")
    parser.add_argument("command", choices=["create", "list", "status", "cleanup"])
    parser.add_argument("--agent", default="temujin", help="Agent name")
    parser.add_argument("--hypothesis", help="Experiment hypothesis")
    parser.add_argument("--files", nargs="+", help="Target files")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout in seconds")
    parser.add_argument("--experiment-id", help="Experiment ID for status/cleanup")

    args = parser.parse_args()

    em = ExperimentManager()

    try:
        if args.command == "create":
            if not args.hypothesis:
                print("Error: --hypothesis required for create", file=sys.stderr)
                sys.exit(1)
            files = args.files or []
            exp = em.create_experiment(
                agent=args.agent,
                hypothesis=args.hypothesis,
                target_files=files,
                timeout=args.timeout
            )
            print(f"Created: {exp.experiment_id}")
            print(f"Branch: {exp.branch}")
            print(f"Base commit: {exp.base_commit}")
            print(f"Baseline quality: {exp.quality_score_baseline}")

        elif args.command == "list":
            experiments = em.list_active_experiments(args.agent)
            if not experiments:
                print("No active experiments")
            for exp in experiments:
                print(f"{exp.experiment_id}\t{exp.agent}\t{exp.status}\t{exp.hypothesis[:50]}")

        elif args.command == "status":
            if not args.experiment_id:
                print("Error: --experiment-id required for status", file=sys.stderr)
                sys.exit(1)
            exp = em.get_experiment(args.experiment_id)
            if exp:
                print(json.dumps(exp.to_dict(), indent=2))
            else:
                print(f"Experiment not found: {args.experiment_id}")

        elif args.command == "cleanup":
            if not args.experiment_id:
                print("Error: --experiment-id required for cleanup", file=sys.stderr)
                sys.exit(1)
            em.cleanup_experiment(args.experiment_id)
            print(f"Cleaned up: {args.experiment_id}")

    finally:
        em.close()


if __name__ == "__main__":
    main()
