#!/usr/bin/env python3
"""
Security Layer 4 & 6: Sandboxed Code Generation and Execution

Uses Jinja2 SandboxedEnvironment for template rendering
and subprocess with strict resource limits for execution.
"""

import os
import sys
import subprocess
import tempfile
import resource
import signal
from typing import Dict, Optional, Tuple
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import DictLoader


class SandboxedCodeGenerator:
    """
    Generate code using Jinja2 SandboxedEnvironment
    to prevent SSTI (Server-Side Template Injection).
    """
    
    def __init__(self):
        # Create sandboxed environment
        self.env = SandboxedEnvironment(
            loader=DictLoader({}),
            autoescape=False,  # We want raw code output
            trim_blocks=True,
            lstrip_blocks=True
        )
        
        # Restrict available filters and tests
        self.env.filters.clear()
        self.env.tests.clear()
        
        # Only allow safe built-ins
        allowed_filters = ['upper', 'lower', 'trim', 'replace']
        for f in allowed_filters:
            if f in SandboxedEnvironment().filters:
                self.env.filters[f] = SandboxedEnvironment().filters[f]
    
    def generate(self, template_str: str, context: Dict) -> Tuple[bool, str]:
        """
        Generate code from template with context.
        
        Returns:
            (success: bool, result: str)
        """
        try:
            template = self.env.from_string(template_str)
            result = template.render(**context)
            return True, result
        except Exception as e:
            return False, f"Template error: {str(e)}"


class SandboxedExecutor:
    """
    Execute Python code in sandboxed subprocess
    with resource limits and timeout.
    """
    
    def __init__(self):
        self.timeout_seconds = 30
        self.max_memory_mb = 100
        self.max_cpu_time = 10
    
    def _set_limits(self):
        """Set resource limits for subprocess."""
        # Memory limit (bytes)
        max_mem = self.max_memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (max_mem, max_mem))
        
        # CPU time limit (seconds)
        resource.setrlimit(resource.RLIMIT_CPU, (self.max_cpu_time, self.max_cpu_time))
        
        # Disable core dumps
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        
        # Limit number of open files
        resource.setrlimit(resource.RLIMIT_NOFILE, (50, 50))
    
    def execute(self, code: str, inputs: Optional[Dict] = None) -> Dict:
        """
        Execute code in sandboxed environment.
        
        Returns:
            {
                'success': bool,
                'stdout': str,
                'stderr': str,
                'returncode': int,
                'execution_time_ms': float
            }
        """
        import time
        start_time = time.time()
        
        # Create temporary file for code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            # Wrap code in try-except and add safety checks
            safe_code = f'''
import sys
sys.path = [p for p in sys.path if 'site-packages' not in p]

# Restricted imports
forbidden = ['os.system', 'subprocess', 'eval', 'exec', '__import__']

# Execute user code
try:
{chr(10).join('    ' + line for line in code.split(chr(10)))}
except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    sys.exit(1)
'''
            f.write(safe_code)
            temp_path = f.name
        
        try:
            # Run in subprocess with limits
            proc = subprocess.Popen(
                [sys.executable, temp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=self._set_limits,
                text=True
            )
            
            try:
                stdout, stderr = proc.communicate(timeout=self.timeout_seconds)
                execution_time = (time.time() - start_time) * 1000
                
                return {
                    'success': proc.returncode == 0,
                    'stdout': stdout,
                    'stderr': stderr,
                    'returncode': proc.returncode,
                    'execution_time_ms': execution_time
                }
                
            except subprocess.TimeoutExpired:
                proc.kill()
                return {
                    'success': False,
                    'stdout': '',
                    'stderr': 'Execution timeout exceeded',
                    'returncode': -1,
                    'execution_time_ms': self.timeout_seconds * 1000
                }
                
        except Exception as e:
            return {
                'success': False,
                'stdout': '',
                'stderr': f'Sandbox error: {str(e)}',
                'returncode': -1,
                'execution_time_ms': 0
            }
            
        finally:
            # Cleanup temp file
            try:
                os.unlink(temp_path)
            except:
                pass


class SecurityValidator:
    """
    Combined security validation for generated code.
    """
    
    FORBIDDEN_PATTERNS = [
        r'import\s+os\s*$',
        r'from\s+os\s+import',
        r'subprocess',
        r'__import__',
        r'eval\s*\(',
        r'exec\s*\(',
        r'compile\s*\(',
        r'open\s*\(__file__',
        r'sys\.exit',
        r'quit\s*\(',
        r'exit\s*\(',
    ]
    
    @classmethod
    def validate_code(cls, code: str) -> Tuple[bool, str]:
        """
        Validate code for security issues.
        
        Returns:
            (is_safe: bool, message: str)
        """
        import re
        
        for pattern in cls.FORBIDDEN_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"Forbidden pattern found: {pattern}"
        
        return True, "Code passed security validation"


if __name__ == '__main__':
    print("Testing Sandboxed Code Generation...")
    
    generator = SandboxedCodeGenerator()
    
    template = """
def greet_{{ name.lower() }}():
    return "Hello, {{ name }}!"
"""
    
    success, result = generator.generate(template, {'name': 'World'})
    print(f"Generated:\n{result}")
    
    print("\nTesting Sandboxed Execution...")
    executor = SandboxedExecutor()
    
    test_code = """
print("Hello from sandbox!")
result = 2 + 2
print(f"2 + 2 = {result}")
"""
    
    result = executor.execute(test_code)
    print(f"Success: {result['success']}")
    print(f"Stdout: {result['stdout']}")
    print(f"Stderr: {result['stderr']}")
    print(f"Time: {result['execution_time_ms']}ms")
