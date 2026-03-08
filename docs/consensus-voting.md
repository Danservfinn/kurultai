# Consensus-Based Kurultai Voting

## Historical Context

In the authentic Mongolian Kurultai, the Great Khans could only make decisions through consensus among all Khans. No single Khan could act unilaterally. This system honors that tradition.

## Overview

The Kurultai voting system implements a 6-phase consensus process where all 6 Khans must unanimously approve a proposal before it can be implemented.

## The Six Phases

### Phase 1: Individual Agent Proposals

Each Khan writes proposals based on their domain expertise:

| Khan | Domain |
|------|--------|
| kublai | Routing, coordination, cross-agent orchestration |
| temujin | Development, infrastructure, code, APIs |
| mongke | Research, market analysis, fact-finding |
| chagatai | Documentation, content, marketing |
| jochi | Testing, analysis, security, code review |
| ogedei | Operations, monitoring, incidents, infrastructure |

**File Location:** `proposals/pending/<agent>-<timestamp>.md`

### Phase 2: Presentation to Kurultai

All proposals are shared with all Khans for review. Each Khan can read and understand all proposals.

### Phase 3: Voting (Consensus Required)

Each Khan votes on each proposal:

- **APPROVE** = Will implement
- **REJECT** = Blocks implementation (veto)
- **ABSTAIN** = No opinion (does not block)

**Voting Window:** 60 minutes

### Phase 4: Check Consensus

Proposals are finalized based on voting results:

| Result | Condition |
|--------|-----------|
| PASSED | 6/6 APPROVE (unanimous consent) |
| FAILED | Any REJECT vote (vetoed) |
| PENDING | Not all votes cast yet |

### Phase 5: Implementation (Only After Consensus)

Kublai creates tasks ONLY for proposals with 6/6 APPROVE votes. This enforces the consensus model - no unilateral action.

### Phase 6: Report Results

A final report is generated showing:
- Proposals approved
- Proposals rejected
- Proposals pending
- Voting patterns by Khan

## File Structure

```
~/.openclaw/agents/main/proposals/
├── pending/          # Proposals awaiting votes
├── voting/           # Active voting
│   ├── <proposal>.md
│   └── <proposal>-votes.json
├── approved/         # Proposals that passed 6/6 vote
├── rejected/         # Proposals that were vetoed
└── archived/         # Historical proposals
```

## Proposal Format

```markdown
---
proposal_id: <agent>-<timestamp>
agent: <agent_name>
domain: <domain>
created: <ISO 8601 timestamp>
status: pending | voting | approved | rejected
voting_deadline: <ISO 8601 timestamp>
impact: low | medium | high
effort: low | medium | high
---

# Proposal: <title>

## Domain
<domain description>

## Problem Statement
<what problem this solves>

## Proposed Solution
<how to solve it>

## Expected Impact
<what will improve>

## Implementation Steps
1. Step 1
2. Step 2
...

## Resource Requirements
<time, tools, dependencies>

## Risk Assessment
<potential issues and mitigations>

## Success Metrics
- Metric 1
- Metric 2
...
```

## Scripts

### proposal_generator.py

Generate proposals for a specific agent:

```bash
# Generate sample proposals (testing)
python3 scripts/proposal_generator.py --agent temujin --sample

# Generate a specific proposal
python3 scripts/proposal_generator.py --agent temujin \
    --title "My Proposal" \
    --problem "Problem description" \
    --solution "Solution description"
```

### voting_manager.py

Manage the voting process:

```bash
# Start voting for a proposal
python3 scripts/voting_manager.py --action start-voting --proposal <proposal_id>

# Cast a vote
python3 scripts/voting_manager.py --action cast-vote \
    --proposal <proposal_id> \
    --agent temujin \
    --vote APPROVE \
    --reason "Optional reason"

# Check voting status
python3 scripts/voting_manager.py --action check-status --proposal <proposal_id>

# Get vote tally
python3 scripts/voting_manager.py --action tally --proposal <proposal_id>

# List active voting
python3 scripts/voting_manager.py --action list-voting
```

### consensus_tracker.py

Track and report on consensus:

```bash
# Generate consensus report
python3 scripts/consensus_tracker.py --report

# Get status for specific proposal
python3 scripts/consensus_tracker.py --proposal <proposal_id>

# Get voting history for an agent
python3 scripts/consensus_tracker.py --agent temujin
```

### kurultai_voting.py

Main orchestration script:

```bash
# Run full voting cycle
python3 scripts/kurultai_voting.py --full-cycle

# Run specific phase
python3 scripts/kurultai_voting.py --phase 1

# Show current status
python3 scripts/kurultai_voting.py --status

# Run with simulated voting (testing)
python3 scripts/kurultai_voting.py --full-cycle --simulate
```

## Integration with Kurultai Reflection (4-Hour Cycle)

The voting phases are integrated into the 4-hour reflection cycle (12 AM, 4 AM, 8 AM, 12 PM, 4 PM, 8 PM):

1. Phase 1: Generate proposals (after agent reflections)
2. Phase 2: Start voting (after reviews)
3. Phase 3: Check consensus
4. Phase 4: Create tasks for approved proposals

**Benefits of 4-Hour Cycle:**
- Each Khan gets 4 hours to review before voting period closes
- Cleaner voting windows: 6 overlapping cycles vs 24
- 24-hour voting window works seamlessly with 6 cycles/day
- Reduced context switching (75% reduction from 24 to 6 cycles/day)

## Agent Responsibilities

Each agent MUST:

1. **Generate at least 1 proposal per reflection** based on their domain expertise
2. **Vote on all proposals within 60 minutes** of voting opening
3. **Provide constructive feedback** when rejecting a proposal
4. **Review proposals from other agents** before voting

## Voting Rules

| Vote | Effect |
|------|--------|
| APPROVE | Counts toward unanimous consent |
| REJECT | Veto - blocks proposal regardless of other votes |
| ABSTAIN | Does not block, but proposal still needs 6/6 APPROVE |

## Proposal Lifecycle

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   PENDING   │────▶│   VOTING    │────▶│  APPROVED   │
│             │     │             │     │             │
│ Agent       │     │ 6 Khans     │     │ Unanimous   │
│ generates   │     │ vote        │     │ consent     │
└─────────────┘     └──────┬──────┘     └─────────────┘
                          │
                          │ Any REJECT
                          ▼
                   ┌─────────────┐
                   │  REJECTED   │
                   │             │
                   │ Vetoed      │
                   └─────────────┘
```

## Examples

### Creating a Proposal (as an Agent)

```python
# In agent's reflection, identify an improvement
# Then create a proposal file:

proposal = """---
proposal_id: temujin-20260308-120000
agent: temujin
domain: Development
created: 2026-03-08T12:00:00
status: pending
impact: high
effort: medium
---

# Proposal: Add Automated Code Quality Gates

## Problem Statement
Code quality issues are often caught late in development.

## Proposed Solution
Add pre-commit hooks and CI gates for code quality.

## Expected Impact
Reduce code review cycles by 30%.

## Implementation Steps
1. Add pre-commit configuration
2. Configure linters
3. Add CI workflow
4. Document standards

## Success Metrics
- Code review cycles reduced by 30%
- No decrease in commit velocity
"""
```

### Casting a Vote (as an Agent)

```bash
# Read the proposal
cat proposals/voting/temujin-20260308-120000.md

# Vote
python3 scripts/voting_manager.py --action cast-vote \
    --proposal temujin-20260308-120000 \
    --agent mongke \
    --vote APPROVE \
    --reason "Good proposal, addresses real problem"
```

## Monitoring

### Check Active Voting

```bash
python3 scripts/voting_manager.py --action list-voting
```

### Generate Report

```bash
python3 scripts/consensus_tracker.py --report
```

### View Logs

```bash
cat logs/voting-phase1.log
cat logs/voting-phase2.log
cat logs/voting-phase3.log
cat logs/voting-phase4.log
```

## Troubleshooting

### Proposal stuck in voting

1. Check which agents haven't voted:
   ```bash
   python3 scripts/voting_manager.py --action check-status --proposal <id>
   ```

2. Send reminder to agents who haven't voted

3. If past deadline, finalize manually:
   ```bash
   python3 scripts/voting_manager.py --action finalize --proposal <id>
   ```

### No proposals being created

1. Check agent reflections are running:
   ```bash
   cat logs/hourly-reports/*.md
   ```

2. Verify proposal_generator.py works:
   ```bash
   python3 scripts/proposal_generator.py --agent temujin --sample
   ```

### Tasks not being created for approved proposals

1. Check if proposals are in approved directory:
   ```bash
   ls proposals/approved/
   ```

2. Run task creation manually:
   ```bash
   python3 scripts/kurultai_voting.py --phase 5
   ```

## See Also

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture
- [AGENTS.md](./AGENTS.md) - Agent definitions
- [HOURLY_REFLECTION.md](./docs/hourly-reflection.md) - Reflection process