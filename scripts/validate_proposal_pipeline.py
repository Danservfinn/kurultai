#!/usr/bin/env python3
"""
validate_proposal_pipeline.py — One-shot validation of every path in the
Kurultai proposal pipeline: extraction, tier classification, dedup,
voting thresholds, veto logic, and TTL expiration.

Usage:
    python3 validate_proposal_pipeline.py --all
    python3 validate_proposal_pipeline.py --test test_t2_approval
"""

import argparse
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proposal_manager import ProposalManager
from neo4j_task_tracker import neo4j_session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

_results = []


def report(name: str, ok: bool, detail: str = ""):
    tag = PASS if ok else FAIL
    msg = f"  [{tag}] {name}"
    if detail:
        msg += f"  — {detail}"
    print(msg)
    _results.append((name, ok))


def cleanup_test_proposal(proposal_id: str):
    """Remove all Neo4j nodes created by a test proposal."""
    with neo4j_session() as session:
        session.run(
            "MATCH (p:Proposal {proposal_id: $pid}) DETACH DELETE p",
            pid=proposal_id,
        )
        session.run(
            "MATCH (v:Vote {proposal_id: $pid}) DETACH DELETE v",
            pid=proposal_id,
        )
    # Also clean up any markdown files the manager may have written
    pending_file = (
        Path(__file__).resolve().parent.parent / "proposals" / "pending" / f"{proposal_id}.md"
    )
    if pending_file.exists():
        pending_file.unlink()


def _ensure_agent_nodes(session, agents):
    """Make sure :Agent nodes exist so vote creation doesn't fail."""
    for a in agents:
        session.run("MERGE (:Agent {name: $name})", name=a)


def _cast_votes(pm, proposal_id, agents, decision="yes"):
    """Cast identical votes from a list of agents on a proposal."""
    with pm.driver.session() as session:
        _ensure_agent_nodes(session, agents)
        for agent in agents:
            pm._cast_vote(proposal_id, agent, decision,
                          "test vote", "test-cycle", session)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_extraction():
    """Create a synthetic reflection, run the extractor, verify proposals."""
    print("\n— test_extraction")
    from reflection_proposal_extractor import extract_proposals, Proposal

    content = """\
# Reflection — ogedei — 2026-03-23

## New WHEN/THEN Rules Proposed

### TST001: Test extraction rule

**WHEN:** A test condition is detected

**THEN:** Run the test handler

**Why:** Validates extraction pipeline

## Immediate Actions Required

1. **HIGH**: Check disk space on server-alpha
"""
    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(
            prefix="reflection-ogedei-2026-03-23-",
            suffix=".md",
            mode="w",
            delete=False,
        )
        tmp.write(content)
        tmp.close()

        proposals = extract_proposals(Path(tmp.name))
        rules = [p for p in proposals if p.proposal_type == "RULE"]
        actions = [p for p in proposals if p.proposal_type == "ACTION"]

        report("extraction_found_rule", len(rules) >= 1,
               f"{len(rules)} rule(s)")
        report("extraction_found_action", len(actions) >= 1,
               f"{len(actions)} action(s)")

        if rules:
            r = rules[0]
            report("rule_when_clause", "test condition" in (r.when_clause or "").lower(),
                   f"WHEN={r.when_clause!r}")
            report("rule_then_clause", "test handler" in (r.then_clause or "").lower(),
                   f"THEN={r.then_clause!r}")
    finally:
        if tmp and os.path.exists(tmp.name):
            os.unlink(tmp.name)


def test_tier_classification():
    """Verify T0/T1/T2 classification logic."""
    print("\n— test_tier_classification")
    from reflection_proposal_extractor import classify_tier, Proposal

    # T0: CRITICAL action with infrastructure keyword
    p0 = Proposal("ACTION", "", "Restart neo4j", "**CRITICAL**: Restart neo4j immediately",
                   "ogedei", "test.md", priority="CRITICAL")
    report("tier_t0", classify_tier(p0) == "T0", f"got {classify_tier(p0)}")

    # T1: self-scoped rule (body mentions only the source agent)
    p1 = Proposal("RULE", "R01", "Self rule", "ogedei should check its own logs",
                   "ogedei", "test.md",
                   when_clause="ogedei detects error", then_clause="ogedei restarts")
    report("tier_t1", classify_tier(p1) == "T1", f"got {classify_tier(p1)}")

    # T2: cross-agent rule
    p2 = Proposal("RULE", "R02", "Cross rule",
                   "mongke should coordinate with chagatai on research",
                   "ogedei", "test.md",
                   when_clause="research needed", then_clause="mongke delegates to chagatai")
    report("tier_t2", classify_tier(p2) == "T2", f"got {classify_tier(p2)}")


def test_dedup():
    """Run extraction twice on the same file; second run should produce 0 new."""
    print("\n— test_dedup")
    from reflection_proposal_extractor import (
        extract_proposals, compute_fingerprint, is_duplicate, mark_seen,
    )

    content = """\
# Reflection — jochi — 2026-03-23

## New WHEN/THEN Rules Proposed

### DDP01: Dedup test rule

**WHEN:** Dedup test fires

**THEN:** Mark it as seen
"""
    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(
            prefix="reflection-jochi-2026-03-23-",
            suffix=".md", mode="w", delete=False,
        )
        tmp.write(content)
        tmp.close()

        # First pass
        proposals = extract_proposals(Path(tmp.name))
        state = {"seen": {}}
        new_first = 0
        for p in proposals:
            p.fingerprint = compute_fingerprint(p)
            if not is_duplicate(p.fingerprint, state):
                mark_seen(p.fingerprint, state)
                new_first += 1

        # Second pass (same state)
        proposals2 = extract_proposals(Path(tmp.name))
        new_second = 0
        for p in proposals2:
            p.fingerprint = compute_fingerprint(p)
            if not is_duplicate(p.fingerprint, state):
                new_second += 1

        report("dedup_first_pass", new_first >= 1, f"{new_first} new")
        report("dedup_second_pass", new_second == 0, f"{new_second} new (expected 0)")
    finally:
        if tmp and os.path.exists(tmp.name):
            os.unlink(tmp.name)


def test_t2_approval():
    """T2 proposal needs 4 YES votes to meet threshold."""
    print("\n— test_t2_approval")
    pm = ProposalManager()
    pid = None
    try:
        pid = pm.create_proposal(
            title="[TEST] T2 approval validation",
            description="Pipeline test — safe to delete",
            proposing_agent="temujin",
            tier="T2",
        )

        # Cast 4 YES votes from non-proposer agents
        _cast_votes(pm, pid, ["mongke", "chagatai", "jochi", "ogedei"])

        approved = pm.check_threshold_met()
        found = any(a["proposal_id"] == pid for a in approved)
        report("t2_threshold_met", found, f"proposal {pid}")
    finally:
        if pid:
            cleanup_test_proposal(pid)
        pm.close()


def test_t3_approval():
    """T3 proposal needs 5 YES votes (4 should NOT suffice)."""
    print("\n— test_t3_approval")
    pm = ProposalManager()
    pid = None
    try:
        pid = pm.create_proposal(
            title="[TEST] T3 approval validation",
            description="Pipeline test — safe to delete",
            proposing_agent="temujin",
            tier="T3",
        )

        # 4 votes — should NOT be enough
        _cast_votes(pm, pid, ["mongke", "chagatai", "jochi", "ogedei"])
        approved_4 = pm.check_threshold_met()
        found_4 = any(a["proposal_id"] == pid for a in approved_4)
        report("t3_four_votes_insufficient", not found_4,
               "4 YES should not meet T3 threshold")

        # 5th vote tips it over
        _cast_votes(pm, pid, ["kublai"])
        approved_5 = pm.check_threshold_met()
        found_5 = any(a["proposal_id"] == pid for a in approved_5)
        report("t3_five_votes_met", found_5,
               "5 YES should meet T3 threshold")
    finally:
        if pid:
            cleanup_test_proposal(pid)
        pm.close()


def test_kublai_veto():
    """Kublai NO vote on T2 should veto even with 5 other YES votes."""
    print("\n— test_kublai_veto")
    pm = ProposalManager()
    pid = None
    try:
        pid = pm.create_proposal(
            title="[TEST] Kublai veto validation",
            description="Pipeline test — safe to delete",
            proposing_agent="temujin",
            tier="T2",
        )

        # 5 YES from everyone except kublai
        _cast_votes(pm, pid, ["mongke", "chagatai", "jochi", "ogedei", "temujin"])

        # Kublai casts NO
        with pm.driver.session() as session:
            _ensure_agent_nodes(session, ["kublai"])
            pm._cast_vote(pid, "kublai", "no", "veto test", "test-cycle", session)

        approved = pm.check_threshold_met()
        found = any(a["proposal_id"] == pid for a in approved)
        report("kublai_veto_excludes", not found,
               "proposal should be excluded when kublai votes NO")
    finally:
        if pid:
            cleanup_test_proposal(pid)
        pm.close()


def test_expiration_ttl():
    """T2 proposal should have expires_at ~5 hours from creation (not 24h)."""
    print("\n— test_expiration_ttl")
    pm = ProposalManager()
    pid = None
    try:
        before = datetime.now()
        pid = pm.create_proposal(
            title="[TEST] TTL validation",
            description="Pipeline test — safe to delete",
            proposing_agent="mongke",
            tier="T2",
        )
        after = datetime.now()

        # Query directly to avoid get_proposal() Cypher map-literal issue
        with pm.driver.session() as session:
            rec = session.run(
                "MATCH (p:Proposal {proposal_id: $pid}) RETURN p.expires_at AS ea",
                pid=pid,
            ).single()
        if not rec:
            report("ttl_proposal_exists", False, "could not retrieve proposal")
            return

        expires_raw = rec["ea"]
        if hasattr(expires_raw, "to_native"):
            expires_dt = expires_raw.to_native().replace(tzinfo=None)
        else:
            expires_dt = datetime.fromisoformat(str(expires_raw))

        expected_low = before + timedelta(hours=4, minutes=55)
        expected_high = after + timedelta(hours=5, minutes=5)

        in_range = expected_low <= expires_dt <= expected_high
        delta_h = (expires_dt - before).total_seconds() / 3600
        report("ttl_is_5h", in_range,
               f"expires_at delta={delta_h:.2f}h (expected ~5h)")
    finally:
        if pid:
            cleanup_test_proposal(pid)
        pm.close()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ALL_TESTS = {
    "test_extraction": test_extraction,
    "test_tier_classification": test_tier_classification,
    "test_dedup": test_dedup,
    "test_t2_approval": test_t2_approval,
    "test_t3_approval": test_t3_approval,
    "test_kublai_veto": test_kublai_veto,
    "test_expiration_ttl": test_expiration_ttl,
}


def main():
    parser = argparse.ArgumentParser(
        description="Validate the Kurultai proposal pipeline end-to-end.",
    )
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--test", type=str, help="Run a single test by name")
    args = parser.parse_args()

    if not args.all and not args.test:
        parser.print_help()
        sys.exit(1)

    tests_to_run = ALL_TESTS if args.all else {args.test: ALL_TESTS[args.test]}

    print(f"=== Proposal Pipeline Validation ({len(tests_to_run)} test(s)) ===")
    start = time.time()

    for name, fn in tests_to_run.items():
        try:
            fn()
        except Exception as exc:
            report(name, False, f"EXCEPTION: {exc}")

    elapsed = time.time() - start
    passed = sum(1 for _, ok in _results if ok)
    failed = sum(1 for _, ok in _results if not ok)

    print(f"\n{'='*50}")
    print(f"  {passed} passed, {failed} failed  ({elapsed:.1f}s)")
    if failed:
        print("  Failed:")
        for name, ok in _results:
            if not ok:
                print(f"    - {name}")
    print(f"{'='*50}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
