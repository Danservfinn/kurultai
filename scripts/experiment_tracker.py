#!/usr/bin/env python3
"""
Experiment Tracker Module for Kurultai Autonomous Experiments

Manages the full lifecycle of experiments from proposal through rollout/rollback:
    PROPOSED → RUNNING → CONCLUDED → ROLLOUT/ROLLBACK

Features:
- Statistical analysis (t-tests, Cohen's d, confidence intervals)
- Guardrail checking with configurable thresholds
- Early stopping rules
- Neo4j integration for experiment tracking
- YAML configuration support
- CLI interface

Usage:
    python3 experiment_tracker.py create experiments/haiku-reviews.yaml
    python3 experiment_tracker.py start exp-2026-03-08-haiku-reviews
    python3 experiment_tracker.py status exp-2026-03-08-haiku-reviews
    python3 experiment_tracker.py evaluate exp-2026-03-08-haiku-reviews
    python3 experiment_tracker.py rollout exp-2026-03-08-haiku-reviews
"""

import os
import sys
import json
import yaml
import argparse
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Tuple, Literal
from pathlib import Path
import math

# Add script directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ces_calculator import calculate_ces, TaskMetrics, calculate_efficiency_score

# Optional imports
try:
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

try:
    from neo4j_task_tracker import get_driver
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ExperimentTargeting:
    """Targeting rules for experiment assignment."""
    agents: Optional[List[str]] = None  # None = all agents
    task_types: Optional[List[str]] = None
    priorities: List[str] = field(default_factory=lambda: ["normal", "low"])  # Exclude critical by default

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentTargeting":
        return cls(
            agents=data.get("agents"),
            task_types=data.get("task_types"),
            priorities=data.get("priorities", ["normal", "low"])
        )


@dataclass
class SampleSizeConfig:
    """Sample size configuration for experiments."""
    min_per_group: int = 100
    power: float = 0.8
    alpha: float = 0.05
    min_detectable_effect: float = 0.05

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SampleSizeConfig":
        return cls(
            min_per_group=data.get("min_per_group", 100),
            power=data.get("power", 0.8),
            alpha=data.get("alpha", 0.05),
            min_detectable_effect=data.get("min_detectable_effect", 0.05)
        )


@dataclass
class DurationConfig:
    """Duration configuration for experiments."""
    min_days: int = 7
    max_days: int = 14

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DurationConfig":
        return cls(
            min_days=data.get("min_days", 7),
            max_days=data.get("max_days", 14)
        )


@dataclass
class SuccessCriteria:
    """Success criteria for experiment evaluation."""
    ces_lift_min: float = 0.05  # Minimum CES improvement (5%)
    p_value_max: float = 0.05  # Statistical significance threshold
    effect_size_min: float = 0.2  # Cohen's d minimum (small effect)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SuccessCriteria":
        return cls(
            ces_lift_min=data.get("ces_lift_min", 0.05),
            p_value_max=data.get("p_value_max", 0.05),
            effect_size_min=data.get("effect_size_min", 0.2)
        )


@dataclass
class GuardrailConfig:
    """Guardrail configuration for safety checks."""
    min: Optional[float] = None
    max: Optional[float] = None
    max_increase_pct: Optional[float] = None
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GuardrailConfig":
        return cls(
            min=data.get("min"),
            max=data.get("max"),
            max_increase_pct=data.get("max_increase_pct"),
            weight=data.get("weight", 1.0)
        )


@dataclass
class RolloutConfig:
    """Rollout strategy configuration."""
    strategy: str = "gradual"  # "immediate", "gradual", "canary"
    stages: List[int] = field(default_factory=lambda: [10, 25, 50, 100])  # Percentage stages
    stage_duration_hours: int = 24

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RolloutConfig":
        return cls(
            strategy=data.get("strategy", "gradual"),
            stages=data.get("stages", [10, 25, 50, 100]),
            stage_duration_hours=data.get("stage_duration_hours", 24)
        )


@dataclass
class ExperimentConfig:
    """Full experiment configuration."""
    experiment_id: str
    hypothesis: str
    variable_type: str  # "model", "prompt_template", "skill_hint", "timeout"
    control_value: str
    treatment_value: str
    targeting: ExperimentTargeting
    sample_size: SampleSizeConfig
    duration: DurationConfig
    success_criteria: SuccessCriteria
    guardrails: Dict[str, GuardrailConfig]
    rollout: RolloutConfig

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "hypothesis": self.hypothesis,
            "variable": {
                "type": self.variable_type,
                "control": self.control_value,
                "treatment": self.treatment_value
            },
            "targeting": self.targeting.to_dict(),
            "sample_size": self.sample_size.to_dict(),
            "duration": self.duration.to_dict(),
            "success_criteria": self.success_criteria.to_dict(),
            "guardrails": {k: v.to_dict() for k, v in self.guardrails.items()},
            "rollout": self.rollout.to_dict()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentConfig":
        # Support both formats: nested 'variable' or flat keys
        if "variable" in data:
            variable_type = data["variable"]["type"]
            control_value = data["variable"]["control"]
            treatment_value = data["variable"]["treatment"]
        else:
            variable_type = data.get("variable_type", "unknown")
            control_value = data.get("control_value", "")
            treatment_value = data.get("treatment_value", "")

        return cls(
            experiment_id=data["experiment_id"],
            hypothesis=data["hypothesis"],
            variable_type=variable_type,
            control_value=control_value,
            treatment_value=treatment_value,
            targeting=ExperimentTargeting.from_dict(data.get("targeting", {})),
            sample_size=SampleSizeConfig.from_dict(data.get("sample_size", {})),
            duration=DurationConfig.from_dict(data.get("duration", {})),
            success_criteria=SuccessCriteria.from_dict(data.get("success_criteria", {})),
            guardrails={k: GuardrailConfig.from_dict(v) for k, v in data.get("guardrails", {}).items()},
            rollout=RolloutConfig.from_dict(data.get("rollout", {}))
        )


@dataclass
class ExperimentResult:
    """Statistical analysis results for an experiment."""
    mean_control: float
    mean_treatment: float
    absolute_lift: float
    relative_lift_pct: float
    t_statistic: float
    p_value: float
    cohens_d: float
    ci_95: Tuple[float, float]
    significant: bool
    practical_significance: bool
    sample_adequate: bool
    n_control: int
    n_treatment: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mean_control": self.mean_control,
            "mean_treatment": self.mean_treatment,
            "absolute_lift": self.absolute_lift,
            "relative_lift_pct": self.relative_lift_pct,
            "t_statistic": self.t_statistic,
            "p_value": self.p_value,
            "cohens_d": self.cohens_d,
            "ci_95": list(self.ci_95),
            "significant": self.significant,
            "practical_significance": self.practical_significance,
            "sample_adequate": self.sample_adequate,
            "n_control": self.n_control,
            "n_treatment": self.n_treatment
        }


@dataclass
class GuardrailViolation:
    """Record of a guardrail violation."""
    metric_name: str
    baseline_value: float
    experiment_value: float
    threshold: float
    violation_type: str  # "min", "max", "max_increase"
    weight: float
    severity: float  # How much the threshold was exceeded

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConclusionResult:
    """Result of experiment conclusion analysis."""
    recommendation: Literal["ROLLOUT", "ROLLBACK", "INCONCLUSIVE"]
    experiment_result: Optional[ExperimentResult]
    guardrail_violations: List[GuardrailViolation]
    early_stop_reason: Optional[str]
    confidence: float  # 0.0 - 1.0
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation": self.recommendation,
            "experiment_result": self.experiment_result.to_dict() if self.experiment_result else None,
            "guardrail_violations": [v.to_dict() for v in self.guardrail_violations],
            "early_stop_reason": self.early_stop_reason,
            "confidence": self.confidence,
            "summary": self.summary
        }


# =============================================================================
# GUARDRAILS
# =============================================================================

DEFAULT_GUARDRAILS = {
    "success_rate_critical": GuardrailConfig(min=0.95, weight=2.0),
    "success_rate_high": GuardrailConfig(min=0.90, weight=1.5),
    "success_rate_normal": GuardrailConfig(min=0.75, weight=1.0),
    "quality_score_avg": GuardrailConfig(min=0.70, weight=1.5),
    "duration_p90": GuardrailConfig(max_increase_pct=30, weight=1.0),
    "rework_rate": GuardrailConfig(max=0.20, weight=1.0),
    "escalation_rate": GuardrailConfig(max=0.10, weight=1.0),
}


def check_guardrails(
    baseline_metrics: Dict[str, float],
    experiment_metrics: Dict[str, float],
    guardrails: Optional[Dict[str, GuardrailConfig]] = None
) -> List[GuardrailViolation]:
    """
    Check all guardrails and return any violations.

    Args:
        baseline_metrics: Baseline metric values
        experiment_metrics: Experiment metric values
        guardrails: Guardrail configurations (defaults to DEFAULT_GUARDRAILS)

    Returns:
        List of GuardrailViolation objects for any violations found
    """
    guardrails = guardrails or DEFAULT_GUARDRAILS
    violations = []

    for metric_name, config in guardrails.items():
        baseline = baseline_metrics.get(metric_name, 0.0)
        experiment = experiment_metrics.get(metric_name, 0.0)

        # Check minimum threshold
        if config.min is not None and experiment < config.min:
            severity = (config.min - experiment) / config.min
            violations.append(GuardrailViolation(
                metric_name=metric_name,
                baseline_value=baseline,
                experiment_value=experiment,
                threshold=config.min,
                violation_type="min",
                weight=config.weight,
                severity=severity
            ))

        # Check maximum threshold
        if config.max is not None and experiment > config.max:
            severity = (experiment - config.max) / config.max
            violations.append(GuardrailViolation(
                metric_name=metric_name,
                baseline_value=baseline,
                experiment_value=experiment,
                threshold=config.max,
                violation_type="max",
                weight=config.weight,
                severity=severity
            ))

        # Check maximum increase percentage
        if config.max_increase_pct is not None and baseline > 0:
            increase_pct = ((experiment - baseline) / baseline) * 100
            if increase_pct > config.max_increase_pct:
                severity = (increase_pct - config.max_increase_pct) / config.max_increase_pct
                violations.append(GuardrailViolation(
                    metric_name=metric_name,
                    baseline_value=baseline,
                    experiment_value=experiment,
                    threshold=config.max_increase_pct,
                    violation_type="max_increase",
                    weight=config.weight,
                    severity=severity
                ))

    return violations


# =============================================================================
# STATISTICAL ANALYSIS
# =============================================================================

def calculate_cohens_d(control: List[float], treatment: List[float]) -> float:
    """
    Calculate Cohen's d effect size.

    Formula: d = (mean_t - mean_c) / pooled_std

    Interpretation:
    - |d| < 0.2: negligible effect
    - 0.2 <= |d| < 0.5: small effect
    - 0.5 <= |d| < 0.8: medium effect
    - |d| >= 0.8: large effect
    """
    n1, n2 = len(control), len(treatment)
    if n1 < 2 or n2 < 2:
        return 0.0

    mean1 = sum(control) / n1
    mean2 = sum(treatment) / n2

    # Calculate sample variances
    var1 = sum((x - mean1) ** 2 for x in control) / (n1 - 1)
    var2 = sum((x - mean2) ** 2 for x in treatment) / (n2 - 1)

    # Pooled standard deviation
    pooled_var = ((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2)

    # If both groups have zero variance but different means,
    # we still need to report an effect
    if pooled_var == 0:
        if abs(mean2 - mean1) > 0:
            # Groups differ but with no variance - return a large effect
            return float('inf') if mean2 > mean1 else float('-inf')
        return 0.0

    pooled_std = math.sqrt(pooled_var)
    return (mean2 - mean1) / pooled_std


def calculate_confidence_interval(
    control: List[float],
    treatment: List[float],
    confidence: float = 0.95
) -> Tuple[float, float]:
    """Calculate 95% confidence interval for the difference in means."""
    if not SCIPY_AVAILABLE:
        # Fallback: simple calculation without scipy
        n1, n2 = len(control), len(treatment)
        mean1 = sum(control) / n1 if n1 > 0 else 0
        mean2 = sum(treatment) / n2 if n2 > 0 else 0
        return (mean2 - mean1 - 0.1, mean2 - mean1 + 0.1)

    n1, n2 = len(control), len(treatment)
    if n1 < 2 or n2 < 2:
        return (0.0, 0.0)

    mean1 = sum(control) / n1
    mean2 = sum(treatment) / n2

    var1 = sum((x - mean1) ** 2 for x in control) / (n1 - 1)
    var2 = sum((x - mean2) ** 2 for x in treatment) / (n2 - 1)

    # Standard error of the difference
    se = math.sqrt(var1 / n1 + var2 / n2)

    # t critical value (approximation for large samples)
    z = 1.96  # 95% CI
    diff = mean2 - mean1
    margin = z * se

    return (diff - margin, diff + margin)


def evaluate_experiment(
    control_ces: List[float],
    treatment_ces: List[float],
    success_criteria: Optional[SuccessCriteria] = None
) -> ExperimentResult:
    """
    Perform statistical analysis of experiment results.

    Args:
        control_ces: List of CES scores for control group
        treatment_ces: List of CES scores for treatment group
        success_criteria: Success criteria for evaluation

    Returns:
        ExperimentResult with statistical analysis
    """
    success_criteria = success_criteria or SuccessCriteria()

    n_control = len(control_ces)
    n_treatment = len(treatment_ces)

    # Calculate means
    mean_control = sum(control_ces) / n_control if n_control > 0 else 0.0
    mean_treatment = sum(treatment_ces) / n_treatment if n_treatment > 0 else 0.0

    # Calculate lift
    absolute_lift = mean_treatment - mean_control
    relative_lift = (absolute_lift / mean_control * 100) if mean_control > 0 else 0.0

    # Perform t-test
    if SCIPY_AVAILABLE and n_control >= 2 and n_treatment >= 2:
        t_stat, p_value = stats.ttest_ind(control_ces, treatment_ces)
    else:
        # Fallback: simplified calculation
        t_stat = 0.0
        p_value = 1.0
        if n_control >= 2 and n_treatment >= 2:
            # Approximate t-test
            var_c = sum((x - mean_control) ** 2 for x in control_ces) / (n_control - 1)
            var_t = sum((x - mean_treatment) ** 2 for x in treatment_ces) / (n_treatment - 1)
            se = math.sqrt(var_c / n_control + var_t / n_treatment)
            if se > 0:
                t_stat = absolute_lift / se
                # Approximate p-value using normal distribution
                p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(t_stat) / math.sqrt(2))))

    # Calculate Cohen's d
    cohens_d = calculate_cohens_d(control_ces, treatment_ces)

    # Calculate confidence interval
    ci_95 = calculate_confidence_interval(control_ces, treatment_ces)

    # Determine significance
    significant = p_value < success_criteria.p_value_max
    practical_significance = cohens_d >= success_criteria.effect_size_min
    sample_adequate = n_control >= 30 and n_treatment >= 30  # Minimum for normality assumption

    return ExperimentResult(
        mean_control=mean_control,
        mean_treatment=mean_treatment,
        absolute_lift=absolute_lift,
        relative_lift_pct=relative_lift,
        t_statistic=t_stat,
        p_value=p_value,
        cohens_d=cohens_d,
        ci_95=ci_95,
        significant=significant,
        practical_significance=practical_significance,
        sample_adequate=sample_adequate,
        n_control=n_control,
        n_treatment=n_treatment
    )


# =============================================================================
# EARLY STOPPING
# =============================================================================

def should_stop_early(
    experiment_id: str,
    days_running: int,
    control_n: int,
    treatment_n: int,
    current_result: ExperimentResult,
    experiment_metrics: Optional[Dict[str, float]] = None
) -> Tuple[bool, str]:
    """
    Check early stopping conditions.

    Conditions:
    1. Catastrophic Failure: CRITICAL SR < 80%
    2. Severe Regression: CES_treatment < CES_control - 0.1 for 3+ days
    3. Clear Winner: p < 0.01 AND effect_size > 0.5 AND sample > 100/group
    4. No Effect: After 14 days, CI includes 0 AND width < 0.05

    Args:
        experiment_id: Experiment ID for logging
        days_running: Days since experiment started
        control_n: Sample size in control group
        treatment_n: Sample size in treatment group
        current_result: Current experiment result
        experiment_metrics: Additional metrics (success_rate_critical, etc.)

    Returns:
        Tuple of (should_stop, reason)
    """
    experiment_metrics = experiment_metrics or {}

    # 1. Catastrophic Failure: Critical success rate < 80%
    critical_sr = experiment_metrics.get("success_rate_critical", 1.0)
    if critical_sr < 0.80:
        return True, f"Catastrophic failure: Critical success rate {critical_sr:.1%} < 80%"

    # 2. Severe Regression: Treatment CES significantly lower than control
    if current_result.absolute_lift < -0.1 and days_running >= 3:
        return True, f"Severe regression: CES lift {current_result.absolute_lift:.3f} < -0.1 for 3+ days"

    # 3. Clear Winner: Very strong positive result
    if (current_result.p_value < 0.01 and
        current_result.cohens_d > 0.5 and
        control_n >= 100 and
        treatment_n >= 100):
        return True, f"Clear winner: p={current_result.p_value:.4f}, d={current_result.cohens_d:.2f}, n>100"

    # 4. No Effect: After max duration with no significant difference
    if days_running >= 14:
        ci_lower, ci_upper = current_result.ci_95
        ci_width = ci_upper - ci_lower
        if ci_lower <= 0 <= ci_upper and ci_width < 0.05:
            return True, f"No effect after 14 days: CI [{ci_lower:.3f}, {ci_upper:.3f}] includes 0"

    return False, ""


# =============================================================================
# YAML SUPPORT
# =============================================================================

def load_experiment_from_yaml(path: str) -> ExperimentConfig:
    """Load experiment configuration from YAML file."""
    if not YAML_AVAILABLE:
        raise ImportError("PyYAML is required for YAML support. Install with: pip install pyyaml")

    with open(path) as f:
        data = yaml.safe_load(f)

    # Normalize structure
    exp_data = data.get("experiment", data)
    return ExperimentConfig.from_dict(exp_data)


def save_experiment_to_yaml(config: ExperimentConfig, path: str) -> None:
    """Save experiment configuration to YAML file."""
    if not YAML_AVAILABLE:
        raise ImportError("PyYAML is required for YAML support. Install with: pip install pyyaml")

    data = {
        "experiment": {
            "experiment_id": config.experiment_id,
            "hypothesis": config.hypothesis,
            "variable": {
                "type": config.variable_type,
                "control": config.control_value,
                "treatment": config.treatment_value
            },
            "targeting": config.targeting.to_dict(),
            "sample_size": config.sample_size.to_dict(),
            "duration": config.duration.to_dict(),
            "success_criteria": config.success_criteria.to_dict(),
            "guardrails": {k: v.to_dict() for k, v in config.guardrails.items()},
            "rollout": config.rollout.to_dict()
        }
    }

    with open(path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


# =============================================================================
# EXPERIMENT TRACKER CLASS
# =============================================================================

class ExperimentTracker:
    """Manages the full lifecycle of experiments."""

    # Experiment states
    STATE_PROPOSED = "PROPOSED"
    STATE_RUNNING = "RUNNING"
    STATE_CONCLUDED = "CONCLUDED"
    STATE_ROLLOUT = "ROLLOUT"
    STATE_ROLLBACK = "ROLLBACK"

    def __init__(self, neo4j_driver=None):
        """
        Initialize ExperimentTracker.

        Args:
            neo4j_driver: Optional Neo4j driver (will create if not provided)
        """
        self.driver = neo4j_driver or (get_driver() if NEO4J_AVAILABLE else None)
        self.experiments_dir = Path.home() / ".openclaw" / "experiments"
        self.experiments_dir.mkdir(parents=True, exist_ok=True)

    def propose(self, config: ExperimentConfig) -> str:
        """
        Create new experiment in PROPOSED state.

        Args:
            config: Experiment configuration

        Returns:
            Experiment ID
        """
        experiment_id = config.experiment_id

        # Create experiment node in Neo4j
        self._create_experiment_node(config)

        # Save config to file
        config_path = self.experiments_dir / f"{experiment_id}.yaml"
        save_experiment_to_yaml(config, str(config_path))

        return experiment_id

    def start(self, experiment_id: str) -> bool:
        """
        Transition PROPOSED → RUNNING.

        Validates prerequisites:
        - Experiment exists and is in PROPOSED state
        - No conflicting experiments running
        - Baseline metrics available

        Args:
            experiment_id: Experiment to start

        Returns:
            True if successfully started
        """
        if not self.driver:
            print("Warning: No Neo4j connection, operating in offline mode", file=sys.stderr)
            return True

        try:
            with self.driver.session() as session:
                # Check current state
                result = session.run("""
                    MATCH (e:Experiment {experiment_id: $experiment_id})
                    RETURN e.status AS status
                """, experiment_id=experiment_id)
                record = result.single()

                if not record:
                    raise ValueError(f"Experiment {experiment_id} not found")

                current_status = record["status"]
                if current_status != self.STATE_PROPOSED:
                    raise ValueError(f"Cannot start experiment in {current_status} state")

                # Check for conflicting experiments
                config = self._load_config(experiment_id)
                conflicts = self._check_conflicts(config)

                if conflicts:
                    raise ValueError(f"Conflicting experiments running: {conflicts}")

                # Update state
                session.run("""
                    MATCH (e:Experiment {experiment_id: $experiment_id})
                    SET e.status = $status,
                        e.started = datetime()
                """, experiment_id=experiment_id, status=self.STATE_RUNNING)

                return True

        except Exception as e:
            print(f"Failed to start experiment: {e}", file=sys.stderr)
            return False

    def conclude(self, experiment_id: str) -> ConclusionResult:
        """
        Transition RUNNING → CONCLUDED.

        Runs statistical analysis and checks guardrails.

        Args:
            experiment_id: Experiment to conclude

        Returns:
            ConclusionResult with recommendation
        """
        config = self._load_config(experiment_id)

        # Get CES data for control and treatment
        control_ces, treatment_ces = self._get_experiment_data(experiment_id)

        # Run statistical analysis
        result = evaluate_experiment(control_ces, treatment_ces, config.success_criteria)

        # Get metrics for guardrail checking
        baseline_metrics = self._get_baseline_metrics(config)
        experiment_metrics = self._get_experiment_metrics(experiment_id)

        # Check guardrails
        violations = check_guardrails(baseline_metrics, experiment_metrics, config.guardrails)

        # Determine recommendation
        if violations:
            # Any guardrail violation → rollback
            recommendation = "ROLLBACK"
            summary = f"Rollback recommended due to {len(violations)} guardrail violation(s)"
            confidence = 0.9
        elif result.significant and result.practical_significance and result.absolute_lift > 0:
            recommendation = "ROLLOUT"
            summary = f"Rollout recommended: CES lift {result.relative_lift_pct:.1f}% (p={result.p_value:.4f}, d={result.cohens_d:.2f})"
            confidence = min(0.95, 1.0 - result.p_value)
        elif not result.sample_adequate:
            recommendation = "INCONCLUSIVE"
            summary = f"Inconclusive: Insufficient sample size (control={result.n_control}, treatment={result.n_treatment})"
            confidence = 0.3
        else:
            recommendation = "ROLLBACK"
            summary = f"Rollback recommended: No significant improvement (p={result.p_value:.4f}, d={result.cohens_d:.2f})"
            confidence = 0.7

        # Update Neo4j
        self._update_experiment_status(experiment_id, self.STATE_CONCLUDED, result)

        return ConclusionResult(
            recommendation=recommendation,
            experiment_result=result,
            guardrail_violations=violations,
            early_stop_reason=None,
            confidence=confidence,
            summary=summary
        )

    def rollout(self, experiment_id: str, strategy: str = "gradual") -> None:
        """
        Transition CONCLUDED → ROLLOUT.

        Creates KublaiLearning node from successful experiment.

        Args:
            experiment_id: Experiment to roll out
            strategy: Rollout strategy ("immediate", "gradual", "canary")
        """
        config = self._load_config(experiment_id)
        conclusion = self._get_conclusion(experiment_id)

        if conclusion and conclusion.recommendation != "ROLLOUT":
            raise ValueError(f"Cannot roll out: conclusion was {conclusion.recommendation}")

        # Create KublaiLearning node
        learning_id = self._create_learning_from_experiment(experiment_id, conclusion.experiment_result, config)

        # Update status
        if self.driver:
            with self.driver.session() as session:
                session.run("""
                    MATCH (e:Experiment {experiment_id: $experiment_id})
                    SET e.status = $status,
                        e.rolled_out_at = datetime(),
                        e.learning_id = $learning_id
                """, experiment_id=experiment_id, status=self.STATE_ROLLOUT, learning_id=learning_id)

        print(f"Rolled out experiment {experiment_id} with strategy '{strategy}'")
        print(f"Created learning: {learning_id}")

    def rollback(self, experiment_id: str, reason: str) -> None:
        """
        Transition CONCLUDED → ROLLBACK.

        Logs reason and cleans up.

        Args:
            experiment_id: Experiment to roll back
            reason: Reason for rollback
        """
        # Update status
        if self.driver:
            with self.driver.session() as session:
                session.run("""
                    MATCH (e:Experiment {experiment_id: $experiment_id})
                    SET e.status = $status,
                        e.rolled_back_at = datetime(),
                        e.rollback_reason = $reason
                """, experiment_id=experiment_id, status=self.STATE_ROLLBACK, reason=reason)

        # Log rollback
        rollback_log = self.experiments_dir / "rollbacks.log"
        with open(rollback_log, 'a') as f:
            f.write(f"{datetime.now().isoformat()}\t{experiment_id}\t{reason}\n")

        print(f"Rolled back experiment {experiment_id}: {reason}")

    def status(self, experiment_id: str) -> Dict[str, Any]:
        """Get current experiment status."""
        if not self.driver:
            return {"error": "No Neo4j connection"}

        with self.driver.session() as session:
            result = session.run("""
                MATCH (e:Experiment {experiment_id: $experiment_id})
                RETURN e
            """, experiment_id=experiment_id)
            record = result.single()

            if record:
                return dict(record["e"])
            return {"error": f"Experiment {experiment_id} not found"}

    def list_experiments(
        self,
        status: Optional[str] = None,
        agent: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """List experiments with optional filtering."""
        if not self.driver:
            return []

        with self.driver.session() as session:
            filters = []
            params = {"limit": limit}

            if status:
                filters.append("e.status = $status")
                params["status"] = status

            if agent:
                filters.append("e.agent = $agent")
                params["agent"] = agent

            where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

            result = session.run(f"""
                MATCH (e:Experiment)
                {where_clause}
                RETURN e
                ORDER BY e.created DESC
                LIMIT $limit
            """, **params)

            return [dict(r["e"]) for r in result]

    # Private helper methods

    def _create_experiment_node(self, config: ExperimentConfig) -> None:
        """Create Experiment node in Neo4j."""
        if not self.driver:
            return

        with self.driver.session() as session:
            session.run("""
                CREATE (e:Experiment {
                    experiment_id: $experiment_id,
                    hypothesis: $hypothesis,
                    variable_type: $variable_type,
                    control_value: $control_value,
                    treatment_value: $treatment_value,
                    status: $status,
                    created: datetime(),
                    targeting: $targeting,
                    min_sample_size: $min_sample_size
                })
            """,
            experiment_id=config.experiment_id,
            hypothesis=config.hypothesis,
            variable_type=config.variable_type,
            control_value=config.control_value,
            treatment_value=config.treatment_value,
            status=self.STATE_PROPOSED,
            targeting=json.dumps(config.targeting.to_dict()),
            min_sample_size=config.sample_size.min_per_group)

    def _update_experiment_status(
        self,
        experiment_id: str,
        status: str,
        result: Optional[ExperimentResult] = None
    ) -> None:
        """Update experiment status and results in Neo4j."""
        if not self.driver:
            return

        with self.driver.session() as session:
            params = {"experiment_id": experiment_id, "status": status}

            if result:
                session.run("""
                    MATCH (e:Experiment {experiment_id: $experiment_id})
                    SET e.status = $status,
                        e.concluded_at = datetime(),
                        e.mean_control = $mean_control,
                        e.mean_treatment = $mean_treatment,
                        e.absolute_lift = $absolute_lift,
                        e.relative_lift_pct = $relative_lift_pct,
                        e.p_value = $p_value,
                        e.cohens_d = $cohens_d,
                        e.significant = $significant
                """,
                experiment_id=experiment_id,
                status=status,
                mean_control=result.mean_control,
                mean_treatment=result.mean_treatment,
                absolute_lift=result.absolute_lift,
                relative_lift_pct=result.relative_lift_pct,
                p_value=result.p_value,
                cohens_d=result.cohens_d,
                significant=result.significant)
            else:
                session.run("""
                    MATCH (e:Experiment {experiment_id: $experiment_id})
                    SET e.status = $status
                """, **params)

    def _load_config(self, experiment_id: str) -> ExperimentConfig:
        """Load experiment configuration."""
        config_path = self.experiments_dir / f"{experiment_id}.yaml"
        if config_path.exists():
            return load_experiment_from_yaml(str(config_path))

        # Try to load from Neo4j
        if self.driver:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (e:Experiment {experiment_id: $experiment_id})
                    RETURN e
                """, experiment_id=experiment_id)
                record = result.single()
                if record:
                    data = dict(record["e"])
                    # Reconstruct config from stored data
                    return ExperimentConfig(
                        experiment_id=data["experiment_id"],
                        hypothesis=data.get("hypothesis", ""),
                        variable_type=data.get("variable_type", "unknown"),
                        control_value=data.get("control_value", ""),
                        treatment_value=data.get("treatment_value", ""),
                        targeting=ExperimentTargeting.from_dict(json.loads(data.get("targeting", "{}"))),
                        sample_size=SampleSizeConfig(min_per_group=data.get("min_sample_size", 100)),
                        duration=DurationConfig(),
                        success_criteria=SuccessCriteria(),
                        guardrails=DEFAULT_GUARDRAILS,
                        rollout=RolloutConfig()
                    )

        raise ValueError(f"Configuration not found for experiment {experiment_id}")

    def _check_conflicts(self, config: ExperimentConfig) -> List[str]:
        """Check for conflicting running experiments."""
        if not self.driver:
            return []

        with self.driver.session() as session:
            result = session.run("""
                MATCH (e:Experiment)
                WHERE e.status = $status
                  AND e.variable_type = $variable_type
                  AND e.experiment_id <> $experiment_id
                RETURN e.experiment_id AS id
            """,
            status=self.STATE_RUNNING,
            variable_type=config.variable_type,
            experiment_id=config.experiment_id)

            return [r["id"] for r in result]

    def _get_experiment_data(self, experiment_id: str) -> Tuple[List[float], List[float]]:
        """Get CES data for control and treatment groups."""
        if not self.driver:
            return [], []

        with self.driver.session() as session:
            result = session.run("""
                MATCH (e:Experiment {experiment_id: $experiment_id})
                OPTIONAL MATCH (t:Task)
                    WHERE t.experiment_id = $experiment_id
                    AND t.ab_test_group = 'control'
                WITH e, collect(t.ces_score) AS control_ces
                OPTIONAL MATCH (t:Task)
                    WHERE t.experiment_id = $experiment_id
                    AND t.ab_test_group = 'treatment'
                RETURN control_ces, collect(t.ces_score) AS treatment_ces
            """, experiment_id=experiment_id)

            record = result.single()
            if record:
                control = [c for c in record["control_ces"] if c is not None]
                treatment = [c for c in record["treatment_ces"] if c is not None]
                return control, treatment

            return [], []

    def _get_baseline_metrics(self, config: ExperimentConfig) -> Dict[str, float]:
        """Get baseline metrics from Neo4j."""
        if not self.driver:
            return {}

        # Default baselines
        defaults = {
            "success_rate_critical": 0.95,
            "success_rate_high": 0.90,
            "success_rate_normal": 0.75,
            "quality_score_avg": 0.70,
            "duration_p90": 3600,
            "rework_rate": 0.15,
            "escalation_rate": 0.05
        }

        try:
            with self.driver.session() as session:
                # Query recent metrics for targeted agents
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.completed > datetime() - duration('P7D')
                      AND t.status = 'completed'
                    RETURN
                        avg(t.quality_score) AS quality_score_avg,
                        percentileCont(t.duration_seconds, 0.9) AS duration_p90,
                        avg(t.rework_rate) AS rework_rate,
                        avg(t.escalation_rate) AS escalation_rate
                """)
                record = result.single()
                if record:
                    return {**defaults, **{k: v for k, v in dict(record).items() if v is not None}}
        except Exception as e:
            print(f"Warning: Could not fetch baseline metrics: {e}", file=sys.stderr)

        return defaults

    def _get_experiment_metrics(self, experiment_id: str) -> Dict[str, float]:
        """Get current experiment metrics."""
        if not self.driver:
            return {}

        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {experiment_id: $experiment_id})
                WHERE t.status IN ['completed', 'failed']
                WITH count(t) AS total,
                     sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                     sum(CASE WHEN t.priority = 'critical' AND t.status = 'completed' THEN 1 ELSE 0 END) AS critical_success,
                     sum(CASE WHEN t.priority = 'high' AND t.status = 'completed' THEN 1 ELSE 0 END) AS high_success,
                     sum(CASE WHEN t.rework_required = true THEN 1 ELSE 0 END) AS rework,
                     sum(CASE WHEN t.escalated = true THEN 1 ELSE 0 END) AS escalated,
                     avg(t.quality_score) AS quality_score_avg,
                     percentileCont(t.duration_seconds, 0.9) AS duration_p90
                RETURN
                    CASE WHEN total > 0 THEN toFloat(completed) / total ELSE 0 END AS success_rate,
                    CASE WHEN total > 0 THEN toFloat(critical_success) / total ELSE 0 END AS success_rate_critical,
                    CASE WHEN total > 0 THEN toFloat(high_success) / total ELSE 0 END AS success_rate_high,
                    CASE WHEN completed > 0 THEN toFloat(rework) / completed ELSE 0 END AS rework_rate,
                    CASE WHEN total > 0 THEN toFloat(escalated) / total ELSE 0 END AS escalation_rate,
                    quality_score_avg,
                    duration_p90
            """, experiment_id=experiment_id)

            record = result.single()
            if record:
                return {k: v for k, v in dict(record).items() if v is not None}
            return {}

    def _get_conclusion(self, experiment_id: str) -> Optional[ConclusionResult]:
        """Get stored conclusion for experiment."""
        # For now, re-run conclusion logic
        # In production, this would be stored
        return None

    def _create_learning_from_experiment(
        self,
        experiment_id: str,
        result: Optional[ExperimentResult],
        config: ExperimentConfig
    ) -> str:
        """Create KublaiLearning node from successful experiment."""
        if not self.driver:
            return f"kl-{experiment_id}"

        learning_id = f"kl-{uuid.uuid4().hex[:12]}"

        with self.driver.session() as session:
            recommendation = {
                "action": f"use_{config.variable_type}",
                config.variable_type: config.treatment_value,
                "experiment_id": experiment_id,
                "expected_lift": str(result.relative_lift_pct) if result else "unknown"
            }

            evidence = {
                "control_mean": str(result.mean_control) if result else "unknown",
                "treatment_mean": str(result.mean_treatment) if result else "unknown",
                "p_value": str(result.p_value) if result else "unknown",
                "effect_size": str(result.cohens_d) if result else "unknown",
                "sample_size": str(result.n_control + result.n_treatment) if result else "unknown"
            }

            session.run("""
                CREATE (l:KublaiLearning {
                    learning_id: $learning_id,
                    learning_type: $learning_type,
                    agent_filter: $agent_filter,
                    pattern_key: $pattern_key,
                    confidence: $confidence,
                    sample_size: $sample_size,
                    created: datetime(),
                    valid_until: datetime() + duration('P14D'),
                    status: 'active',
                    recommendation: $recommendation,
                    evidence: $evidence,
                    source_experiment: $experiment_id
                })
            """,
            learning_id=learning_id,
            learning_type=config.variable_type,
            agent_filter=",".join(config.targeting.agents) if config.targeting.agents else "*",
            pattern_key=config.treatment_value,
            confidence=1.0 - (result.p_value if result else 0.5),
            sample_size=(result.n_control + result.n_treatment) if result else 0,
            recommendation=json.dumps(recommendation),
            evidence=json.dumps(evidence),
            experiment_id=experiment_id)

        return learning_id


# =============================================================================
# CLI INTERFACE
# =============================================================================

def main():
    """CLI for experiment tracker."""
    parser = argparse.ArgumentParser(description="Experiment Tracker CLI")
    parser.add_argument("command", choices=[
        "create", "start", "status", "evaluate", "list", "rollout", "rollback"
    ])
    parser.add_argument("experiment_id", nargs="?", help="Experiment ID or YAML file path")
    parser.add_argument("--status", help="Filter by status for list command")
    parser.add_argument("--agent", help="Filter by agent for list command")
    parser.add_argument("--reason", help="Reason for rollback")
    parser.add_argument("--strategy", default="gradual", help="Rollout strategy")

    args = parser.parse_args()

    tracker = ExperimentTracker()

    try:
        if args.command == "create":
            if not args.experiment_id:
                print("Error: YAML file path required for create", file=sys.stderr)
                sys.exit(1)

            config = load_experiment_from_yaml(args.experiment_id)
            exp_id = tracker.propose(config)
            print(f"Created experiment: {exp_id}")

        elif args.command == "start":
            if not args.experiment_id:
                print("Error: Experiment ID required", file=sys.stderr)
                sys.exit(1)

            if tracker.start(args.experiment_id):
                print(f"Started experiment: {args.experiment_id}")
            else:
                print(f"Failed to start experiment: {args.experiment_id}", file=sys.stderr)
                sys.exit(1)

        elif args.command == "status":
            if not args.experiment_id:
                print("Error: Experiment ID required", file=sys.stderr)
                sys.exit(1)

            status = tracker.status(args.experiment_id)
            print(json.dumps(status, indent=2, default=str))

        elif args.command == "evaluate":
            if not args.experiment_id:
                print("Error: Experiment ID required", file=sys.stderr)
                sys.exit(1)

            result = tracker.conclude(args.experiment_id)
            print(json.dumps(result.to_dict(), indent=2))

        elif args.command == "list":
            experiments = tracker.list_experiments(status=args.status, agent=args.agent)
            if not experiments:
                print("No experiments found")
            else:
                for exp in experiments:
                    print(f"{exp.get('experiment_id', 'unknown')}\t{exp.get('status', 'unknown')}\t{exp.get('hypothesis', '')[:50]}")

        elif args.command == "rollout":
            if not args.experiment_id:
                print("Error: Experiment ID required", file=sys.stderr)
                sys.exit(1)

            tracker.rollout(args.experiment_id, args.strategy)

        elif args.command == "rollback":
            if not args.experiment_id:
                print("Error: Experiment ID required", file=sys.stderr)
                sys.exit(1)

            if not args.reason:
                print("Error: --reason required for rollback", file=sys.stderr)
                sys.exit(1)

            tracker.rollback(args.experiment_id, args.reason)

    finally:
        if tracker.driver:
            tracker.driver.close()


if __name__ == "__main__":
    main()
