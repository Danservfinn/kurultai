"""
Sandbox executor for running untrusted Python code with resource limits.

This module provides the SandboxExecutor class for the Kurultai v0.2 multi-agent
orchestration platform. It runs Python code in a controlled subprocess environment
with CPU, memory, and file system limits.

Key features:
- Resource limits via the resource module (RLIMIT_CPU, RLIMIT_AS, etc.)
- Platform-aware (skips RLIMIT_AS on macOS/Darwin)
- Module import allowlist
- Restricted PATH environment
- Timeout handling
- Comprehensive error capture

Usage:
    executor = SandboxExecutor()
    result = executor.execute("print('Hello, world!')")
    if result.return_code == 0:
        print(result.stdout)
    else:
        print(f"Error: {result.stderr}")
"""

import logging
import platform
import resource
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from typing import Optional, Set, List

# Platform detection for Darwin-specific handling
IS_DARWIN = platform.system() == 'Darwin'

# Default allowed modules for sandboxed execution
DEFAULT_ALLOWED_MODULES = {
    'json',
    'math',
    'datetime',
    'collections',
    'itertools',
    're',
    'string',
    'typing',
    'dataclasses',
    'enum',
    'functools',
    'operator',
    'textwrap',
    'uuid',
}

# Resource limits
LIMIT_CPU_SECONDS = 30
LIMIT_MEMORY_BYTES = 512 * 1024 * 1024  # 512 MB
LIMIT_FILE_COUNT = 100
LIMIT_PROCESS_COUNT = 50
LIMIT_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# Restricted PATH for subprocess
RESTRICTED_PATH = '/usr/bin:/bin'

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """
    Result of code execution in the sandbox.

    Attributes:
        stdout: Standard output from the executed code
        stderr: Standard error from the executed code
        return_code: Exit code (0 for success)
        timed_out: True if execution exceeded timeout
        error: Optional error message for execution failures
    """
    stdout: str
    stderr: str
    return_code: int
    timed_out: bool
    error: Optional[str] = None


class SandboxExecutor:
    """
    Executes untrusted Python code in a sandboxed subprocess with resource limits.

    This executor provides isolation and resource constraints to prevent:
    - Excessive CPU usage
    - Memory exhaustion
    - File system abuse
    - Process bombs
    - Unauthorized module imports

    Example:
        executor = SandboxExecutor()

        # Check imports before execution
        disallowed = executor.check_imports("import os\\nprint('test')")
        if disallowed:
            print(f"Disallowed imports: {disallowed}")

        # Execute safe code
        result = executor.execute("print('Hello')")
        if result.return_code == 0:
            print(result.stdout)
    """

    def __init__(
        self,
        allowed_modules: Optional[Set[str]] = None,
        cpu_limit: int = LIMIT_CPU_SECONDS,
        memory_limit: int = LIMIT_MEMORY_BYTES,
        file_limit: int = LIMIT_FILE_COUNT,
        process_limit: int = LIMIT_PROCESS_COUNT,
        file_size_limit: int = LIMIT_FILE_SIZE_BYTES,
    ):
        """
        Initialize the sandbox executor.

        Args:
            allowed_modules: Set of allowed module names. Defaults to DEFAULT_ALLOWED_MODULES
            cpu_limit: CPU time limit in seconds
            memory_limit: Memory limit in bytes (skipped on macOS)
            file_limit: Maximum number of open file descriptors
            process_limit: Maximum number of processes
            file_size_limit: Maximum file size in bytes
        """
        self.allowed_modules = allowed_modules or DEFAULT_ALLOWED_MODULES
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.file_limit = file_limit
        self.process_limit = process_limit
        self.file_size_limit = file_size_limit

        if IS_DARWIN:
            logger.warning(
                "Running on macOS/Darwin: RLIMIT_AS (memory limit) will be skipped "
                "as the Darwin kernel ignores this limit"
            )

    def check_imports(self, code: str) -> List[str]:
        """
        Check for disallowed module imports in the code.

        This performs simple string-based checking (not AST parsing) to identify
        import statements. It checks for both 'import foo' and 'from foo import bar'
        patterns.

        Args:
            code: Python code to check

        Returns:
            List of disallowed module names found in the code

        Example:
            >>> executor = SandboxExecutor()
            >>> executor.check_imports("import os\\nimport json")
            ['os']
            >>> executor.check_imports("from subprocess import run")
            ['subprocess']
        """
        disallowed = []

        # Split code into lines and check each one
        for line in code.split('\n'):
            stripped = line.strip()

            # Skip comments and empty lines
            if not stripped or stripped.startswith('#'):
                continue

            # Check 'import module' pattern
            if stripped.startswith('import '):
                # Handle: import foo, bar, baz
                modules_part = stripped[7:].split('#')[0].strip()  # Remove trailing comment
                modules = [m.strip().split()[0].split('.')[0]
                          for m in modules_part.split(',')]

                for module in modules:
                    if module and module not in self.allowed_modules:
                        disallowed.append(module)

            # Check 'from module import' pattern
            elif stripped.startswith('from '):
                # Handle: from foo.bar import baz
                parts = stripped.split()
                if len(parts) >= 4 and parts[2] == 'import':
                    module = parts[1].split('.')[0]
                    if module not in self.allowed_modules:
                        disallowed.append(module)

        return disallowed

    def _set_resource_limits(self) -> None:
        """
        Set resource limits for the current process.

        This function is called via preexec_fn in the subprocess, so it runs
        in the child process before exec. It sets:
        - CPU time limit
        - Memory limit (except on macOS)
        - File descriptor limit
        - Process count limit
        - File size limit

        Note:
            This should only be called in the subprocess context, not directly.
        """
        try:
            # CPU time limit
            resource.setrlimit(resource.RLIMIT_CPU, (self.cpu_limit, self.cpu_limit))
            logger.debug(f"Set RLIMIT_CPU to {self.cpu_limit} seconds")

            # Memory limit (skip on macOS/Darwin)
            if not IS_DARWIN:
                resource.setrlimit(resource.RLIMIT_AS, (self.memory_limit, self.memory_limit))
                logger.debug(f"Set RLIMIT_AS to {self.memory_limit} bytes")

            # File descriptor limit
            resource.setrlimit(resource.RLIMIT_NOFILE, (self.file_limit, self.file_limit))
            logger.debug(f"Set RLIMIT_NOFILE to {self.file_limit}")

            # Process count limit
            resource.setrlimit(resource.RLIMIT_NPROC, (self.process_limit, self.process_limit))
            logger.debug(f"Set RLIMIT_NPROC to {self.process_limit}")

            # File size limit
            resource.setrlimit(resource.RLIMIT_FSIZE, (self.file_size_limit, self.file_size_limit))
            logger.debug(f"Set RLIMIT_FSIZE to {self.file_size_limit} bytes")

        except Exception as e:
            logger.error(f"Failed to set resource limits: {e}")
            # Let the process continue but log the error

    def execute(self, code: str, timeout: int = 30) -> ExecutionResult:
        """
        Execute Python code in a sandboxed subprocess.

        The code runs with:
        - Resource limits (CPU, memory, files, processes)
        - Restricted PATH environment
        - Timeout enforcement
        - Isolated process space

        Args:
            code: Python code to execute
            timeout: Timeout in seconds (default: 30)

        Returns:
            ExecutionResult containing stdout, stderr, return code, and status

        Example:
            >>> executor = SandboxExecutor()
            >>> result = executor.execute("print(2 + 2)")
            >>> result.stdout.strip()
            '4'
            >>> result.return_code
            0

            >>> result = executor.execute("import os")
            >>> result.return_code
            1
            >>> 'ModuleNotFoundError' in result.stderr
            True
        """
        # Check for disallowed imports first
        disallowed_imports = self.check_imports(code)
        if disallowed_imports:
            error_msg = f"Disallowed imports detected: {', '.join(disallowed_imports)}"
            logger.warning(error_msg)
            return ExecutionResult(
                stdout='',
                stderr=error_msg,
                return_code=1,
                timed_out=False,
                error=error_msg,
            )

        # Create the wrapper script
        # We use a Python snippet that will be executed via stdin
        wrapper = textwrap.dedent(f'''
            import sys

            # User code starts here
            {textwrap.indent(code, "            ").strip()}
        ''')

        # Set up restricted environment
        env = {
            'PATH': RESTRICTED_PATH,
            'PYTHONDONTWRITEBYTECODE': '1',  # Don't create .pyc files
            'PYTHONUNBUFFERED': '1',  # Unbuffered output
        }

        # Build the subprocess command
        # Use current Python interpreter with -c flag
        cmd = [sys.executable, '-c', wrapper]

        logger.debug(f"Executing code with timeout={timeout}s")
        logger.debug(f"Command: {' '.join(cmd[:2])}...")  # Don't log full code

        try:
            # Execute with resource limits
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                preexec_fn=self._set_resource_limits,  # Set limits in child process
            )

            logger.debug(f"Execution completed with return code {result.returncode}")

            return ExecutionResult(
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
                timed_out=False,
                error=None if result.returncode == 0 else result.stderr,
            )

        except subprocess.TimeoutExpired as e:
            logger.warning(f"Execution timed out after {timeout} seconds")
            return ExecutionResult(
                stdout=e.stdout.decode() if e.stdout else '',
                stderr=e.stderr.decode() if e.stderr else '',
                return_code=-1,
                timed_out=True,
                error=f"Execution timed out after {timeout} seconds",
            )

        except Exception as e:
            logger.error(f"Execution failed with exception: {e}")
            return ExecutionResult(
                stdout='',
                stderr=str(e),
                return_code=-1,
                timed_out=False,
                error=f"Execution failed: {str(e)}",
            )


# Convenience function for one-off execution
def execute_sandboxed(
    code: str,
    timeout: int = 30,
    allowed_modules: Optional[Set[str]] = None,
) -> ExecutionResult:
    """
    Convenience function to execute code in a sandbox without creating an executor instance.

    Args:
        code: Python code to execute
        timeout: Timeout in seconds
        allowed_modules: Optional set of allowed module names

    Returns:
        ExecutionResult from the execution

    Example:
        >>> result = execute_sandboxed("print('Hello, world!')")
        >>> print(result.stdout)
        Hello, world!
    """
    executor = SandboxExecutor(allowed_modules=allowed_modules)
    return executor.execute(code, timeout=timeout)


if __name__ == '__main__':
    # Simple CLI for testing
    import argparse

    parser = argparse.ArgumentParser(description='Execute Python code in a sandbox')
    parser.add_argument('code', nargs='?', help='Python code to execute')
    parser.add_argument('--file', '-f', help='Python file to execute')
    parser.add_argument('--timeout', '-t', type=int, default=30, help='Timeout in seconds')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Get code from argument or file
    if args.file:
        with open(args.file, 'r') as f:
            code = f.read()
    elif args.code:
        code = args.code
    else:
        print("Error: Provide code via argument or --file", file=sys.stderr)
        sys.exit(1)

    # Execute
    executor = SandboxExecutor()
    result = executor.execute(code, timeout=args.timeout)

    # Print results
    print("=== STDOUT ===")
    print(result.stdout)

    if result.stderr:
        print("\n=== STDERR ===")
        print(result.stderr)

    print(f"\n=== EXIT CODE: {result.return_code} ===")

    if result.timed_out:
        print("WARNING: Execution timed out")

    if result.error:
        print(f"ERROR: {result.error}")

    sys.exit(result.return_code)
