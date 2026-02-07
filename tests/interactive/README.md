# Interactive Workflow Observation Tests

This directory contains tools for recording and analyzing chat sessions with Kublai to observe real workflow processes and validate behavior against architecture specifications.

## Components

### chat_session_recorder.py

The `ChatSessionRecorder` class records:
- All messages with timestamps
- Timing events for workflow milestones (delegation, agent response, synthesis)
- Neo4j queries with performance metrics
- Architecture validation results

### test_scenarios.py

Predefined test scenarios covering key workflows:
1. **Simple Delegation** - Single agent routing to Mongke
2. **Multi-Agent Collaboration** - Coordinated work across Temüjin, Chagatai, Jochi
3. **Capability-Based Routing** - Verification of correct agent selection
4. **Fallback Handling** - Behavior when specialist is unavailable
5. **Complex DAG Coordination** - Multi-task dependency management
6. **Security Audit** - Security-specific task routing to Temüjin

### run_interactive_tests.py

Command-line interface for running scenarios:

```bash
# List all available scenarios
python tests/interactive/run_interactive_tests.py list

# Run a specific scenario
python tests/interactive/run_interactive_tests.py run 0

# Run all scenarios
python tests/interactive/run_interactive_tests.py run-all

# Compare two sessions for regression detection
python tests/interactive/run_interactive_tests.py compare session1.json session2.json
```

## Directory Structure

```
tests/interactive/
├── __init__.py                     # Package exports
├── chat_session_recorder.py        # Recording and validation
├── test_scenarios.py               # Scenario definitions
├── run_interactive_tests.py        # CLI runner
├── README.md                       # This file
├── sessions/                       # Saved session recordings
│   └── *.json
└── checklists/                     # Validation checklists
    └── *_checklist.json
```

## Workflow

1. **Select Scenario**: Choose from predefined scenarios or create your own
2. **Run Interactive**: The runner guides you through sending the message to Kublai
3. **Record Response**: Paste Kublai's response for analysis
4. **Provide Observations**: Note which agents participated, duration
5. **Validate**: System compares observed vs expected behavior
6. **Checklist**: Complete manual validation checklist
7. **Save**: Session and checklist saved for regression testing

## Session Format

Saved sessions contain:

```json
{
  "session_name": "Simple_Delegation_to_Researcher_20260207_120000",
  "start_time": 1757260800.0,
  "end_time": 1757260830.0,
  "duration_seconds": 30.0,
  "messages": [
    {
      "role": "user",
      "content": "Research the latest advances...",
      "timestamp": 1757260800.0,
      "agent_responding": null
    },
    {
      "role": "assistant",
      "content": "Based on my research...",
      "timestamp": 1757260825.0,
      "agent_responding": "kublai"
    }
  ],
  "timing_events": [
    {
      "event_type": "delegation_start",
      "timestamp": 1757260801.0,
      "agent": "kublai",
      "metadata": {}
    }
  ],
  "neo4j_queries": [],
  "agents_observed": ["kublai", "mongke"],
  "architecture_spec": {...}
}
```

## Validation Findings

The validator produces:

- **Validations**: Expected behaviors that were observed
- **Warnings**: Missing expected agents or behaviors
- **Violations**: Timing or behavior deviations from spec
- **Metrics**: Quantitative measurements (latency, counts, etc.)

## Adding New Scenarios

Add scenarios to `INTERACTIVE_TEST_SCENARIOS` in `test_scenarios.py`:

```python
TestScenario(
    name="My New Scenario",
    description="What this scenario tests",
    user_message="The user message to send",
    expected_agents=["kublai", "mongke"],
    expected_workflow_steps=[
        "Step 1",
        "Step 2",
    ],
    expected_duration_range=(10, 60),
    success_criteria=[
        "Criterion 1",
        "Criterion 2",
    ],
)
```

## Regression Testing

Compare sessions over time to detect regressions:

```bash
python tests/interactive/run_interactive_tests.py compare \
    sessions/baseline.json \
    sessions/current.json
```

Output shows:
- Duration differences
- Agent participation changes
- Message count differences
- Neo4j query variations

## Architecture Specification

The validator loads expectations from:
- `ARCHITECTURE.md` - System architecture
- `neo4j.md` - Memory operations
- `kurultai_0.2.md` - Agent workflows

If not found, uses default expectations.

## Integration with CI/CD

These tests are designed for **manual execution** due to the interactive nature of chat-based testing. However, saved sessions can be:

1. Archived as baselines
2. Compared programmatically in CI
3. Used to generate coverage reports
