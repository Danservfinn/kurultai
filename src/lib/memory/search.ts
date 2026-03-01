/**
 * Unified Search API for Kurultai Memory
 * 
 * Single search interface across all memory types:
 * - Neo4j (graph)
 * - Memory files (vector/keyword)
 * - Shared context (keyword)
 * 
 * Inspired by Cognee's unified search.
 * 
 * @module @kurultai/memory/search
 */

import { neo4j } from '@/lib/neo4j'
import { extractEntities } from './entity-extractor'

// Search result types
export type SearchResultType =
  | 'neo4j_node'
  | 'neo4j_relationship'
  | 'memory_file'
  | 'shared_context'

export interface SearchResult {
  type: SearchResultType
  content: string
  source: string
  relevance: number
  metadata?: Record<string, string>
}

export interface SearchOptions {
  // Limit results
  limit?: number
  
  // Filter by type
  types?: SearchResultType[]
  
  // Filter by date range
  startDate?: Date
  endDate?: Date
  
  // Minimum relevance score
  minRelevance?: number
  
  // Include weighted results
  useWeights?: boolean
}

const DEFAULT_OPTIONS: SearchOptions = {
  limit: 20,
  types: ['neo4j_node', 'neo4j_relationship', 'memory_file', 'shared_context'],
  minRelevance: 0.5,
  useWeights: true
}

/**
 * Unified search across all memory types
 */
export async function kurultaiSearch(
  query: string,
  options: SearchOptions = DEFAULT_OPTIONS
): Promise<SearchResult[]> {
  const opts = { ...DEFAULT_OPTIONS, ...options }
  const results: SearchResult[] = []
  
  // Search Neo4j (graph)
  if (opts.types?.includes('neo4j_node') || opts.types?.includes('neo4j_relationship')) {
    const neo4jResults = await searchNeo4j(query, opts)
    results.push(...neo4jResults)
  }
  
  // Search memory files (keyword + entity)
  if (opts.types?.includes('memory_file')) {
    const memoryResults = await searchMemoryFiles(query, opts)
    results.push(...memoryResults)
  }
  
  // Search shared context (keyword)
  if (opts.types?.includes('shared_context')) {
    const contextResults = await searchSharedContext(query, opts)
    results.push(...contextResults)
  }
  
  // Sort by relevance
  results.sort((a, b) => b.relevance - a.relevance)
  
  // Apply limit
  return results.slice(0, opts.limit)
}

/**
 * Search Neo4j graph
 */
async function searchNeo4j(query: string, options: SearchOptions): Promise<SearchResult[]> {
  const results: SearchResult[] = []
  
  // Extract entities from query for better matching
  const { entities } = await extractEntities(query)
  const entityNames = entities.map(e => e.name)
  
  // Search nodes by content
  const nodeQuery = `
    MATCH (n)
    WHERE 
      n.name CONTAINS $query OR
      n.description CONTAINS $query OR
      n.content CONTAINS $query OR
      n.id IN $entityNames
    RETURN 
      labels(n)[0] as type,
      n.name as name,
      n.description as content,
      COALESCE(n.weight, 1) as weight,
      COALESCE(n.last_accessed, n.created_at) as last_accessed
    ORDER BY 
      ${options.useWeights ? 'weight DESC,' : ''}
      last_accessed DESC
    LIMIT $limit
  `
  
  try {
    const nodeResults = await neo4j.query(nodeQuery, {
      query,
      entityNames,
      limit: options.limit
    })
    
    for (const record of nodeResults.records) {
      results.push({
        type: 'neo4j_node',
        content: record.get('content'),
        source: `Neo4j:${record.get('type')}:${record.get('name')}`,
        relevance: calculateRelevance(query, record.get('content')),
        metadata: {
          nodeType: record.get('type'),
          nodeName: record.get('name'),
          weight: record.get('weight')
        }
      })
    }
  } catch (error) {
    console.error('Neo4j node search failed:', error)
  }
  
  // Search relationships
  if (options.types?.includes('neo4j_relationship')) {
    const relQuery = `
      MATCH ()-[r]->()
      WHERE type(r) CONTAINS $query
      RETURN 
        type(r) as type,
        COALESCE(r.weight, 1) as weight,
        COALESCE(r.last_accessed, datetime()) as last_accessed
      ORDER BY 
        ${options.useWeights ? 'weight DESC,' : ''}
        last_accessed DESC
      LIMIT $limit
    `
    
    try {
      const relResults = await neo4j.query(relQuery, { query, limit: options.limit })
      
      for (const record of relResults.records) {
        results.push({
          type: 'neo4j_relationship',
          content: record.get('type'),
          source: `Neo4j:Relationship:${record.get('type')}`,
          relevance: 0.8,
          metadata: {
            relationshipType: record.get('type'),
            weight: record.get('weight')
          }
        })
      }
    } catch (error) {
      console.error('Neo4j relationship search failed:', error)
    }
  }
  
  return results
}

/**
 * Search memory files
 */
async function searchMemoryFiles(query: string, options: SearchOptions): Promise<SearchResult[]> {
  const fs = await import('fs/promises')
  const path = await import('path')
  const results: SearchResult[] = []
  
  const memoryDir = '/Users/kublai/.openclaw/agents/main/memory'
  
  try {
    const files = await fs.readdir(memoryDir)
    const mdFiles = files.filter(f => f.endsWith('.md'))
    
    for (const file of mdFiles) {
      const filePath = path.join(memoryDir, file)
      const content = await fs.readFile(filePath, 'utf-8')
      
      // Check if query matches
      const relevance = calculateRelevance(query, content)
      
      if (relevance >= (options.minRelevance || 0.5)) {
        // Extract matching snippet
        const snippet = extractSnippet(content, query, 200)
        
        results.push({
          type: 'memory_file',
          content: snippet,
          source: `Memory:${file}`,
          relevance,
          metadata: {
            fileName: file,
            filePath
          }
        })
      }
    }
  } catch (error) {
    console.error('Memory file search failed:', error)
  }
  
  return results
}

/**
 * Search shared context files
 */
async function searchSharedContext(query: string, options: SearchOptions): Promise<SearchResult[]> {
  const fs = await import('fs/promises')
  const path = await import('path')
  const results: SearchResult[] = []
  
  const contextDir = '/Users/kublai/.openclaw/agents/main/shared-context'
  
  try {
    const files = await fs.readdir(contextDir)
    const mdFiles = files.filter(f => f.endsWith('.md'))
    
    for (const file of mdFiles) {
      const filePath = path.join(contextDir, file)
      const content = await fs.readFile(filePath, 'utf-8')
      
      // Check if query matches
      const relevance = calculateRelevance(query, content)
      
      if (relevance >= (options.minRelevance || 0.5)) {
        // Extract matching snippet
        const snippet = extractSnippet(content, query, 200)
        
        results.push({
          type: 'shared_context',
          content: snippet,
          source: `SharedContext:${file}`,
          relevance,
          metadata: {
            fileName: file,
            filePath
          }
        })
      }
    }
  } catch (error) {
    console.error('Shared context search failed:', error)
  }
  
  return results
}

/**
 * Calculate relevance score (simple keyword matching)
 */
function calculateRelevance(query: string, content: string): number {
  const queryLower = query.toLowerCase()
  const contentLower = content.toLowerCase()
  
  // Exact match
  if (contentLower.includes(queryLower)) {
    return 1.0
  }
  
  // Word overlap
  const queryWords = queryLower.split(/\s+/).filter(w => w.length > 2)
  const contentWords = contentLower.split(/\s+/)
  
  let matches = 0
  for (const word of queryWords) {
    if (contentWords.some(cw => cw.includes(word))) {
      matches++
    }
  }
  
  return matches / queryWords.length
}

/**
 * Extract snippet around query match
 */
function extractSnippet(content: string, query: string, maxLength: number): string {
  const index = content.toLowerCase().indexOf(query.toLowerCase())
  
  if (index === -1) {
    return content.slice(0, maxLength) + '...'
  }
  
  const start = Math.max(0, index - 50)
  const end = Math.min(content.length, index + query.length + 50)
  
  return (start > 0 ? '...' : '') +
    content.slice(start, end) +
    (end < content.length ? '...' : '')
}

/**
 * Increment edge weight when search result is clicked
 */
export async function incrementSearchResultWeight(source: string): Promise<void> {
  // Parse source to get node/relationship info
  const parts = source.split(':')
  
  if (parts[0] === 'Neo4j' && parts.length >= 3) {
    const [, type, name] = parts
    
    try {
      await neo4j.query(`
        MATCH (n)
        WHERE labels(n)[0] = $type AND n.name = $name
        SET n.weight = COALESCE(n.weight, 1) + 1,
            n.last_accessed = datetime()
      `, { type, name })
    } catch (error) {
      console.error('Failed to increment weight:', error)
    }
  }
}
