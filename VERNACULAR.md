# Kurultai Vernacular

**Version**: 1.0  
**Last Updated**: 2026-02-25  
**Status**: Active

---

## Core Vernacular

### "brain" = Neo4j

Throughout all Kurultai systems, documentation, and agent communications, the term **"brain"** refers to the Neo4j graph database that serves as our operational memory and knowledge store.

#### Rationale

The term "brain" reinforces the conceptual model of Neo4j as:
- A shared cognitive resource for all agents
- The central knowledge repository
- The memory layer of the Kurultai system
- The persistent store for learned patterns and insights

#### Usage Guidelines

| Context | Preferred | Avoid |
|---------|-----------|-------|
| General reference | "the brain" or "brain (Neo4j)" | "the Neo4j" |
| Querying | "query brain (Neo4j)" | "query Neo4j" |
| Storage | "store in brain (Neo4j)" | "store in Neo4j" |
| Retrieval | "from brain (Neo4j)" | "from Neo4j" |
| Graph context | "brain graph" | "Neo4j graph" |
| Schema | "brain schema" | "Neo4j schema" |
| Knowledge | "brain knowledge" | "Neo4j knowledge" |

#### Examples

**Documentation:**
```
"Kurultai is built on OpenClaw gateway messaging and brain (Neo4j) 
operational memory."

"Agents query brain (Neo4j) for historical context before making decisions."

"All learned patterns are stored in brain for cross-agent sharing."
```

**Code Comments:**
```python
# Query brain for agent context
# Store reflection in brain (Neo4j)
# Gather full context from brain
```

**Agent Communications:**
```
"I searched brain for similar patterns..."

"According to brain, the last successful approach was..."

"Let me check brain for relevant historical data."
```

---

## Technical Exceptions

When discussing technical implementation details, use explicit terminology:

| Context | Usage |
|---------|-------|
| Driver/Connection | "Neo4j driver", "Neo4j connection" |
| Configuration | "NEO4J_URI", "NEO4J_PASSWORD" |
| Cypher queries | "Cypher query to Neo4j" |
| Database administration | "Neo4j admin", "Neo4j logs" |
| Version numbers | "Neo4j 5 Community" |

---

## Files Using This Vernacular

### Documentation
- `ARCHITECTURE.md` - Primary architecture document
- `FINALIZED_SELF_IMPROVEMENT_PLAN.md` - Self-improvement system
- `AGENT_SOULS_IMPLEMENTATION.md` - Agent souls guide
- `VERNACULAR.md` - This file

### Python Code
- `tools/kurultai/agent_reflection.py`
- `tools/kurultai/kublai_review.py`
- `tools/kurultai/baseline_tracker.py`
- `tools/kurultai/openclaw_memory.py`
- `tools/kurultai/heartbeat_master.py`

### Agent Souls
- `~/.openclaw/agents/{main,researcher,developer,writer,analyst,ops}/SOUL.md`

---

## Migration Notes

### Historical Documents
Older documents may still use "Neo4j" exclusively. When updating:
1. Add vernacular note at top if significant Neo4j references remain
2. Update to "brain (Neo4j)" for primary references
3. Keep "Neo4j" for technical configuration details

### Code Comments
When modifying existing code:
1. Update comments to use "brain" vernacular
2. Keep variable names and configuration keys as NEO4J_* for clarity
3. Add clarifying comments where needed

---

## Summary Statistics

| Metric | Count |
|--------|-------|
| Files with brain vernacular | 14+ |
| Total "brain" references | 282+ |
| Documentation files updated | 3 |
| Code files updated | 3 |
| Agent soul files updated | 8 |

---

## Enforcement

This vernacular is enforced through:
1. **Documentation standards** - All new docs should use "brain"
2. **Code review** - PRs should adopt vernacular for consistency
3. **Agent training** - Agents are instructed to use "brain" in communications
4. **This document** - Reference for contributors and agents

---

*When in doubt, remember: **brain = Neo4j = our shared knowledge store***
