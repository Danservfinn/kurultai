# Multi-Goal Orchestration Implementation

## Overview

This implementation provides UX patterns and components for AI-driven multi-goal orchestration in the Kublai agent system. It handles goal detection, progress visibility, transparency modes, and natural language commands for mid-course corrections.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    KUBLAI ORCHESTRATOR                       │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Goal Parser  │→ │ Goal Graph   │→ │ Progress     │     │
│  │ (NLP)        │  │ (Synergies)  │  │ Tracker      │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Goal Orchestration Panel                │   │
│  │  • Cards View (default)                              │   │
│  │  • Timeline View                                      │   │
│  │  • Graph View                                         │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Files

- `/Users/kurultai/molt/docs/plans/multi-goal-ux-recommendations.md` - Complete UX recommendations with conversation flows
- `/Users/kurultai/molt/steppe-visualization/app/components/mission-control/GoalOrchestrationPanel.tsx` - React UI component
- `/Users/kurultai/molt/steppe-visualization/app/lib/GoalOrchestrator.ts` - Natural language command parser
- `/Users/kurultai/molt/steppe-visualization/app/lib/GoalOrchestrator.example.ts` - Usage examples

## Key Features

### 1. Goal Detection & Classification

Automatically detects relationships between goals:

- **Independent**: Goals that can run in parallel without conflicts
- **Synergistic**: Goals that benefit each other (earnings + community)
- **Sequential**: Goals where one depends on another
- **Conflicting**: Goals with opposing requirements

```typescript
// Example
const orchestrator = new GoalOrchestrator(goals);
const parsed = orchestrator.parseCommand("prioritize earnings");
// Returns: { type: 'prioritize', targetGoalIds: ['goal-earnings'], confidence: 0.9 }
```

### 2. Transparency Modes

Three levels of detail based on user preference:

**Simple Mode** (Default)
```
🎯 Earn 1,000 USDC
   Progress: 80%
```

**Normal Mode** (Agent attribution)
```
🎯 Earn 1,000 USDC
   Progress: 80%
   Team: @mongke, @temujin, @chagatai
```

**Detailed Mode** (Full breakdown)
```
🎯 Earn 1,000 USDC
   Status: ACTIVE
   Progress: 80%
   Priority: HIGH
   Agents: @mongke (research), @temujin (dev), @chagatai (writing)
   Synergies: Connected to "Start Money-Making Community"
   Deadline: Feb 18, 2026
   Tasks: 8/10 complete
```

### 3. Progress Visibility

Multiple ways to track progress:

- **Progress bars** with percentage indicators
- **Agent avatars** showing who's working on what
- **Synergy indicators** showing related goals
- **Timeline view** with milestone history
- **Daily standup** summaries

### 4. Natural Language Commands

Users can control goals using natural language:

```bash
# Status updates
"status" / "progress" / "how's it going"
"detail [goal name]" / "tell me about [goal]"

# Prioritization
"prioritize [goal]" / "focus on [goal]"
"pause [goal]" / "resume [goal]"
"cancel [goal]" / "remove [goal]"

# Transparency
"show everything" / "show agents" / "show graph"
"headlines mode" / "detailed mode"

# Modification
"change [goal] deadline to [date]"
"increase [goal] target to [amount]"
```

### 5. Complexity Prevention

Prevents overwhelming users by:

- **Smart grouping**: Combines related goals into tracks
- **Progressive disclosure**: Shows details on request
- **Batch updates**: Combines multiple notifications
- **Complexity warnings**: Alerts when too many goals are active

## Usage

### Basic Setup

```typescript
import { GoalOrchestrationPanel } from './components/mission-control/GoalOrchestrationPanel';
import { GoalOrchestrator, createSampleGoals } from './lib/GoalOrchestrator';

function App() {
  const goals = createSampleGoals();
  const agents = [
    { id: 'mongke', name: 'Möngke', specialization: ['research'], capacity: 60 },
    { id: 'temujin', name: 'Temüjin', specialization: ['development'], capacity: 80 },
    // ... more agents
  ];

  const orchestrator = new GoalOrchestrator(goals);

  return (
    <GoalOrchestrationPanel
      goals={goals}
      agents={agents}
      transparencyMode="normal"
      onGoalSelect={(goalId) => console.log('Selected:', goalId)}
      onReprioritize={(goalIds, priority) => console.log('Reprioritize:', goalIds, priority)}
      onPauseGoal={(goalId) => orchestrator.pauseGoal(goalId)}
    />
  );
}
```

### Handling Natural Language Commands

```typescript
const orchestrator = new GoalOrchestrator(goals);

// Parse user input
const parsed = orchestrator.parseCommand("pause community, focus on freelancing");

// Generate response
const response = orchestrator.generateResponse(parsed);
console.log(response);

// Execute action
if (parsed.type === 'pause' && parsed.targetGoalIds) {
  parsed.targetGoalIds.forEach(goalId => {
    // Update goal status to paused
    updateGoalStatus(goalId, 'paused');
  });
}
```

## UX Patterns

### Pattern 1: Immediate Feedback

When Kublai detects synergistic goals:

```
User: Earn 1,000 USDC
User: Start money-making community

Kublai: 💡 These work together—building unified strategy
        Earnings fund community, community amplifies earnings

        📋 INTEGRATED PLAN:
        Week 1: Quick earnings (freelance sprints)
        Week 2: Community MVP launch
        Week 3: Merge (community referral program)

        Starting now. Reply "details" for full agent assignments
```

### Pattern 2: Mid-Course Correction

User changes direction:

```
User: Actually, pause community, focus on freelancing

Kublai: 🔀 Pausing community, accelerating freelancing

        IMPACT:
        @ogedei (ops): Paused Discord setup
        @jochi (analyst): Paused competitor analysis
        @mongke (research): SHIFT to freelancing research
        @chagatai (writer): SHIFT to outreach content

        Freelancing timeline: 2 days faster
        Community: Resumes when freelancing hits $1,000

        Confirm? (yes/no)
```

### Pattern 3: Progress Update

Daily standup format:

```
📊 DAILY STANDUP — Feb 4, 2026

✅ COMPLETED YESTERDAY:
• @mongke: Analyzed 5 freelance platforms
• @ogedei: Configured Discord server
• @temujin: Portfolio template 80% complete

🔄 IN PROGRESS:
• Earnings: 60% complete → Pipeline full
• Community: 40% complete → On track

🚫 BLOCKERS: None

👀 NEEDS INPUT:
• Portfolio color scheme: Blue or Purple?

🎯 TODAY'S PRIORITIES:
1. Finish portfolio template
2. Send first 5 outreach emails
```

## API Reference

### GoalOrchestrator

#### Constructor
```typescript
constructor(goals: Goal[])
```

#### Methods

**parseCommand(input: string): ParsedCommand**
Parse natural language input into structured command.

**generateResponse(command: ParsedCommand): string**
Generate human-readable response for command.

**updateGoals(goals: Goal[]): void**
Update the goal list for parsing and context.

### GoalOrchestrationPanel

#### Props

```typescript
interface GoalOrchestrationPanelProps {
  goals: Goal[];
  agents: AgentRef[];
  synergies?: SynergyEdge[];
  timeline?: TimelineEvent[];
  transparencyMode?: 'simple' | 'normal' | 'detailed';
  onGoalSelect?: (goalId: string) => void;
  onReprioritize?: (goalIds: string[], priority: 'high' | 'medium' | 'low') => void;
  onPauseGoal?: (goalId: string) => void;
  onResumeGoal?: (goalId: string) => void;
  onRemoveGoal?: (goalId: string) => void;
}
```

## Data Models

### Goal
```typescript
interface Goal {
  id: string;
  title: string;
  description: string;
  progress: number; // 0-100
  status: 'active' | 'paused' | 'completed' | 'blocked';
  priority: 'high' | 'medium' | 'low';
  category?: string;
  tags?: string[];
  assignedAgents: string[];
  synergyWith?: string[]; // IDs of related goals
  deadline?: Date;
  createdAt: Date;
}
```

### AgentRef
```typescript
interface AgentRef {
  id: string;
  name: string;
  avatar?: string;
  specialization: string[];
  currentTasks: number;
  capacity: number; // 0-100
}
```

### SynergyEdge
```typescript
interface SynergyEdge {
  source: string; // Goal ID
  target: string; // Goal ID
  type: 'sequential' | 'synergistic' | 'shared-resource';
  strength: number; // 0-1
}
```

## Testing

Run the examples to see the system in action:

```typescript
import { runAllExamples } from './lib/GoalOrchestrator.example';

// Run all examples
runAllExamples();

// Or run specific examples
import { example1_BasicParsing } from './lib/GoalOrchestrator.example';
example1_BasicParsing();
```

## Integration with Kublai

To integrate with the existing Kublai system:

1. **Connect to Signal Channel**: Use the existing Signal integration to send/receive messages
2. **Parse User Messages**: Route user messages through GoalOrchestrator
3. **Update Agent Workloads**: When goals are reprioritized, reassign agents via OpenClaw
4. **Track Progress**: Monitor task completion and update goal progress
5. **Send Notifications**: Use Signal for milestone notifications and daily standups

### Example Signal Integration

```typescript
// In your Signal message handler
async function handleSignalMessage(message: string) {
  const orchestrator = new GoalOrchestrator(currentGoals);

  // Parse the command
  const parsed = orchestrator.parseCommand(message);

  // Generate response
  const response = orchestrator.generateResponse(parsed);

  // Send back via Signal
  await sendSignalMessage(response);

  // Execute the action
  if (parsed.targetGoalIds) {
    await executeGoalAction(parsed.type, parsed.targetGoalIds);
  }
}
```

## Future Enhancements

- [ ] Real-time goal graph visualization with Three.js
- [ ] Agent workload balancing algorithms
- [ ] Predictive timeline estimation (ML-based)
- [ ] Voice command support via Signal
- [ ] Mobile app for on-the-go goal tracking
- [ ] Goal templates for common workflows
- [ ] Performance metrics and goal completion analytics

## Contributing

When adding new features:

1. Update the UX recommendations document first
2. Add examples to GoalOrchestrator.example.ts
3. Update the GoalOrchestrationPanel component
4. Test with sample goals and agents
5. Document new natural language commands

## References

- Main UX doc: `/Users/kurultai/molt/docs/plans/multi-goal-ux-recommendations.md`
- Mission Control: `/Users/kurultai/molt/plans/mission-control-multi-agent.md`
- Steppe Visualization: `/Users/kurultai/molt/steppe-visualization/`
