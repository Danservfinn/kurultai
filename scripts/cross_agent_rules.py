#!/usr/bin/env python3
"""
cross_agent_rules.py — Rule propagation pipeline.

Runs hourly after reflections. Finds proven rules (invocations >= 3) and
proposes them to related agents as RuleProposal nodes in Neo4j.

Anti-groupthink safeguards:
- Only related agents (DOMAIN_OVERLAP matrix)
- Only proven rules (3+ invocations)
- Max 2 proposals per target agent per cycle
- 24h cooldown per (source, rule) pair targeting the same agent

Usage:
    python3 cross_agent_rules.py
    python3 cross_agent_rules.py --dry-run
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import LOGS_DIR

# Domain overlap: which agents share enough domain overlap for rule propagation
# kublai->none: kublai is a router, rules don't transfer to specialists
DOMAIN_OVERLAP = {
    "temujin": ["jochi", "ogedei"],
    "jochi":   ["temujin", "ogedei"],
    "ogedei":  ["temujin", "jochi"],
    "mongke":  ["chagatai"],
    "chagatai": ["mongke"],
    "kublai":  [],  # Router — no rule propagation out
}

MIN_INVOCATIONS = 3
MAX_PROPOSALS_PER_CYCLE = 2
COOLDOWN_HOURS = 24
COOLDOWN_FILE = LOGS_DIR / "cross-agent-rules-cooldown.json"


def _load_cooldown():
    """Load cooldown state: {(source, rule_id, target): last_proposed_iso}"""
    if not COOLDOWN_FILE.exists():
        return {}
    try:
        with open(COOLDOWN_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cooldown(cooldown):
    try:
        os.makedirs(str(LOGS_DIR), exist_ok=True)
        with open(COOLDOWN_FILE, "w") as f:
            json.dump(cooldown, f, indent=2)
    except Exception:
        pass


def _is_on_cooldown(cooldown, source_agent, rule_id, target_agent):
    key = f"{source_agent}|{rule_id}|{target_agent}"
    last_str = cooldown.get(key)
    if not last_str:
        return False
    try:
        last = datetime.fromisoformat(last_str)
        return datetime.now() - last < timedelta(hours=COOLDOWN_HOURS)
    except (ValueError, TypeError):
        return False


def _mark_cooldown(cooldown, source_agent, rule_id, target_agent):
    key = f"{source_agent}|{rule_id}|{target_agent}"
    cooldown[key] = datetime.now().isoformat()


def run(dry_run=False):
    """Main propagation pipeline."""
    try:
        from neo4j_task_tracker import get_driver
        driver = get_driver()
    except Exception as exc:
        print(f"Neo4j unavailable: {exc}")
        return

    cooldown = _load_cooldown()
    proposals_created = 0

    try:
        # 1. Query proven rules
        with driver.session() as session:
            result = session.run(
                """
                MATCH (r:Rule)
                WHERE r.status = 'active' AND r.invocations >= $min_inv
                RETURN r.id AS rule_id, r.agent AS source_agent,
                       r.condition AS condition, r.action AS action,
                       r.invocations AS invocations
                ORDER BY r.invocations DESC
                LIMIT 50
                """,
                min_inv=MIN_INVOCATIONS,
            )
            rules = [dict(row) for row in result]

        print(f"Found {len(rules)} proven rules (invocations >= {MIN_INVOCATIONS})")

        if not rules:
            # Provide actionable guidance when no rules qualify
            with driver.session() as session:
                count_result = session.run("MATCH (r:Rule) RETURN count(r) AS total")
                total_rules = count_result.single()["total"]
            if total_rules == 0:
                print(
                    "INFO: No Rule nodes found in Neo4j. Rules are created when agents "
                    "reflect and generate WHEN/THEN rules. Run reflections first, then "
                    "rules will be synced via the reflection pipeline."
                )
            else:
                print(
                    f"INFO: {total_rules} Rule node(s) exist but none meet the threshold "
                    f"(invocations >= {MIN_INVOCATIONS}). Rules need more invocations."
                )
            return 0

        # 2. For each rule, find candidate target agents
        target_proposal_count = {}  # target_agent -> count this cycle

        for rule in rules:
            source = rule.get("source_agent")
            rule_id = rule.get("rule_id")
            if not source or not rule_id:
                continue

            related_agents = DOMAIN_OVERLAP.get(source, [])
            rule_text = f"WHEN {rule.get('condition', '?')} THEN {rule.get('action', '?')}"

            for target in related_agents:
                # Check cycle cap
                if target_proposal_count.get(target, 0) >= MAX_PROPOSALS_PER_CYCLE:
                    continue

                # Check cooldown
                if _is_on_cooldown(cooldown, source, rule_id, target):
                    continue

                # Check if proposal already exists in Neo4j (pending)
                with driver.session() as session:
                    exists = session.run(
                        """
                        MATCH (p:RuleProposal)
                        WHERE p.source_agent = $src AND p.rule_id = $rid
                          AND p.target_agent = $tgt AND p.status = 'pending'
                        RETURN count(p) AS cnt
                        """,
                        src=source, rid=rule_id, tgt=target,
                    ).single()
                    if exists and exists["cnt"] > 0:
                        continue

                print(
                    f"{'[DRY-RUN] ' if dry_run else ''}Propose rule {rule_id} "
                    f"from {source} -> {target}: {rule_text[:60]}"
                )

                if not dry_run:
                    with driver.session() as session:
                        session.run(
                            """
                            CREATE (p:RuleProposal {
                                source_agent: $src,
                                target_agent: $tgt,
                                rule_id: $rid,
                                rule_text: $rule_text,
                                invocations: $inv,
                                reason: 'domain_overlap_proven_rule',
                                status: 'pending',
                                created: datetime()
                            })
                            """,
                            src=source,
                            tgt=target,
                            rid=rule_id,
                            rule_text=rule_text,
                            inv=rule.get("invocations", MIN_INVOCATIONS),
                        )
                    _mark_cooldown(cooldown, source, rule_id, target)

                    # Emit pipeline event for observability
                    try:
                        from neo4j_task_tracker import get_tracker
                        get_tracker().emit_pipeline_event(
                            "RULE_PROPAGATION", agent=source,
                            payload={"rule_id": rule_id, "target": target,
                                     "rule_text": rule_text[:100]},
                        )
                    except Exception:
                        pass

                target_proposal_count[target] = target_proposal_count.get(target, 0) + 1
                proposals_created += 1

    finally:
        driver.close()

    if not dry_run:
        _save_cooldown(cooldown)

    print(f"Cross-agent rule propagation complete: {proposals_created} proposals created")
    return proposals_created


def main():
    parser = argparse.ArgumentParser(description="Cross-agent rule propagation")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be proposed without creating nodes")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
