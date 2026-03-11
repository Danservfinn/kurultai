#!/usr/bin/env python3
"""
Centralized Subprocess Manager for Kurultai agents.

Handles process lifecycle, zombie reaping, and graceful termination.
Prevents accumulation of zombie processes and ensures clean subprocess management.

Usage:
    from subprocess_manager import SubprocessManager

    manager = SubprocessManager()
    result = manager.run_command(['ls', '-la'], timeout=30)
"""

import os
import signal
import subprocess
import logging
import time
from typing import Optional, List, Dict, Any, Union
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


class SubprocessError(Exception):
    """Custom exception for subprocess errors."""
    pass


class TimeoutError(SubprocessError):
    """Raised when subprocess times out."""
    pass


class SubprocessManager:
    """
    Centralized subprocess management with:
    - Zombie process prevention
    - Timeout handling
    - Process tree termination
    - Resource cleanup
    """

    def __init__(self, default_timeout: int = 300):
        self.default_timeout = default_timeout
        self._active_processes: Dict[int, subprocess.Popen] = {}
        self._lock = None  # Will be initialized when needed

    def _get_lock(self):
        """Lazy initialization of lock to avoid import issues."""
        if self._lock is None:
            import threading
            self._lock = threading.RLock()
        return self._lock

    def _register_process(self, proc: subprocess.Popen) -> None:
        """Track an active process."""
        with self._get_lock():
            self._active_processes[proc.pid] = proc

    def _unregister_process(self, pid: int) -> None:
        """Remove a process from tracking."""
        with self._get_lock():
            self._active_processes.pop(pid, None)

    def terminate_process_tree(self, proc: subprocess.Popen, timeout: int = 30) -> bool:
        """
        Terminate a process and all its children.

        Uses process group to kill entire tree, preventing orphaned children.

        Args:
            proc: The Popen object to terminate
            timeout: Seconds to wait for graceful termination before SIGKILL

        Returns:
            True if process terminated successfully
        """
        if proc.poll() is not None:
            return True  # Already dead

        try:
            # Try graceful termination first
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)

            try:
                proc.wait(timeout=timeout)
                logger.debug(f"Process {proc.pid} terminated gracefully")
                return True
            except subprocess.TimeoutExpired:
                # Force kill
                os.killpg(pgid, signal.SIGKILL)
                proc.wait()
                logger.warning(f"Process {proc.pid} force-killed after timeout")
                return True

        except ProcessLookupError:
            # Process already gone
            return True
        except PermissionError:
            logger.error(f"Permission denied killing process {proc.pid}")
            return False
        except Exception as e:
            logger.error(f"Error terminating process {proc.pid}: {e}")
            return False
        finally:
            self._unregister_process(proc.pid)

    def run_command(
        self,
        cmd: Union[List[str], str],
        timeout: Optional[int] = None,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        capture_output: bool = True,
        check: bool = False
    ) -> subprocess.CompletedProcess:
        """
        Run a command with proper timeout and cleanup.

        Args:
            cmd: Command to run (list or string)
            timeout: Timeout in seconds (default: self.default_timeout)
            cwd: Working directory
            env: Environment variables
            capture_output: Whether to capture stdout/stderr
            check: Raise exception on non-zero exit

        Returns:
            CompletedProcess with result
        """
        timeout = timeout or self.default_timeout

        try:
            result = subprocess.run(
                cmd,
                timeout=timeout,
                cwd=cwd,
                env=env,
                capture_output=capture_output,
                text=True,
                check=check
            )
            return result

        except subprocess.TimeoutExpired as e:
            logger.error(f"Command timed out after {timeout}s: {cmd}")
            raise TimeoutError(f"Command timed out: {cmd}") from e
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed with exit {e.returncode}: {cmd}")
            raise

    @contextmanager
    def managed_process(
        self,
        cmd: List[str],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None
    ):
        """
        Context manager for running a subprocess with automatic cleanup.

        Usage:
            with manager.managed_process(['python', 'script.py']) as proc:
                stdout, stderr = proc.communicate(timeout=30)

        Yields:
            Popen object
        """
        timeout = timeout or self.default_timeout
        proc = None

        try:
            # Start process in new process group for clean termination
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                preexec_fn=os.setsid,  # Create new process group
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self._register_process(proc)
            logger.debug(f"Started process {proc.pid}: {cmd}")
            yield proc

        finally:
            if proc and proc.poll() is None:
                self.terminate_process_tree(proc, timeout=10)

    def reap_zombies(self) -> int:
        """
        Reap any zombie child processes.

        Call this periodically to clean up defunct processes.

        Returns:
            Number of zombies reaped
        """
        reaped = 0
        try:
            while True:
                pid, status = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
                reaped += 1
                self._unregister_process(pid)
                logger.debug(f"Reaped zombie process {pid}")
        except ChildProcessError:
            pass  # No children
        return reaped

    def cleanup_all(self) -> int:
        """
        Terminate all tracked processes.

        Call this on shutdown to ensure clean exit.

        Returns:
            Number of processes terminated
        """
        terminated = 0
        with self._get_lock():
            pids = list(self._active_processes.keys())

        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                terminated += 1
            except ProcessLookupError:
                pass
            except PermissionError:
                try:
                    os.kill(pid, signal.SIGKILL)
                    terminated += 1
                except:
                    pass

        # Reap zombies
        time.sleep(0.5)
        self.reap_zombies()

        logger.info(f"Cleaned up {terminated} active processes")
        return terminated

    def get_active_count(self) -> int:
        """Get count of active tracked processes."""
        with self._get_lock():
            return len(self._active_processes)


# Module-level singleton
_manager: Optional[SubprocessManager] = None


def get_manager() -> SubprocessManager:
    """Get the global subprocess manager singleton."""
    global _manager
    if _manager is None:
        _manager = SubprocessManager()
    return _manager


if __name__ == "__main__":
    import sys

    manager = SubprocessManager()

    # Test basic command
    print("Testing basic command...")
    result = manager.run_command(['echo', 'hello'])
    print(f"Output: {result.stdout.strip()}")

    # Test timeout
    print("\nTesting timeout...")
    try:
        manager.run_command(['sleep', '10'], timeout=1)
        print("ERROR: Should have timed out")
    except TimeoutError:
        print("Timeout worked correctly")

    # Test managed process
    print("\nTesting managed process...")
    with manager.managed_process(['python3', '-c', 'import time; time.sleep(0.1); print("done")']) as proc:
        stdout, stderr = proc.communicate(timeout=5)
        print(f"Output: {stdout.strip()}")

    print("\nAll tests passed!")
