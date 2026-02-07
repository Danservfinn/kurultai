#!/usr/bin/env node
/**
 * Run Cypher Migration
 *
 * Executes a Cypher migration file against Neo4j.
 * Usage: node scripts/run-cypher-migration.js <migration-file>
 */

const fs = require('fs');
const path = require('path');

// Neo4j configuration from environment
const NEO4J_URI = process.env.NEO4J_URI || 'bolt://localhost:7687';
const NEO4J_USER = process.env.NEO4J_USER || 'neo4j';
const NEO4J_PASSWORD = process.env.NEO4J_PASSWORD || '';

async function createNeo4jDriver() {
  try {
    const neo4j = require('neo4j-driver');
    return neo4j.driver(
      NEO4J_URI,
      neo4j.auth.basic(NEO4J_USER, NEO4J_PASSWORD)
    );
  } catch (e) {
    console.error('[Migration] neo4j-driver not installed');
    console.error('[Migration] Install with: npm install neo4j-driver');
    process.exit(1);
  }
}

async function runMigration(migrationFile) {
  const driver = await createNeo4jDriver();
  const session = driver.session();

  try {
    // Read migration file
    const migrationPath = path.resolve(process.cwd(), migrationFile);
    console.log(`[Migration] Reading: ${migrationPath}`);

    const cypher = fs.readFileSync(migrationPath, 'utf-8');

    // Remove comment lines first
    const lines = cypher.split('\n');
    const codeLines = lines.filter(line => {
      const trimmed = line.trim();
      return trimmed.length > 0 &&
             !trimmed.startsWith('//') &&
             !trimmed.startsWith('/*') &&
             !trimmed.startsWith('*');
    });

    // Split by semicolon and run each statement
    const statements = codeLines
      .join('\n')
      .split(';')
      .map(s => s.trim())
      .filter(s => s.length > 0);

    console.log(`[Migration] Found ${statements.length} statements to execute`);

    for (const statement of statements) {
      console.log(`[Migration] Executing: ${statement.substring(0, 60)}...`);
      try {
        await session.run(statement);
        console.log(`[Migration] ✓ Success`);
      } catch (error) {
        // Ignore "already exists" errors from constraints/indexes
        if (error.message.includes('AlreadyExists') || error.message.includes('equivalent')) {
          console.log(`[Migration] ⊘ Already exists (skipped)`);
        } else {
          console.error(`[Migration] ✗ Failed: ${error.message}`);
          throw error;
        }
      }
    }

    console.log(`[Migration] Complete!`);
  } catch (error) {
    console.error(`[Migration] Failed: ${error.message}`);
    process.exit(1);
  } finally {
    await session.close();
    await driver.close();
  }
}

// Main
const migrationFile = process.argv[2];
if (!migrationFile) {
  console.error('Usage: node scripts/run-cypher-migration.js <migration-file>');
  process.exit(1);
}

runMigration(migrationFile).catch(console.error);
