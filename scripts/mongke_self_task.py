#!/usr/bin/env python3
"""
mongke_self_task.py — Self-tasking for mongke when queue is empty.

Queries Neo4j for stale knowledge nodes (>7 days without update),
checks for knowledge gaps, and generates research refresh tasks.

Called from reflections or cron when mongke has 0 pending tasks.

Usage:
    python3 mongke_self_task.py          # dry-run (print what would be created)
    python3 mongke_self_task.py --exec   # actually create tasks
"""

import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kurultai_paths import AGENTS_DIR
from neo4j_task_tracker import get_driver


# Max tasks to self-generate per invocation (prevent flooding)
MAX_SELF_TASKS = 2

# Staleness threshold in days
STALE_DAYS = 7

# Cooldown file to prevent over-generation
_COOLDOWN_FILE = Path(__file__).parent.parent / "logs" / "mongke-self-task-cooldown.json"
_COOLDOWN_HOURS = 2  # Don't self-task more than once per 2 hours


def _check_cooldown():
    """Return True if cooldown has expired (ok to generate tasks)."""
    if not _COOLDOWN_FILE.exists():
        return True
    try:
        with open(_COOLDOWN_FILE) as f:
            data = json.load(f)
        last_run = datetime.fromisoformat(data.get("last_run", "2000-01-01"))
        return datetime.now() - last_run > timedelta(hours=_COOLDOWN_HOURS)
    except (json.JSONDecodeError, ValueError):
        return True


def _update_cooldown():
    """Record that we just generated tasks."""
    _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_COOLDOWN_FILE, "w") as f:
        json.dump({"last_run": datetime.now().isoformat()}, f)


def _mongke_queue_empty():
    """Check if mongke has 0 pending tasks."""
    tasks_dir = AGENTS_DIR / "mongke" / "tasks"
    if not tasks_dir.exists():
        return True
    for f in tasks_dir.iterdir():
        name = f.name
        if name.endswith(".md") and not any(
            tag in name for tag in [".done", ".failed", ".completed", ".verified", ".rerouted", ".absorbed"]
        ):
            return False
    return True


def _find_stale_knowledge():
    """Query Neo4j for knowledge nodes not updated in STALE_DAYS days."""
    cutoff_iso = (datetime.now() - timedelta(days=STALE_DAYS)).isoformat()
    tasks = []

    driver = get_driver()
    try:
        with driver.session() as s:
            # Hypothesis nodes use 'created' (neo4j DateTime), 'action' as title
            result = s.run("""
                MATCH (h:Hypothesis)
                WHERE h.created < datetime($cutoff)
                RETURN h.action as title, toString(h.created) as created
                ORDER BY h.created ASC
                LIMIT 5
            """, cutoff=cutoff_iso)
            for rec in result:
                title = rec["title"] or "Unknown hypothesis"
                age = rec["created"] or "unknown"
                tasks.append({
                    "type": "refresh_hypothesis",
                    "title": f"Research refresh: Verify hypothesis '{title[:60]}'",
                    "body": (
                        f"The hypothesis '{title}' was created {age}. "
                        f"Research whether this finding is still valid. "
                        f"Check current sources and update or invalidate the Neo4j node.\n\n"
                        f"Use /horde-learn to extract and store updated findings."
                    ),
                })

            # StrategicInsight nodes use 'created'/'updated' (ISO strings), 'name' as title
            result = s.run("""
                MATCH (si:StrategicInsight)
                WHERE si.updated < $cutoff OR si.created < $cutoff
                RETURN si.name as title, si.updated as updated, si.created as created
                ORDER BY coalesce(si.updated, si.created) ASC
                LIMIT 3
            """, cutoff=cutoff_iso)
            for rec in result:
                title = rec["title"] or "Unknown insight"
                tasks.append({
                    "type": "refresh_insight",
                    "title": f"Research refresh: Validate strategic insight '{title[:50]}'",
                    "body": (
                        f"The strategic insight '{title}' may be outdated. "
                        f"Research current market/technical landscape to confirm or update.\n\n"
                        f"Use /horde-learn to store validated findings."
                    ),
                })

            # ContentBrief nodes use 'created_at' (neo4j DateTime), 'angle'/'tip_topic' as title
            result = s.run("""
                MATCH (cb:ContentBrief)
                WHERE cb.status IN ['draft_pending', 'pending', 'draft']
                   AND cb.created_at < datetime($cutoff)
                RETURN coalesce(cb.angle, cb.tip_topic, cb.id) as title, cb.status as status
                LIMIT 3
            """, cutoff=cutoff_iso)
            for rec in result:
                title = rec["title"] or "Unknown brief"
                tasks.append({
                    "type": "research_for_content",
                    "title": f"Research sources for content brief: '{title[:50]}'",
                    "body": (
                        f"Content brief '{title}' needs research support. "
                        f"Find 3-5 authoritative sources, statistics, or examples "
                        f"that can strengthen this content.\n\n"
                        f"Use /horde-learn to extract and store source findings."
                    ),
                })

    finally:
        driver.close()

    return tasks


def _find_shared_context_research():
    """Scan shared-context/ for stale research files that need refresh."""
    tasks = []
    shared_ctx = Path(__file__).parent.parent / "shared-context"
    if not shared_ctx.exists():
        return tasks

    stale_cutoff = datetime.now() - timedelta(days=2)

    for f in sorted(shared_ctx.iterdir()):
        if not f.suffix == ".md":
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < stale_cutoff:
            age_days = (datetime.now() - mtime).days
            # Extract title from first heading or filename
            title_hint = f.stem.replace("-", " ").replace("_", " ").title()
            try:
                with open(f) as fh:
                    for line in fh:
                        line = line.strip()
                        if line.startswith("#"):
                            title_hint = line.lstrip("# ").strip()[:60]
                            break
            except Exception:
                pass

            tasks.append({
                "type": "refresh_shared_context",
                "title": f"Research refresh: Update '{title_hint}' ({age_days}d stale)",
                "body": (
                    f"The shared-context file `{f.name}` was last updated {age_days} days ago.\n\n"
                    f"Research current developments and update the document with:\n"
                    f"- New findings or market changes since last update\n"
                    f"- Verify existing claims are still accurate\n"
                    f"- Add any new sources discovered\n\n"
                    f"File path: {f}\n\n"
                    f"Use /horde-learn to extract and store updated findings."
                ),
            })

    # Prioritize oldest files first (already sorted by name, re-sort by staleness)
    tasks.sort(key=lambda t: t["title"], reverse=True)  # higher age_days first in title
    return tasks


def _find_capability_gaps():
    """Generate tasks based on low capability scores or missing coverage."""
    tasks = []

    # Check capability scores file
    scores_file = Path(__file__).parent.parent / "logs" / "capability-scores.json"
    if scores_file.exists():
        try:
            with open(scores_file) as f:
                scores = json.load(f)
            mongke_scores = scores.get("mongke", {})
            # Find categories where score < 5
            for category, score in mongke_scores.items():
                if isinstance(score, (int, float)) and score < 5:
                    tasks.append({
                        "type": "capability_improvement",
                        "title": f"Research to improve {category} capability score ({score}/10)",
                        "body": (
                            f"Mongke's {category} capability score is {score}/10. "
                            f"Research best practices and methodologies to improve "
                            f"performance in this area. Document findings for future tasks.\n\n"
                            f"Use /horde-learn to store methodology improvements."
                        ),
                    })
        except (json.JSONDecodeError, KeyError):
            pass

    return tasks


def generate_self_tasks(dry_run=True):
    """Main entry point. Find stale knowledge and generate research tasks."""
    if not _mongke_queue_empty():
        print("mongke queue not empty — skipping self-task generation")
        return []

    if not _check_cooldown():
        print(f"cooldown active (last run < {_COOLDOWN_HOURS}h ago) — skipping")
        return []

    # Collect candidate tasks from all sources
    candidates = []

    try:
        candidates.extend(_find_stale_knowledge())
    except Exception as e:
        print(f"Warning: Neo4j stale knowledge query failed: {e}")

    candidates.extend(_find_shared_context_research())
    candidates.extend(_find_capability_gaps())

    if not candidates:
        print("No stale knowledge or capability gaps found — system knowledge is fresh")
        return []

    # Take top MAX_SELF_TASKS candidates
    selected = candidates[:MAX_SELF_TASKS]

    if dry_run:
        print(f"DRY RUN: Would create {len(selected)} task(s):")
        for t in selected:
            print(f"  [{t['type']}] {t['title']}")
        return selected

    # Actually create tasks
    from task_intake import create_task

    created = []
    for t in selected:
        task_id = create_task(
            title=t["title"],
            body=t["body"],
            priority="normal",
            source="mongke-self-task",
            agent="mongke",
            skill_hint="/horde-learn",
            depth=0,
        )
        if task_id:
            print(f"Created: {task_id} — {t['title']}")
            created.append(task_id)
        else:
            print(f"Rejected (duplicate?): {t['title']}")

    if created:
        _update_cooldown()
        print(f"\nGenerated {len(created)} self-task(s) for mongke")

    return created


if __name__ == "__main__":
    dry_run = "--exec" not in sys.argv
    generate_self_tasks(dry_run=dry_run)
