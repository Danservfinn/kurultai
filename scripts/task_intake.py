#!/usr/bin/env python3
"""
task_intake.py — Single entry point for all task creation.

Pipeline:
    1. Validate depth (reject if >= MAX_DEPTH)
    2. Route via canonical router (task_router.py)
    3. Duplicate check (has_pending_task)
    4. Create in Neo4j (primary) via create_task_full()
    5. Write filesystem (backward compat, done by create_task_full)

Usage:
    from task_intake import create_task

    task_id = create_task(
        title="Investigate error spike",
        body="Check logs for errors...",
        priority="high",
        source="kublai-actions",
        depth=0,
        agent=None,  # auto-route from title
    )
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Minimal routing table -- source of truth is kurultai-router SKILL.md
# This is the fallback for programmatic task creation (cron, heartbeat, etc.)
AGENT_KEYWORDS = {
    "temujin": ["code", "build", "implement", "fix", "deploy", "design", "architect",
                "bug", "feature", "api", "script", "brainstorm", "payment", "protocol"],
    "mongke": ["research", "investigate", "discover", "explore", "competitor", "market"],
    "chagatai": ["write", "document", "blog", "content", "changelog", "copy", "article"],
    "jochi": ["test", "verify", "audit", "review", "security", "analyze", "vulnerability",
              "error", "debug", "scan", "prompt injection"],
    "ogedei": ["monitor", "health", "restart", "backup", "alert", "uptime", "cron",
               "incident", "status"],
    "kublai": ["triage", "coordinate", "prioritize", "system-wide", "assessment", "status assessment",
               "agent status", "backlog"],
}

# Disambiguation rules (first-match-wins) -- mirrors AGENTS.md hard rules
_DISAMBIGUATION = [
    ({"status", "implement"}, "kublai"),  # project status -> kublai (PM)
    ({"status", "progress"}, "kublai"),
    ({"status", "next"}, "kublai"),
    ({"status", "feature"}, "kublai"),
    ({"status", "project"}, "kublai"),
    ({"status"}, "ogedei"),               # bare ops status -> ogedei
    ({"research", "security"}, "jochi"),
    ({"research", "vulnerabilit"}, "jochi"),
    ({"research", "audit"}, "jochi"),
    ({"test", "write"}, "jochi"),
    ({"fix", "cron"}, "ogedei"),
    ({"fix", "backup"}, "ogedei"),
    ({"fix", "monitor"}, "ogedei"),
    ({"design", "research"}, "temujin"),
]

def route_by_text(text):
    """Keyword routing for programmatic task creation with disambiguation."""
    text_lower = text.lower()

    # Check disambiguation rules first (first-match-wins)
    for keywords_set, target in _DISAMBIGUATION:
        if all(kw in text_lower for kw in keywords_set):
            return target

    best, best_score = "temujin", 0
    for agent, keywords in AGENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best, best_score = agent, score
    return best

# --- LOAD BALANCING ---
# Overflow routing: when primary agent is busy, route to a capable alternate
OVERFLOW_MAP = {
    # (primary_agent, task_category): [overflow_agents in priority order]
    ("temujin", "code_review"):     ["jochi"],
    ("temujin", "deploy"):          ["ogedei"],
    ("temujin", "infrastructure"):  ["ogedei"],
    ("temujin", "testing"):         ["jochi"],
    ("jochi", "code_review"):       ["temujin"],
    ("jochi", "security"):          ["temujin", "ogedei"],
    ("mongke", "research"):         ["chagatai"],
    ("chagatai", "docs"):           ["mongke"],
    ("ogedei", "deploy"):           ["temujin"],
    ("ogedei", "monitoring"):       ["jochi"],
}

CATEGORY_KEYWORDS = {
    "code_review": ["review", "code review", "pull request", "PR review"],
    "deploy": ["deploy", "deployment", "railway", "production", "ship"],
    "infrastructure": ["infrastructure", "infra", "docker", "container"],
    "testing": ["test", "tests", "testing", "spec", "e2e"],
    "security": ["security", "vulnerability", "audit", "scan", "injection"],
    "research": ["research", "investigate", "discover", "explore", "competitor"],
    "docs": ["document", "documentation", "readme", "changelog"],
    "monitoring": ["monitor", "health", "alert", "status", "uptime"],
}


# --- SKILL HINT DETECTION ---
# Auto-detect the best horde/domain skill for the task
SKILL_HINTS = {
    ("temujin", "design"):     "/horde-brainstorming",
    ("temujin", "architect"):  "/horde-brainstorming",
    ("temujin", "brainstorm"): "/horde-brainstorming",
    ("temujin", "plan"):       "/horde-brainstorming",
    ("temujin", "protocol"):   "/horde-brainstorming",
    ("temujin", "payment"):    "/horde-brainstorming",
    ("temujin", "implement"):  "/horde-implement",
    ("temujin", "build"):      "/horde-implement",
    ("temujin", "scaffold"):   "/horde-implement",
    ("temujin", "finish"):     "/horde-implement",
    ("temujin", "complete"):   "/horde-implement",
    ("temujin", "debug"):      "/systematic-debugging",
    ("temujin", "broken"):     "/systematic-debugging",
    ("temujin", "error"):      "/systematic-debugging",
    ("temujin", "crash"):      "/systematic-debugging",
    ("temujin", "deploy"):     "/dev-deploy",
    ("temujin", "railway"):    "/dev-deploy",
    ("mongke", "research"):    "/horde-learn",
    ("mongke", "investigate"): "/horde-learn",
    ("mongke", "discover"):    "/horde-learn",
    ("mongke", "explore"):     "/horde-learn",
    ("mongke", "scrape"):      "/scrapling-research",
    ("mongke", "crawl"):       "/scrapling-research",
    ("chagatai", "blog"):      "/content-research-writer",
    ("chagatai", "article"):   "/content-research-writer",
    ("chagatai", "content"):   "/content-research-writer",
    ("chagatai", "changelog"): "/changelog-generator",
    ("chagatai", "release"):   "/changelog-generator",
    ("jochi", "debug"):        "/systematic-debugging",
    ("jochi", "bug"):          "/systematic-debugging",
    ("jochi", "error"):        "/systematic-debugging",
    ("jochi", "review"):       "/code-reviewer",
    ("jochi", "audit"):        "/code-reviewer",
    ("jochi", "security"):     "/code-reviewer",
    ("ogedei", "health"):      "/kurultai-health",
    ("ogedei", "diagnostic"):  "/kurultai-health",
    ("ogedei", "deploy"):      "/dev-deploy",
    ("ogedei", "railway"):     "/dev-deploy",
}


def detect_skill_hint(agent, text):
    """Auto-detect the best skill for this agent + task combination."""
    text_lower = text.lower()
    for (hint_agent, keyword), skill in SKILL_HINTS.items():
        if agent == hint_agent and keyword in text_lower:
            return skill
    return None


def is_agent_busy(agent):
    """Check if agent has an actively executing task."""
    task_dir = f"{AGENT_DIR}/{agent}/tasks"
    if not os.path.exists(task_dir):
        return False
    for fname in os.listdir(task_dir):
        if '.executing' in fname and '.done' not in fname:
            return True
    return False


def _detect_category(text):
    """Detect task category from text for overflow lookup."""
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return category
    return None


def find_overflow_agent(primary_agent, text):
    """Find an available overflow agent if primary is busy.
    Returns (agent, overflow_reason) tuple.
    """
    if not is_agent_busy(primary_agent):
        return primary_agent, None

    category = _detect_category(text)
    if not category:
        return primary_agent, "no category match"

    overflow_agents = OVERFLOW_MAP.get((primary_agent, category), [])
    for overflow in overflow_agents:
        if not is_agent_busy(overflow):
            return overflow, f"{primary_agent} busy, {category} -> {overflow}"

    return primary_agent, "all overflow agents busy"


def _log_overflow(original, overflow, title, reason):
    """Log overflow routing decision to JSONL."""
    import json as _json
    from datetime import datetime as _dt
    log_path = os.path.expanduser("~/.openclaw/agents/main/logs/routing-overflow.jsonl")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        entry = {"ts": _dt.now().isoformat(), "from": original, "to": overflow,
                 "title": title[:100], "reason": reason}
        with open(log_path, "a") as f:
            f.write(_json.dumps(entry) + "\n")
    except Exception:
        pass


MAX_TASK_DEPTH = 3
AGENT_DIR = os.path.expanduser("~/.openclaw/agents")

# --- NOTION INTEGRATION ---
_NOTION_CRED_FILE = os.path.expanduser("~/.openclaw/agents/main/.credentials.env")
_NOTION_CONFIG_FILE = os.path.expanduser("~/.openclaw/config/notion.json")

PRIORITY_TO_NOTION = {
    "high": "P1 — High",
    "normal": "P2 — Normal",
    "low": "P3 — Low",
}

SOURCE_TO_NOTION = {
    "gateway-router": "Kublai",
    "kublai": "Kublai",
    "kublai-actions": "Kublai",
    "kublai-initiative": "Kublai",
    "kublai-reflection": "Kublai",
    "hourly-reflection": "Schedule",
    "self-wake": "Agent",
    "agent": "Agent",
    "agent-self-wake": "Agent",
    "overflow": "Overflow",
    "cron": "Schedule",
    "cli": "Kublai",
    "ci": "CI/CD",
}


def _create_notion_page(title, agent, priority, source, task_file, body=""):
    """Create a Notion page for a newly created task. Fails silently."""
    try:
        # Load credentials
        token = os.environ.get("NOTION_TOKEN")
        if not token:
            for line in open(_NOTION_CRED_FILE):
                if line.startswith("NOTION_KURULTAI_BRIDGE="):
                    token = line.split("=", 1)[1].strip()
                    break
        if not token:
            return

        db_id = os.environ.get("NOTION_TASK_DB")
        if not db_id:
            config = json.loads(open(_NOTION_CONFIG_FILE).read())
            db_id = config["task_board_database_id"]
        if not db_id:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        props = {
            "Task": {"title": [{"text": {"content": title[:100]}}]},
            "Status": {"select": {"name": "Pending"}},
            "Agent": {"select": {"name": agent}},
            "Task File": {"rich_text": [{"text": {"content": task_file}}]},
            "Last Synced": {"date": {"start": now_iso}},
            "Created": {"date": {"start": now_iso[:10]}},
        }
        notion_priority = PRIORITY_TO_NOTION.get(priority)
        if notion_priority:
            props["Priority"] = {"select": {"name": notion_priority}}
        notion_source = SOURCE_TO_NOTION.get(source.lower(), "Agent")
        props["Source"] = {"select": {"name": notion_source}}
        if body:
            props["Description"] = {"rich_text": [{"text": {"content": body[:2000]}}]}

        req_body = json.dumps({"parent": {"database_id": db_id}, "properties": props}).encode()
        req = urllib.request.Request("https://api.notion.com/v1/pages", data=req_body, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Notion-Version", "2022-06-28")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        print(f"NOTION: Created page for {agent}: {title[:60]}")
        return result.get("id")
    except Exception as e:
        print(f"NOTION: Failed to create page (non-blocking): {e}")
        return None


def has_pending_task(agent, title_prefix):
    """Check if an agent already has an uncompleted task with this title prefix."""
    task_dir = f"{AGENT_DIR}/{agent}/tasks"
    if not os.path.exists(task_dir):
        return False
    for fname in os.listdir(task_dir):
        if '.done' in fname:
            continue
        fpath = os.path.join(task_dir, fname)
        try:
            with open(fpath) as f:
                content = f.read(500)
            if f"# Task: {title_prefix}" in content:
                return True
        except Exception:
            continue
    return False


def create_task(title, body, priority="normal", source="task_intake",
                depth=0, agent=None, parent_id=None, skip_duplicate_check=False):
    """Create a task through the canonical pipeline.

    Args:
        title: Task title (used for routing if agent is None)
        body: Task body/description
        priority: "high", "normal", or "low"
        source: Origin of the task
        depth: Current task chain depth
        agent: Target agent (auto-routed from title if None)
        parent_id: Parent task ID for chain tracking
        skip_duplicate_check: Set True to skip the has_pending_task guard

    Returns:
        task_id string on success, None on rejection
    """
    # 1. Validate depth
    if depth >= MAX_TASK_DEPTH:
        print(f"REJECT: depth={depth} >= {MAX_TASK_DEPTH} for '{title[:60]}'")
        return None

    # 2. Route if no agent specified
    if agent is None:
        agent = route_by_text(title)
        if agent == "subagent":
            agent = "kublai"  # Default fallback

    # 2.5. Load balancing — overflow if primary agent is busy
    if agent not in ("kublai", "subagent"):
        original_agent = agent
        agent, overflow_reason = find_overflow_agent(agent, title)
        if overflow_reason and agent != original_agent:
            print(f"OVERFLOW: {original_agent} -> {agent} ({overflow_reason})")
            _log_overflow(original_agent, agent, title, overflow_reason)

    # 2.6. Skill hint detection
    skill_hint = detect_skill_hint(agent, title)

    # 3. Duplicate check
    if not skip_duplicate_check:
        # Use first 40 chars of title as prefix
        prefix = title[:40]
        if has_pending_task(agent, prefix):
            print(f"SKIP: duplicate task for {agent}: '{title[:60]}'")
            return None

    # 4-5. Create in Neo4j + filesystem
    try:
        from neo4j_task_tracker import get_tracker
        tracker = get_tracker()
        task_id = tracker.create_task_full(
            agent=agent,
            title=title,
            body=body,
            priority=priority,
            source=source,
            depth=depth,
            parent_id=parent_id,
            skill_hint=skill_hint,
        )
        if skill_hint:
            print(f"CREATED: {priority} task {task_id} for {agent} (skill: {skill_hint}): {title[:60]}")
        else:
            print(f"CREATED: {priority} task {task_id} for {agent}: {title[:60]}")
        # 6. Create Notion page (non-blocking, best-effort)
        # Find the actual task file just created by create_task_full
        task_dir = f"{AGENT_DIR}/{agent}/tasks"
        task_file = None
        try:
            candidates = sorted(
                [f for f in os.listdir(task_dir) if f.startswith(priority) and f.endswith(".md") and ".done" not in f],
                key=lambda f: os.path.getmtime(os.path.join(task_dir, f)),
                reverse=True,
            )
            if candidates:
                task_file = f"{agent}/tasks/{candidates[0]}"
        except Exception:
            pass
        if task_file:
            _create_notion_page(title, agent, priority, source, task_file, body)
        return task_id
    except Exception as e:
        print(f"ERROR: Neo4j unavailable, falling back to filesystem-only: {e}")
        # Filesystem-only fallback
        import time
        task_dir = f"{AGENT_DIR}/{agent}/tasks"
        os.makedirs(task_dir, exist_ok=True)
        epoch = int(time.time())
        filepath = f"{task_dir}/{priority}-{epoch}.md"
        skill_line = f"skill_hint: {skill_hint}\n" if skill_hint else ""
        content = f"""---
agent: {agent}
priority: {priority}
created: {datetime.now().isoformat()}
source: {source}
depth: {depth}
{skill_line}---

# Task: {title}

{body}
"""
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"CREATED (filesystem-only): {filepath}")
        # 6. Create Notion page (non-blocking, best-effort)
        task_file = f"{agent}/tasks/{priority}-{epoch}.md"
        _create_notion_page(title, agent, priority, source, task_file, body)
        return f"fs-{epoch}"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Task Intake — single entry point for task creation")
    parser.add_argument("--title", required=True, help="Task title")
    parser.add_argument("--body", default="", help="Task body")
    parser.add_argument("--priority", default="normal", choices=["high", "normal", "low"])
    parser.add_argument("--agent", default=None, help="Target agent (auto-routed if omitted)")
    parser.add_argument("--source", default="cli", help="Task source")
    args = parser.parse_args()

    task_id = create_task(
        title=args.title,
        body=args.body or f"Task: {args.title}",
        priority=args.priority,
        source=args.source,
        agent=args.agent,
    )
    if task_id:
        print(f"Task ID: {task_id}")
    else:
        print("Task creation rejected")
        sys.exit(1)
