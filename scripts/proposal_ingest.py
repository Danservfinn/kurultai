#!/usr/bin/env python3
"""
proposal_ingest.py - Ingest filesystem proposals into Neo4j for voting pipeline.

Reads proposal markdown files from ~/.openclaw/agents/main/proposals/ and creates
Proposal nodes in Neo4j, bridging the gap between filesystem-based proposal creation
(during reflection cycles) and the Neo4j voting pipeline.

Usage:
    python3 proposal_ingest.py --dry-run                          # Show what would be ingested
    python3 proposal_ingest.py --ingest                           # Ingest all pending proposals
    python3 proposal_ingest.py --ingest --file proposals/chagatai-20260312-223513.md  # Single file
"""

import os
import sys
import re
import json
import hashlib
import argparse
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import neo4j_session
from kurultai_paths import AGENTS_DIR

PROPOSALS_DIR = AGENTS_DIR / "main" / "proposals"
KURULTAI_AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]


def parse_proposal_file(filepath: Path) -> dict:
    """Parse a proposal markdown file into structured data.

    Handles two formats:
    1. Standard: `# Proposal: <title>` with **Agent:**, **Timestamp:**, **Domain:**
    2. Reflection: `# Skill Improvement Proposal: <title>` with similar metadata
    """
    text = filepath.read_text()
    filename = filepath.name  # e.g. chagatai-20260312-223513.md

    data = {
        "filepath": str(filepath),
        "filename": filename,
        "title": None,
        "agent": None,
        "timestamp": None,
        "domain": None,
        "category": None,
        "model": None,
        "problem": None,
        "solution": None,
        "implemented": None,
        "full_text": text,
    }

    # Parse agent and timestamp from filename
    # Format: agent-YYYYMMDD-HHMMSS.md or agent-reflect-YYYYMMDD-HHMMSS.md
    fname_match = re.match(r'^(\w+?)(?:-reflect)?-(\d{8}-\d{6})\.md$', filename)
    if fname_match:
        data["agent"] = fname_match.group(1)
        ts_str = fname_match.group(2)
        try:
            data["timestamp"] = datetime.strptime(ts_str, "%Y%m%d-%H%M%S").isoformat()
        except ValueError:
            pass

    # Parse title from first heading
    title_match = re.search(r'^#\s+(?:Proposal|Skill Improvement Proposal):\s*(.+)$', text, re.MULTILINE)
    if title_match:
        data["title"] = title_match.group(1).strip()

    # Parse metadata fields
    agent_match = re.search(r'\*\*Agent:\*\*\s*(\w+)', text)
    if agent_match:
        data["agent"] = agent_match.group(1)

    timestamp_match = re.search(r'\*\*Timestamp:\*\*\s*(.+)', text)
    if timestamp_match:
        ts_raw = timestamp_match.group(1).strip()
        # Normalize timestamp
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"]:
            try:
                data["timestamp"] = datetime.strptime(ts_raw, fmt).isoformat()
                break
            except ValueError:
                continue

    domain_match = re.search(r'\*\*Domain:\*\*\s*(.+)', text)
    if domain_match:
        data["domain"] = domain_match.group(1).strip()

    model_match = re.search(r'\*\*Model:\*\*\s*(.+)', text)
    if model_match:
        data["model"] = model_match.group(1).strip()

    # Parse sections
    problem_match = re.search(r'##\s*(?:Problem|Measured Problem)\s*\n+(.*?)(?=\n##\s|\Z)', text, re.DOTALL)
    if problem_match:
        data["problem"] = problem_match.group(1).strip()

    solution_match = re.search(r'##\s*(?:Solution|Proposed Change|Proposed Solution)\s*\n+(.*?)(?=\n##\s|\Z)', text, re.DOTALL)
    if solution_match:
        data["solution"] = solution_match.group(1).strip()

    # Parse status
    impl_match = re.search(r'\*\*Implemented:\*\*\s*(YES|NO|PARTIAL)', text, re.IGNORECASE)
    if impl_match:
        data["implemented"] = impl_match.group(1).upper()

    # Parse category
    cat_match = re.search(r'\*\*Category:\*\*\s*(.+)', text)
    if cat_match:
        data["category"] = cat_match.group(1).strip()

    # Generate a stable ID from agent + timestamp + title
    id_source = f"{data['agent']}-{data['timestamp']}-{data['title']}"
    data["proposal_id"] = hashlib.sha256(id_source.encode()).hexdigest()[:12]

    return data


def check_existing_in_neo4j(proposal_id: str) -> bool:
    """Check if a proposal with this ID already exists in Neo4j."""
    with neo4j_session() as session:
        result = session.run(
            "MATCH (p:Proposal {proposal_id: $pid}) RETURN count(p) AS cnt",
            pid=proposal_id
        )
        record = result.single()
        return record and record["cnt"] > 0


TIER_TTL_HOURS = {"T0": 1, "T1": 1, "T2": 5, "T3": 14}

def ingest_proposal(data: dict) -> bool:
    """Create a Proposal node in Neo4j from parsed data."""
    now = datetime.now()
    tier = data.get("tier", "T2")
    ttl_hours = TIER_TTL_HOURS.get(tier, 24)
    expires_at = now + timedelta(hours=ttl_hours)

    # Determine status based on implementation state
    status = "pending"
    if data.get("implemented") == "YES":
        status = "implemented"

    with neo4j_session() as session:
        # Ensure Agent node exists
        session.run(
            "MERGE (a:Agent {name: $name})",
            name=data["agent"]
        )

        # Create Proposal node
        session.run("""
            MATCH (a:Agent {name: $agent})
            CREATE (p:Proposal {
                proposal_id: $proposal_id,
                title: $title,
                description: $description,
                proposing_agent: $agent,
                created_at: datetime($created_at),
                expires_at: datetime($expires_at),
                status: $status,
                priority: 'normal',
                category: $category,
                domain: $domain,
                implementation_tasks: [],
                vote_yes_count: 0,
                vote_no_count: 0,
                vote_abstain_count: 0,
                vote_total: 0,
                vote_unanimous: false,
                vote_threshold_met: false,
                tier: $tier,
                ingested_from: $filename,
                ingested_at: datetime()
            })
            CREATE (a)-[:PROPOSED {at: datetime($created_at)}]->(p)
        """,
            proposal_id=data["proposal_id"],
            title=data["title"] or data["filename"],
            description=data["full_text"],
            agent=data["agent"],
            created_at=data["timestamp"] or now.isoformat(),
            expires_at=expires_at.isoformat(),
            status=status,
            category=data["category"] or "feature",
            domain=data["domain"] or "general",
            filename=data["filename"],
            tier=tier
        )

        # Auto-cast YES vote from proposer (T0/T1 only).
        # T2/T3 proposers are excluded from voting on their own proposals.
        if tier in ("T0", "T1"):
            session.run("""
                MATCH (p:Proposal {proposal_id: $proposal_id})
                MATCH (a:Agent {name: $agent})
                CREATE (a)-[:VOTED_ON {at: datetime()}]->(v:Vote {
                    vote_id: $vote_id,
                    proposal_id: $proposal_id,
                    agent: $agent,
                    decision: 'yes',
                    reasoning: 'Proposed by me',
                    voted_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (v)-[:FOR_PROPOSAL]->(p)
                SET p.vote_yes_count = 1, p.vote_total = 1
            """,
                proposal_id=data["proposal_id"],
                agent=data["agent"],
                vote_id=hashlib.sha256(f"vote-{data['proposal_id']}-{data['agent']}".encode()).hexdigest()[:12]
            )

    return True


def collect_proposal_files(single_file: str = None) -> list:
    """Collect proposal files to process."""
    if single_file:
        p = Path(single_file)
        if not p.is_absolute():
            p = PROPOSALS_DIR / single_file
        if p.exists():
            return [p]
        # Try relative to proposals dir
        p = PROPOSALS_DIR / Path(single_file).name
        if p.exists():
            return [p]
        print(f"ERROR: File not found: {single_file}")
        return []

    # Collect all .md files in proposals root (not subdirectories like approved/, pending/, etc.)
    files = []
    for f in sorted(PROPOSALS_DIR.glob("*.md")):
        if f.is_file():
            files.append(f)
    return files


def main():
    parser = argparse.ArgumentParser(description="Ingest filesystem proposals into Neo4j")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be ingested without writing")
    parser.add_argument("--ingest", action="store_true", help="Ingest proposals into Neo4j")
    parser.add_argument("--file", type=str, default=None, help="Ingest a single proposal file")
    args = parser.parse_args()

    if not args.dry_run and not args.ingest:
        parser.print_help()
        return 1

    files = collect_proposal_files(args.file)
    if not files:
        print("No proposal files found.")
        return 0

    print(f"Found {len(files)} proposal file(s) in {PROPOSALS_DIR}")

    neo4j_ready = args.ingest

    ingested = 0
    skipped_dup = 0
    skipped_parse = 0
    errors = 0

    for filepath in files:
        data = parse_proposal_file(filepath)

        if not data["title"] and not data["agent"]:
            print(f"  SKIP (parse fail): {filepath.name}")
            skipped_parse += 1
            continue

        if args.dry_run:
            status_str = f"[{data.get('implemented', 'N/A')}]" if data.get("implemented") else "[pending]"
            print(f"  WOULD INGEST: {filepath.name}")
            print(f"    ID:       {data['proposal_id']}")
            print(f"    Title:    {data['title']}")
            print(f"    Agent:    {data['agent']}")
            print(f"    Domain:   {data.get('domain', 'N/A')}")
            print(f"    Category: {data.get('category', 'N/A')}")
            print(f"    Status:   {status_str}")
            print()
            ingested += 1
            continue

        # Check for duplicate
        if check_existing_in_neo4j(data["proposal_id"]):
            print(f"  SKIP (exists): {filepath.name} [{data['proposal_id']}]")
            skipped_dup += 1
            continue

        try:
            ingest_proposal(data)
            print(f"  INGESTED: {filepath.name} -> {data['proposal_id']} ({data['title'][:60]})")
            ingested += 1
        except Exception as e:
            print(f"  ERROR: {filepath.name}: {e}")
            errors += 1

    print(f"\n--- Summary ---")
    if args.dry_run:
        print(f"Would ingest: {ingested}")
        print(f"Parse failures: {skipped_parse}")
    else:
        print(f"Ingested: {ingested}")
        print(f"Skipped (duplicates): {skipped_dup}")
        print(f"Skipped (parse fail): {skipped_parse}")
        print(f"Errors: {errors}")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
