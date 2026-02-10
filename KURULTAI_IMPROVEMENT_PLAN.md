# Kurultai Improvement Plan

## Overview

**Kurultai** is an intelligent multi-agent orchestration system that coordinates specialized AI agents to handle complex tasks. Named after the Mongolian council of chiefs, it enables collaborative decision-making and task execution.

**Current Version:** v2.0 (Phase 3 Complete)  
**Last Updated:** 2026-02-10

---

## Phase 3: Major Enhancements (COMPLETE) ✓

### Summary

Phase 3 transforms Kurultai from a scheduled task system into a truly intelligent, self-managing platform with predictive capabilities and autonomous decision-making.

### Features Delivered

#### 1. Dynamic Task Generation System ✓
**File:** `tools/dynamic_task_generator.py`

Intelligent task creation based on system state and knowledge gaps:
- **Knowledge Gap Detection:** Automatically identifies missing documentation, orphaned concepts, sparse topics
- **Actionable Finding Monitor:** Scans research outputs for TODOs, FIXMEs, and action items
- **Auto-Spawning:** Spawns appropriate agents when knowledge gaps are detected
- **Confidence-Based Filtering:** Only generates tasks when confidence exceeds threshold (0.7)
- **Duplicate Prevention:** Tracks recently processed gaps to avoid task duplication

**Key Classes:**
- `DynamicTaskGenerator` - Main orchestrator
- `KnowledgeGap` - Represents detected gaps
- `GeneratedTask` - Auto-created tasks
- `GapType` - Categories: MISSING_DOCUMENTATION, ORPHANED_CONCEPT, etc.

**Integration:**
- Runs every heartbeat cycle in `heartbeat_master.py`
- Persists gaps to Neo4j as `KnowledgeGap` nodes
- Links generated tasks to source gaps

---

#### 2. Agent Collaboration Protocol ✓
**File:** `tools/agent_collaboration.py`

Multi-agent orchestration with sophisticated collaboration modes:
- **Collaboration Modes:**
  - `SEQUENTIAL` - Agents work in order, passing outputs forward
  - `PARALLEL` - Agents work simultaneously
  - `CONSENSUS` - Agents vote/consensus on result
  - `COMPETITIVE` - Agents compete, best result wins
  - `SPECIALIST` - Each agent handles different aspects

- **Predefined Templates:**
  - `research_deep_dive` - Research → Analysis → Documentation
  - `security_audit` - Multi-perspective security review
  - `complex_implementation` - Design → Code → Test
  - `rapid_analysis` - Fast parallel analysis
  - `competitive_review` - Multiple solutions, best wins

- **Parallel Spawning:** Spawns all required agents simultaneously
- **Result Synthesis:** Intelligent merging of multi-agent outputs
- **Consensus Building:** Detects agreement across agent outputs

**Key Classes:**
- `AgentCollaborationProtocol` - Main orchestrator
- `CollaborationTask` - Multi-agent task definition
- `CollaborationResult` - Synthesized results
- `AgentRole` - Role definition within collaboration

---

#### 3. Predictive Health Monitoring ✓
**File:** `tools/cost_monitor.py`

Advanced monitoring with ML-style trend analysis:
- **Resource Exhaustion Prediction:** Linear extrapolation for CPU, memory, disk
- **Daemon Failure Prediction:** Pattern matching for Signal daemon degradation
- **Database Degradation:** Query time trend analysis
- **Error Spike Prediction:** Early warning for error rate increases
- **Cost Forecasting:** Projected API costs based on usage trends

**Predictive Capabilities:**
- Trend analysis using linear regression
- Volatility calculation for confidence scoring
- Time-to-failure estimation
- Pre-emptive restart scheduling

**Health Metrics Tracked:**
- CPU_USAGE, MEMORY_USAGE, DISK_USAGE
- NEO4J_CONNECTIONS, NEO4J_QUERY_TIME
- SIGNAL_DAEMON_PING, AGENT_HEARTBEAT_LATENCY
- TASK_QUEUE_DEPTH, ERROR_RATE

**Key Classes:**
- `PredictiveHealthMonitor` - Main monitor
- `Prediction` - Predictive alert with confidence
- `HealthMetric` - Metric types
- `PredictedEvent` - Event categories

---

#### 4. Intelligent Workspace Curation ✓
**File:** `tools/workspace_curator.py`

AI-powered workspace management:
- **Auto-Naming:** Generates contextual titles for untitled pages
  - Extracts topics from headers
  - Identifies technical keywords
  - Quality scoring before applying
  
- **Consolidation Suggestions:**
  - Groups related small pages by topic
  - Detects duplicate/similar titles
  - Estimates space savings
  
- **Auto-Archiving:**
  - Identifies stale content (>90 days)
  - Low engagement + low quality detection
  - Organized archive structure

- **Content Analysis:**
  - Word count, technical term detection
  - Topic extraction
  - Quality scoring algorithm

**Key Classes:**
- `WorkspaceCurator` - Main curator
- `PageAnalysis` - Page metadata and analysis
- `ConsolidationSuggestion` - Merge recommendations

---

#### 5. Context-Aware Routing ✓
**File:** `tools/context_aware_router.py`

Intelligent message/task routing with multi-factor analysis:
- **Intent Classification:**
  - QUESTION, REQUEST, COMMAND
  - REPORT, DISCUSSION, FOLLOW_UP, CLARIFICATION

- **Urgency Detection:**
  - CRITICAL: "asap", "immediately", "broken", "blocking"
  - HIGH: "soon", "important", "priority"
  - NORMAL, LOW

- **Sentiment Analysis:**
  - POSITIVE, NEUTRAL, NEGATIVE
  - FRUSTRATED, URGENT

- **Priority Inference:**
  - Combines urgency, sentiment, intent
  - Time constraint detection
  - Contextual scoring

- **Multi-Factor Routing:**
  - Topic matching to agent expertise
  - Keyword analysis
  - Agent mention bonus
  - Confidence scoring

**Key Classes:**
- `ContextAwareRouter` - Main router
- `MessageContext` - Rich context extraction
- `RoutingDecision` - Route with confidence

---

## Integration Points

### Heartbeat Integration
All Phase 3 features integrate into the unified heartbeat:

```python
# heartbeat_master.py - run_cycle()

# Phase 3: Predictive Health Monitoring
monitor = get_health_monitor(driver)
predictions = monitor.run_all_predictions()

# Phase 3: Dynamic Task Generation
generator = get_task_generator(driver)
gen_result = await generator.run_generation_cycle()
```

### Task Registry
New tasks added to `TASK_REGISTRY`:
- `predictive_health_check` (5 min) - Resource failure prediction
- `workspace_curation` (6 hours) - Workspace maintenance
- `collaboration_orchestration` (15 min) - Multi-agent coordination

### Neo4j Schema Extensions
New node types:
- `KnowledgeGap` - Detected knowledge gaps
- `Prediction` - Predictive health alerts
- `Collaboration` - Multi-agent task tracking
- `CurationCycle` - Workspace curation history
- `HealthMetric` - Historical metrics

---

## Architecture

### Module Structure
```
tools/
├── dynamic_task_generator.py    # Phase 3 - Task generation
├── agent_collaboration.py        # Phase 3 - Multi-agent orchestration
├── cost_monitor.py               # Phase 3 - Predictive monitoring
├── workspace_curator.py          # Phase 3 - Workspace curation
├── context_aware_router.py       # Phase 3 - Smart routing
└── kurultai/
    ├── heartbeat_master.py       # Enhanced with Phase 3
    ├── agent_tasks.py            # Phase 3 tasks added
    └── ...
```

### Data Flow
1. **Heartbeat triggers** → Phase 3 features execute
2. **Gaps detected** → Tasks auto-generated
3. **Complex tasks** → Collaboration protocol spawns teams
4. **Health trends** → Predictions trigger pre-emptive actions
5. **Workspace stale** → Auto-curation applies

---

## Configuration

### Environment Variables
```bash
# Required
NEO4J_URI=bolt://localhost:7687
NEO4J_PASSWORD=your_password

# Optional - Phase 3 tuning
KURULTAI_PREDICTION_THRESHOLD=0.7
KURULTAI_ARCHIVE_DAYS=90
KURULTAI_CONFIDENCE_THRESHOLD=0.7
```

### Thresholds
- **Prediction threshold:** 0.7 (alert when probability >= 70%)
- **Critical threshold:** 0.85 (immediate action required)
- **Archive threshold:** 90 days of inactivity
- **Confidence threshold:** 0.7 for auto-generated tasks

---

## Usage

### Running Phase 3 Features

```bash
# Dynamic task generation
cd /data/workspace/souls/main
python tools/dynamic_task_generator.py --cycle

# Agent collaboration
cd /data/workspace/souls/main
python tools/agent_collaboration.py --templates

# Predictive monitoring
cd /data/workspace/souls/main
python tools/cost_monitor.py --dashboard

# Workspace curation (dry-run)
cd /data/workspace/souls/main
python tools/workspace_curator.py --scan

# Context routing demo
cd /data/workspace/souls/main
python tools/context_aware_router.py
```

### Via Heartbeat
All features run automatically every heartbeat cycle:
```bash
cd /data/workspace/souls/main/tools/kurultai
python heartbeat_master.py --cycle
```

---

## Testing

Each Phase 3 module includes standalone execution:

```bash
# Test dynamic task generation
python tools/dynamic_task_generator.py --stats

# Test collaboration templates
python tools/agent_collaboration.py --templates

# Test predictions
python tools/cost_monitor.py --predict

# Test curation
python tools/workspace_curator.py --stats

# Test routing
python tools/context_aware_router.py --route "Can you research the latest AI?"
```

---

## Changelog

### v2.0.0 (2026-02-10)
- ✨ **Dynamic Task Generation:** Auto-create tasks from knowledge gaps
- ✨ **Agent Collaboration Protocol:** Multi-agent orchestration with 5 modes
- ✨ **Predictive Health Monitoring:** Resource exhaustion forecasting
- ✨ **Intelligent Workspace Curation:** Auto-naming and archival
- ✨ **Context-Aware Routing:** Multi-factor intelligent routing
- 🔧 Enhanced heartbeat with Phase 3 integration
- 🔧 Extended Neo4j schema for new node types
- 🔧 Added 3 new background tasks to registry

---

## Roadmap

### Phase 4 (Future)
- [ ] Self-healing capabilities
- [ ] Cross-system integration protocols
- [ ] Advanced ML-based predictions
- [ ] Natural language task creation
- [ ] Autonomous capability acquisition

---

## Contributors

- **Kurultai v2.0** - Phase 3 implementation
- Based on Kurultai v1.0 architecture

---

## License

Internal use only - part of the OpenClaw ecosystem
