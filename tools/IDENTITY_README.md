# Kurultai Identity Management System

A comprehensive identity and privacy management system for the Kurultai multi-agent platform.

## Features

- **Identity Tracking**: Track people across channels (Signal, Discord, Slack, etc.)
- **Fact Storage**: Store facts with privacy levels (public, private, sensitive)
- **Context Memory**: Remember conversations, topics, and preferences
- **Privacy Guard**: Enforce privacy policies and maintain audit trails
- **Semantic Search**: Find similar conversations using vector embeddings

## Components

### 1. Identity Manager (`tools/identity_manager.py`)

Core identity tracking:

```python
from tools.identity_manager import IdentityManager, FactType, PrivacyLevel

manager = IdentityManager(neo4j_password="password")
manager.initialize()

# Get or create person
person = manager.get_or_create_person(
    channel="signal",
    handle="+1234567890",
    name="Alice"
)

# Add facts
fact = manager.add_fact(
    person_id=person.id,
    fact_type=FactType.PREFERENCE,
    key="communication_style",
    value="direct",
    privacy_level=PrivacyLevel.PUBLIC,
    confidence=0.9
)

# Get context
context = manager.get_person_context(person.id)
```

### 2. Context Memory (`tools/context_memory.py`)

Conversation and topic tracking:

```python
from tools.context_memory import ContextMemory

memory = ContextMemory(neo4j_password="password")
memory.initialize()

# Record conversation
conv = memory.record_conversation(
    person_id="signal:+1234567890",
    channel="signal",
    summary="Discussed project architecture",
    topics=["architecture", "database"],
    message_count=15
)

# Find similar conversations
similar = memory.find_similar_conversations(
    person_id="signal:+1234567890",
    query_text="database design",
    limit=3
)
```

### 3. Privacy Guard (`tools/privacy_guard.py`)

Privacy enforcement and audit:

```python
from tools.privacy_guard import PrivacyGuard, PrivacyLevel

guard = PrivacyGuard(neo4j_password="password")
guard.initialize()

# Check content privacy
result = guard.check_content_privacy(
    "My email is user@example.com",
    target_privacy=PrivacyLevel.PUBLIC
)

# Filter content for audience
filtered = guard.filter_content_for_audience(
    content="Alice's password is secret123",
    owner_person_id="signal:alice",
    audience_person_id="signal:bob"
)
# Returns: "Alice's password is [REDACTED]"

# Get audit log
audits = guard.get_audit_log(person_id="signal:alice", days=30)
```

### 4. Unified System (`tools/kurultai_identity_system.py`)

Combined interface for easy integration:

```python
from tools.kurultai_identity_system import KurultaiIdentitySystem

system = KurultaiIdentitySystem(neo4j_password="password")
system.initialize()

# Message received - track identity
context = system.on_message_received(
    channel="signal",
    sender_handle="+1234567890",
    sender_name="Alice"
)

# Build response context
response_ctx = system.build_response_context(context["person_id"])

# Filter outgoing message
filtered = system.filter_outgoing_message(
    content=response_text,
    sender_person_id=None,
    recipient_person_id=context["person_id"]
)

# Record conversation
system.record_conversation_summary(
    person_id=context["person_id"],
    channel="signal",
    summary="Discussed preferences",
    topics=["preferences"]
)
```

## Schema Migration

Apply the Neo4j schema:

```bash
# Run migration
python migrations/v4_identity_management.py

# Or programmatically
from migrations.v4_identity_management import V4IdentityManagement
from migrations.migration_manager import MigrationManager

with MigrationManager(uri, user, password) as manager:
    V4IdentityManagement.register(manager)
    manager.migrate(target_version=4)
```

## Neo4j Schema

### Node Types

- **Person**: Individual identities across channels
- **Fact**: Information about people with privacy levels
- **Preference**: User preferences
- **Conversation**: Conversation summaries
- **Topic**: Recurring discussion topics
- **AuditLog**: Access audit trail

### Privacy Levels

- **PUBLIC**: Can be shared freely
- **PRIVATE**: Only for the person themselves
- **SENSITIVE**: Requires explicit authorization

### Indexes

- 6 unique constraints
- 20 performance indexes
- 1 vector index for semantic search
- 2 full-text indexes

See `docs/identity_management_schema.md` for complete schema documentation.

## Integration

See `docs/identity_management_integration.md` for detailed integration guides for:

- Signal
- Discord
- Slack
- Custom channels

### Quick Integration Example

```python
from tools.kurultai_identity_system import get_identity_system

# Get singleton instance
system = get_identity_system(neo4j_password="password")

# Hook into message reception
def on_message(channel, sender, text):
    ctx = system.on_message_received(channel, sender, text)
    
    # Generate response with context
    response = generate_response(text, ctx)
    
    # Filter and send
    filtered = system.filter_outgoing_message(
        response, None, ctx["person_id"]
    )
    send_message(filtered["content"])
```

## Testing

Run tests:

```bash
pytest tests/test_identity_management.py -v
```

## Configuration

Environment variables:

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

## Maintenance

Run periodic maintenance:

```python
# In your heartbeat or scheduled task
results = system.run_maintenance()
print(f"Purged {results['audit_logs_purged']} audit logs")
print(f"Archived {results['conversations_archived']} conversations")
```

## API Reference

### IdentityManager

- `get_or_create_person(channel, handle, name)` - Get or create identity
- `get_person(person_id)` - Get person by ID
- `add_fact(person_id, fact_type, key, value, privacy_level)` - Add fact
- `get_facts(person_id, privacy_levels, min_confidence)` - Get facts
- `get_person_context(person_id, include_private, include_sensitive)` - Build context

### ContextMemory

- `record_conversation(person_id, channel, summary, topics)` - Record conversation
- `get_conversations(person_id, limit, days, include_topics)` - Get conversations
- `find_similar_conversations(person_id, query_text, limit)` - Semantic search
- `get_recurring_topics(person_id, min_frequency)` - Get recurring topics

### PrivacyGuard

- `check_content_privacy(content, target_privacy)` - Check for sensitive content
- `filter_content_for_audience(content, owner, audience)` - Filter for audience
- `get_audit_log(person_id, action, days)` - Get audit trail
- `purge_expired_audit_logs()` - Clean up old audit logs

### KurultaiIdentitySystem

- `on_message_received(channel, sender_handle, sender_name)` - Track incoming message
- `build_response_context(person_id, current_message)` - Build context for response
- `filter_outgoing_message(content, sender, recipient)` - Filter outgoing message
- `record_conversation_summary(person_id, channel, summary, topics)` - Record conversation

## License

Part of the Kurultai project.
