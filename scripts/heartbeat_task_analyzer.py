#!/usr/bin/env python3
"""
Heartbeat Task Analyzer - Reviews agent's assigned heartbeat tasks

Analyzes heartbeat_master.py tasks for:
- Performance issues
- Redundancies
- Optimization opportunities
- Local LLM candidacy

Usage:
    python3 heartbeat_task_analyzer.py --agent temujin
    python3 heartbeat_task_analyzer.py --all-agents
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

HEARTBEAT_FILE = "/Users/kublai/kurultai/kublai-repo/tools/kurultai/agent_tasks.py"
METRICS_FILE = "/Users/kublai/.openclaw/agents/main/logs/heartbeat_metrics.jsonl"

AGENT_TASKS = {
    "kublai": ["status_synthesis", "task_pickup", "kublai_review"],
    "temujin": ["task_pickup", "code_review"],
    "mongke": ["task_pickup", "quick_research", "knowledge_gap_analysis", "ordo_sacer_research", "ecosystem_intelligence"],
    "chagatai": ["task_pickup", "content_generation", "reflection_consolidation"],
    "jochi": ["task_pickup", "memory_curation_rapid", "smoke_tests", "full_tests", "deep_curation"],
    "ogedei": ["task_pickup", "health_check", "file_consistency"]
}

LOCAL_LLM_CANDIDATES = [
    "task_pickup",
    "health_check", 
    "memory_curation_rapid",
    "file_consistency",
    "smoke_tests",
    "status_synthesis"
]

def parse_heartbeat_tasks():
    """Parse agent_tasks.py to extract task definitions"""
    if not os.path.exists(HEARTBEAT_FILE):
        return {}
    
    with open(HEARTBEAT_FILE, 'r') as f:
        content = f.read()
    
    tasks = {}
    
    # Find all hb.register(HeartbeatTask(...)) calls
    pattern = r'hb\.register\(HeartbeatTask\(\s*name="([^"]+)",\s*agent="([^"]+)",\s*frequency_minutes=(\d+),\s*max_tokens=(\d+),\s*handler=([^,]+),'
    
    for match in re.finditer(pattern, content):
        name, agent, freq, tokens, handler = match.groups()
        
        if agent not in tasks:
            tasks[agent] = []
        
        tasks[agent].append({
            "name": name,
            "agent": agent,
            "frequency_minutes": int(freq),
            "max_tokens": int(tokens),
            "handler": handler.strip()
        })
    
    return tasks

def get_task_metrics(agent=None, hours=24):
    """Get execution metrics for tasks"""
    metrics = []
    
    if os.path.exists(METRICS_FILE):
        try:
            with open(METRICS_FILE, 'r') as f:
                for line in f:
                    try:
                        m = json.loads(line)
                        if agent is None or m.get('agent') == agent:
                            metrics.append(m)
                    except:
                        pass
        except:
            pass
    
    return metrics

def analyze_agent_tasks(agent):
    """Analyze tasks for a specific agent"""
    all_tasks = parse_heartbeat_tasks()
    agent_tasks = all_tasks.get(agent, [])
    metrics = get_task_metrics(agent)
    
    analysis = {
        "agent": agent,
        "timestamp": datetime.now().isoformat(),
        "tasks": [],
        "local_llm_candidates": [],
        "optimization_opportunities": [],
        "concerns": []
    }
    
    for task in agent_tasks:
        task_analysis = {
            "name": task["name"],
            "frequency_minutes": task["frequency_minutes"],
            "max_tokens": task["max_tokens"],
            "estimated_cost_per_day": (1440 / task["frequency_minutes"]) * task["max_tokens"] * 0.00002,  # Rough cloud cost
            "is_local_candidate": task["name"] in LOCAL_LLM_CANDIDATES,
            "issues": []
        }
        
        # Check for issues
        if task["frequency_minutes"] < 5:
            task_analysis["issues"].append(f"Very high frequency ({task['frequency_minutes']}min) - consider reducing")
        
        if task["max_tokens"] > 2000:
            task_analysis["issues"].append(f"High token usage ({task['max_tokens']}) - review if needed")
        
        if task_analysis["is_local_candidate"]:
            analysis["local_llm_candidates"].append({
                "task": task["name"],
                "reason": "Simple, routine task suitable for local LLM",
                "estimated_savings_monthly": task_analysis["estimated_cost_per_day"] * 30
            })
        
        analysis["tasks"].append(task_analysis)
    
    # Calculate total cost
    total_daily_cost = sum(t["estimated_cost_per_day"] for t in analysis["tasks"])
    analysis["total_estimated_cost"] = {
        "daily": total_daily_cost,
        "monthly": total_daily_cost * 30
    }
    
    # Generate optimization suggestions
    if analysis["local_llm_candidates"]:
        analysis["optimization_opportunities"].append({
            "type": "local_llm_migration",
            "priority": "HIGH",
            "tasks": [c["task"] for c in analysis["local_llm_candidates"]],
            "impact": f"Save ~${sum(c['estimated_savings_monthly'] for c in analysis['local_llm_candidates']):.2f}/month",
            "effort": "LOW",
            "description": "Move routine tasks to local LLM (qwen3.5-9b-mlx)"
        })
    
    return analysis

def generate_review(agent):
    """Generate critical review for an agent's heartbeat tasks"""
    analysis = analyze_agent_tasks(agent)
    
    review = f"""# Heartbeat Task Review: {agent.capitalize()}

**Generated:** {analysis['timestamp']}

---

## Your Assigned Heartbeat Tasks

| Task | Frequency | Max Tokens | Est. Cost/Day | Local LLM? |
|------|-----------|------------|---------------|------------|
"""
    
    for task in analysis["tasks"]:
        local = "✅ Yes" if task["is_local_candidate"] else "❌ No"
        review += f"| {task['name']} | {task['frequency_minutes']} min | {task['max_tokens']} | ${task['estimated_cost_per_day']:.4f} | {local} |\n"
    
    review += f"""
**Total Estimated Cost:** ${analysis['total_estimated_cost']['daily']:.4f}/day (${analysis['total_estimated_cost']['monthly']:.2f}/month)

---

## Local LLM Candidates

"""
    
    if analysis["local_llm_candidates"]:
        for candidate in analysis["local_llm_candidates"]:
            review += f"""
### {candidate['task']}
- **Reason:** {candidate['reason']}
- **Estimated Savings:** ${candidate['estimated_savings_monthly']:.2f}/month
- **Recommendation:** Move to local LLM (qwen3.5-9b-mlx) with cloud fallback
"""
    else:
        review += "*No local LLM candidates identified*\n"
    
    review += f"""
---

## Optimization Opportunities

"""
    
    if analysis["optimization_opportunities"]:
        for opt in analysis["optimization_opportunities"]:
            review += f"""
### {opt['type']} ({opt['priority']})
- **Tasks:** {', '.join(opt['tasks'])}
- **Impact:** {opt['impact']}
- **Effort:** {opt['effort']}
- **Description:** {opt['description']}
"""
    else:
        review += "*No optimization opportunities identified*\n"
    
    review += f"""
---

## Critical Evaluation Questions

### 1. Task Performance

- Are your heartbeat tasks running reliably?
- Any timeouts or failures?
- Token budgets appropriate?

**Your assessment:**
```
[Agent responds here]
```

---

### 2. Local LLM Migration

**Recommended for you:** {', '.join([c['task'] for c in analysis['local_llm_candidates']]) or 'None'}

- Do you agree with these recommendations?
- Any concerns about local LLM quality?
- Should additional tasks be considered?

**Your feedback:**
```
[Agent responds here]
```

---

### 3. Task Necessity

- Are all your heartbeat tasks still necessary?
- Any tasks that could be removed or consolidated?
- Frequency appropriate for each task?

**Your assessment:**
```
[Agent responds here]
```

---

## Recommendations to Kublai

**Priority:** [ ] CRITICAL  [ ] HIGH  [ ] MEDIUM  [ ] LOW

**Proposed Changes:**
```
[List specific changes to heartbeat tasks]
Example:
- Move task_pickup to local LLM with cloud fallback
- Reduce health_check frequency from 5min to 10min
- Add retry logic to code_review task
```

**Implementation Tasks:**
```
[List tasks Kublai should assign]
Example:
- Update agent_tasks.py to route task_pickup to local LLM (assign to: temujin)
- Add metrics tracking for local LLM success rate (assign to: jochi)
- Implement fallback mechanism (assign to: temujin)
```

---

*Generated by heartbeat_task_analyzer.py*
"""
    
    return review

def main():
    parser = argparse.ArgumentParser(description='Analyze heartbeat tasks')
    parser.add_argument('--agent', help='Specific agent')
    parser.add_argument('--all-agents', action='store_true', help='All 6 agents')
    
    args = parser.parse_args()
    
    if args.all_agents:
        agents = list(AGENT_TASKS.keys())
    elif args.agent:
        agents = [args.agent]
    else:
        print("Usage: python3 heartbeat_task_analyzer.py --agent <name> OR --all-agents")
        sys.exit(1)
    
    for agent in agents:
        print(f"\n{'='*70}")
        print(f"AGENT: {agent.upper()}")
        print(f"{'='*70}\n")
        
        review = generate_review(agent)
        print(review)

if __name__ == "__main__":
    main()
