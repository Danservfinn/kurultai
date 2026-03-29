#!/usr/bin/env python3
from __future__ import annotations
"""
Agent Circuit Breaker — Prevent routing to failing agents.

States:
- CLOSED: Normal operation, routing allowed
- OPEN: Agent quarantined, routing blocked
- HALF-OPEN: Probation, limited routing allowed

Transitions:
CLOSED → OPEN: Failure rate ≥80% over 1h (min 3 tasks)
OPEN → HALF-OPEN: After 30min timeout
HALF-OPEN → CLOSED: Successful task completion OR 20min timeout (graceful recovery)
HALF-OPEN → OPEN: Failed task completion (re-opens circuit)

Usage:
    from circuit_breaker import AgentCircuitBreaker

    breaker = AgentCircuitBreaker()
    state = breaker.check_agent("temujin")
    if not state["available"]:
        # Find alternative agent
        ...
"""
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

# Import from kurultai_paths
try:
    from kurultai_paths import AGENTS_DIR, LOGS_DIR, VALID_AGENTS, DISPATCH_AGENTS
except ImportError:
    # Fallback paths
    AGENTS_DIR = Path.home() / ".openclaw" / "agents"
    LOGS_DIR = AGENTS_DIR / "main" / "logs"
    VALID_AGENTS = frozenset({"kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"})
    DISPATCH_AGENTS = ["temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]

try:
    from kurultai_ledger import read_ledger
except ImportError:
    # Fallback ledger reader
    TASK_LEDGER = Path.home() / ".openclaw" / "tasks" / "task-ledger.jsonl"

    def read_ledger(hours: float | None = None) -> list:
        """Fallback ledger reader if kurultai_ledger not available."""
        if not TASK_LEDGER.exists():
            return []
        cutoff = None
        if hours is not None:
            cutoff = datetime.now() - timedelta(hours=hours)
        events = []
        try:
            with open(TASK_LEDGER, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                        if cutoff is not None:
                            ts_str = ev.get("ts", "")
                            if ts_str:
                                try:
                                    ev_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                    if ev_time.tzinfo:
                                        if ev_time < cutoff:
                                            continue
                                    else:
                                        if ev_time < cutoff.replace(tzinfo=None):
                                            continue
                                except (ValueError, TypeError):
                                    pass
                        events.append(ev)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        return events


# Import task_utils for extracting task_id
try:
    from task_utils import extract_task_id
except ImportError:
    def extract_task_id(filepath: str):
        """Fallback task_id extraction."""
        import re
        from pathlib import Path
        filepath = Path(filepath)
        # Check filename for UUID pattern
        uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', filepath.name, re.I)
        if uuid_match:
            return uuid_match.group(1).lower()
        return None

# Neo4j sync helper
def _update_neo4j_task_agent(task_id: str, new_agent: str) -> bool:
    """Update task agent in Neo4j after redistribution.

    Note: Uses the neo4j_session() context manager which handles
    driver lifecycle automatically.
    """
    if not task_id:
        return False
    try:
        from neo4j_task_tracker import neo4j_session
        with neo4j_session() as session:
            result = session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.agent = $new_agent,
                    t.updated = datetime(),
                    t.redistributed = true
                RETURN t.task_id AS updated
            """, task_id=task_id, new_agent=new_agent)
            return result.single() is not None
    except Exception as e:
        print(f"[CircuitBreaker] Neo4j sync failed for {task_id}: {e}")
        return False


AgentState = Literal["CLOSED", "OPEN", "HALF_OPEN"]


class AgentCircuitBreaker:
    """Circuit breaker pattern for agent health."""

    # Configuration
    FAILURE_THRESHOLD = 0.8      # Open circuit at 80% failure rate
    MIN_TASKS_THRESHOLD = 3      # Minimum tasks before measuring
    RECOVERY_TIMEOUT = 1800      # 30 minutes in OPEN before HALF-OPEN
    HALF_OPEN_RECOVERY_TIMEOUT = 1200  # 20 minutes in HALF_OPEN before forced CLOSED (graceful recovery)
    SUCCESS_THRESHOLD = 0.5      # 50% success in HALF-OPEN to close circuit
    MAX_REDISTRIBUTION_PER_CYCLE = 10  # Max tasks to move per cycle
    MAX_REDISPATCH_COUNT = 3     # Max allowed agent-to-agent moves (matches task-redistribute.py)

    # State file location
    STATE_FILE = LOGS_DIR / "circuit-breaker-state.json"
    STATE_BACKUP_FILE = LOGS_DIR / "circuit-breaker-state.backup.json"
    LOG_FILE = LOGS_DIR / "circuit-breaker.log"

    def __init__(self, state_file: str | Path | None = None):
        """Initialize circuit breaker with optional custom state file."""
        if state_file:
            self.STATE_FILE = Path(state_file)
        self.state = self.load_state()

    def log(self, msg: str, level: str = "INFO"):
        """Write to circuit breaker log file."""
        try:
            self.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.LOG_FILE, "a") as f:
                f.write(f"[{ts}] {level}: {msg}\n")
        except Exception:
            pass

    def check_agent(self, agent: str) -> dict:
        """Check if agent is available for task routing.

        Returns:
            {
                "available": bool,
                "state": "CLOSED|OPEN|HALF_OPEN",
                "reason": str,
                "detail": str | None
            }
        """
        if agent not in VALID_AGENTS:
            return {
                "available": False,
                "state": "INVALID",
                "reason": "invalid_agent",
                "detail": f"Agent '{agent}' not in VALID_AGENTS"
            }

        # Initialize agent state if not exists
        if agent not in self.state["agents"]:
            self.state["agents"][agent] = {
                "state": "CLOSED",
                "since": 0,
                "failure_count": 0,
                "success_count": 0,
                "last_failure_rate": 0.0
            }
            self.save_state()

        agent_state = self.state["agents"][agent]
        current_state = agent_state["state"]

        # Handle OPEN → HALF-OPEN transition (timeout)
        if current_state == "OPEN":
            time_in_state = time.time() - agent_state["since"]
            if time_in_state > self.RECOVERY_TIMEOUT:
                self.log(f"Circuit breaker: {agent} entering HALF-OPEN (probation after {int(time_in_state)}s)")
                agent_state["state"] = "HALF_OPEN"
                agent_state["since"] = time.time()
                agent_state["half_open_trials"] = 0
                self.save_state()
                return {
                    "available": True,
                    "state": "HALF_OPEN",
                    "reason": "probation",
                    "detail": f"Agent entering probation after {int(time_in_state // 60)}min quarantine"
                }

        # Handle HALF_OPEN → CLOSED transition (timeout - graceful recovery)
        # This prevents agents from being stuck in HALF_OPEN forever when
        # they receive no tasks or all tasks fail. After 20min, force recovery.
        if current_state == "HALF_OPEN":
            time_in_state = time.time() - agent_state["since"]
            if time_in_state > self.HALF_OPEN_RECOVERY_TIMEOUT:
                self.log(f"Circuit breaker: {agent} HALF_OPEN→CLOSED (graceful recovery after {int(time_in_state)}s)")
                agent_state["state"] = "CLOSED"
                agent_state["since"] = 0
                # Reset failure count to give agent a fresh start
                agent_state["failure_count"] = 0
                if "half_open_trials" in agent_state:
                    del agent_state["half_open_trials"]
                self.save_state()
                return {
                    "available": True,
                    "state": "CLOSED",
                    "reason": "normal",
                    "detail": f"Graceful recovery after {int(time_in_state // 60)}min in HALF_OPEN"
                }

        # Handle OPEN/HALF_OPEN states
        if current_state == "OPEN":
            return {
                "available": False,
                "state": "OPEN",
                "reason": "quarantined",
                "detail": f"{agent_state['failure_count']} failures, {agent_state['last_failure_rate']:.0%} failure rate"
            }

        if current_state == "HALF_OPEN":
            return {
                "available": True,
                "state": "HALF_OPEN",
                "reason": "probation",
                "detail": f"Testing recovery, {agent_state.get('half_open_trials', 0)} trial(s)"
            }

        # CLOSED state
        return {
            "available": True,
            "state": "CLOSED",
            "reason": "normal",
            "detail": None
        }

    def record_result(self, agent: str, success: bool, task_id: str | None = None):
        """Record task result and update circuit state.

        Args:
            agent: Agent name
            success: True if task completed successfully
            task_id: Optional task ID for logging
        """
        if agent not in VALID_AGENTS:
            return

        # Initialize agent state if not exists
        if agent not in self.state["agents"]:
            self.state["agents"][agent] = {
                "state": "CLOSED",
                "since": 0,
                "failure_count": 0,
                "success_count": 0,
                "last_failure_rate": 0.0
            }

        agent_state = self.state["agents"][agent]
        task_info = f"({task_id[:8]})" if task_id else ""

        if success:
            agent_state["failure_count"] = 0
            agent_state["success_count"] += 1

            # HALF-OPEN → CLOSED on success
            if agent_state["state"] == "HALF_OPEN":
                trials = agent_state.get("half_open_trials", 0) + 1
                agent_state["half_open_trials"] = trials

                # Close circuit after first success in HALF-OPEN
                self.log(f"Circuit breaker: {agent} recovered, closing circuit {task_info}")
                agent_state["state"] = "CLOSED"
                agent_state["since"] = 0
                agent_state["failure_count"] = 0  # Reset failure count on recovery
                agent_state["last_failure_rate"] = 0.0  # FIX: Clear stale failure rate that blocks dispatch
                del agent_state["half_open_trials"]

            self.save_state()
        else:
            agent_state["failure_count"] += 1

            # Check if we should OPEN the circuit
            if agent_state["state"] in ["CLOSED", "HALF_OPEN"]:
                if agent_state["failure_count"] >= self.MIN_TASKS_THRESHOLD:
                    # Check recent failure rate
                    recent_rate = self.get_recent_failure_rate(agent, hours=1)
                    agent_state["last_failure_rate"] = recent_rate

                    if recent_rate >= self.FAILURE_THRESHOLD:
                        old_state = agent_state["state"]
                        agent_state["state"] = "OPEN"
                        agent_state["since"] = time.time()

                        self.log(
                            f"Circuit breaker: {agent} OPENING ({old_state}→OPEN) "
                            f"failure rate: {recent_rate:.0%}, {agent_state['failure_count']} consecutive {task_info}"
                        )

                        # Trigger redistribution
                        self.redistribute_agent_tasks(agent)

            self.save_state()

    def get_recent_failure_rate(self, agent: str, hours: int = 1) -> float:
        """Calculate failure rate from task ledger.

        Returns:
            float: Failure rate (0.0 to 1.0)
        """
        try:
            events = read_ledger(hours=hours)

            # Filter events for this agent
            agent_events = [
                e for e in events
                if e.get("agent") == agent and e.get("event") in ["COMPLETED", "FAILED"]
            ]

            if not agent_events:
                return 0.0

            if len(agent_events) < self.MIN_TASKS_THRESHOLD:
                return 0.0

            failed = sum(1 for e in agent_events if e.get("event") == "FAILED")
            return failed / len(agent_events)

        except Exception as e:
            self.log(f"Error calculating failure rate for {agent}: {e}", "ERROR")
            return 0.0

    def redistribute_agent_tasks(self, failed_agent: str):
        """Move pending tasks from failed agent to healthy agents.

        Limits to MAX_REDISTRIBUTION_PER_CYCLE tasks to avoid mass moves.
        """
        if failed_agent not in VALID_AGENTS:
            return

        # Find healthy agents (CLOSED state, not the failed agent)
        healthy = []
        for agent in DISPATCH_AGENTS:
            if agent == failed_agent:
                continue
            check = self.check_agent(agent)
            if check["state"] == "CLOSED":
                healthy.append(agent)

        if not healthy:
            self.log(f"No healthy agents available to redistribute from {failed_agent}", "WARN")
            return

        # Get pending tasks for failed agent
        tasks_dir = AGENTS_DIR / failed_agent / "tasks"
        if not tasks_dir.exists():
            return

        pending = []
        for f in tasks_dir.iterdir():
            if not f.name.endswith(".md"):
                continue
            # Skip terminal-state tasks — aligned with task-redistribute.py TERMINAL_MARKERS
            # to prevent redistribution of tasks that are no longer actionable.
            # Previously only filtered [".executing", ".completed", ".done"] which allowed
            # .stale-resolved, .revision, .quarantine files to be redistributed indefinitely.
            TERMINAL_MARKERS = (
                '.done', '.executing', '.stale', '.failed', '.obsolete',
                '.cancelled', '.resolved', '.revision', '.no_output', '.loop',
                '.pending-gate', '.blocked', '.quarantine',
            )
            if (any(marker in f.name for marker in TERMINAL_MARKERS)
                    or f.name.startswith('.')
                    or 'archived' in f.name
                    or f.name.endswith('.completed.md')):
                continue
            if not f.is_file():
                continue

            # FIX: Check Neo4j status to skip tasks already executing
            # This prevents moving tasks that are currently being worked on
            # which causes orphaned files when the original agent completes them
            task_id = extract_task_id(str(f))
            if task_id:
                try:
                    from neo4j_task_tracker import neo4j_session
                    with neo4j_session() as session:
                        result = session.run("""
                            MATCH (t:Task {task_id: $task_id})
                            RETURN t.status as status, t.claimed_by as claimed_by
                        """, task_id=task_id)
                        record = result.single()
                        if record:
                            status = record.get("status", "").upper()
                            if status == "EXECUTING":
                                self.log(f"Skipping {f.name}: already EXECUTING in Neo4j")
                                continue
                            # Also skip COMPLETED/FAILED tasks (shouldn't be here, but be safe)
                            if status in ("COMPLETED", "FAILED", "CANCELLED"):
                                self.log(f"Skipping {f.name}: already {status} in Neo4j (cleanup candidate)")
                                continue
                except Exception as e:
                    # If Neo4j check fails, log but don't skip (fail-open)
                    self.log(f"Neo4j check failed for {f.name}: {e}", "WARN")

            pending.append(f)

        if not pending:
            self.log(f"No pending tasks to redistribute from {failed_agent}")
            return

        # Sort by mtime (oldest first) for priority redistribution
        pending.sort(key=lambda p: p.stat().st_mtime)

        # Redistribute evenly, up to limit
        moved = 0
        for i, task_path in enumerate(pending[:self.MAX_REDISTRIBUTION_PER_CYCLE]):
            target = healthy[i % len(healthy)]

            try:
                # Move task file to target agent
                target_dir = AGENTS_DIR / target / "tasks"
                target_dir.mkdir(parents=True, exist_ok=True)

                new_path = target_dir / task_path.name

                # Update file content: change agent field AND add redistribution note
                content = task_path.read_text(encoding="utf-8", errors="replace")

                # Check redispatch_count to prevent infinite bouncing
                # This matches task-redistribute.py logic: tasks that have been
                # redistributed MAX_REDISPATCH_COUNT times need manual review
                redispatch_match = re.search(r'^redispatch_count:\s*(\d+)$', content, re.MULTILINE)
                current_count = int(redispatch_match.group(1)) if redispatch_match else 0
                if current_count >= self.MAX_REDISPATCH_COUNT:
                    self.log(f"Skipping {task_path.name}: redispatch_count={current_count} >= {self.MAX_REDISPATCH_COUNT}", "WARN")
                    continue

                # CRITICAL FIX: Update the agent field in frontmatter
                # Without this, task-watcher won't dispatch the task because
                # the file is in target's directory but frontmatter still points to failed_agent
                new_count = current_count + 1
                updated_content = re.sub(
                    r'^agent:\s*\w+\s*$',
                    f'agent: {target}',
                    content,
                    flags=re.MULTILINE
                )

                # Increment or insert redispatch_count (same logic as task-redistribute.py)
                if redispatch_match:
                    # Update existing redispatch_count
                    updated_content = re.sub(
                        r'^redispatch_count:\s*\d+$',
                        f'redispatch_count: {new_count}',
                        updated_content,
                        flags=re.MULTILINE
                    )
                else:
                    # Insert redispatch_count after priority line
                    updated_content = re.sub(
                        r'^(priority:.*)$',
                        rf'\1\nredispatch_count: {new_count}',
                        updated_content,
                        count=1,
                        flags=re.MULTILINE
                    )

                # Add redistribution note for audit trail (with count)
                redistribution_note = (
                    f"\n\n<!-- Task redistributed from {failed_agent} at {datetime.now().isoformat()} -->\n"
                    f"<!-- Reason: Circuit breaker quarantine -->\n"
                    f"<!-- Redispatch count: {new_count} -->\n"
                )
                updated_content = updated_content + redistribution_note

                new_path.write_text(updated_content)
                task_path.unlink()

                # Touch mtime so watcher picks it up
                new_path.touch()

                # Sync to Neo4j
                task_id = extract_task_id(str(task_path))
                if task_id:
                    if _update_neo4j_task_agent(task_id, target):
                        self.log(f"Synced Neo4j: {task_id[:8]}... -> {target}")
                    else:
                        self.log(f"WARNING: Neo4j sync failed for {task_id[:8]}...", "WARN")

                moved += 1
                self.log(f"Redistributed {task_path.name} from {failed_agent} to {target}")

                # Record in state
                if "redistributions" not in self.state:
                    self.state["redistributions"] = []
                self.state["redistributions"].append({
                    "from": failed_agent,
                    "to": target,
                    "task": task_path.name,
                    "ts": datetime.now().isoformat()
                })

            except Exception as e:
                self.log(f"Failed to redistribute {task_path.name}: {e}", "ERROR")

        if moved > 0:
            self.save_state()
            self.log(f"Redistribution complete: {moved} tasks moved from {failed_agent}")

    def load_state(self) -> dict:
        """Load circuit state from file with backup recovery."""
        default_state = {
            "ts": datetime.now().isoformat(),
            "agents": {},
            "redistributions": []
        }

        if not self.STATE_FILE.exists():
            # Try backup if main doesn't exist
            if self.STATE_BACKUP_FILE.exists():
                self.log(f"Main state missing, trying backup", "WARN")
                try:
                    with open(self.STATE_BACKUP_FILE, "r") as f:
                        loaded = json.load(f)
                        # Restore main file from backup
                        self.STATE_FILE.write_text(self.STATE_BACKUP_FILE.read_text())
                        self.log(f"Restored state from backup", "INFO")
                        return self._validate_state(loaded)
                except Exception as backup_err:
                    self.log(f"Backup recovery failed: {backup_err}", "ERROR")
            return default_state

        try:
            with open(self.STATE_FILE, "r") as f:
                loaded = json.load(f)
                return self._validate_state(loaded)
        except (json.JSONDecodeError, Exception) as e:
            self.log(f"Error loading state (corrupted?): {e}", "ERROR")
            # Try to recover from backup
            if self.STATE_BACKUP_FILE.exists():
                try:
                    with open(self.STATE_BACKUP_FILE, "r") as f:
                        loaded = json.load(f)
                        # Restore main file from backup
                        self.STATE_FILE.write_text(self.STATE_BACKUP_FILE.read_text())
                        self.log(f"Recovered state from backup after corruption", "INFO")
                        return self._validate_state(loaded)
                except Exception as backup_err:
                    self.log(f"Backup recovery also failed: {backup_err}", "ERROR")
            return default_state

    def _validate_state(self, state: dict) -> dict:
        """Ensure state structure is valid."""
        if "agents" not in state:
            state["agents"] = {}
        if "redistributions" not in state:
            state["redistributions"] = []
        return state

    def save_state(self):
        """Save circuit state to file using atomic write with backup."""
        try:
            self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.state["ts"] = datetime.now().isoformat()

            # Create backup of existing state before overwriting
            if self.STATE_FILE.exists():
                try:
                    import shutil
                    shutil.copy2(self.STATE_FILE, self.STATE_BACKUP_FILE)
                except Exception as backup_err:
                    self.log(f"Warning: backup creation failed: {backup_err}", "WARN")

            # Atomic write: write to temp file, then rename
            temp_file = self.STATE_FILE.with_suffix('.tmp.json')
            with open(temp_file, "w") as f:
                json.dump(self.state, f, indent=2)

            # Atomic rename (overwrites target)
            temp_file.replace(self.STATE_FILE)

        except Exception as e:
            self.log(f"Error saving state: {e}", "ERROR")

    def get_status_report(self) -> dict:
        """Return current status of all agents.

        Returns:
            {
                "ts": str,
                "agents": dict,
                "summary": {
                    "closed": int,
                    "open": int,
                    "half_open": int
                }
            }
        """
        report = {
            "ts": datetime.now().isoformat(),
            "agents": {},
            "summary": {"closed": 0, "open": 0, "half_open": 0}
        }

        for agent in VALID_AGENTS:
            if agent not in DISPATCH_AGENTS:
                continue

            check = self.check_agent(agent)
            state = check["state"]

            report["agents"][agent] = {
                "state": state,
                "available": check["available"],
                "reason": check["reason"],
                "detail": check["detail"]
            }

            # Update summary
            if state == "CLOSED":
                report["summary"]["closed"] += 1
            elif state == "OPEN":
                report["summary"]["open"] += 1
            elif state == "HALF_OPEN":
                report["summary"]["half_open"] += 1

        return report

    def reset_agent(self, agent: str):
        """Manually reset an agent's circuit to CLOSED (for admin use)."""
        if agent in self.state["agents"]:
            self.state["agents"][agent] = {
                "state": "CLOSED",
                "since": 0,
                "failure_count": 0,
                "success_count": 0,
                "last_failure_rate": 0.0
            }
            self.save_state()
            self.log(f"Manual reset: {agent} circuit reset to CLOSED")
            return True
        return False

    def recover_stale_circuits(self) -> dict:
        """Auto-recover circuits that have been OPEN longer than RECOVERY_TIMEOUT.

        This method transitions OPEN → HALF_OPEN after 30min quarantine.
        Called by watchdog every tick to ensure circuits don't stay stuck.

        Returns:
            {
                "recovered": list of agent names transitioned to HALF_OPEN,
                "still_open": list of agents still in quarantine,
                "timestamp": str
            }
        """
        recovered = []
        still_open = []

        for agent in VALID_AGENTS:
            if agent not in self.state["agents"]:
                continue

            agent_state = self.state["agents"][agent]
            if agent_state["state"] != "OPEN":
                continue

            time_in_state = time.time() - agent_state["since"]
            if time_in_state > self.RECOVERY_TIMEOUT:
                # Transition to HALF_OPEN
                self.log(
                    f"Auto-recovery: {agent} OPEN→HALF_OPEN after {int(time_in_state//60)}min quarantine "
                    f"({agent_state['failure_count']} failures, {agent_state['last_failure_rate']:.0%} rate)"
                )
                agent_state["state"] = "HALF_OPEN"
                agent_state["since"] = time.time()
                agent_state["half_open_trials"] = 0
                recovered.append(agent)
            else:
                still_open.append({
                    "agent": agent,
                    "minutes_remaining": int((self.RECOVERY_TIMEOUT - time_in_state) // 60),
                    "failures": agent_state["failure_count"]
                })

        if recovered:
            self.save_state()

        return {
            "recovered": recovered,
            "still_open": still_open,
            "timestamp": datetime.now().isoformat()
        }


# CLI for manual management
def main():
    """CLI for circuit breaker management."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Agent Circuit Breaker — Manage agent quarantines"
    )
    parser.add_argument("--status", action="store_true", help="Show circuit breaker status")
    parser.add_argument("--reset", type=str, metavar="AGENT", help="Reset agent circuit to CLOSED")
    parser.add_argument("--check", type=str, metavar="AGENT", help="Check specific agent status")
    parser.add_argument("--recover", action="store_true", help="Auto-recover stale OPEN circuits")
    args = parser.parse_args()

    breaker = AgentCircuitBreaker()

    if args.status:
        report = breaker.get_status_report()
        print(json.dumps(report, indent=2))
        return

    if args.check:
        check = breaker.check_agent(args.check)
        print(json.dumps(check, indent=2))
        return

    if args.reset:
        if breaker.reset_agent(args.reset):
            print(f"Reset {args.reset} circuit to CLOSED")
        else:
            print(f"Agent {args.reset} not found in circuit state")
        return

    if args.recover:
        result = breaker.recover_stale_circuits()
        print(json.dumps(result, indent=2))
        return

    # Default: show status
    report = breaker.get_status_report()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
