#!/usr/bin/env python3
"""Deferred voting phase launcher.

Runs after all Phase 3 proposals complete. Creates voting tasks
with embedded proposal context, quality-gated.

Usage:
    python3 launch_voting_phase.py --pipeline reflection-2026-03-24
    python3 launch_voting_phase.py --pipeline reflection-2026-03-24 --dry-run
"""
import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_v2_core import TaskStore
from agents_config import AGENTS

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

AGENT_COUNT = len(AGENTS)
MIN_PROPOSAL_LENGTH = 100
MIN_PROPOSALS_REQUIRED = 3


def fetch_proposals(store, pid):
    """Fetch Phase 3 outputs with quality gate."""
    with store.driver.session() as s:
        result = s.run("""
            MATCH (t:Task {pipeline_id: $pid, phase: 3, status: 'COMPLETED'})
            OPTIONAL MATCH (t)-[:HAS_OUTPUT]->(o:TaskOutput)
            RETURN t.task_id AS tid, t.title AS title, t.assigned_to AS agent,
                   o.text AS text, o.solution AS solution, o.rationale AS rationale
            ORDER BY t.assigned_to
        """, pid=pid)
        proposals = []
        for r in result:
            content = r["text"] or r["solution"] or ""
            if len(content) >= MIN_PROPOSAL_LENGTH:
                proposals.append({
                    "task_id": r["tid"],
                    "title": r["title"],
                    "agent": r["agent"],
                    "content": content,
                    "rationale": r["rationale"] or "",
                })
            else:
                print(f"QUALITY GATE: Skipping {r['tid']} ({len(content)} chars < {MIN_PROPOSAL_LENGTH})")
        return proposals


def build_vote_prompt(agent, proposals, pid):
    """Build a rich voting prompt with all proposal content."""
    sections = [f"# Vote on Proposals — Pipeline {pid}\n"]
    sections.append(f"You are **{agent.upper()}**, voting on {len(proposals)} proposals.\n")
    sections.append("For each proposal, respond with APPROVE or REJECT + one-line reason.\n")

    for i, p in enumerate(proposals, 1):
        sections.append(f"## Proposal {i}: {p['title']} (by {p['agent']})")
        sections.append(p["content"][:2000])
        if p["rationale"]:
            sections.append(f"**Rationale:** {p['rationale'][:500]}")
        sections.append("")

    sections.append("## Your Votes\nFor each proposal, output:\n")
    sections.append("PROPOSAL_ID: {task_id}\nVOTE: APPROVE or REJECT\nREASON: one sentence\n")
    return "\n".join(sections)


def create_downstream_tasks(store, pid, consensus_tid, source, dry_run, agent_name):
    """Create Phase 7-10 downstream tasks depending on the consensus sentinel."""
    task_ids = {}

    # Phase 7 Tier 0: Post-review — 2 tasks
    post_review_ids = []
    for name, cmd, timeout in [
        ("anomaly-scan", "python3 reflection_anomaly_scanner.py", 60),
        ("rule-compliance", "python3 parse_rule_compliance.py", 30),
    ]:
        tid = f"{pid}-{name}"
        if not dry_run:
            store.create_task(
                task_id=tid,
                title=f"Post-review: {name}",
                prompt=cmd,
                assigned_to=agent_name("ogedei"),
                priority="normal",
                domain="analysis",
                source=source,
                depends_on=[consensus_tid],
                pipeline_id=pid,
                phase=7,
                timeout_s=timeout,
                max_retries=1,
            )
        post_review_ids.append(tid)
        print(f"{'[DRY-RUN] ' if dry_run else ''}Created post-review task: {tid}")
    task_ids["post_review"] = post_review_ids

    # Phase 8 Tier 1: Downstream scoring — 6 parallel tasks
    tier1_scripts = [
        ("memory-audit", "python3 memory_audit.py --fix", 30),
        ("cross-agent-rules", "python3 cross_agent_rules.py", 30),
        ("route-quality", "python3 route_quality_tracker.py", 30),
        ("routing-audit", "python3 routing_audit_action.py", 30),
        ("neo4j-scorer", "python3 neo4j_v2_scorer.py --update-all", 30),
        ("action-scorer", "python3 action_scorer.py", 30),
    ]
    tier1_ids = []
    for name, cmd, timeout in tier1_scripts:
        tid = f"{pid}-{name}"
        if not dry_run:
            store.create_task(
                task_id=tid,
                title=f"Downstream: {name}",
                prompt=cmd,
                assigned_to=agent_name("ogedei"),
                priority="normal",
                domain="scoring",
                source=source,
                depends_on=post_review_ids,
                pipeline_id=pid,
                phase=8,
                timeout_s=timeout,
                max_retries=1,
            )
        tier1_ids.append(tid)
        print(f"{'[DRY-RUN] ' if dry_run else ''}Created tier1 task: {tid}")
    task_ids["tier1"] = tier1_ids

    # Phase 9 Tier 2: Skill stats
    tier2_tid = f"{pid}-skill-stats"
    if not dry_run:
        store.create_task(
            task_id=tier2_tid,
            title="Downstream: update-skill-stats",
            prompt="python3 update_skill_stats.py",
            assigned_to=agent_name("ogedei"),
            priority="normal",
            domain="scoring",
            source=source,
            depends_on=tier1_ids,
            pipeline_id=pid,
            phase=9,
            timeout_s=30,
            max_retries=1,
        )
    print(f"{'[DRY-RUN] ' if dry_run else ''}Created tier2 task: {tier2_tid}")
    task_ids["tier2"] = [tier2_tid]

    # Phase 10 Tier 3: Final reports
    tier3_scripts = [
        ("kublai-actions", "python3 kublai-actions.py --trigger kurultai", 60),
        ("daily-report", "python3 generate_hourly_report.py", 60),
    ]
    tier3_ids = []
    for name, cmd, timeout in tier3_scripts:
        tid = f"{pid}-{name}"
        if not dry_run:
            store.create_task(
                task_id=tid,
                title=f"Final: {name}",
                prompt=cmd,
                assigned_to=agent_name("ogedei"),
                priority="normal",
                domain="reporting",
                source=source,
                depends_on=[tier2_tid],
                pipeline_id=pid,
                phase=10,
                timeout_s=timeout,
                max_retries=1,
            )
        tier3_ids.append(tid)
        print(f"{'[DRY-RUN] ' if dry_run else ''}Created tier3 task: {tid}")
    task_ids["tier3"] = tier3_ids

    return task_ids


def main():
    parser = argparse.ArgumentParser(description="Deferred voting phase launcher")
    parser.add_argument("--pipeline", required=True, help="Pipeline ID")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate without creating tasks")
    args = parser.parse_args()

    store = TaskStore()
    pid = args.pipeline
    source = "pipeline"

    def agent_name(agent):
        return agent

    try:
        # 1. Quality-gated proposals
        proposals = fetch_proposals(store, pid)
        if len(proposals) < MIN_PROPOSALS_REQUIRED:
            print(f"ABORT: Only {len(proposals)} proposals passed quality gate "
                  f"(need {MIN_PROPOSALS_REQUIRED})")
            sys.exit(1)

        print(f"Quality gate passed: {len(proposals)} proposals")

        # 2. Create voting tasks with embedded proposal context
        vote_ids = []
        for agent in AGENTS:
            tid = f"{pid}-vote-{agent}"
            prompt = build_vote_prompt(agent, proposals, pid)
            if not args.dry_run:
                store.create_task(
                    task_id=tid,
                    title=f"Vote on proposals: {agent}",
                    prompt=prompt,
                    assigned_to=agent,
                    priority="high",
                    domain="voting",
                    source=source,
                    depends_on=[],    # No deps — created only after proposals verified
                    pipeline_id=pid,
                    phase=4,
                    timeout_s=600,
                    max_retries=1,
                )
            vote_ids.append(tid)
            print(f"{'[DRY-RUN] ' if args.dry_run else ''}Created vote task: {tid}")

        # 3. Consensus sentinel
        consensus_tid = f"{pid}-consensus"
        if not args.dry_run:
            store.create_task(
                task_id=consensus_tid,
                title="Consensus check + approval routing",
                prompt=f"python3 pipeline_monitor.py --consensus {pid} --complete-sentinel",
                assigned_to="ogedei",
                priority="high",
                domain="consensus",
                source=source,
                depends_on=vote_ids,
                pipeline_id=pid,
                phase=5,
                timeout_s=600,
                max_retries=1,
            )
        print(f"{'[DRY-RUN] ' if args.dry_run else ''}Created consensus sentinel: {consensus_tid}")

        # 4. Downstream tasks (phases 7-10)
        downstream = create_downstream_tasks(
            store, pid, consensus_tid, source, args.dry_run, agent_name
        )

        summary = {
            "pipeline_id": pid,
            "proposals_found": len(proposals),
            "vote_tasks_created": len(vote_ids),
            "consensus_sentinel": consensus_tid,
            "downstream_tasks": sum(len(v) for v in downstream.values()),
            "dry_run": args.dry_run,
        }
        print(json.dumps(summary, indent=2))

    finally:
        store.close()


if __name__ == "__main__":
    main()
