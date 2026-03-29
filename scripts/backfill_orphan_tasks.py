#!/usr/bin/env python3
"""
backfill_orphan_tasks.py — Register gateway-created task files into Neo4j.

The openclaw npm gateway writes task .md files directly to agent task dirs
using YAML frontmatter format, but without calling task_intake.py. These
files have no task_id and no Neo4j record, making them invisible to the
dispatcher.

This script:
  1. Scans all agent task dirs for .md files with YAML frontmatter but no task_id
  2. Registers each in Neo4j (creates a Task node with status=PENDING)
  3. Patches the frontmatter in-place (adds task_id field + body marker)

Usage:
    python3 backfill_orphan_tasks.py              # register all orphans
    python3 backfill_orphan_tasks.py --dry-run    # report only, no writes
    python3 backfill_orphan_tasks.py --json       # output stats as JSON
"""

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow imports from scripts dir
sys.path.insert(0, str(Path(__file__).parent))

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from kurultai_paths import AGENTS_DIR, VALID_AGENTS, agent_tasks_dir
from kurultai_ledger import generate_task_id
from neo4j_task_tracker import neo4j_session, is_neo4j_available

logger = logging.getLogger(__name__)

# Match YAML frontmatter block: --- ... ---
YAML_FRONT_RE = re.compile(r'^---\s*\n(.*?)\n---', re.DOTALL)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def find_orphan_files() -> list[Path]:
    """Return .md task files with YAML frontmatter but no task_id field."""
    orphans = []
    for agent in VALID_AGENTS:
        tasks_dir = agent_tasks_dir(agent)
        if not tasks_dir.exists():
            continue
        for f in sorted(tasks_dir.glob("*.md")):
            # Skip terminal states
            if ".done." in f.name or ".failed." in f.name or ".pending-gate." in f.name:
                continue
            try:
                content = f.read_text(errors="replace")
            except OSError:
                continue
            m = YAML_FRONT_RE.match(content)
            if m and "task_id:" not in m.group(1):
                orphans.append(f)
    return orphans


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from file content. Returns {} on failure."""
    m = YAML_FRONT_RE.match(content)
    if not m:
        return {}
    if YAML_AVAILABLE:
        try:
            return yaml.safe_load(m.group(1)) or {}
        except Exception:
            pass
    # Minimal fallback parser for key: value lines
    result = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


# ---------------------------------------------------------------------------
# Deduplication check
# ---------------------------------------------------------------------------

def is_already_registered(title: str, agent: str) -> bool:
    """Return True if a non-terminal Task with matching title+agent exists in Neo4j."""
    if not is_neo4j_available():
        return False
    try:
        with neo4j_session() as session:
            result = session.run(
                """
                MATCH (t:Task {agent: $agent})
                WHERE t.title CONTAINS $title
                  AND NOT t.status IN ['DONE', 'FAILED', 'CANCELLED']
                RETURN count(t) AS n
                """,
                agent=agent,
                title=title[:80],
            )
            record = result.single()
            return bool(record and record["n"] > 0)
    except Exception as e:
        logger.warning(f"Neo4j dedup check failed: {e}")
        return False


# ---------------------------------------------------------------------------
# In-place file patching
# ---------------------------------------------------------------------------

def _patch_frontmatter(file_path: Path, task_id: str) -> None:
    """Insert task_id into the YAML frontmatter block and add body marker."""
    content = file_path.read_text()
    m = YAML_FRONT_RE.match(content)
    if not m:
        return
    old_fm_body = m.group(1)
    new_fm_body = old_fm_body.rstrip() + f"\ntask_id: {task_id}"
    # Replace the frontmatter block (first occurrence only)
    new_content = content.replace(
        f"---\n{old_fm_body}\n---",
        f"---\n{new_fm_body}\n---",
        1,
    )
    # Append canonical body marker for agent-task-handler.py compatibility
    if f"*Task ID: {task_id}*" not in new_content:
        new_content = new_content.rstrip() + f"\n\n*Task ID: {task_id}*\n"
    file_path.write_text(new_content)


# ---------------------------------------------------------------------------
# Neo4j registration
# ---------------------------------------------------------------------------

def register_orphan(file_path: Path, fm: dict) -> str | None:
    """Create Neo4j Task node and patch file frontmatter. Returns task_id or None."""
    title = fm.get("title", file_path.stem)
    priority = fm.get("priority", "normal")
    agent = fm.get("agent", "kublai")
    source = fm.get("source", "gateway-router")
    skill = fm.get("skill_hint") or fm.get("skill")
    now = datetime.now(timezone.utc)

    task_id = generate_task_id(priority)

    if not is_neo4j_available():
        # Patch file only — Neo4j sync happens next heartbeat when available
        logger.warning(f"Neo4j unavailable; patching file only for {file_path.name}")
        _patch_frontmatter(file_path, task_id)
        return task_id

    try:
        with neo4j_session() as session:
            session.run(
                """
                MERGE (t:Task {task_id: $task_id})
                ON CREATE SET
                  t.label      = $label,
                  t.title      = $title,
                  t.agent      = $agent,
                  t.priority   = $priority,
                  t.source     = $source,
                  t.status     = 'PENDING',
                  t.skill_hint = $skill,
                  t.createdAt  = datetime($now),
                  t.file_path  = $fp,
                  t.backfilled = true
                """,
                task_id=task_id,
                label=f"{agent}-{task_id}",
                title=title,
                agent=agent,
                priority=priority,
                source=source,
                skill=skill,
                now=now.isoformat(),
                fp=str(file_path),
            )
    except Exception as e:
        logger.error(f"Neo4j write failed for {file_path.name}: {e}")
        return None

    _patch_frontmatter(file_path, task_id)
    return task_id


# ---------------------------------------------------------------------------
# Main backfill loop
# ---------------------------------------------------------------------------

def run_backfill(dry_run: bool = False) -> dict:
    """Scan all agent task dirs and register orphan files. Returns stats dict."""
    orphans = find_orphan_files()
    stats: dict = {
        "found": len(orphans),
        "registered": 0,
        "skipped": 0,
        "errors": 0,
        "files": [],
    }

    for f in orphans:
        try:
            content = f.read_text(errors="replace")
            fm = parse_frontmatter(content)
            if not fm.get("title"):
                logger.warning(f"Skipping {f.name}: no title in frontmatter")
                stats["skipped"] += 1
                continue

            title = fm["title"]
            agent = fm.get("agent", "")

            if is_already_registered(title, agent):
                logger.info(f"Skipping {f.name}: already registered in Neo4j")
                stats["skipped"] += 1
                continue

            if dry_run:
                stats["files"].append(str(f))
                logger.info(f"[dry-run] Would register: {f.name}")
                continue

            task_id = register_orphan(f, fm)
            if task_id:
                stats["registered"] += 1
                stats["files"].append(f"{f.name} → {task_id}")
                logger.info(f"Backfilled {f.name} as {task_id}")
            else:
                stats["errors"] += 1
                logger.error(f"Failed to register {f.name}")

        except Exception as e:
            stats["errors"] += 1
            logger.error(f"Unexpected error processing {f}: {e}")

    return stats


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Register gateway-created task files into Neo4j"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report orphan files without registering them",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output stats as JSON to stdout",
    )
    args = parser.parse_args()

    stats = run_backfill(dry_run=args.dry_run)

    if args.output_json:
        print(json.dumps(stats))
    else:
        prefix = "[dry-run] " if args.dry_run else ""
        print(
            f"{prefix}Orphan task backfill: "
            f"found={stats['found']}, "
            f"registered={stats['registered']}, "
            f"skipped={stats['skipped']}, "
            f"errors={stats['errors']}"
        )
        for line in stats["files"]:
            print(f"  {line}")
