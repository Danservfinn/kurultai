# Relationship Tracking System

A comprehensive system for tracking ALL relationships between ALL humans in Kurultai's social graph, with complete web-like relationship tracking (not just star topology from Danny).

## Overview

The Relationship Tracking System uses the golden-horde pattern for parallel analysis of conversations to detect and track relationships between people. It builds a complete social network graph stored in Neo4j.

## Components

### 1. RelationshipDetector (`tools/relationship_detector.py`)

Single-conversation relationship analysis using pattern matching and NLP.

**Features:**
- Extract mentions of ALL people from conversation text
- Detect speaker's relationships to others
- Detect third-party relationships (A talking about B's relationship to C)
- Detect inferred relationships from co-occurrence patterns
- Calculate relationship strength from signal words
- Track confidence levels and discovery metadata

**Relationship Types:**
- **Positive/Neutral:** FRIEND, COLLEAGUE, FAMILY, BUSINESS_PARTNER, MENTOR, MENTEE, ACQUAINTANCE, COLLABORATOR
- **Negative/Complex:** RIVAL, STRANGER, UNKNOWN

**Usage:**
```python
from tools.relationship_detector import RelationshipDetector, RelationshipType

detector = RelationshipDetector(primary_human="Danny")

# Analyze a conversation - detects ALL relationships mentioned
relationships = detector.analyze_conversation(
    conversation_text="Alice and Bob are colleagues. Charlie is my friend.",
    speaker_id="signal:danny",
    speaker_name="Danny"
)

for rel in relationships:
    print(f"{rel.person_a} -> {rel.person_b}: {rel.relationship_type.value}")
    print(f"  Discovered via: {rel.discovered_via}")
    print(f"  Is explicit: {rel.is_explicit}")
```

### 2. RelationshipAnalyzer (`tools/relationship_analyzer.py`)

Horde-based parallel analysis of conversation batches with graph analytics.

**Features:**
- Spawn agents to process conversation batches in parallel
- Aggregate findings from multiple agents
- Resolve conflicts between agent assessments
- **Graph Analytics:**
  - Find clusters/communities
  - Identify bridge people (connect different groups)
  - Detect isolated individuals
  - Map influence networks
  - Compute graph density and clustering

**Usage:**
```python
from tools.relationship_analyzer import analyze_relationships_horde

conversations = [
    {"text": "Alice and Bob work together.", "speaker_id": "carol"},
    {"text": "Bob is my friend.", "speaker_id": "danny"},
]

result = analyze_relationships_horde(
    conversations=conversations,
    primary_human="Danny",
    batch_size=10
)

# Access aggregated relationships
for rel in result.aggregated_relationships:
    print(f"{rel.person_a} -> {rel.person_b}: {rel.relationship_type.value}")

# Access graph analytics
if result.graph_analytics:
    print(f"Clusters found: {len(result.graph_analytics.clusters)}")
    print(f"Bridge people: {len(result.graph_analytics.bridge_people)}")
    print(f"Isolated individuals: {result.graph_analytics.isolated_individuals}")
```

### 3. RelationshipManager (`tools/relationship_manager.py`)

Integration with the identity system for persistent storage and full social graph support.

**Features:**
- Store and retrieve ALL relationships from Neo4j
- Build complete social graph (not just star topology)
- Privacy-respecting tracking (only observed relationships)
- Graph analytics queries (clusters, bridges, influence)
- Track explicit vs inferred relationships

**Usage:**
```python
from tools.relationship_manager import RelationshipManager, RelationshipType

manager = RelationshipManager(primary_human="Danny")
manager.initialize()

# Record relationship with privacy tracking
manager.record_observed_relationship(
    person_a_id="signal:alice",
    person_b_id="signal:bob",
    relationship_type=RelationshipType.COLLEAGUE,
    strength=0.8,
    context="Work together",
    confidence=0.9,
    discovered_in_conversation="Danny",
    is_explicit=True
)

# Build full social graph
graph = manager.build_full_social_graph(
    min_confidence=0.3,
    respect_privacy=True
)
print(f"Total people: {graph['total_nodes']}")
print(f"Total relationships: {graph['total_edges']}")

# Find clusters
clusters = manager.find_clusters_and_communities()
for cluster in clusters:
    print(f"Cluster {cluster['cluster_id']}: {cluster['size']} members")

# Find bridge people
bridges = manager.find_bridge_people()
for person in bridges[:5]:
    print(f"{person['person_id']} connects: {person['connects_clusters']}")

# Get influence network
influencers = manager.get_influence_network(top_n=10)
```

### 4. Graph Analytics Data Structures

```python
@dataclass
class GraphAnalytics:
    total_nodes: int
    total_edges: int
    clusters: List[Cluster]
    bridge_people: List[BridgePerson]
    isolated_individuals: List[str]
    influence_scores: Dict[str, float]
    density: float
    average_clustering: float

@dataclass
class Cluster:
    cluster_id: str
    members: List[str]
    size: int
    internal_edges: int
    external_edges: int
    cohesion_score: float
    dominant_relationship_types: List[str]

@dataclass
class BridgePerson:
    person_id: str
    betweenness_score: float
    connects_clusters: List[str]
    bridge_strength: float
```

## Neo4j Schema

### Node Types

- `Person` - Person nodes from identity system
- `AggregatedRelationship` - Aggregated relationship data
- `RelationshipEvidence` - Evidence supporting relationships
- `RelationshipAnalysis` - Analysis job tracking

### Relationship Types

**`(:Person)-[:KNOWS]->(:Person)`** - Direct relationship with properties:
- `type`: Relationship type (friend, colleague, rival, etc.)
- `strength`: 0.0 to 1.0
- `context`: Description
- `discovered_at`: When first detected
- `last_updated`: When last confirmed
- `confidence`: Confidence level
- `evidence_count`: Number of supporting evidence
- `discovered_via`: How was this discovered (conversation, inference, etc.)
- `discovered_in_conversation_with`: Who mentioned this relationship
- `is_explicit`: True if explicitly stated, False if inferred
- `privacy_level`: observed, inferred, sensitive

### Privacy-First Design

The system respects privacy by only tracking relationships that are:
1. **Explicitly mentioned** in conversations with Kurultai
2. **Directly observed** through interactions
3. **Never inferred** outside of observed interactions without marking as inferred

```cypher
// Only get explicitly mentioned relationships
MATCH (p1:Person)-[r:KNOWS {is_explicit: true}]-(p2:Person)
RETURN p1.name, p2.name, r.type, r.discovered_in_conversation_with

// Mark inferred relationships differently
MATCH (p1:Person)-[r:KNOWS {is_explicit: false}]-(p2:Person)
SET r.privacy_level = 'inferred', r.confidence = r.confidence * 0.8
```

## Golden-Horde Agent Tasks

The relationship analysis uses multiple specialized agents:

1. **Agent 1 (Explicit Detector)**
   - Analyzes conversations for explicit relationship mentions
   - Task: Find "X is my colleague" patterns
   - Output: Explicit relationships with high confidence

2. **Agent 2 (Context Inferencer)**
   - Infers relationships from contextual clues
   - Task: Detect co-occurrence patterns, shared contexts
   - Output: Inferred relationships with lower confidence

3. **Agent 3 (Graph Builder)**
   - Builds the social graph structure
   - Task: Connect all detected relationships into a graph
   - Output: Connected graph with all nodes and edges

4. **Agent 4 (Validator)**
   - Validates and resolves conflicts
   - Task: Detect contradictions, merge duplicates, resolve conflicts
   - Output: Validated, conflict-free relationship set

5. **Agent 5 (Analytics Calculator)**
   - Computes network metrics
   - Task: Find clusters, bridge people, isolated individuals, influence scores
   - Output: GraphAnalytics object with complete metrics

## Data Model

### Basic Relationship
```cypher
(:Person {name: "Alice"})-[:KNOWS {
    type: "COLLEAGUE",
    strength: 0.8,
    context: "Work together on Kurultai",
    confidence: 0.9,
    discovered_via: "conversation",
    discovered_in_conversation_with: "Danny",
    is_explicit: true,
    privacy_level: "observed"
}]->(:Person {name: "Bob"})
```

### Third-Party Relationship
```cypher
(:Person {name: "Carol"})-[:KNOWS {
    type: "FRIEND",
    strength: 0.7,
    context: "Mentioned as friends by Danny",
    discovered_via: "third_party_mention",
    discovered_in_conversation_with: "Danny",
    is_explicit: true,
    privacy_level: "observed"
}]->(:Person {name: "Alice"})
```

### Inferred Relationship
```cypher
(:Person {name: "Bob"})-[:KNOWS {
    type: "ACQUAINTANCE",
    strength: 0.3,
    context: "Mentioned together in conversation",
    discovered_via: "inferred_cooccurrence",
    discovered_in_conversation_with: "Danny",
    is_explicit: false,
    privacy_level: "inferred"
}]->(:Person {name: "Eve"})
```

## Relationship Detection Keywords

### COLLABORATOR
- collaborator, collaborate, working together
- joint project, partnership, co-author
- co-creator, teammate on, fellow
- ally, confederate

### RIVAL
- rival, competitor, opponent, adversary
- enemy, nemesis, arch-rival, competition
- competing with, against, opposed to
- frenemy, thorn in my side

### STRANGER
- stranger, don't know, never met
- unknown person, no idea who, never heard of

See `relationship_detector.py` for complete keyword lists for all types.

## Graph Analytics Queries

### Find All Clusters
```cypher
MATCH (p:Person)-[r:KNOWS]-(other:Person)
WHERE r.strength >= 0.4
WITH p, collect(other) as neighbors
// Use community detection or connected components
```

### Find Bridge People
```cypher
MATCH (p:Person)-[r:KNOWS]-(other:Person)
WHERE r.strength >= 0.4
WITH p, count(DISTINCT other) as connections,
     collect(DISTINCT other) as neighbors
// Find people connecting different communities
```

### Get Influence Network
```cypher
MATCH (p:Person)-[r:KNOWS]-(other:Person)
WHERE r.strength >= 0.3
WITH p, sum(r.strength) as total_strength, count(other) as connections
RETURN p.name, total_strength, connections,
       (total_strength * connections) as influence_score
ORDER BY influence_score DESC
```

### Find Isolated People
```cypher
MATCH (p:Person)
OPTIONAL MATCH (p)-[r:KNOWS]-(other:Person)
WITH p, count(other) as connection_count
WHERE connection_count <= 1
RETURN p.name, connection_count
```

## Testing

Run the test suite:

```bash
cd /data/workspace/souls/main
python -m pytest tools/test_relationship_system.py -v
```

Tests cover:
- Relationship detection for all types
- Third-party relationship detection
- Inferred relationship detection
- Graph analytics (clusters, bridges, influence)
- Privacy-respecting tracking
- Edge cases and error handling

## Configuration

Environment variables:

```bash
# Neo4j connection
NEO4J_URI=bolt://localhost:7687
NEO4J_PASSWORD=your_password

# Primary human name (for reference, not exclusive tracking)
PRIMARY_HUMAN_NAME=Danny

# Horde settings
KURULTAI_AGENT_SPAWNING=false
RELATIONSHIP_BATCH_SIZE=10
RELATIONSHIP_MAX_WORKERS=5

# Privacy settings
RELATIONSHIP_RESPECT_PRIVACY=true
RELATIONSHIP_MIN_CONFIDENCE=0.3
RELATIONSHIP_MIN_STRENGTH=0.2
```

## Future Enhancements

1. **Temporal Analysis**: Track how relationships evolve over time
2. **Sentiment Tracking**: Monitor relationship sentiment
3. **Predictive Analytics**: Predict relationship formation/deterioration
4. **Visualization**: Generate graph visualizations
5. **Advanced ML**: Use transformers for better relationship extraction

## License

Part of the Kurultai project.
