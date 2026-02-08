#!/usr/bin/env node
/**
 * Railway-deployable architecture sync script
 *
 * This script is designed to run within the Railway environment where
 * it has access to the private Neo4j instance.
 *
 * Usage: Deploy to Railway and run, or use as entrypoint for one-off job
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// Neo4j configuration from Railway environment
const NEO4J_URI = process.env.NEO4J_URI || 'bolt://neo4j.railway.internal:7687';
const NEO4J_USER = process.env.NEO4J_USER || 'neo4j';
const NEO4J_PASSWORD = process.env.NEO4J_PASSWORD || '';

/**
 * Parse markdown file into sections by H2 headers
 */
function parseArchitectureSections(markdown) {
  const lines = markdown.split('\n');
  const sections = [];
  let currentSection = null;
  let currentContent = [];
  let sectionOrder = 0;

  for (const line of lines) {
    const h2Match = line.match(/^##\s+(.+)$/);

    if (h2Match) {
      if (currentSection) {
        sections.push({
          ...currentSection,
          content: currentContent.join('\n').trim(),
          order: sectionOrder++
        });
      }

      currentSection = {
        title: h2Match[1].trim(),
        content: []
      };
      currentContent = [];
    } else if (currentSection) {
      currentContent.push(line);
    }
  }

  if (currentSection) {
    sections.push({
      ...currentSection,
      content: currentContent.join('\n').trim(),
      order: sectionOrder++
    });
  }

  return sections;
}

/**
 * Calculate checksum for content
 */
function calculateChecksum(content) {
  return crypto.createHash('sha256').update(content).digest('hex');
}

/**
 * Create full-text search index
 */
async function createSearchIndex(session) {
  await session.run(`
    CREATE FULLTEXT INDEX architecture_search_index
    IF NOT EXISTS
    FOR (n:ArchitectureSection)
    ON EACH [n.title, n.content]
    OPTIONS {
      indexConfig: {
        'fulltext.analyzer': 'standard'
      }
    }
  `);
}

/**
 * Sync sections to Neo4j
 */
async function syncSectionsToNeo4j(sections, commitHash) {
  const neo4j = require('neo4j-driver');
  const driver = neo4j.driver(
    NEO4J_URI,
    neo4j.auth.basic(NEO4J_USER, NEO4J_PASSWORD)
  );

  const session = driver.session();

  try {
    // Verify connection
    await driver.verifyConnectivity();
    console.log('[ARCH-sync] Connected to Neo4j');

    // Create full-text search index
    await createSearchIndex(session);
    console.log('[ARCH-sync] Full-text index ready');

    // Mark existing sections as potentially stale
    await session.run(`
      MATCH (s:ArchitectureSection)
      SET s._stale = true
    `);

    // Upsert each section
    for (const section of sections) {
      const checksum = calculateChecksum(section.content);
      const slug = section.title.toLowerCase()
        .replace(/[^\w\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .trim();

      const parentMatch = section.title.match(/^(.+?)\s*>\s*(.+)$/);
      let parentTitle = null;
      if (parentMatch) {
        parentTitle = parentMatch[1].trim();
      }

      await session.run(`
        MERGE (s:ArchitectureSection {slug: $slug})
        SET
          s.title = $title,
          s.content = $content,
          s.order = $order,
          s.checksum = $checksum,
          s.git_commit = $git_commit,
          s.updated_at = datetime(),
          s._stale = false,
          s.parent_section = $parent_section
      `, {
        slug,
        title: section.title,
        content: section.content,
        order: section.order,
        checksum,
        git_commit: commitHash,
        parent_section: parentTitle
      });

      console.log(`[ARCH-sync] Synced: ${section.title}`);
    }

    // Delete stale sections
    const deleteResult = await session.run(`
      MATCH (s:ArchitectureSection)
      WHERE s._stale = true
      DETACH DELETE s
      RETURN count(*) as deleted
    `);

    if (deleteResult.records.length > 0) {
      const deleted = deleteResult.records[0].get('deleted');
      if (deleted > 0) {
        console.log(`[ARCH-sync] Deleted ${deleted.toNumber()} stale sections`);
      }
    }

    // Also store as ArchitectureDocument for the Python script compatibility
    const archPath = path.join(process.cwd(), 'ARCHITECTURE.md');
    const fullContent = fs.readFileSync(archPath, 'utf-8');

    await session.run(`
      MERGE (a:ArchitectureDocument {id: 'kurultai-unified-architecture'})
      SET a.title = 'Kurultai Unified Architecture',
          a.version = '3.0',
          a.content = $content,
          a.updated_at = datetime(),
          a.updated_by = 'railway-sync',
          a.file_path = $file_path
    `, { content: fullContent, file_path: archPath });

    console.log('[ARCH-sync] Stored full ArchitectureDocument');

    // Ensure Kublai agent exists and link
    await session.run(`
      MERGE (agent:Agent {id: 'main'})
      SET agent.name = 'Kublai',
          agent.type = 'orchestrator',
          agent.updated_at = datetime()
    `);

    await session.run(`
      MATCH (a:ArchitectureDocument {id: 'kurultai-unified-architecture'})
      MATCH (agent:Agent {id: 'main'})
      MERGE (agent)-[r:HAS_ARCHITECTURE]->(a)
      SET r.updated_at = datetime()
    `);

    console.log('[ARCH-sync] Linked to Kublai agent');

    // Create summary node
    await session.run(`
      MERGE (s:ArchitectureSummary {id: 'kurultai-v3-summary'})
      SET s.version = '3.0',
          s.components = [
            'Unified Heartbeat Engine',
            'OpenClaw Gateway',
            'Neo4j Memory Layer',
            '6-Agent System'
          ],
          s.heartbeat_tasks = 13,
          s.agents = ['kublai', 'mongke', 'chagatai', 'temujin', 'jochi', 'ogedei'],
          s.updated_at = datetime()
    `);

    console.log('[ARCH-sync] Created architecture summary');

    console.log(`\n✅ Successfully synced ${sections.length} sections to Neo4j`);

  } catch (error) {
    console.error('[ARCH-sync] Error:', error.message);
    throw error;
  } finally {
    await session.close();
    await driver.close();
  }
}

/**
 * Main execution
 */
async function main() {
  console.log('[ARCH-sync] Starting architecture sync...');
  console.log(`[ARCH-sync] Neo4j URI: ${NEO4J_URI}`);

  if (!NEO4J_PASSWORD) {
    console.error('[ARCH-sync] ERROR: NEO4J_PASSWORD not set');
    process.exit(1);
  }

  const architecturePath = path.join(process.cwd(), 'ARCHITECTURE.md');

  if (!fs.existsSync(architecturePath)) {
    console.error(`[ARCH-sync] ARCHITECTURE.md not found at ${architecturePath}`);
    process.exit(1);
  }

  const markdown = fs.readFileSync(architecturePath, 'utf-8');
  const sections = parseArchitectureSections(markdown);

  console.log(`[ARCH-sync] Parsed ${sections.length} sections`);

  const commitHash = process.argv[2] || `sync-${Date.now()}`;
  await syncSectionsToNeo4j(sections, commitHash);
}

main().catch(err => {
  console.error('[ARCH-sync] Fatal error:', err);
  process.exit(1);
});
