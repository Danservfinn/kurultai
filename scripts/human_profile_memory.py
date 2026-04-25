#!/usr/bin/env python3
"""
Human Profile Memory - File-based narrative context for human profiles

Stores rich, unstructured context about humans in Markdown files.
Complements the structured Neo4j HumanProfile with narrative details.

File Structure:
    ~/.openclaw/agents/{agent}/memory/humans/{human_id}.md

Where human_id is the E.164 phone number (normalized for filesystem safety).

Usage:
    from human_profile_memory import HumanProfileMemory
    memory = HumanProfileMemory()

    # Write a profile
    memory.write_profile("+19194133445", {
        "display_name": "Danny",
        "what_to_call": "Danny",
        "timezone": "America/New_York",
        "communication_style": {...},
        "projects": {...},
        "notes": "Coffee enthusiast...",
        "conversations": [...]
    })

    # Read a profile
    profile = memory.read_profile("+19194133445")

    # Update with conversation snippet
    memory.add_conversation("+19194133445", {
        "date": "2026-03-07",
        "channel": "Signal",
        "summary": "Discussed new feature..."
    })
"""
from __future__ import annotations

import os
import re
import json
import stat
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path


# Default agents directory
DEFAULT_AGENTS_DIR = Path.home() / ".openclaw" / "agents"


class HumanProfileMemory:
    """File-based memory storage for rich human profile context."""

    def __init__(self, agent_name: str = "main"):
        """
        Initialize memory for an agent.

        Args:
            agent_name: Name of the agent (e.g., "kublai", "chagatai")
        """
        self.agent_name = agent_name
        self.memory_dir = DEFAULT_AGENTS_DIR / agent_name / "memory" / "humans"
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensure the memory directory exists with proper permissions."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # Set directory permissions to 700 (owner only)
        os.chmod(self.memory_dir, stat.S_IRWXU)  # 700

        # Verify permissions were set correctly
        actual_mode = oct(self.memory_dir.stat().st_mode)[-3:]
        if actual_mode != "700":
            print(f"Warning: Could not set secure permissions on {self.memory_dir}. Current: {actual_mode}, Expected: 700")

    def _normalize_id(self, human_id: str) -> str:
        """
        Normalize human_id for safe filesystem usage.

        Converts +19194133445 to 19194133445 (removes + for filesystem safety)
        """
        return human_id.lstrip("+").replace("/", "_")

    def _denormalize_id(self, filename: str) -> str:
        """Convert filename back to phone number format."""
        return "+" + filename.replace(".md", "").replace("_", "/")

    def _verify_and_set_permissions(self, path: Path, is_dir: bool = True) -> bool:
        """
        Verify and set correct permissions on a file or directory.

        Args:
            path: Path to verify/set permissions on
            is_dir: True if path is a directory, False if file

        Returns:
            True if permissions are correct, False otherwise
        """
        if not path.exists():
            return False

        try:
            if is_dir:
                os.chmod(path, stat.S_IRWXU)  # 700 - owner read/write/execute only
                expected_mode = "700"
            else:
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 600 - owner read/write only
                expected_mode = "600"

            actual_mode = oct(path.stat().st_mode)[-3:]
            return actual_mode == expected_mode
        except (OSError, PermissionError) as e:
            print(f"Warning: Could not set permissions on {path}: {e}")
            return False

    def _get_file_path(self, human_id: str) -> Path:
        """Get the file path for a human profile."""
        normalized = self._normalize_id(human_id)
        return self.memory_dir / f"{normalized}.md"

    def _format_communication_style(self, style: Dict[str, Any]) -> str:
        """Format communication style for markdown."""
        lines = []
        mapping = {
            "preferred_channel": "Preferred Channel",
            "preferred_time": "Best Time to Reach",
            "response_style": "Response Style",
            "emoji_friendly": "Emoji Friendly",
            "detail_level": "Detail Level",
            "formality": "Formality"
        }
        for key, label in mapping.items():
            value = style.get(key)
            if value is not None:
                if isinstance(value, bool):
                    value = "Yes" if value else "No"
                lines.append(f"- **{label}:** {value}")
        return "\n".join(lines)

    def _format_preferences(self, prefs: Dict[str, Any]) -> str:
        """Format preferences for markdown."""
        lines = []
        mapping = {
            "response_time": "Response Time",
            "detail_level": "Detail Level",
            "formatting": "Preferred Format",
            "code_review_style": "Code Review Style",
            "meeting_style": "Meeting Style",
            "file_organization": "File Organization"
        }
        for key, label in mapping.items():
            value = prefs.get(key)
            if value and key != "notifications":
                lines.append(f"- **{label}:** {value}")

        # Handle notifications separately
        notifications = prefs.get("notifications", {})
        if notifications:
            notif_str = ", ".join(
                f"{k}: {'on' if v else 'off'}"
                for k, v in notifications.items() if isinstance(v, bool)
            )
            if notif_str:
                lines.append(f"- **Notifications:** {notif_str}")

        return "\n".join(lines)

    def _format_projects(self, projects: Dict[str, Any]) -> str:
        """Format projects for markdown."""
        lines = []

        active = projects.get("active", [])
        if active:
            lines.append("### Active")
            for proj in active:
                name = proj.get("name", "Unnamed")
                role = proj.get("role", "")
                priority = proj.get("priority", "")
                desc = proj.get("description", "")
                lines.append(f"- **{name}**")
                if role:
                    lines.append(f"  - Role: {role}")
                if priority:
                    lines.append(f"  - Priority: {priority}")
                if desc:
                    lines.append(f"  - {desc}")

        planned = projects.get("planned", [])
        if planned:
            lines.append("\n### Planned")
            for proj in planned:
                lines.append(f"- {proj.get('name', 'Unnamed')}")

        completed = projects.get("completed", [])
        if completed:
            lines.append("\n### Completed")
            for proj in completed[:5]:  # Limit completed projects
                lines.append(f"- {proj.get('name', 'Unnamed')}")

        return "\n".join(lines)

    def _format_conversations(self, conversations: List[Dict[str, Any]]) -> str:
        """Format conversation history for markdown."""
        lines = []

        # Show most recent 10 conversations
        for conv in reversed(conversations[-10:]):
            date = conv.get("date", "Unknown date")
            channel = conv.get("channel", "Unknown")
            topic = conv.get("topic", "")
            summary = conv.get("summary", "")
            insights = conv.get("insights", [])

            lines.append(f"### {date} ({channel})")
            if topic:
                lines.append(f"**Topic:** {topic}")
            if summary:
                lines.append(f"\n{summary}")
            if insights:
                lines.append("\n**Insights:**")
                for insight in insights:
                    lines.append(f"- {insight}")
            lines.append("")

        return "\n".join(lines)

    def _format_conversion_context(self, conversion_context: Dict[str, Any]) -> str:
        """Format conversion context for markdown."""
        if not conversion_context:
            return "*No conversion data recorded.*"

        lines = []

        # First touch
        first_touch = conversion_context.get("first_touch", {})
        if first_touch:
            source = first_touch.get("source", "unknown")
            date = first_touch.get("date", "unknown")
            lines.append(f"- **First Touch:** {date} via {source.title()}")

        # Pricing views
        pricing_views = conversion_context.get("pricing_views", {})
        if pricing_views:
            count = pricing_views.get("count", 0)
            last = pricing_views.get("last_viewed", "never")
            if count > 0:
                lines.append(f"- **Pricing Views:** {count} (last: {last})")

        # Checkout attempts
        attempts = conversion_context.get("checkout_attempts", 0)
        if attempts > 0:
            lines.append(f"- **Checkout Attempts:** {attempts}")

        # Abort reasons
        aborts = conversion_context.get("abort_reasons", [])
        if aborts:
            lines.append(f"- **Abort Reasons:** {', '.join(aborts)}")

        # Subscription
        subscription = conversion_context.get("subscription", {})
        if subscription:
            status = subscription.get("status", "none")
            if status != "none":
                mrr = subscription.get("mrr_cents", 0)
                start = subscription.get("start_date", "unknown")
                if mrr > 0:
                    lines.append(f"- **Subscription:** {status.replace('_', ' ').title()} (${mrr/100:.0f}/mo) since {start}")
                else:
                    lines.append(f"- **Subscription:** {status.replace('_', ' ').title()} since {start}")

        # Conversion trigger
        trigger = conversion_context.get("conversion_trigger")
        if trigger:
            lines.append(f"- **Conversion Trigger:** \"{trigger}\"")

        # Plan preferences
        prefs = conversion_context.get("plan_preferences", {})
        if prefs:
            lines.append(f"- **Plan Preferences:**")
            for key, value in prefs.items():
                if isinstance(value, list):
                    lines.append(f"  - **{key.replace('_', ' ').title()}:** {', '.join(value)}")
                elif isinstance(value, bool):
                    lines.append(f"  - **{key.replace('_', ' ').title()}:** {'Yes' if value else 'No'}")
                else:
                    lines.append(f"  - **{key.replace('_', ' ').title()}:** {value}")

        return "\n".join(lines) if lines else "*No conversion data recorded.*"

    def _parse_profile(self, content: str) -> Dict[str, Any]:
        """Parse a markdown profile back into a dict."""
        profile = {
            "conversations": []
        }

        # Extract metadata
        meta_match = re.search(r'\*\*Profile ID:\*\*\s*(\S+)', content)
        if meta_match:
            profile["profile_id"] = meta_match.group(1)

        human_id_match = re.search(r'\*\*Human ID:\*\*\s*(\S+)', content)
        if human_id_match:
            profile["human_id"] = human_id_match.group(1)

        # Extract quick facts
        facts_match = re.search(r'## Quick Facts\n(.*?)(?=##|$)', content, re.DOTALL)
        if facts_match:
            facts_text = facts_match.group(1)

            name_match = re.search(r'\*\*Preferred Name:\*\*\s*(.+)', facts_text)
            if name_match:
                profile["what_to_call"] = name_match.group(1).strip()

            tz_match = re.search(r'\*\*Timezone:\*\*\s*(\S+)', facts_text)
            if tz_match:
                profile["timezone"] = tz_match.group(1)

            pronouns_match = re.search(r'\*\*Pronouns:\*\*\s*(\S+)', facts_text)
            if pronouns_match:
                profile["pronouns"] = pronouns_match.group(1)

        # This is a simplified parser - full parsing would be more robust
        return profile

    # ==========================================================================
    # Public API
    # ==========================================================================

    def write_profile(self, human_id: str, data: Dict[str, Any]) -> Path:
        """
        Write or overwrite a profile file.

        Args:
            human_id: Phone number (E.164 format)
            data: Profile data dict

        Returns:
            Path to the written file
        """
        file_path = self._get_file_path(human_id)
        self._ensure_dir()

        display_name = data.get("display_name", "Unknown")
        profile_id = data.get("profile_id", f"hp-{human_id}")
        what_to_call = data.get("what_to_call", display_name)
        timezone = data.get("timezone", "Unknown")
        pronouns = data.get("pronouns", "Not specified")
        notes = data.get("notes", "")

        communication_style = data.get("communication_style", {})
        preferences = data.get("preferences", {})
        projects = data.get("projects", {})
        conversations = data.get("conversations", [])
        conversion_context = data.get("conversion_context", {})

        content = f"""# Human Profile: {display_name}

**Profile ID:** {profile_id}
**Human ID:** {human_id}
**Last Updated:** {datetime.now().strftime("%Y-%m-%d %H:%M")}
**Source:** {data.get("source", "unknown")}
**Confidence:** {data.get("confidence", 1.0)}/1.0

---

## Quick Facts
- **Preferred Name:** {what_to_call}
- **Timezone:** {timezone}
- **Pronouns:** {pronouns}

---

## Communication Style
{self._format_communication_style(communication_style) if communication_style else "*No communication style preferences recorded.*"}

---

## Preferences
{self._format_preferences(preferences) if preferences else "*No preferences recorded.*"}

---

## Projects
{self._format_projects(projects) if projects else "*No projects recorded.*"}

---

## Notes
{notes if notes else "*No personal notes.*"}

---

## Conversion Context
{self._format_conversion_context(conversion_context)}

---

## Conversation History
{self._format_conversations(conversations) if conversations else "*No conversation history recorded.*"}

---

*This profile is managed by the Kurultai Human Profile System. Last synced from Neo4j on {datetime.now().strftime("%Y-%m-%d")}.*
"""

        file_path.write_text(content, encoding="utf-8")

        # Ensure secure file permissions (600 - owner read/write only)
        self._verify_and_set_permissions(file_path, is_dir=False)

        return file_path

    def read_profile(self, human_id: str) -> Optional[Dict[str, Any]]:
        """
        Read a profile file and parse it.

        Args:
            human_id: Phone number

        Returns:
            Parsed profile dict or None if not found
        """
        file_path = self._get_file_path(human_id)

        if not file_path.exists():
            return None

        content = file_path.read_text(encoding="utf-8")
        return self._parse_profile(content)

    def read_profile_raw(self, human_id: str) -> Optional[str]:
        """
        Read raw markdown content of a profile.

        Args:
            human_id: Phone number

        Returns:
            Raw markdown content or None
        """
        file_path = self._get_file_path(human_id)

        if not file_path.exists():
            return None

        return file_path.read_text(encoding="utf-8")

    def add_conversation(self, human_id: str, conversation: Dict[str, Any]) -> bool:
        """
        Add a conversation entry to a profile.

        Args:
            human_id: Phone number
            conversation: Dict with date, channel, topic, summary, insights

        Returns:
            True if successful
        """
        # Read existing profile if any
        profile = self.read_profile(human_id) or {}

        # Initialize conversations list
        if "conversations" not in profile:
            profile["conversations"] = []

        # Add new conversation
        profile["conversations"].append(conversation)

        # Keep only last 50 conversations
        profile["conversations"] = profile["conversations"][-50:]

        # Merge with data that might exist in the file but wasn't parsed
        file_path = self._get_file_path(human_id)
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")

            # Extract profile_id and other metadata if not already set
            if "profile_id" not in profile:
                match = re.search(r'\*\*Profile ID:\*\*\s*(\S+)', content)
                if match:
                    profile["profile_id"] = match.group(1)

            # Extract notes if present and not already in profile
            if "notes" not in profile or not profile["notes"]:
                notes_match = re.search(r'## Notes\n(.*?)(?=##|$)', content, re.DOTALL)
                if notes_match:
                    notes_text = notes_match.group(1).strip()
                    if notes_text != "*No personal notes.*":
                        profile["notes"] = notes_text

        # Write back
        self.write_profile(human_id, profile)
        return True

    def update_notes(self, human_id: str, notes: str, append: bool = False) -> bool:
        """
        Update the notes section of a profile.

        Args:
            human_id: Phone number
            notes: New notes content
            append: If True, append to existing notes

        Returns:
            True if successful
        """
        profile = self.read_profile(human_id) or {}

        if append and profile.get("notes"):
            profile["notes"] = profile["notes"] + "\n\n" + notes
        else:
            profile["notes"] = notes

        self.write_profile(human_id, profile)
        return True

    def list_profiles(self) -> List[str]:
        """
        List all human IDs with profiles.

        Returns:
            List of human IDs (phone numbers)
        """
        if not self.memory_dir.exists():
            return []

        profiles = []
        for file_path in self.memory_dir.glob("*.md"):
            human_id = self._denormalize_id(file_path.name)
            profiles.append(human_id)

        return sorted(profiles)

    def delete_profile(self, human_id: str) -> bool:
        """
        Delete a profile file.

        Args:
            human_id: Phone number

        Returns:
            True if deleted, False if didn't exist
        """
        file_path = self._get_file_path(human_id)

        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def profile_exists(self, human_id: str) -> bool:
        """
        Check if a profile exists.

        Args:
            human_id: Phone number

        Returns:
            True if exists
        """
        return self._get_file_path(human_id).exists()

    def update_conversion_context(self, human_id: str, conversion_context: Dict[str, Any]) -> bool:
        """
        Update the conversion context section of a profile.

        Args:
            human_id: Phone number
            conversion_context: Conversion context dict

        Returns:
            True if successful
        """
        profile = self.read_profile(human_id) or {}
        profile["conversion_context"] = conversion_context
        self.write_profile(human_id, profile)
        return True


# ==========================================================================
# Sync Utilities
# ==========================================================================

class ProfileSync:
    """Bidirectional sync between Neo4j and file-based memory."""

    def __init__(self, agent_name: str = "main"):
        from neo4j_human_profile import HumanProfileStore
        self.store = HumanProfileStore()
        self.memory = HumanProfileMemory(agent_name)

    def close(self):
        """Close Neo4j connection."""
        self.store.close()

    def sync_to_file(self, human_id: str) -> bool:
        """
        Sync a profile from Neo4j to file.

        Args:
            human_id: Phone number

        Returns:
            True if successful
        """
        profile = self.store.get_profile_by_phone(human_id)

        if not profile:
            return False

        # Preserve existing conversations from file
        existing = self.memory.read_profile(human_id)
        if existing and existing.get("conversations"):
            profile["conversations"] = existing["conversations"]

        self.memory.write_profile(human_id, profile)
        return True

    def sync_all_to_files(self) -> int:
        """
        Sync all Neo4j profiles to files.

        Returns:
            Number of profiles synced
        """
        profiles = self.store.list_profiles()
        count = 0

        for profile in profiles:
            phone_e164 = profile["phone_e164"]
            if self.sync_to_file(phone_e164):
                count += 1

        return count

    def get_enriched_profile(self, human_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a profile with both structured (Neo4j) and narrative (file) data.

        Args:
            human_id: Phone number

        Returns:
            Enriched profile dict or None
        """
        # Get structured data from Neo4j
        profile = self.store.get_profile_by_phone(human_id)

        if not profile:
            return None

        # Get narrative data from file
        narrative = self.memory.read_profile_raw(human_id)

        if narrative:
            profile["_narrative"] = narrative

        return profile


def sync_all_profiles(agent_name: str = "main") -> int:
    """
    Utility function to sync all profiles to files.

    Args:
        agent_name: Agent name for file storage

    Returns:
        Number of profiles synced
    """
    sync = ProfileSync(agent_name)
    try:
        return sync.sync_all_to_files()
    finally:
        sync.close()


if __name__ == "__main__":
    # Test the module
    import sys

    memory = HumanProfileMemory("main")

    # Test write
    test_id = "+19999999999"
    memory.write_profile(test_id, {
        "profile_id": "hp-test-123",
        "display_name": "Test User",
        "what_to_call": "Test",
        "timezone": "America/New_York",
        "pronouns": "they/them",
        "source": "test",
        "confidence": 0.9,
        "communication_style": {
            "preferred_channel": "signal",
            "preferred_time": "morning",
            "response_style": "direct",
            "emoji_friendly": True,
            "detail_level": "brief"
        },
        "preferences": {
            "response_time": "fast",
            "detail_level": "concise",
            "notifications": {"signal": True, "email": False}
        },
        "projects": {
            "active": [{"name": "Test Project", "role": "tester", "priority": "high"}]
        },
        "notes": "This is a test profile.",
        "conversations": [
            {"date": "2026-03-07", "channel": "Signal", "topic": "Testing", "summary": "Testing the profile system"}
        ]
    })
    print(f"Wrote test profile to: {memory._get_file_path(test_id)}")

    # Test read
    profile = memory.read_profile(test_id)
    print(f"Read profile: {profile.get('what_to_call') if profile else 'Not found'}")

    # Test add conversation
    memory.add_conversation(test_id, {
        "date": "2026-03-07",
        "channel": "Signal",
        "topic": "Follow-up",
        "summary": "Second test conversation",
        "insights": ["Likes testing", "Appreciates documentation"]
    })
    print("Added conversation")

    # List profiles
    profiles = memory.list_profiles()
    print(f"Profiles in memory: {profiles}")

    # Cleanup
    memory.delete_profile(test_id)
    print("Test profile deleted")
