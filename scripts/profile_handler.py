#!/usr/bin/env python3
"""
Human Profile Command Handler - Signal commands for profile management

Handles profile commands from Signal messages:
    profile show                    - Show my profile
    profile update timezone X       - Update timezone
    profile update name X           - Update display name
    profile privacy X               - Set privacy level
    profile consent add X           - Add consent category
    profile consent list            - List consents
    profile notes X                 - Add personal notes

Integrates with:
    - neo4j_human_profile.py (structured data)
    - human_profile_memory.py (narrative context)

Usage (from calendar_handler or standalone):
    from profile_handler import handle_profile_command

    result = handle_profile_command(
        command_text="profile update timezone America/New_York",
        sender_phone="+19194133445",
        sender_name="Danny"
    )
    if result:
        send_group_message(result)
"""

import os
import sys
import re
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_human_profile import HumanProfileStore, DEFAULT_COMMUNICATION_STYLE, DEFAULT_PREFERENCES
from human_profile_memory import HumanProfileMemory


# =============================================================================
# Command Parser
# =============================================================================

def parse_privacy_command(text: str) -> Optional[Dict[str, Any]]:
    """Parse a /privacy, /mydata, /forget, or /consent command.

    Returns:
        Dict with 'action' and relevant fields, or None if not a privacy command
    """
    text_lower = text.lower().strip()

    # /privacy — show consent dashboard
    if text_lower in ("/privacy", "/privacy show"):
        return {"action": "privacy_show"}

    # /consent <category> — toggle consent
    consent_match = re.match(r'/consent\s+(\w+)', text_lower)
    if consent_match:
        return {"action": "consent_toggle", "category": consent_match.group(1)}

    # /mydata — export all data
    if text_lower == "/mydata":
        return {"action": "mydata"}

    # /forget — request deletion
    if text_lower == "/forget":
        return {"action": "forget_request"}

    # FORGET EVERYTHING — confirm deletion
    if text_lower == "forget everything":
        return {"action": "forget_confirm"}

    return None


def parse_profile_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse a profile command from text.

    Args:
        text: The message text

    Returns:
        Dict with 'action', 'field', 'value', 'args' or None if not a profile command
    """
    text_lower = text.lower().strip()

    # Check for v2 privacy commands first
    privacy_parsed = parse_privacy_command(text)
    if privacy_parsed:
        return privacy_parsed

    # Must start with 'profile'
    if not text_lower.startswith("profile"):
        return None

    # Remove 'profile' prefix
    remainder = text[7:].strip()

    # profile show
    if remainder in ["show", "me", ""]:
        return {"action": "show"}

    # profile update <field> <value>
    update_match = re.match(r'update\s+(\w+)\s+(.+)', remainder, re.IGNORECASE)
    if update_match:
        field = update_match.group(1).lower()
        value = update_match.group(2).strip()
        return {"action": "update", "field": field, "value": value}

    # profile privacy <level>
    privacy_match = re.match(r'privacy\s+(\w+)', remainder, re.IGNORECASE)
    if privacy_match:
        level = privacy_match.group(1).lower()
        return {"action": "privacy", "level": level}

    # profile consent add <category>
    consent_add_match = re.match(r'consent\s+add\s+(\w+)', remainder, re.IGNORECASE)
    if consent_add_match:
        category = consent_add_match.group(1).lower()
        return {"action": "consent_add", "category": category}

    # profile consent remove <category>
    consent_remove_match = re.match(r'consent\s+remove\s+(\w+)', remainder, re.IGNORECASE)
    if consent_remove_match:
        category = consent_remove_match.group(1).lower()
        return {"action": "consent_remove", "category": category}

    # profile consent list
    if re.match(r'consent\s+(list|show)', remainder, re.IGNORECASE):
        return {"action": "consent_list"}

    # profile notes <text>
    notes_match = re.match(r'notes?\s+(.+)', remainder, re.DOTALL | re.IGNORECASE)
    if notes_match:
        note_text = notes_match.group(1).strip()
        return {"action": "notes", "text": note_text}

    # profile what_to_call <name>
    call_match = re.match(r'(what_to_call|callme|call me)\s+(.+)', remainder, re.IGNORECASE)
    if call_match:
        name = call_match.group(2).strip()
        return {"action": "update", "field": "what_to_call", "value": name}

    # profile timezone <tz>
    tz_match = re.match(r'timezone\s+(.+)', remainder, re.IGNORECASE)
    if tz_match:
        tz = tz_match.group(1).strip()
        return {"action": "update", "field": "timezone", "value": tz}

    # Unknown profile command
    return {"action": "help"}


# =============================================================================
# Formatters
# =============================================================================

def format_profile_summary(profile: Dict[str, Any]) -> str:
    """Format a profile for display in Signal."""
    name = profile.get("display_name", "Unknown")
    what_to_call = profile.get("what_to_call", name)
    timezone = profile.get("timezone", "Not set")
    pronouns = profile.get("pronouns")
    privacy = profile.get("privacy_level", "contacts")
    consents = profile.get("active_consents", [])
    confidence = profile.get("confidence", 1.0)

    lines = [
        f"**Profile: {name}**",
        "",
        f"**Preferred name:** {what_to_call}",
    ]

    if pronouns:
        lines.append(f"**Pronouns:** {pronouns}")

    lines.extend([
        f"**Timezone:** {timezone}",
        f"**Privacy:** {privacy}",
        f"**Consents:** {', '.join(consents) if consents else 'None'}",
        "",
        f"_Profile confidence: {confidence:.0%}_"
    ])

    # Add communication preferences if available
    comm_style = profile.get("communication_style", {})
    if comm_style and isinstance(comm_style, dict):
        lines.append("")
        lines.append("**Communication:**")
        if comm_style.get("preferred_channel"):
            lines.append(f"- Channel: {comm_style['preferred_channel']}")
        if comm_style.get("preferred_time"):
            lines.append(f"- Best time: {comm_style['preferred_time']}")
        if comm_style.get("response_style"):
            lines.append(f"- Style: {comm_style['response_style']}")
        if comm_style.get("messaging_frequency") and comm_style["messaging_frequency"] != "normal":
            lines.append(f"- Message frequency: {comm_style['messaging_frequency']}")
        if comm_style.get("quiet_hours") and isinstance(comm_style["quiet_hours"], dict):
            qh = comm_style["quiet_hours"]
            if qh.get("before"):
                lines.append(f"- Quiet before: {qh['before']}")
            if qh.get("after"):
                lines.append(f"- Quiet after: {qh['after']}")
        if comm_style.get("topics_of_interest"):
            lines.append(f"- Interested in: {', '.join(comm_style['topics_of_interest'])}")
        if comm_style.get("topics_to_avoid"):
            lines.append(f"- Avoid topics: {', '.join(comm_style['topics_to_avoid'])}")

    # Add active projects
    projects = profile.get("projects", {})
    if projects and isinstance(projects, dict):
        active = projects.get("active", [])
        if active:
            lines.append("")
            lines.append("**Active projects:**")
            for proj in active[:3]:  # Limit to 3
                proj_name = proj.get("name", "Unnamed")
                proj_role = proj.get("role", "")
                if proj_role:
                    lines.append(f"- {proj_name} ({proj_role})")
                else:
                    lines.append(f"- {proj_name}")

    lines.append("")
    lines.append("_Update with: profile update <field> <value>_")

    return "\n".join(lines)


def format_consent_list(profile: Dict[str, Any], all_categories: list) -> str:
    """Format consent categories for display."""
    active_consents = set(profile.get("active_consents", []))

    lines = [
        f"**Consent Settings for {profile.get('display_name', 'You')}**",
        "",
        "**Active:**"
    ]

    if active_consents:
        for cat in sorted(active_consents):
            lines.append(f"- {cat}")
    else:
        lines.append("_No active consents_")

    lines.append("")
    lines.append("**Available:**")

    available = set(c["name"] for c in all_categories) - active_consents
    if available:
        for cat in sorted(available):
            lines.append(f"- {cat}")
    else:
        lines.append("_All categories enabled_")

    lines.append("")
    lines.append("_Manage with: profile consent add/remove <category>_")

    return "\n".join(lines)


def format_help() -> str:
    """Return help text for profile commands."""
    return """**Profile Commands:**

`profile show` - Show your profile
`profile update <field> <value>` - Update a field
`profile timezone <tz>` - Set timezone (e.g., America/New_York)
`profile what_to_call <name>` - Set preferred name
`profile privacy <level>` - Set privacy (public/contacts/private)
`profile consent add <category>` - Add consent
`profile consent remove <category>` - Remove consent
`profile consent list` - List your consents
`profile notes <text>` - Add personal notes

**Privacy Commands:**
`/privacy` - Show consent dashboard
`/consent <category>` - Toggle consent on/off
`/mydata` - View your data summary
`/forget` - Delete all your data

**Fields you can update:**
- display_name, timezone, pronouns, notes
"""


# =============================================================================
# Handlers
# =============================================================================

def handle_profile_show(store: HumanProfileStore, sender_phone: str) -> str:
    """Handle 'profile show' command."""
    profile = store.get_profile_by_phone(sender_phone)

    if not profile:
        return "No profile found. I can create one for you with your timezone and preferences. What timezone are you in?"

    return format_profile_summary(profile)


def handle_profile_update(store: HumanProfileStore, sender_phone: str,
                          field: str, value: str) -> str:
    """Handle 'profile update' command."""
    # Map common aliases
    field_map = {
        "name": "display_name",
        "callme": "what_to_call",
        "call_me": "what_to_call",
        "preferred_name": "what_to_call",
        "tz": "timezone",
    }

    normalized_field = field_map.get(field, field)

    # Validate field
    valid_fields = [
        "display_name", "what_to_call", "timezone", "pronouns",
        "notes", "privacy_level"
    ]

    if normalized_field not in valid_fields:
        return f"Unknown field: {field}. Valid fields: {', '.join(valid_fields)}"

    # Ensure profile exists
    profile = store.get_profile_by_phone(sender_phone)
    if not profile:
        # Auto-create minimal profile
        person_result = store.create_profile(
            human_id=sender_phone,
            display_name="User",  # Will be updated
            timezone="America/New_York",
            source="signal"
        )
        if not person_result:
            return "Could not create profile. Make sure you're registered in the system."

    # Update the field
    success = store.update_field(sender_phone, normalized_field, value, updated_by="signal_bot")

    if success:
        return f"Updated **{normalized_field}** to: {value}"
    else:
        return "Failed to update profile. Please try again."


def handle_profile_privacy(store: HumanProfileStore, sender_phone: str,
                           level: str) -> str:
    """Handle 'profile privacy' command."""
    valid_levels = ["public", "contacts", "private"]

    if level not in valid_levels:
        return f"Invalid privacy level. Choose: {', '.join(valid_levels)}"

    # Ensure profile exists
    profile = store.get_profile_by_phone(sender_phone)
    if not profile:
        return "No profile found. Create one first with 'profile show'"

    success = store.set_privacy_level(sender_phone, level)

    if success:
        descriptions = {
            "public": "Anyone can see your basic info",
            "contacts": "Only Signal group members can see your profile",
            "private": "Only you and admin agents can see your full profile"
        }
        return f"Privacy set to **{level}**. {descriptions[level]}."
    else:
        return "Failed to update privacy setting."


def handle_consent_add(store: HumanProfileStore, sender_phone: str,
                       category: str) -> str:
    """Handle 'profile consent add' command."""
    # Ensure profile exists
    profile = store.get_profile_by_phone(sender_phone)
    if not profile:
        return "No profile found. Create one first with 'profile show'"

    # Get valid categories
    valid_categories = store.get_consent_categories()
    valid_names = [c["name"] for c in valid_categories]

    if category not in valid_names:
        return f"Invalid category. Valid: {', '.join(valid_names)}"

    success = store.add_consent(sender_phone, category)

    if success:
        descriptions = {
            "calendar": "I can store your event preferences and availability",
            "tasks": "I can remember your task assignments and progress",
            "research": "I can store your research interests and preferences",
            "social": "I can remember personal interests and context",
            "marketing": "I can send you product updates (not used yet)"
        }
        return f"✓ Consent added for **{category}**. {descriptions.get(category, '')}"
    else:
        return "Failed to add consent. Please try again."


def handle_consent_remove(store: HumanProfileStore, sender_phone: str,
                          category: str) -> str:
    """Handle 'profile consent remove' command."""
    profile = store.get_profile_by_phone(sender_phone)
    if not profile:
        return "No profile found."

    success = store.revoke_consent(sender_phone, category)

    if success:
        return f"✓ Consent revoked for **{category}**. I will no longer store related data."
    else:
        return f"You haven't consented to **{category}** or it couldn't be removed."


def handle_consent_list(store: HumanProfileStore, sender_phone: str) -> str:
    """Handle 'profile consent list' command."""
    profile = store.get_profile_by_phone(sender_phone)
    if not profile:
        return "No profile found. Create one with 'profile show'"

    categories = store.get_consent_categories()
    return format_consent_list(profile, categories)


def handle_profile_notes(store: HumanProfileStore, memory: HumanProfileMemory,
                         sender_phone: str, text: str) -> str:
    """Handle 'profile notes' command."""
    # Ensure profile exists
    profile = store.get_profile_by_phone(sender_phone)
    if not profile:
        return "No profile found. Create one first with 'profile show'"

    # Update Neo4j
    store.update_field(sender_phone, "notes", text)

    # Update file memory
    memory.update_notes(sender_phone, text, append=True)

    return "✓ Notes updated. These are private to your profile."


# =============================================================================
# V2 Privacy Command Handlers
# =============================================================================

def handle_privacy_show(sender_phone: str) -> str:
    """Handle /privacy — show consent dashboard."""
    try:
        from neo4j_human_v2 import HumanStoreV2
        from consent_decorator import get_consent_status, CONSENT_HIERARCHY, CONSENT_DESCRIPTIONS

        human_store = HumanStoreV2()
        human = human_store.find_human_by_identifier("SIGNAL_PHONE", sender_phone)
        human_store.close()

        if not human:
            return ("**Privacy Dashboard**\n\n"
                    "No profile found. Your data is not being stored.\n\n"
                    "Available commands:\n"
                    "`/consent <category>` — toggle consent\n"
                    "`/mydata` — export your data\n"
                    "`/forget` — delete all your data")

        status = get_consent_status(human["id"])

        lines = [
            f"**Privacy Dashboard for {human['displayName']}**",
            "",
            "**Consent Status:**",
        ]

        for cat in sorted(CONSENT_DESCRIPTIONS.keys()):
            info = status.get(cat, {})
            granted = info.get("granted", False)
            icon = "ON" if granted else "OFF"
            desc = CONSENT_DESCRIPTIONS.get(cat, "")
            # Show hierarchy depth
            depth = 0
            for parent, children in CONSENT_HIERARCHY.items():
                if cat in children:
                    depth = 1
                    for gp, gc in CONSENT_HIERARCHY.items():
                        if parent in gc:
                            depth = 2
                            break
                    break
            indent = "  " * depth
            lines.append(f"{indent}[{icon}] **{cat}** — {desc}")

        lines.extend([
            "",
            "**Commands:**",
            "`/consent <category>` — toggle a category",
            "`/mydata` — export all your data as JSON",
            "`/forget` — permanently delete all your data",
        ])

        return "\n".join(lines)

    except Exception as e:
        return f"Error loading privacy dashboard: {e}"


def handle_consent_toggle(sender_phone: str, category: str) -> str:
    """Handle /consent <category> — toggle consent on/off."""
    try:
        from neo4j_human_v2 import HumanStoreV2
        from consent_decorator import (
            check_consent, grant_consent, revoke_consent,
            ALL_CATEGORIES, get_descendants, CONSENT_DESCRIPTIONS,
        )

        human_store = HumanStoreV2()
        human = human_store.find_or_create_by_phone(sender_phone)
        human_store.close()
        human_id = human["id"]

        if category not in ALL_CATEGORIES:
            return f"Unknown category: {category}\nValid: {', '.join(sorted(ALL_CATEGORIES))}"

        # Check current state
        currently_granted = check_consent(human_id, category)

        if currently_granted:
            # Revoke (with cascade)
            result = revoke_consent(human_id, category)
            revoked = result.get("revoked", [])
            cascade = result.get("cascade_warning")
            msg = f"Consent **revoked** for: {', '.join(revoked)}"
            if cascade:
                msg += f"\n{cascade}"
            return msg
        else:
            # Grant
            success = grant_consent(human_id, category, source="signal_command")
            if success:
                desc = CONSENT_DESCRIPTIONS.get(category, "")
                return f"Consent **granted** for **{category}**.\n{desc}"
            return f"Failed to grant consent for {category}."

    except Exception as e:
        return f"Error toggling consent: {e}"


def handle_mydata(sender_phone: str) -> str:
    """Handle /mydata — export all data."""
    try:
        from neo4j_human_v2 import HumanStoreV2
        from neo4j_task_tracker import neo4j_session
        import json

        human_store = HumanStoreV2()
        human = human_store.find_human_by_identifier("SIGNAL_PHONE", sender_phone)
        human_store.close()

        if not human:
            return "No data found for your phone number."

        human_id = human["id"]

        with neo4j_session() as session:
            # Count data
            msg_count = session.run(
                "MATCH (m:Message {humanId: $hid}) RETURN count(m) AS cnt",
                hid=human_id,
            ).single()["cnt"]

            thread_count = session.run(
                "MATCH (t:Thread {humanId: $hid}) RETURN count(t) AS cnt",
                hid=human_id,
            ).single()["cnt"]

            topic_count = session.run(
                "MATCH (:Human {id: $hid})-[:DISCUSSED]->(t:Topic) RETURN count(t) AS cnt",
                hid=human_id,
            ).single()["cnt"]

        lines = [
            f"**Your Data Summary**",
            "",
            f"**Name:** {human.get('displayName', '?')}",
            f"**Human ID:** {human_id[:12]}...",
            f"**Messages:** {msg_count}",
            f"**Threads:** {thread_count}",
            f"**Topics:** {topic_count}",
            f"**Identifiers:** {len(human.get('identifiers', []))}",
            "",
            "To receive a full JSON export, contact an admin.",
            "To delete all data: `/forget`",
        ]

        return "\n".join(lines)

    except Exception as e:
        return f"Error exporting data: {e}"


def handle_forget_request(sender_phone: str) -> str:
    """Handle /forget — first step (confirmation request)."""
    return ("**Data Deletion Request**\n\n"
            "This will permanently delete ALL your data:\n"
            "- All messages and conversations\n"
            "- Thread history and topics\n"
            "- Action items and inferences\n"
            "- Consent settings\n"
            "- Identity links\n\n"
            "Your Human node will be anonymized (not deleted) for graph integrity.\n\n"
            "**This cannot be undone.**\n\n"
            "To confirm, reply with exactly:\n"
            "`FORGET EVERYTHING`")


def handle_forget_confirm(sender_phone: str) -> str:
    """Handle FORGET EVERYTHING — execute deletion cascade."""
    try:
        from neo4j_human_v2 import HumanStoreV2
        from deletion_cascade import execute_deletion_cascade, verify_deletion

        human_store = HumanStoreV2()
        human = human_store.find_human_by_identifier("SIGNAL_PHONE", sender_phone)
        human_store.close()

        if not human:
            return "No data found. Nothing to delete."

        human_id = human["id"]

        # Execute deletion
        result = execute_deletion_cascade(human_id, confirm=True)

        if result.get("success"):
            counts = result.get("counts", {})
            total = result.get("total_deleted", 0)

            # Verify
            verification = verify_deletion(human_id)

            lines = [
                "**Data Deleted**",
                "",
                f"Messages: {counts.get('messages', 0)}",
                f"Threads: {counts.get('threads', 0)}",
                f"Action items: {counts.get('action_items', 0)}",
                f"Topic links: {counts.get('discussed_edges', 0)}",
                f"Inferences: {counts.get('inferences', 0)}",
                f"Total items: {total}",
                "",
            ]

            if verification.get("clean"):
                lines.append("Verification: All data confirmed deleted.")
            else:
                lines.append("Verification: Some residual data may remain. Contact admin.")

            lines.append("\nYour profile has been anonymized. Goodbye.")
            return "\n".join(lines)
        else:
            return f"Deletion failed: {result.get('error', 'Unknown error')}"

    except Exception as e:
        return f"Error during deletion: {e}"


# =============================================================================
# Main Entry Point
# =============================================================================

def handle_profile_command(text: str, sender_phone: str,
                           sender_name: Optional[str] = None) -> Optional[str]:
    """
    Handle a profile command from Signal.

    Args:
        text: The full message text
        sender_phone: Sender's phone number (E.164)
        sender_name: Optional sender display name

    Returns:
        Response message or None if not a profile command
    """
    parsed = parse_profile_command(text)

    if not parsed:
        return None

    store = HumanProfileStore()
    memory = HumanProfileMemory("main")

    try:
        action = parsed.get("action")

        # V2 privacy commands (use Human V2 system)
        if action == "privacy_show":
            return handle_privacy_show(sender_phone)

        elif action == "consent_toggle":
            return handle_consent_toggle(sender_phone, parsed.get("category", ""))

        elif action == "mydata":
            return handle_mydata(sender_phone)

        elif action == "forget_request":
            return handle_forget_request(sender_phone)

        elif action == "forget_confirm":
            return handle_forget_confirm(sender_phone)

        # Original profile commands
        elif action == "show":
            return handle_profile_show(store, sender_phone)

        elif action == "update":
            return handle_profile_update(
                store, sender_phone,
                parsed.get("field", ""),
                parsed.get("value", "")
            )

        elif action == "privacy":
            return handle_profile_privacy(store, sender_phone, parsed.get("level", ""))

        elif action == "consent_add":
            return handle_consent_add(store, sender_phone, parsed.get("category", ""))

        elif action == "consent_remove":
            return handle_consent_remove(store, sender_phone, parsed.get("category", ""))

        elif action == "consent_list":
            return handle_consent_list(store, sender_phone)

        elif action == "notes":
            return handle_profile_notes(
                store, memory, sender_phone,
                parsed.get("text", "")
            )

        elif action == "help":
            return format_help()

        else:
            return format_help()

    finally:
        store.close()


# =============================================================================
# Automatic Profile Extraction
# =============================================================================

def extract_profile_hints(text: str) -> Dict[str, Any]:
    """
    Extract potential profile updates from natural language.

    This can be called on any message to detect profile-related hints:
    - "I prefer to be called Dan" -> what_to_call: "Dan"
    - "I'm in the pacific timezone" -> timezone: "America/Los_Angeles"
    - "I don't like long messages" -> communication_style.detail_level: "brief"
    - "message me less" -> communication_style.messaging_frequency: "minimal"
    - "don't message before 9am" -> communication_style.quiet_hours: {"before": "09:00"}
    - "I care about security" -> communication_style.topics_of_interest: ["security"]

    Args:
        text: Message text to analyze

    Returns:
        Dict of extracted hints (may be empty)
    """
    hints = {}
    text_lower = text.lower()

    # Preferred name patterns
    name_patterns = [
        r'(?:prefer|like) to be called (\w+)',
        r'call me (\w+)',
        r'my name is (\w+)',
    ]
    for pattern in name_patterns:
        match = re.search(pattern, text_lower)
        if match:
            hints["what_to_call"] = match.group(1).capitalize()
            break

    # Timezone patterns
    tz_patterns = [
        (r'in (?:the )?(pacific|eastern|central|mountain) (?:time|timezone|zone)', {
            "pacific": "America/Los_Angeles",
            "eastern": "America/New_York",
            "central": "America/Chicago",
            "mountain": "America/Denver",
        }),
        (r'timezone is ([\w/]+)', None),
    ]
    for pattern, mapping in tz_patterns:
        match = re.search(pattern, text_lower)
        if match:
            tz_key = match.group(1)
            if mapping:
                hints["timezone"] = mapping.get(tz_key, tz_key)
            else:
                hints["timezone"] = tz_key
            break

    # Communication style patterns
    if any(phrase in text_lower for phrase in ["short messages", "brief", "concise", "to the point"]):
        hints["communication_style_detail_level"] = "brief"
    elif any(phrase in text_lower for phrase in ["detailed", "thorough", "comprehensive"]):
        hints["communication_style_detail_level"] = "detailed"

    if any(phrase in text_lower for phrase in ["morning person", "early bird", "best in morning"]):
        hints["communication_style_preferred_time"] = "morning"
    elif any(phrase in text_lower for phrase in ["night owl", "evening", "best at night"]):
        hints["communication_style_preferred_time"] = "evening"

    # --- Messaging frequency preferences ---
    less_phrases = [
        "message me less", "text me less", "fewer messages",
        "stop messaging so much", "too many messages",
        "less frequent", "reduce messages", "not so often",
        "only important", "only when important", "only for important",
        "only urgent", "only when urgent", "only critical",
        "don't bother me", "leave me alone", "back off",
        "less chatty", "stop spamming",
        "only message me for", "only text me for",
    ]
    more_phrases = [
        "message me more", "keep me posted", "keep me updated",
        "send me everything", "i want all updates", "more updates",
        "don't hold back", "tell me everything",
    ]
    if any(phrase in text_lower for phrase in less_phrases):
        hints["communication_style_messaging_frequency"] = "minimal"
    elif any(phrase in text_lower for phrase in more_phrases):
        hints["communication_style_messaging_frequency"] = "frequent"

    # --- Quiet hours / do-not-disturb ---
    quiet_before = re.search(
        r"(?:don'?t|no) (?:message|text|ping|bother|contact) (?:me )?(?:before|until) (\d{1,2})\s*(?::(\d{2}))?\s*(am|pm)?",
        text_lower
    )
    if quiet_before:
        hour = int(quiet_before.group(1))
        minute = int(quiet_before.group(2) or 0)
        ampm = quiet_before.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        hints["communication_style_quiet_hours_before"] = f"{hour:02d}:{minute:02d}"

    quiet_after = re.search(
        r"(?:don'?t|no) (?:message|text|ping|bother|contact) (?:me )?(?:after|past) (\d{1,2})\s*(?::(\d{2}))?\s*(am|pm)?",
        text_lower
    )
    if quiet_after:
        hour = int(quiet_after.group(1))
        minute = int(quiet_after.group(2) or 0)
        ampm = quiet_after.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        hints["communication_style_quiet_hours_after"] = f"{hour:02d}:{minute:02d}"

    # --- Topic preferences ---
    interest_match = re.search(
        r"i (?:care about|am interested in|want to hear about|like hearing about) (.+?)(?:\.|$)",
        text_lower
    )
    if interest_match:
        topic = interest_match.group(1).strip().rstrip(".")
        hints["communication_style_topic_interest"] = topic

    avoid_match = re.search(
        r"(?:don'?t|stop) (?:tell|message|notify|bother|send)(?:ing)? me (?:about|with|regarding|stuff about) (.+?)(?:\.|$)",
        text_lower
    )
    if avoid_match:
        topic = avoid_match.group(1).strip().rstrip(".")
        hints["communication_style_topic_avoid"] = topic

    # --- Formality ---
    if any(phrase in text_lower for phrase in ["be formal", "professional tone", "keep it professional"]):
        hints["communication_style_formality"] = "formal"
    elif any(phrase in text_lower for phrase in ["be casual", "chill", "keep it casual", "informal"]):
        hints["communication_style_formality"] = "casual"

    # --- Personal context: expertise ---
    expertise_match = re.search(
        r"i (?:work with|specialize in|know|am experienced in|am an? expert (?:in|on|with)) (.+?)(?:\.|,|$)",
        text_lower
    )
    if expertise_match:
        hints["personal_context_expertise"] = expertise_match.group(1).strip().rstrip(".")

    # --- Personal context: role ---
    role_match = re.search(
        r"i(?:'m| am) (?:a |an |the )?(\w+(?:\s+\w+)?)\s+(?:at|for|here)",
        text_lower
    )
    if role_match:
        role = role_match.group(1).strip()
        if role not in ("person", "user", "human", "member", "fan", "bit"):
            hints["personal_context_role"] = role

    # --- Personal context: location ---
    location_match = re.search(
        r"i(?:'m| am) (?:in|from|based in|located in) ([A-Z][\w\s,]+?)(?:\.|!|$)",
        text  # Use original case for location
    )
    if location_match:
        hints["personal_context_location"] = location_match.group(1).strip().rstrip(".")

    # --- Personal context: decision style ---
    if any(phrase in text_lower for phrase in ["just tell me what to do", "give me your recommendation", "just decide"]):
        hints["personal_context_decision_style"] = "wants recommendations"
    elif any(phrase in text_lower for phrase in ["give me options", "what are my choices", "let me decide"]):
        hints["personal_context_decision_style"] = "wants options"

    return hints


def apply_profile_hints(sender_phone: str, text: str,
                        confidence: float = 0.7) -> Optional[str]:
    """
    Extract and apply profile hints from a message.

    Args:
        sender_phone: Phone number
        text: Message text
        confidence: Confidence level for inferred updates

    Returns:
        Confirmation message or None if no hints found
    """
    hints = extract_profile_hints(text)

    if not hints:
        return None

    store = HumanProfileStore()

    try:
        # Ensure profile exists
        profile = store.get_profile_by_phone(sender_phone)
        if not profile:
            # Create minimal profile
            store.create_profile(
                human_id=sender_phone,
                display_name="User",
                source="inferred"
            )

        updates = {}
        comm_style_updates = {}
        personal_context_updates = {}
        topic_interests = []
        topic_avoids = []
        quiet_hours = {}
        profile = None  # lazy-loaded when needed

        for key, value in hints.items():
            if key == "communication_style_topic_interest":
                topic_interests.append(value)
            elif key == "communication_style_topic_avoid":
                topic_avoids.append(value)
            elif key == "communication_style_quiet_hours_before":
                quiet_hours["before"] = value
            elif key == "communication_style_quiet_hours_after":
                quiet_hours["after"] = value
            elif key.startswith("communication_style_"):
                field = key.replace("communication_style_", "")
                comm_style_updates[field] = value
            elif key.startswith("personal_context_"):
                field = key.replace("personal_context_", "")
                personal_context_updates[field] = value
            else:
                updates[key] = value

        # Apply direct updates
        if updates:
            for field, value in updates.items():
                store.update_field(sender_phone, field, value,
                                   updated_by="inference", source="inferred")

        # Apply communication style updates (merge into existing)
        if comm_style_updates or topic_interests or topic_avoids or quiet_hours:
            profile = store.get_profile_by_phone(sender_phone)
            comm_style = profile.get("communication_style", {})
            if not isinstance(comm_style, dict):
                comm_style = {}

            # Merge scalar updates
            comm_style.update(comm_style_updates)

            # Merge topics (append, deduplicate)
            if topic_interests:
                existing = comm_style.get("topics_of_interest", []) or []
                comm_style["topics_of_interest"] = list(set(existing + topic_interests))

            if topic_avoids:
                existing = comm_style.get("topics_to_avoid", []) or []
                comm_style["topics_to_avoid"] = list(set(existing + topic_avoids))

            # Merge quiet hours
            if quiet_hours:
                existing_qh = comm_style.get("quiet_hours") or {}
                if not isinstance(existing_qh, dict):
                    existing_qh = {}
                existing_qh.update(quiet_hours)
                comm_style["quiet_hours"] = existing_qh

            store.update_field(sender_phone, "communication_style", comm_style,
                               updated_by="inference", source="inferred")

        # Apply personal context updates (merge into existing)
        if personal_context_updates:
            if not profile:
                profile = store.get_profile_by_phone(sender_phone)
            personal_ctx = profile.get("personal_context", {})
            if not isinstance(personal_ctx, dict):
                personal_ctx = {}

            for field, value in personal_context_updates.items():
                if field == "expertise":
                    # Append to expertise list
                    existing = personal_ctx.get("expertise", []) or []
                    personal_ctx["expertise"] = list(set(existing + [value]))
                else:
                    personal_ctx[field] = value

            store.update_field(sender_phone, "personal_context", personal_ctx,
                               updated_by="inference", source="inferred")

        # Build human-readable confirmation
        readable = []
        for key in hints:
            label = key.replace("communication_style_", "").replace("personal_context_", "").replace("_", " ")
            readable.append(label)
        return f"_Noted: Updated your preferences ({', '.join(readable)})_"

    finally:
        store.close()


# =============================================================================
# Context Enrichment
# =============================================================================

def get_context_for_conversation(phone_numbers: list) -> Dict[str, Dict[str, Any]]:
    """
    Get profile context for enriching a conversation.

    Args:
        phone_numbers: List of phone numbers in the conversation

    Returns:
        Dict mapping phone numbers to profile context
    """
    store = HumanProfileStore()

    try:
        profiles = store.get_profiles_for_context(phone_numbers)

        context = {}
        for profile in profiles:
            human_id = profile.get("human_id")
            if human_id:
                comm_style = profile.get("communication_style", {})
                if not isinstance(comm_style, dict):
                    comm_style = {}

                personal = profile.get("personal_context", {})
                if not isinstance(personal, dict):
                    personal = {}

                ctx = {
                    "name": profile.get("what_to_call") or profile.get("display_name"),
                    "timezone": profile.get("timezone"),
                    "communication_style": comm_style,
                    "projects": profile.get("projects", {}).get("active", []),
                }

                # Surface key chat preferences at top level for easy access
                if comm_style.get("messaging_frequency"):
                    ctx["messaging_frequency"] = comm_style["messaging_frequency"]
                if comm_style.get("quiet_hours"):
                    ctx["quiet_hours"] = comm_style["quiet_hours"]
                if comm_style.get("topics_to_avoid"):
                    ctx["topics_to_avoid"] = comm_style["topics_to_avoid"]
                if comm_style.get("formality"):
                    ctx["formality"] = comm_style["formality"]
                if comm_style.get("detail_level") and comm_style["detail_level"] != "moderate":
                    ctx["detail_level"] = comm_style["detail_level"]

                # Surface personal context at top level
                if personal.get("expertise"):
                    ctx["expertise"] = personal["expertise"]
                if personal.get("role"):
                    ctx["role"] = personal["role"]
                if personal.get("decision_style"):
                    ctx["decision_style"] = personal["decision_style"]
                if personal.get("personal_facts"):
                    ctx["personal_facts"] = personal["personal_facts"]

                # Sentiment is ephemeral — 24h TTL
                if personal.get("last_sentiment") and personal.get("last_interaction"):
                    try:
                        last_ts = datetime.fromisoformat(personal["last_interaction"])
                        if (datetime.now() - last_ts).total_seconds() < 86400:
                            ctx["last_sentiment"] = personal["last_sentiment"]
                    except (ValueError, TypeError):
                        pass

                context[human_id] = ctx

        return context

    finally:
        store.close()


def format_context_for_agent(sender_context: Dict[str, Any]) -> str:
    """
    Format loaded profile context into a concise instruction block
    that agents can use when crafting responses.

    Args:
        sender_context: Profile context dict from get_context_for_conversation

    Returns:
        Human-readable context string, or empty string if no meaningful context
    """
    if not sender_context:
        return ""

    lines = []
    name = sender_context.get("name")
    if name:
        lines.append(f"Talking to: {name}")

    role = sender_context.get("role")
    if role:
        lines.append(f"Role: {role}")

    tz = sender_context.get("timezone")
    if tz:
        lines.append(f"Timezone: {tz}")

    # Communication preferences (actionable)
    freq = sender_context.get("messaging_frequency")
    if freq and freq != "normal":
        if freq == "minimal":
            lines.append("PREF: Keep messages brief and infrequent. Only contact for important items.")
        elif freq == "frequent":
            lines.append("PREF: This person wants frequent updates.")

    formality = sender_context.get("formality")
    if formality and formality != "casual":
        lines.append(f"PREF: Use {formality} tone.")

    detail = sender_context.get("detail_level")
    if detail:
        if detail == "brief":
            lines.append("PREF: Keep responses short and to the point.")
        elif detail == "detailed":
            lines.append("PREF: This person prefers detailed, thorough responses.")

    quiet = sender_context.get("quiet_hours")
    if quiet and isinstance(quiet, dict):
        parts = []
        if quiet.get("before"):
            parts.append(f"before {quiet['before']}")
        if quiet.get("after"):
            parts.append(f"after {quiet['after']}")
        if parts:
            lines.append(f"PREF: Quiet hours — do not message {' or '.join(parts)}.")

    avoid = sender_context.get("topics_to_avoid")
    if avoid:
        lines.append(f"PREF: Avoid topics: {', '.join(avoid)}")

    decision = sender_context.get("decision_style")
    if decision:
        lines.append(f"PREF: Decision style — {decision}.")

    sentiment = sender_context.get("last_sentiment")
    if sentiment and sentiment != "neutral":
        lines.append(f"NOTE: Last interaction sentiment was {sentiment}.")

    expertise = sender_context.get("expertise")
    if expertise:
        lines.append(f"Expertise: {', '.join(expertise)}")

    facts = sender_context.get("personal_facts")
    if facts:
        lines.append(f"Facts: {'; '.join(facts[:5])}")

    if len(lines) <= 1:
        return ""

    return "--- Person Context ---\n" + "\n".join(lines) + "\n--- End Context ---"


if __name__ == "__main__":
    # Test the module
    import sys

    # Test parsing
    test_cases = [
        "profile show",
        "profile update timezone America/New_York",
        "profile privacy private",
        "profile consent add calendar",
        "profile consent list",
        "profile notes I like coffee",
        "profile what_to_call Danny",
        "profile timezone America/Los_Angeles",
    ]

    print("Testing command parser:")
    for cmd in test_cases:
        parsed = parse_profile_command(cmd)
        print(f"  {cmd!r} -> {parsed}")

    print("\nTesting profile hints extraction:")
    hint_tests = [
        "I prefer to be called Dan",
        "I'm in the pacific timezone",
        "I like short messages",
        "I'm a morning person",
    ]
    for text in hint_tests:
        hints = extract_profile_hints(text)
        print(f"  {text!r} -> {hints}")
