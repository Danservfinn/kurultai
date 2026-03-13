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
_COOLDOWN_MINUTES = 30  # Don't self-task more than once per 30 minutes (reduced from 2h)

# Exclude file to track already-tasked items (prevents failing task loops)
_EXCLUDED_TITLES_FILE = Path(__file__).parent.parent / "logs" / "mongke-self-task-exclusions.json"
_EXCLUSION_DAYS = 7  # Keep exclusions for 7 days, then allow retry


def _check_cooldown():
    """Return True if cooldown has expired (ok to generate tasks)."""
    if not _COOLDOWN_FILE.exists():
        return True
    try:
        with open(_COOLDOWN_FILE) as f:
            data = json.load(f)
        last_run = datetime.fromisoformat(data.get("last_run", "2000-01-01"))
        return datetime.now() - last_run > timedelta(minutes=_COOLDOWN_MINUTES)
    except (json.JSONDecodeError, ValueError):
        return True


def _update_cooldown():
    """Record that we just generated tasks."""
    _COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_COOLDOWN_FILE, "w") as f:
        json.dump({"last_run": datetime.now().isoformat()}, f)


def _load_excluded_titles() -> set:
    """Load set of titles that have already had self-tasks created."""
    if not _EXCLUDED_TITLES_FILE.exists():
        return set()

    try:
        with open(_EXCLUDED_TITLES_FILE) as f:
            data = json.load(f)

        # Filter out expired exclusions (older than _EXCLUSION_DAYS)
        cutoff = datetime.now() - timedelta(days=_EXCLUSION_DAYS)
        valid = {
            title: ts for title, ts in data.items()
            if datetime.fromisoformat(ts) > cutoff
        }

        # If we pruned any, update the file
        if len(valid) != len(data):
            _EXCLUDED_TITLES_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_EXCLUDED_TITLES_FILE, "w") as f:
                json.dump(valid, f)

        return set(valid.keys())
    except (json.JSONDecodeError, ValueError):
        return set()


def _add_excluded_title(title: str):
    """Add a title to the exclusion list after creating a task for it."""
    _EXCLUDED_TITLES_FILE.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(_EXCLUDED_TITLES_FILE) as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        data = {}

    data[title] = datetime.now().isoformat()

    with open(_EXCLUDED_TITLES_FILE, "w") as f:
        json.dump(data, f)


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
    excluded = _load_excluded_titles()
    tasks = []

    driver = get_driver()
    with driver.session() as s:
        # Hypothesis nodes use 'created' (neo4j DateTime), 'action' as title
        result = s.run("""
            MATCH (h:Hypothesis)
            WHERE h.created < datetime($cutoff)
            RETURN h.action as title, toString(h.created) as created
            ORDER BY h.created ASC
            LIMIT 20
        """, cutoff=cutoff_iso)
        for rec in result:
            title = rec["title"] or "Unknown hypothesis"
            # Skip if we've already created a task for this hypothesis
            if title in excluded:
                continue
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
                "exclude_key": title,  # Track for exclusion after task creation
            })
            if len(tasks) >= 5:  # Limit after filtering
                break

        # StrategicInsight nodes use 'created'/'updated' (ISO strings), 'name' as title
        result = s.run("""
            MATCH (si:StrategicInsight)
            WHERE si.updated < $cutoff OR si.created < $cutoff
            RETURN si.name as title, si.updated as updated, si.created as created
            ORDER BY coalesce(si.updated, si.created) ASC
            LIMIT 10
        """, cutoff=cutoff_iso)
        for rec in result:
            title = rec["title"] or "Unknown insight"
            if title in excluded:
                continue
            tasks.append({
                "type": "refresh_insight",
                "title": f"Research refresh: Validate strategic insight '{title[:50]}'",
                "body": (
                    f"The strategic insight '{title}' may be outdated. "
                    f"Research current market/technical landscape to confirm or update.\n\n"
                    f"Use /horde-learn to store validated findings."
                ),
                "exclude_key": title,
            })
            if len(tasks) >= 8:
                break

        # ContentBrief nodes use 'created_at' (neo4j DateTime), 'angle'/'tip_topic' as title
        result = s.run("""
            MATCH (cb:ContentBrief)
            WHERE cb.status IN ['draft_pending', 'pending', 'draft']
               AND cb.created_at < datetime($cutoff)
            RETURN coalesce(cb.angle, cb.tip_topic, cb.id) as title, cb.status as status
            LIMIT 10
        """, cutoff=cutoff_iso)
        for rec in result:
            title = rec["title"] or "Unknown brief"
            if title in excluded:
                continue
            tasks.append({
                "type": "research_for_content",
                "title": f"Research sources for content brief: '{title[:50]}'",
                "body": (
                    f"Content brief '{title}' needs research support. "
                    f"Find 3-5 authoritative sources, statistics, or examples "
                    f"that can strengthen this content.\n\n"
                    f"Use /horde-learn to extract and store source findings."
                ),
                "exclude_key": title,
            })
            if len(tasks) >= 10:
                break

    # Note: Do NOT close driver here - it's a singleton managed by neo4j_task_tracker.py

    return tasks


def _find_research_needed_nodes():
    """Query Neo4j for nodes with research-needed flags or properties.

    Looks for nodes that have properties indicating research is required:
    - needs_research=true
    - research_required=true
    - research_pending=true
    - Any node with 'research_needed' label
    """
    tasks = []

    driver = get_driver()
    with driver.session() as s:
        # Find nodes with explicit research flags
        result = s.run("""
            MATCH (n)
            WHERE n.needs_research = true
               OR n.research_required = true
               OR n.research_pending = true
            RETURN labels(n) as labels, n as node
            LIMIT 5
        """)
        for rec in result:
            node = rec["node"]
            labels = rec["labels"]

            # Extract identifying info
            title = (
                node.get("action") or node.get("name") or
                node.get("title") or node.get("task") or
                node.get("description") or
                f"{labels[0] if labels else 'Node'}-{node.element_id}"
            )

            tasks.append({
                "type": "research_flagged",
                "title": f"Research needed: {str(title)[:60]}",
                "body": (
                    f"A {labels[0] if labels else 'node'} has been flagged as requiring research.\n\n"
                    f"Node details: {dict(node)}\n\n"
                    f"Conduct the required research and update the node with findings. "
                    f"Clear the research flag when complete.\n\n"
                    f"Use /horde-learn to extract and store findings."
                ),
            })

        # Find nodes with ResearchNeeded label
        result = s.run("""
            MATCH (n:ResearchNeeded)
            RETURN n as node
            LIMIT 3
        """)
        for rec in result:
            node = rec["node"]
            title = (
                node.get("action") or node.get("name") or
                node.get("title") or node.get("task") or
                node.get("description") or "Research task"
            )

            tasks.append({
                "type": "research_needed_label",
                "title": f"Research (labeled): {str(title)[:60]}",
                "body": (
                    f"A node was explicitly labeled :ResearchNeeded.\n\n"
                    f"Node details: {dict(node)}\n\n"
                    f"Conduct the required research and remove the :ResearchNeeded label when complete.\n\n"
                    f"Use /horde-learn to extract and store findings."
                ),
            })

    # Note: Do NOT close driver here - it's a singleton managed by neo4j_task_tracker.py

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


def _find_implicit_research_opportunities():
    """Detect implicit research opportunities from system activity.

    Scans for research needs that aren't explicitly flagged:
    1. Routing decisions with research keywords that went to other agents
    2. Recent proposals needing competitive/market research
    3. Tech decisions requiring alternatives analysis

    Returns a list of task dicts for potential research tasks.
    """
    tasks = []

    # 1. Scan routing decisions for missed research opportunities
    routing_log = Path(__file__).parent.parent / "logs" / "routing-decisions.jsonl"
    if routing_log.exists():
        research_keywords = [
            "competitor", "market", "landscape", "benchmark", "compare",
            "alternatives", "vs", "versus", "evaluation", "analysis"
        ]

        # Get last 100 routing decisions
        missed_tasks = set()
        try:
            lines = []
            with open(routing_log) as f:
                for line in f:
                    lines.append(line.strip())
                    if len(lines) > 100:
                        lines.pop(0)

            for line in lines:
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    task_title = entry.get("task", "").lower()
                    dest = entry.get("dest", "")

                    # If research keywords present but NOT routed to mongke
                    if (any(kw in task_title for kw in research_keywords) and
                        dest != "mongke" and
                        entry.get("method") != "explicit"):
                        missed_tasks.add(entry.get("task", "unknown")[:80])
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

        # Generate aggregate research task if multiple misses found
        if len(missed_tasks) >= 3:
            topics = list(missed_tasks)[:3]
            tasks.append({
                "type": "implicit_research_aggregate",
                "title": f"Research: Competitive landscape for recent system topics ({len(missed_tasks)} signals)",
                "body": (
                    f"Detected {len(missed_tasks)} recent tasks with research keywords "
                    f"that were routed elsewhere. Example topics:\n"
                    + "\n".join(f"  - {t}" for t in topics)
                    + f"\n\nResearch the competitive landscape and best practices "
                    f"for these topics. Store findings in Neo4j for future routing decisions.\n\n"
                    f"Use /horde-learn to extract and store competitive insights."
                ),
            })

    # 2. Scan proposals for new features needing market research
    proposals_dir = Path(__file__).parent.parent / "proposals"
    if proposals_dir.exists():
        recent_proposals = []
        cutoff = datetime.now() - timedelta(hours=24)

        for f in proposals_dir.iterdir():
            if not f.suffix == ".md":
                continue
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime > cutoff:
                    # Extract title from filename
                    title = f.stem.replace("-", " ").title()
                    recent_proposals.append((title, mtime))
            except Exception:
                pass

        if len(recent_proposals) >= 2:
            tasks.append({
                "type": "proposal_market_research",
                "title": f"Research: Market analysis for {len(recent_proposals)} recent proposals",
                "body": (
                    f"{len(recent_proposals)} new feature proposals were created in the last 24h.\n"
                    "Research the competitive landscape:\n"
                    "  - Are similar features offered by competitors?\n"
                    "  - What are industry best practices for these features?\n"
                    "  - Any open-source implementations to reference?\n\n"
                    f"Recent proposals: {', '.join(p[0][:30] for p in recent_proposals[:3])}\n\n"
                    "Use /horde-learn to store competitive analysis."
                ),
            })

    return tasks


def generate_self_tasks(dry_run=True):
    """Main entry point. Find stale knowledge and generate research tasks."""
    if not _mongke_queue_empty():
        print("mongke queue not empty — skipping self-task generation")
        return []

    if not _check_cooldown():
        print(f"cooldown active (last run < {_COOLDOWN_MINUTES}m ago) — skipping")
        return []

    # Collect candidate tasks from all sources
    candidates = []

    # Priority 1: Explicitly flagged research-needed nodes
    try:
        flagged = _find_research_needed_nodes()
        if flagged:
            print(f"Found {len(flagged)} research-needed node(s)")
            candidates.extend(flagged)
    except Exception as e:
        print(f"Warning: Research-needed query failed: {e}")

    # Priority 2: Implicit research opportunities (proactive - creates demand)
    implicit = _find_implicit_research_opportunities()
    if implicit:
        print(f"Found {len(implicit)} implicit research opportunity(ies)")
        candidates.extend(implicit)

    # Priority 3: Stale knowledge refresh
    try:
        candidates.extend(_find_stale_knowledge())
    except Exception as e:
        print(f"Warning: Neo4j stale knowledge query failed: {e}")

    # Priority 4: Shared context gaps
    candidates.extend(_find_shared_context_research())

    # Priority 5: Capability improvements
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
            # Add to exclusion list to prevent recreation of same failing task
            exclude_key = t.get("exclude_key", t["title"][:80])
            _add_excluded_title(exclude_key)
        else:
            print(f"Rejected (duplicate?): {t['title']}")

    if created:
        _update_cooldown()
        print(f"\nGenerated {len(created)} self-task(s) for mongke")

    return created


if __name__ == "__main__":
    dry_run = "--exec" not in sys.argv
    generate_self_tasks(dry_run=dry_run)
