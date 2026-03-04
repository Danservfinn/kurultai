#!/usr/bin/env python3
"""
Agent Meta-Reflection Generator

Generates meta-reflection prompts for all 6 agents with their actual metrics.
Agents submit feedback to Kublai via Neo4j AgentFeedback nodes.

Usage:
    python3 meta_reflection.py --agent temujin --hours 1
    python3 meta_reflection.py --all-agents --hours 1
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from neo4j_task_tracker import get_tracker

AGENT_ROLES = {
    "kublai": "Squad Lead / Router",
    "temujin": "Developer (code, builds, infrastructure)",
    "mongke": "Researcher (web research, API discovery)",
    "chagatai": "Writer (documentation, creative content)",
    "jochi": "Analyst (testing, security, pattern recognition)",
    "ogedei": "Ops (monitoring, health checks, failover)"
}

AGENT_MODELS = {
    "kublai": "bailian/qwen3.5-plus",
    "mongke": "bailian/MiniMax-M2.5",
    "chagatai": "bailian/kimi-k2.5",
    "temujin": "bailian/MiniMax-M2.5",
    "jochi": "bailian/qwen3.5-plus",
    "ogedei": "bailian/qwen3.5-plus"
}


def get_system_context():
    """Generate compact system context from OpenClaw config for agent awareness."""
    import subprocess

    ctx = {}

    # Gateway health
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "health"],
            capture_output=True, text=True, timeout=10
        )
        ctx["gateway_health"] = result.stdout.strip() if result.returncode == 0 else "UNREACHABLE"
    except Exception:
        ctx["gateway_health"] = "UNKNOWN"

    # Cron job status
    try:
        result = subprocess.run(
            ["openclaw", "cron", "list"],
            capture_output=True, text=True, timeout=10
        )
        lines = [l for l in result.stdout.strip().split("\n") if l and not l.startswith("ID")]
        cron_summary = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 7:
                name = " ".join(parts[1:-5])
                status = parts[-3] if len(parts) > 3 else "?"
                cron_summary.append(f"  - {name}: {status}")
        ctx["cron_jobs"] = "\n".join(cron_summary) if cron_summary else "No cron jobs"
    except Exception:
        ctx["cron_jobs"] = "Unavailable"

    # Agent session usage
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "call", "status", "--json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            agent_status = []
            for a in data.get("sessions", {}).get("byAgent", []):
                agent_id = a.get("agentId", "?")
                count = a.get("count", 0)
                recent = a.get("recent", [{}])[0] if a.get("recent") else {}
                pct = recent.get("percentUsed", 0)
                model = recent.get("model", "?")
                agent_status.append(f"  - {agent_id}: {count} sessions, {pct}% ctx used, model={model}")
            ctx["agent_sessions"] = "\n".join(agent_status)
        else:
            ctx["agent_sessions"] = "Unavailable"
    except Exception:
        ctx["agent_sessions"] = "Unavailable"

    return ctx


def format_system_context(ctx):
    """Format system context as a compact markdown block for agent reflection."""
    return f"""## System Context (OpenClaw)

**Gateway:** {ctx.get('gateway_health', 'UNKNOWN')}

**Agents:**
| ID | Role | Model |
|----|------|-------|
| kublai | Squad Lead | bailian/qwen3.5-plus |
| mongke | Researcher | bailian/MiniMax-M2.5 |
| chagatai | Writer/Ops | bailian/kimi-k2.5 |
| temujin | Developer | bailian/MiniMax-M2.5 |
| jochi | Analyst | bailian/qwen3.5-plus |
| ogedei | Ops | bailian/qwen3.5-plus |

**Session Usage:**
{ctx.get('agent_sessions', 'Unavailable')}

**Cron Jobs:**
{ctx.get('cron_jobs', 'Unavailable')}

**Signal:** Bot +15165643945, Group: Kublai Klub
**Config:** ~/.openclaw/openclaw.json
**Workspaces:** ~/.openclaw/agents/{{id}}/
"""

def get_agent_metrics(agent, hours=1):
    """Get metrics for an agent"""
    tracker = get_tracker()
    
    # Get task data
    task_data = tracker.get_reflection_data(agent, hours)
    
    # Get recent tasks
    try:
        recent_tasks = tracker.get_tasks_by_agent(agent, limit=5)
    except:
        recent_tasks = []
    
    # Get completion rate
    try:
        completion = tracker.get_completion_rate(hours * 24)
    except:
        completion = {}
    
    total = task_data.get('total_tasks', 0) or 0
    completed = task_data.get('completed', 0) or 0
    
    success_rate = f"{100 * completed / total:.1f}%" if total > 0 else "N/A"
    avg_duration = task_data.get('avg_duration')
    
    tracker.close()
    
    return {
        "total_tasks": total,
        "completed": completed,
        "failed": task_data.get('failed', 0) or 0,
        "retries": task_data.get('total_retries', 0) or 0,
        "success_rate": success_rate,
        "avg_duration": f"{avg_duration:.1f}s" if avg_duration else "N/A",
        "recent_tasks": recent_tasks[:5],
        "completion_rate": completion
    }

def generate_reflection(agent, hours=1, include_chat_review=False, chat_hours=2, include_heartbeat_review=False):
    """Generate meta-reflection prompt for an agent"""
    metrics = get_agent_metrics(agent, hours)
    role = AGENT_ROLES.get(agent, "Unknown")
    model = AGENT_MODELS.get(agent, "Unknown")

    # Gather live system context
    try:
        sys_ctx = get_system_context()
        system_context_block = format_system_context(sys_ctx)
    except Exception as e:
        system_context_block = f"*System context unavailable: {e}*\n"

    # Optionally include chat log review
    chat_review = ""
    if include_chat_review:
        try:
            from chat_log_analyzer import generate_chat_review
            chat_review = generate_chat_review(chat_hours)
        except Exception as e:
            chat_review = f"*Chat log review unavailable: {e}*\n"

    # Optionally include heartbeat task review
    heartbeat_review = ""
    if include_heartbeat_review:
        try:
            from heartbeat_task_analyzer import generate_review
            heartbeat_review = generate_review(agent)
        except Exception as e:
            heartbeat_review = f"*Heartbeat task review unavailable: {e}*\n"

    template = f"""# Agent Meta-Reflection: Task & Spawning System Evaluation

**Agent:** {agent.capitalize()}
**Role:** {role}
**Model:** {model}
**Reflection Period:** Last {hours} hour(s)
**Timestamp:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

{system_context_block}

---

## Your Metrics This Period
"""
    
    # Add chat review if available
    if chat_review:
        template += f"""
---

## 📝 Chat Log Review (Last {chat_hours} Hours)

{chat_review}

---
"""
    
    # Add heartbeat task review if available
    if heartbeat_review:
        template += f"""
---

## ⚙️ Heartbeat Task Review

{heartbeat_review}

---
"""
    
    template += f"""
## Your Metrics This Period

- **Tasks completed:** {metrics['completed']} of {metrics['total_tasks']}
- **Success rate:** {metrics['success_rate']}
- **Retries:** {metrics['retries']}
- **Avg duration:** {metrics['avg_duration']}

---

## Critical Evaluation Questions

### 1. System Performance (Your Experience)

Reflect on your own tasks:
- How many tasks did you complete this period?
- What was your success rate?
- Did you experience any failures or retries? Why?
- Were tasks clearly defined or ambiguous?
- Did you have the right tools/context to succeed?

**Your assessment:**
```
[Agent responds here]
```

---

### 2. System Bottlenecks

From your perspective, what's broken or slow?

Consider:
- Task classification accuracy (are you getting the right tasks?)
- Spawn latency (how long from task creation to execution?)
- Queue backlog (are tasks waiting too long?)
- Resource constraints (model limits, timeouts, etc.)
- Coordination gaps (missing handoffs between agents?)

**Your observations:**
```
[Agent responds here]
```

---

### 3. Improvement Ideas

What would make the system better?

Think about:
- New features or capabilities
- Process improvements
- Better routing/classification
- Monitoring or alerting
- Automation opportunities

**Your proposals:**
```
[Agent responds here - be specific and actionable]
```

---

### 4. Agent-to-Agent Feedback

What do you observe about OTHER agents?

- Who's overloaded? Who's underutilized?
- Any coordination issues between agents?
- Tasks that should be rerouted to different agents?
- Collaboration opportunities?

**Your observations:**
```
[Agent responds here]
```

---

### 5. Strategic Recommendations

Big-picture thinking:

If you could change ONE thing about the task/spawning system to make it 10x better, what would it be?

**Your recommendation:**
```
[Agent's boldest idea]
```

---

## Submission to Kublai

**Priority Level:**
- [ ] CRITICAL (system broken, needs immediate fix)
- [ ] HIGH (significant improvement, implement soon)
- [ ] MEDIUM (nice to have, schedule when possible)
- [ ] LOW (minor optimization, backlog)

**Proposal Summary:**
```
[1-2 sentence summary]
```

**Specific Tasks to Implement:**
```
[List specific tasks and which agent should handle each]
```

---

*Generated by meta_reflection.py*
"""
    
    return template

def submit_feedback(agent, feedback_text, priority="MEDIUM", proposals=None):
    """Submit feedback to Kublai via Neo4j"""
    tracker = get_tracker()
    
    with tracker.driver.session() as session:
        session.run("""
            MERGE (a:Agent {name: $agent})
            CREATE (f:AgentFeedback {
                agent: $agent,
                feedback: $feedback,
                priority: $priority,
                proposals: $proposals,
                submitted: datetime(),
                status: 'pending_review',
                id: $feedback_id
            })
            CREATE (a)-[:SUBMITTED]->(f)
        """,
        agent=agent,
        feedback=feedback_text,
        priority=priority,
        proposals=json.dumps(proposals or []),
        feedback_id=f"{agent}-{int(datetime.now().timestamp())}"
        )
    
    tracker.close()
    print(f"✓ Feedback submitted to Kublai: {agent}")

def get_pending_feedback():
    """Get all pending feedback for Kublai to review"""
    tracker = get_tracker()
    
    with tracker.driver.session() as session:
        result = session.run("""
            MATCH (f:AgentFeedback {status: 'pending_review'})
            RETURN f ORDER BY 
                CASE f.priority 
                    WHEN 'CRITICAL' THEN 1 
                    WHEN 'HIGH' THEN 2 
                    WHEN 'MEDIUM' THEN 3 
                    ELSE 4 
                END,
                f.submitted DESC
        """)
        feedback = [dict(r['f']) for r in result]
    
    tracker.close()
    return feedback

def main():
    parser = argparse.ArgumentParser(description='Generate agent meta-reflections')
    parser.add_argument('--agent', help='Specific agent')
    parser.add_argument('--all-agents', action='store_true', help='Generate for all 6 agents')
    parser.add_argument('--hours', type=int, default=1, help='Hours to look back')
    parser.add_argument('--chat-review', action='store_true', help='Include chat log review (last 2 hours)')
    parser.add_argument('--chat-hours', type=int, default=2, help='Hours for chat log review')
    parser.add_argument('--heartbeat-review', action='store_true', help='Include heartbeat task review')
    parser.add_argument('--submit', action='store_true', help='Submit feedback to Kublai (vs just printing)')
    parser.add_argument('--list-pending', action='store_true', help='List pending feedback for Kublai')
    
    args = parser.parse_args()
    
    if args.list_pending:
        feedback = get_pending_feedback()
        print(f"Pending feedback for Kublai: {len(feedback)}")
        for f in feedback:
            print(f"  - [{f.get('priority')}] {f.get('agent')}: {f.get('feedback', '')[:50]}...")
        return
    
    agents = [args.agent] if args.agent else (list(AGENT_ROLES.keys()) if args.all_agents else [])
    
    if not agents:
        print("Usage: python3 meta_reflection.py --agent <name> OR --all-agents")
        sys.exit(1)
    
    for agent in agents:
        reflection = generate_reflection(
            agent, 
            args.hours, 
            include_chat_review=args.chat_review,
            chat_hours=args.chat_hours,
            include_heartbeat_review=args.heartbeat_review
        )
        
        if args.submit:
            # In real usage, agent would fill out the reflection and submit
            # For now, just demonstrate the mechanism
            submit_feedback(
                agent=agent,
                feedback_text=reflection[:500],  # Truncated for demo
                priority="MEDIUM",
                proposals=[]
            )
        else:
            print(f"\n{'='*60}")
            print(f"AGENT: {agent.upper()}")
            print(f"{'='*60}")
            print(reflection)
            print(f"\n{'='*60}\n")

if __name__ == "__main__":
    main()
