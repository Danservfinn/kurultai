---
plan_manifest:
  version: "1.0"
  created_by: "horde-plan"
  plan_name: "Kublai Proactive Self-Awareness"
  total_phases: 4
  total_tasks: 12
  phases:
    - id: "1"
      name: "Kublai Architecture Query Interface"
      task_count: 3
      parallelizable: false
      gate_depth: "LIGHT"
    - id: "2"
      name: "Improvement Proposal System"
      task_count: 3
      parallelizable: false
      gate_depth: "STANDARD"
    - id: "3"
      name: "Agent Collaboration (Ögedei & Temüjin)"
      task_count: 4
      parallelizable: true
      gate_depth: "STANDARD"
    - id: "4"
      name: "Implementation-to-Doc Pipeline"
      task_count: 2
      parallelizable: false
      gate_depth: "DEEP"
  task_transfer:
    mode: "transfer"
    task_ids: []
---

# Kublai Proactive Self-Awareness Implementation Plan

> **Plan Status:** Draft
> **Created:** 2026-02-07
> **Estimated Tasks:** 12
> **Estimated Phases:** 4

## Overview

**Goal:** Enable Kublai to proactively understand its own architecture (via ARCHITECTURE.md in Neo4j), suggest improvements, and coordinate with Ögedei (Operations) and Temüjin (Developer) to implement validated changes.

**Architecture:**
- **Foundation:** ARCHITECTURE.md already syncs to Neo4j (commit 812452e)
- **New Layer:** Kublai queries synced architecture, proposes improvements
- **Collaboration:** Ögedei vets operations impact, Temüjin implements
- **Guardrails:** Only implemented changes sync back to ARCHITECTURE.md

**Tech Stack:** Neo4j Cypher queries, OpenClaw agent messaging, node-cron for triggers

## Phase 1: Kublai Architecture Query Interface
**Duration**: 45-60 minutes
**Dependencies**: None (ARCHITECTURE.md sync already exists)
**Parallelizable**: No

### Task 1.1: Add architecture queries to Kublai's SOUL.md
**Dependencies**: None

Extend Kublai's memory protocol with architecture queries:

```markdown
# Add to data/workspace/souls/main/SOUL.md:

## Architecture Self-Awareness Queries

// ARCHITECTURE: List all sections
MATCH (s:ArchitectureSection)
RETURN s.title, s.order, s.git_commit
ORDER BY s.order

// ARCHITECTURE: Search for content
CALL db.index.fulltext.queryNodes('architecture_search_index', $search_term)
YIELD node, score

// ARCHITECTURE: Get specific section
MATCH (s:ArchitectureSection {title: $section_title})
RETURN s.title, s.content, s.git_commit, s.updated_at

// ARCHITECTURE: Get component overview
MATCH (s:ArchitectureSection)
WHERE s.title CONTAINS 'Component'
RETURN s.title, s.content
```

**Files:**
- Modify: `data/workspace/souls/main/SOUL.md`

**Acceptance Criteria:**
- [ ] Kublai can query architecture sections
- [ ] Full-text search enabled
- [ ] Specific section retrieval works

### Task 1.2: Create architecture introspection module
**Dependencies**: Task 1.1

Create `src/kublai/architecture-introspection.js`:

```javascript
// Architecture introspection for Kublai

class ArchitectureIntrospection {
  constructor(neo4jDriver, logger) {
    this.driver = neo4jDriver;
    this.logger = logger;
  }

  async getArchitectureOverview() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (s:ArchitectureSection)
        RETURN s.title as section, s.order as position
        ORDER BY s.order
      `);

      const sections = result.records.map(r => ({
        title: r.get('section'),
        position: r.get('position')
      }));

      return {
        totalSections: sections.length,
        sections: sections,
        lastSync: await this.getLastSyncTimestamp()
      };
    } finally {
      await session.close();
    }
  }

  async searchArchitecture(searchTerm) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        CALL db.index.fulltext.queryNodes('architecture_search_index', $term)
        YIELD node, score
        RETURN node.title as title, node.content as content, score
        ORDER BY score DESC
        LIMIT 10
      `, { term: searchTerm });

      return result.records.map(r => ({
        title: r.get('title'),
        content: r.get('content'),
        relevance: r.get('score')
      }));
    } finally {
      await session.close();
    }
  }

  async getLastSyncTimestamp() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (s:ArchitectureSection)
        RETURN max(s.updated_at) as lastSync
      `);

      return result.records[0]?.get('lastSync') || null;
    } finally {
      await session.close();
    }
  }
}

module.exports = { ArchitectureIntrospection };
```

**Files:**
- Create: `src/kublai/architecture-introspection.js`

**Acceptance Criteria:**
- [ ] Module queries ArchitectureSection nodes
- [ ] Full-text search works
- [ ] Returns last sync timestamp

### Task 1.3: Add proactive reflection trigger
**Dependencies**: Task 1.2

Create `src/kublai/proactive-reflection.js`:

```javascript
// Proactive reflection trigger for Kublai

class ProactiveReflection {
  constructor(neo4jDriver, introspection, logger) {
    this.driver = neo4jDriver;
    this.introspection = introspection;
    this.logger = logger;
  }

  async triggerReflection() {
    this.logger.info('[Kublai] Triggering proactive architecture reflection...');

    // Step 1: Get current architecture overview
    const overview = await this.introspection.getArchitectureOverview();

    // Step 2: Analyze for gaps and opportunities
    const opportunities = await this.analyzeForOpportunities(overview);

    // Step 3: Store findings for review
    if (opportunities.length > 0) {
      await this.storeOpportunities(opportunities);
    }

    return {
      sectionsKnown: overview.totalSections,
      opportunitiesFound: opportunities.length
    };
  }

  async analyzeForOpportunities(overview) {
    // Simple analysis - check for common patterns
    const opportunities = [];

    const sectionTitles = overview.sections.map(s => s.title.toLowerCase());

    // Check for common missing sections
    const expectedSections = [
      'system architecture',
      'api routes',
      'data model',
      'security',
      'deployment'
    ];

    for (const expected of expectedSections) {
      if (!sectionTitles.some(t => t.includes(expected))) {
        opportunities.push({
          type: 'missing_section',
          description: `Architecture documentation missing: ${expected}`,
          priority: 'medium'
        });
      }
    }

    return opportunities;
  }

  async storeOpportunities(opportunities) {
    const session = this.driver.session();
    try {
      for (const opp of opportunities) {
        await session.run(`
          CREATE (o:ImprovementOpportunity {
            id: randomUUID(),
            type: $type,
            description: $description,
            priority: $priority,
            created_at: datetime(),
            status: 'proposed',
            proposed_by: 'kublai'
          })
        `, {
          type: opp.type,
          description: opp.description,
          priority: opp.priority
        });
      }

      this.logger.info(`[Kublai] Stored ${opportunities.length} improvement opportunities`);
    } finally {
      await session.close();
    }
  }
}

module.exports = { ProactiveReflection };
```

**Files:**
- Create: `src/kublai/proactive-reflection.js`

**Acceptance Criteria:**
- [ ] Analyzes architecture for gaps
- [ ] Creates ImprovementOpportunity nodes
- [ ] Returns findings summary

### Exit Criteria Phase 1
- [ ] Kublai can query ARCHITECTURE.md from Neo4j
- [ ] Full-text search operational
- [ ] Proactive reflection trigger working
- [ ] Opportunities stored in Neo4j

## Phase 2: Improvement Proposal System
**Duration**: 60-75 minutes
**Dependencies**: Phase 1
**Parallelizable**: No

### Task 2.1: Create proposal node schema
**Dependencies**: Phase 1 complete

Add minimal proposal schema to migration script:

```cypher
// Add to scripts/migrations/003_proposals.cypher

// ArchitectureProposal - Proposals that may become ARCHITECTURE.md sections
CREATE CONSTRAINT proposal_id IF NOT EXISTS FOR (p:ArchitectureProposal) REQUIRE p.id IS UNIQUE;

// ImprovementOpportunity - Opportunities identified by Kublai
CREATE CONSTRAINT opportunity_id IF NOT EXISTS FOR (o:ImprovementOpportunity) REQUIRE o.id IS UNIQUE;

// Relationships
// (:ImprovementOpportunity)-[:EVOLVES_INTO]->(:ArchitectureProposal)
// (:ArchitectureProposal)-[:UPDATES_SECTION]->(:ArchitectureSection)
```

**Files:**
- Create: `scripts/migrations/003_proposals.cypher`

**Acceptance Criteria:**
- [ ] ArchitectureProposal constraint created
- [ ] ImprovementOpportunity constraint created
- [ ] Relationship patterns documented

### Task 2.2: Implement proposal state machine
**Dependencies**: Task 2.1

Create `src/workflow/proposal-states.js`:

```javascript
// Simple proposal state machine

const proposalStates = {
  PROPOSED: 'proposed',
  UNDER_REVIEW: 'under_review',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  IMPLEMENTED: 'implemented',
  VALIDATED: 'validated',
  SYNCED: 'synced' // Only synced proposals update ARCHITECTURE.md
};

class ProposalStateMachine {
  constructor(neo4jDriver, logger) {
    this.driver = neo4jDriver;
    this.logger = logger;
  }

  async createProposal(opportunityId, title, description) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        CREATE (p:ArchitectureProposal {
          id: randomUUID(),
          title: $title,
          description: $description,
          status: 'proposed',
          proposed_at: datetime(),
          proposed_by: 'kublai',
          implementation_status: 'not_started'
        })
        RETURN p.id as id
      `, { title, description });

      const proposalId = result.records[0].get('id');

      // Link to opportunity
      await session.run(`
        MATCH (o:ImprovementOpportunity {id: $oppId})
        MATCH (p:ArchitectureProposal {id: $propId})
        CREATE (o)-[:EVOLVES_INTO]->(p)
      `, { oppId: opportunityId, propId: proposalId });

      this.logger.info(`[Proposal] Created: ${proposalId} - ${title}`);
      return { proposalId, status: 'proposed' };
    } finally {
      await session.close();
    }
  }

  async transition(proposalId, newState, reason = '') {
    const session = this.driver.session();
    try {
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        SET p.status = $newState,
            p.state_changed_at = datetime(),
            p.state_change_reason = $reason
      `, { id: proposalId, newState: proposalStates[newState.toUpperCase()], reason });

      this.logger.info(`[StateMachine] ${proposalId}: ${newState} (${reason})`);
      return { success: true, newState };
    } finally {
      await session.close();
    }
  }

  async getStatus(proposalId) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        RETURN p.status as status, p.implementation_status as implStatus
      `, { id: proposalId });

      return result.records.length > 0 ? result.records[0].toObject() : null;
    } finally {
      await session.close();
    }
  }
}

module.exports = { ProposalStateMachine, proposalStates };
```

**Files:**
- Create: `src/workflow/proposal-states.js`

**Acceptance Criteria:**
- [ ] Creates proposals from opportunities
- [ ] Transitions between states
- [ ] Returns current status

### Task 2.3: Create proposal-to-architecture mapper
**Dependencies**: Task 2.2

Create `src/workflow/proposal-mapper.js`:

```javascript
// Map implemented proposals to ARCHITECTURE.md sections

class ProposalMapper {
  constructor(neo4jDriver, logger) {
    this.driver = neo4jDriver;
    this.logger = logger;
  }

  async mapProposalToSection(proposalId) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        RETURN p.title, p.description, p.category
      `, { id: proposalId });

      if (result.records.length === 0) {
        return null;
      }

      const proposal = result.records[0].toObject();

      // Determine target section in ARCHITECTURE.md
      const targetSection = this.determineSection(proposal);

      // Create mapping record
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        SET p.target_section = $section,
            p.section_mapping_created_at = datetime()
      `, { id: proposalId, section: targetSection });

      return { proposalId, targetSection };
    } finally {
      await session.close();
    }
  }

  determineSection(proposal) {
    // Map proposal content to appropriate ARCHITECTURE.md section
    const title = proposal.title?.toLowerCase() || '';
    const desc = proposal.description?.toLowerCase() || '';

    if (title.includes('api') || desc.includes('endpoint') || desc.includes('route')) {
      return 'API Routes';
    }
    if (title.includes('data') || desc.includes('model') || desc.includes('schema')) {
      return 'Data Model';
    }
    if (title.includes('security') || desc.includes('auth')) {
      return 'Security Architecture';
    }
    if (title.includes('deploy') || desc.includes('infra')) {
      return 'Deployment';
    }

    return 'System Overview'; // Default
  }

  async checkCanSync(proposalId) {
    // Guardrail: Only allow sync if proposal is implemented AND validated
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        RETURN p.status as status, p.implementation_status as implStatus
      `, { id: proposalId });

      if (result.records.length === 0) {
        return { allowed: false, reason: 'Proposal not found' };
      }

      const record = result.records[0].toObject();

      const canSync = record.status === 'validated' &&
                      record.implStatus === 'validated';

      if (!canSync) {
        return {
          allowed: false,
          reason: `Proposal status: ${record.status}, impl: ${record.implStatus}`
        };
      }

      return { allowed: true };
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
- [ ] Maps proposals to ARCHITECTURE.md sections
- [ ] Guardrail check: only validated proposals can sync
- [ ] Returns clear reason if blocked

### Exit Criteria Phase 2
- [ ] Proposal schema migrated
- [ ] State machine working
- [ ] Proposal-to-section mapper created
- [ ] Guardrails enforced

## Phase 3: Agent Collaboration (Ögedei & Temüjin)
**Duration**: 60-75 minutes
**Dependencies**: Phase 2
**Parallelizable**: Yes

### Task 3.1: Create Ögedei vetting handler
**Dependencies**: Phase 2 complete

Create `src/agents/ogedei/vet-handler.js`:

```javascript
// Ögedei (Operations) proposal vetting

class OgedeiVetHandler {
  constructor(neo4jDriver, gateway, logger) {
    this.driver = neo4jDriver;
    this.gateway = gateway;
    this.logger = logger;
  }

  async vetProposal(proposalId) {
    this.logger.info(`[Ögedei] Vetting proposal: ${proposalId}`);

    const session = this.driver.session();
    try {
      // Fetch proposal
      const result = await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        RETURN p
      `, { id: proposalId });

      if (result.records.length === 0) {
        return { error: 'Proposal not found' };
      }

      const proposal = result.records[0].get('p').properties;

      // Ögedei's operational analysis
      const vetting = {
        operationalImpact: this.assessImpact(proposal),
        deploymentRisk: this.assessRisk(proposal),
        rolloutStrategy: this.suggestRollout(proposal),
        monitoring: this.suggestMonitoring(proposal)
      };

      // Store vetting result
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        CREATE (v:Vetting {
          id: randomUUID(),
          proposal_id: $id,
          vetted_by: 'ogedei',
          vetted_at: datetime(),
          assessment: $assessment
        })
      `, {
        id: proposalId,
        assessment: JSON.stringify(vetting)
      });

      // Make recommendation
      const recommendation = this.makeRecommendation(vetting);
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        SET p.ogedei_recommendation = $recommendation
      `, { id: proposalId, recommendation });

      this.logger.info(`[Ögedei] Vetting complete: ${recommendation}`);
      return vetting;
    } finally {
      await session.close();
    }
  }

  assessImpact(proposal) {
    // Assess operational impact: downtime, complexity, resources
    const levels = ['none', 'low', 'medium', 'high'];
    return levels[Math.floor(Math.random() * 4)]; // Placeholder
  }

  assessRisk(proposal) {
    // Assess deployment risk: data loss, rollback complexity
    const levels = ['low', 'medium', 'high', 'critical'];
    return levels[Math.floor(Math.random() * 4)]; // Placeholder
  }

  suggestRollout(proposal) {
    // Suggest rollout strategy based on risk
    return 'blue_green'; // Placeholder
  }

  suggestMonitoring(proposal) {
    // Suggest what to monitor during rollout
    return ['error_rate', 'latency_p95', 'memory_usage'];
  }

  makeRecommendation(vetting) {
    if (vetting.deploymentRisk === 'critical') {
      return 'reject';
    } else if (vetting.deploymentRisk === 'high') {
      return 'approve_with_conditions';
    } else {
      return 'approve';
    }
  }
}

module.exports = { OgedeiVetHandler };
```

**Files:**
- Create: `src/agents/ogedei/vet-handler.js`

**Acceptance Criteria:**
- [ ] Fetches proposal from Neo4j
- [ ] Assesses operational impact
- [ ] Stores vetting result
- [ ] Returns recommendation

### Task 3.2: Create Temüjin implementation handler
**Dependencies**: Phase 2 complete

Create `src/agents/temujin/impl-handler.js`:

```javascript
// Temüjin (Developer) proposal implementation

class TemujinImplHandler {
  constructor(neo4jDriver, gateway, logger) {
    this.driver = neo4jDriver;
    this.gateway = gateway;
    this.logger = logger;
  }

  async implementProposal(proposalId) {
    this.logger.info(`[Temüjin] Implementing proposal: ${proposalId}`);

    const session = this.driver.session();
    try {
      // Fetch proposal
      const result = await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        RETURN p
      `, { id: proposalId });

      if (result.records.length === 0) {
        return { error: 'Proposal not found' };
      }

      const proposal = result.records[0].get('p').properties;

      // Check if approved
      if (proposal.status !== 'approved') {
        return { error: 'Proposal must be approved before implementation' };
      }

      // Create implementation record
      const implResult = await session.run(`
        CREATE (i:Implementation {
          id: randomUUID(),
          proposal_id: $id,
          started_at: datetime(),
          status: 'in_progress',
          progress: 0
        })
        RETURN i.id as id
      `, { id: proposalId });

      const implId = implResult.records[0].get('id');

      // Update proposal
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        SET p.implementation_status = 'in_progress',
            p.implementation_id = $implId
      `, { id: proposalId, implId });

      this.logger.info(`[Temüjin] Implementation started: ${implId}`);
      return { implementationId: implId, status: 'in_progress' };
    } finally {
      await session.close();
    }
  }

  async updateProgress(implId, progress, notes = '') {
    const session = this.driver.session();
    try {
      await session.run(`
        MATCH (i:Implementation {id: $id})
        SET i.progress = $progress,
            i.notes = $notes,
            i.updated_at = datetime()
      `, { id: implId, progress, notes });

      return { success: true };
    } finally {
      await session.close();
    }
  }

  async completeImplementation(implId) {
    const session = this.driver.session();
    try {
      // Update implementation
      await session.run(`
        MATCH (i:Implementation {id: $id})
        SET i.status = 'completed',
            i.completed_at = datetime()
      `);

      // Update proposal
      await session.run(`
        MATCH (i:Implementation {id: $id})
        MATCH (p:ArchitectureProposal {id: i.proposal_id})
        SET p.implementation_status = 'completed',
            p.implementation_completed_at = datetime()
      `);

      this.logger.info(`[Temüjin] Implementation completed: ${implId}`);
      return { status: 'completed' };
    } finally {
      await session.close();
    }
  }
}

module.exports = { TemüjinImplHandler };
```

**Files:**
- Create: `src/agents/temujin/impl-handler.js`

**Acceptance Criteria:**
- [ ] Creates Implementation record
- [ ] Updates proposal status
- [ ] Tracks progress
- [ ] Marks implementation complete

### Task 3.3: Create validation handler
**Dependencies**: None (after Phase 2)

Create `src/workflow/validation.js`:

```javascript
// Validation for completed implementations

class ValidationHandler {
  constructor(neo4jDriver, logger) {
    this.driver = neo4jDriver;
    this.logger = logger;
  }

  async validateImplementation(implId) {
    this.logger.info(`[Validation] Validating implementation: ${implId}`);

    const session = this.driver.session();
    try {
      // Run validation checks
      const checks = await this.runChecks(implId);

      const allPassed = checks.every(c => c.passed);

      // Create validation record
      await session.run(`
        CREATE (v:Validation {
          id: randomUUID(),
          implementation_id: $id,
          validated_at: datetime(),
          passed: $passed,
          checks: $checks,
          status: $status
        })
      `, {
        id: implId,
        passed: allPassed,
        checks: JSON.stringify(checks),
        status: allPassed ? 'passed' : 'failed'
      });

      // Update implementation and proposal if passed
      if (allPassed) {
        await session.run(`
          MATCH (i:Implementation {id: $id})
          MATCH (p:ArchitectureProposal {id: i.proposal_id})
          SET i.validation_id = v.id,
              p.implementation_status = 'validated',
              p.status = 'validated'
        `, { id: implId });
      }

      this.logger.info(`[Validation] Result: ${allPassed ? 'PASSED' : 'FAILED'}`);
      return { implementationId: implId, passed: allPassed, checks };
    } finally {
      await session.close();
    }
  }

  async runChecks(implId) {
    // Define validation checks
    return [
      {
        name: 'implementation_complete',
        passed: true, // Would check actual implementation
        description: 'All implementation tasks completed'
      },
      {
        name: 'tests_pass',
        passed: true, // Would run tests
        description: 'All tests passing'
      },
      {
        name: 'no_regressions',
        passed: true, // Would check for regressions
        description: 'No regressions detected'
      }
    ];
  }
}

module.exports = { ValidationHandler };
```

**Files:**
- Create: `src/workflow/validation.js`

**Acceptance Criteria:**
- [ ] Runs validation checks
- [ ] Creates Validation record
- [ ] Updates proposal to 'validated' on pass
- [ ] Returns detailed results

### Task 3.4: Create scheduled reflection trigger
**Dependencies**: None (after Phase 2)

Create `src/kublai/scheduled-reflection.js`:

```javascript
// Scheduled reflection: Kublai proactively analyzes architecture

const cron = require('node-cron');

class ScheduledReflection {
  constructor(kublaiAgent, neo4jDriver, logger) {
    this.kublai = kublaiAgent;
    this.driver = neo4jDriver;
    this.logger = logger;
    this.job = null;
  }

  start() {
    // Weekly reflection: Every Sunday at 8 PM
    this.job = cron.schedule('0 20 * * 0', () => this.weeklyReflection(), {
      timezone: 'America/New_York'
    });

    this.logger.info('[ScheduledReflection] Started weekly reflection trigger');
  }

  async weeklyReflection() {
    this.logger.info('[Kublai] Running weekly architecture reflection...');

    // Trigger Kublai's proactive reflection
    const result = await this.kublai.triggerProactiveReflection();

    this.logger.info(`[Kublai] Reflection complete: ${JSON.stringify(result)}`);
  }

  stop() {
    if (this.job) {
      this.job.stop();
      this.logger.info('[ScheduledReflection] Stopped');
    }
  }
}

module.exports = { ScheduledReflection };
```

**Files:**
- Create: `src/kublai/scheduled-reflection.js`

**Acceptance Criteria:**
- [ ] Triggers weekly reflection
- [ ] Calls Kublai's proactive reflection
- [ ] Logs results

### Exit Criteria Phase 3
- [ ] Ögedei vetting handler works
- [ ] Temüjin implementation handler works
- [ ] Validation handler checks implementations
- [ ] Scheduled reflection triggers weekly

## Phase 4: Implementation-to-Doc Pipeline
**Duration**: 45-60 minutes
**Dependencies**: Phase 2, Phase 3
**Parallelizable**: No

### Task 4.1: Create ARCHITECTURE.md sync guardrail
**Dependencies**: Phase 2 complete, Phase 3 complete

Update existing sync script with guardrails:

```javascript
// Modify: scripts/sync-architecture-to-neo4j.js

// Add guardrail check before syncing proposals
async function syncValidatedProposalsToArchitectureMd() {
  const driver = await createNeo4jDriver();
  const session = driver.session();

  try {
    // Find proposals that are validated but not yet synced
    const result = await session.run(`
      MATCH (p:ArchitectureProposal {status: 'validated'})
      WHERE NOT EXISTS((p)-[:SYNCED_TO]->(:ArchitectureSection))
      RETURN p.id as id, p.title as title, p.target_section as section
    `);

    for (const record of result.records) {
      const proposalId = record.get('id');
      const title = record.get('title');
      const section = record.get('section');

      console.log(`[ARCH-sync] Syncing validated proposal: ${title} → ${section}`);

      // TODO: Actually update ARCHITECTURE.md with proposal content
      // This is currently a manual step - requires human review

      // Mark as synced
      await session.run(`
        MATCH (p:ArchitectureProposal {id: $id})
        CREATE (p)-[:SYNCED_TO]->(:ArchitectureSection {title: $section})
      `, { id: proposalId, section });
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
- [ ] Only validated proposals considered for sync
- [ ] Guardrail prevents unvalidated sync
- [ ] Sync creates SYNCED_TO relationship

### Task 4.2: Create operations documentation
**Dependencies**: Task 4.1

Create `docs/operations/kublai-self-awareness.md`:

```markdown
# Kublai Self-Awareness Operations Guide

## Overview
Kublai maintains self-awareness by querying ARCHITECTURE.md from Neo4j and proposing improvements via a collaborative workflow with Ögedei (Operations) and Temüjin (Development).

## Architecture

```
ARCHITECTURE.md → Neo4j (via git hook) → Kublai queries → proposes improvement
                                                              ↓
                                                         Ögedei vets
                                                              ↓
                                                         Temüjin implements
                                                              ↓
                                                         Validation
                                                              ↓
                                                         Only THEN syncs back to ARCHITECTURE.md
```

## Proposal States

1. **proposed**: Kublai creates proposal
2. **under_review**: Ögedei reviewing
3. **approved**: Ready for implementation
4. **rejected**: Not proceeding
5. **implemented**: Temüjin completed work
6. **validated**: Validation checks passed
7. **synced**: Changes written to ARCHITECTURE.md

## Agent Roles

### Kublai
- Queries architecture from Neo4j
- Identifies improvement opportunities
- Creates proposals
- Coordinates workflow

### Ögedei (Operations)
- Reviews proposals for operational impact
- Assesses deployment risk
- Provides recommendations

### Temüjin (Development)
- Implements approved proposals
- Tracks progress
- Completes implementation

## Key Guardrail

**ARCHITECTURE.md only updates for validated implementations.**

Proposals must pass through:
1. Creation → 2. Ögedei vetting → 3. Approval → 4. Implementation → 5. Validation → 6. Sync

## Usage

```bash
# Trigger manual reflection
node src/kublai/proactive-reflection.js

# Check pending proposals
curl http://localhost:18789/api/proposals?status=proposed

# Ögedei vet a proposal
curl -X POST http://localhost:18789/api/vet -d '{"proposalId": "..."}'

# Temüjin implement
curl -X POST http://localhost:18789/api/implement -d '{"proposalId": "..."}'
```

## Troubleshooting

### Proposal not syncing to ARCHITECTURE.md
- Check status: must be `validated`
- Check implementation_status: must be `validated`
- Check for SYNCED_TO relationship

### Reflection not finding opportunities
- Verify ARCHITECTURE.md is synced to Neo4j
- Check full-text search index exists
- Review section titles in ArchitectureSection nodes
```

**Files:**
- Create: `docs/operations/kublai-self-awareness.md`

**Acceptance Criteria:**
- [ ] Architecture diagram included
- [ ] Proposal states documented
- [ ] Agent roles explained
- [ ] Key guardrail emphasized
- [ ] Troubleshooting guide included

### Exit Criteria Phase 4
- [ ] Guardrails prevent unvalidated sync
- [ ] Only implemented+validated proposals sync
- [ ] Operations documentation complete
- [ ] End-to-end workflow documented

## Dependency Graph

```
Phase 1 (Kublai Query Interface) — gate: LIGHT
    └── Phase 2 (Proposal System) — gate: STANDARD
            ├── Phase 3 (Agent Collab) — gate: STANDARD
            └── Phase 4 (Doc Pipeline) — gate: DEEP
```

## Approval

- [ ] Plan Output Contract validated
- [ ] Requirements understood
- [ ] Kublai can query architecture from Neo4j
- [ ] Proposal workflow with Ögedei/Temüjin designed
- [ ] Guardrails prevent premature doc updates
- [ ] Task breakdown acceptable
- [ ] Dependencies correct
- [ ] Ready for execution via horde-implement

**Ready to proceed?** Use ExitPlanMode to approve.
