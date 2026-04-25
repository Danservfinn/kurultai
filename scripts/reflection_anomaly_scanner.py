#!/usr/bin/env python3
"""
reflection_anomaly_scanner.py — Post-review anomaly detection and escalation.

Reads /horde-review outputs and the task ledger to detect anomalies that
need cross-agent escalation. Creates tasks via task_intake when issues are
found, transforming passive analytics into proactive intelligence.

Runs after the review phase in hourly_reflection.sh (Tier 1 step).

Anomaly types detected:
  1. Low review scores (<= 3/10) — agent needs intervention
  2. Unanalyzed task failures — failures with no follow-up investigation
  3. Repeated failures — same agent failing multiple tasks in 1h

Usage:
    python3 reflection_anomaly_scanner.py [--hours 1] [--dry-run]
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import LOGS_DIR, VALID_AGENTS
from kurultai_ledger import read_ledger

# Model detection
def get_model():
    """Get the default model from main agent config."""
    try:
        settings_file = LOGS_DIR.parent / "main" / ".claude" / "settings.json"
        if not settings_file.exists():
            settings_file = Path.home() / ".openclaw" / "agents" / "main" / ".claude" / "settings.json"
        if settings_file.exists():
            with open(settings_file) as f:
                config = json.load(f)
            return config.get("env", {}).get("ANTHROPIC_MODEL", "unknown")
    except Exception:
        pass
    return "unknown"

MODEL = get_model()

REVIEWS_DIR = LOGS_DIR / "reviews"
ESCALATION_COOLDOWN_FILE = LOGS_DIR / "anomaly-escalation-cooldown.json"
ESCALATION_COOLDOWN_SECONDS = 3600  # Don't re-escalate same agent within 1h
REFLECTION_GAP_THRESHOLD_S = 28 * 3600  # 28 hours — flag if no daily reflection (4h past 6AM run)


def parse_review_file(agent):
    """Parse a review file and extract score + priority_fix.

    Returns dict with keys: score, priority_fix, weaknesses, raw (or None).
    """
    review_path = REVIEWS_DIR / f"{agent}-latest.md"
    if not review_path.exists():
        return None

    # Stale check: skip reviews older than 2h
    try:
        age = time.time() - review_path.stat().st_mtime
        if age > 7200:
            return None
    except Exception:
        return None

    try:
        content = review_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    result = {"agent": agent, "score": None, "priority_fix": None, "weaknesses": []}

    # Extract SCORE: N/10 pattern (handles "SCORE: 3/10", "**3/10**", "SCORE\n**3/10**")
    score_match = re.search(r"SCORE[:\s]*\*{0,2}(\d+)/10", content, re.IGNORECASE)
    if score_match:
        result["score"] = int(score_match.group(1))

    # Extract PRIORITY_FIX section (everything until next ** header or ---)
    fix_match = re.search(
        r"\*\*PRIORITY_FIX:\*\*\s*(.*?)(?=\n\*\*|\n---|\Z)",
        content, re.DOTALL | re.IGNORECASE,
    )
    if not fix_match:
        fix_match = re.search(
            r"PRIORITY_FIX:\s*(.*?)(?=\n\*\*|\n---|\nSCORE|\Z)",
            content, re.DOTALL | re.IGNORECASE,
        )
    if fix_match:
        result["priority_fix"] = fix_match.group(1).strip()[:300]

    # Extract WEAKNESSES bullets
    weak_match = re.search(
        r"WEAKNESSES:\s*(.*?)(?=\n\*\*|\nPATTERNS|\Z)",
        content, re.DOTALL | re.IGNORECASE,
    )
    if weak_match:
        for line in weak_match.group(1).strip().split("\n"):
            line = line.strip()
            if line.startswith(("-", "*", "•")):
                result["weaknesses"].append(line.lstrip("-*• ").strip()[:150])

    return result


def get_recent_failures(hours=1):
    """Get task failures from ledger grouped by agent.

    Returns dict: agent -> [{"task_id": ..., "error": ..., "ts": ...}]
    """
    events = read_ledger(hours=hours)
    failures = {}
    for e in events:
        if e.get("event") == "FAILED":
            agent = e.get("agent")
            if agent:
                failures.setdefault(agent, []).append({
                    "task_id": e.get("task_id", "?"),
                    "error": (e.get("error") or "unknown")[:100],
                    "ts": e.get("ts", ""),
                    "summary": e.get("task_summary", "")[:80],
                })
    return failures


def load_cooldowns():
    """Load escalation cooldown state."""
    if not ESCALATION_COOLDOWN_FILE.exists():
        return {}
    try:
        with open(ESCALATION_COOLDOWN_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_cooldowns(cooldowns):
    """Save escalation cooldown state."""
    try:
        ESCALATION_COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ESCALATION_COOLDOWN_FILE, "w") as f:
            json.dump(cooldowns, f, indent=2)
    except Exception as exc:
        print(f"[anomaly-scanner] WARNING: could not save cooldowns: {exc}", file=sys.stderr)


def is_on_cooldown(cooldowns, key):
    """Check if an escalation key is on cooldown."""
    last_ts = cooldowns.get(key)
    if not last_ts:
        return False
    try:
        elapsed = time.time() - last_ts
        return elapsed < ESCALATION_COOLDOWN_SECONDS
    except (TypeError, ValueError):
        return False


def get_last_reflection_age(agent):
    """Find the age (in seconds) of the most recent reflection for an agent.

    Checks Neo4j for completed reflection tasks (new system).
    Falls back to log files for backwards compatibility (old system).
    Returns age in seconds, or None if no reflection found.
    """
    try:
        # NEW SYSTEM: Check Neo4j for completed reflection tasks
        from neo4j_v2_core import TaskStore
        store = TaskStore()
        try:
            with store.driver.session() as s:
                # Use ENDS WITH with concatenated string parameter
                suffix = f"-reflect-{agent}"
                result = s.run("""
                    MATCH (t:Task)
                    WHERE t.task_id ENDS WITH $suffix
                      AND t.status = 'COMPLETED'
                      AND t.completed_at IS NOT NULL
                    RETURN t.completed_at AS completed
                    ORDER BY t.completed_at DESC
                    LIMIT 1
                """, suffix=suffix)
                record = result.single()
                if record and record["completed"]:
                    # Convert neo4j.time.DateTime to timestamp
                    completed_ts = record["completed"].to_native().timestamp()
                    return time.time() - completed_ts
        finally:
            store.close()
    except Exception:
        # If Neo4j check fails, fall back to old log file check
        pass

    try:
        # OLD SYSTEM: Check for log files (backwards compatibility)
        md_pattern = f"kurultai-reflect-*-{agent}.md"
        log_pattern = f"kurultai-reflect-{agent}.log"

        files = []
        files.extend(REFLECTION_LOGS_DIR.glob(md_pattern))
        files.extend(REFLECTION_LOGS_DIR.glob(log_pattern))

        if not files:
            return None
        return time.time() - max(f.stat().st_mtime for f in files)
    except Exception:
        return None


def scan_anomalies(hours=1):
    """Scan review files and ledger for anomalies.

    Returns list of anomaly dicts with keys:
      type, agent, severity, title, body, route_to
    """
    anomalies = []
    failures = get_recent_failures(hours=hours)

    # Anomaly 0: Proposal extractor stall detection
    extractor_state = LOGS_DIR / "extractor-state.json"
    if extractor_state.exists():
        try:
            state = json.loads(extractor_state.read_text())
            last_run = datetime.fromisoformat(state.get("last_run", "2000-01-01T00:00:00"))
            # Handle timezone-aware datetimes
            if last_run.tzinfo is not None:
                now = datetime.now(timezone.utc)
            else:
                now = datetime.now()
            hours_since = (now - last_run).total_seconds() / 3600
            if hours_since > 8:  # 2 reflection cycles without extraction
                anomalies.append({
                    "type": "extraction_stall",
                    "agent": "ogedei",
                    "severity": "high",
                    "title": f"Proposal extractor stalled ({hours_since:.0f}h since last run)",
                    "body": (
                        f"## Anomaly: Proposal Extractor Stall\n\n"
                        f"The proposal extractor has not run in {hours_since:.0f} hours "
                        f"(expected: every 4 hours during reflection cycle).\n\n"
                        f"**Last run:** {state.get('last_run', 'unknown')}\n"
                        f"**State file:** {extractor_state}\n\n"
                        f"**Action required:** Check if Step 2.5 in hourly_reflection.sh "
                        f"is executing. Verify the safety-net cron job is running.\n\n"
                        f"Source: reflection_anomaly_scanner.py (extraction health check)\n"
                        f"Model: {MODEL}"
                    ),
                    "route_to": "ogedei",
                })
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[anomaly-scanner] Warning: could not read extractor state: {e}", file=sys.stderr)

    for agent in VALID_AGENTS:
        review = parse_review_file(agent)

        # Anomaly 1: Low review score
        if review and review["score"] is not None and review["score"] <= 3:
            priority_fix = review.get("priority_fix") or "No specific fix identified"
            weaknesses = "; ".join(review["weaknesses"][:2]) if review["weaknesses"] else "See review"

            anomalies.append({
                "type": "low_review_score",
                "agent": agent,
                "severity": "high" if review["score"] <= 2 else "normal",
                "title": f"Investigate {agent} low performance (score {review['score']}/10)",
                "body": (
                    f"## Anomaly: Low Review Score\n\n"
                    f"**Agent:** {agent}\n"
                    f"**Score:** {review['score']}/10\n"
                    f"**Weaknesses:** {weaknesses}\n\n"
                    f"**Priority Fix (from review):**\n{priority_fix}\n\n"
                    f"**Action required:** Investigate root cause and implement the priority fix. "
                    f"Check if this is a recurring pattern or a one-off issue.\n\n"
                    f"Source: reflection_anomaly_scanner.py (automated escalation)\n"
                    f"Model: {MODEL}"
                ),
                "route_to": _escalation_target(agent),
            })

        # Anomaly 2: Unanalyzed failures
        agent_failures = failures.get(agent, [])
        if agent_failures:
            fail_count = len(agent_failures)
            fail_summaries = "\n".join(
                f"- task={f['task_id'][:8]}: {f['error']}" for f in agent_failures[:3]
            )

            # Only escalate if 2+ failures or if review also flagged issues
            if fail_count >= 2 or (review and review["score"] is not None and review["score"] <= 4):
                anomalies.append({
                    "type": "unanalyzed_failures",
                    "agent": agent,
                    "severity": "high" if fail_count >= 3 else "normal",
                    "title": f"Investigate {agent} task failures ({fail_count} in last {hours}h)",
                    "body": (
                        f"## Anomaly: Unanalyzed Task Failures\n\n"
                        f"**Agent:** {agent}\n"
                        f"**Failure count:** {fail_count} in last {hours}h\n\n"
                        f"**Failed tasks:**\n{fail_summaries}\n\n"
                        f"**Action required:** Determine if failures share a common root cause "
                        f"(timeout, resource, config). Recommend fix or routing adjustment.\n\n"
                        f"Source: reflection_anomaly_scanner.py (automated escalation)\n"
                        f"Model: {MODEL}"
                    ),
                    "route_to": _escalation_target(agent),
                })

        # Anomaly 3: Reflection gap — agent hasn't reflected in 4+ hours
        # Skip tolui (gateway agent, doesn't participate in reflections)
        if agent == "tolui":
            continue
        reflection_age = get_last_reflection_age(agent)
        if reflection_age is None or reflection_age > REFLECTION_GAP_THRESHOLD_S:
            gap_hours = round(reflection_age / 3600, 1) if reflection_age else "unknown"
            anomalies.append({
                "type": "reflection_gap",
                "agent": agent,
                "severity": "high" if (reflection_age and reflection_age > 8 * 3600) else "normal",
                "title": f"Reflection gap: {agent} last reflected {gap_hours}h ago",
                "body": (
                    f"## Anomaly: Reflection Pipeline Gap\n\n"
                    f"**Agent:** {agent}\n"
                    f"**Last reflection:** {gap_hours}h ago\n"
                    f"**Threshold:** {REFLECTION_GAP_THRESHOLD_S // 3600}h\n\n"
                    f"The daily reflection pipeline has not produced output for this agent. "
                    f"Possible causes: launchd job not firing, pipeline not creating tasks, "
                    f"agent not claiming task, or task execution failure.\n\n"
                    f"**Action required:** Check launchd status (com.kurultai.daily-reflection-pipeline), "
                    f"verify pipeline tasks are created in Neo4j, and check agent completion status.\n\n"
                    f"Source: reflection_anomaly_scanner.py (automated escalation)\n"
                    f"Model: {MODEL}"
                ),
                "route_to": "ogedei" if agent != "ogedei" else "jochi",
            })

    return anomalies


def _escalation_target(failing_agent):
    """Determine who should investigate an anomaly for a given agent.

    Routes to jochi (analyst) for most agents, to temujin for code issues,
    to kublai for routing/coordination issues.
    """
    if failing_agent == "jochi":
        return "temujin"  # Can't investigate yourself
    if failing_agent == "kublai":
        return "jochi"    # Analyst reviews the router
    return "jochi"        # Default: analyst investigates


MAX_ESCALATIONS_PER_RUN = 3  # Flood gate: cap individual escalations


def _apply_flood_gate(anomalies):
    """If 4+ agents have low scores, collapse into one kublai coordination task.

    This prevents a system-wide bad cycle from spamming the queue with
    individual investigation tasks.
    """
    low_score_agents = set()
    other_anomalies = []
    for a in anomalies:
        if a["type"] == "low_review_score":
            low_score_agents.add(a["agent"])
        else:
            other_anomalies.append(a)

    if len(low_score_agents) >= 4:
        agents_str = ", ".join(sorted(low_score_agents))
        consolidated = {
            "type": "system_wide_low_scores",
            "agent": "system",
            "severity": "high",
            "title": f"System-wide low review scores ({len(low_score_agents)} agents)",
            "body": (
                f"## Anomaly: System-Wide Low Performance\n\n"
                f"**Affected agents:** {agents_str}\n"
                f"**Count:** {len(low_score_agents)}/6 agents scored <= 3/10\n\n"
                f"This is likely a systemic issue (idle period, no incoming tasks, "
                f"reflection baseline shift) rather than individual agent failures.\n\n"
                f"**Action required:** Assess whether the low scores reflect a real "
                f"problem or an expected idle period. Check task intake pipeline "
                f"and external triggers.\n\n"
                f"Source: reflection_anomaly_scanner.py (flood gate consolidation)\n"
                f"Model: {MODEL}"
            ),
            "route_to": "ogedei",
        }
        return [consolidated] + other_anomalies[:MAX_ESCALATIONS_PER_RUN - 1]

    # Normal case: cap individual escalations
    return anomalies[:MAX_ESCALATIONS_PER_RUN]


def create_escalation_tasks(anomalies, dry_run=False):
    """Create tasks for detected anomalies, respecting cooldowns.

    Returns list of created task IDs.
    """
    if not anomalies:
        return []

    cooldowns = load_cooldowns()
    created = []

    for anomaly in anomalies:
        cooldown_key = f"{anomaly['type']}:{anomaly['agent']}"

        if is_on_cooldown(cooldowns, cooldown_key):
            print(f"[anomaly-scanner] SKIP (cooldown): {anomaly['title']}")
            continue

        if dry_run:
            print(f"[anomaly-scanner] DRY-RUN would create: {anomaly['title']} -> {anomaly['route_to']}")
            continue

        try:
            from task_intake import create_task
            task_id = create_task(
                title=anomaly["title"],
                body=anomaly["body"],
                priority=anomaly["severity"],
                source="anomaly-scanner",
                agent=anomaly["route_to"],
                skill_hint="/systematic-debugging",
            )
            if task_id:
                cooldowns[cooldown_key] = time.time()
                created.append(task_id)
                print(f"[anomaly-scanner] CREATED: {task_id} -> {anomaly['route_to']}: {anomaly['title']}")
            else:
                print(f"[anomaly-scanner] SKIP (duplicate/rejected): {anomaly['title']}")
        except Exception as exc:
            print(f"[anomaly-scanner] ERROR creating task: {exc}", file=sys.stderr)

    if not dry_run:
        save_cooldowns(cooldowns)

    return created


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Post-review anomaly scanner and escalation")
    parser.add_argument("--hours", type=int, default=1, help="Lookback hours for ledger")
    parser.add_argument("--dry-run", action="store_true", help="Print anomalies without creating tasks")
    args = parser.parse_args()

    print(f"[anomaly-scanner] Scanning reviews and ledger (last {args.hours}h)...")
    print(f"[anomaly-scanner] Model: {MODEL}")
    anomalies = scan_anomalies(hours=args.hours)

    if not anomalies:
        print("[anomaly-scanner] No anomalies detected.")
        return

    print(f"[anomaly-scanner] Found {len(anomalies)} raw anomalie(s):")
    for a in anomalies:
        print(f"  - [{a['severity']}] {a['type']}: {a['agent']} -> route to {a['route_to']}")

    # Apply flood gate to prevent queue spam
    raw_count = len(anomalies)
    anomalies = _apply_flood_gate(anomalies)
    if len(anomalies) < raw_count:
        print(f"[anomaly-scanner] After flood gate: {len(anomalies)} escalation(s) (was {raw_count})")

    created = create_escalation_tasks(anomalies, dry_run=args.dry_run)
    print(f"[anomaly-scanner] Created {len(created)} escalation task(s).")


if __name__ == "__main__":
    main()
