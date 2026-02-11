"""
Kurultai Notion Task Integration
Reads real tasks from Notion and drives agent conversations.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

# Notion API setup
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")  # Kurultai Business Operations

@dataclass
class NotionTask:
    """Represents a task from Notion."""
    id: str
    title: str
    status: str  # Not Started, In Progress, Done, Blocked
    assignee: str  # Agent name: Kublai, Möngke, etc.
    priority: str
    url: str
    last_edited: datetime
    description: str = ""
    tags: List[str] = None
    due_date: Optional[datetime] = None
    
    def is_assigned_to(self, agent_name: str) -> bool:
        return self.assignee.lower() == agent_name.lower()


class NotionTaskReader:
    """Reads tasks from Notion Kurultai Business Operations database."""
    
    def __init__(self, token: str = None, database_id: str = None):
        self.token = token or NOTION_TOKEN
        self.database_id = database_id or DATABASE_ID
        self.last_check = None
        self.cached_tasks: Dict[str, NotionTask] = {}
        
    def fetch_tasks(self) -> List[NotionTask]:
        """Fetch all tasks from Notion database."""
        import requests
        
        if not self.token or not self.database_id:
            print("⚠️ Notion credentials not configured")
            return []
        
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            tasks = []
            for page in data.get("results", []):
                task = self._parse_task(page)
                if task:
                    tasks.append(task)
            
            self.last_check = datetime.utcnow()
            self._update_cache(tasks)
            return tasks
            
        except Exception as e:
            print(f"❌ Error fetching Notion tasks: {e}")
            return list(self.cached_tasks.values())
    
    def _parse_task(self, page: dict) -> Optional[NotionTask]:
        """Parse a Notion page into a NotionTask."""
        props = page.get("properties", {})
        
        # Extract title
        title = ""
        name_prop = props.get("Name", props.get("Task", {}))
        if "title" in name_prop:
            title_parts = [t.get("plain_text", "") for t in name_prop["title"]]
            title = "".join(title_parts)
        
        if not title:
            return None
        
        # Extract status
        status = "Not Started"
        status_prop = props.get("Status", {})
        if "select" in status_prop and status_prop["select"]:
            status = status_prop["select"].get("name", "Not Started")
        elif "status" in status_prop and status_prop["status"]:
            status = status_prop["status"].get("name", "Not Started")
        
        # Extract assignee
        assignee = "Unassigned"
        assignee_prop = props.get("Assignee", props.get("Assigned to", {}))
        if "people" in assignee_prop and assignee_prop["people"]:
            person = assignee_prop["people"][0]
            assignee = person.get("name", "Unknown")
        elif "select" in assignee_prop and assignee_prop["select"]:
            assignee = assignee_prop["select"].get("name", "Unknown")
        
        # Extract priority
        priority = "Medium"
        priority_prop = props.get("Priority", {})
        if "select" in priority_prop and priority_prop["select"]:
            priority = priority_prop["select"].get("name", "Medium")
        
        # Extract description
        description = ""
        desc_prop = props.get("Description", props.get("Notes", {}))
        if "rich_text" in desc_prop:
            desc_parts = [t.get("plain_text", "") for t in desc_prop["rich_text"]]
            description = "".join(desc_parts)
        
        # Extract tags
        tags = []
        tags_prop = props.get("Tags", props.get("Type", {}))
        if "multi_select" in tags_prop:
            tags = [t.get("name", "") for t in tags_prop["multi_select"]]
        
        # Extract due date
        due_date = None
        date_prop = props.get("Due", props.get("Due Date", {}))
        if "date" in date_prop and date_prop["date"]:
            date_str = date_prop["date"].get("start")
            if date_str:
                due_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        
        return NotionTask(
            id=page.get("id", ""),
            title=title,
            status=status,
            assignee=assignee,
            priority=priority,
            url=page.get("url", ""),
            last_edited=datetime.fromisoformat(
                page.get("last_edited_time", datetime.utcnow().isoformat()).replace("Z", "+00:00")
            ),
            description=description,
            tags=tags,
            due_date=due_date
        )
    
    def _update_cache(self, tasks: List[NotionTask]):
        """Update the task cache."""
        self.cached_tasks = {t.id: t for t in tasks}
    
    def get_tasks_for_agent(self, agent_name: str) -> List[NotionTask]:
        """Get all tasks assigned to a specific agent."""
        all_tasks = self.fetch_tasks()
        return [t for t in all_tasks if t.is_assigned_to(agent_name)]
    
    def get_active_tasks(self) -> List[NotionTask]:
        """Get all tasks that are In Progress or Blocked."""
        all_tasks = self.fetch_tasks()
        return [t for t in all_tasks if t.status in ["In Progress", "Blocked", "In Review"]]
    
    def get_recently_completed(self, hours: int = 24) -> List[NotionTask]:
        """Get tasks completed in the last N hours."""
        all_tasks = self.fetch_tasks()
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [
            t for t in all_tasks 
            if t.status == "Done" and t.last_edited > cutoff
        ]
    
    def detect_changes(self) -> Dict:
        """Detect what changed since last check."""
        if not self.last_check:
            return {"new": [], "updated": [], "completed": []}
        
        current_tasks = self.fetch_tasks()
        changes = {
            "new": [],
            "updated": [],
            "completed": []
        }
        
        current_ids = {t.id for t in current_tasks}
        cached_ids = set(self.cached_tasks.keys())
        
        # New tasks
        for task in current_tasks:
            if task.id not in cached_ids:
                changes["new"].append(task)
            elif task.last_edited > self.cached_tasks[task.id].last_edited:
                # Check if it was just completed
                old_status = self.cached_tasks[task.id].status
                if old_status != "Done" and task.status == "Done":
                    changes["completed"].append(task)
                else:
                    changes["updated"].append(task)
        
        return changes


# Agent name mappings (handles different naming conventions)
AGENT_NAME_MAPPINGS = {
    "Kublai": ["Kublai", "kublai", "Router", "Orchestrator"],
    "Möngke": ["Möngke", "Mongke", "mongke", "Researcher"],
    "Chagatai": ["Chagatai", "chagatai", "Writer", "Scribe"],
    "Temüjin": ["Temüjin", "Temujin", "temujin", "Developer", "Builder"],
    "Jochi": ["Jochi", "jochi", "Analyst", "Security"],
    "Ögedei": ["Ögedei", "Ogedei", "ogedei", "Operations", "Ops"],
}


def normalize_agent_name(notion_name: str) -> Optional[str]:
    """Normalize a Notion assignee name to agent name."""
    for agent, variants in AGENT_NAME_MAPPINGS.items():
        if any(variant.lower() in notion_name.lower() for variant in variants):
            return agent
    return None
