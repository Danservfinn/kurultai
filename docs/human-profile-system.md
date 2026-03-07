# Human Profile Storage System

Complete implementation of the human profile storage system for the Kurultai.

## Overview

This system stores and retrieves contextual information about humans the Kurultai interacts with. It provides:

- **Structured storage** in Neo4j for queryable data
- **Narrative storage** in Markdown files for rich context
- **Privacy controls** with consent categories and privacy levels
- **Signal integration** for profile commands
- **Natural language queries** ("what do I know about Danny?")

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Signal CLI    │────►│ Profile Handler │────►│ Neo4j         │
│   (messages)    │     │ (commands/NL)   │     │ (structured)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │ File Memory     │
                        │ (humans/*.md)   │
                        └─────────────────┘
```

## Components

### 1. Neo4j Schema (`neo4j_human_profile_schema.cypher`)

Cypher schema defining:
- `HumanProfile` node with rich properties
- `ConsentCategory` nodes for privacy management
- `Tag` nodes for flexible categorization
- Indexes and constraints for performance
- Query patterns for common operations

### 2. Neo4j CRUD (`neo4j_human_profile.py`)

Python module with:
- `HumanProfileStore` class for all CRUD operations
- Consent management
- Privacy filtering
- Tagging system
- Profile search

### 3. File Memory (`human_profile_memory.py`)

Python module for:
- Markdown-based narrative storage
- Conversation history tracking
- Bidirectional sync with Neo4j
- Rich context preservation

### 4. Signal Integration (`profile_handler.py`)

Command handler for:
- `profile show` - Display profile
- `profile update <field> <value>` - Update fields
- `profile timezone <tz>` - Set timezone
- `profile privacy <level>` - Set privacy
- `profile consent add/remove <category>` - Manage consent
- `profile notes <text>` - Add personal notes

## Quick Start

### 1. Initialize the Schema

```bash
cd ~/.openclaw/agents/main/scripts
python3 neo4j_human_profile.py init
```

Or run the Cypher directly:

```bash
cat neo4j_human_profile_schema.cypher | cypher-shell
```

### 2. Create a Profile (Python)

```python
from neo4j_human_profile import HumanProfileStore

store = HumanProfileStore()

# Create profile
store.create_profile(
    human_id="+19194133445",
    display_name="Danny",
    timezone="America/New_York",
    what_to_call="Danny",
    source="manual"
)

# Add consent
store.add_consent("+19194133445", "calendar")
store.add_consent("+19194133445", "tasks")

# Update preferences
store.update_field(
    "+19194133445",
    "communication_style",
    {
        "preferred_channel": "signal",
        "preferred_time": "morning",
        "response_style": "direct",
        "emoji_friendly": True,
        "detail_level": "brief"
    }
)

# Get profile
profile = store.get_profile_by_phone("+19194133445")
print(f"Name: {profile['display_name']}")
print(f"Timezone: {profile['timezone']}")

store.close()
```

### 3. Use Signal Commands

Send these commands via Signal:

```
profile show                           # View your profile
profile update timezone America/NYC    # Update timezone
profile privacy contacts               # Set privacy level
profile consent add calendar           # Allow calendar storage
profile notes I prefer async updates   # Add personal notes
```

### 4. File-Based Memory

```python
from human_profile_memory import HumanProfileMemory

memory = HumanProfileMemory("main")

# Write rich profile
memory.write_profile("+19194133445", {
    "display_name": "Danny",
    "notes": "Coffee enthusiast, likes hiking",
    "conversations": [
        {
            "date": "2026-03-07",
            "channel": "Signal",
            "topic": "Feature planning",
            "summary": "Discussed calendar integration"
        }
    ]
})

# Add conversation snippet
memory.add_conversation("+19194133445", {
    "date": "2026-03-07",
    "channel": "Signal",
    "topic": "Profile system",
    "summary": "Asked about profile storage",
    "insights": ["Values privacy", "Prefers async communication"]
})
```

### 5. Sync Neo4j to Files

```python
from human_profile_memory import ProfileSync

sync = ProfileSync("main")

# Sync single profile
sync.sync_to_file("+19194133445")

# Sync all profiles
sync.sync_all_to_files()

sync.close()
```

### 6. Natural Language Queries

```python
from neo4j_human_profile import HumanProfileStore

store = HumanProfileStore()

# Search profiles
results = store.search_profiles("Danny")

# Get communication preferences
prefs = store.get_communication_preferences("+19194133445")

# Get context for conversation
context = store.get_profiles_for_context(["+19194133445", "+15551234567"])

store.close()
```

## Schema Reference

### HumanProfile Properties

| Property | Type | Description |
|----------|------|-------------|
| `profile_id` | String | UUID (e.g., "hp-a1b2c3d4") |
| `human_id` | String | Phone number (E.164 format) |
| `display_name` | String | Preferred display name |
| `what_to_call` | String | How to address them |
| `pronouns` | String | Optional pronouns |
| `timezone` | String | IANA timezone |
| `communication_style` | Map | JSON object with preferences |
| `preferences` | Map | JSON object with settings |
| `projects` | Map | JSON object with project info |
| `privacy_level` | String | "public", "contacts", "private" |
| `consent_categories` | List | Active consents |
| `source` | String | "signal", "manual", "inferred" |
| `confidence` | Float | 0.0-1.0 accuracy score |
| `status` | String | "active", "anonymized", "deleted" |

### Consent Categories

| Category | Description |
|----------|-------------|
| `calendar` | Store event preferences |
| `tasks` | Remember task assignments |
| `research` | Store research interests |
| `social` | Personal context |
| `marketing` | Product updates |

### Privacy Levels

| Level | Access |
|-------|--------|
| `public` | Any agent |
| `contacts` | Signal group members |
| `private` | Owner + admin agents |

## Integration with Calendar System

The profile system integrates with Signal Calendar:

```python
from neo4j_human_profile import HumanProfileStore
from neo4j_calendar import get_or_create_person

# When creating a calendar person, also create profile
person = get_or_create_person("+19194133445", "Danny")

store = HumanProfileStore()
store.create_profile(
    human_id="+19194133445",
    display_name="Danny",
    source="calendar"
)
store.close()
```

## Testing

Run the module tests:

```bash
cd ~/.openclaw/agents/main/scripts

# Test Neo4j module
python3 neo4j_human_profile.py

# Test file memory
python3 human_profile_memory.py

# Test profile handler
python3 profile_handler.py
```

## File Locations

| File | Location |
|------|----------|
| Schema | `main/scripts/neo4j_human_profile_schema.cypher` |
| Neo4j CRUD | `main/scripts/neo4j_human_profile.py` |
| File Memory | `main/scripts/human_profile_memory.py` |
| Signal Handler | `main/scripts/profile_handler.py` |
| Profile Files | `{agent}/memory/humans/{phone}.md` |

## Security & Privacy

1. **Consent Required**: No data stored without explicit consent
2. **Privacy Levels**: Field-level access control
3. **Right to Deletion**: Soft delete (anonymize) or hard delete available
4. **Audit Trail**: All updates tracked with timestamps
5. **Confidence Decay**: Old data confidence decreases over time

## Future Enhancements

- [ ] Automatic profile extraction from conversations
- [ ] Profile suggestions ("I noticed you mentioned...")
- [ ] Cross-profile relationship mapping
- [ ] Profile analytics dashboard
- [ ] Bulk import/export

## License

Part of the Kurultai OpenClaw system.
