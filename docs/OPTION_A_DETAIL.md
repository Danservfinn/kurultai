# Option A: Quick & Dirty Agent Workspace Implementation

## Overview

A minimal implementation that adds file-writing capabilities to Gemini CLI agents without major infrastructure changes. Can be implemented in 1-2 hours and immediately improves agent usefulness.

---

## How It Works

### The Core Idea

Instead of agents just returning text, they return **structured output** that includes file operations. The system parses this output and executes the operations automatically.

```
Agent Response → Parse for FILE_WRITE markers → Execute writes → Confirm completion
```

### Example Flow

**Before (Current):**
```
Me: "Write a database.py file"
Temujin: "Here's the code: [code block]"
Me: [manually copy code, create file, paste]
```

**After (With Option A):**
```
Me: "Write a database.py file"
Temujin: "FILE_WRITE:backend/database.py
           ```python
           import sqlite3
           ...
           ```
           File written successfully!"
System: [automatically creates the file]
Me: "✅ File created"
```

---

## Implementation Details

### Step 1: Modify Agent Prompt Template

Add "available tools" to every agent prompt:

```python
AGENT_PROMPT_TEMPLATE = """
You are {agent_name}, a specialized AI agent.

AVAILABLE TOOLS:
When you need to create or modify files, use these markers:

FILE_WRITE:path/to/file.py
```python
# Your code here
```

FILE_APPEND:path/to/file.py
```python
# Code to append
```

FILE_READ:path/to/file.py
# I will return the file contents

EXECUTE:command
# I will run the command and return output

WORKSPACE_LIST:
# I will list all files in the workspace

WORKSPACE_STATUS:
# Show current workspace state

RULES:
1. Use FILE_WRITE for new files
2. Use FILE_APPEND for adding to existing files
3. Always use relative paths from workspace root
4. Include complete, working code
5. Verify your code with EXECUTE when possible

CURRENT TASK: {task}
WORKSPACE: {workspace_path}

{context}

Proceed with the task.
"""
```

### Step 2: Create Response Parser

```python
import re
import os
from pathlib import Path

class AgentWorkspace:
    def __init__(self, agent_name, base_path="/tmp/agent_workspaces"):
        self.path = Path(base_path) / agent_name
        self.path.mkdir(parents=True, exist_ok=True)
        self.agent_name = agent_name
    
    def parse_and_execute(self, agent_response):
        """Parse agent response and execute file operations."""
        results = []
        
        # Parse FILE_WRITE operations
        write_pattern = r'FILE_WRITE:(\S+)\n```(?:\w+)?\n(.*?)```'
        for match in re.finditer(write_pattern, agent_response, re.DOTALL):
            filepath = match.group(1)
            content = match.group(2)
            result = self.write_file(filepath, content)
            results.append(result)
        
        # Parse FILE_APPEND operations
        append_pattern = r'FILE_APPEND:(\S+)\n```(?:\w+)?\n(.*?)```'
        for match in re.finditer(append_pattern, agent_response, re.DOTALL):
            filepath = match.group(1)
            content = match.group(2)
            result = self.append_file(filepath, content)
            results.append(result)
        
        # Parse FILE_READ requests
        read_pattern = r'FILE_READ:(\S+)'
        for match in re.finditer(read_pattern, agent_response):
            filepath = match.group(1)
            content = self.read_file(filepath)
            # Replace the marker with actual content in response
            agent_response = agent_response.replace(
                f"FILE_READ:{filepath}",
                f"FILE_READ:{filepath}\n```\n{content}\n```"
            )
        
        # Parse EXECUTE requests
        exec_pattern = r'EXECUTE:(.+?)(?:\n|$)'
        for match in re.finditer(exec_pattern, agent_response):
            command = match.group(1).strip()
            result = self.execute(command)
            results.append(result)
        
        return results, agent_response
    
    def write_file(self, filepath, content):
        """Write content to file in workspace."""
        full_path = self.path / filepath
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(full_path, 'w') as f:
            f.write(content)
        
        return f"✅ Wrote {filepath} ({len(content)} chars)"
    
    def append_file(self, filepath, content):
        """Append content to file in workspace."""
        full_path = self.path / filepath
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(full_path, 'a') as f:
            f.write(content)
        
        return f"✅ Appended to {filepath} ({len(content)} chars)"
    
    def read_file(self, filepath):
        """Read file from workspace."""
        full_path = self.path / filepath
        if not full_path.exists():
            return f"❌ File not found: {filepath}"
        
        with open(full_path, 'r') as f:
            return f.read()
    
    def execute(self, command, timeout=30):
        """Execute command in workspace."""
        import subprocess
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.path
            )
            
            output = result.stdout if result.returncode == 0 else result.stderr
            status = "✅" if result.returncode == 0 else "❌"
            
            return f"{status} EXECUTE: {command}\n{output[:500]}"
        except subprocess.TimeoutExpired:
            return f"⏱️ EXECUTE: {command} (timeout after {timeout}s)"
        except Exception as e:
            return f"❌ EXECUTE: {command}\nError: {str(e)}"
    
    def list_files(self):
        """List all files in workspace."""
        files = []
        for root, dirs, filenames in os.walk(self.path):
            for filename in filenames:
                filepath = Path(root) / filename
                rel_path = filepath.relative_to(self.path)
                size = filepath.stat().st_size
                files.append(f"{rel_path} ({size} bytes)")
        return "\n".join(files) if files else "(empty workspace)"
```

### Step 3: Modify Agent Calling Code

```python
# Current approach (agent_gemini.py)
class AgentGemini:
    def query(self, prompt):
        # Just returns text
        return gemini.query(prompt)

# New approach with workspace
class AgentGemini:
    def __init__(self, agent_name):
        self.agent_name = agent_name
        self.workspace = AgentWorkspace(agent_name)
    
    def query(self, task, context=""):
        # Build prompt with tools
        prompt = AGENT_PROMPT_TEMPLATE.format(
            agent_name=self.agent_name,
            task=task,
            workspace_path=str(self.workspace.path),
            context=context
        )
        
        # Get agent response
        response = gemini.query(prompt)
        
        # Parse and execute file operations
        results, updated_response = self.workspace.parse_and_execute(response)
        
        # Return results to caller
        return {
            "response": updated_response,
            "operations": results,
            "workspace": str(self.workspace.path)
        }
```

### Step 4: Update Usage Pattern

```python
# Before (current)
temujin = temujin_gemini()
response = temujin.query("Create database.py")
# Response is just text, I have to manually create the file

# After (with Option A)
temujin = temujin_gemini()  # Now returns AgentGemini with workspace
result = temujin.query("Create database.py with SQLite schema")

# Files are automatically created!
print(result["operations"])
# ["✅ Wrote database.py (1500 chars)"]

# Access created files
print(result["workspace"])
# /tmp/agent_workspaces/temujin/

# Copy to actual project
import shutil
shutil.copy(
    f"{result['workspace']}/database.py",
    "/actual/project/path/database.py"
)
```

---

## Workflow Example

### Building LLM Survivor Backend

```python
# 1. Initialize agent
from tools.kurultai.agent_gemini import temujin_gemini
temujin = temujin_gemini()

# 2. Create database layer
result = temujin.query("""
Create a complete database.py with:
- SQLite connection
- GameState model
- Agent model
- Message model
- All CRUD operations
""")
# Files automatically created in /tmp/agent_workspaces/temujin/

# 3. Create API layer
result = temujin.query("""
Create api.py with FastAPI routes:
- GET /api/state - Get game state
- POST /api/message - Send message
- GET /api/agents - List agents
Use the database.py I just created.
""")

# 4. Test it
result = temujin.query("""
EXECUTE: python -c "import database; print('OK')"
""")

# 5. Copy to actual project
import shutil
src = "/tmp/agent_workspaces/temujin/"
dst = "~/projects/llm_survivor/backend/"
for file in ["database.py", "api.py"]:
    shutil.copy(f"{src}/{file}", f"{dst}/{file}")
```

---

## Advantages

### ✅ **Quick to Implement** (1-2 hours)
- No new infrastructure
- No Redis, no queues
- Just parse text and write files

### ✅ **Immediately Useful**
- Agents can actually create files
- Can test code immediately
- Reduces manual copy-paste

### ✅ **Safe**
- Files go to isolated workspace first
- Human reviews before copying to project
- No direct writes to production code

### ✅ **Familiar**
- Same agent calling pattern
- Just enhanced response
- Easy to understand

---

## Limitations

### ⚠️ **Not True Autonomy**
- Still requires human to trigger calls
- Still requires human to copy files to project
- No background execution

### ⚠️ **Parsing Can Be Fragile**
- Relies on regex patterns
- Agents might not follow format
- Need retry logic

### ⚠️ **No Persistence**
- Workspace is temporary
- No memory between calls
- Must reload context each time

### ⚠️ **Single-Threaded**
- One agent at a time
- No parallel execution
- Blocking calls

---

## Files to Modify

1. **`tools/kurultai/agent_gemini.py`**
   - Add AgentWorkspace class
   - Modify AgentGemini to use workspace
   - Update query() method

2. **`tools/kurultai/agent_gemini.py`** (or new file)
   - Add AGENT_PROMPT_TEMPLATE
   - Add parsing functions

3. **Test file**
   - Create test_agent_workspace.py
   - Verify file operations work

---

## Next Steps After Option A

Once this works, you can incrementally add:

1. **Option A+**: Persistent workspace (save to disk)
2. **Option A++**: Neo4j memory (context between calls)
3. **Option B**: Full background workers (Redis queue)

But Option A alone provides 80% of the value with 20% of the effort.

---

## Summary

**Option A = Parseable output + Auto-execution**

- Agents use markers like `FILE_WRITE:path`
- System parses response automatically
- Files created in isolated workspace
- Human reviews before moving to project

**Time:** 1-2 hours  
**Value:** High (agents can actually write files)  
**Complexity:** Low (just text parsing)  
**Risk:** Low (isolated workspace)

**This is the recommended starting point.**
