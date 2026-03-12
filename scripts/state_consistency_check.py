#!/usr/bin/env python3
"""
State Consistency Check for OpenClaw Kurultai

Compares Neo4j task state with filesystem state and reports discrepancies.
Detects:
- Tasks in Neo4j but missing on filesystem (orphaned Neo4j nodes)
- Tasks on filesystem but missing in Neo4j (filesystem-only tasks)
- Stale task status (Neo4j says pending but file is .done.md)
- Stale lock files (>15 min old)

Usage: python3 scripts/state_consistency_check.py [--fix]
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

# Add scripts dir to path
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    print("WARNING: neo4j module not available - skipping Neo4j checks")

AGENTS_DIR = Path.home() / ".openclaw" / "agents"
MAIN_DIR = AGENTS_DIR / "main"
LOGS_DIR = MAIN_DIR / "logs"

STALE_LOCK_THRESHOLD = 15 * 60  # 15 minutes


def parse_lock_timestamp(lock_path: Path) -> datetime | None:
    """Parse timestamp from lock file."""
    try:
        content = lock_path.read_text().strip()
        # Format: PID\n2026-03-11T14:15:00.640429
        if "\n" in content:
            timestamp_str = content.split("\n")[1]
            return datetime.fromisoformat(timestamp_str)
    except Exception:
        pass
    return None


def check_stale_locks() -> List[Path]:
    """Find lock files older than STALE_LOCK_THRESHOLD seconds."""
    stale = []
    for lock_file in LOGS_DIR.glob("*.lock"):
        ts = parse_lock_timestamp(lock_file)
        if ts:
            age = (datetime.now() - ts).total_seconds()
            if age > STALE_LOCK_THRESHOLD:
                stale.append((lock_file, age))
    return stale


def get_filesystem_tasks(agent: str) -> Dict[str, str]:
    """Get all tasks for an agent from filesystem.
    
    Returns dict mapping task_name -> status ('pending', 'done', 'executing')
    """
    tasks_dir = AGENTS_DIR / agent / "tasks"
    if not tasks_dir.exists():
        return {}
    
    result = {}
    for f in tasks_dir.glob("*.md"):
        if f.name.startswith("."):
            continue
        name = f.stem
        
        if f.name.endswith(".done.md"):
            result[name] = "done"
        elif ".executing." in f.name:
            result[name] = "executing"
        else:
            result[name] = "pending"
    
    return result


def get_neo4j_tasks(agent: str, driver) -> Dict[str, str]:
    """Get all tasks for an agent from Neo4j."""
    if not NEO4J_AVAILABLE:
        return {}
    
    query = """
        MATCH (t:Task {agent: $agent})
        RETURN t.name as name, t.status as status
    """
    with driver.session() as session:
        result = session.run(query, agent=agent)
        return {record["name"]: record["status"] for record in result}


def compare_states(agent: str, driver=None) -> Dict:
    """Compare filesystem and Neo4j states for an agent."""
    fs_tasks = get_filesystem_tasks(agent)
    neo_tasks = get_neo4j_tasks(agent, driver) if driver else {}
    
    # Tasks in Neo4j but not on filesystem
    orphaned_neo = set(neo_tasks.keys()) - set(fs_tasks.keys())
    
    # Tasks on filesystem but not in Neo4j
    orphaned_fs = set(fs_tasks.keys()) - set(neo_tasks.keys())
    
    # Status mismatches
    mismatches = []
    for name in set(fs_tasks.keys()) & set(neo_tasks.keys()):
        fs_status = fs_tasks[name]
        neo_status = neo_tasks[name]
        
        # Map filesystem status to Neo4j status
        # fs: pending/done/executing -> neo: pending/completed/executing
        status_map = {"pending": "pending", "done": "completed", "executing": "executing"}
        expected_neo = status_map.get(fs_status, fs_status)
        
        if neo_status != expected_neo:
            mismatches.append({
                "name": name,
                "fs_status": fs_status,
                "neo_status": neo_status,
                "expected": expected_neo
            })
    
    return {
        "agent": agent,
        "fs_count": len(fs_tasks),
        "neo_count": len(neo_tasks),
        "orphaned_neo": list(orphaned_neo),
        "orphaned_fs": list(orphaned_fs),
        "mismatches": mismatches
    }


def main():
    parser = argparse.ArgumentParser(description="Check state consistency")
    parser.add_argument("--fix", action="store_true", help="Auto-fix stale locks")
    parser.add_argument("--agent", help="Check specific agent only")
    args = parser.parse_args()
    
    issues_found = False
    
    print("=" * 60)
    print("STATE CONSISTENCY CHECK")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)
    
    # Check stale locks
    print("\n[1] Checking for stale lock files...")
    stale_locks = check_stale_locks()
    if stale_locks:
        issues_found = True
        for lock_path, age in stale_locks:
            print(f"  STALE: {lock_path.name} ({age/60:.1f} min old)")
            if args.fix:
                print(f"    -> Removing stale lock...")
                lock_path.unlink()
    else:
        print("  OK: No stale locks")
    
    # Check Neo4j/filesystem consistency
    if NEO4J_AVAILABLE:
        print("\n[2] Checking Neo4j/filesystem consistency...")
        
        try:
            driver = GraphDatabase.driver(
                "bolt://localhost:7687",
                auth=("neo4j", "password"),
                max_connection_lifetime=30
            )
            driver.verify_connectivity()
            
            agents = [args.agent] if args.agent else ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]
            
            total_orphaned_neo = 0
            total_orphaned_fs = 0
            total_mismatches = 0
            
            for agent in agents:
                result = compare_states(agent, driver)
                
                agent_issues = (
                    len(result["orphaned_neo"]) +
                    len(result["orphaned_fs"]) +
                    len(result["mismatches"])
                )
                
                if agent_issues > 0:
                    issues_found = True
                    print(f"\n  {agent.upper()}:")
                    print(f"    fs={result['fs_count']} neo={result['neo_count']}")
                    
                    if result["orphaned_neo"]:
                        print(f"    Orphaned Neo4j nodes ({len(result['orphaned_neo'])}):")
                        for t in result["orphaned_neo"][:5]:
                            print(f"      - {t}")
                        total_orphaned_neo += len(result["orphaned_neo"])
                    
                    if result["orphaned_fs"]:
                        print(f"    Orphaned filesystem tasks ({len(result['orphaned_fs'])}):")
                        for t in result["orphaned_fs"][:5]:
                            print(f"      - {t}")
                        total_orphaned_fs += len(result["orphaned_fs"])
                    
                    if result["mismatches"]:
                        print(f"    Status mismatches ({len(result['mismatches'])}):")
                        for m in result["mismatches"][:3]:
                            print(f"      - {m['name']}: fs={m['fs_status']} neo={m['neo_status']}")
                        total_mismatches += len(result["mismatches"])
            
            if not issues_found:
                print("  OK: All agents consistent")
            else:
                print(f"\n  Summary: {total_orphaned_neo} orphaned Neo4j, {total_orphaned_fs} orphaned fs, {total_mismatches} mismatches")
            
            driver.close()
            
        except Exception as e:
            print(f"  ERROR: {e}")
            issues_found = True
    else:
        print("\n[2] Skipping Neo4j checks (module unavailable)")
    
    # Exit code
    print("\n" + "=" * 60)
    if issues_found:
        print("RESULT: ISSUES FOUND")
        print("Run with --fix to auto-correct stale locks")
        return 1
    else:
        print("RESULT: ALL CHECKS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
