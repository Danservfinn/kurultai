#!/usr/bin/env python3
"""
Shared Metric Calculations - Common analytics utilities.

Consolidates duplicate metric calculation functions from:
- score_skills.py
- update_skill_stats.py
- self_healing_score.py
- routing_accuracy_tracker.py

Usage:
    from metrics import calculate_success_rate, compute_trend, recommended_action

    success_rate = calculate_success_rate(events, success_field='completed')
    trend = compute_trend(current_rate, previous_rate)
    action = recommended_action(success_rate)
"""

from typing import List, Dict, Any, Optional, Literal
from dataclasses import dataclass


@dataclass
class TrendResult:
    """Result of trend computation."""
    direction: Literal['improving', 'declining', 'stable']
    change_percent: float
    threshold: float


def calculate_success_rate(
    events: List[Dict[str, Any]],
    success_field: str = 'success',
    filter_func: Optional[callable] = None
) -> float:
    """Calculate success rate from a list of events.

    Args:
        events: List of event dictionaries
        success_field: Field name to check for success (default: 'success')
            Can also be 'completed', 'passed', etc.
        filter_func: Optional function to filter events before calculation

    Returns:
        Success rate as float 0.0-1.0

    Example:
        events = [{'success': True}, {'success': False}, {'success': True}]
        rate = calculate_success_rate(events)  # 0.666...
    """
    if not events:
        return 0.0

    if filter_func:
        events = [e for e in events if filter_func(e)]

    if not events:
        return 0.0

    successes = sum(1 for e in events if e.get(success_field, False))
    return successes / len(events)


def compute_trend(
    current: float,
    previous: float,
    threshold: float = 0.1
) -> TrendResult:
    """Compute trend direction from two values.

    Args:
        current: Current value
        previous: Previous value (baseline)
        threshold: Minimum percent change to consider significant (default: 10%)

    Returns:
        TrendResult with direction, change_percent, and threshold

    Example:
        result = compute_trend(0.85, 0.70)
        # result.direction == 'improving'
        # result.change_percent == 21.43
    """
    if previous == 0:
        if current == 0:
            return TrendResult('stable', 0.0, threshold)
        return TrendResult('improving', 100.0, threshold)

    change = (current - previous) / previous

    if change > threshold:
        return TrendResult('improving', change * 100, threshold)
    elif change < -threshold:
        return TrendResult('declining', change * 100, threshold)
    return TrendResult('stable', change * 100, threshold)


def recommended_action(
    success_rate: float,
    improve_threshold: float = 0.7,
    review_threshold: float = 0.4
) -> Literal['keep', 'review', 'disable']:
    """Get recommended action based on success rate.

    Args:
        success_rate: Current success rate (0.0-1.0)
        improve_threshold: Rate above which to keep (default: 0.7)
        review_threshold: Rate above which to review (default: 0.4)

    Returns:
        'keep', 'review', or 'disable'

    Example:
        action = recommended_action(0.85)  # 'keep'
        action = recommended_action(0.55)  # 'review'
        action = recommended_action(0.25)  # 'disable'
    """
    if success_rate >= improve_threshold:
        return 'keep'
    elif success_rate >= review_threshold:
        return 'review'
    return 'disable'


def moving_average(
    values: List[float],
    window: int = 5
) -> List[float]:
    """Calculate simple moving average.

    Args:
        values: List of numeric values
        window: Window size for averaging

    Returns:
        List of averaged values (same length, padded with first value)
    """
    if not values or window <= 0:
        return []

    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        window_values = values[start:i + 1]
        result.append(sum(window_values) / len(window_values))

    return result


def exponential_moving_average(
    values: List[float],
    alpha: float = 0.3
) -> List[float]:
    """Calculate exponential moving average.

    Args:
        values: List of numeric values
        alpha: Smoothing factor (0-1). Higher = more weight on recent values.

    Returns:
        List of EMA values
    """
    if not values:
        return []

    result = [values[0]]
    for i in range(1, len(values)):
        ema = alpha * values[i] + (1 - alpha) * result[-1]
        result.append(ema)

    return result


def percentile(
    values: List[float],
    p: float
) -> float:
    """Calculate percentile of a list.

    Args:
        values: List of numeric values
        p: Percentile (0-100)

    Returns:
        Value at percentile p
    """
    if not values:
        return 0.0

    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * p / 100
    f = int(k)
    c = f + 1

    if c >= len(sorted_values):
        return sorted_values[-1]

    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


def aggregate_by_key(
    items: List[Dict[str, Any]],
    key_field: str,
    value_field: str = 'value',
    aggregation: str = 'sum'
) -> Dict[str, float]:
    """Aggregate items by a key field.

    Args:
        items: List of dictionaries
        key_field: Field to group by
        value_field: Field to aggregate
        aggregation: 'sum', 'count', 'avg', 'min', 'max'

    Returns:
        Dict mapping keys to aggregated values

    Example:
        items = [{'agent': 'temujin', 'tasks': 5},
                 {'agent': 'temujin', 'tasks': 3},
                 {'agent': 'mongke', 'tasks': 2}]
        result = aggregate_by_key(items, 'agent', 'tasks', 'sum')
        # {'temujin': 8, 'mongke': 2}
    """
    from collections import defaultdict

    groups: Dict[str, List[float]] = defaultdict(list)

    for item in items:
        key = item.get(key_field)
        value = item.get(value_field, 0)
        if key is not None:
            groups[str(key)].append(float(value))

    result = {}
    for key, values in groups.items():
        if aggregation == 'sum':
            result[key] = sum(values)
        elif aggregation == 'count':
            result[key] = len(values)
        elif aggregation == 'avg':
            result[key] = sum(values) / len(values) if values else 0
        elif aggregation == 'min':
            result[key] = min(values) if values else 0
        elif aggregation == 'max':
            result[key] = max(values) if values else 0

    return result


def normalize_score(
    value: float,
    min_val: float,
    max_val: float
) -> float:
    """Normalize a value to 0-1 range.

    Args:
        value: Value to normalize
        min_val: Minimum possible value
        max_val: Maximum possible value

    Returns:
        Normalized value (0-1)
    """
    if max_val == min_val:
        return 0.5
    return (value - min_val) / (max_val - min_val)


def weighted_average(
    values: List[float],
    weights: List[float]
) -> float:
    """Calculate weighted average.

    Args:
        values: List of values
        weights: List of weights (same length)

    Returns:
        Weighted average

    Raises:
        ValueError: If lengths don't match or weights sum to zero
    """
    if len(values) != len(weights):
        raise ValueError("Values and weights must have same length")

    total_weight = sum(weights)
    if total_weight == 0:
        raise ValueError("Weights sum to zero")

    return sum(v * w for v, w in zip(values, weights)) / total_weight
