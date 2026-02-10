# Documentation Archive Manifest

**Archive Date:** 2026-02-10  
**Archive Reason:** Phase 2 Documentation Consolidation

## Archived Documents

### Superseded Version Documents
These documents represent old versions of the Kurultai system that have been superseded by newer implementations:

- `kurultai_0.1.md` - v0.1 architecture (superseded by v0.2)
- `kurultai_0.2.md` - v0.2 architecture (superseded by current)
- `kurultai_0.2-completion.md` - v0.2 completion notes
- `kurultai_v0.2_execution_plan.md` - v0.2 execution plan
- `kurultai_v0.2_gap_remediation.md` - v0.2 gap remediation
- `kurultai_0.3.md` - v0.3 architecture (superseded by improvement plan)

### Deprecated Architecture Documents
These architecture plans have been deprecated in favor of current implementation:

- `neo4j.md` - Old Neo4j documentation (superseded by database folder docs)
- `neo4jreview.md` - Review notes (outdated)
- `bounded-file-memory-architecture.md` - Memory architecture (implemented differently)
- `neo4j-memory-optimization-architecture.md` - Optimization plans (implemented)
- `neo4j-multi-database-sensitive-data-architecture.md` - Multi-db design (not implemented)
- `data-retention-policy-recommendations.md` - Retention policy (integrated into main docs)

### Superseded Design Documents
These design documents have been superseded by newer approaches:

- `autonomous-skill-acquisition-architecture.md` - Skill acquisition (implemented differently)
- `parse-autonomous-monetization.md` - Monetization plans (deferred)
- `rebuild-deployment-architecture.md` - Deployment architecture (superseded)
- `swarm-orchestrator-proposal.md` - Swarm proposal (deferred)
- `swarm-validator-agent-proposal.md` - Validator proposal (deferred)
- `multi-goal-ux-recommendations.md` - UX recommendations (integrated)

### Date-Specific Plans (Completed)
These were time-bound plans that have been completed or superseded:

- `2026-02-03-openclaw-neo4j-memory-design.md` - Memory design (implemented)
- `2026-02-07-kublai-proactive-self-awareness.md` - Self-awareness plan (completed)
- `2026-02-07-kublai-self-understanding.md` - Self-understanding plan (completed)
- `2026-02-07-two-tier-heartbeat-system.md` - Heartbeat design (implemented)
- `kublai-domain-switch-plan.md` - Domain switch (completed)
- `kublai-infrastructure-checklist.md` - Infrastructure checklist (completed)
- `kublai-testing-plan.md` - Testing plan (completed)
- `kurultai-neo4j-railway-v3.md` - Railway deployment v3 (completed)
- `jochi-memory-curation-design.md` - Memory curation (implemented)

### Process Documents
These process documents are no longer needed:

- `EXECUTION_SCRIPTS_CREATED.md` - Script creation notes (completed)

## Retained Documents (Not Archived)

The following documents remain in the main docs/plans/ directory as they are still relevant:

- `architecture.md` - Current architecture documentation
- `agent_team_orchestration.md` - Active orchestration patterns
- `autonomous-skill-acquisition.md` - Active skill acquisition docs
- `capability-acquisition-patterns.md` - Active capability patterns
- `capability-acquisition-system-architecture.md` - Active system architecture
- `horde-*.md` - Horde-related documentation (active project)
- `KURULTAI_BUILD_PROMPT.md` - Build prompt (referenced)
- `KURULTAI_V0.2_EXECUTION_GUIDE.md` - Execution guide (referenced)
- `MODEL_SWITCHER_QUICKSTART.md` - Quickstart guide (active)
- `TEST_EXECUTION_PROMPT.md` - Test execution (active)
- `JOCHI_TEST_AUTOMATION.md` - Test automation (active)
- `notion_setup_guide.md` - Notion setup (active)
- `CLAUDE.md` - Memory context (active)

## Restoration

To restore any archived document:

```bash
cp docs/archive/plans/FILENAME.md docs/plans/
```

All archived documents are preserved for reference but are no longer part of the active documentation set.
