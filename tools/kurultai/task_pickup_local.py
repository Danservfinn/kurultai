"""
Updated Task Pickup with Local LLM Routing

Uses local LLM for routine task pickup with cloud fallback.
"""

import glob
import json
import os
import time
from typing import Dict

async def generic_task_pickup(agent_name: str, driver) -> Dict:
    """
    Generic task pickup handler for any agent.
    Uses local LLM for routing decisions with cloud fallback.
    """
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from local_llm_router import run_with_routing, log_metric
    
    task_dir = f"/Users/kublai/.openclaw/agents/main/agent/{agent_name}/tasks"
    spawn_queue = "/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json"
    
    results = {
        "tasks_found": 0,
        "tasks_queued": 0,
        "tokens_used": 100,
        "model_used": "unknown"
    }
    
    if not os.path.exists(task_dir):
        return {"summary": f"No task directory for {agent_name}", "tokens_used": 50, "data": results}
    
    # Find pending tasks
    try:
        tasks = (glob.glob(f"{task_dir}/high-*.md") +
                 glob.glob(f"{task_dir}/normal-*.md") +
                 glob.glob(f"{task_dir}/low-*.md"))
        results["tasks_found"] = len(tasks)
        
        if not tasks:
            return {"summary": f"No pending tasks for {agent_name}", "tokens_used": 50, "data": results}
        
        # Load existing queue
        existing_spawns = []
        if os.path.exists(spawn_queue):
            try:
                with open(spawn_queue, 'r') as f:
                    data = json.load(f)
                    existing_spawns = data.get('spawns', [])
            except:
                pass
        
        # Process each task
        for task_file in tasks:
            task_name = os.path.basename(task_file)
            
            # Read task description
            with open(task_file, 'r') as f:
                content = f.read()
                import re
                match = re.search(r'^# Task: (.+)$', content, re.MULTILINE)
                task_desc = match.group(1) if match else task_name
            
            # Determine priority from filename
            priority = "normal"
            if "high-" in task_file:
                priority = "high"
            elif "low-" in task_file:
                priority = "low"
            
            # Use local LLM to validate/categorize task (with cloud fallback)
            prompt = f"Categorize this task for {agent_name}: {task_desc[:100]}"
            
            llm_result = run_with_routing(
                agent=agent_name,
                task_name="task_pickup",
                prompt=prompt,
                force_cloud=False
            )
            
            results["model_used"] = llm_result.get('model', 'unknown')
            
            # Write spawn request
            spawn_request = {
                "agent": agent_name,
                "model": "qwen3.5-plus" if agent_name == "jochi" else "qwen3.5-plus",
                "task": task_desc,
                "priority": priority,
                "label": f"{agent_name}-{int(time.time())}",
                "source": "heartbeat_pickup",
                "processed_by": llm_result.get('model', 'unknown')
            }
            
            existing_spawns.append(spawn_request)
            
            # Move to executing
            executing_file = task_file.replace('.md', '.executing.md')
            os.rename(task_file, executing_file)
            
            results["tasks_queued"] += 1
        
        # Save updated queue
        os.makedirs(os.path.dirname(spawn_queue), exist_ok=True)
        with open(spawn_queue, 'w') as f:
            json.dump({'spawns': existing_spawns, 'updated': time.time()}, f, indent=2)
        
        return {
            "summary": f"Found {results['tasks_found']} tasks, queued {results['tasks_queued']} spawns for {agent_name} (model: {results['model_used']})",
            "tokens_used": 200,
            "data": results
        }
        
    except Exception as e:
        import logging
        logging.getLogger("kurultai.agent_tasks").exception(f"{agent_name} task pickup failed")
        return {"summary": f"Error: {e}", "tokens_used": 100, "data": {"error": str(e)}}
