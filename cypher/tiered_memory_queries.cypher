// =============================================================================
// Tiered Memory Retrieval Queries for OpenClaw MemoryManager
// =============================================================================
//
// These queries support the 4-tier memory system:
// - Hot: In-memory, eagerly loaded (~1,600 tokens)
// - Warm: On-demand from Neo4j (~400 tokens)
// - Cold: On-demand with timeout (~200 tokens)
// - Archive: Query only, never loaded
//
// =============================================================================

// =============================================================================
// HOT TIER QUERIES - Eagerly Loaded
// =============================================================================

// Query: Load Hot Tier - Current Session Context
// Description: Load active session context for the agent
// Token Budget: ~400 tokens
// Called: On every initialization
MATCH (ctx:SessionContext {agent: $agent})
WHERE ctx.active = true
RETURN ctx.id as id,
       ctx.content as content,
       ctx.created_at as created_at,
       'session_context' as entry_type,
       $agent as agent,
       ctx.embedding as embedding
ORDER BY ctx.priority DESC, ctx.created_at DESC
LIMIT 10;

// Query: Load Hot Tier - Active Tasks
// Description: Load pending and in-progress tasks
// Token Budget: ~600 tokens
MATCH (t:Task)
WHERE (t.assigned_to = $agent OR t.delegated_by = $agent)
  AND t.status IN ['pending', 'in_progress']
RETURN t.id as id,
       t.description as content,
       t.created_at as created_at,
       'active_task' as entry_type,
       t.assigned_to as agent,
       t.priority as priority,
       t.status as status
ORDER BY CASE t.priority
    WHEN 'critical' THEN 4
    WHEN 'high' THEN 3
    WHEN 'normal' THEN 2
    WHEN 'low' THEN 1
    ELSE 0
END DESC, t.created_at ASC
LIMIT 15;

// Query: Load Hot Tier - Critical Notifications
// Description: Load unread critical notifications
// Token Budget: ~300 tokens
MATCH (n:Notification {agent: $agent, read: false})
WHERE n.type IN ['task_completed', 'task_failed', 'critical_alert', 'blocker']
RETURN n.id as id,
       n.summary as content,
       n.created_at as created_at,
       'notification' as entry_type,
       $agent as agent,
       n.type as notification_type
ORDER BY n.created_at DESC
LIMIT 10;

// Query: Load Hot Tier - High-Confidence Beliefs
// Description: Load active high-confidence beliefs
// Token Budget: ~300 tokens
MATCH (b:Belief)
WHERE (b.agent = $agent OR b.agent = 'shared')
  AND b.state = 'active'
  AND b.confidence >= 0.8
RETURN b.id as id,
       b.content as content,
       b.created_at as created_at,
       'belief' as entry_type,
       b.agent as agent,
       b.confidence as confidence,
       b.domain as domain
ORDER BY b.last_accessed DESC, b.confidence DESC
LIMIT 15;

// Combined Hot Tier Query (Single Round-Trip)
MATCH (ctx:SessionContext {agent: $agent})
WHERE ctx.active = true
WITH ctx
LIMIT 10
RETURN ctx.id as id, ctx.content as content, ctx.created_at as created_at,
       'session_context' as entry_type, $agent as agent

UNION

MATCH (t:Task)
WHERE (t.assigned_to = $agent OR t.delegated_by = $agent)
  AND t.status IN ['pending', 'in_progress']
WITH t
ORDER BY CASE t.priority
    WHEN 'critical' THEN 4
    WHEN 'high' THEN 3
    WHEN 'normal' THEN 2
    WHEN 'low' THEN 1
    ELSE 0
END DESC, t.created_at ASC
LIMIT 15
RETURN t.id as id, t.description as content, t.created_at as created_at,
       'active_task' as entry_type, t.assigned_to as agent

UNION

MATCH (n:Notification {agent: $agent, read: false})
WHERE n.type IN ['task_completed', 'task_failed', 'critical_alert', 'blocker']
WITH n
ORDER BY n.created_at DESC
LIMIT 10
RETURN n.id as id, n.summary as content, n.created_at as created_at,
       'notification' as entry_type, $agent as agent

UNION

MATCH (b:Belief)
WHERE (b.agent = $agent OR b.agent = 'shared')
  AND b.state = 'active'
  AND b.confidence >= 0.8
WITH b
ORDER BY b.last_accessed DESC, b.confidence DESC
LIMIT 15
RETURN b.id as id, b.content as content, b.created_at as created_at,
       'belief' as entry_type, b.agent as agent

ORDER BY created_at DESC
LIMIT 50;

// =============================================================================
// WARM TIER QUERIES - Lazy Loaded
// =============================================================================

// Query: Load Warm Tier - Recent Completed Tasks
// Description: Tasks completed in last 24 hours
// Token Budget: ~200 tokens
// Timeout: 2 seconds
MATCH (t:Task)
WHERE (t.assigned_to = $agent OR t.delegated_by = $agent)
  AND t.status = 'completed'
  AND t.completed_at >= datetime() - duration('P1D')
RETURN t.id as id,
       t.description + ' (Outcome: ' + t.outcome + ')' as content,
       t.completed_at as created_at,
       'completed_task' as entry_type,
       t.assigned_to as agent,
       t.quality_score as quality_score
ORDER BY t.completed_at DESC
LIMIT 10;

// Query: Load Warm Tier - Recent Notifications
// Description: All notifications from last 24 hours
// Token Budget: ~100 tokens
MATCH (n:Notification {agent: $agent})
WHERE n.created_at >= datetime() - duration('P1D')
RETURN n.id as id,
       n.summary as content,
       n.created_at as created_at,
       'notification' as entry_type,
       $agent as agent,
       n.read as is_read
ORDER BY n.created_at DESC
LIMIT 10;

// Query: Load Warm Tier - Medium-Confidence Beliefs
// Description: Active beliefs with confidence 0.5-0.8
// Token Budget: ~100 tokens
MATCH (b:Belief)
WHERE (b.agent = $agent OR b.agent = 'shared')
  AND b.state = 'active'
  AND b.confidence >= 0.5 AND b.confidence < 0.8
RETURN b.id as id,
       b.content as content,
       b.created_at as created_at,
       'belief' as entry_type,
       b.agent as agent,
       b.confidence as confidence
ORDER BY b.confidence DESC, b.last_accessed DESC
LIMIT 10;

// Combined Warm Tier Query (Single Round-Trip)
MATCH (t:Task)
WHERE (t.assigned_to = $agent OR t.delegated_by = $agent)
  AND t.status = 'completed'
  AND t.completed_at >= datetime() - duration('P1D')
WITH t
ORDER BY t.completed_at DESC
LIMIT 10
RETURN t.id as id,
       t.description + ' (Outcome: ' + t.outcome + ')' as content,
       t.completed_at as created_at,
       'completed_task' as entry_type,
       t.assigned_to as agent

UNION

MATCH (n:Notification {agent: $agent})
WHERE n.created_at >= datetime() - duration('P1D')
WITH n
ORDER BY n.created_at DESC
LIMIT 10
RETURN n.id as id, n.summary as content, n.created_at as created_at,
       'notification' as entry_type, $agent as agent

UNION

MATCH (b:Belief)
WHERE (b.agent = $agent OR b.agent = 'shared')
  AND b.state = 'active'
  AND b.confidence >= 0.5 AND b.confidence < 0.8
WITH b
ORDER BY b.confidence DESC, b.last_accessed DESC
LIMIT 10
RETURN b.id as id, b.content as content, b.created_at as created_at,
       'belief' as entry_type, b.agent as agent

ORDER BY created_at DESC
LIMIT 30;

// =============================================================================
// COLD TIER QUERIES - Timeout Protected
// =============================================================================

// Query: Load Cold Tier - Historical Tasks
// Description: Tasks completed 7-30 days ago
// Token Budget: ~100 tokens
// Timeout: 5 seconds
MATCH (t:Task)
WHERE (t.assigned_to = $agent OR t.delegated_by = $agent)
  AND t.status = 'completed'
  AND t.completed_at >= datetime() - duration('P7D')
  AND t.completed_at < datetime() - duration('P1D')
RETURN t.id as id,
       t.description as content,
       t.completed_at as created_at,
       'historical_task' as entry_type,
       t.assigned_to as agent
ORDER BY t.completed_at DESC
LIMIT 5;

// Query: Load Cold Tier - Archived Beliefs
// Description: Superseded or archived beliefs
// Token Budget: ~50 tokens
MATCH (b:Belief)
WHERE (b.agent = $agent OR b.agent = 'shared')
  AND b.state = 'archived'
RETURN b.id as id,
       b.content as content,
       b.created_at as created_at,
       'archived_belief' as entry_type,
       b.agent as agent,
       b.superseded_by as superseded_by
ORDER BY b.updated_at DESC
LIMIT 5;

// Query: Load Cold Tier - Recent Synthesis
// Description: Synthesis from other agents in last 7 days
// Token Budget: ~50 tokens
MATCH (s:Synthesis)
WHERE s.created_by <> $agent
  AND s.created_at >= datetime() - duration('P7D')
RETURN s.id as id,
       s.insight as content,
       s.created_at as created_at,
       'synthesis' as entry_type,
       s.created_by as agent,
       s.confidence as confidence
ORDER BY s.created_at DESC
LIMIT 5;

// Combined Cold Tier Query (Single Round-Trip)
MATCH (t:Task)
WHERE (t.assigned_to = $agent OR t.delegated_by = $agent)
  AND t.status = 'completed'
  AND t.completed_at >= datetime() - duration('P7D')
  AND t.completed_at < datetime() - duration('P1D')
WITH t
ORDER BY t.completed_at DESC
LIMIT 5
RETURN t.id as id, t.description as content, t.completed_at as created_at,
       'historical_task' as entry_type, t.assigned_to as agent

UNION

MATCH (b:Belief)
WHERE (b.agent = $agent OR b.agent = 'shared')
  AND b.state = 'archived'
WITH b
ORDER BY b.updated_at DESC
LIMIT 5
RETURN b.id as id, b.content as content, b.created_at as created_at,
       'archived_belief' as entry_type, b.agent as agent

UNION

MATCH (s:Synthesis)
WHERE s.created_by <> $agent
  AND s.created_at >= datetime() - duration('P7D')
WITH s
ORDER BY s.created_at DESC
LIMIT 5
RETURN s.id as id, s.insight as content, s.created_at as created_at,
       'synthesis' as entry_type, s.created_by as agent

ORDER BY created_at DESC
LIMIT 20;

// =============================================================================
// ARCHIVE TIER QUERIES - Query Only
// =============================================================================

// Query: Archive Search by Text
// Description: Full-text search across all knowledge nodes
// Timeout: 5 seconds (query-only, never cached)
CALL db.index.fulltext.queryNodes('knowledge_content', $query_text)
YIELD node, score
WHERE (node.agent = $agent OR node.agent = 'shared')
  AND node.created_at >= datetime() - duration('P' + $days + 'D')
RETURN node.id as id,
       node.content as content,
       node.created_at as created_at,
       labels(node)[0] as entry_type,
       node.agent as agent,
       score
ORDER BY score DESC
LIMIT $limit;

// Query: Archive Search by Type
// Description: Search specific node types with filters
MATCH (n)
WHERE ($node_type IS NULL OR labels(n)[0] = $node_type)
  AND (n.agent = $agent OR n.agent = 'shared')
  AND n.created_at >= datetime() - duration('P' + $days + 'D')
  AND ($query_text IS NULL OR n.content CONTAINS $query_text)
RETURN n.id as id,
       n.content as content,
       n.created_at as created_at,
       labels(n)[0] as entry_type,
       n.agent as agent
ORDER BY n.created_at DESC
LIMIT $limit;

// Query: Archive - Cross-Agent Knowledge Discovery
// Description: Find knowledge from other agents not yet seen
MATCH (me:Agent {name: $agent})
MATCH (other:Agent)-[:CREATED]->(k)
WHERE other.name <> $agent
  AND NOT (me)-[:ACCESSED]->(k)
  AND k.confidence > $min_confidence
  AND k.created_at >= datetime() - duration('P' + $days + 'D')
OPTIONAL MATCH (me)-[sub:SUBSCRIBES_TO]->(other)
WITH k, other, sub
WHERE sub IS NOT NULL
   OR EXISTS { MATCH (sk:SharedKnowledge {knowledge_id: k.id}) }
RETURN other.name as from_agent,
       labels(k)[0] as entry_type,
       k.id as id,
       k.content as content,
       k.created_at as created_at,
       k.confidence as confidence
ORDER BY k.created_at DESC
LIMIT $limit;

// Query: Archive - Related Knowledge Graph Traversal
// Description: Traverse graph to find related knowledge
MATCH (start)
WHERE start.id = $start_id
CALL apoc.path.subgraphNodes(start, {
    relationshipFilter: 'DISCOVERED|REFINED|SYNTHESIZES|EXPLAINS|VALIDATED|CHALLENGED|CONTRIBUTED_TO|PRODUCED|EVOLVED_INTO|SUPPORTS',
    labelFilter: 'Concept|Research|Content|Application|Synthesis|Belief',
    minLevel: 1,
    maxLevel: 3,
    limit: $limit
})
YIELD node
WHERE node.id <> $start_id
RETURN node.id as id,
       node.content as content,
       node.created_at as created_at,
       labels(node)[0] as entry_type,
       node.agent as agent
LIMIT $limit;

// =============================================================================
// MEMORY MANAGEMENT QUERIES
// =============================================================================

// Query: Persist Memory Entry
// Description: Store a new memory entry to Neo4j
CREATE (e:MemoryEntry {
    id: $id,
    content: $content,
    tier: $tier,
    token_count: $token_count,
    agent: $agent,
    entry_type: $entry_type,
    confidence: $confidence,
    created_at: $created_at,
    metadata: $metadata
})
RETURN e.id as id;

// Query: Update Belief Last Accessed
// Description: Track when beliefs are accessed
MATCH (b:Belief {id: $belief_id})
SET b.last_accessed = datetime(),
    b.access_count = coalesce(b.access_count, 0) + 1
RETURN b.id as id;

// Query: Get Memory Statistics
// Description: Get counts by tier for an agent
MATCH (n)
WHERE n.agent = $agent
RETURN labels(n)[0] as node_type,
       count(*) as count,
       sum(n.token_count) as total_tokens
ORDER BY count DESC;

// Query: Evict Old Entries
// Description: Mark old entries for eviction from hot tier
MATCH (e:MemoryEntry {agent: $agent, tier: 'hot'})
WHERE e.last_accessed < datetime() - duration('PT1H')
SET e.tier = 'warm'
RETURN count(e) as evicted_count;

// Query: Archive Old Entries
// Description: Move old entries to archive tier
MATCH (e:MemoryEntry {agent: $agent})
WHERE e.tier IN ['warm', 'cold']
  AND e.created_at < datetime() - duration('P30D')
SET e.tier = 'archive'
RETURN count(e) as archived_count;

// =============================================================================
// INDEXES FOR PERFORMANCE
// =============================================================================

// Index: Agent + Created At (for tier queries)
CREATE INDEX memory_agent_created IF NOT EXISTS
FOR (n:MemoryEntry|Task|Belief|Notification) ON (n.agent, n.created_at);

// Index: Tier + Agent (for eviction)
CREATE INDEX memory_tier_agent IF NOT EXISTS
FOR (n:MemoryEntry) ON (n.tier, n.agent);

// Index: Last Accessed (for LRU eviction)
CREATE INDEX memory_last_accessed IF NOT EXISTS
FOR (n:MemoryEntry|Belief) ON (n.last_accessed);

// Index: State + Confidence (for belief queries)
CREATE INDEX belief_state_confidence IF NOT EXISTS
FOR (b:Belief) ON (b.state, b.confidence);

// Full-Text Index (for archive search)
CREATE FULLTEXT INDEX knowledge_content IF NOT EXISTS
FOR (n:Research|Content|Concept|Belief|Analysis|Synthesis)
ON EACH [n.content, n.findings, n.description, n.insight];

// Vector Index (for semantic search)
CREATE VECTOR INDEX concept_embedding IF NOT EXISTS
FOR (c:Concept)
ON c.embedding OPTIONS {indexConfig: {
    `vector.dimensions`: 384,
    `vector.similarity_function`: 'cosine'
}};
