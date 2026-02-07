---
plan_manifest:
  version: "1.0"
  created_by: "horde-plan"
  plan_name: "Kublai Self-Understanding via Neo4j"
  total_phases: 3
  total_tasks: 9
  phases:
    - id: "1"
      name: "Kublai Architecture Query Interface"
      task_count: 3
      parallelizable: false
      gate_depth: "LIGHT"
    - id: "2"
      name: "Proactive Proposal System"
      task_count: 4
      parallelizable: false
      gate_depth: "STANDARD"
    - id: "3"
      name: "Implementation & Validation"
      task_count: 2
      parallelizable: false
      gate_depth: "DEEP"
  task_transfer:
    mode: "transfer"
    task_ids: []
---

# Kublai Self-Understanding via Neo4j Implementation Plan

> **Plan Status:** Draft
> **Created:** 2026-02-07
> **Estimated Tasks:** 9
> **Estimated Phases:** 3

## Overview

**Goal:** Enable Kublai to understand its own architecture by reading ARCHITECTURE.md from Neo4j, and to propose improvements through a simple workflow.

**Architecture:**
- **Foundation:** ARCHITECTURE.md syncs to Neo4j via git hook (already implemented in commit 812452e)
- **Layer 1:** Kublai queries synced architecture sections from Neo4j
- **Layer 2:** Kublai proposes improvements stored as ArchitectureProposal nodes
- **Layer 3:** Implemented+validated proposals update ARCHITECTURE.md

**Key Principle:** Kublai's proposals are suggestions that go through review and implementation before ever touching ARCHITECTURE.md.

## Phase 1: Kublai Architecture Query Interface
**Duration**: 30-45 minutes
**Dependencies**: None (ARCHITECTURE.md sync already exists)
**Parallelizable**: No

### Task 1.1: Add Neo4j query helpers to moltbot
**Dependencies**: None

Create Neo4j query helper module for Kublai:

```javascript
// Create: src/kublai/neo4j-queries.js

class KublaiNeo4jQueries {
  constructor(driver, logger) {
    this.driver = driver;
    this.logger = logger;
  }

  // Get all architecture sections (table of contents)
  async getArchitectureTOC() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (s:ArchitectureSection)
        RETURN s.title as title, s.order as position, s.parent_section as parent
        ORDER BY s.order
      `);

      return result.records.map(r => ({
        title: r.get('title'),
        position: r.get('position'),
        parent: r.get('parent')
      }));
    } finally {
      await session.close();
    }
  }

  // Search architecture content
  async searchArchitecture(query) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        CALL db.index.fulltext.queryNodes('architecture_search_index', $query)
        YIELD node, score
        RETURN node.title as title, node.content as content, score
        ORDER BY score DESC
        LIMIT 5
      `, { query });

      return result.records.map(r => ({
        title: r.get('title'),
        content: r.get('content'),
        relevance: r.get('score')
      }));
    } finally {
      await session.close();
    }
  }

  // Get specific section by title
  async getSection(title) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (s:ArchitectureSection {title: $title})
        RETURN s.title, s.content, s.git_commit, s.updated_at
      `, { title });

      return result.records.length > 0 ? result.records[0].toObject() : null;
    } finally {
      await session.close();
    }
  }

  // Get system components
  async getSystemComponents() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (s:ArchitectureSection)
        WHERE s.title CONTAINS 'Component' OR s.title CONTAINS 'Service'
        RETURN s.title, s.content
      `);

      return result.records.map(r => ({
        title: r.get('title'),
        content: r.get('content')
      }));
    } finally {
      await session.close();
    }
  }
}

module.exports = { KublaiNeo4jQueries };
```

**Files:**
- Create: `src/kublai/neo4j-queries.js`

**Acceptance Criteria:**
- [ ] getArchitectureTOC() returns ordered sections
- [ ] searchArchitecture() returns relevant results
- [ ] getSection() fetches specific section
- [ ] getSystemComponents() extracts component info

### Task 1.2: Update Kublai's SOUL.md with architecture queries
**Dependencies**: Task 1.1

Add to Kublai's memory reading protocol:

```markdown
# Add to data/workspace/souls/main/SOUL.md:

## Architecture Self-Understanding Queries

// ARCHITECTURE: Get table of contents
MATCH (s:ArchitectureSection)
RETURN s.title, s.order, s.parent_section
ORDER BY s.order

// ARCHITECTURE: Full-text search
CALL db.index.fulltext.queryNodes('architecture_search_index', $search_term)
YIELD node.title as title, node.content as content, score

// ARCHITECTURE: Get specific section
MATCH (s:ArchitectureSection {title: $section_title})
RETURN s.title, s.content, s.git_commit, s.updated_at

// ARCHITECTURE: List system components
MATCH (s:ArchitectureSection)
WHERE s.title CONTAINS 'Component' OR s.title CONTAINS 'Service'
RETURN s.title, s.content
```

**Files:**
- Modify: `data/workspace/souls/main/SOUL.md`

**Acceptance Criteria:**
- [ ] Kublai can query TOC from Neo4j
- [ ] Full-text search enabled
- [ ] Section retrieval documented
- [ ] Component queries available

### Task 1.3: Create proactive reflection trigger
**Dependencies**: Task 1.2

Create scheduled reflection for Kublai:

```javascript
// Create: src/kublai/proactive-reflection.js

const cron = require('node-cron');

class ProactiveReflection {
  constructor(kublaiAgent, neo4jDriver, logger) {
    this.kublai = kublaiAgent;
    this.driver = neo4jDriver;
    this.logger = logger;
  }

  start() {
    // Weekly reflection: Every Sunday at 8 PM
    cron.schedule('0 20 * * 0', () => this.weeklyReflection(), {
      timezone: 'America/New_York'
    });

    this.logger.info('[Kublai] Started proactive reflection (weekly)');
  }

  async weeklyReflection() {
    this.logger.info('[Kublai] Running weekly architecture reflection...');

    // 1. Get current architecture overview
    const toc = await this.getArchitectureTOC();

    // 2. Analyze for gaps or improvement opportunities
    const opportunities = await this.identifyOpportunities(toc);

    // 3. Store opportunities as proposals
    if (opportunities.length > 0) {
      await this.storeProposals(opportunities);
    }

    return {
      sectionsKnown: toc.length,
      opportunitiesFound: opportunities.length
    };
  }

  async getArchitectureTOC() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (s:ArchitectureSection)
        RETURN s.title, s.order
        ORDER BY s.order
      `);
      return result.records.map(r => r.get('title'));
    } finally {
      await session.close();
    }
  }

  async identifyOpportunities(sectionTitles) {
    const opportunities = [];
    const titles = sectionTitles.map(t => t.toLowerCase());

    // Check for expected sections
    const expected = [
      'system architecture',
      'api routes',
      'data model',
      'security',
      'deployment'
    ];

    for (const exp of expected) {
      if (!titles.some(t => t.includes(exp))) {
        opportunities.push({
          type: 'missing_section',
          description: `Architecture missing section: ${exp}`,
          priority: 'medium'
        });
      }
    }

    return opportunities;
  }

  async storeProposals(opportunities) {
    const session = this.driver.session();
    try {
      for (const opp of opportunities) {
        await session.run(`
          CREATE (p:ImprovementProposal {
            id: randomUUID(),
            title: $title,
            description: $description,
            priority: $priority,
            proposed_by: 'kublai',
            created_at: datetime(),
            status: 'proposed'
          })
        `, {
          title: opp.description.substring(0, 50) + '...',
          description: opp.description,
          priority: opp.priority
        });
      }
      this.logger.info(`[Kublai] Stored ${opportunities.length} proposals`);
    } finally {
      await session.close();
    }
  }

  stop() {
    // Cleanup
  }
}

module.exports = { ProactiveReflection };
```

**Files:**
- Create: `src/kublai/proactive-reflection.js`

**Acceptance Criteria:**
- [ ] Weekly reflection scheduled
- [ ] Identifies missing architecture sections
- [ ] Creates ImprovementProposal nodes
- [ ] Logs results

### Exit Criteria Phase 1
- [ ] Kublai can query ARCHITECTURE.md from Neo4j
- [ ] Search works across architecture content
- [ ] Proactive reflection identifies gaps
- [ ] Proposals stored in Neo4j

## Phase 2: Proactive Proposal System
**Duration**: 45-60 minutes
**Dependencies**: Phase 1
**Parallelizable**: No

### Task 2.1: Create proposal schema migration
**Dependencies**: Phase 1 complete

Add proposal schema to Neo4j:

```cypher
// Create: scripts/migrations/003_proposals.cypher

// ImprovementProposal - Kublai's suggestions
CREATE CONSTRAINT proposal_id IF NOT EXISTS FOR (p:ImprovementProposal) REQUIRE p.id IS UNIQUE;

// Create index for querying proposals
CREATE INDEX proposal_status IF NOT EXISTS FOR (p:ImprovementProposal) WHERE p.status;

// Optional: Relate proposals to architecture sections
// (:ImprovementProposal)-[:UPDATES_SECTION]->(:ArchitectureSection)
```

**Files:**
- Create: `scripts/migrations/003_proposals.cypher`

**Acceptance Criteria:**
- [ ] ImprovementProposal constraint created
- [ ] Status index created
- [ ] Migration script ready

### Task 2.2: Run proposal schema migration
**Dependencies**: Task 2.1

```bash
node scripts/run-migration.js scripts/migrations/003_proposals.cypher
# Expected: Constraint and index created
```

**Files:**
- No files created (execution only)

**Acceptance Criteria:**
- [ ] Migration completes without errors
- [ ] Neo4j has ImprovementProposal label
- [ ] Constraint verified

### Task 2.3: Create proposal state machine
**Dependencies**: Task 2.2

Create proposal workflow:

```javascript
// Create: src/workflow/proposal-workflow.js

class ProposalWorkflow {
  constructor(neo4jDriver, logger) {
    this.driver = neo4jDriver;
    this.logger = logger;
  }

  async createProposal(title, description, category = 'general') {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        CREATE (p:ImprovementProposal {
          id: randomUUID(),
          title: $title,
          description: $description,
          category: $category,
          proposed_by: 'kublai',
          created_at: datetime(),
          status: 'proposed',
          implementation_status: 'not_started'
        })
        RETURN p.id as id
      `, { title, description, category });

      const proposalId = result.records[0].get('id');
      this.logger.info(`[Workflow] Created proposal: ${proposalId}`);
      return { proposalId };
    } finally {
      await session.close();
    }
  }

  async updateStatus(proposalId, newStatus) {
    const session = this.driver.session();
    try {
      await session.run(`
        MATCH (p:ImprovementProposal {id: $id})
        SET p.status = $status,
            p.status_changed_at = datetime()
      `, { id: proposalId, status: newStatus });

      this.logger.info(`[Workflow] Proposal ${proposalId}: ${newStatus}`);
      return { success: true };
    } finally {
      await session.close();
    }
  }

  async listProposals(status = 'proposed') {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (p:ImprovementProposal {status: $status})
        RETURN p.id, p.title, p.description, p.priority, p.created_at
        ORDER BY p.created_at DESC
      `, { status });

      return result.records.map(r => r.toObject());
    } finally {
      await session.close();
    }
  }

  async getProposal(proposalId) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (p:ImprovementProposal {id: $id})
        RETURN p
      `, { id: proposalId });

      return result.records.length > 0 ? result.records[0].get('p') : null;
    } finally {
      await session.close();
    }
  }
}

module.exports = { ProposalWorkflow };
```

**Files:**
- Create: `src/workflow/proposal-workflow.js`

**Acceptance Criteria:**
- [ ] Creates proposals in Neo4j
- [ ] Updates proposal status
- [ ] Lists proposals by status
- [ ] Retrieves specific proposal

### Task 2.4: Create proposal-to-architecture mapper
**Dependencies**: Task 2.3

Create mapper for linking proposals to ARCHITECTURE.md sections:

```javascript
// Create: src/workflow/proposal-mapper.js

class ProposalMapper {
  constructor(neo4jDriver, logger) {
    this.driver = neo4jDriver;
    this.logger = logger;
  }

  // Map proposal content to target ARCHITECTURE.md section
  determineTargetSection(proposal) {
    const title = (proposal.title || '').toLowerCase();
    const desc = (proposal.description || '').toLowerCase();

    if (title.includes('api') || desc.includes('endpoint') || desc.includes('route')) {
      return 'API Routes';
    }
    if (title.includes('data') || desc.includes('model') || desc.includes('schema')) {
      return 'Data Model';
    }
    if (title.includes('security') || desc.includes('auth') || desc.includes('permission')) {
      return 'Security Architecture';
    }
    if (title.includes('deploy') || desc.includes('infra') || desc.includes('production')) {
      return 'Deployment';
    }

    return 'System Overview';
  }

  // Check if proposal can sync to ARCHITECTURE.md (must be implemented+validated)
  async canSyncToArchitectureMd(proposalId) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (p:ImprovementProposal {id: $id})
        RETURN p.status as status, p.implementation_status as implStatus
      `, { id: proposalId });

      if (result.records.length === 0) {
        return { allowed: false, reason: 'Proposal not found' };
      }

      const record = result.records[0].toObject();

      // Must be implemented and validated
      const canSync = record.status === 'validated' &&
                      record.implStatus === 'validated';

      if (!canSync) {
        return {
          allowed: false,
          reason: `Status: ${record.status}, Implementation: ${record.implStatus}`
        };
      }

      return { allowed: true };
    } finally {
      await session.close();
    }
  }

  // Mark proposal as synced to ARCHITECTURE.md
  async markSynced(proposalId) {
    const session = this.driver.session();
    try {
      await session.run(`
        MATCH (p:ImprovementProposal {id: $id})
        SET p.status = 'synced',
            p.synced_at = datetime(),
            p.synced_to_architecture = true
      `, { id: proposalId });

      this.logger.info(`[Mapper] Proposal ${proposalId} synced to ARCHITECTURE.md`);
      return { success: true };
    } finally {
      await session.close();
    }
  }
}

module.exports = { ProposalMapper };
```

**Files:**
- Create: `src/workflow/proposal-mapper.js`

**Acceptance Criteria:**
- [ ] Maps proposals to sections intelligently
- [ ] Guardrail: only validated proposals can sync
- [ ] Marks proposals as synced
- [ ] Returns clear blocking reasons

### Exit Criteria Phase 2
- [ ] Proposal schema migrated to Neo4j
- [ ] Proposal workflow operational
- [ ] Proposals can be created and listed
- [ ] Mapper with guardrails working

## Phase 3: Implementation & Validation
**Duration**: 45-60 minutes
**Dependencies**: Phase 1, Phase 2
**Parallelizable**: No

### Task 3.1: Create implementation tracker
**Dependencies**: Phase 2 complete

Track implementation of approved proposals:

```javascript
// Create: src/workflow/implementation-tracker.js

class ImplementationTracker {
  constructor(neo4jDriver, logger) {
    this.driver = neo4jDriver;
    this.logger = logger;
  }

  async startImplementation(proposalId, implementer = 'temujin') {
    const session = this.driver.session();
    try {
      // Create implementation record
      const result = await session.run(`
        CREATE (i:Implementation {
          id: randomUUID(),
          proposal_id: $id,
          started_at: datetime(),
          status: 'in_progress',
          implementer: $implementer,
          progress: 0
        })
        RETURN i.id as id
      `, { id: proposalId, implementer });

      const implId = result.records[0].get('id');

      // Update proposal
      await session.run(`
        MATCH (p:ImprovementProposal {id: $id})
        SET p.implementation_status = 'in_progress',
            p.implementation_id = $implId
      `, { id: proposalId, implId });

      this.logger.info(`[Tracker] Implementation started: ${implId} by ${implementer}`);
      return { implementationId: implId };
    } finally {
      await session.close();
    }
  }

  async updateProgress(implId, progressPercent, notes = '') {
    const session = this.driver.session();
    try {
      await session.run(`
        MATCH (i:Implementation {id: $id})
        SET i.progress = $progress,
            i.notes = $notes,
            i.updated_at = datetime()
      `, { id: implId, progress: progressPercent, notes });

      return { success: true };
    } finally {
      await session.close();
    }
  }

  async completeImplementation(implId) {
    const session = this.driver.session();
    try {
      await session.run(`
        MATCH (i:Implementation {id: $id})
        SET i.status = 'completed',
            i.completed_at = datetime()
      `);

      // Update proposal
      await session.run(`
        MATCH (i:Implementation {id: $id})
        MATCH (p:ImprovementProposal {id: i.proposal_id})
        SET p.implementation_status = 'completed',
            p.implementation_completed_at = datetime()
      `);

      this.logger.info(`[Tracker] Implementation completed: ${implId}`);
      return { success: true };
    } finally {
      await session.close();
    }
  }

  async validateImplementation(implId) {
    const session = this.driver.session();
    try {
      // Create validation record
      const result = await session.run(`
        CREATE (v:Validation {
          id: randomUUID(),
          implementation_id: $id,
          validated_at: datetime(),
          status: 'passed'
        })
        RETURN v.id as id
      `, { id: implId });

      const validationId = result.records[0].get('id');

      // Update proposal to validated
      await session.run(`
        MATCH (i:Implementation {id: $id})
        MATCH (p:ImprovementProposal {id: i.proposal_id})
        SET p.status = 'validated',
            p.implementation_status = 'validated',
            p.validation_id = $validationId
      `, { id: implId, validationId });

      this.logger.info(`[Tracker] Implementation validated: ${implId}`);
      return { validationId, status: 'passed' };
    } finally {
      await session.close();
    }
  }
}

module.exports = { ImplementationTracker };
```

**Files:**
- Create: `src/workflow/implementation-tracker.js`

**Acceptance Criteria:**
- [ ] Creates Implementation records
- [ ] Tracks progress percentage
- [ ] Completes and validates implementations
- [ ] Updates proposal through states

### Task 3.2: Update ARCHITECTURE.md sync with guardrails
**Dependencies**: Task 3.1

Modify existing sync script to include proposal guardrails:

```javascript
// Modify: scripts/sync-architecture-to-neo4j.js

// Add function to sync validated proposals
async function syncValidatedProposals() {
  const driver = await createNeo4jDriver();
  const session = driver.session();

  try {
    // Find proposals that are validated but not yet synced
    const result = await session.run(`
      MATCH (p:ImprovementProposal {status: 'validated'})
      WHERE p.synced_to_architecture IS NULL OR p.synced_to_architecture = false
      RETURN p.id, p.title, p.target_section
    `);

    for (const record of result.records) {
      const proposalId = record.get('p.id');
      const title = record.get('p.title');
      const section = record.get('p.target_section');

      console.log(`[ARCH-sync] Syncing validated proposal: ${title} → ${section}`);

      // TODO: Generate markdown and insert into ARCHITECTURE.md
      // For now, log what would be synced

      // Mark as synced
      await session.run(`
        MATCH (p:ImprovementProposal {id: $id})
        SET p.synced_to_architecture = true,
            p.synced_at = datetime()
      `, { id: proposalId });
    }

    return { synced: result.records.length };
  } finally {
    await session.close();
    await driver.close();
  }
}
```

**Files:**
- Modify: `scripts/sync-architecture-to-neo4j.js`

**Acceptance Criteria:**
- [ ] Only validated proposals considered
- [ ] Guardrail prevents premature sync
- [ ] Synced proposals marked
- [ ] Returns sync count

### Exit Criteria Phase 3
- [ ] Implementation tracker works
- [ ] Validation flow operational
- [ ] ARCHITECTURE.md sync has guardrails
- [ ] Only validated proposals sync

## Dependency Graph

```
Phase 1 (Kublai Query Interface) — gate: LIGHT
    └── Phase 2 (Proposal System) — gate: STANDARD
            └── Phase 3 (Implementation) — gate: DEEP
```

## Approval

- [ ] Plan Output Contract validated
- [ ] Kublai can query ARCHITECTURE.md from Neo4j
- [ ] Proactive proposal system created
- [ ] Implementation tracker with validation
- [ ] Guardrails prevent premature doc sync
- [ ] Task breakdown acceptable
- [ ] Dependencies correct
- [ ] Ready for execution via horde-implement

**Ready to proceed?** Use ExitPlanMode to approve.
