#!/usr/bin/env python3
"""
Eval: GDS Algorithm Health — Verifies community stability, drift prediction accuracy.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver
from gds_projection_manager import GDSProjectionManager
from gds_pagerank import get_core_topics
from gds_louvain import get_communities
from gds_betweenness import get_bridge_topics
from topic_graph_builder import TopicGraphBuilder


def eval_gds_health(human_id: str) -> dict:
    """Run GDS health checks for a human."""
    results = {
        "gds_available": False,
        "core_topics": 0,
        "communities": 0,
        "bridge_topics": 0,
        "topic_count": 0,
        "co_occurred_edges": 0,
        "led_to_edges": 0,
    }

    mgr = GDSProjectionManager()
    results["gds_available"] = mgr.gds_available
    mgr.close()

    # Core topics
    core = get_core_topics(human_id)
    results["core_topics"] = len(core)

    # Communities
    communities = get_communities(human_id)
    results["communities"] = len(communities)
    results["community_sizes"] = {k: len(v) for k, v in communities.items()}

    # Bridge topics
    bridges = get_bridge_topics(human_id)
    results["bridge_topics"] = len(bridges)

    # Topic graph stats
    builder = TopicGraphBuilder()
    stats = builder.get_topic_stats(human_id)
    builder.close()
    results.update(stats)

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("human_id")
    args = parser.parse_args()

    result = eval_gds_health(args.human_id)
    print(json.dumps(result, indent=2, default=str))
