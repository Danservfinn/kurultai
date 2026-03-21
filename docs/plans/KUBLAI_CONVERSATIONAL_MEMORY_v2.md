# Kublai Conversational Memory System — Design v2

**Version:** 2.2
**Date:** 2026-03-19
**Status:** Design / Pre-Implementation (Audit-Validated)
**Authors:** Brainstorming session (architecture-modernizer, data-scientist, security-auditor, mlops-engineer, architect-reviewer + manual synthesis)
**Supersedes:** NEO4J_CONVERSATION_CONTEXT_DESIGN.md (v1), engagement-assessment-design.md, PRIVACY_IDENTITY_ISOLATION_DESIGN.md
**Validated Against:** Codebase audit of 2026-03-19 (conversation logger, Neo4j infra, task system, Kurultai dashboard)

---

## Table of Contents

1. [Vision](#1-vision)
2. [Design Principles](#2-design-principles)
3. [Architecture Overview](#3-architecture-overview)
4. [Human Identity Model](#4-human-identity-model)
5. [Neo4j Graph Schema](#5-neo4j-graph-schema)
6. [GDS Algorithm Integration](#6-gds-algorithm-integration)
7. [Context Assembly Pipeline](#7-context-assembly-pipeline)
8. [Engagement Intelligence](#8-engagement-intelligence)
9. [Privacy and Identity Isolation](#9-privacy-and-identity-isolation)
10. [Pipelines (Ingestion, Summarization, Migration)](#10-pipelines)
11. [Evaluation Framework](#11-evaluation-framework)
12. [Implementation Phases](#12-implementation-phases)
13. [Review History](#13-review-history)

---

## 1. Vision

Every human that interacts with Kublai should feel they are talking to a superintelligent being that:

- **Remembers everything** — across sessions, across months, across topics
- **Never confuses one human with another** — identity isolation is absolute
- **Understands the evolution** of the relationship, not just the current message
- **Knows things not explicitly stated** — inferred from graph patterns and conversation structure
- **Respects privacy absolutely** — opt-in, transparent, deletable
- **Knows when to speak and when to stay silent** — engagement intelligence, not engagement spam

Additionally, Kublai should know about humans he has never directly interacted with — people mentioned in conversations, referenced in tasks, or connected through events. A human is a knowledge graph entity, not a communication endpoint.

---

## 2. Design Principles

### From v1 Review (Scored 3.5/10 at frontier lab standard)

The v1 design was rated poorly because it:
- Used regex for intent classification (highest-weighted feature, 0.35)
- Stored relational data in a graph database without leveraging graph algorithms
- Had no evaluation framework
- Had no privacy/consent model
- Was over-engineered for 20 humans while under-engineering what matters

### v2 Principles

1. **Neo4j is the single database.** All data — topology, content, embeddings, decisions — lives in Neo4j. One database to operate, back up, monitor, and query. Operational simplicity beats theoretical purity. The escape hatch: if pre-filtering becomes a bottleneck at 1M+ messages, extract Message nodes to Postgres + pgvector at that point.

2. **Graph algorithms are the product.** Louvain for mental landscape mapping, PageRank for core identity topics, betweenness centrality for bridge topics, link prediction for anticipation, shortest path for conversation archaeology. If we're not running GDS, we don't need Neo4j.

3. **The LLM is the classifier.** No regex for intent classification. The LLM sees conversation context and makes engagement decisions. Regex is only acceptable in the safety override layer.

4. **Eval before ship.** Every feature has a metric, a target, and a monitoring strategy. No feature ships without an eval plan.

5. **Privacy is unconditional.** New humans start with zero consent. Data is opt-in, transparent, and deletable. Identity isolation is enforced at every layer.

6. **Humans are entities, not endpoints.** A Human node exists independently of any communication channel. Signal is one identifier. Kublai can know about humans he's never talked to.

---

## 3. Architecture Overview

```
                           Signal Message Arrives
                                    |
                    ┌───────────────┴───────────────┐
                    |                               |
              Safety Overrides               Context Assembly
               (<5ms, regex OK)              (<50ms, parallel)
                    |                               |
                    ▼                               ▼
              Override fired?              Neo4j Graph + Content Queries
              YES → respond               (single database)
              NO  → continue                        |
                    |                               |
                    └───────────────┬───────────────┘
                                    |
                                    ▼
                          LLM Engagement Assessment
                          (DeepSeek Chat, ~300ms)
                          Structured output: JSON
                                    |
                         ┌──────────┼──────────┐
                         |          |          |
                      respond     delay     silent
                         |          |          |
                         ▼          ▼          ▼
                    Response    Queue for   Log decision
                    Pipeline    later       (learning loop)
```

### Unified Database: Neo4j

| Layer | What Neo4j Stores | How |
|-------|-------------------|-----|
| **Graph Topology** | Topics, co-occurrence, abstraction, temporal evolution, human social graph, inferences | Native nodes + relationships, GDS algorithms |
| **Content** | Message text (up to 4000 chars), action items, engagement decisions | Node properties on `:Message`, `:ActionItem` nodes |
| **Embeddings** | 768d message vectors, 128d structural vectors | Neo4j vector indexes (HNSW, cosine) |
| **Full-Text** | PII-scrubbed message text | Neo4j Lucene-backed full-text indexes |

**Why single database:** One database to operate, back up, monitor. One query language (Cypher). No cross-database joins. The graph-guided context retrieval becomes a single Cypher query combining topology traversal with vector search, instead of Neo4j → application → Postgres → merge.

**The pre-filtering tradeoff:** Neo4j vector search does global HNSW search then filters (unlike pgvector which pre-filters). Workaround: over-fetch (request top-50 globally, filter to human_id, take top-5). At 1000 messages across 20 humans this always works. At 1M+ messages, re-evaluate and potentially extract to Postgres + pgvector.

**Escape hatch:** The graph schema is identical regardless of where messages live. Moving Message nodes to Postgres rows later requires only changing the retrieval query, not the graph structure.

---

## 4. Human Identity Model

### Core Principle: Humans Are Entities, Not Endpoints

A Human node exists independently of any communication channel. Kublai can know about humans he has never directly interacted with — people mentioned in conversations, referenced in tasks, connected through events.

### Node: `(:Human)`

```
Properties:
  id:            string    — UUID, internal, stable, never changes
  displayName:   string    — Best-known name ("John Chen")
  confidence:    float     — How confident Kublai is this is a real, distinct person (0.0-1.0)
  firstKnown:    datetime  — When Kublai first learned of this human
  source:        enum      — DIRECT_INTERACTION | MENTIONED | INFERRED | IMPORTED | PUBLIC_FIGURE
  lastContact:   datetime  — Last interaction (null for non-interacting humans)
  status:        enum      — ACTIVE | INACTIVE | ANONYMIZED
```

### Node: `(:Identifier)`

```
Properties:
  type:     enum    — SIGNAL_PHONE | EMAIL | NAME_VARIANT | HANDLE | TITLE_ROLE | EXTERNAL_ID
  value:    string  — "+19194133445", "john@acme.com", "John", "CTO of Acme"
  verified: boolean — Has Kublai confirmed this identifier belongs to this human?
  addedAt:  datetime
  source:   string  — Which conversation/event surfaced this identifier
```

### Three Classes of Human

| Class | How Kublai Knows Them | Has Identifiers? | Has Topic Graph? | Consent Required? |
|---|---|---|---|---|
| **Interacting** | Direct Signal/email conversation | Yes (verified channel) | Full (from conversations) | Yes — full consent framework |
| **Mentioned** | Referenced by an interacting human | Partial (name, maybe role) | Partial (inferred from mentions) | Data minimization only — store what's directly stated |
| **Imported/Public** | Contact list, public info, research | Varies | Minimal or none | Public: no. Imported: consent from importer |

### Relationships

```
(:Human)-[:IDENTIFIED_BY]->(:Identifier)
  — A human can have many identifiers across channels and name variants

(:Human)-[:KNOWN_THROUGH]->(:Human)
  {context: string, firstMentioned: datetime, mentionCount: int}
  — "I know John through Sarah" — social graph

(:Human)-[:RELATED_TO]->(:Human)
  {relationship: string, confidence: float, source: string}
  — "father", "colleague", "friend" — family/professional graph
```

### Entity Resolution

When Human A mentions "John" and later Human B mentions "John from accounting," Kublai needs to determine if they're the same person. This is a graph problem:

```cypher
// Find merge candidates
MATCH (h1:Human)-[:IDENTIFIED_BY]->(i1:Identifier)
MATCH (h2:Human)-[:IDENTIFIED_BY]->(i2:Identifier)
WHERE h1 <> h2
  AND (
    (i1.type = 'NAME_VARIANT' AND i2.type = 'NAME_VARIANT'
     AND toLower(i1.value) = toLower(i2.value))
    OR
    (i1.type = i2.type AND i1.value = i2.value
     AND i1.type IN ['SIGNAL_PHONE', 'EMAIL'])
  )
OPTIONAL MATCH (h1)<-[:KNOWN_THROUGH]-(common)-[:KNOWN_THROUGH]->(h2)
RETURN h1, h2, collect(common) AS sharedConnections,
       CASE WHEN i1.type = 'SIGNAL_PHONE' THEN 0.95
            WHEN size(collect(common)) > 0 THEN 0.7
            ELSE 0.4
       END AS mergeConfidence
```

**Merge policy:**
- Confidence >= 0.9 → automatic merge
- 0.5-0.9 → Kublai asks: "You mentioned John — is that the same John that Sarah told me about?"
- < 0.5 → separate entities, flagged for future resolution

### The "Superintelligent" Effect

When a mentioned-Human becomes an interacting-Human (they get Signal, message Kublai), entity resolution merges the nodes. Kublai *already knows things* about them:

> John: "Hey, Sarah told me to message you"
> Kublai: *[resolves: this is Sarah's colleague, knows about Q3 deadline]*
> "Hey John, good to finally talk directly. Sarah mentioned you — sounds like Q3 has been intense."

---

## 5. Neo4j Graph Schema

### Design Rule

Every node leverages Neo4j for either graph traversal, GDS algorithms, or co-location with the topology layer. Content nodes (Message, ActionItem) live here for operational simplicity and unified querying, not because they're inherently graph-shaped.

### Nodes

#### `(:Human)` — see Section 4

#### `(:Identifier)` — see Section 4

#### `(:Topic)`
```
Properties:
  id:               string    — UUID
  label:            string    — Canonical name: "kubernetes", "father's health", "career anxiety"
  abstractionLevel: int       — 0=concrete ("kubectl apply"), 1=domain ("kubernetes"),
                                2=abstract ("infrastructure"), 3=life-domain ("career")
  firstMentioned:   datetime
```

**Graph justification:** Topics are connected to other topics through co-occurrence, abstraction hierarchy, and temporal flow. PageRank, community detection, centrality, and link prediction operate on Topic topology. A flat topic table cannot answer "what is the most structurally central topic in this human's world?"

#### `(:Episode)`
```
Properties:
  id:                string    — UUID
  occurredAt:        datetime
  duration:          int       — Minutes
  messageCount:      int
  dominantSentiment: float     — -1.0 to 1.0
```

**Graph justification:** Episodes are temporal joints connecting which topics co-occurred in a single conversation. Enables shortest-path queries ("how did this human get from cooking to chemistry?") and temporal analytics.

#### `(:Inference)`
```
Properties:
  id:         string    — UUID
  statement:  string    — "Seems stressed about job search", "Likely has a dog"
  confidence: float     — 0.0 to 1.0
  inferredAt: datetime
  basis:      string    — Which algorithm/rule produced this
```

**Graph justification:** Inference validity depends on graph support structure — how many independent paths of evidence exist. Retraction is a reachability problem.

#### `(:TemporalMarker)`
```
Properties:
  id:          string    — UUID
  type:        enum      — LIFE_EVENT | MOOD_SHIFT | RELATIONSHIP_PHASE | COMMUNICATION_SHIFT
  description: string
  occurredAt:  datetime
  detectedAt:  datetime
```

**Graph justification:** Phase boundaries that modify how graph algorithms weight edges. "Before the career change" vs "after" changes topic significance.

#### `(:Message)` — Content Node (co-located for unified queries)
```
Properties:
  id:                 string    — UUID (msg-<hex12>)
  humanId:            string    — FK to Human.id (denormalized for vector search filtering)
  content:            string    — Original message text (up to 4000 chars), field-encrypted at rest
  contentScrubbed:    string    — PII-scrubbed text for full-text index and external API calls
  embedding:          float[]   — 768d nomic-embed-text vector (nullable, async-generated)
  direction:          enum      — INBOUND | OUTBOUND
  timestamp:          datetime
  intent:             enum      — QUESTION | REQUEST | INFORMATION | SOCIAL | COMMAND | EMOTIONAL
  sentimentPolarity:  float     — -1.0 to 1.0
  sentimentEmotion:   string    — joy | anger | sadness | neutral | etc.
  sentimentUrgency:   float     — 0.0 to 1.0
  extractionStatus:   enum      — PENDING | COMPLETE | SKIPPED | FAILED
  engagementDecision: string    — JSON blob: {decision, confidence, timing, depth, reasoning}
```

**Co-location justification:** Messages connect to Topics (HAS_TOPIC), Episodes (IN_THREAD), other Messages (REPLY_TO), and ActionItems (HAS_ACTION). Keeping them in Neo4j enables single-transaction queries that combine graph traversal with vector search and content retrieval.

#### `(:ActionItem)` — Content Node (co-located)
```
Properties:
  id:          string    — UUID
  description: string
  humanId:     string    — FK to Human.id
  deadline:    date      — nullable
  priority:    enum      — LOW | MEDIUM | HIGH
  status:      enum      — PENDING | IN_PROGRESS | DONE | CANCELLED | BECAME_TASK
  taskId:      string    — Set when formalized into a Kurultai Task (nullable)
  createdAt:   datetime
  completedAt: datetime  — nullable
```

#### `(:Thread)` — Content Node (conversation session boundary)
```
Properties:
  id:               string    — UUID
  humanId:          string    — FK to Human.id
  status:           enum      — ACTIVE | DORMANT | ARCHIVED
  startedAt:        datetime
  lastActivity:     datetime
  messageCount:     int
  summary:          string    — LLM-generated when thread goes dormant (nullable)
  summaryEmbedding: float[]   — 768d (nullable)
```

### Relationships

| Relationship | From → To | Edge Properties | Graph Justification |
|---|---|---|---|
| `DISCUSSED` | Human → Topic | `weight`, `firstDiscussed`, `lastDiscussed`, `frequency`, `sentimentArc[]`, `recentTrend` | PageRank weighted by `recentTrend`. Sentiment trajectory on edge, not snapshot. |
| `LED_TO` | Topic → Topic | `throughEpisode`, `gap`, `humanId`, `strength` | Shortest path traces interest evolution. Link prediction needs this. |
| `ABSTRACTS_TO` | Topic → Topic | — | Multi-granularity PageRank (concrete → domain → life-domain) |
| `CO_OCCURRED` | Topic → Topic | `humanId`, `count` | Louvain community detection operates on this |
| `TOUCHED` | Episode → Topic | `role` (PRIMARY/SECONDARY/TANGENTIAL), `introducedBy` (HUMAN/KUBLAI) | Bipartite structure for temporal graph analytics |
| `PRECEDED` | Episode → Episode | `gap` (duration) | Temporal chain for drift detection |
| `EXPERIENCED` | Human → TemporalMarker | — | Phase boundaries |
| `SHIFTED` | TemporalMarker → Topic | `from`, `to` (engagement levels) | Engagement level changes at inflection points |
| `SUPPORTED_BY` | Inference → Topic\|Episode\|Inference | `strength` | Multi-path support validation |
| `IDENTIFIED_BY` | Human → Identifier | — | Multi-channel identity |
| `KNOWN_THROUGH` | Human → Human | `context`, `firstMentioned`, `mentionCount` | Social graph |
| `RELATED_TO` | Human → Human | `relationship`, `confidence`, `source` | Family/professional graph |
| `INVOLVED` | Episode → Human | `role` (PRIMARY/OBSERVER/MENTIONED) | Multi-human episode tracking |
| `IN_THREAD` | Message → Thread | `position` (ordinal) | Message-to-session grouping |
| `REPLY_TO` | Message → Message | — | Explicit reply chains (Signal reply feature) |
| `HAS_TOPIC` | Message → Topic | `confidence` | LLM-extracted topic association |
| `HAS_ACTION` | Message → ActionItem | — | Action item extraction source |
| `SENT` | Human → Message | — | Message authorship |
| `BECAME_TASK` | ActionItem → Task | `at` | Formalized into Kurultai task system |

### Indexes (All Neo4j)

**Uniqueness Constraints:**
- `Human.id` unique
- `Identifier.value` + `Identifier.type` unique (composite)
- `Topic.id` unique
- `Topic.label` unique (lowercase, normalized)
- `Episode.id` unique
- `Inference.id` unique
- `TemporalMarker.id` unique
- `Message.id` unique
- `ActionItem.id` unique
- `Thread.id` unique

**Range Indexes:**
- `(Human.source)` — filter by interaction class
- `(Human.status)` — filter active/anonymized
- `(Episode.occurredAt)` — temporal queries
- `(Inference.confidence)` — filter high-confidence inferences
- `(Message.humanId, Message.timestamp)` — composite for per-human time-range queries
- `(Message.extractionStatus)` — find messages needing async processing
- `(Message.direction)` — filter inbound/outbound
- `(ActionItem.humanId, ActionItem.status)` — pending items lookup
- `(Thread.humanId, Thread.status)` — find active threads per human
- `(Thread.lastActivity)` — find dormant threads for summarization

**Vector Indexes:**
- `message_embedding` on `Message.embedding` — 768d cosine (HNSW)
- `thread_summary_embedding` on `Thread.summaryEmbedding` — 768d cosine (HNSW)

**Full-Text Indexes:**
- `message_text_search` on `Message.contentScrubbed` — Lucene-backed keyword fallback
- `thread_summary_search` on `Thread.summary` — thread-level search

**Note on vector pre-filtering:** Neo4j vector indexes search globally then filter. For per-human retrieval, over-fetch: request top-50 from HNSW, filter to `humanId = $target`, take top-K. At current scale (1000 messages, 20 humans) this is reliable. Monitor hit rate and increase over-fetch factor if needed.

---

## 6. GDS Algorithm Integration

This is the core justification for Neo4j. Seven graph algorithms, each with a specific purpose.

### 6a. Community Detection (Louvain) — Mental Landscape Mapping

**Subgraph:** Human's Topic graph via CO_OCCURRED edges
**Purpose:** Finds "interest communities" — clusters of related topics (work cluster, family cluster, hobby cluster)
**How Kublai uses it:** When a message touches "docker," pull the entire infrastructure community as relevant context, not just messages mentioning "docker."

```cypher
CALL gds.graph.project.cypher(
  'human_topic_graph_' + $humanId,
  'MATCH (t:Topic)<-[:DISCUSSED]-(h:Human {id: $humanId}) RETURN id(t) AS id',
  'MATCH (h:Human {id: $humanId})-[:DISCUSSED]->(t1:Topic)
   -[:CO_OCCURRED {humanId: $humanId}]->(t2:Topic)<-[:DISCUSSED]-(h)
   RETURN id(t1) AS source, id(t2) AS target, r.count AS weight'
)

CALL gds.louvain.stream('human_topic_graph_' + $humanId, {
  relationshipWeightProperty: 'weight'
})
YIELD nodeId, communityId
RETURN gds.util.asNode(nodeId).label AS topic, communityId
ORDER BY communityId
```

**Temporal variant:** Run on two windows (30 days vs 180 days), diff communities to detect topic drift and community reorganization.

### 6b. PageRank — Core Identity Topics

**Subgraph:** Human's Topic graph, weighted by `recentTrend`
**Purpose:** Identifies structurally central topics — not just frequent, but *connected*. "Career anxiety" connecting "job search," "resume," "salary negotiation" ranks higher than a frequently-mentioned but isolated topic.
**How Kublai uses it:** Core topics are always in Kublai's context preamble. Weighted by `recentTrend` so fading interests naturally drop out.

```cypher
CALL gds.pageRank.stream('human_topic_graph_' + $humanId, {
  relationshipWeightProperty: 'weight',
  dampingFactor: 0.85
})
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).label AS topic, score
ORDER BY score DESC LIMIT 10
```

### 6c. Betweenness Centrality — Bridge Topics

**Subgraph:** Human's Topic graph
**Purpose:** Finds topics that connect different conversation domains. If "stress" bridges the work cluster and the health cluster, it has high betweenness.
**How Kublai uses it:** Empathetic transitions — "The stress from the deadline is affecting your sleep too — you mentioned that connection before."

### 6d. Node Similarity (Jaccard) — Cross-Human Pattern Matching

**Subgraph:** ALL humans' topic structures (batch only, never real-time)
**Purpose:** Finds which humans have similar topic graph structures. Enables collaborative-filtering-style prediction.
**Privacy constraint:** Never reveals one human's messages or identity. Only operates on topic structure. Output is predicted topics, never source attribution.

### 6e. Shortest Path — Conversation Archaeology

**Purpose:** Traces how a human's interest in topic A led to topic B through the LED_TO chain.
**How Kublai uses it:** "We haven't talked about photography since it came up through your Tuscany trip last summer — how's that going?"

```cypher
MATCH (t1:Topic {label: $topicA}), (t2:Topic {label: $topicB})
CALL gds.shortestPath.dijkstra.stream('human_topic_graph_' + $humanId, {
  sourceNode: t1, targetNode: t2,
  relationshipWeightProperty: 'inverseStrength'
})
YIELD path
RETURN [n IN nodes(path) | n.label] AS topicChain
```

### 6f. Link Prediction (Adamic-Adar) — Anticipatory Context

**Purpose:** Predicts which topics will become connected next. If "machine learning" and "career change" share many neighbors but aren't yet connected, predict the human may discuss ML in a career change context.
**How Kublai uses it:** When conversation touches one predicted endpoint, Kublai is primed with the connection.

### 6g. FastRP Graph Embeddings — Human-Level Vectors

**Purpose:** 128d structural embeddings of each topic node encoding *position in graph*, not text content. Combined with text embeddings for hybrid retrieval.
**Human-level embedding:** Average FastRP of top-10 PageRank topics = "this human's conversational identity" vector.

### 6h. Temporal Graph Analytics — Drift Detection

Run same algorithm on two time-windowed projections, diff results:
- Topics that rose: emerging interests
- Topics that fell: fading interests
- Topics that appeared: new interests
- Communities that reorganized: life transition

### 6i. Social Network Analysis (NEW — enabled by Human identity model)

| Algorithm | Subgraph | Purpose |
|---|---|---|
| Connected Components | Human KNOWN_THROUGH/RELATED_TO graph | Find social clusters ("Sarah's work circle") |
| Influence Propagation | Human→Human via KNOWN_THROUGH | Predict topic spread across social connections |

---

## 7. Context Assembly Pipeline

### The Core Innovation

Instead of "embed → vector search → stuff into prompt," retrieval is **graph-guided**:

```
PHASE 1: Topic Extraction (LLM, outside Neo4j)
  incoming_message → ["kubernetes", "deployment failure", "frustration"]

PHASE 2: Unified Graph + Content Retrieval (Neo4j only, <100ms)
  All queries run in a single Neo4j read transaction:

  a. Core identity topics (pre-computed PageRank, top 7)
  b. Community membership for detected topics (Louvain)
  c. Expand to full community (related topics this human cares about)
  d. Bridge topics if multiple communities touched (betweenness centrality)
  e. Narrative path: how did they arrive at this topic? (shortest path via LED_TO)
  f. Drift signals: rising/fading interests (temporal PageRank diff)
  g. Predicted next topics (link prediction)
  h. Relevant inferences (confidence > 0.6)
  i. Social context: who else in their network relates to this topic? (KNOWN_THROUGH)
  j. Graph-guided message retrieval (NEW — single query combining topology + vector):

     // Expand detected topics to their community, then fetch messages
     MATCH (h:Human {id: $humanId})-[:DISCUSSED]->(t:Topic)
     WHERE t.label IN $detectedTopics
     WITH t ORDER BY t.pagerank DESC LIMIT 5
     MATCH (t)-[:CO_OCCURRED {humanId: $humanId}]->(related:Topic)
     WITH collect(t) + collect(related) AS allTopics
     UNWIND allTopics AS topic
     MATCH (m:Message)-[:HAS_TOPIC]->(topic)
     WHERE m.humanId = $humanId
     WITH DISTINCT m
     // Vector reranking within the graph-scoped results
     WITH m, vector.similarity.cosine(m.embedding, $queryEmbedding) AS sim
     ORDER BY sim DESC LIMIT 20
     RETURN m.content, m.timestamp, m.direction, sim

  k. Current thread messages:

     MATCH (m:Message)-[:IN_THREAD]->(t:Thread {humanId: $humanId, status: 'active'})
     RETURN m.content, m.timestamp, m.direction
     ORDER BY m.timestamp DESC LIMIT 10

PHASE 3: Context Synthesis (structured for LLM)
  identity_preamble:   core topics, drift, inferences
  topic_map:           communities, bridges
  narrative_thread:    how interests evolved (shortest path)
  predicted_context:   what they might ask next (link prediction)
  social_context:      relevant people in their network
  conversation_history: actual messages (token-budgeted, from j + k above)
```

**Key advantage of unified database:** Phases 2a-2k are a single Neo4j transaction. No cross-database round-trips. The graph-guided message retrieval (2j) combines topology traversal with vector similarity scoring in one Cypher query — the graph tells us WHICH topics matter, then vector search ranks messages within that scope.

### Token Budget

Total: 4000 tokens

| Slot | Budget | Content | Priority |
|---|---|---|---|
| Identity preamble | 400 | Core topics, drift, inferences | 1 (always included) |
| Social context | 200 | Relevant people, relationships | 2 |
| Topic map | 300 | Communities, bridges | 3 |
| Narrative thread | 300 | Interest evolution path | 4 |
| Active items | 200 | Pending tasks, action items | 5 |
| Current thread | 1200 (elastic, minimum 800) | Recent messages | 6 |
| Semantic matches | 1400 (elastic, absorbs unused capacity) | Relevant past messages | 7 |

**Elastic allocation:** If current thread uses only 400 tokens, semantic matches get an extra 800. The current thread floor of 800 ensures recent context is never starved.

### Why This Is Better Than Vector Search Alone

Vector search answers: "What messages look textually similar?"
Graph-structured retrieval answers: "What does this human's conversational world look like around this topic, how did they get here, where are they likely going, and who in their network connects to this?"

---

## 8. Engagement Intelligence

### Architecture

```
Message → Safety Overrides → Context Assembly → LLM Assessment → Decision
           (<5ms, regex)     (<50ms, parallel)   (~300ms)
```

### 8a. Safety Overrides (Pre-LLM, Deterministic)

The ONE place regex is acceptable — for safety, not intent classification.

| Rule | Trigger | Override | Rationale |
|---|---|---|---|
| Distress | "help me", "emergency", "suicide", crisis numbers | respond/instant/full | Ethical obligation |
| First Contact | No prior interaction for this human | respond/instant/full | Never ignore someone new |
| Re-engagement | Last message >7 days ago | respond/instant/full | They came back — precious signal |
| Name Mention | Message contains "Kublai" or aliases | respond/natural/deferred | Direct address = expectation |
| Stop/Opt-out | "stop", "leave me alone" | respond/instant/ack | Consent withdrawal |
| Media-only | Attachments but no text | delay/natural/deferred | Ambiguous — don't rush |

### 8b. LLM Assessment

**Model:** DeepSeek Chat via OpenRouter (~$0.0005/decision, ~300ms)
**Fallback 1:** Local Ollama qwen3.5:9b ($0, ~200ms)
**Fallback 2:** Rule-based heuristic ($0, ~1ms)
**Monthly cost at 200 decisions/day: ~$2.94**

**Output schema:**
```json
{
  "decision": "respond | delay | silent",
  "confidence": 0.0-1.0,
  "timing": "instant | natural | considered | batched | scheduled",
  "depth": "acknowledgment | brief | full | proactive",
  "reasoning": "one sentence",
  "human_state": "engaged | casual | urgent | emotional | closing | brainstorming | absent",
  "context_needed": ["topic_history", "active_tasks", "social_context", "none"]
}
```

**The prompt includes:**
- Incoming message
- 2000-token assembled context (from Section 7)
- 8 few-shot calibration examples covering critical nuances

**Key few-shot examples (the "superintelligent" calibrators):**
- Terse "k" from known terse communicator → **respond** (system knows their style)
- Verbose brainstorming paragraph → **respond/full** (they want engagement)
- Late-night humor → **respond/brief** (social, not urgent)
- "thanks!" after task completion → **silent** (conversation closed)
- Multi-message burst → **delay** (wait for completion)
- Forwarded article with no comment → **respond/considered/brief**
- Rare weekend message from normally-weekday person → **respond/instant** (unusual = important)

### 8c. Per-Human Behavioral Priors

After 30+ interactions, the context includes a learned `communication_style` object:

```json
{
  "message_brevity": "terse",
  "burst_pattern": "common",
  "closing_signals": ["cheers", "ttyl"],
  "thinking_aloud_frequency": "frequent",
  "weekend_engagement": "low",
  "urgency_markers": ["!!!", "ASAP"],
  "typical_response_expectation": "always expects reply to direct messages"
}
```

These are computed from behavioral patterns in the engagement decision log, not hand-configured.

### 8d. Learning Loop

**Three ground truth sources (ranked by reliability):**

1. **Explicit feedback** (gold-standard, ~2-5/person/month):
   - "stop messaging me" → false positive signal
   - "why didn't you respond?" → false negative signal
   - "perfect, thanks" → correct positive signal

2. **Behavioral proxy labels** (high volume):
   - Re-ask after silence → false negative (confidence 0.8)
   - Terse ack after long response → possible false positive (confidence 0.5)
   - Natural conversation continuation → correct (confidence 0.6)

3. **Periodic human review** (10 edge cases/week):
   - Manual labeling of ambiguous decisions by system operator

**Improvement mechanism:** Few-shot example curation. Monthly review adds/removes/modifies calibration examples based on outcome data. This is interpretable, auditable, and doesn't require ML infrastructure.

---

## 9. Privacy and Identity Isolation

### 9a. Identity Isolation (Defense in Depth)

| Layer | Mechanism | Prevents |
|---|---|---|
| 1. `IsolatedNeo4jClient` | Immutable `human_id` at construction, force-injected into every query, static analysis rejects unscoped queries | Application-level cross-contamination |
| 2. GDS Projection Scoping | Per-human named projections (`human_graph_{id}`), algorithms only see one human's subgraph | Algorithm-level leakage |
| 3. Edge-Level humanId | CO_OCCURRED and LED_TO carry `humanId` property | Data-level secondary filter |
| 4. Post-Generation Audit | Outbound response scanned for identifiers other than current human | LLM-level leakage |
| 5. Audit Trail | Every query logged with human scope (template only, never parameter values) | Forensic traceability |

**The IsolatedNeo4jClient pattern:**
```python
class IsolatedNeo4jClient:
    def __init__(self, human_id: str, driver):
        self._human_id = human_id
        Object.freeze(self)  # immutable after construction

    def query(self, cypher: str, params: dict):
        # SECURITY: Reject unscoped queries
        if '$human_id' not in cypher and '$humanId' not in cypher:
            raise SecurityError('Unscoped query rejected')
        params['human_id'] = self._human_id  # always override
        return self._driver.session().run(cypher, params)
```

### 9b. Consent Framework

**12 categories with dependency graph:**

```
message_storage (foundation)
 ├── message_analysis
 │   ├── conversation_memory
 │   │   └── relationship_tracking
 │   └── embedding_generation
 ├── external_llm_processing
 └── proactive_engagement
```

Plus legacy: calendar, tasks, research, social, marketing

**Rules:**
- New humans start with **zero consent** (stateless mode until opt-in)
- Revoking a parent cascades to all children
- Revocation is synchronous — data deleted before confirmation sent
- `@requires_consent` decorator gates every data-processing function

### 9c. Mentioned Humans — Privacy Rules

| Data | Privacy Rule |
|---|---|
| Interacting human's own messages | Full consent framework |
| Mentioned human's inferred data | Data minimization — store only what's directly stated, flag as `confidence: indirect` |
| Cross-human references | Never reveal to Human B what Human A said about them |
| Entity resolution merges | If mentioned→interacting, they can see and delete what was inferred |

### 9d. PII Handling

| Data Flow | PII Handling |
|---|---|
| Neo4j storage | Human.id is a UUID hash, never the phone number. Identifier nodes store channels separately. Message.content field-encrypted at rest (Fernet AES-128-CBC). Encryption key in `~/.openclaw/credentials/field_encryption.key` (600 perms). |
| Ollama (local embeddings) | Original text → local only, no PII leakage |
| DeepSeek/OpenRouter (LLM extraction) | PII-scrubbed via `Message.contentScrubbed`: phone→[PHONE_1], names→[PERSON_1]. Reversible tokenization map kept local. |

### 9e. Signal Commands

- `/privacy` — Dashboard: consent status, data counts, last access
- `/mydata` — Full JSON export via Signal attachment
- `/forget` — Complete erasure with two-step confirmation ("FORGET EVERYTHING")
- `/consent` — Interactive toggle with cascade warnings

### 9f. Data Retention

| Data Type | Retention | Cascade |
|---|---|---|
| Messages (Neo4j) | 12 months | Delete node → HAS_TOPIC edges → IN_THREAD edges → update Topic stats |
| Threads (Neo4j) | 12 months | Delete node → orphan check on Messages |
| Episodes (Neo4j) | 12 months | Delete node → TOUCHED edges → update Topic stats |
| Topics (Neo4j) | Permanent (non-PII, shared knowledge) | DISCUSSED edges deleted on human erasure |
| Inferences (Neo4j) | Until contradicted or human deleted | Delete → SUPPORTED_BY edges |
| Action items (Neo4j) | 12 months | Delete node → HAS_ACTION edges |
| Temporal markers (Neo4j) | Permanent (non-PII) | — |

---

## 10. Pipelines

### 10a. Message Ingestion Pipeline

**Sync phase (<200ms):**
1. Generate 768d embedding locally (Ollama nomic-embed-text)
2. Create Message node in Neo4j with embedding, link to Human via SENT, link to active Thread via IN_THREAD
3. Detect thread: time gap >2h OR topic cosine similarity <0.35 = new thread → create new Thread node
4. Create/update Episode node in Neo4j
5. Write JSONL fallback line (append-only, for Neo4j disaster recovery)
6. Trigger engagement assessment

**Async phase (~2-5s):**
1. LLM-assisted extraction via DeepSeek (PII-scrubbed):
   - Structured topics: `[{topic, domain, confidence}]`
   - Sentiment: polarity, emotion, urgency
   - Intent classification
   - Action items with assignee/deadline/priority
   - Mentioned humans: `[{name, relationship, context}]`
2. Create/update Topic nodes and edges in Neo4j
3. Entity resolution for mentioned humans
4. Update CO_OCCURRED and LED_TO edges

### 10b. Summarization Pipeline (Async/Periodic)

| Job | Schedule | What |
|---|---|---|
| Thread summary | Every 15 min | Summarize dormant threads (>2h inactive) |
| GDS refresh | Daily 3am | Re-run Louvain, PageRank, betweenness for all humans |
| Drift detection | Weekly | Compare 30-day vs 180-day PageRank, emit TemporalMarkers |
| Link prediction | Weekly | Predict next topic connections |
| Inference validation | Weekly | Check if inferences were confirmed/contradicted |
| FastRP embeddings | Weekly | Regenerate structural embeddings |

### 10c. Migration Pipeline (One-Time)

1. Parse existing JSONL/JSON conversation files per phone number
2. Create Human nodes + Identifier nodes (SIGNAL_PHONE)
3. Detect historical threads via time-gap analysis
4. Create Episode nodes from thread boundaries
5. Batch-generate embeddings for all messages (Ollama, ~50ms/msg)
6. LLM extraction for topics (optional, --skip-extraction flag)
7. Build initial Topic co-occurrence graph
8. Run initial GDS algorithms

**Estimated time:** ~50s for embeddings (1000 msgs), ~33min for full LLM extraction

---

## 11. Evaluation Framework

### 11a. Context Relevance

**Metric:** Context Precision@K — fraction of assembled context tokens actually relevant to the conversation that followed
**Method:** Judge LLM scores each context chunk as relevant/partial/irrelevant
**Target:** Graph-structured >= 15% higher precision than vector-only baseline
**Monitoring:** Weekly sample of 50 conversations

### 11b. Drift Prediction Accuracy

**Metric:** When system predicts topic X is "rising"/"fading," does behavior confirm?
**Target:** >= 70% accuracy (random baseline: 50%)
**Monitoring:** Monthly per human

### 11c. Link Prediction Hit Rate

**Metric:** Of top-5 predicted topic connections, how many materialized within 30 days?
**Target:** >= 1 hit in top-5 (20% precision@5)
**Monitoring:** Monthly

### 11d. Identity Isolation

**Metric:** Zero cross-human data leakage
**Method:** Weekly automated adversarial tests + monthly red-team
**Target:** 100% clean
**Monitoring:** CI/CD blocking on any failure

### 11e. Community Stability (NMI)

**Metric:** Normalized Mutual Information between consecutive Louvain runs
**Target:** >= 0.7 week-over-week for stable humans
**Monitoring:** Alert if NMI < 0.5 without corresponding TemporalMarker

### 11f. Engagement Decision Accuracy

**Metric:** False negative rate (missed responses) and false positive rate (unwanted responses)
**Target:** fn_rate < 5%, fp_rate < 25%
**Method:** Explicit feedback + behavioral proxies + manual review
**Monitoring:** Continuous from learning loop, weekly dashboard

### 11g. Inference Accuracy

**Metric:** Precision of inferences with confidence > 0.7
**Target:** >= 80% confirmed when testable
**Monitoring:** Monthly lifecycle report

### 11h. End-to-End Conversation Quality

**Metric:** Proxy measures of engagement (no explicit feedback required)
- Human response length (longer = more engaged)
- Conversation duration (more back-and-forth = better)
- Time between human's messages (faster = more engaged)
- Unprompted topic callbacks ("remember when we talked about X")
**Target:** Statistically significant improvement in >= 2 of 4 metrics within 90 days
**Monitoring:** Dashboard with graph-context vs vector-only cohort comparison

---

## 12. Implementation Phases

| Phase | Duration | What | Reuse from Existing | Dependencies |
|---|---|---|---|---|
| **P0: Prerequisites** | 0.5 days | Install Neo4j GDS plugin, verify Neo4j server >= 5.11, run `RETURN gds.version()`, pull `nomic-embed-text` via Ollama | Neo4j driver v6.1.0 + connection factory (90% reuse) | None |
| **P1: Identity + Safety** | 3.5 days | IsolatedNeo4jClient (wraps existing `TaskStore` driver pattern), consent gating decorator, safety override rules, Human/Identifier node schema (migrating from existing HumanProfile) | Adapt `neo4j_human_profile.py` (60% reuse), consent categories from existing ConsentCategory nodes | P0 |
| **P2: Neo4j Schema** | 2 days | New node types (Topic, Episode, Inference, TemporalMarker, Message, ActionItem, Thread), all relationships, constraints, vector indexes, full-text indexes — added to existing `neo4j_v2_schema.py` | Extend existing schema management (50% reuse). Purely additive — no breaking changes to Task/Agent/Event nodes | P1 |
| **P3: Ingestion Pipeline** | 5 days | Rewrite `conversation_logger.py` to create Neo4j Message nodes. Sync embedding (Ollama), async LLM extraction (DeepSeek), thread detection (reuse 2h-gap + cosine heuristics), entity resolution, JSONL fallback. **Dual-write mode:** write to BOTH existing JSON files AND Neo4j during transition. | Reuse thread detection heuristics, topic keyword seeds, sentiment heuristics from `conversation_logger.py` (30% reuse). Reuse FastAPI routes from `conversation_api.py` (80% reuse) | P2 |
| **P4: GDS Algorithms** | 5 days | PageRank, Louvain, betweenness, link prediction, FastRP, drift detection. Scheduled runners. Per-human named projections. | Greenfield — no existing GDS code | P2, P3 |
| **P5: Context Assembly** | 5 days | Unified graph-guided retrieval (single-transaction Cypher combining topology + vector), token budgeting, prompt formatting. Replaces `conversation_search.py` keyword search. | Reuse relevance scoring formula from `conversation_search.py` (40% reuse). Port filter logic to Cypher WHERE clauses | P4 |
| **P6: LLM Engagement** | 3 days | Assessment prompt, DeepSeek/Ollama model routing, few-shot calibration examples, learning loop (decision logging on Message nodes, outcome inference). | Greenfield — no existing engagement code | P5 |
| **P7: Privacy + Commands** | 4 days | Signal commands (/privacy, /mydata, /forget, /consent) via `profile_handler.py` adaptation. Deletion cascades. PII scrubbing pipeline. Fernet field encryption for Message.content. `@requires_consent` decorator. | Adapt `conversation_privacy.py` audit logging (60% reuse). Adapt `profile_handler.py` command parsing (80% reuse). Extend existing consent categories | P1, P3 |
| **P8: Migration** | 3 days | Parse existing JSONL/JSON per phone number, create Human + Identifier nodes (migrating from HumanProfile), detect historical threads, batch embeddings, build initial Topic graph, run initial GDS. | Reuse phone normalization from `human_profile_memory.py`. Parse existing `~/.openclaw/agents/main/memory/humans/index/*.json` files | P3, P4 |
| **P9: Frontend** | 8 days | Add "Humans" tab + "Conversations" sub-view to Kurultai dashboard (Express + vanilla JS). API endpoints: `/api/humans`, `/api/conversations/:human_id`, `/api/conversations/search`. Consent management widget. Privacy enforcement. | Extend existing Kurultai dashboard patterns (kanban tab structure, Neo4j query layer, auth). Zero existing conversation UI. | P5, P7 |
| **P10: Eval Harness** | 3 days | Eval framework for all 8 metrics. Automated adversarial identity isolation tests. Weekly context relevance sampling. | Greenfield | P5, P6 |

**Total: ~42 developer-days across 11 phases** (added P0 prerequisites, P9 frontend, split from original 34.5 + 8 frontend days)

### Critical Path

P0 → P1 → P2 → P3 → P4 → P5 → P6/P7/P9 (parallel) → P8 → P10

### Dual-Write Migration Strategy

During P3, the ingestion pipeline writes to BOTH existing JSON files AND new Neo4j nodes. This provides:
- **Zero-downtime cutover:** Old consumers keep reading JSON until all are migrated
- **Rollback capability:** If Neo4j has issues, JSON files are intact
- **Data validation:** Compare JSON vs Neo4j to catch discrepancies
- **Cutover trigger:** When all API consumers read from Neo4j, disable JSON writes

### Prerequisites Checklist (P0)

- [ ] Neo4j server version >= 5.11 (vector index support)
- [ ] GDS plugin installed (`neo4j-graph-data-science-*.jar` in plugins dir)
- [ ] `RETURN gds.version()` succeeds
- [ ] Ollama has `nomic-embed-text` pulled (`ollama pull nomic-embed-text`)
- [ ] Neo4j password changed from default (per security audit)
- [ ] Bolt TLS enabled (`bolt+s://`)
- [ ] Field encryption key generated at `~/.openclaw/credentials/field_encryption.key`

---

## 13. Review History

### v1 Review (2026-03-19) — Score: 3.5/10

**Reviewers:** Architecture (architect-reviewer), Data Science (data-scientist), Graph Schema (general-purpose)

**Key findings:**
- Regex-based engagement intelligence scored 3/10 ("a toy")
- Neo4j used as a document store, not a graph engine
- No evaluation framework (blocking at any serious lab)
- No privacy/consent model
- Over-engineered for 20 humans while under-engineering what matters
- Feature weights (0.35, 0.20...) were "vibes-based" with no empirical justification
- Learning loop statistically underpowered (6 false negatives per 30 days insufficient for per-human estimation)
- Threshold convergence math was broken (3x penalty converges to fn/fp = 1/3, not 1/5 as targeted)

**Actions taken in v2:**
- Replaced regex engagement with LLM assessment
- Restructured Neo4j to use GDS algorithms (7 algorithms, all justified)
- Moved message content to Postgres + pgvector
- Added comprehensive eval framework (8 metrics with targets)
- Added full privacy/consent model with Signal commands
- Decoupled Human identity from Signal identifiers
- Added social graph for mentioned/non-interacting humans

### v2.2 Codebase Audit (2026-03-19) — Implementation Readiness

**Reviewers:** Conversation/profile auditor (Explore), Neo4j/task auditor (Explore), Frontend auditor (Explore)

**Overall compatibility:** ~25% reuse, ~25% adapt, ~50% new code. No blockers.

**Key findings:**
- Neo4j infrastructure is production-ready (v2 fencing, connection pool, schema management). All new nodes are purely additive — zero breaking changes to Task/Agent/Event
- Neo4j driver is v6.1.0 (Python), connection factory supports custom driver instances (needed for IsolatedNeo4jClient)
- GDS library is NOT installed — must install before P4. No vector indexes exist yet
- Current Human identity is phone-based (`HumanProfile.human_id = "+19194133445"`). Migration to UUID + Identifier nodes is non-destructive
- Existing `conversation_logger.py` thread detection heuristics (2h gap, cosine <0.35) are sound and portable to Neo4j
- Task system's CAS fencing and BECAME_TASK integration path is clean
- Kurultai dashboard has ZERO conversation/human UI — frontend is longest pole (~8 dev-days)
- Parse platform conversations page is a stub — not priority for v2.2
- Existing `conversation_api.py` FastAPI routes (80% reusable), `conversation_privacy.py` audit logging (60% reusable)
- Entire engagement intelligence layer is greenfield

**Actions taken in v2.2:**
- Added P0 prerequisites phase (GDS install, Ollama pull, TLS, encryption key)
- Added P9 frontend phase (8 days for Kurultai dashboard Humans + Conversations tabs)
- Added dual-write migration strategy for safe cutover
- Updated all phases with "Reuse from Existing" column showing specific files and percentages
- Added prerequisites checklist
- Updated Appendix A with full file audit map
- Added Appendix D with existing Neo4j infrastructure details
- Total adjusted from 34.5 to 42 dev-days (added frontend + prerequisites)

### v2.1 Revision (2026-03-19) — Unified to Neo4j-Only

**Change:** Eliminated Postgres as a second database. All data (messages, embeddings, action items, engagement decisions) now lives in Neo4j alongside the graph topology.

**Rationale:**
- Operational simplicity: one database, one query language, one backup strategy, one failure mode
- Unified queries: graph-guided context retrieval becomes a single Cypher transaction instead of Neo4j → app → Postgres → merge
- The pre-filtering tradeoff (Neo4j vector search does global→filter vs pgvector's pre-filter) is acceptable at current scale (<1000 messages, ~20 humans) via over-fetching
- Escape hatch preserved: if pre-filtering becomes a bottleneck at 1M+ messages, extract Message nodes to Postgres + pgvector without changing the graph schema

**Impact:** Saved ~2 dev-days (eliminated Postgres schema phase and cross-DB integration). Reduced operational complexity. Simplified deployment.

**Open questions for next review:**
- Is nomic-embed-text the right model for short informal multilingual messages? (Need offline eval)
- Should GDS projections be pre-computed on a schedule or computed on-demand?
- What's the right confidence threshold for automatic entity resolution merges?
- How to handle group Signal chats (multiple humans in one thread)?
- Should inferences be visible to the human they're about? (Transparency vs uncanny valley)

---

## Appendix A: Key File Locations

### Design Documents
| File | Purpose |
|---|---|
| `~/.openclaw/agents/main/docs/plans/KUBLAI_CONVERSATIONAL_MEMORY_v2.md` | This document |
| `~/.openclaw/agents/main/docs/NEO4J_CONVERSATION_CONTEXT_DESIGN.md` | v1 design (superseded) |
| `~/.openclaw/agents/main/docs/engagement-assessment-design.md` | LLM engagement detail (supplementary) |
| `~/.openclaw/agents/main/docs/PRIVACY_IDENTITY_ISOLATION_DESIGN.md` | Privacy/security detail (supplementary) |

### Existing Code (Audit Compatibility)
| File | v2.2 Action | Reuse % |
|---|---|---|
| `~/.openclaw/agents/main/scripts/neo4j_task_tracker.py` | REUSE — connection factory, singleton pool, health checks | 90% |
| `~/.openclaw/agents/main/scripts/neo4j_v2_core.py` | REUSE — TaskStore CAS fencing, claim/complete primitives | 90% |
| `~/.openclaw/agents/main/scripts/neo4j_v2_schema.py` | EXTEND — add new constraints, indexes, vector indexes | 50% |
| `~/.openclaw/agents/main/scripts/neo4j_human_profile.py` | EXPAND — keep HumanProfile, add Human/Identifier schema | 60% |
| `~/.openclaw/agents/main/scripts/conversation_logger.py` | REPLACE — file→Neo4j rewrite. Reuse thread heuristics, topic seeds | 30% |
| `~/.openclaw/agents/main/scripts/conversation_search.py` | REPLACE — keyword→graph-guided. Reuse relevance formula | 40% |
| `~/.openclaw/agents/main/scripts/conversation_api.py` | ADAPT — FastAPI routes stable, add consent + IsolatedNeo4jClient | 80% |
| `~/.openclaw/agents/main/scripts/profile_handler.py` | ADAPT — command parsing stable, add cascade consent + /mydata | 80% |
| `~/.openclaw/agents/main/scripts/conversation_privacy.py` | ADAPT — audit logging good, add PII scrub + field encryption | 60% |
| `~/.openclaw/agents/main/scripts/human_profile_memory.py` | REPLACE — file-based→Neo4j. Reuse phone normalization only | 10% |

### Infrastructure
| File | Purpose |
|---|---|
| `~/.openclaw/credentials/neo4j.env` | Neo4j connection config (`bolt://localhost:7687`) |
| `~/.openclaw/credentials/field_encryption.key` | Fernet key for Message.content encryption (to be created) |
| `~/.openclaw/agents/main/memory/humans/index/*.json` | Existing conversation data (migration source) |
| `~/.openclaw/agents/main/memory/humans/*.md` | Existing narrative profiles (migration source) |
| `~/.openclaw/tasks/task-ledger.jsonl` | Task ledger (existing, compatible) |

### Frontend
| File | Purpose |
|---|---|
| `~/.openclaw/apps/the-kurultai/` | Kurultai dashboard (Express + vanilla JS, port 18790) |
| `~/.openclaw/apps/the-kurultai/neo4j.js` | Neo4j driver singleton for dashboard (Node.js) |
| `~/projects/parse-github/src/app/conversations/` | Parse conversations page (stub only, not priority) |

## Appendix B: Cost Analysis

| Component | Cost/Unit | Daily (200 msgs) | Monthly |
|---|---|---|---|
| LLM Engagement (DeepSeek) | $0.0005/decision | $0.10 | $2.94 |
| LLM Topic Extraction (DeepSeek) | $0.001/message | $0.20 | $5.88 |
| Local Embeddings (Ollama) | $0 | $0 | $0 |
| Neo4j (local, single instance) | $0 | $0 | $0 |
| **Total** | | **$0.30/day** | **~$8.82/month** |

## Appendix C: Neo4j-Only Tradeoffs

| Concern | Mitigation | Revisit When |
|---|---|---|
| Vector pre-filtering | Over-fetch (top-50 global → filter to human) | Hit rate drops below 80% |
| Schema migrations | Cypher scripts, no Prisma-style tooling | If team grows beyond 1-2 developers |
| JSONB-style flexibility | Neo4j node properties are schema-free (like JSONB) | N/A — already flexible |
| Backup maturity | `neo4j-admin dump` + JSONL fallback writes | If backup restore takes >5 min |
| Connection pooling | Neo4j driver handles this natively | If concurrent query contention appears |
| Message volume scaling | At current rate (~50K msgs/year), fine for years | If approaching 500K total messages |

## Appendix D: Existing Neo4j Infrastructure (from Audit)

### Connection Factory
- **Driver:** neo4j Python driver v6.1.0
- **Pattern:** Singleton with refcount pooling (`get_driver()` / `close_driver()`)
- **Pool:** max_connection_pool_size=30, acquisition_timeout=15s
- **Credentials:** `~/.openclaw/credentials/neo4j.env` (bolt://localhost:7687)
- **Fallback:** `safe_get_driver()` returns None when Neo4j unavailable — graceful degradation

### Existing Schema (Coexists with v2.2 Additions)
- **Constraints (2):** `task_id_unique`, `agent_name_unique`
- **Indexes (7):** v2_task_status_agent, v2_task_lease, v2_task_claim_composite, v2_task_orphan_composite, v2_agent_heartbeat + implicit PK indexes
- **Node types:** Task (60+ properties), Agent, TaskOutput, FailureReport, Event
- **Relationships:** ASSIGNED_TO, SPAWNED, HAS_OUTPUT, HAS_FAILURE, EXECUTED, RETRIED

### Task Lifecycle (Compatible with BECAME_TASK)
```
PENDING → WORKING → COMPLETED (requires TaskOutput + no blocking children)
                  → FAILED (permanent or retries exhausted)
                  → ORPHANED (lease expired → auto-recover to PENDING)
```
- CAS fencing via `claim_epoch` prevents double-claim
- `lease_expires_at` + orphan recovery watchdog
- Events written to `task-ledger.jsonl` with `executor: "claude-code"` field

### Integration Point: ActionItem → Task
- Current: Action items exist only in conversation JSON metadata
- v2.2: Create `:ActionItem` nodes in Neo4j, link to Message via `HAS_ACTION`
- When action is formalized: `(ActionItem)-[:BECAME_TASK]->(Task)` using existing `TaskStore.create_task()`
- Enables conversation archaeology: `MATCH (m:Message)-[:HAS_ACTION]->(ai)-[:BECAME_TASK]->(t:Task)`

## Appendix E: Frontend Requirements (from Audit)

### Kurultai Dashboard Changes (P9)

**Current state:** 5 tabs (Kanban, Calendar, Reflections, Sessions, Settings). Zero conversation UI.

**Required additions:**

1. **"Humans" tab** — List + detail view
   - List: HumanProfile nodes with displayName, source, confidence, lastContact
   - Detail: communication_style, topic graph summary, consent status, privacy level
   - Filter by: interaction class (DIRECT/MENTIONED/IMPORTED), status (ACTIVE/INACTIVE)

2. **"Conversations" sub-view** (under Humans detail)
   - Message feed per Human (content, direction, timestamp, sentiment badges)
   - Thread grouping with summaries and status (ACTIVE/DORMANT/ARCHIVED)
   - Inline topic tags on messages
   - Full-text + semantic search

3. **Consent management widget** (in Human detail or Settings)
   - Checkbox grid: Human × ConsentCategory
   - Show granted_at/revoked_at timestamps
   - Cascade warnings on parent revocation

4. **Privacy enforcement**
   - Privacy badge on every Human profile
   - Hide cross-human data based on privacy_level

**API endpoints to add:**
- `GET /api/humans` — list, filter, paginate
- `GET /api/humans/:id` — full profile + consent + recent threads
- `GET /api/conversations/:human_id` — messages in threads
- `GET /api/conversations/search?q=...` — full-text + semantic search
- `POST /api/humans/:id/consent` — toggle consent categories

### Parse Platform (Deferred)
Parse conversations page (`~/projects/parse-github/src/app/conversations/`) is a UI stub with empty data arrays. Not required for v2.2 — focus on Kurultai dashboard first. Can integrate later via Neo4j API bridge.
