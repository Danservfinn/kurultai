/**
 * Vector Index Migration
 *
 * Creates vector indexes for semantic search across the Kurultai system.
 * These indexes enable efficient similarity search on embeddings using cosine similarity.
 *
 * Index Configuration:
 * - Dimensions: 384 (standard for sentence-transformers 'all-MiniLM-L6-v2')
 * - Similarity Function: cosine
 * - Index Type: vector (Neo4j 5.x+)
 *
 * Indexed Properties:
 * - Belief.belief_embedding - For belief system semantic search
 * - MemoryEntry.memory_entry_embedding - For memory recall
 * - Research.research_embedding - For research content similarity
 */

// ============================================================================
// Belief Vector Index - For belief system semantic search
// ============================================================================
CREATE VECTOR INDEX belief_embedding_index IF NOT EXISTS
FOR (b:Belief)
ON (b.belief_embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }
};

// ============================================================================
// MemoryEntry Vector Index - For memory semantic search
// ============================================================================
CREATE VECTOR INDEX memory_entry_embedding_index IF NOT EXISTS
FOR (m:MemoryEntry)
ON (m.memory_entry_embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }
};

// ============================================================================
// Research Vector Index - For research content similarity
// ============================================================================
CREATE VECTOR INDEX research_embedding_index IF NOT EXISTS
FOR (r:Research)
ON (r.research_embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }
};

// ============================================================================
// Task Vector Index - For task similarity search (optional)
// ============================================================================
CREATE VECTOR INDEX task_embedding_index IF NOT EXISTS
FOR (t:Task)
ON (t.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine'
    }
};

// ============================================================================
// Constraints for nodes with embeddings
// ============================================================================
CREATE CONSTRAINT belief_id IF NOT EXISTS FOR (b:Belief) REQUIRE b.id IS UNIQUE;
CREATE CONSTRAINT memory_entry_id IF NOT EXISTS FOR (m:MemoryEntry) REQUIRE m.id IS UNIQUE;

// ============================================================================
// Indexes for efficient metadata queries
// ============================================================================
CREATE INDEX belief_agent IF NOT EXISTS FOR (b:Belief) ON (b.agent);
CREATE INDEX belief_created_at IF NOT EXISTS FOR (b:Belief) ON (b.created_at);
CREATE INDEX memory_entry_agent IF NOT EXISTS FOR (m:MemoryEntry) ON (m.agent);
CREATE INDEX memory_entry_created_at IF NOT EXISTS FOR (m:MemoryEntry) ON (m.created_at);
CREATE INDEX research_topic IF NOT EXISTS FOR (r:Research) ON (r.topic);
CREATE INDEX research_agent IF NOT EXISTS FOR (r:Research) ON (r.agent);

// ============================================================================
// Wait for indexes to be online
// ============================================================================
CALL db.awaitIndexes();

// ============================================================================
// Verification query (run manually to verify indexes)
// ============================================================================
// SHOW INDEXES WHERE type = 'VECTOR'
// YIELD name, type, entityType, labelsOrTypes, properties, options
// RETURN name, type, entityType, labelsOrTypes, properties,
//        options.indexConfig.`vector.dimensions` as dimensions,
//        options.indexConfig.`vector.similarity_function` as similarity_function;
