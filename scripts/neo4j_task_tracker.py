#!/usr/bin/env python3
"""
Neo4j Task Tracker - Persistent task history with queryable metrics

Schema:
- (:Task {label, agent, status, created, completed, ...})
- (:Agent {name})-[:EXECUTED]->(:Task)
- (:Task)-[:RETRIED]->(:Task)

Usage:
    from neo4j_task_tracker import TaskTracker
    tracker = TaskTracker()
    tracker.create_task("mongke-123", "mongke", "Research X")
    tracker.update_status("mongke-123", "completed")
"""

import os
import json
import uuid
import glob
from datetime import datetime
from neo4j import GraphDatabase

# Credentials env file — single source of truth
_NEO4J_ENV_FILE = os.path.expanduser("~/.openclaw/credentials/neo4j.env")


def _load_neo4j_env():
    """Load Neo4j credentials from env file into os.environ if not already set."""
    if os.path.exists(_NEO4J_ENV_FILE):
        with open(_NEO4J_ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    if key.strip() not in os.environ:
                        os.environ[key.strip()] = value.strip()


def get_driver():
    """Get a Neo4j driver using centralized credentials.

    This is the SOLE connection factory. All scripts should use this
    instead of creating their own GraphDatabase.driver() calls.
    """
    _load_neo4j_env()
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "myStrongPassword123")
    return GraphDatabase.driver(uri, auth=(user, password))


class TaskTracker:
    def __init__(self):
        self.driver = get_driver()
        
    def close(self):
        self.driver.close()
    
    def create_task(self, label, agent, task_desc, priority="normal", 
                    mode="run", continuous=False, source="chat"):
        """Create a task node"""
        with self.driver.session() as session:
            session.run("""
                MERGE (a:Agent {name: $agent})
                CREATE (t:Task {
                    label: $label,
                    agent: $agent,
                    task: $task,
                    priority: $priority,
                    mode: $mode,
                    continuous: $continuous,
                    source: $source,
                    status: 'ready',
                    created: datetime(),
                    retry_count: 0,
                    max_retries: 3
                })
                CREATE (a)-[:EXECUTED]->(t)
            """,
            label=label, agent=agent, task=task_desc,
            priority=priority, mode=mode, continuous=continuous, source=source)
    
    def update_status(self, label, status, error=None, session_key=None):
        """Update task status"""
        with self.driver.session() as session:
            session.run("""
                MATCH (t:Task {label: $label})
                SET t.status = $status,
                    t.updated = datetime()
                """,
                label=label, status=status)
            
            if status == 'running' and session_key:
                session.run("""
                    MATCH (t:Task {label: $label})
                    SET t.session_key = $session_key,
                        t.started = datetime()
                """, label=label, session_key=session_key)
            
            if status in ['completed', 'failed', 'killed']:
                session.run("""
                    MATCH (t:Task {label: $label})
                    SET t.completed = datetime()
                """, label=label)
            
            if error:
                session.run("""
                    MATCH (t:Task {label: $label})
                    SET t.error = $error
                """, label=label, error=error)
    
    def increment_retry(self, label):
        """Increment retry count"""
        with self.driver.session() as session:
            session.run("""
                MATCH (t:Task {label: $label})
                SET t.retry_count = t.retry_count + 1,
                    t.last_retry = datetime()
            """, label=label)
    
    def get_tasks_by_agent(self, agent, limit=10):
        """Get recent tasks for an agent"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:Agent {name: $agent})-[:EXECUTED]->(t:Task)
                RETURN t ORDER BY t.created DESC LIMIT $limit
            """, agent=agent, limit=limit)
            return [dict(r['t']) for r in result]
    
    def get_tasks_by_status(self, status, limit=50):
        """Get tasks by status"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {status: $status})
                RETURN t ORDER BY t.created DESC LIMIT $limit
            """, status=status, limit=limit)
            return [dict(r['t']) for r in result]
    
    def get_hourly_summary(self, hours=1):
        """Get task summary for last N hours"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                WITH 
                    t.agent AS agent,
                    t.status AS status,
                    t
                WITH
                    agent,
                    status,
                    count(t) AS count
                WITH
                    agent,
                    sum(CASE WHEN status = 'completed' THEN count ELSE 0 END) AS completed,
                    sum(CASE WHEN status = 'failed' THEN count ELSE 0 END) AS failed,
                    sum(CASE WHEN status = 'running' THEN count ELSE 0 END) AS running,
                    sum(CASE WHEN status = 'ready' THEN count ELSE 0 END) AS ready,
                    sum(count) AS total
                RETURN
                    agent,
                    total,
                    completed,
                    failed,
                    running,
                    ready
                ORDER BY total DESC
            """, hours=hours)
            return [dict(r) for r in result]
    
    def get_completion_rate(self, hours=24):
        """Get success/failure rates"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration('PT' + $hours + 'H')
                  AND t.status IN ['completed', 'failed']
                WITH 
                    count(t) AS total,
                    sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS success
                RETURN 
                    total,
                    success,
                    round(100.0 * success / total, 1) AS success_rate
            """, hours=hours)
            record = result.single()
            return dict(record) if record else {}
    
    def get_continuous_tasks(self):
        """Get all running continuous tasks"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {continuous: true, status: 'running'})
                RETURN t ORDER BY t.created DESC
            """)
            return [dict(r['t']) for r in result]
    
    def get_reflection_data(self, agent=None, hours=1):
        """Get data for hourly reflection"""
        with self.driver.session() as session:
            if agent:
                result = session.run("""
                    MATCH (t:Task {agent: $agent})
                    WHERE t.created > datetime() - duration({hours: $hours})
                    RETURN 
                        count(t) AS total_tasks,
                        sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                        sum(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END) AS failed,
                        coalesce(sum(t.retry_count), 0) AS total_retries
                    """, agent=agent, hours=hours)
            else:
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.created > datetime() - duration({hours: $hours})
                    RETURN 
                        count(t) AS total_tasks,
                        sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                        sum(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END) AS failed,
                        coalesce(sum(t.retry_count), 0) AS total_retries
                    """, hours=hours)
            
            record = result.single()
            return dict(record) if record else {}
    
    def get_historical_trends(self, days=7):
        """Get daily task trends for last N days"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({days: $days})
                WITH 
                    date(t.created) AS day,
                    t.status AS status,
                    t
                WITH
                    day,
                    status,
                    count(t) AS count
                WITH
                    day,
                    sum(CASE WHEN status = 'completed' THEN count ELSE 0 END) AS completed,
                    sum(CASE WHEN status = 'failed' THEN count ELSE 0 END) AS failed,
                    sum(CASE WHEN status = 'running' THEN count ELSE 0 END) AS running,
                    sum(count) AS total
                RETURN
                    day,
                    completed,
                    failed,
                    running,
                    total
                ORDER BY day DESC
                """, days=days)
            return [dict(r) for r in result]
    
    def get_agent_workload(self, days=7):
        """Get workload distribution by agent"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({days: $days})
                WITH 
                    t.agent AS agent,
                    t.status AS status,
                    t
                WITH 
                    agent,
                    count(t) AS total_tasks,
                    sum(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed
                RETURN 
                    agent,
                    total_tasks,
                    completed,
                    round(100.0 * completed / total_tasks, 1) AS success_rate
                ORDER BY total_tasks DESC
                """, days=days)
            return [dict(r) for r in result]
    
    def get_peak_hours(self, days=7):
        """Get busiest hours of day"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({days: $days})
                WITH 
                    t.created.hour AS hour,
                    count(t) AS count
                RETURN 
                    hour,
                    count
                ORDER BY count DESC
                LIMIT 5
                """, days=days)
            return [dict(r) for r in result]
    
    def get_bottlenecks(self, hours=24):
        """Find tasks with most retries (potential bottlenecks)"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                  AND t.retry_count > 0
                RETURN 
                    t.agent AS agent,
                    t.label AS label,
                    t.retry_count AS retries,
                    t.status AS status
                ORDER BY retries DESC
                LIMIT 10
                """, hours=hours)
            return [dict(r) for r in result]


    # ==========================================================
    # Phase B: Neo4j as single source of truth
    # ==========================================================

    def create_task_full(self, agent, title, body, priority="normal",
                         source="system", depth=0, parent_id=None):
        """Create task in Neo4j (primary) AND filesystem (backward compat).

        Returns the task_id (uuid).
        """
        task_id = str(uuid.uuid4())[:12]
        label = f"{agent}-{task_id}"

        with self.driver.session() as session:
            session.run("""
                MERGE (a:Agent {name: $agent})
                CREATE (t:Task {
                    task_id: $task_id,
                    label: $label,
                    agent: $agent,
                    title: $title,
                    body: $body,
                    priority: $priority,
                    source: $source,
                    depth: $depth,
                    parent_id: $parent_id,
                    status: 'PENDING',
                    created: datetime(),
                    retry_count: 0,
                    max_retries: 3
                })
                CREATE (a)-[:EXECUTED]->(t)
            """,
            task_id=task_id, label=label, agent=agent, title=title,
            body=body, priority=priority, source=source, depth=depth,
            parent_id=parent_id)

        # Backward-compatible filesystem write
        base = os.path.expanduser("~/.openclaw/agents/main/agent")
        task_dir = f"{base}/{agent}/tasks"
        os.makedirs(task_dir, exist_ok=True)
        epoch = int(datetime.now().timestamp())
        filepath = f"{task_dir}/{priority}-{epoch}.md"

        content = f"""---
agent: {agent}
priority: {priority}
created: {datetime.now().isoformat()}
source: {source}
depth: {depth}
task_id: {task_id}
parent_id: {parent_id or ''}
---

# Task: {title}

{body}
"""
        with open(filepath, 'w') as f:
            f.write(content)

        return task_id

    def transition_task(self, task_id, new_status, actor="system"):
        """Transition task to new state with validation.

        Valid transitions:
            PENDING -> ASSIGNED, CANCELLED
            ASSIGNED -> EXECUTING, CANCELLED
            EXECUTING -> COMPLETED, FAILED, TIMEOUT, CANCELLED
            FAILED -> PENDING (retry)
            TIMEOUT -> PENDING (retry)
        """
        VALID_TRANSITIONS = {
            "PENDING": {"ASSIGNED", "CANCELLED"},
            "ASSIGNED": {"EXECUTING", "CANCELLED"},
            "EXECUTING": {"COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"},
            "FAILED": {"PENDING"},
            "TIMEOUT": {"PENDING"},
        }

        with self.driver.session() as session:
            # Get current status
            result = session.run("""
                MATCH (t:Task {task_id: $task_id})
                RETURN t.status AS status
            """, task_id=task_id)
            record = result.single()

            if not record:
                return {"success": False, "error": f"Task {task_id} not found"}

            current = record["status"]
            allowed = VALID_TRANSITIONS.get(current, set())

            if new_status not in allowed:
                return {
                    "success": False,
                    "error": f"Invalid transition: {current} -> {new_status} (allowed: {allowed})"
                }

            # Apply transition and log it
            session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.status = $new_status,
                    t.updated = datetime()
                CREATE (t)-[:TRANSITIONED {
                    from_status: $current,
                    to_status: $new_status,
                    action: $action,
                    timestamp: datetime(),
                    actor: $actor
                }]->(t)
            """, task_id=task_id, new_status=new_status, current=current,
                action=f"{current}->{new_status}", actor=actor)

            # Set completed timestamp for terminal states
            if new_status in ("COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"):
                session.run("""
                    MATCH (t:Task {task_id: $task_id})
                    SET t.completed = datetime()
                """, task_id=task_id)

            return {"success": True, "from": current, "to": new_status}

    def sync_check(self):
        """Daily sync: compare Neo4j task states with filesystem.

        Returns a dict of discrepancies.
        """
        base = os.path.expanduser("~/.openclaw/agents/main/agent")
        agents = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]
        discrepancies = []

        # Get all recent tasks from Neo4j
        neo4j_tasks = {}
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration('P1D')
                RETURN t.task_id AS task_id, t.agent AS agent,
                       t.status AS status, t.label AS label
            """)
            for r in result:
                tid = r.get("task_id")
                if tid:
                    neo4j_tasks[tid] = {
                        "agent": r["agent"],
                        "status": r["status"],
                        "label": r["label"],
                    }

        # Check filesystem for tasks with task_id in frontmatter
        for agent in agents:
            task_dir = f"{base}/{agent}/tasks"
            if not os.path.isdir(task_dir):
                continue
            for fpath in glob.glob(f"{task_dir}/*.md"):
                try:
                    with open(fpath) as f:
                        content = f.read(500)
                    # Extract task_id from frontmatter
                    import re
                    match = re.search(r'^task_id:\s*(\S+)', content, re.MULTILINE)
                    if not match:
                        continue
                    file_task_id = match.group(1)

                    # Determine file status from filename
                    fname = os.path.basename(fpath)
                    if '.done' in fname:
                        file_status = "COMPLETED"
                    elif '.executing' in fname:
                        file_status = "EXECUTING"
                    else:
                        file_status = "PENDING"

                    neo_entry = neo4j_tasks.get(file_task_id)
                    if neo_entry and neo_entry["status"] != file_status:
                        discrepancies.append({
                            "task_id": file_task_id,
                            "agent": agent,
                            "file": fname,
                            "file_status": file_status,
                            "neo4j_status": neo_entry["status"],
                        })
                except Exception:
                    continue

        return {
            "checked": datetime.now().isoformat(),
            "neo4j_count": len(neo4j_tasks),
            "discrepancies": discrepancies,
        }


    # ==========================================================
    # Phase B4: Hypothesis validation
    # ==========================================================

    def validate_hypotheses(self):
        """Check pending Hypothesis nodes and mark as validated or expired.

        - Hypotheses older than 2h with matching completed tasks -> validated
        - Hypotheses older than 24h with no match -> expired
        """
        results = {"validated": 0, "expired": 0, "pending": 0}

        with self.driver.session() as session:
            # Validate: pending hypotheses older than 2h with completed tasks
            r = session.run("""
                MATCH (h:Hypothesis {status: 'pending'})
                WHERE h.created < datetime() - duration('PT2H')
                OPTIONAL MATCH (t:Task)
                    WHERE t.status = 'completed'
                      AND t.created > h.created
                      AND (toLower(t.title) CONTAINS toLower(substring(h.action, 0, 30))
                           OR toLower(t.task) CONTAINS toLower(substring(h.action, 0, 30)))
                WITH h, count(t) AS matching_tasks
                WHERE matching_tasks > 0
                SET h.status = 'validated',
                    h.validated_at = datetime(),
                    h.validated = true
                RETURN count(h) AS cnt
            """)
            record = r.single()
            results["validated"] = record["cnt"] if record else 0

            # Expire: pending hypotheses older than 24h with no match
            r = session.run("""
                MATCH (h:Hypothesis {status: 'pending'})
                WHERE h.created < datetime() - duration('P1D')
                SET h.status = 'expired',
                    h.expired_at = datetime()
                RETURN count(h) AS cnt
            """)
            record = r.single()
            results["expired"] = record["cnt"] if record else 0

            # Count remaining pending
            r = session.run("""
                MATCH (h:Hypothesis {status: 'pending'})
                RETURN count(h) AS cnt
            """)
            record = r.single()
            results["pending"] = record["cnt"] if record else 0

        return results

    # ==========================================================
    # Phase B5: WHEN/THEN Rules as Neo4j entities
    # ==========================================================

    def create_rule(self, agent, condition, action, source="system"):
        """Create a (:Rule) node with 'proposed' status."""
        rule_id = str(uuid.uuid4())[:12]
        with self.driver.session() as session:
            session.run("""
                CREATE (r:Rule {
                    rule_id: $rule_id,
                    agent: $agent,
                    condition: $condition,
                    action: $action,
                    status: 'proposed',
                    source: $source,
                    created: datetime(),
                    last_invoked: null,
                    invocations: 0
                })
            """, rule_id=rule_id, agent=agent, condition=condition,
                action=action, source=source)
        return rule_id

    def invoke_rule(self, rule_id):
        """Mark a rule as invoked. Transitions proposed->active on first use."""
        with self.driver.session() as session:
            session.run("""
                MATCH (r:Rule {rule_id: $rule_id})
                SET r.invocations = r.invocations + 1,
                    r.last_invoked = datetime(),
                    r.status = CASE
                        WHEN r.status = 'proposed' THEN 'active'
                        ELSE r.status
                    END
            """, rule_id=rule_id)

    def prune_rules(self):
        """Lifecycle management for rules.

        - active rules with no invocation for 7 days -> deprecated
        - deprecated rules with no invocation for 30 days -> pruned (deleted)
        """
        results = {"deprecated": 0, "pruned": 0}
        with self.driver.session() as session:
            # Deprecate: active rules unused for 7 days
            r = session.run("""
                MATCH (r:Rule {status: 'active'})
                WHERE r.last_invoked < datetime() - duration('P7D')
                SET r.status = 'deprecated'
                RETURN count(r) AS cnt
            """)
            record = r.single()
            results["deprecated"] = record["cnt"] if record else 0

            # Prune: deprecated rules unused for 30 days
            r = session.run("""
                MATCH (r:Rule {status: 'deprecated'})
                WHERE r.last_invoked < datetime() - duration('P30D')
                   OR (r.last_invoked IS NULL AND r.created < datetime() - duration('P30D'))
                DELETE r
                RETURN count(r) AS cnt
            """)
            record = r.single()
            results["pruned"] = record["cnt"] if record else 0

        return results

    def get_active_rules(self, agent=None):
        """Get active rules, optionally filtered by agent."""
        with self.driver.session() as session:
            if agent:
                result = session.run("""
                    MATCH (r:Rule)
                    WHERE r.status IN ['proposed', 'active']
                      AND r.agent = $agent
                    RETURN r.rule_id AS rule_id, r.agent AS agent,
                           r.condition AS condition, r.action AS action,
                           r.status AS status, r.invocations AS invocations
                    ORDER BY r.invocations DESC
                """, agent=agent)
            else:
                result = session.run("""
                    MATCH (r:Rule)
                    WHERE r.status IN ['proposed', 'active']
                    RETURN r.rule_id AS rule_id, r.agent AS agent,
                           r.condition AS condition, r.action AS action,
                           r.status AS status, r.invocations AS invocations
                    ORDER BY r.invocations DESC
                """)
            return [dict(r) for r in result]


# Singleton instance
_tracker = None

def get_tracker():
    """Get or create tracker instance"""
    global _tracker
    if _tracker is None:
        _tracker = TaskTracker()
    return _tracker


if __name__ == "__main__":
    # Test
    tracker = get_tracker()
    print("Neo4j Task Tracker initialized")
    print("Hourly summary:", tracker.get_hourly_summary(1))
    tracker.close()
