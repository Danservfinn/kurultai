---
title: Neo4j-Native Conversation Context System — Complete Design
version: 1.1
date: 2026-03-20
author: Architecture Modernization
status: Phase 2 Active (Parallel Write) — updated to match implementation
replaces: file-based conversation JSONL + JSON index system
---

# Neo4j-Native Conversation Context System

## Executive Summary

This document specifies the complete graph schema, index strategy, query library, and
engagement intelligence model for Kublai's conversation context system. It replaces the
current file-based storage (JSONL per phone number, JSON indexes, monthly archives) with
a single Neo4j-native graph that makes conversations, tasks, topics, humans, and events
first-class interconnected citizens.

The core design principle: a single Cypher traversal should be able to answer any
cross-cutting question about the relationship between a human, their messages, the tasks
those messages spawned, and the topics they reveal — with no application-level joins.

---

## Part 1: Integration Topology

Before designing the new nodes, understand what already exists and where the new
nodes attach.

### Existing nodes (do not redefine)

| Node Label          | Primary Key        | Role in new system                              |
|---------------------|--------------------|-------------------------------------------------|
| `HumanProfile`      | `profile_id`       | The human — anchor for all conversation data    |
| `Task`              | `task_id`          | Tasks spawned from conversations                |
| `Agent`             | `name`             | Kublai and other agents                         |
| `ConversionContext` | `context_id`       | Subscription/monetization state                 |
| `FunnelEvent`       | `event_id`         | Conversion funnel events                        |
| `Research`          | `research_id`      | Research artifacts                              |
| `Event`             | `event_id`         | Calendar events                                 |
| `Proposal`          | `proposal_id`      | Democratic proposals                            |
| `Vote`              | `vote_id`          | Agent votes                                     |

### New nodes introduced by this design

**Implemented:** `Thread` (not `ConversationThread`), `Message`, `Topic`, `ActionItem`,
`Inference`, `Consent`/`ConsentCategory`, `Group`, `Identifier`, `TemporalMarker`

**Future Work:** `RelationshipSnapshot`, `EngagementDecision` (as separate nodes —
engagement decisions are currently stored as properties on Message nodes)

### Attachment points (implemented)

```
(Message)-[:SENT]->(Human)           # Message authored by human
(Message)-[:IN_THREAD]->(Thread)     # Message belongs to thread
(Message)-[:IN_GROUP]->(Group)       # Message in group chat
(Message)-[:HAS_TOPIC]->(Topic)      # Extracted topic (async_extractor)
(Human)-[:DISCUSSED]->(Topic)        # Aggregated topic relationship
(Human)-[:IDENTIFIED_BY]->(Identifier) # Phone, email, name variants
(Human)-[:HAS_CONSENT]->(ConsentCategory) # Consent grants
(Human)-[:HAS_INFERENCE]->(Inference) # LLM-derived inferences
(Human)-[:KNOWN_THROUGH|RELATED_TO]->(Human) # Social connections
```

---

## Part 2: Node Specifications

### 2.1 ConversationThread

A ConversationThread groups a temporally and semantically cohesive set of messages.
It is the unit of session detection.

```cypher
(:ConversationThread {
  thread_id:        String,    // UUID, e.g. "ct-a1b2c3d4"  — PRIMARY KEY
  human_id:         String,    // E.164, denormalized for fast filtering
  channel:          String,    // "signal" | "sms" | "email" (extensible)

  // Temporal bounds
  started_at:       DateTime,
  last_message_at:  DateTime,
  ended_at:         DateTime,  // null until thread closed

  // Session detection state
  is_open:          Boolean,   // true while 30-min window is live
  session_gap_mins: Integer,   // gap that opened this thread (0 for first ever)

  // Semantic classification (LLM-assigned at thread close)
  dominant_topics:  [String],  // top 3 topic slugs for quick filtering
  intent:           String,    // "task_request" | "chitchat" | "feedback" |
                               //   "status_check" | "escalation" | "unknown"
  sentiment_arc:    String,    // "positive" | "neutral" | "negative" | "mixed"

  // Aggregate metrics
  message_count:    Integer,
  inbound_count:    Integer,
  outbound_count:   Integer,
  avg_response_secs: Float,    // Kublai response latency within thread

  // Summary (LLM-generated at thread close, embedded for vector search)
  summary:          String,
  summary_embedding: [Float],  // 1536-dim OpenAI / 768-dim alternative

  // Lifecycle
  created_at:       DateTime,
  updated_at:       DateTime
})
```

Session detection rules (enforced at write time by the conversation ingester):
- Gap >= 2 hours (`THREAD_GAP_HOURS = 2.0`) since last message in the open thread:
  close current (set status to 'DORMANT'), open new.
- Topic shift detection via cosine similarity (`THREAD_SIMILARITY_THRESHOLD = 0.35`)
  is designed but not yet active in the ingester.
- Threads are scope-aware: group messages (`scope = 'group:<id>'`) get separate
  threads from DM messages (`scope = 'dm'`).

**Implementation note:** The actual node label is `Thread` (not `ConversationThread`)
with camelCase properties: `id`, `humanId`, `scope`, `status`, `startedAt`, `summary`,
`summaryEmbedding`, `messageCount`. Status values: 'ACTIVE', 'DORMANT', 'ARCHIVED'.

### 2.2 Message

Individual Signal messages. Stored in Neo4j for graph traversal. Content is stored
as-is up to 4000 characters (double the old 2000-char cap). Longer messages are
truncated with a `truncated: true` flag.

Privacy note: content is PII-class HIGH. Stored here only because this is the
local Neo4j instance, not a shared cluster. Review `conversation-privacy-policy.md`
consent rules before exposing via any API.

```cypher
(:Message {
  message_id:     String,    // UUID, e.g. "msg-a1b2c3d4"  — PRIMARY KEY
  thread_id:      String,    // denormalized FK to ConversationThread
  human_id:       String,    // denormalized FK to HumanProfile

  // Content
  direction:      String,    // "inbound" | "outbound"
  content:        String,    // raw text, max 4000 chars
  truncated:      Boolean,   // true if original exceeded 4000 chars
  channel:        String,    // "signal"

  // Embedding for semantic search
  embedding:      [Float],   // 1536-dim; null until embedding job runs

  // Extracted signals (computed synchronously at write time)
  is_question:         Boolean,
  contains_action_item: Boolean,
  urgency_signals:     [String],   // ["ASAP", "urgent", "deadline", ...]
  sentiment_score:     Float,      // -1.0 to 1.0

  // Auto-extracted context (replaces old context_type field)
  context_type:   String,    // "task_request" | "status_update" | "feedback" |
                             //   "chitchat" | "question" | "command"

  // Timestamps
  sent_at:        DateTime,
  received_at:    DateTime,  // when Kublai processed it (may differ from sent)
  created_at:     DateTime
})
```

### 2.3 Topic

Topics are shared across all humans. They form the cross-human knowledge layer — the
same `(:Topic {slug: "neo4j-schema"})` node connects to Danny's message AND any
research artifact about that topic.

This is the replacement for the file-based keyword list. Topics are normalized and
deduplicated at extraction time.

```cypher
(:Topic {
  topic_id:    String,    // UUID  — PRIMARY KEY
  slug:        String,    // UNIQUE, URL-safe lowercase, e.g. "neo4j-schema"
  display:     String,    // human-readable, e.g. "Neo4j Schema Design"
  domain:      String,    // "technical" | "business" | "personal" | "product"
  embedding:   [Float],   // topic centroid embedding for similarity clustering

  // Aggregate usage stats (updated incrementally)
  mention_count:      Integer,   // total times mentioned across all humans
  human_count:        Integer,   // distinct humans who have mentioned this
  first_seen_at:      DateTime,
  last_mentioned_at:  DateTime,

  // Decay / lifecycle
  freshness_score:    Float,     // 0.0-1.0, decays weekly (mirrors KnowledgeArtifact)
  created_at:         DateTime,
  updated_at:         DateTime
})
```

Constraint: `topic_id` unique. Additional unique constraint on `slug`.

### 2.4 ActionItem

An action item is a commitment detected in a conversation. It has its own lifecycle
separate from a Task — it starts as a raw commitment, then either becomes a formal Task
or expires unfulfilled.

```cypher
(:ActionItem {
  action_id:    String,    // UUID  — PRIMARY KEY
  human_id:     String,    // denormalized FK

  // Commitment content
  description:  String,    // what was promised / requested
  owner:        String,    // "kublai" | "human" | "shared"
  due_date:     DateTime,  // if mentioned; null otherwise
  due_explicit: Boolean,   // true if due_date came from explicit statement

  // Lifecycle state machine
  // raw -> confirmed -> in_progress -> done | abandoned | became_task
  status:       String,
  task_id:      String,    // set when status = "became_task"

  // Extraction provenance
  source_message_id: String,
  extracted_at:      DateTime,
  extraction_confidence: Float,   // 0.0-1.0

  // Timestamps
  created_at:   DateTime,
  updated_at:   DateTime,
  resolved_at:  DateTime   // null until terminal state
})
```

### 2.5 RelationshipSnapshot

A periodic (weekly or manually triggered) LLM-generated summary of the human-Kublai
relationship state. This is the long-term relationship memory: trend tracking,
sentiment trajectory, health scoring. Snapshots are never deleted — they form a
timeline of the relationship.

```cypher
(:RelationshipSnapshot {
  snapshot_id:   String,    // UUID  — PRIMARY KEY
  human_id:      String,    // denormalized FK

  // Coverage period
  period_start:  DateTime,
  period_end:    DateTime,
  period_label:  String,    // "2026-W11" for ISO week

  // Relationship health (LLM-scored 0-10)
  health_score:          Float,   // overall relationship health
  sentiment_trend:       String,  // "improving" | "stable" | "declining"
  engagement_trend:      String,  // "increasing" | "stable" | "decreasing"
  response_rate:         Float,   // fraction of Kublai messages that got replies
  avg_thread_depth:      Float,   // avg messages per thread in this period

  // Topic summary for the period
  top_topics:            [String],  // top 5 topic slugs
  new_topics:            [String],  // topics discussed for first time this period

  // LLM narrative
  narrative:             String,    // 300-500 word relationship summary
  key_observations:      [String],  // 3-5 bullet points
  recommended_actions:   [String],  // 1-3 suggested engagement actions

  // Embedding for semantic retrieval of past snapshots
  embedding:             [Float],

  // Generation metadata
  generated_by:          String,   // agent that ran the LLM
  model:                 String,   // model used
  token_count:           Integer,

  created_at:            DateTime
})
```

### 2.6 EngagementDecision

Every time Kublai decides whether to respond to an incoming message, the decision is
logged as a node. This creates a training dataset for improving the engagement model
without manual labeling.

```cypher
(:EngagementDecision {
  decision_id:     String,    // UUID  — PRIMARY KEY

  // Input context
  message_id:      String,    // the message being decided on
  human_id:        String,
  thread_id:       String,

  // Decision output
  decision:        String,    // "respond" | "silent" | "delay"
  delay_until:     DateTime,  // set when decision = "delay"
  confidence:      Float,     // 0.0-1.0, how certain the model was

  // Scoring breakdown (the signals that drove the decision)
  engagement_score:       Float,   // composite 0-100
  score_recency:          Float,   // contribution from recency signal
  score_urgency:          Float,   // contribution from urgency detection
  score_question:         Float,   // contribution from is_question
  score_relationship:     Float,   // contribution from relationship health
  score_active_tasks:     Float,   // contribution from open tasks with human
  score_sentiment:        Float,   // contribution from sentiment trajectory
  threshold_used:         Float,   // the respond/silent threshold at decision time

  // Outcome tracking (filled in retrospectively)
  outcome:                String,  // "positive" | "neutral" | "negative" | null
  outcome_recorded_at:    DateTime,

  // Whether a human override occurred (Kublai was told to respond/not respond manually)
  human_override:         Boolean,
  override_reason:        String,

  created_at:             DateTime
})
```

---

## Part 3: Relationship Types

### 3.1 HumanProfile relationships (new)

```cypher
// Primary ownership — a human owns their threads
(HumanProfile)-[:HAS_THREAD {
  created_at: DateTime
}]->(ConversationThread)

// Relationship evolution timeline
(HumanProfile)-[:HAS_SNAPSHOT {
  created_at: DateTime,
  period_label: String
}]->(RelationshipSnapshot)

// Commitment tracking
(HumanProfile)-[:HAS_ACTION_ITEM {
  created_at: DateTime
}]->(ActionItem)
```

### 3.2 ConversationThread relationships

```cypher
// Thread → Profile (the owning human)
(ConversationThread)-[:BELONGS_TO]->(HumanProfile)

// Thread → Thread (session continuity chain)
(ConversationThread)-[:PRECEDED_BY {
  gap_minutes: Integer,           // time gap between threads
  topic_continuity_score: Float,  // 0.0-1.0 semantic similarity
  reason_closed: String           // "time_gap" | "topic_shift" | "explicit"
}]->(ConversationThread)

// Thread → Task (tasks that originated from this thread)
(ConversationThread)-[:SPAWNED_TASK {
  at: DateTime,
  trigger_message_id: String
}]->(Task)

// Thread → Topic (topics discussed in this thread)
(ConversationThread)-[:DISCUSSES {
  weight: Float,       // frequency score within thread (incremented per mention)
  first_at: DateTime,
  last_at: DateTime
}]->(Topic)
```

### 3.3 Message relationships

```cypher
// Message → Thread (containment)
(Message)-[:IN_THREAD {
  position: Integer,  // ordinal position within thread (1-based)
  at: DateTime
}]->(ConversationThread)

// Message → Message (reply chain within thread)
(Message)-[:REPLIES_TO]->(Message)

// Message → Topic (topics mentioned in this specific message)
(Message)-[:MENTIONS_TOPIC {
  confidence: Float,
  extraction_method: String  // "keyword" | "llm" | "embedding"
}]->(Topic)

// Message → Task (tasks this message directly triggered)
(Message)-[:TRIGGERED_TASK {
  at: DateTime,
  task_type: String
}]->(Task)

// Message → ActionItem (action items extracted from this message)
(Message)-[:EXTRACTED_ACTION {
  at: DateTime,
  confidence: Float
}]->(ActionItem)

// Message → EngagementDecision (decision made about this message)
(Message)-[:HAS_DECISION]->(EngagementDecision)
```

### 3.4 Topic relationships

```cypher
// Topic → Topic (semantic proximity, maintained by clustering job)
(Topic)-[:RELATED_TO {
  similarity: Float,    // cosine similarity 0.0-1.0
  computed_at: DateTime
}]->(Topic)

// Topic → Research (topic appears in a research artifact)
(Topic)-[:REFERENCED_IN {
  at: DateTime
}]->(Research)

// Topic → Task (topic is the subject of a task)
(Topic)-[:SUBJECT_OF {
  relevance: Float
}]->(Task)
```

### 3.5 ActionItem relationships

```cypher
// ActionItem → Task (when the action item was formalized as a task)
(ActionItem)-[:BECAME_TASK {
  at: DateTime
}]->(Task)

// ActionItem → Message (original source)
(ActionItem)-[:SOURCED_FROM]->(Message)
```

### 3.6 RelationshipSnapshot relationships

```cypher
// Snapshot → Snapshot (timeline chain)
(RelationshipSnapshot)-[:FOLLOWS {
  period_gap_days: Integer
}]->(RelationshipSnapshot)

// Snapshot → Topic (topics dominant in this period)
(RelationshipSnapshot)-[:PERIOD_TOPIC {
  rank: Integer,   // 1 = top topic
  count: Integer
}]->(Topic)
```

### 3.7 EngagementDecision relationships

```cypher
// Decision → Message (the message being decided about)
(EngagementDecision)-[:ABOUT_MESSAGE]->(Message)

// Decision → Thread (thread context used)
(EngagementDecision)-[:IN_CONTEXT_OF]->(ConversationThread)
```

### 3.8 Existing relationship extensions

Add properties to existing relationships where the new system enriches them:

```cypher
// Task nodes get a conversation_thread_id property (denormalized) so queries can
// quickly find "what thread was the human in when they requested this task?"
// This avoids a traversal back through the Message node.
// Set via: MATCH (t:Task {task_id: $tid}) SET t.conversation_thread_id = $thread_id

// ASSIGNED_TO gets weight tracking (already in NEO4J_PATTERNS.md — extend only)
// No changes needed to existing relationships.
```

---

## Part 4: Index Strategy

### 4.1 Uniqueness Constraints

```cypher
CREATE CONSTRAINT conv_thread_id_unique IF NOT EXISTS
FOR (ct:ConversationThread) REQUIRE ct.thread_id IS UNIQUE;

CREATE CONSTRAINT message_id_unique IF NOT EXISTS
FOR (m:Message) REQUIRE m.message_id IS UNIQUE;

CREATE CONSTRAINT topic_id_unique IF NOT EXISTS
FOR (t:Topic) REQUIRE t.topic_id IS UNIQUE;

CREATE CONSTRAINT topic_slug_unique IF NOT EXISTS
FOR (t:Topic) REQUIRE t.slug IS UNIQUE;

CREATE CONSTRAINT action_item_id_unique IF NOT EXISTS
FOR (ai:ActionItem) REQUIRE ai.action_id IS UNIQUE;

CREATE CONSTRAINT rel_snapshot_id_unique IF NOT EXISTS
FOR (rs:RelationshipSnapshot) REQUIRE rs.snapshot_id IS UNIQUE;

CREATE CONSTRAINT engagement_decision_id_unique IF NOT EXISTS
FOR (ed:EngagementDecision) REQUIRE ed.decision_id IS UNIQUE;
```

### 4.2 Composite Range Indexes (for the hottest query paths)

```cypher
// Most common: "find open threads for this human"
CREATE INDEX conv_thread_human_open IF NOT EXISTS
FOR (ct:ConversationThread) ON (ct.human_id, ct.is_open);

// Recency fetch: "find most recent threads for this human"
CREATE INDEX conv_thread_human_time IF NOT EXISTS
FOR (ct:ConversationThread) ON (ct.human_id, ct.last_message_at);

// Message timeline within a thread
CREATE INDEX message_thread_time IF NOT EXISTS
FOR (m:Message) ON (m.thread_id, m.sent_at);

// Cross-human engagement decisions — outcome tracking
CREATE INDEX engagement_decision_human_time IF NOT EXISTS
FOR (ed:EngagementDecision) ON (ed.human_id, ed.created_at);

// ActionItem lifecycle queries
CREATE INDEX action_item_human_status IF NOT EXISTS
FOR (ai:ActionItem) ON (ai.human_id, ai.status);

// Snapshot timeline
CREATE INDEX rel_snapshot_human_period IF NOT EXISTS
FOR (rs:RelationshipSnapshot) ON (rs.human_id, rs.period_end);

// Topic freshness for decay job
CREATE INDEX topic_freshness IF NOT EXISTS
FOR (t:Topic) ON (t.freshness_score);

// Topic cross-human analytics
CREATE INDEX topic_mention_count IF NOT EXISTS
FOR (t:Topic) ON (t.mention_count);
```

### 4.3 Vector Indexes (Neo4j 5.x+)

These enable semantic search using embedding similarity.

```cypher
// Message semantic search — find past messages similar to an incoming message
CREATE VECTOR INDEX message_embedding_idx IF NOT EXISTS
FOR (m:Message) ON (m.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

// Thread summary semantic search — find past threads similar to current topic
CREATE VECTOR INDEX thread_summary_embedding_idx IF NOT EXISTS
FOR (ct:ConversationThread) ON (ct.summary_embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

// RelationshipSnapshot semantic search — retrieve relevant past relationship summaries
CREATE VECTOR INDEX rel_snapshot_embedding_idx IF NOT EXISTS
FOR (rs:RelationshipSnapshot) ON (rs.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

// Topic centroid — for clustering and cross-topic similarity
CREATE VECTOR INDEX topic_embedding_idx IF NOT EXISTS
FOR (t:Topic) ON (t.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};
```

Note on embedding dimensions: the schema uses 1536 (OpenAI text-embedding-3-small).
If switching to a local model (384-dim or 768-dim), update the `vector.dimensions`
value and re-index. The system uses OpenRouter which may route to various providers;
standardize on one dimension count and do not mix dimension sizes within an index.

### 4.4 Full-Text Indexes (keyword search)

```cypher
// Keyword search across message content
CREATE FULLTEXT INDEX message_content_search IF NOT EXISTS
FOR (m:Message) ON EACH [m.content];

// Thread summary keyword search
CREATE FULLTEXT INDEX thread_summary_search IF NOT EXISTS
FOR (ct:ConversationThread) ON EACH [ct.summary, ct.dominant_topics];

// Topic name search
CREATE FULLTEXT INDEX topic_search IF NOT EXISTS
FOR (t:Topic) ON EACH [t.slug, t.display];

// ActionItem description search
CREATE FULLTEXT INDEX action_item_search IF NOT EXISTS
FOR (ai:ActionItem) ON EACH [ai.description];

// RelationshipSnapshot narrative search
CREATE FULLTEXT INDEX snapshot_narrative_search IF NOT EXISTS
FOR (rs:RelationshipSnapshot) ON EACH [rs.narrative, rs.key_observations];
```

---

## Part 5: Key Cypher Query Patterns

### Q1 — Context Retrieval

"Given this human and an incoming message embedding, find the most relevant past
conversations."

This is the primary query Kublai runs before composing any response. It combines
vector search (semantic relevance) with graph traversal (relationship context and
active tasks).

```cypher
// Parameters:
//   $human_id     — E.164 phone number
//   $embedding    — Float[], embedding of the incoming message
//   $lookback_days — Integer, how far back to consider (default 90)
//   $top_n        — Integer, number of messages to return (default 10)

// Phase 1: Vector search — semantically similar past messages
CALL db.index.vector.queryNodes('message_embedding_idx', $top_n * 3, $embedding)
YIELD node AS m, score AS vector_score
WHERE m.human_id = $human_id
  AND m.sent_at > datetime() - duration({days: $lookback_days})

// Phase 2: Enrich with thread context
WITH m, vector_score
MATCH (m)-[:IN_THREAD]->(ct:ConversationThread)
OPTIONAL MATCH (ct)-[:SPAWNED_TASK]->(t:Task)
OPTIONAL MATCH (m)-[:MENTIONS_TOPIC]->(tp:Topic)

// Phase 3: Boost score based on graph signals
WITH m, ct, vector_score,
     collect(DISTINCT t.task_id) AS related_tasks,
     collect(DISTINCT tp.slug) AS topics,
     CASE WHEN ct.last_message_at > datetime() - duration({hours: 24}) THEN 1.3
          WHEN ct.last_message_at > datetime() - duration({days: 7})   THEN 1.1
          ELSE 1.0
     END AS recency_boost,
     CASE WHEN t.status IN ['PENDING', 'EXECUTING'] THEN 1.2 ELSE 1.0 END AS task_boost

WITH m, ct, related_tasks, topics,
     vector_score * recency_boost * task_boost AS composite_score

// Phase 4: Return ranked context window
RETURN
  m.message_id,
  m.content,
  m.direction,
  m.sent_at,
  m.context_type,
  ct.thread_id,
  ct.dominant_topics,
  ct.intent,
  topics,
  related_tasks,
  composite_score
ORDER BY composite_score DESC
LIMIT $top_n
```

### Q2 — Thread Detection

"Does this incoming message continue the last open thread, or start a new one?"

This query is called synchronously on every inbound message before writing to Neo4j.
It returns either the open thread to append to, or null (signaling: create new thread).

```cypher
// Parameters:
//   $human_id         — E.164 phone number
//   $now              — DateTime, current time
//   $gap_threshold_mins — Integer (default 30)
//   $new_msg_embedding  — Float[], for topic-shift detection

MATCH (hp:HumanProfile {human_id: $human_id})-[:HAS_THREAD]->(ct:ConversationThread)
WHERE ct.is_open = true
WITH ct ORDER BY ct.last_message_at DESC LIMIT 1

// Compute gap
WITH ct,
     duration.between(ct.last_message_at, $now).minutes AS gap_mins

// Check time gap
WITH ct, gap_mins,
     CASE WHEN gap_mins >= $gap_threshold_mins THEN false ELSE true END AS within_time_window

// If within time window, also check semantic continuity
// (topic_shift_detected comes from application layer cosine check — see note below)
// Here we return the thread plus the gap so the application can decide
RETURN
  ct.thread_id,
  ct.last_message_at,
  ct.dominant_topics,
  ct.summary_embedding,   // application computes cosine(new_msg_embedding, this) to detect shift
  gap_mins,
  within_time_window,
  ct.message_count
```

Note on topic-shift detection: Neo4j 5.x does not yet support inline cosine computation
in regular Cypher (only through `db.index.vector.queryNodes`). The application layer
receives `summary_embedding` and computes `cosine(new_msg_embedding, summary_embedding)`.
If the score < 0.35, it signals a topic shift and forces a new thread regardless of
the time window. This split keeps the hot path fast: a single index lookup + short
computation, not a full vector search.

### Q3 — Engagement Scoring

"Should Kublai respond to this message?"

This query computes a composite engagement score from graph signals. The application
maps the score to a decision using configurable thresholds.

```cypher
// Parameters:
//   $human_id    — E.164 phone number
//   $message_id  — the incoming message
//   $thread_id   — the thread it belongs to

MATCH (m:Message {message_id: $message_id})
MATCH (ct:ConversationThread {thread_id: $thread_id})
MATCH (hp:HumanProfile {human_id: $human_id})

// Signal 1: Recency — time since last interaction
OPTIONAL MATCH (hp)-[:HAS_THREAD]->(prev_ct:ConversationThread)
WHERE prev_ct.thread_id <> $thread_id
WITH m, ct, hp,
     min(duration.between(prev_ct.last_message_at, datetime()).hours) AS hours_since_last_thread

// Signal 2: Active tasks with this human
OPTIONAL MATCH (prev_ct2:ConversationThread)-[:SPAWNED_TASK]->(active_t:Task)
WHERE prev_ct2.human_id = $human_id
  AND active_t.status IN ['PENDING', 'EXECUTING']
WITH m, ct, hp, hours_since_last_thread,
     count(DISTINCT active_t) AS active_task_count

// Signal 3: Recent relationship health
OPTIONAL MATCH (hp)-[:HAS_SNAPSHOT]->(rs:RelationshipSnapshot)
WITH m, ct, hp, hours_since_last_thread, active_task_count, rs
ORDER BY rs.period_end DESC LIMIT 1
WITH m, ct, hp, hours_since_last_thread, active_task_count,
     coalesce(rs.health_score, 5.0) AS relationship_health,
     coalesce(rs.sentiment_trend, 'stable') AS sentiment_trend

// Score computation
WITH m, ct,
     // Recency: 0-20 points. More points if they haven't heard from Kublai recently.
     CASE WHEN hours_since_last_thread IS NULL THEN 20  // first ever message
          WHEN hours_since_last_thread > 48    THEN 20
          WHEN hours_since_last_thread > 24    THEN 15
          WHEN hours_since_last_thread > 8     THEN 10
          ELSE 5
     END AS score_recency,

     // Urgency: 0-25 points from urgency signals in message
     CASE WHEN size(m.urgency_signals) > 2 THEN 25
          WHEN size(m.urgency_signals) > 0 THEN 15
          ELSE 0
     END AS score_urgency,

     // Question detection: 0-20 points
     CASE WHEN m.is_question = true THEN 20 ELSE 0 END AS score_question,

     // Active tasks: 0-15 points — ongoing work raises response priority
     CASE WHEN active_task_count >= 3 THEN 15
          WHEN active_task_count >= 1 THEN 10
          ELSE 0
     END AS score_active_tasks,

     // Relationship health: 0-10 points (scaled from 0-10 score)
     relationship_health AS score_relationship,

     // Sentiment trend modifier: bonus/penalty
     CASE sentiment_trend
          WHEN 'declining' THEN 5   // proactive outreach when trending down
          WHEN 'improving' THEN 0
          ELSE 0
     END AS score_sentiment_modifier

WITH m, ct,
     score_recency + score_urgency + score_question +
     score_active_tasks + score_relationship + score_sentiment_modifier AS engagement_score,
     score_recency, score_urgency, score_question,
     score_active_tasks, score_relationship, score_sentiment_modifier

RETURN
  m.message_id,
  engagement_score,
  score_recency,
  score_urgency,
  score_question,
  score_active_tasks,
  score_relationship,
  score_sentiment_modifier,
  // Decision thresholds:
  //   >= 60: respond immediately
  //   40-59: respond (but can delay to better time window)
  //   20-39: optional — check communication_style.preferred_time before responding
  //   < 20:  silent (e.g., pure acknowledgement "ok" or "thanks" with no question)
  CASE WHEN engagement_score >= 60 THEN 'respond'
       WHEN engagement_score >= 40 THEN 'respond'
       WHEN engagement_score >= 20 THEN 'delay'
       ELSE 'silent'
  END AS decision
```

### Q4 — Topic Pattern Detection

"What topics has this human discussed most in the last 30 days?"

```cypher
// Parameters:
//   $human_id     — E.164 phone number
//   $days         — Integer (default 30)
//   $min_mentions — Integer (default 2, filters noise)

MATCH (hp:HumanProfile {human_id: $human_id})-[:HAS_THREAD]->(ct:ConversationThread)
WHERE ct.last_message_at > datetime() - duration({days: $days})

MATCH (ct)-[d:DISCUSSES]->(tp:Topic)

WITH tp,
     sum(d.weight) AS total_weight,
     count(DISTINCT ct) AS thread_count,
     max(d.last_at) AS last_mentioned_at

WHERE total_weight >= $min_mentions

// Enrich with cross-human context (how many OTHER humans discuss this too)
OPTIONAL MATCH (other_ct:ConversationThread)-[:DISCUSSES]->(tp)
WHERE other_ct.human_id <> $human_id

WITH tp, total_weight, thread_count, last_mentioned_at,
     count(DISTINCT other_ct.human_id) AS other_human_count

RETURN
  tp.slug,
  tp.display,
  tp.domain,
  total_weight     AS mention_weight,
  thread_count     AS thread_appearances,
  last_mentioned_at,
  other_human_count AS cross_human_interest,
  // composite rank score for ordering
  total_weight * log(1 + thread_count) AS topic_rank_score
ORDER BY topic_rank_score DESC
LIMIT 10
```

### Q5 — Relationship Health Trend

"Is this human's sentiment trending up or down?"

```cypher
// Parameters:
//   $human_id       — E.164 phone number
//   $snapshot_count — Integer, how many snapshots to look back (default 4)

MATCH (hp:HumanProfile {human_id: $human_id})-[:HAS_SNAPSHOT]->(rs:RelationshipSnapshot)
WITH rs ORDER BY rs.period_end DESC LIMIT $snapshot_count

WITH collect({
  period: rs.period_label,
  health: rs.health_score,
  sentiment: rs.sentiment_trend,
  engagement: rs.engagement_trend,
  response_rate: rs.response_rate,
  top_topics: rs.top_topics
}) AS snapshots

// Compute linear trend from health scores
WITH snapshots,
     [s IN snapshots | s.health] AS health_series

RETURN
  snapshots,
  health_series,
  // Simple direction: compare most recent to oldest in window
  CASE WHEN health_series[0] > health_series[-1] + 1.0 THEN 'improving'
       WHEN health_series[0] < health_series[-1] - 1.0 THEN 'declining'
       ELSE 'stable'
  END AS overall_trend,
  health_series[0]  AS current_health,
  health_series[-1] AS baseline_health
```

For richer trend analysis (slope, R^2), this data should be post-processed in
the application layer using numpy. The Cypher query provides the raw time series.

### Q6 — Cross-Human Insights

"Which humans have discussed topic X? What was the context each time?"

```cypher
// Parameters:
//   $topic_slug   — String, e.g. "neo4j-schema"
//   $min_weight   — Float (default 1.0, filters casual mentions)

MATCH (tp:Topic {slug: $topic_slug})
MATCH (ct:ConversationThread)-[d:DISCUSSES]->(tp)
WHERE d.weight >= $min_weight

MATCH (ct)-[:BELONGS_TO]->(hp:HumanProfile)
WHERE hp.status = 'active'

WITH hp, ct, d, tp
ORDER BY d.last_at DESC

WITH hp,
     collect({
       thread_id: ct.thread_id,
       intent: ct.intent,
       summary: ct.summary,
       weight: d.weight,
       last_at: d.last_at,
       sentiment_arc: ct.sentiment_arc
     })[..3] AS top_threads,  // at most 3 threads per human
     sum(d.weight) AS total_weight,
     max(d.last_at) AS last_seen

RETURN
  hp.display_name,
  hp.human_id,
  hp.timezone,
  total_weight,
  last_seen,
  top_threads
ORDER BY total_weight DESC
LIMIT 20
```

### Q7 — Task Origin Traversal

"What was the human talking about when they requested task X?"

This is the "single coherent system" query — traversing from Task back through Message
into ConversationThread to recover the full conversational context.

```cypher
// Parameters:
//   $task_id — String

MATCH (t:Task {task_id: $task_id})

// Path 1: Task ← Message ← Thread
OPTIONAL MATCH (m:Message)-[:TRIGGERED_TASK]->(t)
OPTIONAL MATCH (m)-[:IN_THREAD]->(ct:ConversationThread)
OPTIONAL MATCH (m)-[:MENTIONS_TOPIC]->(tp:Topic)

// Path 2: Task ← ActionItem ← Message ← Thread (for formalized commitments)
OPTIONAL MATCH (ai:ActionItem)-[:BECAME_TASK]->(t)
OPTIONAL MATCH (ai)-[:SOURCED_FROM]->(ai_msg:Message)
OPTIONAL MATCH (ai_msg)-[:IN_THREAD]->(ai_ct:ConversationThread)

// Resolve to whichever path exists
WITH t, m, ct, ai, ai_msg, ai_ct,
     coalesce(ct, ai_ct) AS origin_thread,
     coalesce(m, ai_msg) AS origin_message,
     collect(DISTINCT tp.slug) AS origin_topics

// Get the 5 messages immediately before the trigger message for context
OPTIONAL MATCH (context_msg:Message)-[:IN_THREAD]->(origin_thread)
WHERE context_msg.sent_at <= origin_message.sent_at
WITH t, origin_thread, origin_message, origin_topics, context_msg
ORDER BY context_msg.sent_at DESC
LIMIT 5

WITH t, origin_thread, origin_message, origin_topics,
     collect({
       content: context_msg.content,
       direction: context_msg.direction,
       sent_at: context_msg.sent_at
     }) AS conversation_window

RETURN
  t.task_id,
  t.status,
  t.description,
  origin_message.content        AS trigger_message,
  origin_message.sent_at        AS triggered_at,
  origin_thread.thread_id,
  origin_thread.intent          AS thread_intent,
  origin_thread.dominant_topics AS thread_topics,
  origin_topics                 AS trigger_message_topics,
  conversation_window
```

---

## Part 6: Engagement Intelligence Decision Model

### 6.1 Architecture

The engagement decision pipeline runs synchronously on every inbound message before
Kublai formulates a response. It produces a structured `EngagementDecision` node that
is logged regardless of outcome (respond/silent/delay).

```
Inbound Signal Message
        │
        ▼
[Thread Detection — Q2]
        │
        ├── Open thread exists → append Message to thread
        └── No open thread / topic shift → create new ConversationThread
        │
        ▼
[Engagement Scoring — Q3]
Returns engagement_score (0-100) + breakdown
        │
        ┌────────────────────────────────────────────┐
        │  Score    │  Decision  │  Action            │
        │  >= 60    │  respond   │  immediate         │
        │  40-59    │  respond   │  check time window │
        │  20-39    │  delay     │  queue for later   │
        │  < 20     │  silent    │  no response       │
        └────────────────────────────────────────────┘
        │
        ▼
[Write EngagementDecision node]
Captures all score components for retrospective analysis
        │
        ▼
[Context Retrieval — Q1] (only if decision = respond or delay)
Fetches top-N semantically relevant past messages
        │
        ▼
[Compose response with enriched context]
```

### 6.2 Signal Definitions

| Signal | Property Source | Score Range | Rationale |
|--------|-----------------|-------------|-----------|
| `score_recency` | `hours_since_last_thread` | 0-20 | Humans who haven't heard from Kublai in a while get higher priority |
| `score_urgency` | `m.urgency_signals` | 0-25 | Explicit urgency keywords dominate the score |
| `score_question` | `m.is_question` | 0-20 | Direct questions almost always warrant a response |
| `score_active_tasks` | `Task.status` traversal | 0-15 | Open work items make the human more engagement-critical |
| `score_relationship` | `RelationshipSnapshot.health_score` | 0-10 | Healthy relationships have demonstrated value; declining ones need proactive care |
| `score_sentiment_modifier` | `RelationshipSnapshot.sentiment_trend` | 0-5 | Bonus for declining sentiment (proactive recovery) |

Maximum possible score: 95. Thresholds are intentionally not at 100 to allow
headroom for future signals without recalibrating all thresholds.

### 6.3 Threshold Configuration

Thresholds are not hardcoded. They are stored as properties on the Kublai `Agent` node
so they can be adjusted without code deployment:

```cypher
MATCH (a:Agent {name: 'kublai'})
SET a.engagement_threshold_respond  = 60,
    a.engagement_threshold_delay    = 40,
    a.engagement_threshold_silent   = 20,
    a.engagement_thresholds_updated = datetime()
```

The engagement scorer reads these at startup and caches for 5 minutes.

### 6.4 Communication Style Override

Before finalizing the decision, the scorer checks `HumanProfile.communication_style`
for explicit overrides:

```cypher
MATCH (hp:HumanProfile {human_id: $human_id})
RETURN
  hp.communication_style.response_style,   // "immediate" | "batched" | "async"
  hp.communication_style.preferred_time,   // "morning" | "afternoon" | "evening" | "anytime"
  hp.preferences.notifications             // {signal: true, ...}
```

If `response_style = "batched"`, delay decisions with score 40-59 to the human's
`preferred_time` window rather than sending immediately.

### 6.5 Learning Loop

`EngagementDecision` nodes accumulate over time. Weekly, the reflection pipeline
runs a retrospective analysis:

```cypher
// Find cases where Kublai was silent but the human sent a follow-up (suggesting
// they expected a response)
MATCH (ed:EngagementDecision {decision: 'silent'})
WHERE ed.created_at > datetime() - duration({days: 7})

// Check if the human sent another message within 2 hours
MATCH (ed)-[:ABOUT_MESSAGE]->(m:Message)
MATCH (follow_up:Message)
WHERE follow_up.human_id = m.human_id
  AND follow_up.direction = 'inbound'
  AND follow_up.sent_at > m.sent_at
  AND follow_up.sent_at < m.sent_at + duration({hours: 2})

WITH ed, count(follow_up) AS follow_up_count
WHERE follow_up_count > 0

// These are likely false negatives — score was below threshold but human expected response
RETURN ed.decision_id,
       ed.engagement_score,
       ed.score_recency,
       ed.score_urgency,
       ed.score_question,
       follow_up_count AS missed_expectation_signals
ORDER BY ed.engagement_score DESC
```

This output feeds into threshold adjustment proposals (via the Proposal/Vote system).

---

## Part 7: Data Lifecycle and Maintenance

### 7.1 Write Path

Every inbound/outbound Signal message flows through this sequence:

1. Normalize phone number (E.164).
2. Ensure `HumanProfile` exists (`MERGE` by `human_id`).
3. Run Q2 (Thread Detection). Create new `ConversationThread` if needed.
4. Write `Message` node. Link to thread.
5. Extract `urgency_signals`, `is_question`, `context_type`, `sentiment_score`
   synchronously (bag-of-words; < 5ms).
6. Extract topics synchronously (keyword + entity extraction; existing logic
   from `conversation_logger.py::_extract_topics` ported to Cypher-ready output).
   `MERGE` `Topic` nodes by slug. Create `Message-[:MENTIONS_TOPIC]->Topic`
   and update `ConversationThread-[:DISCUSSES]->Topic` weight.
7. Run engagement scorer (Q3). Write `EngagementDecision`.
8. Queue async jobs: embedding generation, action item extraction (LLM).

### 7.2 Async Jobs

| Job | Trigger | What it does |
|-----|---------|--------------|
| `embed_message` | On message write | Generates `Message.embedding` via OpenRouter |
| `embed_thread_summary` | On thread close | Generates `ConversationThread.summary_embedding` |
| `extract_action_items` | On inbound message | LLM extracts `ActionItem` nodes |
| `classify_thread` | On thread close | LLM sets `intent`, `sentiment_arc`, `summary` |
| `generate_snapshot` | Weekly cron | LLM generates `RelationshipSnapshot` |
| `cluster_topics` | Daily cron | Updates `Topic-[:RELATED_TO]->Topic` edges |
| `decay_topics` | Weekly cron | Applies freshness decay to `Topic.freshness_score` |
| `score_engagement_outcomes` | Weekly cron | Updates `EngagementDecision.outcome` from follow-up signals |

### 7.3 Thread Closure

A `ConversationThread` closes when:
- 30 minutes pass without a new message from either party (detected on next write).
- A new thread is being opened due to topic shift (close previous first).

On closure:
```cypher
MATCH (ct:ConversationThread {thread_id: $thread_id})
SET ct.is_open = false,
    ct.ended_at = datetime(),
    ct.updated_at = datetime()
// Queue: classify_thread async job
```

### 7.4 Retention and Pruning

Follow the existing privacy policy (12-month max, soft delete via anonymization).

```cypher
// Archive messages older than 12 months (flag for export, then detach)
MATCH (m:Message)
WHERE m.sent_at < datetime() - duration({months: 12})
SET m.archived = true

// Prune archived messages after export window (13 months)
MATCH (m:Message {archived: true})
WHERE m.sent_at < datetime() - duration({months: 13})
DETACH DELETE m

// Anonymize HumanProfile on deletion request (existing Q9 in human profile schema)
// RelationshipSnapshot narrative is PII — anonymize on deletion
MATCH (rs:RelationshipSnapshot {human_id: $human_id})
SET rs.narrative = '[redacted]',
    rs.key_observations = [],
    rs.recommended_actions = [],
    rs.embedding = null
```

Topic nodes are never deleted (they are not PII). The `DISCUSSES` and `MENTIONS_TOPIC`
relationships are deleted when the human's messages are pruned.

### 7.5 Decay Schedule

```cypher
// Weekly: decay Topic freshness (mirrors KnowledgeArtifact pattern from NEO4J_PATTERNS.md)
MATCH (tp:Topic)
WHERE tp.last_mentioned_at < datetime() - duration({days: 14})
  AND tp.freshness_score > 0.05
SET tp.freshness_score = tp.freshness_score * 0.90

// Weekly: decay DISCUSSES edge weight for old threads
MATCH (ct:ConversationThread)-[d:DISCUSSES]->(tp:Topic)
WHERE ct.last_message_at < datetime() - duration({days: 30})
SET d.weight = d.weight * 0.75
```

---

## Part 8: Migration Plan

### Phase 1 — Schema-only (COMPLETE)

1. Constraints and indexes applied (vector index `message_embedding` active).
2. Consent categories seeded via `seed_consent_categories()`.
3. Engagement assessor active (LLM-based with heuristic fallback).

### Phase 2 — Parallel write (ACTIVE as of 2026-03-20)

1. New messages write to Neo4j graph (primary) + JSONL fallback (DR).
2. Legacy dual-write retired (2026-03-20) — JSONL fallback provides DR coverage.
3. 205+ messages ingested with embeddings, encryption, threads.
4. Embedding generation runs synchronously at ingestion time via Ollama nomic-embed-text.
5. Consent bootstrapped for all active humans (message_storage + message_analysis).

### Phase 3 — Historical backfill (1-2 weeks, background job)

```python
# backfill_conversations.py — reads existing JSONL files, writes to Neo4j
# Process oldest-first to preserve thread ordering
# Rate-limit: 100 messages/second to avoid overwhelming Neo4j
# Skip messages already in Neo4j (check by message hash or timestamp)
```

Backfilled messages will not have embeddings initially. Queue them for the embedding
job. Thread detection during backfill uses the file timestamps, not real-time gaps —
reconstruct threads by grouping messages with < 30-minute gaps.

### Phase 4 — Cutover (1 day)

1. Confirm backfill is complete and row counts match.
2. Disable JSONL writes.
3. Enable full engagement decision pipeline.
4. Keep JSONL files in read-only mode for 30 days before archiving.

### Phase 5 — Vector search activation (after Phase 4)

Vector indexes require embeddings to be populated before they return useful results.
Activate Q1 (Context Retrieval) only after > 80% of messages have embeddings.
Until then, fall back to full-text search (Q1 alternative):

```cypher
// Full-text fallback for context retrieval (no embedding needed)
CALL db.index.fulltext.queryNodes('message_content_search', $keywords)
YIELD node AS m, score
WHERE m.human_id = $human_id
  AND m.sent_at > datetime() - duration({days: $lookback_days})
RETURN m.message_id, m.content, m.sent_at, score
ORDER BY score DESC LIMIT $top_n
```

---

## Part 9: Rollback Procedures

### Rollback from Phase 2 (parallel write)

Stop Neo4j writes. JSONL files remain the authoritative source. Zero data loss.

### Rollback from Phase 4 (post-cutover)

1. Re-enable JSONL writes (code path still exists, just disabled).
2. Export Neo4j conversation data:
   ```cypher
   MATCH (m:Message)
   WHERE m.sent_at > $cutover_date
   RETURN m.human_id, m.content, m.direction, m.sent_at, m.context_type
   ORDER BY m.sent_at ASC
   ```
3. Merge exported data back into JSONL files using existing `ConversationLogger`.
4. Disable Neo4j conversation writes.

JSONL files from Phase 4 onwards are kept in read-only archive until 30 days post-cutover
specifically to enable this rollback.

---

## Part 10: Testing Strategy

### Unit tests

- Thread detection: verify 30-min gap opens new thread, verify topic shift detection.
- Engagement scorer: verify each signal contributes expected score range.
- Topic extraction: verify slug normalization, deduplication, MERGE behavior.

### Integration tests

```cypher
// Test: task origin traversal (Q7) returns correct thread
// Setup: create Message → Task → ConversationThread chain
// Assert: Q7 returns the correct thread_id and conversation_window

// Test: cross-human topic discovery (Q6) isolates by human
// Setup: two HumanProfile nodes both DISCUSSES same Topic
// Assert: Q6 returns both humans when queried by topic slug

// Test: engagement scorer returns 'silent' for bare acknowledgement
// Setup: Message {content: "ok thanks", is_question: false, urgency_signals: []}
//        RelationshipSnapshot {health_score: 5.0, sentiment_trend: 'stable'}
//        No active tasks
// Assert: engagement_score < 20, decision = 'silent'
```

### Load tests

- Write throughput: 100 messages/second sustained for 60 seconds.
- Q1 (vector search) latency: p99 < 200ms with 100k message nodes.
- Q3 (engagement scorer) latency: p99 < 50ms (synchronous, on critical path).
- Thread detection (Q2) latency: p99 < 20ms.

---

## Appendix A: Property Index — Quick Reference

| Node | Property | Index Type | Purpose |
|------|----------|------------|---------|
| `ConversationThread` | `thread_id` | Unique constraint | Primary key |
| `ConversationThread` | `(human_id, is_open)` | Composite | Open thread lookup |
| `ConversationThread` | `(human_id, last_message_at)` | Composite | Recency sort |
| `ConversationThread` | `summary_embedding` | Vector | Semantic search |
| `ConversationThread` | `(summary, dominant_topics)` | Full-text | Keyword search |
| `Message` | `message_id` | Unique constraint | Primary key |
| `Message` | `(thread_id, sent_at)` | Composite | Timeline within thread |
| `Message` | `embedding` | Vector | Semantic context retrieval |
| `Message` | `content` | Full-text | Keyword search fallback |
| `Topic` | `topic_id` | Unique constraint | Primary key |
| `Topic` | `slug` | Unique constraint | Deduplication |
| `Topic` | `mention_count` | Range | Cross-human analytics |
| `Topic` | `freshness_score` | Range | Decay job |
| `Topic` | `embedding` | Vector | Clustering |
| `Topic` | `(slug, display)` | Full-text | Name search |
| `ActionItem` | `action_id` | Unique constraint | Primary key |
| `ActionItem` | `(human_id, status)` | Composite | Lifecycle tracking |
| `ActionItem` | `description` | Full-text | Search |
| `RelationshipSnapshot` | `snapshot_id` | Unique constraint | Primary key |
| `RelationshipSnapshot` | `(human_id, period_end)` | Composite | Timeline |
| `RelationshipSnapshot` | `embedding` | Vector | Semantic retrieval |
| `RelationshipSnapshot` | `(narrative, key_observations)` | Full-text | Keyword search |
| `EngagementDecision` | `decision_id` | Unique constraint | Primary key |
| `EngagementDecision` | `(human_id, created_at)` | Composite | Outcome analysis |

---

## Appendix B: Relationship Map

```
(HumanProfile)
    │
    ├─[:HAS_THREAD]────────────►(ConversationThread)
    │                                   │
    │                                   ├─[:PRECEDED_BY]──►(ConversationThread)
    │                                   │
    │                                   ├─[:SPAWNED_TASK]──►(Task)
    │                                   │
    │                                   └─[:DISCUSSES]──────►(Topic)
    │                                          │
    │                                          │ (Message)-[:IN_THREAD]──►
    │                                          │
    │                             (Message)────┤
    │                                   │      ├─[:MENTIONS_TOPIC]──►(Topic)
    │                                   │      │
    │                                   │      ├─[:TRIGGERED_TASK]──►(Task)
    │                                   │      │
    │                                   │      ├─[:EXTRACTED_ACTION]─►(ActionItem)
    │                                   │      │
    │                                   │      └─[:HAS_DECISION]──────►(EngagementDecision)
    │                                   │
    │                                   └─[:REPLIES_TO]──────►(Message)
    │
    ├─[:HAS_SNAPSHOT]──────────►(RelationshipSnapshot)
    │                                   │
    │                                   └─[:FOLLOWS]──────────►(RelationshipSnapshot)
    │
    ├─[:HAS_ACTION_ITEM]────────►(ActionItem)
    │                                   │
    │                                   └─[:BECAME_TASK]──────►(Task)
    │
    ├─[:HAS_CONVERSION_CONTEXT]─►(ConversionContext)   [existing]
    │
    ├─[:LINKED_TO]──────────────►(Person)              [existing]
    │
    └─[:HAS_CONSENT]────────────►(ConsentCategory)     [existing]
```

---

## Appendix C: File Locations

| Artifact | Path |
|----------|------|
| This design document | `/Users/kublai/.openclaw/agents/main/docs/NEO4J_CONVERSATION_CONTEXT_DESIGN.md` |
| Schema Cypher (to be created) | `/Users/kublai/.openclaw/agents/main/scripts/neo4j_conversation_schema.cypher` |
| Conversation writer (to be created) | `/Users/kublai/.openclaw/agents/main/scripts/neo4j_conversation_writer.py` |
| Engagement scorer (to be created) | `/Users/kublai/.openclaw/agents/main/scripts/engagement_scorer.py` |
| Backfill script (to be created) | `/Users/kublai/.openclaw/agents/main/scripts/backfill_conversations.py` |
| Existing human profile schema | `/Users/kublai/.openclaw/agents/main/scripts/neo4j_human_profile_schema.cypher` |
| Existing conversation logger | `/Users/kublai/.openclaw/agents/main/scripts/conversation_logger.py` |
| Privacy policy | `/Users/kublai/.openclaw/agents/main/docs/conversation-privacy-policy.md` |
| Neo4j patterns reference | `/Users/kublai/.openclaw/agents/main/docs/NEO4J_PATTERNS.md` |
