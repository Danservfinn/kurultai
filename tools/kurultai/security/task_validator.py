"""Task validator for Kurultai v0.2.

Validates deliverable types, priority weights, and task metadata
before they enter the task pipeline.
"""

from typing import Set

VALID_DELIVERABLE_TYPES: Set[str] = {
    "analysis", "report", "code", "documentation",
    "deployment", "investigation", "monitoring", "review",
}

PRIORITY_WEIGHT_MIN = 0.0
PRIORITY_WEIGHT_MAX = 1.0


class TaskValidator:
    """Validates task properties before Neo4j persistence."""

    @staticmethod
    def validate_deliverable_type(deliverable_type: str) -> str:
        """Validate deliverable type against allowed values.

        Args:
            deliverable_type: Type to validate.

        Returns:
            The validated type (lowercased).

        Raises:
            ValueError: If type is not in allowed set.
        """
        normalized = deliverable_type.strip().lower()
        if normalized not in VALID_DELIVERABLE_TYPES:
            raise ValueError(
                f"Invalid deliverable type '{deliverable_type}'. "
                f"Must be one of: {sorted(VALID_DELIVERABLE_TYPES)}"
            )
        return normalized

    @staticmethod
    def validate_priority_weight(weight: float) -> float:
        """Validate priority weight is in [0.0, 1.0].

        Args:
            weight: Priority weight to validate.

        Returns:
            The validated weight.

        Raises:
            ValueError: If weight is out of range.
        """
        if not isinstance(weight, (int, float)):
            raise ValueError(f"Priority weight must be numeric, got {type(weight).__name__}")
        if weight < PRIORITY_WEIGHT_MIN or weight > PRIORITY_WEIGHT_MAX:
            raise ValueError(
                f"Priority weight {weight} out of range "
                f"[{PRIORITY_WEIGHT_MIN}, {PRIORITY_WEIGHT_MAX}]"
            )
        return float(weight)

    @staticmethod
    def validate_task_id(task_id: str) -> str:
        """Validate task ID format (non-empty string)."""
        if not task_id or not isinstance(task_id, str):
            raise ValueError("Task ID must be a non-empty string")
        return task_id.strip()
