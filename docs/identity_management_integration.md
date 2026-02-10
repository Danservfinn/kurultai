# Identity Management System - Integration Guide

How to integrate the Identity Management System into Kurultai's message flow.

## Overview

The Identity Management System provides hooks at two critical points:

1. **Message Reception** (`on_message_received`): Captures sender info, builds context
2. **Message Sending** (`filter_outgoing_message`): Ensures privacy before sending

## Quick Start

### 1. Initialize the System

```python
from tools.kurultai_identity_system import KurultaiIdentitySystem

# Create and initialize
identity_system = KurultaiIdentitySystem(
    neo4j_uri="bolt://localhost:7687",
    neo4j_username="neo4j",
    neo4j_password=os.environ["NEO4J_PASSWORD"]
)

if not identity_system.initialize():
    logger.warning("Identity system in fallback mode")
```

### 2. Use Singleton (Recommended)

```python
from tools.kurultai_identity_system import get_identity_system

# Gets or creates singleton
system = get_identity_system(
    neo4j_uri="bolt://localhost:7687",
    neo4j_password=os.environ["NEO4J_PASSWORD"]
)

# Use throughout your application
```

## Message Reception Integration

### Basic Usage

```python
# When a message is received
def handle_incoming_message(message):
    # Build identity context
    context = identity_system.on_message_received(
        channel=message.channel,           # "signal", "discord", etc.
        sender_handle=message.sender_id,   # Phone number, username, etc.
        sender_name=message.sender_name,   # Display name
        message_text=message.text,         # Message content
        sender_hash=message.sender_hash    # For isolation
    )
    
    # Use context in response generation
    response = generate_response(
        message=message,
        person_context=context
    )
    
    return response
```

### Extracting Facts

After processing a message, extract facts:

```python
# Extract facts from NLP analysis
extracted_facts = nlp_extract_facts(message.text)
# Returns: [{"type": "preference", "key": "style", "value": "direct", "confidence": 0.9}]

# Store them with automatic privacy classification
stored_facts = identity_system.extract_facts_from_message(
    person_id=context["person_id"],
    message_text=message.text,
    extracted_facts=extracted_facts
)
```

### Recording Conversations

After responding, record the conversation:

```python
# Record conversation summary
conversation = identity_system.record_conversation_summary(
    person_id=context["person_id"],
    channel=message.channel,
    summary="Discussed project architecture and preferences",
    topics=["architecture", "preferences"],
    message_count=15,
    duration_minutes=20
)
```

## Message Sending Integration

### Filtering Outgoing Messages

Always filter responses before sending:

```python
def send_response(content, recipient_id):
    # Filter for privacy
    filtered = identity_system.filter_outgoing_message(
        content=content,
        sender_person_id=None,          # System message, or use sender's ID
        recipient_person_id=recipient_id,
        agent_name="kurultai"
    )
    
    if not filtered["safe_to_send"]:
        logger.warning(f"Privacy violation: {filtered['violations']}")
        # Handle appropriately
        
    # Send filtered content
    send_message(filtered["content"])
```

### Building Response Context

For personalized responses:

```python
# Get rich context for response generation
response_context = identity_system.build_response_context(
    recipient_person_id=person_id,
    current_message=message_text
)

# Use in prompt
prompt = f"""
You are responding to: {response_context['person_name']}

Context:
- Known for: {len(response_context['facts'])} facts
- Recent topics: {[t['name'] for t in response_context['context']['recurring_topics']]}
- Conversations this month: {response_context['context']['total_conversations_30d']}

Respond naturally using this context.
"""
```

## Advanced Usage

### Direct Component Access

Access individual components for advanced operations:

```python
# Identity Manager
person = identity_system.identity.get_person("signal:+1234567890")
facts = identity_system.identity.get_facts(
    person_id="signal:+1234567890",
    privacy_levels=[PrivacyLevel.PUBLIC, PrivacyLevel.PRIVATE]
)

# Context Memory
conversations = identity_system.context.get_conversations(
    person_id="signal:+1234567890",
    days=7,
    include_topics=["architecture"]
)

similar = identity_system.context.find_similar_conversations(
    person_id="signal:+1234567890",
    query_text="database design",
    limit=3
)

# Privacy Guard
audit_entries = identity_system.privacy.get_audit_log(
    person_id="signal:+1234567890",
    days=30
)

access_summary = identity_system.privacy.get_access_summary(
    person_id="signal:+1234567890",
    days=7
)
```

### Privacy Policy Configuration

Customize privacy policies:

```python
from tools.privacy_guard import PrivacyPolicy, PrivacyLevel

policy = PrivacyPolicy(
    default_fact_privacy=PrivacyLevel.PRIVATE,
    default_preference_privacy=PrivacyLevel.PRIVATE,
    retain_audit_logs_days=90,
    auto_archive_conversations_days=30,
    enable_privacy_filtering=True,
    enable_audit_logging=True,
    sensitive_keywords=["password", "secret", "ssn"],
    redaction_placeholder="[REDACTED]"
)

system = KurultaiIdentitySystem(
    neo4j_password=os.environ["NEO4J_PASSWORD"],
    privacy_policy=policy
)
```

### Cross-Person Information Sharing

Check if information can be shared:

```python
# Can we share Alice's private info with Bob?
can_share = identity_system.can_share_information(
    source_person_id="signal:alice",
    target_person_id="signal:bob",
    information_privacy=PrivacyLevel.PRIVATE
)
# Returns: False

# Get only public facts about Alice
public_facts = identity_system.get_safe_facts_for_sharing(
    source_person_id="signal:alice",
    target_person_id="signal:bob",
    fact_type=FactType.PREFERENCE,
    limit=10
)
```

## Signal Integration Example

```python
class SignalHandler:
    def __init__(self):
        self.identity = get_identity_system()
    
    async def on_message(self, envelope):
        # Extract sender info
        sender_number = envelope.sourceNumber()
        sender_name = envelope.sourceName() or sender_number
        message_text = envelope.dataMessage().message()
        
        # Build identity context
        context = self.identity.on_message_received(
            channel="signal",
            sender_handle=sender_number,
            sender_name=sender_name,
            message_text=message_text,
            sender_hash=hash(sender_number)
        )
        
        # Build response context
        response_ctx = self.identity.build_response_context(
            recipient_person_id=context["person_id"],
            current_message=message_text
        )
        
        # Generate response
        response_text = await self.generate_response(
            message=message_text,
            context=response_ctx
        )
        
        # Filter for privacy
        filtered = self.identity.filter_outgoing_message(
            content=response_text,
            sender_person_id=None,
            recipient_person_id=context["person_id"]
        )
        
        # Send response
        await self.send_message(
            recipient=sender_number,
            content=filtered["content"]
        )
        
        # Record conversation
        self.identity.record_conversation_summary(
            person_id=context["person_id"],
            channel="signal",
            summary=f"Exchanged {len(message_text.split())} messages",
            topics=self.extract_topics(message_text),
            message_count=2
        )
```

## Discord Integration Example

```python
class DiscordBot(commands.Bot):
    def __init__(self):
        super().__init__()
        self.identity = get_identity_system()
    
    async def on_message(self, message):
        if message.author == self.user:
            return
        
        # Build context
        ctx = self.identity.on_message_received(
            channel="discord",
            sender_handle=str(message.author.id),
            sender_name=message.author.display_name,
            message_text=message.content
        )
        
        # Process command or generate response
        if message.content.startswith('!'):
            await self.process_commands(message)
        else:
            # Generate contextual response
            response_ctx = self.identity.build_response_context(ctx["person_id"])
            response = self.generate_response(message.content, response_ctx)
            
            # Filter and send
            filtered = self.identity.filter_outgoing_message(
                response, None, ctx["person_id"]
            )
            await message.channel.send(filtered["content"])
```

## Slack Integration Example

```python
@app.event("message")
def handle_slack_message(event, say):
    user_id = event.get("user")
    channel_id = event.get("channel")
    text = event.get("text")
    
    # Get user info from Slack
    user_info = app.client.users_info(user=user_id)
    user_name = user_info["user"]["real_name"]
    
    # Build identity context
    ctx = identity_system.on_message_received(
        channel="slack",
        sender_handle=user_id,
        sender_name=user_name,
        message_text=text
    )
    
    # Generate response
    response_ctx = identity_system.build_response_context(ctx["person_id"])
    response = generate_response(text, response_ctx)
    
    # Filter and send
    filtered = identity_system.filter_outgoing_message(
        response, None, ctx["person_id"]
    )
    
    say(filtered["content"])
```

## Maintenance

### Run Maintenance Tasks

```python
# Periodic maintenance (run daily/weekly)
results = identity_system.run_maintenance()
print(f"Purged {results['audit_logs_purged']} audit logs")
print(f"Archived {results['conversations_archived']} conversations")
```

### Manual Maintenance

```python
# Purge old audit logs
deleted = identity_system.privacy.purge_expired_audit_logs()

# Archive old conversations
archived = identity_system.privacy.archive_old_conversations(days=30)

# Get system stats
stats = identity_system.get_system_stats()
print(stats)
```

## Testing

```python
# Test identity tracking
context = identity_system.on_message_received(
    channel="test",
    sender_handle="test-user",
    sender_name="Test User"
)

# Test fact extraction
facts = identity_system.extract_facts_from_message(
    person_id=context["person_id"],
    message_text="I prefer direct communication",
    extracted_facts=[{
        "type": "preference",
        "key": "communication_style",
        "value": "direct",
        "confidence": 0.9
    }]
)

# Test privacy filtering
filtered = identity_system.filter_outgoing_message(
    content="The password is secret123",
    sender_person_id=None,
    recipient_person_id=context["person_id"]
)

assert "secret123" not in filtered["content"]
```

## Error Handling

```python
try:
    context = identity_system.on_message_received(...)
except Exception as e:
    logger.error(f"Identity tracking failed: {e}")
    # Continue without identity context
    context = {"person_id": None, "known_identity": False}

# Fallback mode
if not identity_system._initialized:
    logger.warning("Identity system in fallback mode - data not persisted")
```

## Best Practices

1. **Always filter outgoing messages** - Never send unfiltered content
2. **Log all sensitive access** - Audit trail is automatic but verify it's enabled
3. **Check privacy levels** - Use `can_share_information()` before cross-person sharing
4. **Run maintenance** - Schedule regular cleanup of old data
5. **Handle failures gracefully** - System works in fallback mode if Neo4j is down
6. **Use appropriate privacy levels**:
   - `PUBLIC`: General preferences, interests
   - `PRIVATE`: Personal details, contact info
   - `SENSITIVE`: Financial, health, credentials

## Troubleshooting

### Neo4j Connection Issues

```python
# Check connection
if not identity_system.initialize():
    print("Neo4j unavailable - running in fallback mode")
```

### Privacy Filter Not Working

```python
# Check if filtering is enabled
print(identity_system.privacy.policy.enable_privacy_filtering)

# Check content
result = identity_system.privacy.check_content_privacy(
    content="test content",
    target_privacy=PrivacyLevel.PUBLIC
)
print(result)
```

### Missing Audit Logs

```python
# Check if audit logging is enabled
print(identity_system.privacy.policy.enable_audit_logging)

# Verify audit entries
logs = identity_system.privacy.get_audit_log(days=7)
print(f"Found {len(logs)} audit entries")
```
