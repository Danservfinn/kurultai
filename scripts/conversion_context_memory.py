#!/usr/bin/env python3
"""
Conversion Context Memory - File-based narrative storage for conversion tracking

Extends the human profile memory with conversion funnel and subscription context.
Complements the structured Neo4j ConversionContext with narrative details.

File Structure:
    ~/.openclaw/agents/{agent}/memory/humans/{human_id}.md
    (Conversion Context section added to existing profile)

Usage:
    from conversion_context_memory import ConversionContextMemory
    memory = ConversionContextMemory()

    # Update conversion context in profile
    memory.update_conversion_context("+19194133445", {
        "first_touch_date": "2026-03-01",
        "first_touch_source": "Twitter",
        "pricing_views": 5,
        "last_pricing_view": "2026-03-07",
        "checkout_attempts": 2,
        "abort_reasons": ["need to think about it"],
        "subscription_status": "Pro Monthly",
        "subscription_start": "2026-03-08",
        "mrr_display": "$79/mo",
        "conversion_trigger": "Needed automated task review for team",
        "plan_preferences": "Values time-saving features over cost"
    })

    # Get conversion context section
    context = memory.get_conversion_context("+19194133445")
"""

import os
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

# Default agents directory
DEFAULT_AGENTS_DIR = Path.home() / ".openclaw" / "agents"


class ConversionContextMemory:
    """File-based memory storage for conversion context narrative."""

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
        """Ensure the memory directory exists."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _normalize_id(self, human_id: str) -> str:
        """
        Normalize human_id for safe filesystem usage.
        Converts +19194133445 to 19194133445
        """
        return human_id.lstrip("+").replace("/", "_")

    def _get_file_path(self, human_id: str) -> Path:
        """Get the file path for a human profile."""
        normalized = self._normalize_id(human_id)
        return self.memory_dir / f"{normalized}.md"

    def _format_conversion_section(self, context: Dict[str, Any]) -> str:
        """Format conversion context for markdown."""
        lines = ["## Conversion Context", ""]

        # First touch
        first_touch = context.get("first_touch_date")
        source = context.get("first_touch_source", "Unknown")
        if first_touch:
            lines.append(f"- **First touch:** {first_touch} via {source}")

        # Pricing engagement
        pricing_views = context.get("pricing_views", 0)
        if pricing_views > 0:
            last_view = context.get("last_pricing_view", "")
            if last_view:
                lines.append(f"- **Pricing views:** {pricing_views} (last: {last_view})")
            else:
                lines.append(f"- **Pricing views:** {pricing_views}")

        # Checkout behavior
        checkout_attempts = context.get("checkout_attempts", 0)
        if checkout_attempts > 0:
            abort_reasons = context.get("abort_reasons", [])
            if abort_reasons:
                reasons_str = "; ".join(f'"{r}"' for r in abort_reasons[:3])
                lines.append(f"- **Checkout attempts:** {checkout_attempts} (aborted: {reasons_str})")
            else:
                lines.append(f"- **Checkout attempts:** {checkout_attempts}")

        # Subscription status
        status = context.get("subscription_status", "none")
        if status and status != "none":
            mrr = context.get("mrr_display", "")
            start = context.get("subscription_start", "")
            if start and mrr:
                lines.append(f"- **Subscription:** {status} ({mrr}) since {start}")
            elif mrr:
                lines.append(f"- **Subscription:** {status} ({mrr})")
            else:
                lines.append(f"- **Subscription:** {status}")

        # Conversion trigger
        trigger = context.get("conversion_trigger")
        if trigger:
            lines.append(f"- **Conversion trigger:** {trigger}")

        # Plan preferences
        prefs = context.get("plan_preferences")
        if prefs:
            lines.append(f"- **Plan preferences:** {prefs}")

        # Engagement notes
        notes = context.get("engagement_notes", [])
        if notes:
            lines.append("")
            lines.append("### Engagement Notes")
            for note in notes[:5]:
                lines.append(f"- {note}")

        lines.append("")
        return "\n".join(lines)

    def _extract_conversion_section(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse conversion context section from markdown."""
        match = re.search(r'## Conversion Context\n(.*?)(?=##|$)', content, re.DOTALL)
        if not match:
            return None

        section = match.group(1)
        context = {"engagement_notes": []}

        # First touch
        ft_match = re.search(r'\*\*First touch:\*\*\s*(.+?)\s+via\s+(.+)', section)
        if ft_match:
            context["first_touch_date"] = ft_match.group(1).strip()
            context["first_touch_source"] = ft_match.group(2).strip()

        # Pricing views
        pv_match = re.search(r'\*\*Pricing views:\*\*\s*(\d+)(?:\s*\(last:\s*(.+?)\))?', section)
        if pv_match:
            context["pricing_views"] = int(pv_match.group(1))
            if pv_match.group(2):
                context["last_pricing_view"] = pv_match.group(2).strip()

        # Checkout attempts
        ca_match = re.search(r'\*\*Checkout attempts:\*\*\s*(\d+)(?:\s*\(aborted:\s*(.+?)\))?', section)
        if ca_match:
            context["checkout_attempts"] = int(ca_match.group(1))
            if ca_match.group(2):
                # Parse abort reasons
                reasons_str = ca_match.group(2)
                reasons = re.findall(r'"([^"]+)"', reasons_str)
                context["abort_reasons"] = reasons

        # Subscription
        sub_match = re.search(r'\*\*Subscription:\*\*\s*(.+?)(?:\s*\(([^)]+)\))?(?:\s+since\s+(\S+))?', section)
        if sub_match:
            context["subscription_status"] = sub_match.group(1).strip()
            if sub_match.group(2):
                context["mrr_display"] = sub_match.group(2).strip()
            if sub_match.group(3):
                context["subscription_start"] = sub_match.group(3).strip()

        # Conversion trigger
        ct_match = re.search(r'\*\*Conversion trigger:\*\*\s*(.+)', section)
        if ct_match:
            context["conversion_trigger"] = ct_match.group(1).strip()

        # Plan preferences
        pp_match = re.search(r'\*\*Plan preferences:\*\*\s*(.+)', section)
        if pp_match:
            context["plan_preferences"] = pp_match.group(1).strip()

        return context

    def profile_exists(self, human_id: str) -> bool:
        """Check if a profile exists."""
        return self._get_file_path(human_id).exists()

    def get_conversion_context(self, human_id: str) -> Optional[Dict[str, Any]]:
        """
        Get conversion context section from a profile.

        Args:
            human_id: Phone number

        Returns:
            Parsed conversion context or None
        """
        file_path = self._get_file_path(human_id)
        if not file_path.exists():
            return None

        content = file_path.read_text(encoding="utf-8")
        return self._extract_conversion_section(content)

    def update_conversion_context(self, human_id: str, context: Dict[str, Any]) -> bool:
        """
        Add or update the Conversion Context section in a profile.

        Args:
            human_id: Phone number
            context: Conversion context data

        Returns:
            True if successful
        """
        file_path = self._get_file_path(human_id)
        self._ensure_dir()

        if not file_path.exists():
            # Create minimal profile with conversion context
            self._create_profile_with_conversion(human_id, context)
            return True

        content = file_path.read_text(encoding="utf-8")

        # Check if conversion context section already exists
        section_content = self._format_conversion_section(context)

        if "## Conversion Context" in content:
            # Replace existing section
            new_content = re.sub(
                r'## Conversion Context\n.*?(?=##|$)',
                section_content,
                content,
                flags=re.DOTALL
            )
        else:
            # Insert before the last section or at end
            # Find the "Conversation History" section and insert before it
            if "## Conversation History" in content:
                new_content = content.replace(
                    "## Conversation History",
                    section_content + "---\n\n## Conversation History"
                )
            elif "## Notes" in content:
                new_content = content.replace(
                    "## Notes",
                    section_content + "---\n\n## Notes"
                )
            else:
                # Append at end
                new_content = content.rstrip() + "\n\n---\n\n" + section_content

        # Update last modified timestamp
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_content = re.sub(
            r'\*\*Last Updated:\*\*\s*\S+',
            f'**Last Updated:** {now}',
            new_content
        )

        file_path.write_text(new_content, encoding="utf-8")
        return True

    def _create_profile_with_conversion(self, human_id: str, context: Dict[str, Any]) -> None:
        """Create a minimal profile with conversion context."""
        file_path = self._get_file_path(human_id)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        section_content = self._format_conversion_section(context)

        content = f"""# Human Profile: {human_id}

**Profile ID:** hp-{human_id}
**Human ID:** {human_id}
**Last Updated:** {now}
**Source:** conversion_tracking
**Confidence:** 0.5/1.0

---

{section_content}
---

## Notes
*Profile created from conversion tracking.*

---

*This profile is managed by the Kurultai Human Profile System. Created on {datetime.now().strftime("%Y-%m-%d")} from conversion tracking data.*
"""

        file_path.write_text(content, encoding="utf-8")

    def add_engagement_note(self, human_id: str, note: str) -> bool:
        """
        Add an engagement note to the conversion context.

        Args:
            human_id: Phone number
            note: Note to add

        Returns:
            True if successful
        """
        context = self.get_conversion_context(human_id) or {"engagement_notes": []}

        if "engagement_notes" not in context:
            context["engagement_notes"] = []

        # Add timestamped note
        timestamp = datetime.now().strftime("%Y-%m-%d")
        context["engagement_notes"].append(f"[{timestamp}] {note}")

        # Keep only last 10 notes
        context["engagement_notes"] = context["engagement_notes"][-10:]

        return self.update_conversion_context(human_id, context)

    def remove_conversion_context(self, human_id: str) -> bool:
        """
        Remove the conversion context section from a profile.

        Args:
            human_id: Phone number

        Returns:
            True if successful
        """
        file_path = self._get_file_path(human_id)
        if not file_path.exists():
            return False

        content = file_path.read_text(encoding="utf-8")

        # Remove conversion context section
        new_content = re.sub(
            r'## Conversion Context\n.*?(?=##|$)',
            '',
            content,
            flags=re.DOTALL
        )

        # Clean up multiple newlines
        new_content = re.sub(r'\n{3,}', '\n\n', new_content)

        file_path.write_text(new_content, encoding="utf-8")
        return True


# ==========================================================================
# Sync Utilities
# ==========================================================================

class ConversionSync:
    """Bidirectional sync between Neo4j and file-based memory."""

    def __init__(self, agent_name: str = "main"):
        from neo4j_conversion_tracker import ConversionTracker
        self.tracker = ConversionTracker()
        self.memory = ConversionContextMemory(agent_name)

    def close(self):
        """Close Neo4j connection."""
        self.tracker.close()

    def sync_to_file(self, human_id: str) -> bool:
        """
        Sync conversion context from Neo4j to file.

        Args:
            human_id: Phone number

        Returns:
            True if successful
        """
        context = self.tracker.get_conversion_context(human_id)

        if not context:
            return False

        # Transform to file format
        file_context = {
            "first_touch_date": str(context.get("first_touch_date", ""))[:10] if context.get("first_touch_date") else None,
            "first_touch_source": context.get("first_touch_source", "Unknown"),
            "pricing_views": context.get("pricing_views", 0),
            "last_pricing_view": str(context.get("pricing_view_dates", [])[-1])[:10] if context.get("pricing_view_dates") else None,
            "checkout_attempts": context.get("checkout_attempts", 0),
            "abort_reasons": context.get("checkout_abort_reasons", []),
            "subscription_status": self._format_subscription_status(context.get("subscription_status", "none")),
            "subscription_start": str(context.get("subscription_start", ""))[:10] if context.get("subscription_start") else None,
            "mrr_display": self._format_mrr(context.get("mrr_cents", 0)),
            "conversion_trigger": context.get("conversion_trigger"),
            "plan_preferences": self._format_plan_preferences(context.get("plan_preferences")),
        }

        # Filter None values
        file_context = {k: v for k, v in file_context.items() if v is not None}

        return self.memory.update_conversion_context(human_id, file_context)

    def _format_subscription_status(self, status: str) -> str:
        """Format subscription status for display."""
        mapping = {
            "none": "None",
            "trial": "Trial",
            "pro_monthly": "Pro Monthly",
            "pro_annual": "Pro Annual",
            "enterprise": "Enterprise",
            "churned": "Churned"
        }
        return mapping.get(status, status.title())

    def _format_mrr(self, mrr_cents: int) -> str:
        """Format MRR for display."""
        if not mrr_cents:
            return ""
        dollars = mrr_cents / 100
        if dollars >= 100:
            return f"${dollars:.0f}/mo"
        return f"${dollars:.2f}/mo"

    def _format_plan_preferences(self, prefs: Any) -> Optional[str]:
        """Format plan preferences for display."""
        if not prefs:
            return None
        if isinstance(prefs, str):
            try:
                prefs = __import__("json").loads(prefs)
            except:
                return prefs
        if isinstance(prefs, dict):
            # Extract key preferences
            parts = []
            if "feature_priorities" in prefs:
                parts.append(f"Values: {', '.join(prefs['feature_priorities'][:3])}")
            if "price_sensitivity" in prefs:
                parts.append(f"Price: {prefs['price_sensitivity']}")
            return "; ".join(parts) if parts else None
        return str(prefs)

    def sync_all_to_files(self) -> int:
        """
        Sync all Neo4j conversion contexts to files.

        Returns:
            Number of profiles synced
        """
        # Get all humans with conversion contexts
        with self.tracker.driver.session() as session:
            result = session.run("""
                MATCH (cc:ConversionContext)
                RETURN cc.human_id AS human_id
            """)
            human_ids = [r["human_id"] for r in result]

        count = 0
        for human_id in human_ids:
            if self.sync_to_file(human_id):
                count += 1

        return count


def sync_all_conversion_contexts(agent_name: str = "main") -> int:
    """
    Utility function to sync all conversion contexts to files.

    Args:
        agent_name: Agent name for file storage

    Returns:
        Number of profiles synced
    """
    sync = ConversionSync(agent_name)
    try:
        return sync.sync_all_to_files()
    finally:
        sync.close()


if __name__ == "__main__":
    # Test the module
    memory = ConversionContextMemory("main")

    # Test update
    test_id = "+19999999999"
    memory.update_conversion_context(test_id, {
        "first_touch_date": "2026-03-01",
        "first_touch_source": "Twitter",
        "pricing_views": 5,
        "last_pricing_view": "2026-03-07",
        "checkout_attempts": 2,
        "abort_reasons": ["need to think about it", "budget pending"],
        "subscription_status": "Pro Monthly",
        "subscription_start": "2026-03-08",
        "mrr_display": "$79/mo",
        "conversion_trigger": "Needed automated task review for team",
        "plan_preferences": "Values time-saving features over cost"
    })
    print(f"Updated conversion context for {test_id}")

    # Test read
    context = memory.get_conversion_context(test_id)
    print(f"Read context: {context}")

    # Test add note
    memory.add_engagement_note(test_id, "Asked about team pricing")
    print("Added engagement note")

    # Cleanup
    memory.remove_conversion_context(test_id)
    print("Test conversion context removed")
