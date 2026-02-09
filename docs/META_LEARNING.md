# Meta-Learning System Documentation

**Version**: 1.0  
**Last Updated**: 2026-02-09  
**Author**: Chagatai (Writer Agent)

---

## Overview

The Kurultai Meta-Learning System enables agents to learn from their experiences, identify patterns in reflections, and automatically generate improvement rules that are injected into agent SOUL.md files.

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| MetaLearningEngine | `meta_learning_engine.py` | Clusters reflections, generates rules, tracks effectiveness |
| SOULInjector | `soul_injector.py` | Injects rules into SOUL.md files |
| ArchitectureSync | `arch_sync.py` | Syncs ARCHITECTURE.md with Neo4j |

---

## How Meta-Learning Works

### 1. Reflection Collection

Agents create Reflection nodes in Neo4j when they complete tasks or encounter notable experiences:

```cypher
CREATE (r:Reflection {
    id: $id,
    agent: 'temujin',
    topic: 'error_handling',
    insights: ['Add specific exception types', 'Log context before retry'],
    trigger_task_type: 'code_generation',
    created_at: datetime()
})
```

### 2. Pattern Clustering

The `MetaLearningEngine.cluster_reflections()` method groups similar reflections:

```python
from tools.kurultai.meta_learning_engine import MetaLearningEngine

engine = MetaLearningEngine()
clusters = engine.cluster_reflections(
    min_cluster_size=3,      # Need 3+ reflections per cluster
    time_window_days=30       # Look back 30 days
)
```

**Clustering Process**:
1. Query unconsolidated reflections from Neo4j
2. Group by topic
3. Extract common themes using keyword analysis
4. Generate pattern signatures
5. Persist clusters to Neo4j as ReflectionCluster nodes

### 3. Rule Generation

From each cluster, the engine generates a MetaRule:

```python
rules = engine.generate_rules(
    clusters=clusters,
    min_confidence=0.6        # Minimum 60% confidence
)
```

**Rule Structure**:
- Name and description
- Target agents
- Conditions (when to apply)
- Actions (what to do)
- Priority (1-10, lower is higher)
- Effectiveness score

### 4. Rule Injection

Rules are prepared for injection into SOUL.md files:

```python
injection_plan = engine.inject_rules(
    rules=rules,
    dry_run=True              # Preview without applying
)
```

### 5. Effectiveness Tracking

Rules are continuously evaluated:

```python
evaluations = engine.evaluate_rules(
    evaluation_window_days=7
)
```

Rules with low effectiveness are deprecated automatically.

---

## Rule Generation Process

### Confidence Calculation

Confidence scores determine if a rule is generated from a cluster:

```
confidence = (size_factor × 0.4) + 
             (theme_consistency × 0.4) + 
             (time_consistency × 0.2)
```

| Factor | Description |
|--------|-------------|
| size_factor | Cluster size / 10 (capped at 1.0) |
| theme_consistency | Common insights / reflection count |
| time_consistency | 1.0 - (time_span / 30 days) |

### Rule Types

| Type | Description | Example Actions |
|------|-------------|-----------------|
| error_handling | Exception and error patterns | Add try-except, log context |
| optimization | Performance improvements | Profile code, add caching |
| communication | Inter-agent messaging | Use structured formats |
| workflow | Task sequencing | Break into steps, document deps |
| documentation | Code documentation | Update docstrings, add examples |
| quality_assurance | Testing patterns | Write unit tests, run integration |
| security | Security practices | Validate inputs, use params |
| memory_management | Resource handling | Use generators, clear refs |

---

## Injection Mechanism

### SOUL.md Structure

Rules are injected between special markers:

```markdown
<!-- [LEARNED_RULES] - Auto-generated. Do not edit manually. -->

## Learned Rules

### error_handling_async_patterns_20260209

**Type**: error_handling  
**Priority**: 3/10 (lower is higher)  
**Effectiveness**: 85%

Add specific exception handling to async operations.

**When to apply**:
- task_type IN ['code_generation']
- error_rate > 0.1

**Actions**:
- Add try-except blocks with specific exception types
- Log errors with context before retrying

*Rule ID: `abc123` | Generated: 2026-02-09*

---

<!-- [/LEARNED_RULES] -->
```

### Injection Process

1. Parse existing SOUL.md
2. Check for learned rules section
3. Format rules as markdown
4. Replace or append section
5. Write updated file
6. Git commit (optional)

### Git Integration

The injector can automatically commit changes:

```python
injector = SOULInjector(
    enable_git=True,
    git_auto_commit=False  # Manual commit recommended
)

record = injector.inject_rules(agent_id, rules)
# record.git_commit_hash contains commit reference
```

---

## Evaluation Metrics

### Effectiveness Levels

| Level | Score | Action |
|-------|-------|--------|
| HIGH | ≥ 0.8 | Keep active |
| MEDIUM | 0.5 - 0.8 | Monitor |
| LOW | 0.3 - 0.5 | Review for deprecation |
| UNKNOWN | < 0.3 | Deprecate if applied > 5 times |

### Tracking Methodology

Effectiveness is tracked by monitoring task outcomes:

```cypher
MATCH (mr:MetaRule {id: $rule_id})<-[:USED_RULE]-(t:Task)
RETURN count(t) as applications,
       count(CASE WHEN t.status = 'completed' THEN 1 END) as successes
```

Success rate is combined with original confidence:

```
effectiveness = (original_confidence × 0.3) + (success_rate × 0.7)
```

---

## ARCHITECTURE.md Sync

### Bidirectional Sync

The ArchitectureSync tool keeps ARCHITECTURE.md in sync with Neo4j:

```python
from tools.kurultai.arch_sync import ArchitectureSync

sync = ArchitectureSync()

# File to Neo4j
result = sync.sync_file_to_neo4j()

# Neo4j to file
result = sync.sync_neo4j_to_file(approved_only=True)

# Bidirectional
result = sync.sync_bidirectional(conflict_resolution='manual')
```

### Proposal Workflow

Architecture changes can be proposed through Neo4j:

```python
# Create proposal
proposal_id = sync.create_proposal(
    title="New Component: Metrics Pipeline",
    content="...",
    category="technical",
    author="temujin"
)

# Approve proposal
sync.approve_proposal(proposal_id, approver="kublai")

# Reject proposal
sync.reject_proposal(
    proposal_id, 
    rejector="kublai",
    reason="Duplicate of existing section"
)
```

### Guardrails

Unauthorized changes are prevented:

- Only `AUTHORIZED_AUTHORS` can create proposals
- Proposals must be approved before syncing to file
- Conflicts require manual resolution
- All changes are tracked with git

---

## Usage Examples

### Run Complete Learning Cycle

```python
from tools.kurultai.meta_learning_engine import run_meta_learning_cycle

result = run_meta_learning_cycle(
    min_cluster_size=3,
    generate_rules=True,
    inject=True
)

print(f"Clusters: {result['clusters_created']}")
print(f"Rules: {result['rules_generated']}")
```

### Inject Rules for Specific Agent

```python
from tools.kurultai.soul_injector import SOULInjector
from tools.kurultai.meta_learning_engine import MetaLearningEngine

engine = MetaLearningEngine()
injector = SOULInjector()

# Get rules for agent
rules = engine.get_rules_for_agent('temujin')

# Inject
record = injector.inject_rules('temujin', [r.to_dict() for r in rules])

if record.status == InjectionStatus.INJECTED:
    print(f"Injected rules, commit: {record.git_commit_hash}")
```

### Validate SOUL.md

```python
validation = injector.validate_soul_file('chagatai')

if not validation['valid']:
    for issue in validation['issues']:
        print(f"Issue: {issue}")
```

### Check Sync Status

```python
status = sync.get_sync_status()

print(f"File sections: {status['file_sections']}")
print(f"Neo4j sections: {status['neo4j_sections']}")
print(f"Synced: {status['synced']}")
print(f"Pending proposals: {status['pending_proposals']}")
```

---

## Integration with Kublai

Kublai orchestrates the meta-learning pipeline:

1. **Schedule**: Runs during heartbeat cycle
2. **Trigger**: `run_meta_learning_cycle()`
3. **Delegation**: Injects rules via SOULInjector
4. **Coordination**: Approves architecture proposals

```python
# In Kublai's heartbeat task
from tools.kurultai.meta_learning_engine import MetaLearningEngine
from tools.kurultai.soul_injector import SOULInjector

def meta_learning_task():
    engine = MetaLearningEngine()
    injector = SOULInjector()
    
    # Cluster and generate
    clusters = engine.cluster_reflections()
    if clusters:
        rules = engine.generate_rules(clusters)
        
        # Inject for each agent
        for agent_id, rule_ids in engine.inject_rules(rules).items():
            agent_rules = [engine.rules[rid].to_dict() for rid in rule_ids]
            injector.inject_rules(agent_id, agent_rules)
    
    # Evaluate existing rules
    engine.evaluate_rules()
    engine.deprecate_low_effectiveness_rules(threshold=0.3)
    
    engine.close()
```

---

## Best Practices

### For Rule Authors

1. **High-confidence only**: Don't generate rules from small clusters
2. **Clear conditions**: Rules should have specific, testable conditions
3. **Actionable actions**: Each action should be concrete and achievable
4. **Review periodically**: Check rule effectiveness and deprecate stale rules

### For SOUL.md Maintenance

1. **Don't edit [LEARNED_RULES]**: This section is auto-generated
2. **Review injected rules**: Check that rules make sense for your agent
3. **Rollback if needed**: Use `injector.rollback_injection(record_id)`
4. **Validate after changes**: Run `validate_soul_file()` after manual edits

### For Architecture Sync

1. **Propose changes**: Use Neo4j proposals for significant changes
2. **Get approval**: Have another authorized author approve proposals
3. **Resolve conflicts**: Handle sync conflicts manually
4. **Commit often**: Keep git history clean with descriptive commits

---

## Troubleshooting

### Common Issues

**Issue**: No clusters created
- Check that reflections exist: `MATCH (r:Reflection) RETURN count(r)`
- Verify `min_cluster_size` isn't too high
- Check reflection consolidation status

**Issue**: Rules not injecting
- Verify SOUL.md exists for agent
- Check file permissions
- Review injection record for errors

**Issue**: Sync conflicts
- Use `detect_changes()` to see what's different
- Choose conflict resolution strategy
- Manually merge if needed

**Issue**: Low rule effectiveness
- Review rule conditions for specificity
- Check that tasks are being tagged with rules used
- Consider deprecating and regenerating

### Debug Logging

Enable debug logging for detailed output:

```python
import logging
logging.getLogger('tools.kurultai.meta_learning').setLevel(logging.DEBUG)
```

---

## API Reference

See inline documentation in:
- `meta_learning_engine.py`
- `soul_injector.py`
- `arch_sync.py`

---

## Future Enhancements

- [ ] Semantic clustering using embeddings
- [ ] Rule conflict detection
- [ ] Cross-agent rule sharing
- [ ] Automatic rule refinement
- [ ] Rule explanation generation
