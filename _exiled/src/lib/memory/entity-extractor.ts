/**
 * Entity Extractor for Kurultai Memory
 * 
 * Auto-extract entities from memory files and create Neo4j nodes.
 * Inspired by Cognee's auto-entity extraction.
 * 
 * @module @kurultai/memory/entity-extractor
 */

import { z } from 'zod'
import { neo4j } from '@/lib/neo4j'

// Extracted entity types
export type EntityType =
  | 'Agent'
  | 'Task'
  | 'Goal'
  | 'Decision'
  | 'System'
  | 'File'
  | 'Person'

export interface ExtractedEntity {
  type: EntityType
  name: string
  description?: string
  metadata?: Record<string, string>
}

// Entity extraction result
export interface EntityExtractionResult {
  entities: ExtractedEntity[]
  relationships: EntityRelationship[]
}

export interface EntityRelationship {
  from: string
  to: string
  type: string
}

/**
 * Extract entities from memory content using LLM
 */
export async function extractEntities(content: string): Promise<EntityExtractionResult> {
  // Use LLM to extract entities
  // For now, use rule-based extraction (replace with LLM call)
  const entities = extractEntitiesRuleBased(content)
  const relationships = extractRelationships(entities, content)
  
  return { entities, relationships }
}

/**
 * Rule-based entity extraction (placeholder for LLM)
 */
function extractEntitiesRuleBased(content: string): ExtractedEntity[] {
  const entities: ExtractedEntity[] = []
  
  // Extract agent mentions
  const agentMentions = content.match(/\b(Kublai|Möngke|Chagatai|Temüjin|Jochi|Ögedei)\b/g)
  if (agentMentions) {
    for (const agent of new Set(agentMentions)) {
      entities.push({
        type: 'Agent',
        name: agent,
        description: `Agent ${agent} mentioned in memory`
      })
    }
  }
  
  // Extract task mentions
  const taskPatterns = [
    /task[:\s]+([a-zA-Z\s-]+)/gi,
    /implement[:\s]+([a-zA-Z\s-]+)/gi,
    /build[:\s]+([a-zA-Z\s-]+)/gi,
    /deploy[:\s]+([a-zA-Z\s-]+)/gi
  ]
  
  for (const pattern of taskPatterns) {
    const matches = content.match(pattern)
    if (matches) {
      for (const match of matches) {
        entities.push({
          type: 'Task',
          name: match.split(':')[1]?.trim() || match,
          description: `Task extracted from memory`
        })
      }
    }
  }
  
  // Extract system mentions
  const systemMentions = content.match(/\b(Parse|LLM Survivor|Stripe|Railway|Neo4j|OpenClaw)\b/g)
  if (systemMentions) {
    for (const system of new Set(systemMentions)) {
      entities.push({
        type: 'System',
        name: system,
        description: `System ${system} mentioned`
      })
    }
  }
  
  return entities
}

/**
 * Extract relationships between entities
 */
function extractRelationships(entities: ExtractedEntity[], content: string): EntityRelationship[] {
  const relationships: EntityRelationship[] = []
  
  // Agent → Task relationships
  const agents = entities.filter(e => e.type === 'Agent')
  const tasks = entities.filter(e => e.type === 'Task')
  
  for (const agent of agents) {
    for (const task of tasks) {
      // Check if agent is working on task
      if (content.includes(`${agent.name}`) && content.includes(`${task.name}`)) {
        relationships.push({
          from: agent.name,
          to: task.name,
          type: 'WORKING_ON'
        })
      }
    }
  }
  
  return relationships
}

/**
 * Create Neo4j nodes from extracted entities
 */
export async function createEntityNodes(entities: ExtractedEntity[]): Promise<number> {
  let created = 0
  
  for (const entity of entities) {
    try {
      // Check if node already exists
      const existing = await neo4j.query(`
        MATCH (n:${entity.type} {name: $name})
        RETURN n
      `, { name: entity.name })
      
      if (existing.records.length === 0) {
        // Create new node
        await neo4j.query(`
          CREATE (n:${entity.type} {
            name: $name,
            description: $description,
            created_at: datetime()
          })
        `, {
          name: entity.name,
          description: entity.description || ''
        })
        created++
      }
    } catch (error) {
      console.error(`Failed to create entity ${entity.name}:`, error)
    }
  }
  
  return created
}

/**
 * Create Neo4j relationships from extracted relationships
 */
export async function createEntityRelationships(relationships: EntityRelationship[]): Promise<number> {
  let created = 0
  
  for (const rel of relationships) {
    try {
      await neo4j.query(`
        MATCH (a), (b)
        WHERE a.name = $from AND b.name = $to
        MERGE (a)-[r:${rel.type}]->(b)
        SET r.created_at = datetime(),
            r.weight = 1
        RETURN r
      `, { from: rel.from, to: rel.to })
      created++
    } catch (error) {
      console.error(`Failed to create relationship ${rel.from}→${rel.to}:`, error)
    }
  }
  
  return created
}

/**
 * Process memory file and extract entities
 */
export async function processMemoryFile(
  filePath: string,
  content: string
): Promise<{ entities: number; relationships: number }> {
  // Extract entities
  const { entities, relationships } = await extractEntities(content)
  
  // Create Neo4j nodes
  const entitiesCreated = await createEntityNodes(entities)
  
  // Create Neo4j relationships
  const relationshipsCreated = await createEntityRelationships(relationships)
  
  // Log extraction
  console.log(`Extracted ${entitiesCreated} entities and ${relationshipsCreated} relationships from ${filePath}`)
  
  return {
    entities: entitiesCreated,
    relationships: relationshipsCreated
  }
}

/**
 * Batch process all memory files
 */
export async function processAllMemoryFiles(): Promise<{
  totalEntities: number
  totalRelationships: number
  filesProcessed: number
}> {
  const fs = await import('fs/promises')
  const path = await import('path')
  
  let totalEntities = 0
  let totalRelationships = 0
  let filesProcessed = 0
  
  // Get all memory files
  const memoryDir = '/Users/kublai/.openclaw/agents/main/memory'
  const files = await fs.readdir(memoryDir)
  
  for (const file of files.filter(f => f.endsWith('.md'))) {
    try {
      const filePath = path.join(memoryDir, file)
      const content = await fs.readFile(filePath, 'utf-8')
      
      const result = await processMemoryFile(filePath, content)
      
      totalEntities += result.entities
      totalRelationships += result.relationships
      filesProcessed++
    } catch (error) {
      console.error(`Failed to process ${file}:`, error)
    }
  }
  
  return {
    totalEntities,
    totalRelationships,
    filesProcessed
  }
}
