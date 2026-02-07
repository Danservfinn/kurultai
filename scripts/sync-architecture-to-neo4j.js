#!/usr/bin/env node
/**
 * Sync ARCHITECTURE.md sections to Neo4j
 *
 * This script parses ARCHITECTURE.md by H2 headers and stores each section
 * as an ArchitectureSection node in Neo4j with full-text search indexing.
 *
 * Usage: node scripts/sync-architecture-to-neo4j.js [commit_hash]
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// Neo4j configuration from environment
const NEO4J_URI = process.env.NEO4J_URI || 'neo4j+s://';
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
    // Check for H2 header (## Section Name)
    const h2Match = line.match(/^##\s+(.+)$/);

    if (h2Match) {
      // Save previous section if exists
      if (currentSection) {
        sections.push({
          ...currentSection,
          content: currentContent.join('\n').trim(),
          order: sectionOrder++
        });
      }

      // Start new section
      currentSection = {
        title: h2Match[1].trim(),
        content: []
      };
      currentContent = [];
    } else if (currentSection) {
      currentContent.push(line);
    }
  }

  // Don't forget the last section
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
 * Create Neo4j driver (minimal implementation)
 */
async function createNeo4jDriver() {
  // Use neo4j-driver if available, otherwise basic fetch implementation
  let driver;

  try {
    const neo4j = require('neo4j-driver');
    driver = neo4j.driver(
      NEO4J_URI,
      neo4j.auth.basic(NEO4J_USER, NEO4J_PASSWORD)
    );
  } catch (e) {
    console.error('[ARCH-sync] neo4j-driver not installed, skipping sync');
    console.error('[ARCH-sync] Install with: npm install neo4j-driver');
    process.exit(0);
  }

  return driver;
}

/**
 * Create full-text search index for ArchitectureSection nodes
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
  const driver = await createNeo4jDriver();
  const session = driver.session();

  try {
    // Create full-text search index
    await createSearchIndex(session);

    // First, mark all existing sections as potentially stale
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

      // Extract parent section from title (if nested like "Parent > Child")
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

      console.log(`[ARCH-sync] Synced section: ${section.title}`);
    }

    // Delete sections that are no longer in the document
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

    console.log(`[ARCH-sync] Synced ${sections.length} sections to Neo4j`);
  } finally {
    await session.close();
    await driver.close();
  }
}

/**
 * Main execution (when run as standalone script)
 */
async function main() {
  const commitHash = process.argv[2] || 'manual';
  const architecturePath = path.join(process.cwd(), 'ARCHITECTURE.md');

  console.log(`[ARCH-sync] Reading ARCHITECTURE.md...`);

  if (!fs.existsSync(architecturePath)) {
    console.log(`[ARCH-sync] ARCHITECTURE.md not found, skipping sync`);
    return;
  }

  const markdown = fs.readFileSync(architecturePath, 'utf-8');
  const sections = parseArchitectureSections(markdown);

  console.log(`[ARCH-sync] Parsed ${sections.length} sections`);

  await syncSectionsToNeo4j(sections, commitHash);
}

/**
 * Sync validated proposals back to ARCHITECTURE.md
 *
 * CRITICAL GUARDRAIL: Only validated+implemented proposals can sync.
 * This prevents unproven changes from being documented.
 *
 * Note: This is currently a MANUAL step requiring human review.
 * The proposal content should be reviewed and properly formatted
 * before adding to ARCHITECTURE.md.
 */
async function syncValidatedProposalsToArchitectureMd() {
  const driver = await createNeo4jDriver();
  const session = driver.session();

  try {
    // Find proposals that are validated but not yet synced
    const result = await session.run(`
      MATCH (p:ArchitectureProposal {status: 'validated'})
      WHERE NOT EXISTS((p)-[:SYNCED_TO]->(:ArchitectureSection))
      RETURN p.id as id, p.title as title, p.target_section as section,
             p.description as description
    `);

    console.log(`[ARCH-sync] Found ${result.records.length} validated proposals ready for sync`);

    for (const record of result.records) {
      const proposalId = record.get('id');
      const title = record.get('title');
      const section = record.get('section');
      const description = record.get('description');

      console.log(`[ARCH-sync] Proposal ready for manual sync: "${title}" → ${section}`);
      console.log(`[ARCH-sync]   Description: ${description}`);
      console.log(`[ARCH-sync]   Action: Manually add to ARCHITECTURE.md, then run: markSynced("${proposalId}", "${section}")`);
    }

    return { found: result.records.length };
  } finally {
    await session.close();
    await driver.close();
  }
}

/**
 * Mark a proposal as synced to ARCHITECTURE.md
 * Call this after manually adding proposal content to ARCHITECTURE.md
 */
async function markSynced(proposalId, sectionTitle) {
  const driver = await createNeo4jDriver();
  const session = driver.session();

  try {
    // Verify proposal is validated (guardrail)
    const checkResult = await session.run(`
      MATCH (p:ArchitectureProposal {id: $id})
      RETURN p.status as status, p.implementation_status as implStatus
    `, { id: proposalId });

    if (checkResult.records.length === 0) {
      console.error(`[ARCH-sync] Proposal not found: ${proposalId}`);
      return { success: false };
    }

    const record = checkResult.records[0].toObject();

    // GUARDRAIL: Only validated proposals can be marked as synced
    if (record.status !== 'validated' || record.implStatus !== 'validated') {
      console.error(`[ARCH-sync] GUARDRAIL: Proposal not validated (status=${record.status}, impl=${record.implStatus})`);
      return { success: false, guardrail: true };
    }

    // Create sync relationship
    await session.run(`
      MATCH (p:ArchitectureProposal {id: $id})
      MATCH (s:ArchitectureSection {title: $sectionTitle})
      CREATE (p)-[:SYNCED_TO {synced_at: datetime()}]->(s)
      SET p.status = 'synced',
          p.synced_at = datetime()
    `, { id: proposalId, sectionTitle });

    console.log(`[ARCH-sync] Marked proposal ${proposalId} as synced to "${sectionTitle}"`);
    return { success: true };
  } finally {
    await session.close();
    await driver.close();
  }
}

// Export functions for use as a module
module.exports = {
  parseArchitectureSections,
  calculateChecksum,
  createNeo4jDriver,
  createSearchIndex,
  syncSectionsToNeo4j,
  syncValidatedProposalsToArchitectureMd,
  markSynced
};

// Run main if called directly (not required as module)
if (require.main === module) {
  const command = process.argv[2];

  if (command === 'sync-proposals') {
    syncValidatedProposalsToArchitectureMd().catch(console.error);
  } else if (command === 'mark-synced') {
    const proposalId = process.argv[3];
    const sectionTitle = process.argv[4];
    if (!proposalId || !sectionTitle) {
      console.error('Usage: node sync-architecture-to-neo4j.js mark-synced <proposalId> <sectionTitle>');
    } else {
      markSynced(proposalId, sectionTitle).catch(console.error);
    }
  } else {
    main().catch(console.error);
  }
}
