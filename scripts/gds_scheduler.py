#!/usr/bin/env python3
"""
GDS Scheduler — Cron-compatible runner for GDS algorithm refresh.

Daily: PageRank, Louvain, Betweenness
Weekly: Drift detection, Link prediction, FastRP, Social network

Usage:
    python3 gds_scheduler.py --daily           # Run daily algorithms
    python3 gds_scheduler.py --weekly          # Run weekly algorithms
    python3 gds_scheduler.py --all             # Run everything
    python3 gds_scheduler.py --human UUID      # Run for specific human
"""

import argparse
import logging
import time
from typing import Dict, Any, List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session
from gds_projection_manager import GDSProjectionManager
from gds_pagerank import run_pagerank
from gds_louvain import run_louvain
from gds_betweenness import run_betweenness
from gds_link_prediction import run_link_prediction
from gds_fastrp import run_fastrp
from gds_drift_detection import detect_drift
from gds_social_network import run_connected_components
from topic_graph_builder import TopicGraphBuilder

logger = logging.getLogger(__name__)


def get_active_humans() -> List[str]:
    """Get all active human IDs."""
    with neo4j_session() as session:
        result = session.run(
            """
            MATCH (h:Human {status: 'active'})
            WHERE exists((h)-[:DISCUSSED]->(:Topic))
            RETURN h.id AS id
            """
        )
        return [r["id"] for r in result]


def run_daily(human_ids: List[str] = None) -> Dict[str, Any]:
    """Run daily GDS algorithms."""
    t0 = time.monotonic()
    if not human_ids:
        human_ids = get_active_humans()

    results = {"humans": len(human_ids), "pagerank": 0, "louvain": 0, "betweenness": 0}

    # Rebuild topic graph edges first
    builder = TopicGraphBuilder()

    mgr = GDSProjectionManager()

    for hid in human_ids:
        try:
            # Refresh topic graph
            builder.build_co_occurrence(hid)
            builder.build_temporal_flow(hid)

            # Refresh projection
            mgr.refresh_projection(hid)

            # Run algorithms
            pr = run_pagerank(hid)
            results["pagerank"] += len(pr)

            lv = run_louvain(hid)
            results["louvain"] += len(lv)

            bt = run_betweenness(hid)
            results["betweenness"] += len(bt)

        except Exception as e:
            logger.error(f"Daily GDS failed for {hid[:8]}: {e}")

    builder.close()
    mgr.close()

    results["ms"] = round((time.monotonic() - t0) * 1000)
    return results


def run_weekly(human_ids: List[str] = None) -> Dict[str, Any]:
    """Run weekly GDS algorithms."""
    t0 = time.monotonic()
    if not human_ids:
        human_ids = get_active_humans()

    results = {
        "humans": len(human_ids),
        "drift": 0, "link_prediction": 0, "fastrp": 0, "social": 0,
    }

    # Topic abstractions (global)
    builder = TopicGraphBuilder()
    builder.build_abstractions()
    builder.close()

    for hid in human_ids:
        try:
            drift = detect_drift(hid)
            results["drift"] += len(drift.get("rising", [])) + len(drift.get("fading", []))

            lp = run_link_prediction(hid)
            results["link_prediction"] += len(lp)

            frp = run_fastrp(hid)
            results["fastrp"] += len(frp)

        except Exception as e:
            logger.error(f"Weekly GDS failed for {hid[:8]}: {e}")

    # Social network (global)
    try:
        social = run_connected_components()
        results["social"] = len(social)
    except Exception as e:
        logger.error(f"Social network analysis failed: {e}")

    results["ms"] = round((time.monotonic() - t0) * 1000)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GDS Algorithm Scheduler")
    parser.add_argument("--daily", action="store_true", help="Run daily algorithms")
    parser.add_argument("--weekly", action="store_true", help="Run weekly algorithms")
    parser.add_argument("--all", action="store_true", help="Run all algorithms")
    parser.add_argument("--human", help="Run for specific human UUID")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    human_ids = [args.human] if args.human else None

    if args.daily or args.all:
        print("Running daily GDS algorithms...")
        result = run_daily(human_ids)
        print(f"  Daily: {result}")

    if args.weekly or args.all:
        print("Running weekly GDS algorithms...")
        result = run_weekly(human_ids)
        print(f"  Weekly: {result}")

    if not any([args.daily, args.weekly, args.all]):
        parser.print_help()
