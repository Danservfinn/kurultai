#!/usr/bin/env python3
"""
hermes-knowledge-sync.py - Check knowledge docs against source code freshness.

Scans knowledge markdown files for validated_at frontmatter dates and compares
against the mtime of referenced source files. Flags docs where the source is
newer than the last validation.

Usage:
    python3 hermes-knowledge-sync.py
    python3 hermes-knowledge-sync.py --stale-days 14
    python3 hermes-knowledge-sync.py --update
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kurultai_logging import setup_logging, get_logger

KNOWLEDGE_DIR = Path.home() / ".openclaw" / "agents" / "main" / "knowledge"
KURULTAI_ROOT = Path.home() / ".openclaw"

logger = get_logger("hermes-knowledge-sync", agent="hermes")


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse YAML-like frontmatter from markdown text. Returns key-value pairs."""
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    frontmatter = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            frontmatter[key.strip()] = value.strip().strip('"').strip("'")
    return frontmatter


def extract_source_refs(text: str) -> list[Path]:
    """Extract file paths referenced in the doc body (backtick-quoted paths)."""
    refs = []
    # Match paths in backticks that look like file references
    for match in re.finditer(r"`([^`\s]+\.[a-z]{1,10})`", text):
        candidate = match.group(1)
        # Expand ~ and check if it resolves to a real file
        expanded = Path(candidate.replace("~", str(Path.home())))
        if expanded.exists():
            refs.append(expanded)
    return refs


def scan_docs(stale_days: int, update: bool = False) -> list[dict]:
    """Scan knowledge docs for staleness."""
    stale = []
    stale_threshold = datetime.now(timezone.utc) - timedelta(days=stale_days)

    if not KNOWLEDGE_DIR.exists():
        logger.warning("Knowledge directory not found: %s", KNOWLEDGE_DIR)
        return stale

    for doc_path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = doc_path.read_text()
        frontmatter = parse_frontmatter(text)

        # Get validation date -- look for validated_at or last_validated
        validated_str = frontmatter.get("validated_at") or frontmatter.get("last_validated") or ""

        # Extract source references from the doc body
        source_refs = extract_source_refs(text)
        if not source_refs:
            continue

        # Find the newest source file mtime
        newest_source_mtime = datetime.min.replace(tzinfo=timezone.utc)
        newest_source = None
        for ref in source_refs:
            try:
                mtime = datetime.fromtimestamp(ref.stat().st_mtime, tz=timezone.utc)
                if mtime > newest_source_mtime:
                    newest_source_mtime = mtime
                    newest_source = str(ref)
            except OSError:
                continue

        # Compare validation date vs source mtime
        is_stale = False
        if validated_str:
            try:
                validated_at = datetime.fromisoformat(validated_str)
                if validated_at.tzinfo is None:
                    validated_at = validated_at.replace(tzinfo=timezone.utc)
                if newest_source_mtime > validated_at:
                    is_stale = True
            except ValueError:
                is_stale = True  # Can't parse date = effectively stale
        else:
            # No validation date at all
            if newest_source_mtime < stale_threshold:
                is_stale = True

        if is_stale:
            entry = {
                "doc": doc_path.name,
                "validated_at": validated_str or "(none)",
                "newest_source": newest_source,
                "source_mtime": newest_source_mtime.isoformat(),
            }
            stale.append(entry)

            if update and newest_source:
                # Update validated_at in the frontmatter
                new_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if "validated_at" in frontmatter:
                    text = re.sub(
                        r"validated_at:\s*\S+",
                        f"validated_at: {new_date}",
                        text,
                    )
                elif "last_validated" in frontmatter:
                    text = re.sub(
                        r"last_validated:\s*\S+",
                        f"last_validated: {new_date}",
                        text,
                    )
                else:
                    # Add frontmatter with validated_at
                    text = f"---\nvalidated_at: {new_date}\n---\n" + text.lstrip("-").lstrip("\n")
                doc_path.write_text(text)
                logger.info("Updated validated_at in %s", doc_path.name)

    return stale


def main():
    parser = argparse.ArgumentParser(description="Check knowledge docs against source freshness")
    parser.add_argument("--stale-days", type=int, default=30,
                        help="Days without validation before flagging (default: 30)")
    parser.add_argument("--update", action="store_true",
                        help="Update validated_at dates for matched docs")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON result")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    setup_logging(level=args.log_level, agent_name="hermes-knowledge-sync")

    stale = scan_docs(args.stale_days, args.update)

    result = {
        "scan_at": datetime.now(timezone.utc).isoformat(),
        "stale_days_threshold": args.stale_days,
        "stale_count": len(stale),
        "updated": args.update,
        "stale_docs": stale,
    }

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if stale:
            print(f"Found {len(stale)} stale docs (threshold: {args.stale_days}d):")
            for doc in stale:
                print(f"  {doc['doc']} — validated: {doc['validated_at']}, "
                      f"source: {doc['newest_source']} ({doc['source_mtime'][:10]})")
        else:
            print("All knowledge docs are up to date.")
        if args.update:
            print("validated_at dates updated where applicable.")

    logger.info("Scan complete: %d stale docs found", len(stale))
    return 0


if __name__ == "__main__":
    sys.exit(main())
