"""
Agent Gemini with Full Direct Access
Option 3: Agents can read/write/execute anywhere on the system
"""

import os
import subprocess
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

class AgentDirectAccess:
    """
    Gives agents full direct access to the file system.
    Agents can read, write, edit, and execute commands anywhere.
    """
    
    def __init__(self, agent_name: str, home_dir: str = os.path.expanduser("~")):
        self.agent_name = agent_name
        self.home_dir = Path(home_dir)
        self.execution_log: List[Dict] = []
        
    def read_file(self, filepath: str) -> str:
        """Read any file on the system."""
        # Expand ~ to home directory
        if filepath.startswith("~"):
            filepath = str(self.home_dir) + filepath[1:]
        
        full_path = Path(filepath).expanduser().resolve()
        
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            self._log_action("read", str(full_path), True)
            return content
        except Exception as e:
            self._log_action("read", str(full_path), False, str(e))
            return f"ERROR: {str(e)}"
    
    def write_file(self, filepath: str, content: str) -> str:
        """Write to any file on the system."""
        if filepath.startswith("~"):
            filepath = str(self.home_dir) + filepath[1:]
        
        full_path = Path(filepath).expanduser().resolve()
        
        try:
            # Create parent directories if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self._log_action("write", str(full_path), True)
            return f"✅ Written: {filepath} ({len(content)} chars)"
        except Exception as e:
            self._log_action("write", str(full_path), False, str(e))
            return f"❌ Error writing {filepath}: {str(e)}"
    
    def edit_file(self, filepath: str, old_string: str, new_string: str) -> str:
        """Edit any file on the system (precise replacement)."""
        if filepath.startswith("~"):
            filepath = str(self.home_dir) + filepath[1:]
        
        full_path = Path(filepath).expanduser().resolve()
        
        try:
            content = self.read_file(filepath)
            if content.startswith("ERROR:"):
                return content
            
            if old_string not in content:
                return f"❌ Could not find text to replace in {filepath}"
            
            new_content = content.replace(old_string, new_string, 1)
            
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            self._log_action("edit", str(full_path), True)
            return f"✅ Edited: {filepath}"
        except Exception as e:
            self._log_action("edit", str(full_path), False, str(e))
            return f"❌ Error editing {filepath}: {str(e)}"
    
    def list_directory(self, dirpath: str = ".") -> str:
        """List files in any directory."""
        if dirpath.startswith("~"):
            dirpath = str(self.home_dir) + dirpath[1:]
        
        full_path = Path(dirpath).expanduser().resolve()
        
        try:
            items = []
            for item in full_path.iterdir():
                item_type = "📁" if item.is_dir() else "📄"
                size = item.stat().st_size if item.is_file() else "-"
                items.append(f"{item_type} {item.name:<40} {size}")
            
            self._log_action("list", str(full_path), True)
            return "\n".join(sorted(items)) if items else "(empty directory)"
        except Exception as e:
            self._log_action("list", str(full_path), False, str(e))
            return f"ERROR: {str(e)}"
    
    def execute(self, command: str, timeout: int = 60, cwd: Optional[str] = None) -> str:
        """Execute any shell command."""
        if cwd and cwd.startswith("~"):
            cwd = str(self.home_dir) + cwd[1:]
        
        working_dir = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir
            )
            
            output = result.stdout if result.returncode == 0 else result.stderr
            status = "✅" if result.returncode == 0 else "❌"
            
            self._log_action("execute", command, result.returncode == 0)
            
            return f"{status} Command: {command}\nExit code: {result.returncode}\n\nOutput:\n{output[:2000]}"
        except subprocess.TimeoutExpired:
            self._log_action("execute", command, False, "timeout")
            return f"⏱️ Timeout after {timeout}s: {command}"
        except Exception as e:
            self._log_action("execute", command, False, str(e))
            return f"❌ Error: {str(e)}"
    
    def git_status(self, repo_path: str = ".") -> str:
        """Check git status of a repository."""
        return self.execute("git status", cwd=repo_path)
    
    def git_commit(self, message: str, repo_path: str = ".") -> str:
        """Create a git commit."""
        self.execute("git add -A", cwd=repo_path)
        return self.execute(f'git commit -m "{message}"', cwd=repo_path)
    
    def search_files(self, pattern: str, dirpath: str = ".") -> str:
        """Search for files containing pattern."""
        if dirpath.startswith("~"):
            dirpath = str(self.home_dir) + dirpath[1:]
        
        full_path = Path(dirpath).expanduser().resolve()
        
        results = []
        try:
            for root, dirs, files in os.walk(full_path):
                # Skip common non-code directories
                dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', '__pycache__', '.venv', 'venv']]
                
                for file in files:
                    if file.endswith(('.py', '.js', '.ts', '.tsx', '.json', '.md', '.yml', '.yaml')):
                        filepath = Path(root) / file
                        try:
                            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                                if pattern in content:
                                    # Find line numbers
                                    lines = content.split('\n')
                                    for i, line in enumerate(lines, 1):
                                        if pattern in line:
                                            results.append(f"{filepath}:{i}: {line.strip()}")
                                            break  # Just first occurrence per file
                        except:
                            continue
                        
                        if len(results) >= 20:  # Limit results
                            break
                
                if len(results) >= 20:
                    break
            
            return "\n".join(results) if results else f"No files found containing: {pattern}"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def _log_action(self, action: str, target: str, success: bool, error: str = None):
        """Log all actions for audit trail."""
        from datetime import datetime
        self.execution_log.append({
            "timestamp": datetime.now().isoformat(),
            "agent": self.agent_name,
            "action": action,
            "target": target,
            "success": success,
            "error": error
        })
    
    def get_execution_log(self) -> List[Dict]:
        """Get log of all actions performed."""
        return self.execution_log
    
    def to_prompt_tools(self) -> str:
        """Generate tool documentation for agent prompts."""
        return """
AVAILABLE TOOLS - You have FULL DIRECT ACCESS to the system:

read_file(path)
  Read any file on the system
  Example: read_file("~/projects/myapp/main.py")

write_file(path, content)
  Write/create any file
  Example: write_file("~/projects/myapp/new.py", "print('hello')")

edit_file(path, old_string, new_string)
  Precisely edit a file (replaces first occurrence)
  Example: edit_file("main.py", "old_func()", "new_func()")

list_directory(path=".")
  List files in any directory
  Example: list_directory("~/projects")

execute(command, timeout=60, cwd=None)
  Execute any shell command
  Example: execute("ls -la", cwd="~/projects")
  Example: execute("python test.py")
  Example: execute("npm install", cwd="~/frontend")

git_status(repo_path=".")
  Check git status
  
git_commit(message, repo_path=".")
  Create a git commit

search_files(pattern, dirpath=".")
  Search for pattern in files
  Example: search_files("def main", "~/projects")

IMPORTANT:
- You can access ANY file on the system
- You can write to ANY location
- You can execute ANY command
- Be careful with destructive operations
- Always verify before overwriting important files

TO USE TOOLS:
Simply state what you want to do naturally, like:
"I'll read the current file first..." or
"Let me execute the test suite..."

The system will automatically detect and execute your tool usage.
"""


class AgentGeminiDirect:
    """
    Gemini CLI agent with full direct system access.
    Agents can read, write, edit, and execute anywhere.
    """
    
    def __init__(self, agent_name: str, model: str = "gemini-3.1-pro-preview"):
        self.agent_name = agent_name
        self.model = model
        self.access = AgentDirectAccess(agent_name)
        
        # Load Gemini config
        self.gemini_home = os.path.expanduser(f"~/.gemini-{agent_name.lower()}")
        if not os.path.exists(self.gemini_home):
            self.gemini_home = os.path.expanduser("~/.gemini")
    
    def query(self, prompt: str, context: str = "") -> Dict[str, Any]:
        """
        Send query to Gemini with full tool access.
        Automatically detects and executes tool calls in the response.
        """
        # Build full prompt with tools
        full_prompt = f"""You are {self.agent_name}, an AI agent with FULL DIRECT ACCESS to the file system.

{self.access.to_prompt_tools()}

CURRENT CONTEXT:
{context}

YOUR TASK:
{prompt}

Remember: You can read, write, edit, and execute anywhere on the system.
Be proactive. If you need to see a file, read it. If you need to test code, execute it.
"""
        
        # Call Gemini CLI
        import subprocess
        import json
        
        try:
            result = subprocess.run(
                ["gemini", "--model", self.model, "-p", full_prompt],
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "GEMINI_HOME": self.gemini_home}
            )
            
            response = result.stdout if result.returncode == 0 else result.stderr
            
            # Parse and execute any tool calls in the response
            executed_tools = self._parse_and_execute_tools(response)
            
            # If tools were executed, get follow-up response
            if executed_tools:
                follow_up = f"\n\n[Tool Execution Results]:\n" + "\n".join(executed_tools)
                response += follow_up
            
            return {
                "response": response,
                "tools_executed": executed_tools,
                "execution_log": self.access.get_execution_log(),
                "agent": self.agent_name
            }
            
        except Exception as e:
            return {
                "response": f"Error: {str(e)}",
                "tools_executed": [],
                "execution_log": self.access.get_execution_log(),
                "agent": self.agent_name
            }
    
    def _parse_and_execute_tools(self, response: str) -> List[str]:
        """Parse response for tool calls and execute them."""
        results = []
        
        # Simple pattern matching for tool calls
        # This is a basic implementation - could be made more sophisticated
        
        # Check for explicit tool calls
        if "read_file(" in response or "I'll read" in response.lower():
            # Extract file path and read
            import re
            matches = re.findall(r'read_file\(["\']([^"\']+)["\']\)', response)
            for filepath in matches[:3]:  # Limit to 3 reads per response
                content = self.access.read_file(filepath)
                results.append(f"📖 Read {filepath}: {len(content)} chars")
        
        if "execute(" in response or "run:" in response.lower():
            matches = re.findall(r'execute\(["\']([^"\']+)["\']\)', response)
            for command in matches[:2]:  # Limit to 2 commands
                result = self.access.execute(command)
                results.append(f"⚡ Executed: {command}")
        
        return results


# Convenience functions for creating agents
def kublai_gemini_direct():
    """Create Kublai agent with full direct access."""
    return AgentGeminiDirect("kublai")

def temujin_gemini_direct():
    """Create Temujin agent with full direct access."""
    return AgentGeminiDirect("temujin")

def mongke_gemini_direct():
    """Create Möngke agent with full direct access."""
    return AgentGeminiDirect("mongke")

def chagatai_gemini_direct():
    """Create Chagatai agent with full direct access."""
    return AgentGeminiDirect("chagatai")

def jochi_gemini_direct():
    """Create Jochi agent with full direct access."""
    return AgentGeminiDirect("jochi")

def ogedei_gemini_direct():
    """Create Ögedei agent with full direct access."""
    return AgentGeminiDirect("ogedei")


if __name__ == "__main__":
    # Test the direct access
    print("Testing Agent Direct Access...")
    
    access = AgentDirectAccess("test")
    
    # Test read
    print("\n1. Reading file:")
    content = access.read_file("~/projects/llm_survivor/README.md")
    print(content[:200] if not content.startswith("ERROR") else content)
    
    # Test list
    print("\n2. Listing directory:")
    files = access.list_directory("~/projects/llm_survivor")
    print(files[:500])
    
    # Test execute
    print("\n3. Executing command:")
    result = access.execute("pwd")
    print(result)
    
    print("\n✅ Agent Direct Access is working!")
