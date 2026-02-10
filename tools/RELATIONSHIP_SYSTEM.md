# Relationship Tracking System

A comprehensive system for tracking relationships between people in Kurultai, with special focus on relationships to the primary human (Danny).

## Overview

The Relationship Tracking System uses the golden-horde pattern for parallel analysis of conversations to detect and track relationships between people. It integrates with the existing identity system and stores data in Neo4j.

## Components

### 1. RelationshipDetector (`tools/relationship_detector.py`)

Single-conversation relationship analysis using pattern matching and NLP.

**Features:**
- Extract mentions of people from conversation text
- Detect relationship types from context keywords
- Calculate relationship strength from signal words
- Track confidence levels

**Relationship Types:**
- `FRIEND` - Personal connection
- `COLLEAGUE` - Professional connection
- `FAMILY` - Family member
- `BUSINESS_PARTNER` - Business relationship
- `MENTOR` / `MENTEE` - Guidance relationship
- `ACQUAINTANCE` - Casual connection
- `UNKNOWN` - Relationship unclear

**Usage:**
```python
from tools.relationship_detector import RelationshipDetector, RelationshipType

detector = RelationshipDetector(primary_human="Danny")

# Analyze a conversation
relationships = detector.analyze_conversation(
    conversation_text="My colleague Danny and I work on Kurultai.",
    speaker_id="signal:alice",
    speaker_name="Alice"
)

for rel in relationships:
    print(f"{rel.person_a} -> {rel.person_b}: {rel.relationship_type.value}")
```

### 2. RelationshipAnalyzer (`tools/relationship_analyzer.py`)

Horde-based parallel analysis of conversation batches.

**Features:**
- Spawn agents to process conversation batches in parallel
- Aggregate findings from multiple agents
- Resolve conflicts between agent assessments
- Store analysis results in Neo4j

**Usage:**
```python
from tools.relationship_analyzer import analyze_relationships_horde

conversations = [
    {"text": "Danny is my colleague.", "speaker_id": "alice", "speaker_name": "Alice"},
    {"text": "Danny is my friend.", "speaker_id": "bob", "speaker_name": "Bob"},
]

result = analyze_relationships_horde(
    conversations=conversations,
    primary_human="Danny",
    batch_size=10,
    focus_on_primary=True
)

print(f"Found {len(result.primary_human_relationships)} relationships to Danny")
```

### 3. RelationshipManager (`tools/relationship_manager.py`)

Integration with the identity system for persistent storage and context building.

**Features:**
- Store and retrieve relationships from Neo4j
- Track relationships to primary human
- Build relationship context for conversations
- Update relationship strength over time

**Usage:**
```python
from tools.relationship_manager import RelationshipManager, RelationshipType

manager = RelationshipManager(primary_human="Danny")
manager.initialize()

# Record a relationship
manager.record_relationship(
    person_a_id="signal:alice",
    person_b_id="signal:danny",
    relationship_type=RelationshipType.COLLEAGUE,
    strength=0.8,
    context="Work together on Kurultai",
    confidence=0.9
)

# Get relationships for a person
relationships = manager.get_person_relationships("signal:danny")

# Get relationship context
context = manager.get_relationship_context("signal:alice")
if context.relationship_to_primary:
    print(f"Relationship to Danny: {context.relationship_to_primary.relationship_type.value}")
```

## Neo4j Schema

### Node Types

- `Person` - Existing person nodes from identity system
- `AggregatedRelationship` - Aggregated relationship data
- `RelationshipEvidence` - Evidence supporting relationships
- `RelationshipAnalysis` - Analysis job tracking

### Relationship Types

- `(:Person)-[:KNOWS]->(:Person)` - Direct relationship between people
  - `type`: Relationship type (friend, colleague, etc.)
  - `strength`: 0.0 to 1.0
  - `context`: Description
  - `discovered_at`: When first detected
  - `last_updated`: When last confirmed
  - `confidence`: Confidence level
  - `evidence_count`: Number of supporting evidence

- `(:Person)-[:HAS_RELATIONSHIP]->(:AggregatedRelationship)`
- `(:AggregatedRelationship)-[:SUPPORTED_BY]->(:RelationshipEvidence)`
- `(:RelationshipAnalysis)-[:FOUND]->(:AggregatedRelationship)`

See `tools/relationship_schema.cypher` for full schema definitions.

## Data Model

### Simple Relationship (:KNOWS)

```cypher
(:Person {name: "Alice"})-[:KNOWS {
    type: "COLLEAGUE",
    strength: 0.8,
    context: "Work on Kurultai project together",
    discovered_at: datetime(),
    last_updated: datetime(),
    confidence: 0.85,
    evidence_count: 5,
    source: "conversation_analysis"
}]->(:Person {name: "Danny"})
```

### Aggregated Relationship

```cypher
(:AggregatedRelationship {
    type: "FRIEND",
    avg_strength: 0.75,
    max_strength: 0.9,
    min_strength: 0.6,
    confidence: 0.85,
    evidence_count: 12,
    discovered_at: datetime(),
    last_updated: datetime(),
    agent_votes: "{FRIEND: 5, COLLEAGUE: 2}"
})
```

## Integration with Identity System

The RelationshipManager extends the KurultaiIdentitySystem:

```python
from tools.kurultai_identity_system import KurultaiIdentitySystem
from tools.relationship_manager import extend_identity_system_with_relationships

# Create identity system
identity_system = KurultaiIdentitySystem(
    neo4j_uri="bolt://localhost:7687",
    neo4j_password="password"
)
identity_system.initialize()

# Extend with relationships
rel_manager = extend_identity_system_with_relationships(identity_system)

# Now use for conversation analysis
context = identity_system.on_message_received(
    channel="signal",
    sender_handle="+1234567890",
    sender_name="Alice",
    message_text="Danny and I are working on a project."
)

# Analyze and record relationships
rel_manager.analyze_and_record(
    conversation_text="Danny and I are working on a project.",
    speaker_id=context["person_id"],
    speaker_name="Alice"
)
```

## Relationship Detection Keywords

### Family
- mother, father, mom, dad, parent, parents
- brother, sister, sibling
- son, daughter, child, children
- husband, wife, spouse, married
- grandmother, grandfather, grandparent
- uncle, aunt, cousin, niece, nephew

### Colleague
- colleague, coworker, teammate
- boss, manager, supervisor
- employee, report, works with
- team member, on my team
- office, workplace, company
- project with, collaborate

### Business Partner
- co-founder, founder, partner
- business partner, investor, advisor
- stakeholder, shareholder, client
- vendor, supplier, contractor
- deal with, partnership

### Mentor
- mentor, mentored by, learned from
- advisor, coach, taught me
- career advice, professional guidance

### Friend
- friend, buddy, pal, best friend
- we hang out, we go way back
- friendship, hang out, catch up

### Acquaintance
- acquaintance, know of, heard of
- briefly met, ran into
- not close, don't know well

## Strength Signals

### High Strength
- best, closest, dear, love
- always, everything, trust completely

### Medium Strength
- often, regularly, usually
- good, solid, respect, appreciate

### Low Strength
- sometimes, occasionally, rarely
- not close, distant, lost touch

## Testing

Run the test suite:

```bash
cd /data/workspace/souls/main
python -m pytest tools/test_relationship_system.py -v
```

Tests cover:
- Relationship detection accuracy
- Strength calculation
- Batch processing
- Conflict resolution
- Neo4j integration
- Edge cases and error handling

## Performance

- Single conversation analysis: <100ms
- Batch of 100 conversations: <10s (with 5 workers)
- Relationship storage: <50ms

## Future Enhancements

1. **NLP Integration**: Use spaCy or transformers for better NER
2. **Sentiment Analysis**: Track relationship sentiment over time
3. **Temporal Analysis**: Detect relationship evolution
4. **Graph Analytics**: Find clusters and influencers
5. **ML Classification**: Train models for relationship type prediction

## Configuration

Environment variables:

```bash
# Neo4j connection
NEO4J_URI=bolt://localhost:7687
NEO4J_PASSWORD=your_password

# Primary human name
PRIMARY_HUMAN_NAME=Danny

# Horde settings
KURULTAI_AGENT_SPAWNING=false  # Set to true to spawn real agents
RELATIONSHIP_BATCH_SIZE=10
RELATIONSHIP_MAX_WORKERS=5
```

## License

Part of the Kurultai project.
