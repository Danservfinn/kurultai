#!/usr/bin/env python3
"""
Conversation Logger - Automatic logging of all human conversations with privacy controls

This module provides:
1. Automatic conversation capture from Signal and other channels
2. Privacy controls (file permissions, access checks)
3. Search and retrieval functionality
4. Integration with human_profile_memory.py

Usage:
    from conversation_logger import log_conversation, search_conversations

    # Log a message
    log_conversation("+19194133445", {
        "direction": "inbound",
        "content": "Hello world",
        "channel": "signal"
    })

    # Search conversations
    results = search_conversations("+19194133445", "authentication")
"""

import os
import re
import json
import stat
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

# Import existing memory system
import sys
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from human_profile_memory import HumanProfileMemory

# Configuration
MEMORY_DIR = Path.home() / ".openclaw" / "agents" / "main" / "memory" / "humans"
ARCHIVE_DIR = MEMORY_DIR / "archive"
MAX_CONVERSATIONS_IN_FILE = 50
MAX_ARCHIVE_FILES = 12  # Keep up to 12 monthly archives


class ConversationLogger:
    """Manages persistent conversation storage with privacy controls."""

    def __init__(self, agent_name: str = "main"):
        self.agent_name = agent_name
        self.memory = HumanProfileMemory(agent_name)
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create directories with proper permissions."""
        # Main memory dir
        self.memory.memory_dir.mkdir(parents=True, exist_ok=True)

        # Archive dir
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

        # Set directory permissions to 700 (owner only)
        os.chmod(self.memory.memory_dir, stat.S_IRWXU)
        os.chmod(ARCHIVE_DIR, stat.S_IRWXU)

    def _set_file_permissions(self, file_path: Path) -> None:
        """Set file permissions to 600 (owner read/write only)."""
        if file_path.exists():
            os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)

    def _extract_topics(self, content: str) -> List[str]:
        """Extract key topics from message content."""
        topics = []

        # Technical keywords
        tech_keywords = [
            "authentication", "security", "deploy", "bug", "feature",
            "database", "api", "frontend", "backend", "performance",
            "test", "review", "merge", "release", "config"
        ]

        # Action keywords
        action_keywords = [
            "create", "update", "delete", "fix", "build", "implement",
            "schedule", "cancel", "remind", "notify"
        ]

        content_lower = content.lower()

        for keyword in tech_keywords + action_keywords:
            if keyword in content_lower:
                topics.append(keyword)

        return topics[:5]  # Limit to 5 topics

    def _extract_action_items(self, content: str) -> List[str]:
        """Extract potential action items from message."""
        action_items = []

        # Patterns for action items
        patterns = [
            r"(?:need to|should|must|have to)\s+([^.!?]+)",
            r"(?:todo|task|action):\s*([^.!?]+)",
            r"\[([^\]]+)\]",  # [bracketed items]
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            action_items.extend(matches[:3])

        return action_items[:5]

    def _detect_context(self, content: str) -> str:
        """Detect the context type of a message."""
        content_lower = content.lower()

        # Calendar-related
        calendar_words = ["event", "meeting", "schedule", "calendar", "rsvp", "tomorrow", "monday", "tuesday"]
        if any(w in content_lower for w in calendar_words):
            return "calendar"

        # Task-related
        task_words = ["task", "todo", "implement", "fix", "bug", "feature", "build"]
        if any(w in content_lower for w in task_words):
            return "task"

        # Code-related
        code_words = ["code", "function", "class", "api", "pr", "merge", "commit"]
        if any(w in content_lower for w in code_words):
            return "code"

        # Business-related
        biz_words = ["revenue", "customer", "user", "sales", "pricing", "subscription"]
        if any(w in content_lower for w in biz_words):
            return "business"

        return "general"

    def _analyze_sentiment(self, content: str) -> str:
        """Simple sentiment analysis."""
        positive_words = ["great", "awesome", "thanks", "love", "perfect", "excellent", "good"]
        negative_words = ["bad", "broken", "fail", "error", "problem", "issue", "hate", "frustrated"]

        content_lower = content.lower()

        positive_count = sum(1 for w in positive_words if w in content_lower)
        negative_count = sum(1 for w in negative_words if w in content_lower)

        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        return "neutral"

    def _should_archive(self, phone_number: str) -> bool:
        """Check if profile needs archiving (50+ conversations)."""
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return False

        conversations = profile.get("conversations", [])
        return len(conversations) >= MAX_CONVERSATIONS_IN_FILE

    def _archive_old_conversations(self, phone_number: str) -> None:
        """Archive older conversations to a separate file."""
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return

        conversations = profile.get("conversations", [])
        if len(conversations) < MAX_CONVERSATIONS_IN_FILE:
            return

        # Keep last 30 in main file, archive the rest
        to_archive = conversations[:-30]
        to_keep = conversations[-30:]

        if not to_archive:
            return

        # Write archive file
        normalized_id = self.memory._normalize_id(phone_number)
        archive_date = datetime.now().strftime("%Y-%m")
        archive_file = ARCHIVE_DIR / f"{normalized_id}-archive-{archive_date}.json"

        # Load existing archive if any
        existing_archive = []
        if archive_file.exists():
            try:
                existing_archive = json.loads(archive_file.read_text())
            except (json.JSONDecodeError, Exception):
                existing_archive = []

        # Append new archived conversations
        existing_archive.extend(to_archive)

        # Write archive
        archive_file.write_text(json.dumps(existing_archive, indent=2, default=str))
        self._set_file_permissions(archive_file)

        # Update profile with remaining conversations
        profile["conversations"] = to_keep
        self.memory.write_profile(phone_number, profile)

        # Clean up old archives (keep only MAX_ARCHIVE_FILES)
        self._cleanup_old_archives(phone_number)

    def _cleanup_old_archives(self, phone_number: str) -> None:
        """Remove old archive files beyond retention limit."""
        normalized_id = self.memory._normalize_id(phone_number)
        archives = sorted(ARCHIVE_DIR.glob(f"{normalized_id}-archive-*.json"))

        # Remove oldest archives beyond limit
        while len(archives) > MAX_ARCHIVE_FILES:
            archives[0].unlink()
            archives = archives[1:]

    def log_conversation(
        self,
        phone_number: str,
        direction: str,
        content: str,
        channel: str = "signal",
        message_id: Optional[str] = None,
        related_tasks: Optional[List[str]] = None,
        related_events: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log a conversation with a human.

        Args:
            phone_number: E.164 phone number
            direction: "inbound" or "outbound"
            content: Message content
            channel: Communication channel (signal, email, etc.)
            message_id: Optional message ID for deduplication
            related_tasks: List of related task IDs
            related_events: List of related event names/IDs
            metadata: Additional metadata

        Returns:
            True if logged successfully
        """
        # Check if we need to archive first
        if self._should_archive(phone_number):
            self._archive_old_conversations(phone_number)

        # Build conversation entry
        conversation = {
            "date": datetime.now().isoformat(),
            "channel": channel,
            "direction": direction,
            "content": content[:1000],  # Limit content length
            "topics": self._extract_topics(content),
            "context": self._detect_context(content),
            "action_items": self._extract_action_items(content),
            "sentiment": self._analyze_sentiment(content),
        }

        if message_id:
            conversation["message_id"] = message_id

        if related_tasks:
            conversation["related_tasks"] = related_tasks

        if related_events:
            conversation["related_events"] = related_events

        if metadata:
            conversation["metadata"] = metadata

        # Add to profile
        success = self.memory.add_conversation(phone_number, conversation)

        # Ensure proper file permissions
        file_path = self.memory._get_file_path(phone_number)
        self._set_file_permissions(file_path)

        return success

    def search_conversations(
        self,
        phone_number: str,
        query: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search a human's conversations for a query.

        Args:
            phone_number: Phone number to search
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching conversations
        """
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return []

        conversations = profile.get("conversations", [])
        query_lower = query.lower()

        results = []
        for conv in conversations:
            # Search in content, topics, action items
            content = conv.get("content", "").lower()
            topics = " ".join(conv.get("topics", [])).lower()
            action_items = " ".join(conv.get("action_items", [])).lower()

            if query_lower in content or query_lower in topics or query_lower in action_items:
                results.append(conv)

                if len(results) >= limit:
                    break

        return results

    def search_all_conversations(
        self,
        query: str,
        limit: int = 50
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search across all conversations (admin function).

        Args:
            query: Search query
            limit: Maximum results per person

        Returns:
            Dict mapping phone numbers to matching conversations
        """
        results = {}

        for phone_number in self.memory.list_profiles():
            matches = self.search_conversations(phone_number, query, limit)
            if matches:
                results[phone_number] = matches

        return results

    def get_conversation_stats(self, phone_number: str) -> Dict[str, Any]:
        """Get statistics about a human's conversations."""
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return {"total": 0}

        conversations = profile.get("conversations", [])

        stats = {
            "total": len(conversations),
            "channels": {},
            "contexts": {},
            "sentiments": {"positive": 0, "negative": 0, "neutral": 0},
            "first_conversation": None,
            "last_conversation": None,
        }

        for conv in conversations:
            # Count by channel
            channel = conv.get("channel", "unknown")
            stats["channels"][channel] = stats["channels"].get(channel, 0) + 1

            # Count by context
            context = conv.get("context", "unknown")
            stats["contexts"][context] = stats["contexts"].get(context, 0) + 1

            # Count by sentiment
            sentiment = conv.get("sentiment", "neutral")
            stats["sentiments"][sentiment] = stats["sentiments"].get(sentiment, 0) + 1

        if conversations:
            stats["first_conversation"] = conversations[0].get("date")
            stats["last_conversation"] = conversations[-1].get("date")

        return stats

    def export_conversations(self, phone_number: str) -> Optional[str]:
        """Export all conversations for a user (privacy request)."""
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return None

        conversations = profile.get("conversations", [])

        # Also load archived conversations
        normalized_id = self.memory._normalize_id(phone_number)
        archives = sorted(ARCHIVE_DIR.glob(f"{normalized_id}-archive-*.json"))

        all_conversations = []
        for archive_file in archives:
            try:
                archived = json.loads(archive_file.read_text())
                all_conversations.extend(archived)
            except Exception:
                pass

        all_conversations.extend(conversations)

        return json.dumps(all_conversations, indent=2, default=str)

    def delete_all_conversations(self, phone_number: str) -> bool:
        """Delete all conversations for a user (privacy request)."""
        # Delete main profile conversations
        profile = self.memory.read_profile(phone_number)
        if profile:
            profile["conversations"] = []
            self.memory.write_profile(phone_number, profile)

        # Delete all archive files
        normalized_id = self.memory._normalize_id(phone_number)
        for archive_file in ARCHIVE_DIR.glob(f"{normalized_id}-archive-*.json"):
            archive_file.unlink()

        return True

    def log_human_conversation(
        self,
        phone_number: str,
        direction: str,
        content: str,
        channel: str = "signal",
        context: Optional[str] = None,
        topics: Optional[List[str]] = None,
        action_items: Optional[List[str]] = None,
        sentiment: Optional[str] = None,
        related_events: Optional[List[str]] = None,
        related_tasks: Optional[List[str]] = None,
        message_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Comprehensive conversation logging with full context extraction.

        This is the primary method for logging human conversations with
        automatic extraction of topics, action items, sentiment, and
        optional linking to related events/tasks.

        Args:
            phone_number: E.164 phone number
            direction: "inbound" or "outbound"
            content: Message content
            channel: Communication channel (signal, email, etc.)
            context: Override auto-detected context
            topics: Override auto-extracted topics
            action_items: Override auto-extracted action items
            sentiment: Override auto-detected sentiment
            related_events: List of related calendar event names/IDs
            related_tasks: List of related task IDs
            message_id: Optional message ID for deduplication
            metadata: Additional metadata dict

        Returns:
            True if logged successfully
        """
        # Check if we need to archive first
        if self._should_archive(phone_number):
            self._archive_old_conversations(phone_number)

        # Use provided values or auto-extract
        detected_context = context or self._detect_context(content)
        detected_topics = topics if topics is not None else self._extract_topics(content)
        detected_action_items = action_items if action_items is not None else self._extract_action_items(content)
        detected_sentiment = sentiment or self._analyze_sentiment(content)

        # Build comprehensive conversation entry
        conversation = {
            "date": datetime.now().isoformat(),
            "channel": channel,
            "direction": direction,
            "content": content[:2000],  # Increased limit for full context
            "context": detected_context,
            "topics": detected_topics,
            "action_items": detected_action_items,
            "sentiment": detected_sentiment,
        }

        if message_id:
            conversation["message_id"] = message_id

        if related_events:
            conversation["related_events"] = related_events

        if related_tasks:
            conversation["related_tasks"] = related_tasks

        if metadata:
            conversation["metadata"] = metadata

        # Add to profile
        success = self.memory.add_conversation(phone_number, conversation)

        # Ensure proper file permissions
        file_path = self.memory._get_file_path(phone_number)
        self._set_file_permissions(file_path)

        return success

    def get_recent_conversations(
        self,
        phone_number: str,
        limit: int = 10,
        context_filter: Optional[str] = None,
        sentiment_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent conversations with optional filtering.

        Args:
            phone_number: Phone number
            limit: Maximum conversations to return
            context_filter: Filter by context type
            sentiment_filter: Filter by sentiment

        Returns:
            List of conversation dicts
        """
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return []

        conversations = profile.get("conversations", [])

        # Apply filters
        if context_filter:
            conversations = [c for c in conversations if c.get("context") == context_filter]

        if sentiment_filter:
            conversations = [c for c in conversations if c.get("sentiment") == sentiment_filter]

        # Return most recent first, limited
        return list(reversed(conversations[-limit:]))

    def get_action_items(self, phone_number: str, pending_only: bool = True) -> List[Dict[str, Any]]:
        """
        Extract all action items from conversations.

        Args:
            phone_number: Phone number
            pending_only: Only return items not marked as completed

        Returns:
            List of action item dicts with conversation context
        """
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return []

        conversations = profile.get("conversations", [])
        all_action_items = []

        for conv in conversations:
            items = conv.get("action_items", [])
            for item in items:
                action_item = {
                    "item": item,
                    "date": conv.get("date"),
                    "context": conv.get("context"),
                    "completed": item in conv.get("completed_items", [])
                }
                if not pending_only or not action_item["completed"]:
                    all_action_items.append(action_item)

        return all_action_items

    def link_to_event(self, phone_number: str, conversation_date: str, event_name: str) -> bool:
        """
        Link a conversation to a calendar event.

        Args:
            phone_number: Phone number
            conversation_date: ISO date string of conversation
            event_name: Name of the event to link

        Returns:
            True if linked successfully
        """
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return False

        conversations = profile.get("conversations", [])
        for conv in conversations:
            if conv.get("date") == conversation_date:
                if "related_events" not in conv:
                    conv["related_events"] = []
                if event_name not in conv["related_events"]:
                    conv["related_events"].append(event_name)
                self.memory.write_profile(phone_number, profile)
                return True

        return False

    def link_to_task(self, phone_number: str, conversation_date: str, task_id: str) -> bool:
        """
        Link a conversation to a task.

        Args:
            phone_number: Phone number
            conversation_date: ISO date string of conversation
            task_id: Task ID to link

        Returns:
            True if linked successfully
        """
        profile = self.memory.read_profile(phone_number)
        if not profile:
            return False

        conversations = profile.get("conversations", [])
        for conv in conversations:
            if conv.get("date") == conversation_date:
                if "related_tasks" not in conv:
                    conv["related_tasks"] = []
                if task_id not in conv["related_tasks"]:
                    conv["related_tasks"].append(task_id)
                self.memory.write_profile(phone_number, profile)
                return True

        return False


# Singleton instance for convenience
_logger_instance: Optional[ConversationLogger] = None


def get_logger() -> ConversationLogger:
    """Get or create the singleton logger instance."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = ConversationLogger()
    return _logger_instance


def log_conversation(
    phone_number: str,
    direction: str,
    content: str,
    channel: str = "signal",
    **kwargs
) -> bool:
    """
    Convenience function to log a conversation.

    Args:
        phone_number: E.164 phone number
        direction: "inbound" or "outbound"
        content: Message content
        channel: Communication channel
        **kwargs: Additional arguments passed to ConversationLogger.log_conversation

    Returns:
        True if logged successfully
    """
    return get_logger().log_conversation(phone_number, direction, content, channel, **kwargs)


def log_inbound(phone_number: str, content: str, channel: str = "signal", **kwargs) -> bool:
    """Log an inbound message."""
    return log_conversation(phone_number, "inbound", content, channel, **kwargs)


def log_outbound(phone_number: str, content: str, channel: str = "signal", **kwargs) -> bool:
    """Log an outbound message."""
    return log_conversation(phone_number, "outbound", content, channel, **kwargs)


def search_conversations(phone_number: str, query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search a human's conversations."""
    return get_logger().search_conversations(phone_number, query, limit)


def search_all_conversations(query: str, limit: int = 50) -> Dict[str, List[Dict[str, Any]]]:
    """Search across all conversations (admin)."""
    return get_logger().search_all_conversations(query, limit)


def get_conversation_stats(phone_number: str) -> Dict[str, Any]:
    """Get conversation statistics."""
    return get_logger().get_conversation_stats(phone_number)


def export_conversations(phone_number: str) -> Optional[str]:
    """Export all conversations (privacy request)."""
    return get_logger().export_conversations(phone_number)


def delete_all_conversations(phone_number: str) -> bool:
    """Delete all conversations (privacy request)."""
    return get_logger().delete_all_conversations(phone_number)


def log_human_conversation(
    phone_number: str,
    direction: str,
    content: str,
    channel: str = "signal",
    context: Optional[str] = None,
    topics: Optional[List[str]] = None,
    action_items: Optional[List[str]] = None,
    sentiment: Optional[str] = None,
    related_events: Optional[List[str]] = None,
    related_tasks: Optional[List[str]] = None,
    message_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Comprehensive conversation logging with full context extraction.

    This is the primary function for logging human conversations with
    automatic extraction of topics, action items, sentiment, and
    optional linking to related events/tasks.

    Args:
        phone_number: E.164 phone number
        direction: "inbound" or "outbound"
        content: Message content
        channel: Communication channel (signal, email, etc.)
        context: Override auto-detected context (calendar, task, code, business, general)
        topics: Override auto-extracted topics
        action_items: Override auto-extracted action items
        sentiment: Override auto-detected sentiment (positive, negative, neutral)
        related_events: List of related calendar event names/IDs
        related_tasks: List of related task IDs
        message_id: Optional message ID for deduplication
        metadata: Additional metadata dict

    Returns:
        True if logged successfully

    Example:
        log_human_conversation(
            phone_number="+19194133445",
            direction="inbound",
            content="Can you schedule a meeting for Friday?",
            channel="signal",
            related_events=["Team Standup"],
            related_tasks=["task-abc123"]
        )
    """
    return get_logger().log_human_conversation(
        phone_number=phone_number,
        direction=direction,
        content=content,
        channel=channel,
        context=context,
        topics=topics,
        action_items=action_items,
        sentiment=sentiment,
        related_events=related_events,
        related_tasks=related_tasks,
        message_id=message_id,
        metadata=metadata
    )


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Conversation Logger CLI")
    parser.add_argument("command", choices=["log", "search", "stats", "export", "list"])
    parser.add_argument("--phone", "-p", help="Phone number (E.164)")
    parser.add_argument("--query", "-q", help="Search query")
    parser.add_argument("--content", "-c", help="Message content")
    parser.add_argument("--direction", "-d", choices=["inbound", "outbound"], default="inbound")

    args = parser.parse_args()

    logger = ConversationLogger()

    if args.command == "list":
        profiles = logger.memory.list_profiles()
        print("Profiles with conversations:")
        for p in profiles:
            stats = logger.get_conversation_stats(p)
            print(f"  {p}: {stats['total']} conversations")
        sys.exit(0)

    if not args.phone:
        print("Error: --phone is required for this command")
        sys.exit(1)

    if args.command == "log":
        if not args.content:
            print("Error: --content is required for logging")
            sys.exit(1)
        logger.log_conversation(args.phone, args.direction, args.content)
        print(f"Logged {args.direction} message for {args.phone}")

    elif args.command == "search":
        if not args.query:
            print("Error: --query is required for search")
            sys.exit(1)
        results = logger.search_conversations(args.phone, args.query)
        print(f"Found {len(results)} matching conversations:")
        for r in results:
            print(f"  [{r.get('date', 'unknown')}] {r.get('content', '')[:100]}...")

    elif args.command == "stats":
        stats = logger.get_conversation_stats(args.phone)
        print(f"Conversation stats for {args.phone}:")
        print(json.dumps(stats, indent=2))

    elif args.command == "export":
        export_data = logger.export_conversations(args.phone)
        if export_data:
            print(export_data)
        else:
            print(f"No conversations found for {args.phone}")
