#!/usr/bin/env python3
"""
Eval: Engagement Decision — Computes fn_rate and fp_rate from behavioral proxy labels.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engagement_learner import get_decision_accuracy


def eval_engagement(human_id: str, days: int = 30) -> dict:
    """Evaluate engagement decision quality."""
    accuracy = get_decision_accuracy(human_id, days)
    return {
        "human_id": human_id[:8],
        "window_days": days,
        **accuracy,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("human_id")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    result = eval_engagement(args.human_id, args.days)
    print(json.dumps(result, indent=2))
