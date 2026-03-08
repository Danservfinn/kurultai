#!/usr/bin/env python3
"""
Feature Flags for Kurultai Experiment Safety Rails

Provides deterministic rollout based on task_id hash, enabling gradual
feature deployment and canary testing.

Usage:
    from feature_flags import should_use_experiment, increment_rollout

    if should_use_experiment("experiment-router-v2", task_id):
        # Use experimental path
    else:
        # Use baseline path
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# Feature flags configuration file
FEATURE_FLAGS_PATH = Path(__file__).parent.parent.parent / "config" / "feature_flags.json"


@dataclass
class FeatureFlag:
    """Configuration for a single feature flag."""
    name: str
    enabled: bool = True
    rollout_pct: int = 0  # 0-100
    canary: bool = False
    rollback_on_error_rate: float = 2.0  # Multiplier of baseline error rate
    created: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    modified: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "rollout_pct": self.rollout_pct,
            "canary": self.canary,
            "rollback_on_error_rate": self.rollback_on_error_rate,
            "created": self.created,
            "modified": self.modified,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FeatureFlag":
        return cls(
            name=data["name"],
            enabled=data.get("enabled", True),
            rollout_pct=data.get("rollout_pct", 0),
            canary=data.get("canary", False),
            rollback_on_error_rate=data.get("rollback_on_error_rate", 2.0),
            created=data.get("created", datetime.utcnow().isoformat()),
            modified=data.get("modified", datetime.utcnow().isoformat()),
        )


# Default feature flags for Kurultai experiments
DEFAULT_FEATURE_FLAGS = {
    "experiment-router-v2": FeatureFlag(
        name="experiment-router-v2",
        enabled=True,
        rollout_pct=5,
        canary=True,
        rollback_on_error_rate=2.0,
    ),
    "experiment-scorer-v2": FeatureFlag(
        name="experiment-scorer-v2",
        enabled=False,
        rollout_pct=0,
        canary=True,
        rollback_on_error_rate=1.5,
    ),
    "experiment-task-parallelizer": FeatureFlag(
        name="experiment-task-parallelizer",
        enabled=True,
        rollout_pct=10,
        canary=False,
        rollback_on_error_rate=3.0,
    ),
}


class FeatureFlagManager:
    """Manages feature flags with persistence."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or FEATURE_FLAGS_PATH
        self._flags: dict[str, FeatureFlag] = {}
        self._load_flags()

    def _load_flags(self) -> None:
        """Load flags from config file or use defaults."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                self._flags = {
                    name: FeatureFlag.from_dict(flag_data)
                    for name, flag_data in data.items()
                }
            except (json.JSONDecodeError, KeyError):
                self._flags = dict(DEFAULT_FEATURE_FLAGS)
        else:
            self._flags = dict(DEFAULT_FEATURE_FLAGS)

    def _save_flags(self) -> None:
        """Persist flags to config file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {name: flag.to_dict() for name, flag in self._flags.items()}
        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2)

    def get_flag(self, name: str) -> Optional[FeatureFlag]:
        """Get a feature flag by name."""
        return self._flags.get(name)

    def set_flag(self, flag: FeatureFlag) -> None:
        """Create or update a feature flag."""
        flag.modified = datetime.utcnow().isoformat()
        self._flags[flag.name] = flag
        self._save_flags()

    def list_flags(self) -> list[FeatureFlag]:
        """List all feature flags."""
        return list(self._flags.values())


# Global manager instance
_manager: Optional[FeatureFlagManager] = None


def _get_manager() -> FeatureFlagManager:
    """Get or create the global feature flag manager."""
    global _manager
    if _manager is None:
        _manager = FeatureFlagManager()
    return _manager


def should_use_experiment(feature_name: str, task_id: str) -> bool:
    """
    Determine if an experiment should be used for a given task.

    Uses deterministic hashing based on task_id to ensure consistent
    assignment - same task_id always gets the same result.

    Args:
        feature_name: Name of the feature flag
        task_id: Unique identifier for the task

    Returns:
        True if the experiment should be used, False otherwise

    Example:
        >>> should_use_experiment("test-feature", "task-123")
        True  # Always same result for same feature+task_id
        >>> should_use_experiment("test-feature", "task-123")
        True
    """
    manager = _get_manager()
    flag = manager.get_flag(feature_name)

    if flag is None or not flag.enabled:
        return False

    if flag.rollout_pct <= 0:
        return False

    if flag.rollout_pct >= 100:
        return True

    # Deterministic hash-based assignment
    hash_val = int(hashlib.sha256(task_id.encode()).hexdigest()[:8], 16)
    return (hash_val % 100) < flag.rollout_pct


def increment_rollout(feature_name: str, step: int = 5) -> bool:
    """
    Increase rollout percentage after canary success.

    Args:
        feature_name: Name of the feature flag
        step: Percentage points to increase (default 5)

    Returns:
        True if rollout was incremented, False if flag doesn't exist
        or is at 100%
    """
    manager = _get_manager()
    flag = manager.get_flag(feature_name)

    if flag is None:
        return False

    new_pct = min(100, flag.rollout_pct + step)
    if new_pct == flag.rollout_pct:
        return False  # Already at 100%

    flag.rollout_pct = new_pct
    flag.modified = datetime.utcnow().isoformat()
    manager.set_flag(flag)

    return True


def rollback_rollout(feature_name: str) -> bool:
    """
    Instantly disable a feature flag (set rollout to 0).

    Args:
        feature_name: Name of the feature flag

    Returns:
        True if rollback succeeded, False if flag doesn't exist
    """
    manager = _get_manager()
    flag = manager.get_flag(feature_name)

    if flag is None:
        return False

    flag.enabled = False
    flag.rollout_pct = 0
    flag.modified = datetime.utcnow().isoformat()
    manager.set_flag(flag)

    return True


def get_rollout_status(feature_name: str) -> dict:
    """
    Get current status of a feature rollout.

    Returns:
        Dict with enabled, rollout_pct, canary status
    """
    manager = _get_manager()
    flag = manager.get_flag(feature_name)

    if flag is None:
        return {"exists": False}

    return {
        "exists": True,
        "enabled": flag.enabled,
        "rollout_pct": flag.rollout_pct,
        "canary": flag.canary,
        "rollback_on_error_rate": flag.rollback_on_error_rate,
        "created": flag.created,
        "modified": flag.modified,
    }


def create_feature_flag(
    name: str,
    rollout_pct: int = 0,
    canary: bool = True,
    rollback_on_error_rate: float = 2.0,
) -> FeatureFlag:
    """
    Create a new feature flag.

    Args:
        name: Unique name for the feature
        rollout_pct: Initial rollout percentage (0-100)
        canary: Whether to use canary deployment pattern
        rollback_on_error_rate: Error rate multiplier threshold for auto-rollback

    Returns:
        The created FeatureFlag
    """
    manager = _get_manager()
    flag = FeatureFlag(
        name=name,
        enabled=True,
        rollout_pct=rollout_pct,
        canary=canary,
        rollback_on_error_rate=rollback_on_error_rate,
    )
    manager.set_flag(flag)
    return flag


if __name__ == "__main__":
    # Demo / test
    import sys

    print("Feature Flags Demo")
    print("=" * 50)

    # Test deterministic rollout
    test_tasks = ["task-001", "task-002", "task-003", "task-004", "task-005"]
    feature = "experiment-router-v2"

    print(f"\nTesting feature: {feature}")
    print(f"Tasks with experiment enabled:")
    for task_id in test_tasks:
        if should_use_experiment(feature, task_id):
            print(f"  {task_id}: YES")

    # Verify determinism
    print("\nVerifying determinism (same result each time):")
    for _ in range(3):
        result = should_use_experiment(feature, "task-123")
        print(f"  task-123: {result}")
        assert result == should_use_experiment(feature, "task-123")

    print("\nFeature flags are deterministic!")

    # Show status
    print(f"\nCurrent status for {feature}:")
    status = get_rollout_status(feature)
    for k, v in status.items():
        print(f"  {k}: {v}")