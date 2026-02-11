"""
Discord Action Item Extractor
Analyzes Discord conversations to extract actionable items and sync to Notion.
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from pathlib import Path
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discord.deliberation_client import AgentRole, AGENT_PERSONALITIES

# Notion API setup
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")  # Kurultai Business Operations


class ActionType(Enum):
    """Types of actions extracted from conversations."""
    TASK = "task"           # Specific task to complete
    DECISION = "decision"   # Decision that was made
    FOLLOW_UP = "follow_up" # Follow-up required
    BUG = "bug"             # Bug or issue identified
    IDEA = "idea"           # Idea to explore


@dataclass
class ActionItem:
    """Extracted action item from conversation."""
    id: str
    source_message_id: str
    source_channel: str
    extracted_at: datetime
    action_type: ActionType
    description: str
    assignee: Optional[str]  # Agent name or None
    mentioned_agents: List[str]
    priority: str  # high, medium, low
    confidence: float  # 0.0-1.0 extraction confidence
    context: str  # Surrounding conversation context
    status: str = "pending"  # pending, in_progress, done, dismissed
    notion_page_id: Optional[str] = None


class ActionExtractor:
    """Extracts action items from Discord conversations."""
    
    # Action indicators - phrases that suggest an action item
    ACTION_PATTERNS = {
        ActionType.TASK: [
            r"\b(need to|should|must|will)\s+(\w+)",
            r"\b(todo|to-do|task|action item)\b",
            r"\b(assign|delegate)\s+to\s+@?(\w+)",
            r"\bimplement\b",
            r"\b(build|create|set up|configure)\s+(this|that|it)",
        ],
        ActionType.DECISION: [
            r"\b(decided|decision|agreed|consensus)\b",
            r"\b(we|I)\s+(will|won't|should|agree)\s+(to|that)",
            r"\b(going with|chosen|selected)\b",
        ],
        ActionType.FOLLOW_UP: [
            r"\b(follow[\s-]?up|check (in|on)|revisit)\b",
            r"\b(let's|we should)\s+(discuss|review)\s+(later|tomorrow|next)",
            r"\b(remind|ping)\s+me\b",
        ],
        ActionType.BUG: [
            r"\b(bug|issue|error|broken|failing|crash)\b",
            r"\b(not working|doesn't work|failed)\b",
            r"\b(fix|repair|debug)\s+(this|that|it)\b",
        ],
        ActionType.IDEA: [
            r"\b(idea|concept|proposal|what if|consider)\b",
            r"\b(might|could|should)\s+(be good to|try|explore)\b",
            r"\b(worth|interesting to)\s+(exploring|trying|considering)\b",
        ],
    }
    
    # Priority indicators
    PRIORITY_PATTERNS = {
        "high": [r"\b(urgent|critical|asap|immediately|blocker|P0)\b", r"\b(high priority|important)\b"],
        "low": [r"\b(nice to have|whenever|someday|eventually|P3)\b", r"\b(low priority|minor)\b"],
    }
    
    def __init__(self):
        self.agent_names = [p.name for p in AGENT_PERSONALITIES.values()]
        self.agent_display_names = [p.display_name for p in AGENT_PERSONALITIES.values()]
    
    def extract_actions(self, messages: List[Dict]) -> List[ActionItem]:
        """Extract action items from a list of messages."""
        actions = []
        
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            author = msg.get("author", "")
            msg_id = msg.get("id", "")
            channel = msg.get("channel", "")
            
            # Get context (previous 2 and next 2 messages)
            context_start = max(0, i - 2)
            context_end = min(len(messages), i + 3)
            context = "\n".join([
                f"{m.get('author', '')}: {m.get('content', '')[:100]}"
                for m in messages[context_start:context_end]
            ])
            
            # Detect action type
            action_type, confidence = self._detect_action_type(content)
            if not action_type:
                continue
            
            # Detect assignee
            assignee = self._detect_assignee(content)
            mentioned_agents = self._detect_mentioned_agents(content)
            
            # Detect priority
            priority = self._detect_priority(content)
            
            # Clean up description
            description = self._clean_description(content, action_type)
            
            action = ActionItem(
                id=f"action_{msg_id}_{datetime.utcnow().timestamp()}",
                source_message_id=msg_id,
                source_channel=channel,
                extracted_at=datetime.utcnow(),
                action_type=action_type,
                description=description,
                assignee=assignee,
                mentioned_agents=mentioned_agents,
                priority=priority,
                confidence=confidence,
                context=context
            )
            
            # Only include high-confidence extractions
            if confidence >= 0.6:
                actions.append(action)
        
        return actions
    
    def _detect_action_type(self, content: str) -> tuple[Optional[ActionType], float]:
        """Detect the action type from message content."""
        content_lower = content.lower()
        best_type = None
        best_confidence = 0.0
        
        for action_type, patterns in self.ACTION_PATTERNS.items():
            for pattern in patterns:
                matches = len(re.findall(pattern, content_lower, re.IGNORECASE))
                if matches > 0:
                    confidence = min(0.9, 0.5 + (matches * 0.15))
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_type = action_type
        
        return best_type, best_confidence
    
    def _detect_assignee(self, content: str) -> Optional[str]:
        """Detect if an agent is assigned."""
        content_lower = content.lower()
        
        # Check for explicit assignment
        for name in self.agent_names:
            if f"@{name.lower()}" in content_lower or f"assign to {name.lower()}" in content_lower:
                return name
        
        # Check display names
        for display_name in self.agent_display_names:
            name_part = display_name.split()[0].lower()
            if f"@{name_part}" in content_lower:
                return name_part.capitalize()
        
        return None
    
    def _detect_mentioned_agents(self, content: str) -> List[str]:
        """Detect all mentioned agents."""
        mentioned = []
        content_lower = content.lower()
        
        for name in self.agent_names:
            if name.lower() in content_lower:
                mentioned.append(name)
        
        return mentioned
    
    def _detect_priority(self, content: str) -> str:
        """Detect priority from content."""
        content_lower = content.lower()
        
        for priority, patterns in self.PRIORITY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, content_lower, re.IGNORECASE):
                    return priority
        
        return "medium"
    
    def _clean_description(self, content: str, action_type: ActionType) -> str:
        """Clean and format the action description."""
        # Remove @mentions and URLs
        cleaned = re.sub(r'@\w+', '', content)
        cleaned = re.sub(r'https?://\S+', '[link]', cleaned)
        
        # Truncate if too long
        if len(cleaned) > 200:
            cleaned = cleaned[:197] + "..."
        
        return cleaned.strip()


class NotionActionSync:
    """Syncs action items to Notion database."""
    
    def __init__(self, token: str = None, database_id: str = None):
        self.token = token or NOTION_TOKEN
        self.database_id = database_id or NOTION_DATABASE_ID
    
    def sync_action(self, action: ActionItem) -> Optional[str]:
        """Sync a single action item to Notion."""
        if not self.token or not self.database_id:
            print("⚠️ Notion credentials not configured")
            return None
        
        import requests
        
        # Prepare properties
        properties = {
            "Name": {
                "title": [{"text": {"content": action.description[:100]}}]
            },
            "Status": {
                "select": {"name": "Not Started" if action.status == "pending" else action.status.replace("_", " ").title()}
            },
            "Priority": {
                "select": {"name": action.priority.upper() if action.priority == "high" else action.priority.title()}
            },
            "Type": {
                "select": {"name": action.action_type.value.title()}
            },
        }
        
        # Add assignee if detected
        if action.assignee:
            properties["Assignee"] = {
                "select": {"name": action.assignee}
            }
        
        # Create page
        url = "https://api.notion.com/v1/pages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        data = {
            "parent": {"database_id": self.database_id},
            "properties": properties,
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": f"Source: Discord #{action.source_channel}"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": f"Context:\n{action.context[:500]}"}}]
                    }
                }
            ]
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            action.notion_page_id = result.get("id")
            print(f"✅ Synced action to Notion: {action.description[:50]}...")
            return action.notion_page_id
        except Exception as e:
            print(f"❌ Failed to sync to Notion: {e}")
            return None
    
    def sync_actions(self, actions: List[ActionItem]) -> Dict[str, int]:
        """Sync multiple actions and return summary."""
        results = {"synced": 0, "failed": 0, "skipped": 0}
        
        for action in actions:
            # Skip low confidence items
            if action.confidence < 0.7:
                results["skipped"] += 1
                continue
            
            notion_id = self.sync_action(action)
            if notion_id:
                results["synced"] += 1
            else:
                results["failed"] += 1
        
        return results


class ConversationActionPipeline:
    """Full pipeline: extract actions from conversation and sync to Notion."""
    
    def __init__(self):
        self.extractor = ActionExtractor()
        self.notion_sync = NotionActionSync()
        self.memory_dir = Path("/data/workspace/souls/main/memory/actions")
        self.memory_dir.mkdir(parents=True, exist_ok=True)
    
    def process_conversation(self, messages: List[Dict]) -> List[ActionItem]:
        """Process a conversation and extract/sync actions."""
        # Extract actions
        actions = self.extractor.extract_actions(messages)
        
        if not actions:
            print("ℹ️ No action items detected in conversation")
            return []
        
        print(f"🔍 Extracted {len(actions)} potential action items")
        
        # Filter for high confidence only
        high_confidence = [a for a in actions if a.confidence >= 0.7]
        print(f"✅ {len(high_confidence)} high-confidence actions")
        
        # Sync to Notion
        if NOTION_TOKEN and NOTION_DATABASE_ID:
            results = self.notion_sync.sync_actions(high_confidence)
            print(f"📊 Sync results: {results}")
        
        # Save to memory
        self._save_actions(high_confidence)
        
        return high_confidence
    
    def _save_actions(self, actions: List[ActionItem]):
        """Save extracted actions to memory file."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M")
        filepath = self.memory_dir / f"actions_{timestamp}.json"
        
        data = {
            "extracted_at": datetime.utcnow().isoformat(),
            "count": len(actions),
            "actions": [asdict(a) for a in actions]
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"💾 Saved actions to {filepath}")
    
    def get_recent_actions(self, hours: int = 24) -> List[ActionItem]:
        """Get actions extracted in the last N hours."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        recent_actions = []
        
        for filepath in self.memory_dir.glob("actions_*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    extracted = datetime.fromisoformat(data["extracted_at"])
                    if extracted > cutoff:
                        for action_data in data.get("actions", []):
                            action_data["extracted_at"] = datetime.fromisoformat(action_data["extracted_at"])
                            action_data["action_type"] = ActionType(action_data["action_type"])
                            recent_actions.append(ActionItem(**action_data))
            except Exception:
                continue
        
        return recent_actions


def main():
    """CLI entry point for testing extraction."""
    # Example test messages
    test_messages = [
        {
            "id": "msg1",
            "author": "Kublai 🏛️",
            "channel": "council-chamber",
            "content": "@Temüjin We need to implement the engagement tracker by tomorrow. This is high priority."
        },
        {
            "id": "msg2",
            "author": "Möngke 🔬",
            "channel": "council-chamber",
            "content": "I found an interesting pattern in the Clawnch data. We should explore this further next week."
        },
        {
            "id": "msg3",
            "author": "Jochi 🔍",
            "channel": "council-chamber",
            "content": "There's a bug in the heartbeat writer - it's failing intermittently. Someone needs to fix this."
        },
    ]
    
    pipeline = ConversationActionPipeline()
    actions = pipeline.process_conversation(test_messages)
    
    print("\n" + "="*60)
    print("EXTRACTED ACTIONS:")
    print("="*60)
    for action in actions:
        print(f"\n[{action.action_type.value.upper()}] {action.description[:60]}")
        print(f"  Assignee: {action.assignee or 'Unassigned'}")
        print(f"  Priority: {action.priority}")
        print(f"  Confidence: {action.confidence:.0%}")


if __name__ == "__main__":
    main()
