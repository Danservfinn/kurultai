# Identity Management System - Neo4j Schema

Complete Neo4j schema for Kurultai's Identity Management System.

## Node Types

### Person
Represents an individual across all channels.

```cypher
(:Person {
  id: string,              // Unique ID: "{channel}:{handle}"
  name: string,            // Display name
  handle: string,          // Channel-specific identifier
  channel: string,         // signal, discord, slack, etc.
  email: string,           // Optional email
  phone: string,           // Optional phone
  first_seen: datetime,    // When first encountered
  last_seen: datetime,     // When last active
  total_conversations: int,// Count of conversations
  is_active: boolean,      // Active status
  sender_hash: string,     // For sender isolation
  metadata: map            // Additional metadata
})
```

### Fact
Stores information about a person with privacy classification.

```cypher
(:Fact {
  id: uuid,
  person_id: string,       // Reference to Person
  fact_type: string,       // preference, habit, identity, etc.
  fact_key: string,        // Category/key
  fact_value: string,      // The fact itself
  privacy_level: string,   // public, private, sensitive
  confidence: float,       // 0.0 to 1.0
  source: string,          // Where fact came from
  created_at: datetime,
  updated_at: datetime,
  expires_at: datetime,    // Optional expiration
  verification_count: int  // Times confirmed
})
```

### Preference
User preferences with category and priority.

```cypher
(:Preference {
  id: uuid,
  person_id: string,
  category: string,        // communication, work_style, etc.
  pref_key: string,
  pref_value: string,
  priority: int,           // 1-10 importance
  privacy_level: string,
  created_at: datetime,
  updated_at: datetime,
  expires_at: datetime
})
```

### Conversation
Stores conversation summaries and metadata.

```cypher
(:Conversation {
  id: uuid,
  person_id: string,
  channel: string,
  timestamp: datetime,
  summary: string,         // Conversation summary
  topics: [string],        // List of topics
  content_snippet: string, // Sample content
  message_count: int,
  duration_minutes: int,
  embedding: [float],      // Vector embedding (384-dim)
  archived: boolean,
  archived_at: datetime,
  metadata: map
})
```

### Topic
Tracks recurring discussion topics.

```cypher
(:Topic {
  id: uuid,
  name: string,            // Display name
  normalized_name: string, // Lowercase normalized
  first_discussed: datetime,
  last_discussed: datetime,
  frequency: int           // Times discussed
})
```

### AuditLog
Records all access to private/sensitive data.

```cypher
(:AuditLog {
  id: uuid,
  person_id: string,       // Whose data was accessed
  fact_id: string,         // Which fact (optional)
  action: string,          // read, write, delete, share, filter
  accessed_by: string,     // Agent/system that accessed
  accessed_at: datetime,
  privacy_level: string,   // Level of data accessed
  context: string,         // Why it was accessed
  recipient: string,       // If shared, who received
  was_filtered: boolean,   // Content was filtered
  retain_until: datetime   // When to purge
})
```

### IdentityPrivacyConfig
System-wide privacy configuration.

```cypher
(:IdentityPrivacyConfig {
  id: "default",
  default_fact_privacy: string,
  default_preference_privacy: string,
  retain_audit_logs_days: int,
  auto_archive_conversations_days: int,
  max_conversation_history: int,
  enable_privacy_filtering: boolean,
  enable_audit_logging: boolean
})
```

## Relationships

### HAS_FACT
Connects Person to their facts.

```cypher
(:Person)-[:HAS_FACT {
  created_at: datetime
}]->(:Fact)
```

### HAS_PREFERENCE
Connects Person to their preferences.

```cypher
(:Person)-[:HAS_PREFERENCE {
  created_at: datetime,
  updated_at: datetime
}]->(:Preference)
```

### PARTICIPATED_IN
Connects Person to their conversations.

```cypher
(:Person)-[:PARTICIPATED_IN {
  at: datetime
}]->(:Conversation)
```

### DISCUSSED_TOPIC
Links conversations and persons to topics.

```cypher
(:Conversation)-[:DISCUSSED_TOPIC {
  at: datetime
}]->(:Topic)

(:Person)-[:DISCUSSED_TOPIC {
  count: int
}]->(:Topic)
```

### RELATED_TO
Links related conversations.

```cypher
(:Conversation)-[:RELATED_TO {
  created_at: datetime,
  strength: int
}]->(:Conversation)
```

### ACCESS_AUDIT
Links audit logs to persons.

```cypher
(:Person)-[:ACCESS_AUDIT {
  at: datetime
}]->(:AuditLog)
```

## Constraints

```cypher
// Unique IDs
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT fact_id_unique IF NOT EXISTS
FOR (f:Fact) REQUIRE f.id IS UNIQUE;

CREATE CONSTRAINT preference_id_unique IF NOT EXISTS
FOR (p:Preference) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT conversation_id_unique IF NOT EXISTS
FOR (c:Conversation) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT audit_log_id_unique IF NOT EXISTS
FOR (a:AuditLog) REQUIRE a.id IS UNIQUE;

CREATE CONSTRAINT topic_id_unique IF NOT EXISTS
FOR (t:Topic) REQUIRE t.id IS UNIQUE;
```

## Indexes

### Person Indexes

```cypher
// Person lookups by channel and handle
CREATE INDEX person_channel_lookup IF NOT EXISTS
FOR (p:Person) ON (p.channel, p.handle);

// Person lookups by name
CREATE INDEX person_name_lookup IF NOT EXISTS
FOR (p:Person) ON (p.name);

// Active persons
CREATE INDEX person_active_lookup IF NOT EXISTS
FOR (p:Person) ON (p.is_active, p.last_seen);

// Person sender hash for isolation
CREATE INDEX person_sender_hash_lookup IF NOT EXISTS
FOR (p:Person) ON (p.sender_hash);
```

### Fact Indexes

```cypher
// Fact lookups by person
CREATE INDEX fact_person_lookup IF NOT EXISTS
FOR (f:Fact) ON (f.person_id, f.created_at);

// Fact lookups by type
CREATE INDEX fact_type_lookup IF NOT EXISTS
FOR (f:Fact) ON (f.fact_type, f.privacy_level);

// Fact lookups by privacy level
CREATE INDEX fact_privacy_lookup IF NOT EXISTS
FOR (f:Fact) ON (f.privacy_level, f.person_id);

// Fact confidence filtering
CREATE INDEX fact_confidence_lookup IF NOT EXISTS
FOR (f:Fact) ON (f.confidence);

// Fact key lookups
CREATE INDEX fact_key_lookup IF NOT EXISTS
FOR (f:Fact) ON (f.fact_key, f.person_id);
```

### Preference Indexes

```cypher
// Preference lookups by person
CREATE INDEX preference_person_lookup IF NOT EXISTS
FOR (p:Preference) ON (p.person_id, p.category);

// Preference by key
CREATE INDEX preference_key_lookup IF NOT EXISTS
FOR (p:Preference) ON (p.pref_key, p.person_id);
```

### Conversation Indexes

```cypher
// Conversation lookups by person
CREATE INDEX conversation_person_lookup IF NOT EXISTS
FOR (c:Conversation) ON (c.person_id, c.timestamp);

// Conversation by time range
CREATE INDEX conversation_time_lookup IF NOT EXISTS
FOR (c:Conversation) ON (c.timestamp);

// Conversation by channel
CREATE INDEX conversation_channel_lookup IF NOT EXISTS
FOR (c:Conversation) ON (c.channel, c.timestamp);
```

### Topic Indexes

```cypher
// Topic lookups
CREATE INDEX topic_name_lookup IF NOT EXISTS
FOR (t:Topic) ON (t.name);

// Topic frequency
CREATE INDEX topic_frequency_lookup IF NOT EXISTS
FOR (t:Topic) ON (t.frequency);
```

### Audit Log Indexes

```cypher
// Audit log lookups
CREATE INDEX audit_person_lookup IF NOT EXISTS
FOR (a:AuditLog) ON (a.person_id, a.accessed_at);

// Audit by action type
CREATE INDEX audit_action_lookup IF NOT EXISTS
FOR (a:AuditLog) ON (a.action, a.accessed_at);

// Audit by accessor
CREATE INDEX audit_accessor_lookup IF NOT EXISTS
FOR (a:AuditLog) ON (a.accessed_by, a.accessed_at);

// Audit retention
CREATE INDEX audit_retention_lookup IF NOT EXISTS
FOR (a:AuditLog) ON (a.retain_until)
WHERE a.retain_until IS NOT NULL;
```

## Vector Index

```cypher
// Conversation semantic search
CREATE VECTOR INDEX conversation_embedding IF NOT EXISTS
FOR (c:Conversation) ON (c.embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};
```

## Full-Text Indexes

```cypher
// Search facts by content
CREATE FULLTEXT INDEX fact_content_search IF NOT EXISTS
FOR (f:Fact) ON EACH [f.fact_value];

// Search conversations by content
CREATE FULLTEXT INDEX conversation_content_search IF NOT EXISTS
FOR (c:Conversation) ON EACH [c.summary, c.content_snippet];
```

## Common Queries

### Get or Create Person

```cypher
MERGE (p:Person {id: $person_id})
ON CREATE SET
  p.name = $name,
  p.handle = $handle,
  p.channel = $channel,
  p.first_seen = datetime(),
  p.last_seen = datetime(),
  p.total_conversations = 0,
  p.is_active = true
ON MATCH SET
  p.last_seen = datetime(),
  p.name = COALESCE($name, p.name)
RETURN p
```

### Add Fact with Privacy

```cypher
MATCH (p:Person {id: $person_id})
CREATE (f:Fact {
  id: $fact_id,
  person_id: $person_id,
  fact_type: $fact_type,
  fact_key: $fact_key,
  fact_value: $fact_value,
  privacy_level: $privacy_level,
  confidence: $confidence,
  source: $source,
  created_at: datetime(),
  updated_at: datetime()
})
CREATE (p)-[:HAS_FACT {created_at: datetime()}]->(f)
RETURN f
```

### Get Facts by Privacy Level

```cypher
MATCH (f:Fact {person_id: $person_id})
WHERE f.privacy_level IN $privacy_levels
  AND f.confidence >= $min_confidence
  AND (f.expires_at IS NULL OR f.expires_at > datetime())
RETURN f
ORDER BY f.confidence DESC, f.created_at DESC
```

### Get Recurring Topics

```cypher
MATCH (p:Person {id: $person_id})-[d:DISCUSSED_TOPIC]->(t:Topic)
WITH t, sum(d.count) as frequency,
     min(d.at) as first_discussed,
     max(d.at) as last_discussed
WHERE frequency >= $min_frequency
RETURN t, frequency, first_discussed, last_discussed
ORDER BY frequency DESC
```

### Find Similar Conversations (Vector Search)

```cypher
CALL db.index.vector.queryNodes('conversation_embedding', $limit, $query_embedding)
YIELD node, score
WHERE node.person_id = $person_id AND score >= $min_similarity
RETURN node as conversation, score
ORDER BY score DESC
```

### Audit Trail Query

```cypher
MATCH (a:AuditLog {person_id: $person_id})
WHERE a.accessed_at >= $since
  AND ($action IS NULL OR a.action = $action)
RETURN a
ORDER BY a.accessed_at DESC
LIMIT $limit
```

### Privacy Check - Sensitive Access

```cypher
MATCH (a:AuditLog {person_id: $person_id})
WHERE a.privacy_level IN ['private', 'sensitive']
  AND a.accessed_at >= $since
RETURN 
  count(a) as total_accesses,
  count(CASE WHEN a.was_filtered THEN 1 END) as filtered_count,
  collect(DISTINCT a.accessed_by) as accessors
```

### Data Retention - Expired Audit Logs

```cypher
MATCH (a:AuditLog)
WHERE a.retain_until < datetime()
WITH a LIMIT $batch_size
DETACH DELETE a
RETURN count(a) as deleted
```

### Cross-Person Privacy Check

```cypher
// Check what private facts would be shared
MATCH (f:Fact {person_id: $source_person_id})
WHERE f.privacy_level = 'private'
  AND f.fact_value CONTAINS $content_snippet
RETURN f.fact_key, f.fact_value
```

### Conversation Context Building

```cypher
// Get recent conversations with topics
MATCH (p:Person {id: $person_id})-[:PARTICIPATED_IN]->(c:Conversation)
WHERE c.timestamp >= $since
OPTIONAL MATCH (c)-[:DISCUSSED_TOPIC]->(t:Topic)
WITH c, collect(t.name) as topics
RETURN c.id, c.summary, c.timestamp, topics
ORDER BY c.timestamp DESC
LIMIT $limit
```

### Complete Person Context

```cypher
// Get person with recent facts and conversations
MATCH (p:Person {id: $person_id})
OPTIONAL MATCH (p)-[:HAS_FACT]->(f:Fact)
  WHERE f.privacy_level IN $allowed_privacy_levels
  AND f.confidence >= 0.6
WITH p, f
  ORDER BY f.confidence DESC
  LIMIT 20
WITH p, collect(f) as facts
OPTIONAL MATCH (p)-[:PARTICIPATED_IN]->(c:Conversation)
  WHERE c.timestamp >= datetime() - duration('P7D')
WITH p, facts, c
  ORDER BY c.timestamp DESC
  LIMIT 10
WITH p, facts, collect(c) as conversations
OPTIONAL MATCH (p)-[:DISCUSSED_TOPIC]->(t:Topic)
WITH p, facts, conversations, t
  ORDER BY t.frequency DESC
  LIMIT 10
RETURN p, facts, conversations, collect(t) as topics
```

## Migration

Apply the schema migration:

```bash
python migrations/v4_identity_management.py
```

Or programmatically:

```python
from migrations.v4_identity_management import V4IdentityManagement
from migrations.migration_manager import MigrationManager

with MigrationManager(uri, user, password) as manager:
    V4IdentityManagement.register(manager)
    manager.migrate(target_version=4)
```
