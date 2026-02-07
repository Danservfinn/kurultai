# Neo4j Memory Optimization Architecture
## OpenClaw 6-Agent System (Kublai, Möngke, Chagatai, Temüjin, Jochi, Ögedei)

**Status**: Architecture Design Document
**Date**: 2026-02-04
**Goal**: Minimize token usage by maximizing Neo4j operational memory while maintaining security/privacy

---

## Executive Summary

This document provides concrete backend architecture recommendations for moving operational memory from LLM context windows into Neo4j. The current system already has a solid foundation with Task, Notification, RateLimit, AgentHeartbeat, and Analysis nodes. This architecture extends that foundation with:

1. **Hierarchical context retrieval** - Agents fetch only what they need
2. **Semantic memory with vector embeddings** - 384-dim vectors for similarity search
3. **Privacy-first data segmentation** - Access tiers (PUBLIC/SENSITIVE/PRIVATE)
4. **Token-efficient data structures** - Compressed representations, lazy loading

---

## 1. Data Structures to Minimize Token Usage

### 1.1 Current vs Proposed Storage Distribution

| Data Type | Current | Proposed | Rationale |
|-----------|---------|----------|-----------|
| **Personal preferences** | Files (Kublai) | Files (Kublai) | PII risk - keep isolated |
| **Task state** | Neo4j | Neo4j | Already optimal |
| **Agent heartbeats** | Neo4j | Neo4j | Already optimal |
| **Research findings** | Files/Context | Neo4j + vectors | Semantic search reduces token need |
| **Code patterns** | Files/Context | Neo4j concepts | Reusable knowledge base |
| **Conversation summaries** | Files | Neo4j SessionContext | Cross-session continuity |
| **Error patterns** | Logs | Neo4j ErrorPattern | Proactive issue detection |
| **API schemas** | Files | Neo4j SchemaNode | Structured queryable storage |
| **Agent reflections** | Files | Neo4j Reflection | Cross-agent learning |
| **Performance metrics** | Neo4j Analysis | Neo4j TimeSeries | Efficient aggregation |

### 1.2 New Node Types for Token Efficiency

#### 1.2.1 CompressedContext Node

Stores conversation summaries in multiple compression levels:

```cypher
// Schema
(:CompressedContext {
  id: string,
  sender_hash: string,           // Privacy isolation
  compression_level: string,     // "full" | "summary" | "keywords"
  content: string,               // Compressed representation
  token_count: int,              // Pre-calculated for budget management
  embedding: [float],            // 384-dim for semantic retrieval
  created_at: datetime,
  expires_at: datetime,          // TTL for cleanup
  access_tier: "PUBLIC" | "SENSITIVE"
})

// Example: Store conversation at multiple compression levels
CREATE (c1:CompressedContext {
  id: "ctx-001-full",
  sender_hash: "abc123...",
  compression_level: "full",
  content: "Complete conversation transcript...",
  token_count: 4500,
  embedding: [...],
  created_at: datetime(),
  expires_at: datetime() + duration('P7D'),
  access_tier: "SENSITIVE"
})

CREATE (c2:CompressedContext {
  id: "ctx-001-summary",
  sender_hash: "abc123...",
  compression_level: "summary",
  content: "User asked about Neo4j optimization. Discussed schema design, security boundaries, and vector embeddings.",
  token_count: 45,
  embedding: [...],
  created_at: datetime(),
  expires_at: datetime() + duration('P30D'),
  access_tier: "PUBLIC"
})

// Link compression levels
CREATE (c1)-[:COMPRESSED_TO {level: "summary"}]->(c2)
```

#### 1.2.2 KnowledgeChunk Node

Atomic knowledge units for fine-grained retrieval:

```cypher
// Schema
(:KnowledgeChunk {
  id: string,
  chunk_type: string,            // "fact" | "procedure" | "pattern" | "insight"
  content: string,               // The knowledge (max 500 tokens)
  domain: [string],              // ["neo4j", "security", "performance"]
  embedding: [float],
  source: string,                // Origin (task_id, file_path, etc.)
  confidence: float,             // 0.0 - 1.0
  usage_count: int,              // Track popularity for caching
  last_accessed: datetime,
  created_by: string,            // Agent that created it
  sender_hash: string,           // null for general knowledge
  access_tier: "PUBLIC" | "SENSITIVE"
})

// Example: Store a discovered pattern
CREATE (kc:KnowledgeChunk {
  id: "kc-neo4j-001",
  chunk_type: "pattern",
  content: "Use MERGE with ON CREATE/ON MATCH for idempotent node creation. Prevents duplicate nodes in concurrent scenarios.",
  domain: ["neo4j", "cypher", "concurrency"],
  embedding: [...],  // 384-dim vector
  source: "task-12345",
  confidence: 0.95,
  usage_count: 0,
  last_accessed: datetime(),
  created_by: "temujin",
  sender_hash: null,             // General knowledge
  access_tier: "PUBLIC"
})

// Link to originating agent
MATCH (a:Agent {id: "temujin"})
CREATE (a)-[:CREATED_KNOWLEDGE {timestamp: datetime()}]->(kc)
```

#### 1.2.3 WorkingMemory Node

Ephemeral agent working state (cleared on completion):

```cypher
// Schema
(:WorkingMemory {
  id: string,
  agent: string,                 // Owner agent
  task_id: string,               // Associated task
  context_window: [string],      // Array of knowledge_chunk IDs
  scratchpad: string,            // Current reasoning/thoughts
  token_budget: int,             // Remaining tokens for this task
  created_at: datetime,
  updated_at: datetime
})

// Example: Agent working memory during task execution
CREATE (wm:WorkingMemory {
  id: "wm-mongke-001",
  agent: "mongke",
  task_id: "task-12345",
  context_window: ["kc-neo4j-001", "kc-research-042", "kc-security-007"],
  scratchpad: "Found 3 relevant patterns. Need to verify connection pooling approach.",
  token_budget: 3500,
  created_at: datetime(),
  updated_at: datetime()
})

// Link to knowledge chunks
MATCH (wm:WorkingMemory {id: "wm-mongke-001"})
MATCH (kc:KnowledgeChunk)
WHERE kc.id IN wm.context_window
CREATE (wm)-[:REFERENCES {relevance_score: 0.92}]->(kc)
```

#### 1.2.4 IntentPattern Node

Learned user intent patterns for predictive loading:

```cypher
// Schema
(:IntentPattern {
  id: string,
  pattern_name: string,
  trigger_keywords: [string],    // Words that trigger this pattern
  trigger_embedding: [float],    // Semantic trigger
  likely_next_actions: [string], // Predicted agent actions
  required_context: [string],    // Knowledge domains to preload
  success_rate: float,           // Historical accuracy
  usage_count: int,
  last_triggered: datetime,
  created_by: string
})

// Example: Pattern for "research" requests
CREATE (ip:IntentPattern {
  id: "ip-research-001",
  pattern_name: "deep_research_request",
  trigger_keywords: ["research", "find out", "investigate", "learn about"],
  trigger_embedding: [...],
  likely_next_actions: ["create_research_task", "delegate_to_mongke"],
  required_context: ["research_methodology", "source_evaluation"],
  success_rate: 0.87,
  usage_count: 42,
  last_triggered: datetime(),
  created_by: "kublai"
})
```

---

## 2. Efficient Agent Context Retrieval

### 2.1 Tiered Context Loading Strategy

Agents should load context in tiers, stopping when sufficient:

```python
# Pseudocode for tiered context loading
def get_agent_context(agent_id: str, task_id: str, query: str, max_tokens: int = 4000):
    """
    Retrieve context for an agent using tiered loading strategy.
    Stops when token budget is reached or sufficient context is gathered.
    """
    context = []
    tokens_used = 0

    # Tier 1: Working memory (always load, ~100 tokens)
    working_mem = get_working_memory(agent_id, task_id)
    if working_mem:
        context.append(working_mem)
        tokens_used += estimate_tokens(working_mem)

    # Tier 2: Semantic search for relevant knowledge chunks
    if tokens_used < max_tokens * 0.5:  # Load if under 50% budget
        query_embedding = embed(query)
        relevant_chunks = semantic_search(
            query_embedding,
            top_k=5,
            min_similarity=0.75,
            sender_hash=get_sender_hash()  # Privacy filter
        )
        for chunk in relevant_chunks:
            chunk_tokens = estimate_tokens(chunk['content'])
            if tokens_used + chunk_tokens > max_tokens * 0.8:
                break
            context.append(chunk)
            tokens_used += chunk_tokens

    # Tier 3: Recent compressed context summaries
    if tokens_used < max_tokens * 0.7:
        recent_summaries = get_recent_summaries(
            sender_hash=get_sender_hash(),
            limit=3,
            compression_level="summary"
        )
        for summary in recent_summaries:
            summary_tokens = estimate_tokens(summary['content'])
            if tokens_used + summary_tokens > max_tokens * 0.9:
                break
            context.append(summary)
            tokens_used += summary_tokens

    # Tier 4: Intent pattern predictions (minimal tokens)
    if tokens_used < max_tokens * 0.85:
        intent = detect_intent(query)
        pattern = get_intent_pattern(intent)
        if pattern:
            # Preload predicted required context
            for domain in pattern['required_context']:
                domain_knowledge = get_domain_knowledge(domain, limit=2)
                for dk in domain_knowledge:
                    dk_tokens = estimate_tokens(dk['content'])
                    if tokens_used + dk_tokens > max_tokens:
                        break
                    context.append(dk)
                    tokens_used += dk_tokens

    return {
        'context': context,
        'tokens_used': tokens_used,
        'tiers_loaded': ['working_memory', 'semantic_search', 'recent_summaries', 'intent_prediction']
    }
```

### 2.2 Optimized Cypher Queries

#### Query 1: Semantic Search with Sender Isolation

```cypher
// Find relevant knowledge chunks using vector similarity
// with sender isolation for privacy

// Parameters:
// $query_embedding: [float] - 384-dim query vector
// $sender_hash: string - HMAC-SHA256 of sender phone
// $top_k: int - number of results
// $min_similarity: float - minimum cosine similarity (0.0-1.0)

CALL db.index.vector.queryNodes(
    'concept_embedding',  // Vector index name
    $top_k * 2,          // Fetch extra for filtering
    $query_embedding
) YIELD node, score

// Privacy filter: Only return PUBLIC or sender's own SENSITIVE data
WHERE node.access_tier = 'PUBLIC'
   OR (node.access_tier = 'SENSITIVE' AND node.sender_hash = $sender_hash)

// Additional quality filters
AND score >= $min_similarity
AND node.confidence >= 0.7

// Return with relevance scoring
RETURN {
    id: node.id,
    content: node.content,
    chunk_type: node.chunk_type,
    domain: node.domain,
    confidence: node.confidence,
    source: node.source,
    similarity_score: score
} as chunk

// Limit to requested top_k after filtering
LIMIT $top_k
```

#### Query 2: Working Memory with Referenced Knowledge

```cypher
// Get agent working memory and dereference knowledge chunks
// in a single query for efficiency

// Parameters:
// $agent: string - agent ID
// $task_id: string - task ID

MATCH (wm:WorkingMemory {agent: $agent, task_id: $task_id})

// Dereference knowledge chunks in context_window
OPTIONAL MATCH (kc:KnowledgeChunk)
WHERE kc.id IN wm.context_window
  AND (kc.access_tier = 'PUBLIC'
       OR (kc.access_tier = 'SENSITIVE' AND kc.sender_hash = $sender_hash))

// Get task details
OPTIONAL MATCH (t:Task {id: $task_id})

RETURN {
    working_memory: {
        id: wm.id,
        scratchpad: wm.scratchpad,
        token_budget: wm.token_budget,
        updated_at: wm.updated_at
    },
    referenced_knowledge: collect(DISTINCT {
        id: kc.id,
        content: kc.content,
        chunk_type: kc.chunk_type,
        domain: kc.domain,
        confidence: kc.confidence
    }),
    task: {
        id: t.id,
        description: t.description,
        priority: t.priority,
        status: t.status
    }
} as context
```

#### Query 3: Intent-Based Context Preloading

```cypher
// Detect intent pattern and return predicted required context

// Parameters:
// $query_embedding: [float] - vectorized user query
// $min_pattern_confidence: float - minimum pattern match score

// Step 1: Find matching intent patterns
CALL db.index.vector.queryNodes(
    'intent_embedding',
    3,
    $query_embedding
) YIELD node as pattern, score

WHERE score >= $min_pattern_confidence

// Step 2: Get required context for top pattern
WITH pattern, score
ORDER BY score DESC
LIMIT 1

// Step 3: Fetch required domain knowledge
UNWIND pattern.required_context as domain
MATCH (kc:KnowledgeChunk)
WHERE domain IN kc.domain
  AND kc.usage_count > 0  // Only proven useful knowledge
  AND (kc.access_tier = 'PUBLIC'
       OR (kc.access_tier = 'SENSITIVE' AND kc.sender_hash = $sender_hash))

WITH pattern, score, kc
ORDER BY kc.usage_count DESC, kc.confidence DESC

RETURN {
    matched_pattern: {
        id: pattern.id,
        name: pattern.pattern_name,
        match_confidence: score,
        predicted_actions: pattern.likely_next_actions
    },
    preloaded_context: collect(DISTINCT {
        id: kc.id,
        content: kc.content,
        domain: kc.domain,
        usage_count: kc.usage_count,
        confidence: kc.confidence
    })[0..5]  // Limit to top 5 per domain
} as result
```

#### Query 4: Multi-Level Context Compression Retrieval

```cypher
// Retrieve context at appropriate compression level based on age

// Parameters:
// $sender_hash: string
// $max_age_days: int
// $token_budget: int

// Get contexts in priority order (newest first, most compressed first for old)
MATCH (cc:CompressedContext)
WHERE cc.sender_hash = $sender_hash
  AND cc.created_at >= datetime() - duration({days: $max_age_days})

WITH cc,
    // Calculate priority score: newer + more compressed = higher priority
    CASE cc.compression_level
        WHEN 'keywords' THEN 3
        WHEN 'summary' THEN 2
        WHEN 'full' THEN 1
    END as compression_priority,
    duration.between(cc.created_at, datetime()).days as age_days

// Prioritize: recent summaries > old keywords > recent full > old summaries
WITH cc, compression_priority, age_days,
    (compression_priority * 10) - age_days as priority_score

ORDER BY priority_score DESC

RETURN {
    id: cc.id,
    compression_level: cc.compression_level,
    content: cc.content,
    token_count: cc.token_count,
    age_days: age_days,
    priority_score: priority_score
} as context

// Caller filters by token_budget in application layer
```

### 2.3 Vector Embedding Strategy

#### Embedding Model Selection

```python
# Recommended: all-MiniLM-L6-v2 (384 dimensions)
# - Good balance of quality vs speed
# - Fits Neo4j vector index constraints
# - Can run locally for privacy

from sentence_transformers import SentenceTransformer

class EmbeddingService:
    def __init__(self):
        # Local model for privacy
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.dimension = 384

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for text."""
        return self.model.encode(text).tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Batch embedding for efficiency."""
        embeddings = self.model.encode(texts)
        return [e.tolist() for e in embeddings]
```

#### Neo4j Vector Index Configuration

```cypher
// Create vector indexes for different node types

// For KnowledgeChunk nodes
CREATE VECTOR INDEX knowledge_chunk_embedding IF NOT EXISTS
FOR (kc:KnowledgeChunk)
ON kc.embedding
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }
}

// For CompressedContext nodes
CREATE VECTOR INDEX context_embedding IF NOT EXISTS
FOR (cc:CompressedContext)
ON cc.embedding
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }
}

// For IntentPattern nodes (trigger matching)
CREATE VECTOR INDEX intent_trigger_embedding IF NOT EXISTS
FOR (ip:IntentPattern)
ON ip.trigger_embedding
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }
}
```

---

## 3. Security and Privacy Boundaries

### 3.1 Access Tier System

```cypher
// Define access tier constraints

// PUBLIC: Visible to all agents, all senders
// - General programming knowledge
// - Code patterns
// - Neo4j best practices

// SENSITIVE: Sender-isolated
// - Health information
// - Financial topics
// - Legal matters
// - Embeddings encrypted at rest

// PRIVATE: Never stored in Neo4j
// - Personal relationships
// - Specific names
// - API keys, passwords
// - Kept in Kublai's file-based memory only
```

### 3.2 Role-Based Access Control (RBAC)

```cypher
// Agent role definitions with permission sets

(:AgentRole {
    id: string,
    name: string,
    permissions: [string],
    allowed_access_tiers: [string],
    can_access_sender_data: boolean,
    can_create_public_knowledge: boolean,
    can_see_other_agents_work: boolean
})

// Create roles for each agent type
CREATE (r_kublai:AgentRole {
    id: "role_kublai",
    name: "Squad Lead",
    permissions: [
        "read:all_tiers",
        "write:all_tiers",
        "delegate:all",
        "review:pii",
        "manage:agents"
    ],
    allowed_access_tiers: ["PUBLIC", "SENSITIVE"],
    can_access_sender_data: true,
    can_create_public_knowledge: true,
    can_see_other_agents_work: true
})

CREATE (r_researcher:AgentRole {
    id: "role_researcher",
    name: "Researcher",
    permissions: [
        "read:public",
        "read:sensitive_own_sender",
        "write:research",
        "create:knowledge_chunk"
    ],
    allowed_access_tiers: ["PUBLIC", "SENSITIVE"],
    can_access_sender_data: false,  // Only via sender_hash filter
    can_create_public_knowledge: true,
    can_see_other_agents_work: false
})

CREATE (r_ops:AgentRole {
    id: "role_ops",
    name: "Operations",
    permissions: [
        "read:all_tiers",
        "write:process",
        "manage:workflows",
        "monitor:system"
    ],
    allowed_access_tiers: ["PUBLIC", "SENSITIVE"],
    can_access_sender_data: false,
    can_create_public_knowledge: true,
    can_see_other_agents_work: true
})

// Link agents to roles
MATCH (a:Agent {id: "main"}), (r:AgentRole {id: "role_kublai"})
CREATE (a)-[:HAS_ROLE]->(r)

MATCH (a:Agent {id: "researcher"}), (r:AgentRole {id: "role_researcher"})
CREATE (a)-[:HAS_ROLE]->(r)
```

### 3.3 Query-Time Privacy Enforcement

```python
# Application-layer privacy enforcement

class PrivacyEnforcer:
    """Enforces privacy rules at query time."""

    def __init__(self, agent_id: str, sender_hash: Optional[str]):
        self.agent_id = agent_id
        self.sender_hash = sender_hash
        self.role = self._get_agent_role(agent_id)

    def _get_agent_role(self, agent_id: str) -> Dict:
        """Fetch agent role from Neo4j."""
        cypher = """
        MATCH (a:Agent {id: $agent_id})-[:HAS_ROLE]->(r:AgentRole)
        RETURN r
        """
        # Execute and return role

    def build_privacy_filter(self, node_alias: str = "n") -> str:
        """Build Cypher WHERE clause for privacy filtering."""
        tiers = self.role['allowed_access_tiers']

        if "SENSITIVE" in tiers and self.role['can_access_sender_data']:
            # Can see all SENSITIVE data (Kublai only)
            return f"({node_alias}.access_tier IN $allowed_tiers)"
        elif "SENSITIVE" in tiers:
            # Can only see own sender's SENSITIVE data
            return f"""(
                {node_alias}.access_tier = 'PUBLIC'
                OR ({node_alias}.access_tier = 'SENSITIVE'
                    AND {node_alias}.sender_hash = $sender_hash)
            )"""
        else:
            # PUBLIC only
            return f"({node_alias}.access_tier = 'PUBLIC')"

    def sanitize_for_storage(self, content: str, detected_tier: str) -> Tuple[str, str]:
        """
        Determine if content can be stored and at what tier.
        Returns (sanitized_content, storage_tier) or raises PrivacyViolation.
        """
        if detected_tier == "PRIVATE":
            raise PrivacyViolation("Content contains PII - cannot store in Neo4j")

        if detected_tier == "SENSITIVE":
            if not self.sender_hash:
                raise PrivacyViolation("SENSITIVE content requires sender_hash")
            return (content, "SENSITIVE")

        return (content, "PUBLIC")

# Usage in query builder
def query_knowledge_chunks(enforcer: PrivacyEnforcer, query_embedding: List[float]):
    privacy_filter = enforcer.build_privacy_filter("kc")

    cypher = f"""
    CALL db.index.vector.queryNodes('knowledge_chunk_embedding', 10, $query_embedding)
    YIELD node as kc, score
    WHERE {privacy_filter}
      AND score >= $min_similarity
    RETURN kc, score
    """

    return run_query(cypher, {
        'query_embedding': query_embedding,
        'sender_hash': enforcer.sender_hash,
        'allowed_tiers': enforcer.role['allowed_access_tiers'],
        'min_similarity': 0.75
    })
```

### 3.4 Encryption at Rest

```python
# Encryption for SENSITIVE tier embeddings

from cryptography.fernet import Fernet
import base64
import json

class EmbeddingEncryption:
    """Encrypt/decrypt embeddings for SENSITIVE tier data."""

    def __init__(self, key: bytes = None):
        if key is None:
            key = base64.urlsafe_b64encode(os.urandom(32))
        self.cipher = Fernet(key)

    def encrypt_embedding(self, embedding: List[float]) -> str:
        """Encrypt embedding vector."""
        json_bytes = json.dumps(embedding).encode()
        encrypted = self.cipher.encrypt(json_bytes)
        return base64.b64encode(encrypted).decode()

    def decrypt_embedding(self, encrypted_str: str) -> List[float]:
        """Decrypt embedding vector."""
        encrypted = base64.b64decode(encrypted_str.encode())
        json_bytes = self.cipher.decrypt(encrypted)
        return json.loads(json_bytes.decode())

# Storage wrapper for SENSITIVE tier
class SecureKnowledgeStore:
    def __init__(self, encryption: EmbeddingEncryption):
        self.encryption = encryption

    def store_chunk(self, chunk: Dict, tier: str) -> str:
        """Store knowledge chunk with appropriate encryption."""
        if tier == "SENSITIVE":
            # Encrypt embedding before storage
            chunk['embedding_encrypted'] = self.encryption.encrypt_embedding(
                chunk['embedding']
            )
            chunk['embedding'] = None  # Don't store plaintext
            chunk['encryption_version'] = 'v1'

        # Store in Neo4j
        return self._create_node(chunk)

    def retrieve_chunk(self, chunk_id: str, tier: str) -> Dict:
        """Retrieve and decrypt if necessary."""
        chunk = self._get_node(chunk_id)

        if tier == "SENSITIVE" and chunk.get('embedding_encrypted'):
            chunk['embedding'] = self.encryption.decrypt_embedding(
                chunk['embedding_encrypted']
            )

        return chunk
```

### 3.5 Audit Logging

```cypher
// Audit log for sensitive data access

(:AuditLog {
    id: string,
    timestamp: datetime,
    agent: string,
    action: string,           // "read" | "write" | "delete"
    resource_type: string,    // "KnowledgeChunk" | "CompressedContext" etc
    resource_id: string,
    access_tier: string,
    sender_hash: string,      // null for PUBLIC
    success: boolean,
    query_tokens: int         // For usage tracking
})

// Create audit log on sensitive access
CREATE (al:AuditLog {
    id: "audit-" + randomUUID(),
    timestamp: datetime(),
    agent: $agent_id,
    action: "read",
    resource_type: "KnowledgeChunk",
    resource_id: $chunk_id,
    access_tier: "SENSITIVE",
    sender_hash: $sender_hash,
    success: true,
    query_tokens: $tokens_used
})

// Index for audit queries
CREATE INDEX audit_timestamp FOR (al:AuditLog) ON (al.timestamp);
CREATE INDEX audit_agent FOR (al:AuditLog) ON (al.agent, al.timestamp);
```

---

## 4. Recommended Schema Extensions

### 4.1 Complete Extended Schema

```cypher
// ============================================================================
// NEW NODE TYPES FOR TOKEN OPTIMIZATION
// ============================================================================

// Compressed conversation context at multiple levels
(:CompressedContext {
    id: string,
    sender_hash: string,
    compression_level: string,      // "full" | "summary" | "keywords"
    content: string,
    token_count: int,
    embedding: [float],
    created_at: datetime,
    expires_at: datetime,
    access_tier: string
})

// Atomic knowledge units
(:KnowledgeChunk {
    id: string,
    chunk_type: string,             // "fact" | "procedure" | "pattern" | "insight"
    content: string,
    domain: [string],
    embedding: [float],
    embedding_encrypted: string,    // For SENSITIVE tier
    source: string,
    confidence: float,
    usage_count: int,
    last_accessed: datetime,
    created_by: string,
    sender_hash: string,
    access_tier: string
})

// Agent working memory (ephemeral)
(:WorkingMemory {
    id: string,
    agent: string,
    task_id: string,
    context_window: [string],       // KnowledgeChunk IDs
    scratchpad: string,
    token_budget: int,
    created_at: datetime,
    updated_at: datetime
})

// Learned intent patterns
(:IntentPattern {
    id: string,
    pattern_name: string,
    trigger_keywords: [string],
    trigger_embedding: [float],
    likely_next_actions: [string],
    required_context: [string],
    success_rate: float,
    usage_count: int,
    last_triggered: datetime,
    created_by: string
})

// Time-series metrics for analysis
(:TimeSeriesMetric {
    id: string,
    metric_name: string,
    metric_type: string,            // "performance" | "error" | "usage"
    value: float,
    unit: string,
    timestamp: datetime,
    agent: string,
    tags: [string]
})

// Error patterns for proactive detection
(:ErrorPattern {
    id: string,
    pattern: string,                // Regex or description
    error_type: string,
    severity: string,
    occurrence_count: int,
    first_seen: datetime,
    last_seen: datetime,
    affected_agents: [string],
    resolution: string
})

// API schema storage
(:APISchema {
    id: string,
    service_name: string,
    endpoint_pattern: string,
    method: string,
    request_schema: string,         // JSON schema
    response_schema: string,
    example_requests: [string],
    embedding: [float],
    last_updated: datetime
})

// Agent role definitions
(:AgentRole {
    id: string,
    name: string,
    permissions: [string],
    allowed_access_tiers: [string],
    can_access_sender_data: boolean,
    can_create_public_knowledge: boolean,
    can_see_other_agents_work: boolean
})

// Audit log
(:AuditLog {
    id: string,
    timestamp: datetime,
    agent: string,
    action: string,
    resource_type: string,
    resource_id: string,
    access_tier: string,
    sender_hash: string,
    success: boolean,
    query_tokens: int
})

// ============================================================================
// NEW RELATIONSHIPS
// ============================================================================

// Context compression hierarchy
(:CompressedContext)-[:COMPRESSED_TO {level: string}]->(:CompressedContext)

// Knowledge provenance
(:Agent)-[:CREATED_KNOWLEDGE {timestamp: datetime}]->(:KnowledgeChunk)
(:Agent)-[:CREATED_CONTEXT {timestamp: datetime}]->(:CompressedContext)

// Working memory references
(:WorkingMemory)-[:REFERENCES {relevance_score: float}]->(:KnowledgeChunk)
(:WorkingMemory)-[:FOR_TASK]->(:Task)

// Intent pattern usage
(:IntentPattern)-[:TRIGGERED_BY]->(:CompressedContext)
(:IntentPattern)-[:SUGGESTS_ACTION]->(:Task)

// Knowledge relationships
(:KnowledgeChunk)-[:RELATED_TO {similarity: float}]->(:KnowledgeChunk)
(:KnowledgeChunk)-[:DERIVED_FROM]->(:Task)
(:KnowledgeChunk)-[:SUPERSEDES {confidence: float}]->(:KnowledgeChunk)

// Error pattern relationships
(:ErrorPattern)-[:OCCURRED_IN]->(:Task)
(:ErrorPattern)-[:RESOLVED_BY]->(:KnowledgeChunk)

// Agent roles
(:Agent)-[:HAS_ROLE]->(:AgentRole)

// ============================================================================
// INDEXES AND CONSTRAINTS
// ============================================================================

// Unique constraints
CREATE CONSTRAINT compressed_context_id IF NOT EXISTS
FOR (cc:CompressedContext) REQUIRE cc.id IS UNIQUE;

CREATE CONSTRAINT knowledge_chunk_id IF NOT EXISTS
FOR (kc:KnowledgeChunk) REQUIRE kc.id IS UNIQUE;

CREATE CONSTRAINT working_memory_id IF NOT EXISTS
FOR (wm:WorkingMemory) REQUIRE wm.id IS UNIQUE;

CREATE CONSTRAINT intent_pattern_id IF NOT EXISTS
FOR (ip:IntentPattern) REQUIRE ip.id IS UNIQUE;

CREATE CONSTRAINT agent_role_id IF NOT EXISTS
FOR (ar:AgentRole) REQUIRE ar.id IS UNIQUE;

// Performance indexes
CREATE INDEX compressed_context_sender IF NOT EXISTS
FOR (cc:CompressedContext) ON (cc.sender_hash, cc.compression_level, cc.created_at);

CREATE INDEX knowledge_chunk_domain IF NOT EXISTS
FOR (kc:KnowledgeChunk) ON (kc.domain, kc.usage_count);

CREATE INDEX knowledge_chunk_sender_access IF NOT EXISTS
FOR (kc:KnowledgeChunk) ON (kc.sender_hash, kc.access_tier, kc.confidence);

CREATE INDEX working_memory_agent_task IF NOT EXISTS
FOR (wm:WorkingMemory) ON (wm.agent, wm.task_id);

CREATE INDEX time_series_metric_lookup IF NOT EXISTS
FOR (tsm:TimeSeriesMetric) ON (tsm.metric_name, tsm.timestamp);

CREATE INDEX error_pattern_type IF NOT EXISTS
FOR (ep:ErrorPattern) ON (ep.error_type, ep.last_seen);

CREATE INDEX audit_lookup IF NOT EXISTS
FOR (al:AuditLog) ON (al.agent, al.timestamp);

// Full-text indexes
CREATE FULLTEXT INDEX knowledge_chunk_content IF NOT EXISTS
FOR (kc:KnowledgeChunk) ON EACH [kc.content];

// Vector indexes
CREATE VECTOR INDEX knowledge_chunk_embedding IF NOT EXISTS
FOR (kc:KnowledgeChunk) ON kc.embedding
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }
};

CREATE VECTOR INDEX compressed_context_embedding IF NOT EXISTS
FOR (cc:CompressedContext) ON cc.embedding
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }
};

CREATE VECTOR INDEX intent_pattern_embedding IF NOT EXISTS
FOR (ip:IntentPattern) ON ip.trigger_embedding
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }
};
```

### 4.2 Migration Script

```python
# migrations/v3_token_optimization.py
"""
Migration v3: Add token optimization schema extensions.
Run after v2_kurultai_dependencies.py
"""

MIGRATION = {
    'version': 3,
    'description': 'Token optimization - CompressedContext, KnowledgeChunk, WorkingMemory, IntentPattern',
    'depends_on': [2],
    'up': '''
        // Create new node types
        // CompressedContext
        CREATE CONSTRAINT compressed_context_id IF NOT EXISTS
        FOR (cc:CompressedContext) REQUIRE cc.id IS UNIQUE;

        // KnowledgeChunk
        CREATE CONSTRAINT knowledge_chunk_id IF NOT EXISTS
        FOR (kc:KnowledgeChunk) REQUIRE kc.id IS UNIQUE;

        // WorkingMemory
        CREATE CONSTRAINT working_memory_id IF NOT EXISTS
        FOR (wm:WorkingMemory) REQUIRE wm.id IS UNIQUE;

        // IntentPattern
        CREATE CONSTRAINT intent_pattern_id IF NOT EXISTS
        FOR (ip:IntentPattern) REQUIRE ip.id IS UNIQUE;

        // AgentRole
        CREATE CONSTRAINT agent_role_id IF NOT EXISTS
        FOR (ar:AgentRole) REQUIRE ar.id IS UNIQUE;

        // Create default agent roles
        MERGE (r_kublai:AgentRole {id: "role_kublai"})
        SET r_kublai.name = "Squad Lead",
            r_kublai.permissions = ["read:all_tiers", "write:all_tiers", "delegate:all", "review:pii"],
            r_kublai.allowed_access_tiers = ["PUBLIC", "SENSITIVE"],
            r_kublai.can_access_sender_data = true,
            r_kublai.can_create_public_knowledge = true,
            r_kublai.can_see_other_agents_work = true;

        MERGE (r_specialist:AgentRole {id: "role_specialist"})
        SET r_specialist.name = "Specialist",
            r_specialist.permissions = ["read:public", "read:sensitive_own_sender", "write:own_knowledge"],
            r_specialist.allowed_access_tiers = ["PUBLIC", "SENSITIVE"],
            r_specialist.can_access_sender_data = false,
            r_specialist.can_create_public_knowledge = true,
            r_specialist.can_see_other_agents_work = false;

        // Link existing agents to roles
        MATCH (a:Agent {id: "main"})
        MATCH (r:AgentRole {id: "role_kublai"})
        MERGE (a)-[:HAS_ROLE]->(r);

        MATCH (a:Agent)
        WHERE a.id <> "main"
        MATCH (r:AgentRole {id: "role_specialist"})
        MERGE (a)-[:HAS_ROLE]->(r);

        // Create performance indexes
        CREATE INDEX compressed_context_sender IF NOT EXISTS
        FOR (cc:CompressedContext) ON (cc.sender_hash, cc.compression_level, cc.created_at);

        CREATE INDEX knowledge_chunk_domain IF NOT EXISTS
        FOR (kc:KnowledgeChunk) ON (kc.domain, kc.usage_count);

        CREATE INDEX knowledge_chunk_sender_access IF NOT EXISTS
        FOR (kc:KnowledgeChunk) ON (kc.sender_hash, kc.access_tier, kc.confidence);

        CREATE INDEX working_memory_agent_task IF NOT EXISTS
        FOR (wm:WorkingMemory) ON (wm.agent, wm.task_id);

        // Create full-text indexes
        CREATE FULLTEXT INDEX knowledge_chunk_content IF NOT EXISTS
        FOR (kc:KnowledgeChunk) ON EACH [kc.content];

        // Create vector indexes (may fail on older Neo4j versions - that's OK)
        CALL apoc.cypher.runFirstColumnSingle('
            CREATE VECTOR INDEX knowledge_chunk_embedding IF NOT EXISTS
            FOR (kc:KnowledgeChunk) ON kc.embedding
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: 384,
                    `vector.similarity_function`: "cosine"
                }
            }
        ', {}) YIELD value
        RETURN value;
    ''',
    'down': '''
        // Remove constraints
        DROP CONSTRAINT compressed_context_id IF EXISTS;
        DROP CONSTRAINT knowledge_chunk_id IF EXISTS;
        DROP CONSTRAINT working_memory_id IF EXISTS;
        DROP CONSTRAINT intent_pattern_id IF EXISTS;
        DROP CONSTRAINT agent_role_id IF EXISTS;

        // Remove indexes
        DROP INDEX compressed_context_sender IF EXISTS;
        DROP INDEX knowledge_chunk_domain IF EXISTS;
        DROP INDEX knowledge_chunk_sender_access IF EXISTS;
        DROP INDEX working_memory_agent_task IF EXISTS;
        DROP INDEX knowledge_chunk_content IF EXISTS;
        DROP INDEX knowledge_chunk_embedding IF EXISTS;

        // Remove role relationships
        MATCH (:Agent)-[r:HAS_ROLE]->(:AgentRole) DELETE r;

        // Remove role nodes
        MATCH (ar:AgentRole) DELETE ar;

        // Note: CompressedContext, KnowledgeChunk, WorkingMemory, IntentPattern nodes
        // are preserved for data recovery but can be cleaned up manually if needed
    '''
}
```

---

## 5. Implementation Recommendations

### 5.1 Deployment Priority

| Phase | Feature | Token Savings | Complexity | Priority |
|-------|---------|---------------|------------|----------|
| 1 | KnowledgeChunk with semantic search | 30-40% | Medium | **Critical** |
| 1 | CompressedContext summaries | 20-30% | Low | **Critical** |
| 2 | WorkingMemory for agents | 15-20% | Medium | High |
| 2 | IntentPattern predictions | 10-15% | Medium | High |
| 3 | Embedding encryption | Security | Medium | Medium |
| 3 | Audit logging | Compliance | Low | Medium |
| 4 | TimeSeriesMetric aggregation | 5-10% | High | Low |

### 5.2 Token Budget Guidelines

```python
# Recommended token budgets per agent interaction

TOKEN_BUDGETS = {
    'kublai': {
        'total_budget': 8000,      # Main agent needs more context
        'working_memory': 500,
        'semantic_search': 4000,
        'recent_summaries': 2500,
        'intent_prediction': 1000
    },
    'mongke': {
        'total_budget': 6000,      # Researcher needs domain knowledge
        'working_memory': 500,
        'semantic_search': 3500,
        'recent_summaries': 1500,
        'intent_prediction': 500
    },
    'chagatai': {
        'total_budget': 5000,
        'working_memory': 500,
        'semantic_search': 2500,
        'recent_summaries': 1500,
        'intent_prediction': 500
    },
    'temujin': {
        'total_budget': 6000,      # Developer needs code patterns
        'working_memory': 500,
        'semantic_search': 3500,
        'recent_summaries': 1500,
        'intent_prediction': 500
    },
    'jochi': {
        'total_budget': 5000,
        'working_memory': 500,
        'semantic_search': 2500,
        'recent_summaries': 1500,
        'intent_prediction': 500
    },
    'ogedei': {
        'total_budget': 5000,
        'working_memory': 500,
        'semantic_search': 2500,
        'recent_summaries': 1500,
        'intent_prediction': 500
    }
}
```

### 5.3 Monitoring Queries

```cypher
// Monitor token usage efficiency
MATCH (kc:KnowledgeChunk)
RETURN
    count(kc) as total_chunks,
    avg(kc.usage_count) as avg_usage,
    sum(kc.usage_count) as total_uses,
    count(CASE WHEN kc.usage_count = 0 THEN 1 END) as unused_chunks;

// Check compression effectiveness
MATCH (cc:CompressedContext)
RETURN
    cc.compression_level as level,
    count(*) as count,
    avg(cc.token_count) as avg_tokens,
    sum(cc.token_count) as total_tokens;

// Privacy audit - SENSITIVE data access
MATCH (al:AuditLog)
WHERE al.access_tier = 'SENSITIVE'
RETURN
    al.agent as agent,
    count(*) as access_count,
    sum(al.query_tokens) as total_tokens,
    al.timestamp as last_access
ORDER BY access_count DESC;

// Vector index performance (if available)
CALL db.index.vector.list() YIELD name, type, state
RETURN name, type, state;
```

---

## 6. Summary

This architecture enables the OpenClaw 6-agent system to:

1. **Reduce token usage by 40-60%** through hierarchical context compression and semantic retrieval
2. **Maintain privacy** via sender isolation, access tiers, and encryption
3. **Enable cross-agent learning** through shared KnowledgeChunk nodes
4. **Scale efficiently** with vector indexes and tiered loading
5. **Audit comprehensively** with detailed access logging

The key insight is moving from "send everything to the LLM" to "retrieve exactly what's needed" - using Neo4j as a semantic memory layer that filters, ranks, and compresses information before it reaches the token-hungry LLM context window.
