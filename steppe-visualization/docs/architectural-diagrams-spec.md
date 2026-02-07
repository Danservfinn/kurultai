# Kurultai Multi-Agent System: Architectural Diagrams Specification

## Overview

This document provides detailed specifications for 4 interactive architectural diagrams to visualize the Kurultai multi-agent system on the Mission Control webpage. These diagrams will complement the existing 3D Steppe visualization and control panel.

---

## Brand Foundation

### Visual Identity
- **Theme**: Mongol Empire meets modern tech - combining historical steppe aesthetics with clean, professional data visualization
- **Mood**: Authoritative yet approachable, organized complexity, dynamic collaboration
- **Style**: Modern dashboard with subtle historical accents (geometric patterns inspired by Mongol textiles, clean lines)

### Color Palette

#### Primary Colors
| Color | Hex | Usage |
|-------|-----|-------|
| Imperial Gold | `#FFD700` | Kublai (coordinator), primary highlights, CTAs |
| Steppe Blue | `#1E40AF` | Möngke (researcher), information elements |
| Sage Green | `#228B22` | Temüjin (developer), success states |
| Sunset Orange | `#EA580C` | Chagatai (operations), warnings, activity |
| Royal Purple | `#7C3AED` | Jochi (analyst), data visualization |
| Amber | `#F39C12` | Ögedei (writer/ops), notifications |

#### Neutral Colors
| Color | Hex | Usage |
|-------|-----|-------|
| Dark Slate | `#0F172A` | Primary background |
| Slate 800 | `#1E293B` | Card backgrounds |
| Slate 700 | `#334155` | Borders, dividers |
| Slate 400 | `#94A3B8` | Secondary text |
| Slate 200 | `#E2E8F0` | Primary text |
| White | `#FFFFFF` | Headings, emphasis |

#### Semantic Colors
| Color | Hex | Usage |
|-------|-----|-------|
| Success Green | `#10B981` | Online, completed, healthy |
| Warning Amber | `#F59E0B` | Idle, pending, attention |
| Error Red | `#EF4444` | Blocked, error, offline |
| Info Blue | `#3B82F6` | Active, in-progress |

### Typography
- **Headings**: Inter, 600-700 weight
- **Body**: Inter, 400-500 weight
- **Monospace**: JetBrains Mono for data/timestamps
- **Scale**: 12px (labels), 14px (body), 16px (subheadings), 20-24px (headings), 32px+ (hero numbers)

### Spacing & Layout
- **Container max-width**: 1920px
- **Grid**: 12-column system
- **Gap scale**: 4px, 8px, 12px, 16px, 24px, 32px, 48px
- **Border radius**: 8px (cards), 12px (panels), 24px+ (hero elements)
- **Shadows**: Subtle depth with colored glows for active states

---

## Diagram 1: System Overview Diagram

### Purpose
Show all 6 agents and their hierarchical relationships in the Kurultai system. Illustrates Kublai as the central coordinator with 5 specialist agents.

### Visual Style
- **Type**: Radial network diagram / Org chart hybrid
- **Layout**: Kublai at center, 5 specialists arranged in a pentagon around
- **Style**: Modern node-link diagram with glowing connection lines

### Structure
```
                    [Möngke]
                   Researcher
                       |
                       |
    [Jochi] --------[Kublai]-------- [Temüjin]
   Analyst       Coordinator        Developer
                       |
                       |
                   [Chagatai]
                  Operations
                       |
                   [Ögedei]
                  Writer/Ops
```

### Key Elements

#### Nodes (Agent Cards)
- **Size**: 120x80px for specialists, 160x100px for Kublai
- **Shape**: Rounded rectangle (16px radius)
- **Content**:
  - Avatar/icon (40px circle with agent color)
  - Agent name (bold, 14px)
  - Role label (12px, muted)
  - Status indicator (8px dot, animated pulse when active)
- **Background**: Slate 800 with subtle gradient
- **Border**: 2px solid with agent's primary color
- **Shadow**: Colored glow matching agent color (0 0 20px rgba(color, 0.3))

#### Connection Lines
- **Style**: Curved bezier paths
- **Color**: Gradient from source to target agent color
- **Width**: 2px default, 4px on hover
- **Animation**: Subtle pulse traveling from Kublai to specialists (representing delegation)

#### Central Hub (Kublai)
- **Visual distinction**: Larger size, golden glow, crown icon
- **Animation**: Gentle pulsing glow to indicate coordinator role
- **Connections**: 5 primary links to specialists

### Interactivity

#### Hover States
- **Node hover**: Scale 1.05, enhanced glow, show tooltip
- **Tooltip content**:
  - Full agent name
  - Current status
  - Active task count
  - Capabilities list
  - "Click to view details" hint

#### Click Actions
- Click agent: Open agent detail panel (reuse existing AgentDetailPanel)
- Click connection: Show relationship info (delegation patterns, message frequency)

#### Animation Sequence (On Load)
1. Kublai node fades in with glow (0.5s)
2. Connection lines draw outward (0.3s each, staggered 0.1s)
3. Specialist nodes pop in with bounce (0.3s each, staggered)
4. Continuous: Subtle pulse animation on active agent connections

### Accessibility
- **ARIA**: `role="img"`, `aria-label="System architecture showing 6 agents with Kublai as coordinator"`
- **Keyboard**: Tab navigation through nodes, Enter to select
- **Screen reader**: Announce agent name, role, and status on focus
- **Color contrast**: All text meets WCAG 4.5:1 ratio
- **Motion**: Respect `prefers-reduced-motion` for animations

### Implementation Notes
- Use D3.js or React Flow for layout engine
- Responsive: Stack vertically on mobile, radial on desktop
- Data source: `/api/agents` endpoint

---

## Diagram 2: Two-Tier Memory Visualization

### Purpose
Illustrate the dual memory architecture: Personal files (Kublai only) vs Shared Neo4j graph database (all agents).

### Visual Style
- **Type**: Split-view layered diagram with toggle
- **Layout**: Side-by-side comparison with visual metaphor
- **Style**: Cloud/hexagon shapes for memory stores, flowing particles for data

### Structure

#### Left Panel: Personal Memory (Kublai)
- **Visual metaphor**: Private vault / personal yurt
- **Icon**: Shield or lock icon with Kublai's gold color
- **Label**: "Personal Memory (Kublai Only)"
- **Contents visualization**:
  - File icons representing personal notes
  - Folder structure (simplified)
  - "Private" badge

#### Right Panel: Shared Memory (Neo4j)
- **Visual metaphor**: Connected network cloud / public archive
- **Icon**: Database/graph icon with blue/purple gradient
- **Label**: "Shared Memory (All Agents)"
- **Contents visualization**:
  - Node graph preview (simplified Neo4j nodes)
  - Connection lines between nodes
  - Agent avatars around the perimeter

#### Center Bridge
- **Visual**: Bidirectional arrow with access indicator
- **Shows**: Kublai can access both, specialists only access shared
- **Animation**: Data particles flowing between systems

### Key Elements

#### Memory Tier Cards
```
+------------------------+        +------------------------+
|     PERSONAL MEMORY    |  <---> |     SHARED MEMORY      |
|     (Kublai Only)      |        |    (All Agents)        |
|                        |        |                        |
|   [File] [File] [File] |        |    [Node]--[Node]      |
|   [File] [Folder]      |        |       \    /           |
|                        |        |      [Node]--[Node]    |
|   Capacity: 2.4 MB     |        |   Nodes: 1,247         |
|   Files: 12            |        |   Relationships: 3,892 |
+------------------------+        +------------------------+
```

#### Visual Details
- **Personal tier**: Warm tones (amber/gold), enclosed shape, lock icon
- **Shared tier**: Cool tones (blue/purple), open network shape, share icon
- **Connection**: Animated dashed line with flowing dots

### Interactivity

#### Toggle Views
- **Tab buttons**: "Personal", "Shared", "Both" (default: Both)
- **Animation**: Smooth crossfade between views (0.3s)

#### Hover States
- **Personal files**: Show file name, size, last modified
- **Shared nodes**: Show node type, connected agents, creation date
- **Bridge**: Show sync status, last sync time

#### Click Actions
- Click personal file: Open file preview modal
- Click shared node: Show node details, connected data
- Click "View Full Graph": Link to Neo4j Browser or detailed view

#### Animation Sequence
1. Both panels slide in from sides (0.5s)
2. Contents fade in with stagger (0.1s per item)
3. Bridge connection draws between them (0.3s)
4. Continuous: Subtle particle flow along bridge

### Data Display
- **Personal stats**: File count, total size, recent files
- **Shared stats**: Node count, relationship count, recent additions
- **Sync status**: Last sync time, pending changes indicator

### Accessibility
- **ARIA**: `role="region"`, labeled sections for each memory tier
- **Keyboard**: Tab between panels, arrow keys navigate items
- **Screen reader**: Announce memory type, statistics, and access permissions
- **Visual**: Clear labels, icons reinforce meaning

---

## Diagram 3: Task Delegation Flow

### Purpose
Show how a user request flows through the system: from user input through Kublai to specialists, then to Neo4j storage, and back as synthesized response.

### Visual Style
- **Type**: Horizontal flowchart with animated sequence
- **Layout**: Left-to-right timeline with branching
- **Style**: Step cards connected by animated paths

### Structure

#### Flow Stages
```
[User Request] -> [Kublai] -> [Analysis] -> [Delegation] -> [Specialists] -> [Neo4j] -> [Synthesis] -> [Response]
                    |              |              |              |              |              |
                 Receive      Parse intent   Route task    Execute      Store         Combine
                 input        Determine      to agent      work         results       & format
                              specialist
```

#### Detailed Flow
1. **User Input** - Text input icon
2. **Kublai Router** - Central hub with routing logic
3. **Intent Analysis** - Magnifying glass/brain icon
4. **Task Delegation** - Branching arrows to specialists
5. **Specialist Execution** - 5 parallel tracks
6. **Neo4j Storage** - Database write icon
7. **Kublai Synthesis** - Merge/combine icon
8. **User Response** - Output/chat bubble icon

### Key Elements

#### Step Nodes
- **Size**: 80px circle for main steps, 60px for substeps
- **Style**: Outlined circle with icon, fills when active
- **States**:
  - Pending: Gray outline, 30% opacity
  - Active: Colored fill, pulsing glow
  - Complete: Solid color, checkmark

#### Connection Paths
- **Style**: Horizontal lines with directional arrows
- **Branching**: From Kublai, 5 paths to specialists (fan out)
- **Merging**: From specialists, converge back to Kublai

#### Specialist Tracks
- **Visual**: 5 horizontal mini-flows stacked
- **Each track**: Agent avatar -> Working -> Complete check
- **Animation**: Progress bar filling during "working" phase

### Interactivity

#### Playback Controls
- **Play/Pause**: Start/stop the animation
- **Step forward/back**: Navigate manually
- **Reset**: Return to beginning
- **Speed**: 1x, 2x, 0.5x speed options

#### Step-by-Step Mode
- Click any step to pause and see details:
  - Step description
  - Time estimate
  - Current agent responsible
  - Data being processed

#### Hover States
- **Step hover**: Preview what happens at this stage
- **Path hover**: Highlight the full flow path
- **Agent track**: Show agent's specific responsibilities

#### Animation Sequence (Full Play)
1. User input pulses (1s)
2. Arrow draws to Kublai (0.5s)
3. Kublai activates, routing logic shows (1s)
4. Arrows fan out to specialists (0.5s)
5. All specialists activate simultaneously (2s working animation)
6. Progress bars fill
7. Arrows converge to Neo4j (0.5s)
8. Database write animation (1s)
9. Arrow to Kublai synthesis (0.5s)
10. Synthesis animation (1s)
11. Final response delivery (0.5s)

### Data Visualization
- **Timing estimates**: Show expected duration per step
- **Parallel execution**: Visual emphasis on concurrent specialist work
- **Bottleneck indicators**: Highlight slow steps

### Accessibility
- **ARIA**: `role="region"`, `aria-live="polite"` for step announcements
- **Keyboard**: Space to play/pause, arrows to step
- **Screen reader**: Announce current step, describe flow direction
- **Visual**: High contrast step states, clear progress indication

---

## Diagram 4: Agent-to-Agent Messaging

### Purpose
Visualize the communication patterns between agents: message types, notification flow, and coordination patterns.

### Visual Style
- **Type**: Sequence diagram / Message flow visualization
- **Layout**: Vertical timeline with horizontal message lines
- **Style**: Clean timeline with animated message packets

### Structure

#### Timeline Layout
```
Time    Kublai    Möngke    Temüjin   Jochi    Chagatai   Ögedei
  |        |         |         |         |         |         |
  |--------|---------|---------|---------|---------|---------|
  |        |         |         |         |         |         |
  |   [====DELEGATION====>]    |         |         |         |
  |        |         |         |         |         |         |
  |        |    [<====PROGRESS====]       |         |         |
  |        |         |         |         |         |         |
  |        |         |    [====BLOCKED====>]        |         |
  |        |         |         |         |         |         |
  |   [<===COMPLETION===]      |         |         |         |
  |        |         |         |         |         |         |
```

#### Message Types (Color Coded)
| Type | Color | Icon | Description |
|------|-------|------|-------------|
| DELEGATION | Gold | Arrow right | Task assignment |
| PROGRESS | Blue | Clock | Status update |
| COMPLETION | Green | Check | Task finished |
| BLOCKED | Red | X | Issue/escalation |
| INSIGHT | Purple | Lightbulb | New discovery |
| COORDINATION | Orange | Sync | Sync request |

### Key Elements

#### Agent Lanes
- **Vertical tracks**: One per agent, labeled with avatar and name
- **Style**: Subtle background color matching agent theme
- **Width**: Equal spacing, ~120px per lane

#### Message Lines
- **Horizontal arrows**: From sender to receiver
- **Style**: Solid line with arrowhead
- **Color**: Matches message type
- **Animation**: Packet/dot travels along path

#### Message Packets
- **Shape**: Rounded pill with icon
- **Content**: Message type label
- **Animation**: Move along path from sender to receiver
- **Duration**: Proportional to "delivery time"

### Interactivity

#### Playback Controls
- **Play message flow**: Animate messages in sequence
- **Pause**: Freeze current state
- **Scrubber**: Drag to any point in timeline
- **Filter**: Show only specific message types

#### Message Details
- **Click message**: Show full details in panel:
  - Message type
  - From/To agents
  - Timestamp
  - Content preview
  - Related task

#### Hover States
- **Message hover**: Highlight full path, show tooltip summary
- **Agent lane hover**: Filter to show only their messages
- **Time point hover**: Show all messages at that moment

#### Animation Sequence
1. Timeline draws from top to bottom (0.5s)
2. Agent lanes fade in (0.3s)
3. Messages appear in chronological order:
   - Message packet spawns at sender (0.2s)
   - Travels along path (0.5s)
   - Arrives at receiver, brief glow (0.3s)
4. Loop or pause at end

### Real-time Mode
- **Live view**: Show actual messages from `/api/notifications`
- **Recent history**: Last 50 messages
- **Auto-scroll**: Keep newest messages visible

### Data Visualization
- **Message volume**: Line thickness or packet size by frequency
- **Response times**: Gaps between request/response
- **Hot paths**: Highlight most active communication channels

### Accessibility
- **ARIA**: `role="log"` for message stream, `aria-live="polite"`
- **Keyboard**: Tab through messages, Enter to view details
- **Screen reader**: Announce "[Type] message from [Agent] to [Agent]"
- **Visual**: Color + icon + label for message types (not color alone)

---

## Component Architecture

### Shared Components

#### AgentAvatar
```typescript
interface AgentAvatarProps {
  agentId: string;
  size: 'sm' | 'md' | 'lg';
  showStatus?: boolean;
  animate?: boolean;
}
```

#### StatusIndicator
```typescript
interface StatusIndicatorProps {
  status: AgentStatus;
  size: 'sm' | 'md' | 'lg';
  pulse?: boolean;
}
```

#### ConnectionLine
```typescript
interface ConnectionLineProps {
  from: { x: number; y: number };
  to: { x: number; y: number };
  color: string;
  animated?: boolean;
  thickness?: number;
  style: 'solid' | 'dashed' | 'dotted';
}
```

#### Tooltip
```typescript
interface TooltipProps {
  content: React.ReactNode;
  position: 'top' | 'bottom' | 'left' | 'right';
  delay?: number;
}
```

### Diagram-Specific Components

Each diagram will be a self-contained React component:
- `SystemOverviewDiagram`
- `MemoryVisualization`
- `TaskDelegationFlow`
- `AgentMessagingDiagram`

### Animation Library
- **Framer Motion**: For React component animations
- **D3.js**: For complex layouts and data-driven graphics
- **CSS Animations**: For simple transitions and pulsing effects

---

## Responsive Behavior

### Breakpoints
| Breakpoint | Layout Adjustments |
|------------|-------------------|
| Desktop (1280px+) | Full diagrams side-by-side |
| Laptop (1024px) | 2x2 grid of diagrams |
| Tablet (768px) | Single column, stacked |
| Mobile (<768px) | Simplified views, vertical layouts |

### Mobile Adaptations
- **System Overview**: Vertical stack instead of radial
- **Memory Viz**: Tabbed interface instead of side-by-side
- **Task Flow**: Vertical flow (top to bottom)
- **Messaging**: Collapsible agent lanes

---

## Integration with Existing System

### Data Sources
```
/api/agents          -> Agent definitions, status
/api/tasks           -> Task flow data
/api/notifications   -> Message flow data
/api/memory-stats    -> Memory visualization data
/api/collaborations  -> Connection patterns
```

### State Management
- Use existing `useAgentStore` for agent data
- Local state for diagram interactions (selection, playback)
- Real-time updates via existing polling mechanism

### Navigation
- Add "Architecture" tab to Mission Control
- Deep links: `/control-panel/architecture/[diagram-id]`
- Cross-link: Click agent in diagram -> scroll to AgentStatusCard

---

## Implementation Phases

### Phase 1: System Overview
- Radial layout engine
- Agent nodes with hover states
- Basic connection lines

### Phase 2: Memory Visualization
- Split-view layout
- File/node representations
- Toggle interactions

### Phase 3: Task Delegation Flow
- Flowchart layout
- Step-by-step animation
- Playback controls

### Phase 4: Agent Messaging
- Timeline layout
- Message packet animations
- Real-time mode

---

## Performance Considerations

### Optimization
- Use `will-change` for animated elements
- Implement `requestAnimationFrame` for smooth animations
- Lazy load diagrams below the fold
- Use CSS transforms instead of position changes

### Accessibility
- Respect `prefers-reduced-motion`
- Provide static alternatives for animations
- Ensure keyboard navigation works
- Test with screen readers

---

## File Structure

```
app/
  control-panel/
    architecture/
      page.tsx                    # Main architecture page
      components/
        SystemOverviewDiagram.tsx
        MemoryVisualization.tsx
        TaskDelegationFlow.tsx
        AgentMessagingDiagram.tsx
        shared/
          AgentAvatar.tsx
          StatusIndicator.tsx
          ConnectionLine.tsx
          DiagramContainer.tsx
          PlaybackControls.tsx
      hooks/
        useDiagramAnimation.ts
        useMessageStream.ts
      types/
        diagrams.ts
      utils/
        layoutEngines.ts
        animations.ts
```

---

## Summary

These 4 diagrams provide comprehensive visualization of the Kurultai multi-agent architecture:

1. **System Overview**: High-level org structure showing agent relationships
2. **Memory Visualization**: Clear separation of personal vs shared memory
3. **Task Delegation Flow**: Step-by-step request processing pipeline
4. **Agent Messaging**: Real-time communication patterns

Each diagram follows consistent visual design, supports full interactivity, and meets accessibility standards. Together they provide both technical understanding and visual appeal for the Mission Control dashboard.
