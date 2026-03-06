#!/usr/bin/env python3
"""
notion-task-sync.py — Sync Kurultai agent tasks to Notion kanban board.

Scans all agent task directories, parses file states, and syncs to the
"Agent Task Board" Notion database. Designed to run from watchdog-gather.sh
or standalone.

Usage:
    python3 notion-task-sync.py              # Full sync
    python3 notion-task-sync.py --dry-run    # Show what would change
    python3 notion-task-sync.py --active     # Only sync active (non-done) tasks
"""

import os
import sys
import json
import re
import glob
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# --- Config ---
CRED_FILE = os.path.expanduser("~/.openclaw/agents/main/.credentials.env")
CONFIG_FILE = os.path.expanduser("~/.openclaw/config/notion.json")


def _load_token():
    """Load Notion token from credentials file (not hardcoded)."""
    token = os.environ.get("NOTION_TOKEN")
    if token:
        return token
    try:
        for line in open(CRED_FILE):
            if line.startswith("NOTION_KURULTAI_BRIDGE="):
                return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    print(f"ERROR: Notion token not found in env or {CRED_FILE}", file=sys.stderr)
    sys.exit(1)


def _load_database_id():
    """Load database ID from config file."""
    db_id = os.environ.get("NOTION_TASK_DB")
    if db_id:
        return db_id
    try:
        config = json.loads(open(CONFIG_FILE).read())
        return config["task_board_database_id"]
    except Exception:
        pass
    print(f"ERROR: Database ID not found in env or {CONFIG_FILE}", file=sys.stderr)
    sys.exit(1)


NOTION_TOKEN = _load_token()
DATABASE_ID = _load_database_id()
AGENTS_DIR = os.path.expanduser("~/.openclaw/agents")
AGENTS = ["kublai", "temujin", "chagatai", "jochi", "mongke", "ogedei"]
STATE_FILE = os.path.expanduser("~/.openclaw/agents/ogedei/workspace/.notion-sync-state.json")

DRY_RUN = "--dry-run" in sys.argv
ACTIVE_ONLY = "--active" in sys.argv
BACKFILL_DESCRIPTIONS = "--backfill-descriptions" in sys.argv
PULL_ENABLED = "--no-pull" not in sys.argv  # Pull from Notion by default

# Reverse map: Notion priority -> filename prefix
PRIORITY_REVERSE = {
    "P0 — Critical": "high",
    "P1 — High": "high",
    "P2 — Normal": "normal",
    "P3 — Low": "low",
}

# Map filename priority prefixes to Notion board select values
PRIORITY_MAP = {
    "high": "P1 — High",
    "normal": "P2 — Normal",
    "auto": "P2 — Normal",
    "direct": "P1 — High",
    "low": "P3 — Low",
    "triage": "P2 — Normal",
}

# Map source strings to valid Notion select values
SOURCE_MAP = {
    "gateway-router": "Kublai",
    "kublai": "Kublai",
    "self-wake": "Agent",
    "agent": "Agent",
    "overflow": "Overflow",
    "cron": "Schedule",
    "ci": "CI/CD",
}


def notion_api(method, endpoint, body=None):
    """Make a Notion API request."""
    url = f"https://api.notion.com/v1/{endpoint}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {NOTION_TOKEN}")
    req.add_header("Notion-Version", "2022-06-28")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"  API error {e.code}: {err_body[:200]}", file=sys.stderr)
        return None


def parse_task_file(filepath, agent):
    """Parse a task file to extract metadata from filename and frontmatter."""
    basename = os.path.basename(filepath)

    # Determine status from filename patterns
    lower = basename.lower()
    if ".executing" in lower:
        status = "Executing"
    elif any(x in lower for x in [".completed", ".resolved", ".obsolete", ".stale", ".failed"]):
        status = "Finished"
    elif ".done" in lower:
        status = "Finished"
    else:
        # No state suffix — could be pending or a reference file
        status = "Pending"

    is_done = ".done" in lower

    # Parse priority from filename prefix
    priority = "normal"
    for p in ["high", "normal", "auto", "direct", "low", "triage"]:
        if lower.startswith(p):
            priority = p
            break

    # Read frontmatter for title, metadata, and full description
    title = basename
    source = ""
    created_str = ""
    description = ""
    notion_page_id = ""
    try:
        with open(filepath, "r") as f:
            content = f.read(8000)
        body = content  # full content after frontmatter
        # Parse YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm = parts[1]
                body = parts[2].strip()
                for line in fm.strip().split("\n"):
                    if line.startswith("source:"):
                        source = line.split(":", 1)[1].strip()
                    if line.startswith("created:"):
                        created_str = line.split(":", 1)[1].strip()
                    if line.startswith("notion_page_id:"):
                        notion_page_id = line.split(":", 1)[1].strip()
        # Extract title from markdown heading
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                title = line[2:].strip()
                # Remove "Task: " prefix if present
                if title.lower().startswith("task: "):
                    title = title[6:]
                break
        # Extract description: everything after the title line in the body
        lines = body.split("\n")
        found_title = False
        desc_lines = []
        for line in lines:
            if not found_title:
                if line.strip().startswith("# "):
                    found_title = True
                continue
            desc_lines.append(line)
        description = "\n".join(desc_lines).strip()
    except Exception:
        pass

    # Build a stable key from agent + filename (without state suffixes)
    # Strip all state suffixes to get the base task ID
    base_name = basename
    for suffix in [".done", ".completed", ".failed", ".stale", ".resolved",
                   ".obsolete", ".executing", ".retry-1", ".retry-2",
                   ".stale-cleared", ".md"]:
        base_name = base_name.replace(suffix, "")
    task_key = f"{agent}/{base_name}"

    return {
        "task_key": task_key,
        "title": title[:100],  # Notion title limit
        "status": status,
        "agent": agent,
        "priority": priority,
        "source": source,
        "created": created_str,
        "task_file": f"{agent}/tasks/{basename}",
        "is_done": is_done,
        "filepath": filepath,
        "description": description,
        "notion_page_id": notion_page_id,
    }


def get_all_notion_pages():
    """Fetch all pages from the Notion database."""
    pages = []
    start_cursor = None
    while True:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        result = notion_api("POST", f"databases/{DATABASE_ID}/query", body)
        if not result:
            break
        pages.extend(result.get("results", []))
        if result.get("has_more"):
            start_cursor = result["next_cursor"]
        else:
            break
    return pages


def extract_notion_task_key(page):
    """Extract the task_key from a Notion page's Task File property."""
    tf = page.get("properties", {}).get("Task File", {})
    rt = tf.get("rich_text", [])
    if rt:
        text = rt[0].get("plain_text", "")
        # Convert task_file path back to task_key
        # e.g. "ogedei/tasks/normal-1772768782.executing.md" -> "ogedei/normal-1772768782"
        base = text.replace("/tasks/", "/")
        for suffix in [".done", ".completed", ".failed", ".stale", ".resolved",
                       ".obsolete", ".executing", ".retry-1", ".retry-2",
                       ".stale-cleared", ".md"]:
            base = base.replace(suffix, "")
        return base
    return None


def _description_to_blocks(description):
    """Convert markdown description text to Notion block objects.

    Splits into paragraph blocks, respecting headings (## -> heading_2, ### -> heading_3)
    and bullet lists (lines starting with - or *).
    Notion text blocks have a 2000 char limit per rich_text element.
    """
    blocks = []
    for line in description.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"text": {"content": stripped[4:][:2000]}}]},
            })
        elif stripped.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"text": {"content": stripped[3:][:2000]}}]},
            })
        elif stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"text": {"content": stripped[2:][:2000]}}]},
            })
        elif stripped[0].isdigit() and ". " in stripped[:5]:
            text = stripped.split(". ", 1)[1] if ". " in stripped else stripped
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": [{"text": {"content": text[:2000]}}]},
            })
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": stripped[:2000]}}]},
            })
    # Notion limit: max 100 blocks per request
    return blocks[:100]


def create_notion_page(task):
    """Create a new page in the Notion database."""
    props = {
        "Task": {"title": [{"text": {"content": task["title"]}}]},
        "Status": {"select": {"name": task["status"]}},
        "Agent": {"select": {"name": task["agent"]}},
        "Task File": {"rich_text": [{"text": {"content": task["task_file"]}}]},
        "Last Synced": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
    }
    notion_priority = PRIORITY_MAP.get(task["priority"])
    if notion_priority:
        props["Priority"] = {"select": {"name": notion_priority}}
    if task["source"]:
        notion_source = SOURCE_MAP.get(task["source"].lower(), "Agent")
        props["Source"] = {"select": {"name": notion_source}}
    if task["created"]:
        try:
            # Parse ISO datetime, truncate to date for Notion
            dt = task["created"][:10]
            props["Created"] = {"date": {"start": dt}}
        except Exception:
            pass

    if task["status"] == "Finished":
        props["Completed"] = {"date": {"start": datetime.now(timezone.utc).isoformat()}}

    # Add description as property (truncated to 2000 chars for rich_text limit)
    if task.get("description"):
        props["Description"] = {"rich_text": [{"text": {"content": task["description"][:2000]}}]}

    body = {"parent": {"database_id": DATABASE_ID}, "properties": props}

    # Add full description as page body content (supports longer text)
    if task.get("description"):
        body["children"] = _description_to_blocks(task["description"])

    return notion_api("POST", "pages", body)


def update_notion_page(page_id, task, existing_status):
    """Update an existing Notion page if status changed."""
    props = {
        "Status": {"select": {"name": task["status"]}},
        "Task File": {"rich_text": [{"text": {"content": task["task_file"]}}]},
        "Last Synced": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
    }
    if task["status"] == "Finished" and existing_status != "Finished":
        props["Completed"] = {"date": {"start": datetime.now(timezone.utc).isoformat()}}
    # Sync description if present
    if task.get("description"):
        props["Description"] = {"rich_text": [{"text": {"content": task["description"][:2000]}}]}
    body = {"properties": props}
    return notion_api("PATCH", f"pages/{page_id}", body)


def archive_notion_page(page_id):
    """Archive a Notion page (task no longer exists on filesystem). Ignores already-archived."""
    result = notion_api("PATCH", f"pages/{page_id}", {"archived": True})
    if result is None:
        print(f"    (page {page_id[:8]}... may already be archived)", file=sys.stderr)
    return result


def load_sync_state():
    """Load previous sync state for delta detection."""
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_sync_state(state):
    """Save sync state."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def pull_from_notion():
    """Pull new tasks from Notion and create task files for agents.

    Queries for pages where:
    - Status = "Pending"
    - Task File is empty (not yet synced to filesystem)
    - Agent is assigned
    - Not archived

    Returns count of tasks pulled.
    """
    # Query Notion for pending tasks without a Task File
    body = {
        "filter": {
            "and": [
                {"property": "Status", "select": {"equals": "Pending"}},
                {"property": "Task File", "rich_text": {"is_empty": True}},
            ]
        },
        "page_size": 20,
    }
    result = notion_api("POST", f"databases/{DATABASE_ID}/query", body)
    if not result:
        return 0

    pages = result.get("results", [])
    if not pages:
        return 0

    pulled = 0
    for page in pages:
        if page.get("archived"):
            continue

        props = page.get("properties", {})

        # Extract agent assignment
        agent_prop = props.get("Agent", {}).get("select")
        if not agent_prop:
            print(f"  SKIP PULL: no agent assigned (page {page['id'][:8]})")
            continue
        agent = agent_prop["name"].lower()
        if agent not in AGENTS:
            print(f"  SKIP PULL: unknown agent '{agent}' (page {page['id'][:8]})")
            continue

        # Extract title
        title_prop = props.get("Task", {}).get("title", [])
        title = title_prop[0]["plain_text"] if title_prop else "Untitled"

        # Extract priority
        priority_prop = props.get("Priority", {}).get("select")
        priority_name = priority_prop["name"] if priority_prop else "P2 — Normal"
        prefix = PRIORITY_REVERSE.get(priority_name, "normal")

        # Extract description
        desc_rt = props.get("Description", {}).get("rich_text", [])
        description = desc_rt[0]["plain_text"] if desc_rt else ""

        # Extract type/project for context
        type_prop = props.get("Type", {}).get("select")
        task_type = type_prop["name"] if type_prop else ""
        project_prop = props.get("Project", {}).get("select")
        project = project_prop["name"] if project_prop else ""

        # Build task file
        timestamp = int(time.time())
        safe_title = re.sub(r'[^\w\-]', '_', title)[:60]
        filename = f"{prefix}-notion-{safe_title}-{timestamp}.md"
        task_dir = os.path.join(AGENTS_DIR, agent, "tasks")
        os.makedirs(task_dir, exist_ok=True)
        task_path = os.path.join(task_dir, filename)
        task_file_ref = f"{agent}/tasks/{filename}"

        # Write task file with frontmatter
        content = f"""---
agent: {agent}
priority: {prefix}
created: {datetime.now(timezone.utc).isoformat()}
source: notion
notion_page_id: {page['id']}
"""
        if task_type:
            content += f"type: {task_type}\n"
        if project:
            content += f"project: {project}\n"
        content += f"""---

# Task: {title}
"""
        if description:
            content += f"\n{description}\n"
        content += f"""
Execute this task completely using your tools. Read files, write code, run commands, verify your work.
"""

        print(f"  PULL: {agent}/{filename} <- Notion [{priority_name}] \"{title[:40]}\"")

        if not DRY_RUN:
            with open(task_path, "w") as f:
                f.write(content)

            # Update Notion page with the Task File reference so it won't be pulled again
            notion_api("PATCH", f"pages/{page['id']}", {
                "properties": {
                    "Task File": {"rich_text": [{"text": {"content": task_file_ref}}]},
                    "Status": {"select": {"name": "Executing"}},
                    "Last Synced": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
                }
            })
            time.sleep(0.35)

        pulled += 1

    return pulled


def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] notion-task-sync: starting {'(dry-run)' if DRY_RUN else ''}")

    # 0. Pull new tasks from Notion -> filesystem
    pulled = 0
    if PULL_ENABLED:
        try:
            pulled = pull_from_notion()
            if pulled > 0:
                print(f"  Pulled {pulled} task(s) from Notion")
        except Exception as e:
            print(f"  Pull error: {e}", file=sys.stderr)

    # 1. Scan all agent task directories
    all_tasks = {}
    for agent in AGENTS:
        task_dir = os.path.join(AGENTS_DIR, agent, "tasks")
        if not os.path.isdir(task_dir):
            continue
        for f in os.listdir(task_dir):
            fpath = os.path.join(task_dir, f)
            if not os.path.isfile(fpath):
                continue
            if f.startswith("."):
                continue
            task = parse_task_file(fpath, agent)
            if ACTIVE_ONLY and task["is_done"] and not task["notion_page_id"]:
                continue  # Skip done tasks unless they came from Notion (need status push-back)
            all_tasks[task["task_key"]] = task

    print(f"  Found {len(all_tasks)} tasks on filesystem")
    by_status = {}
    for t in all_tasks.values():
        by_status.setdefault(t["status"], []).append(t)
    for s, tasks in sorted(by_status.items()):
        print(f"    {s}: {len(tasks)}")

    # 2. Fetch existing Notion pages
    notion_pages = get_all_notion_pages()
    print(f"  Found {len(notion_pages)} pages in Notion")

    # Build index by task_key
    notion_by_key = {}
    for page in notion_pages:
        key = extract_notion_task_key(page)
        if key:
            # Extract current status
            status_prop = page.get("properties", {}).get("Status", {}).get("select")
            current_status = status_prop.get("name") if status_prop else None
            desc_rt = page.get("properties", {}).get("Description", {}).get("rich_text", [])
            has_desc = bool(desc_rt and desc_rt[0].get("plain_text", "").strip())
            notion_by_key[key] = {
                "page_id": page["id"],
                "status": current_status,
                "archived": page.get("archived", False),
                "has_description": has_desc,
            }

    # 2b. Direct Notion update for tasks that were pulled from Notion
    #     These have notion_page_id in frontmatter — update status directly
    notion_direct_updated = set()
    for key, task in all_tasks.items():
        page_id = task.get("notion_page_id")
        if not page_id:
            continue
        # Check current Notion status for this page
        current = notion_by_key.get(key, {})
        if current.get("status") == task["status"]:
            continue  # Already in sync
        print(f"  NOTION-DIRECT: {task['agent']}/{task['title'][:40]} -> {task['status']}")
        if not DRY_RUN:
            update_notion_page(page_id, task, current.get("status", "Pending"))
            time.sleep(0.35)
        notion_direct_updated.add(key)

    # 3. Sync: create new, update changed, archive removed
    created = 0
    updated = 0
    archived = 0
    unchanged = 0

    for key, task in all_tasks.items():
        if key in notion_direct_updated:
            updated += 1
            continue  # Already handled above
        if key in notion_by_key:
            existing = notion_by_key[key]
            needs_update = existing["status"] != task["status"]
            # Backfill: update description even if status unchanged
            if BACKFILL_DESCRIPTIONS and task.get("description") and not existing.get("has_description"):
                needs_update = True
            if needs_update:
                reason = f"[{existing['status']} -> {task['status']}]" if existing["status"] != task["status"] else "[backfill desc]"
                print(f"  UPDATE: {task['agent']}/{task['title'][:40]} {reason}")
                if not DRY_RUN:
                    update_notion_page(existing["page_id"], task, existing["status"])
                    time.sleep(0.35)  # Rate limit
                updated += 1
            else:
                unchanged += 1
        else:
            print(f"  CREATE: {task['agent']}/{task['title'][:40]} [{task['status']}]")
            if not DRY_RUN:
                create_notion_page(task)
                time.sleep(0.35)  # Rate limit
            created += 1

    # Archive Notion pages whose tasks no longer exist on filesystem
    for key, info in notion_by_key.items():
        if key not in all_tasks and not info["archived"]:
            print(f"  ARCHIVE: {key}")
            if not DRY_RUN:
                archive_notion_page(info["page_id"])
                time.sleep(0.35)
            archived += 1

    print(f"  Summary: {created} created, {updated} updated, "
          f"{archived} archived, {unchanged} unchanged")

    # 4. Save sync state
    if not DRY_RUN:
        state = {
            "last_sync": datetime.now(timezone.utc).isoformat(),
            "task_count": len(all_tasks),
            "created": created,
            "updated": updated,
            "archived": archived,
            "pulled": pulled if PULL_ENABLED else 0,
            "database_id": DATABASE_ID,
        }
        save_sync_state(state)

    return 0


if __name__ == "__main__":
    sys.exit(main())
