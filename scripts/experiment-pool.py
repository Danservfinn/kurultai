#!/usr/bin/env python3
"""
Experiment Pool - Bounded concurrent experiment daemon for Kurultai

Manages a pool of experiment workers with:
- Hard limit on concurrent experiments (MAX_CONCURRENT)
- Per-experiment timeout (EXPERIMENT_TIMEOUT)
- Resource pre-checks (memory, disk, load average)
- Process group isolation for clean termination
- Automatic zombie cleanup

Usage:
    # Run as daemon
    python3 experiment-pool.py

    # Submit experiment via queue.json
    echo '{"agent":"temujin","hypothesis":"test","target_files":["scripts/test.py"]}' > queue.json

    # Query status
    python3 experiment-pool.py --status
"""

import os
import sys
import json
import time
import signal
import subprocess
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List, Dict

import psutil

# Configuration
MAX_CONCURRENT = 3
EXPERIMENT_TIMEOUT = 300  # 5 minutes

# Resource thresholds
MIN_FREE_MEMORY_GB = 2
MIN_FREE_DISK_GB = 20
MAX_LOAD_MULTIPLIER = 2.0

# Paths
OPENCLAW_DIR = Path.home() / ".openclaw"
POOL_DIR = OPENCLAW_DIR / "agents" / "main" / ".experiment-pool"
QUEUE_FILE = POOL_DIR / "queue.json"
STATE_FILE = POOL_DIR / "state.json"
LOG_FILE = OPENCLAW_DIR / "agents" / "main" / "logs" / "experiment-pool.log"

# Ensure directories exist
POOL_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("experiment-pool")


@dataclass
class Experiment:
    """Represents an experiment in the pool."""
    exp_id: str
    agent: str
    hypothesis: str
    target_files: List[str]
    pid: Optional[int] = None
    pgid: Optional[int] = None  # Process group ID
    status: str = "pending"  # pending, running, completed, crashed, timeout
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        # Convert datetime objects to ISO strings
        for key, value in d.items():
            if isinstance(value, datetime):
                d[key] = value.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Experiment":
        """Create Experiment from dictionary."""
        # Convert ISO strings back to datetime
        for key in ["created_at", "started_at", "completed_at"]:
            if data.get(key) and isinstance(data[key], str):
                data[key] = datetime.fromisoformat(data[key])
        return cls(**data)

    def runtime_seconds(self) -> float:
        """Get elapsed runtime in seconds."""
        if self.started_at is None:
            return 0
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()


class ResourceChecker:
    """Checks system resources before starting experiments."""

    @staticmethod
    def check_memory() -> tuple[bool, str]:
        """Check if sufficient free memory available."""
        try:
            mem = psutil.virtual_memory()
            free_gb = mem.available / (1024 ** 3)

            if free_gb < MIN_FREE_MEMORY_GB:
                return False, f"Insufficient memory: {free_gb:.1f}GB free, {MIN_FREE_MEMORY_GB}GB required"

            return True, f"Memory OK: {free_gb:.1f}GB free"
        except Exception as e:
            logger.warning(f"Could not check memory: {e}")
            return True, "Memory check skipped"

    @staticmethod
    def check_disk() -> tuple[bool, str]:
        """Check if sufficient disk space available."""
        try:
            disk = psutil.disk_usage(str(OPENCLAW_DIR))
            free_gb = disk.free / (1024 ** 3)

            if free_gb < MIN_FREE_DISK_GB:
                return False, f"Insufficient disk: {free_gb:.1f}GB free, {MIN_FREE_DISK_GB}GB required"

            return True, f"Disk OK: {free_gb:.1f}GB free"
        except Exception as e:
            logger.warning(f"Could not check disk: {e}")
            return True, "Disk check skipped"

    @staticmethod
    def check_load() -> tuple[bool, str]:
        """Check if system load is acceptable."""
        try:
            load1, load5, load15 = os.getloadavg()
            cpu_count = os.cpu_count() or 1

            if load1 > cpu_count * MAX_LOAD_MULTIPLIER:
                return False, f"High load: {load1:.2f} (CPU count: {cpu_count})"

            return True, f"Load OK: {load1:.2f}"
        except Exception as e:
            logger.warning(f"Could not check load: {e}")
            return True, "Load check skipped"

    @classmethod
    def check_all(cls) -> tuple[bool, List[str]]:
        """Run all resource checks."""
        checks = [
            cls.check_memory(),
            cls.check_disk(),
            cls.check_load()
        ]

        all_passed = all(check[0] for check in checks)
        messages = [check[1] for check in checks]

        return all_passed, messages


class ExperimentPool:
    """
    Manages a bounded pool of concurrent experiments.

    Features:
    - MAX_CONCURRENT limit enforced
    - EXPERIMENT_TIMEOUT per experiment
    - Resource pre-checks before starting
    - Process group isolation for clean termination
    - Zombie process cleanup
    """

    def __init__(self):
        self.experiments: Dict[str, Experiment] = {}
        self._running = True
        self._load_state()

    def _load_state(self):
        """Load previous state from disk."""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE) as f:
                    data = json.load(f)
                    for exp_data in data.get("experiments", []):
                        exp = Experiment.from_dict(exp_data)
                        # Reset running experiments to pending (they may have died)
                        if exp.status == "running":
                            exp.status = "pending"
                            exp.pid = None
                            exp.pgid = None
                        self.experiments[exp.exp_id] = exp
                logger.info(f"Loaded {len(self.experiments)} experiments from state")
            except Exception as e:
                logger.warning(f"Could not load state: {e}")

    def _save_state(self):
        """Save current state to disk."""
        try:
            data = {
                "experiments": [exp.to_dict() for exp in self.experiments.values()],
                "updated": datetime.now().isoformat()
            }
            temp_file = STATE_FILE.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)
            temp_file.rename(STATE_FILE)
        except Exception as e:
            logger.error(f"Could not save state: {e}")

    def _generate_exp_id(self) -> str:
        """Generate unique experiment ID."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        counter = 1
        while True:
            exp_id = f"exp-{timestamp}-{counter:03d}"
            if exp_id not in self.experiments:
                return exp_id
            counter += 1

    def _read_queue(self) -> List[dict]:
        """Read and clear the queue file."""
        if not QUEUE_FILE.exists():
            return []

        try:
            with open(QUEUE_FILE) as f:
                data = json.load(f)

            # Clear queue after reading
            QUEUE_FILE.unlink()

            # Normalize to list
            if isinstance(data, dict):
                data = [data]
            return data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not read queue: {e}")
            return []

    def _count_running(self) -> int:
        """Count currently running experiments."""
        return sum(1 for exp in self.experiments.values() if exp.status == "running")

    def _is_process_alive(self, pid: int) -> bool:
        """Check if a process is still running."""
        try:
            return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def _kill_process_group(self, pgid: int) -> bool:
        """Kill entire process group."""
        try:
            os.killpg(pgid, signal.SIGTERM)
            # Wait a bit for graceful shutdown
            time.sleep(0.5)
            # Force kill if still running
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # Already dead
            return True
        except ProcessLookupError:
            return True  # Already dead
        except Exception as e:
            logger.warning(f"Could not kill process group {pgid}: {e}")
            return False

    def _start_experiment(self, exp: Experiment) -> bool:
        """Start an experiment subprocess."""
        # Build command to run experiment via agent task handler
        cmd = [
            sys.executable,
            str(OPENCLAW_DIR / "agents" / "main" / "scripts" / "agent-task-handler.py"),
            "--agent", exp.agent,
            "--task-type", "experiment",
            "--hypothesis", exp.hypothesis,
            "--target-files", ",".join(exp.target_files),
            "--experiment-id", exp.exp_id
        ]

        try:
            # Start process in new session (process group isolation)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True  # Creates new process group
            )

            exp.pid = proc.pid
            exp.pgid = proc.pid  # Process group ID equals PID in new session
            exp.status = "running"
            exp.started_at = datetime.now()

            logger.info(f"Started {exp.exp_id} with PID {exp.pid}, PGID {exp.pgid}")
            return True

        except Exception as e:
            logger.error(f"Failed to start {exp.exp_id}: {e}")
            exp.status = "crashed"
            exp.error_message = str(e)
            exp.completed_at = datetime.now()
            return False

    def submit(self, request: dict) -> Optional[str]:
        """
        Submit a new experiment to the pool.

        Args:
            request: Dict with agent, hypothesis, target_files

        Returns:
            Experiment ID if submitted/queued, None if rejected
        """
        # Validate request
        required = ["agent", "hypothesis", "target_files"]
        if not all(k in request for k in required):
            logger.warning(f"Invalid request, missing required fields: {required}")
            return None

        # Check resource availability
        resources_ok, messages = ResourceChecker.check_all()
        if not resources_ok:
            logger.warning(f"Resource check failed: {messages}")
            return None

        # Create experiment
        exp = Experiment(
            exp_id=self._generate_exp_id(),
            agent=request["agent"],
            hypothesis=request["hypothesis"],
            target_files=request["target_files"]
        )

        self.experiments[exp.exp_id] = exp
        self._save_state()

        # Try to start immediately if capacity available
        if self._count_running() < MAX_CONCURRENT:
            if self._start_experiment(exp):
                logger.info(f"Started {exp.exp_id} immediately")
            else:
                logger.error(f"Failed to start {exp.exp_id}")
        else:
            logger.info(f"Queued {exp.exp_id} (max concurrent reached)")

        return exp.exp_id

    def monitor(self) -> None:
        """Monitor running experiments for timeout, crash, or completion."""
        now = datetime.now()

        for exp in self.experiments.values():
            if exp.status != "running":
                continue

            # Check if process is still alive
            if exp.pid and not self._is_process_alive(exp.pid):
                self._crashed(exp)
                continue

            # Check timeout
            if exp.started_at and (now - exp.started_at).total_seconds() > EXPERIMENT_TIMEOUT:
                self._timeout(exp)
                continue

            # Check for natural completion
            if exp.pid:
                try:
                    proc = psutil.Process(exp.pid)
                    if proc.status() == psutil.STATUS_ZOMBIE:
                        # Reap zombie
                        proc.wait()
                        self._completed(exp, proc.returncode)
                        continue
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # Process died between checks
                    self._crashed(exp)
                    continue

    def _timeout(self, exp: Experiment) -> None:
        """Handle experiment timeout."""
        logger.warning(f"Timeout: {exp.exp_id} after {exp.runtime_seconds():.1f}s")

        if exp.pgid:
            if self._kill_process_group(exp.pgid):
                logger.info(f"Killed process group {exp.pgid}")

        exp.status = "timeout"
        exp.completed_at = datetime.now()
        self._save_state()

        # Trigger rollback by notifying the agent
        self._trigger_rollback(exp, "timeout")

    def _crashed(self, exp: Experiment) -> None:
        """Handle crashed experiment."""
        logger.warning(f"Crashed: {exp.exp_id}")

        exp.status = "crashed"
        exp.completed_at = datetime.now()

        # Try to get exit code
        if exp.pid:
            try:
                proc = psutil.Process(exp.pid)
                exp.exit_code = proc.returncode
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        self._save_state()
        self._trigger_rollback(exp, "crash")

    def _completed(self, exp: Experiment, exit_code: int) -> None:
        """Handle successfully completed experiment."""
        logger.info(f"Completed: {exp.exp_id} with exit code {exit_code}")

        exp.status = "completed"
        exp.exit_code = exit_code
        exp.completed_at = datetime.now()
        self._save_state()

    def _trigger_rollback(self, exp: Experiment, reason: str) -> None:
        """Trigger rollback for failed experiment."""
        # Create rollback task in mongke's workspace
        mongke_workspace = Path.home() / ".openclaw" / "agents" / "mongke" / "workspace"
        mongke_workspace.mkdir(parents=True, exist_ok=True)

        rollback_file = mongke_workspace / f"rollback-{exp.exp_id}.json"
        rollback_data = {
            "experiment_id": exp.exp_id,
            "agent": exp.agent,
            "hypothesis": exp.hypothesis,
            "target_files": exp.target_files,
            "reason": reason,
            "status": exp.status,
            "created_at": datetime.now().isoformat()
        }

        try:
            with open(rollback_file, "w") as f:
                json.dump(rollback_data, f, indent=2)
            logger.info(f"Created rollback task: {rollback_file}")
        except Exception as e:
            logger.error(f"Could not create rollback task: {e}")

    def process_queue(self) -> int:
        """
        Process queued experiments and start pending ones.

        Returns:
            Number of new experiments started
        """
        started = 0

        # Read new requests from queue
        requests = self._read_queue()
        for req in requests:
            exp_id = self.submit(req)
            if exp_id:
                logger.info(f"Submitted {exp_id}")
                started += 1

        # Start pending experiments if capacity available
        running_count = self._count_running()
        available = MAX_CONCURRENT - running_count

        if available > 0:
            for exp in self.experiments.values():
                if exp.status == "pending" and available > 0:
                    if self._start_experiment(exp):
                        started += 1
                        available -= 1

        return started

    def cleanup_zombies(self) -> int:
        """Clean up zombie processes."""
        cleaned = 0

        for proc in psutil.process_iter(['pid', 'name', 'status']):
            try:
                if proc.info['status'] == psutil.STATUS_ZOMBIE:
                    # Try to reap zombie
                    proc.wait(timeout=0.1)
                    cleaned += 1
            except (psutil.NoSuchProcess, psutil.TimeoutExpired, psutil.AccessDenied):
                pass

        if cleaned > 0:
            logger.info(f"Cleaned {cleaned} zombie processes")

        return cleaned

    def get_status(self) -> dict:
        """Get current pool status."""
        return {
            "max_concurrent": MAX_CONCURRENT,
            "running": self._count_running(),
            "pending": sum(1 for exp in self.experiments.values() if exp.status == "pending"),
            "completed": sum(1 for exp in self.experiments.values() if exp.status == "completed"),
            "crashed": sum(1 for exp in self.experiments.values() if exp.status == "crashed"),
            "timeout": sum(1 for exp in self.experiments.values() if exp.status == "timeout"),
            "experiments": [exp.to_dict() for exp in self.experiments.values()]
        }

    def run_once(self) -> None:
        """Single iteration of the pool loop."""
        # Process queue and start pending experiments
        started = self.process_queue()

        # Monitor running experiments
        self.monitor()

        # Cleanup zombies
        self.cleanup_zombies()

        # Save state
        self._save_state()

        return started

    def run(self, interval: int = 5) -> None:
        """
        Run the pool daemon loop.

        Args:
            interval: Seconds between iterations
        """
        logger.info(f"Starting ExperimentPool (max={MAX_CONCURRENT}, timeout={EXPERIMENT_TIMEOUT}s)")

        while self._running:
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"Error in pool loop: {e}", exc_info=True)

            time.sleep(interval)

        logger.info("ExperimentPool stopped")

    def stop(self) -> None:
        """Stop the pool daemon."""
        logger.info("Stopping ExperimentPool...")
        self._running = False

        # Terminate all running experiments
        for exp in self.experiments.values():
            if exp.status == "running" and exp.pgid:
                logger.info(f"Terminating {exp.exp_id}")
                self._kill_process_group(exp.pgid)

        self._save_state()


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}")
    if pool:
        pool.stop()
    sys.exit(0)


pool: Optional[ExperimentPool] = None


def main():
    """Main entry point."""
    global pool

    # Check for --status flag
    if "--status" in sys.argv:
        temp_pool = ExperimentPool()
        status = temp_pool.get_status()
        print(json.dumps(status, indent=2))
        return

    # Check for --submit flag
    if "--submit" in sys.argv:
        # Read JSON from stdin or file
        if len(sys.argv) > 2:
            with open(sys.argv[2]) as f:
                request = json.load(f)
        else:
            request = json.load(sys.stdin)

        # Ensure queue directory exists
        POOL_DIR.mkdir(parents=True, exist_ok=True)

        # Write to queue
        with open(QUEUE_FILE, "w") as f:
            json.dump(request, f)

        print(f"Submitted to queue: {QUEUE_FILE}")
        return

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create and run pool
    pool = ExperimentPool()
    pool.run()


if __name__ == "__main__":
    main()
