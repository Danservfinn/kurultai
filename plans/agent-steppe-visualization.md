# 3D Mongolian Steppe Agent Visualization

## Vision

An interactive 3D visualization of the Mongolian steppe where each agent (Kublai, Mongke, Ogedei, Temujin, Jochi, Chagatai) appears as a distinct character on the landscape. Users can zoom, pan, and click on agents to see their current work, status, and recent activities.

## Architecture

### Tech Stack
- **Framework**: React 19 + TypeScript
- **3D Engine**: Three.js + React Three Fiber (@react-three/fiber)
- **3D Helpers**: React Three Drei (@react-three/drei) - for camera controls, environment
- **State Management**: Zustand (lightweight, perfect for game-like state)
- **Styling**: Tailwind CSS + shadcn/ui for UI overlays
- **Animations**: Framer Motion for UI, R3F for 3D animations
- **Data**: Real-time agent status from file system / API

### Core Components

```
app/
├── page.tsx                    # Main 3D canvas page
├── layout.tsx                  # Root layout
├── globals.css                 # Global styles
├── components/
│   ├── SteppeScene.tsx         # Main 3D scene container
│   ├── Terrain.tsx             # Mongolian steppe terrain
│   ├── Agent.tsx               # Individual agent character
│   ├── AgentCamp.tsx           # Agent's workspace area
│   ├── CameraController.tsx    # Camera movement & zoom
│   ├── SkyEnvironment.tsx      # Sky, lighting, atmosphere
│   ├── ParticleEffects.tsx     # Dust, wind, fire effects
│   └── UI/
│       ├── AgentDetailPanel.tsx    # Slide-out agent details
│       ├── AgentStatusBadge.tsx    # Floating status indicator
│       ├── ActivityLog.tsx         # Recent work timeline
│       ├── MiniMap.tsx             # Overview map
│       └── Legend.tsx              # Agent role key
├── hooks/
│   ├── useAgentData.ts         # Fetch agent status & work
│   ├── useCamera.ts            # Camera control hook
│   └── useSteppeAudio.ts       # Ambient sound management
├── stores/
│   └── agentStore.ts           # Zustand store for agent state
├── types/
│   └── agents.ts               # TypeScript definitions
└── lib/
    ├── agents.ts               # Agent configuration & metadata
    └── utils.ts                # Utilities
```

## Agent Characters & Placement

### Visual Design
Each agent has a distinct visual identity inspired by Mongolian culture:

| Agent | Role | Visual | Camp Location | Color Theme |
|-------|------|--------|---------------|-------------|
| **Kublai** | Coordinator | Seated on elevated platform, reviewing scrolls | Center plateau | Gold/Royal Blue |
| **Mongke** | Researcher | With telescope, surrounded by scrolls/maps | Eastern hills (sunrise) | Deep Blue/Silver |
| **Ogedei** | Writer | At writing desk with quill, papers flying | Near river | Green/Brown |
| **Temujin** | Developer | With tools, armor, defensive position | Northern rocky outcrop | Steel/Red |
| **Jochi** | Analyst | With charts, counting frames | Western plateau | Purple/Gold |
| **Chagatai** | Operations | With organizational tools, schedules | Southern valley | Orange/Bronze |

### 3D Models (Simplified Approach)
Use stylized low-poly representations:
- **Base**: Simple geometric shapes (cylinders, spheres, boxes)
- **Animations**: Idle breathing, working motions, status indicators
- **No external models needed** - everything procedural/geometry-based

## Data Model

```typescript
interface Agent {
  id: string;
  name: string;
  role: 'coordinator' | 'researcher' | 'writer' | 'developer' | 'analyst' | 'operations';
  position: { x: number; z: number }; // 3D world position
  status: 'idle' | 'working' | 'reviewing' | 'alert';
  currentTask?: {
    title: string;
    description: string;
    progress: number;
    startedAt: Date;
  };
  recentActivity: Activity[];
  metrics: {
    tasksCompleted: number;
    itemsProduced: number;
    lastActive: Date;
  };
}

interface Activity {
  id: string;
  type: 'research' | 'content' | 'code' | 'analysis' | 'operations';
  title: string;
  timestamp: Date;
  details: string;
  deliverablePath?: string;
}
```

## Data Sources

### File System Watcher
Monitor `/data/workspace/deliverables/` for real-time updates:
- `research/` → Mongke's activity
- `content/` → Ogedei's activity
- `security/`, `code-review/` → Temujin's activity
- `analytics/` → Jochi's activity

### API Endpoint (Optional)
```typescript
// /api/agents/status
{
  agents: Agent[];
  lastUpdated: Date;
  systemStatus: 'healthy' | 'degraded' | 'down';
}
```

## User Interactions

### Camera Controls
- **Orbit**: Drag to rotate around the steppe
- **Zoom**: Scroll to zoom in/out
- **Focus**: Double-click agent to zoom to them
- **Reset**: Button to return to overview

### Agent Interaction
- **Hover**: Show agent name + current task tooltip
- **Click**: Open detail panel with full activity log
- **Follow**: Camera follows agent as they work

### Detail Panel Contents
```
┌─────────────────────────────────────┐
│  [Avatar] Kublai - Coordinator      │
│  Status: 🟢 Working                 │
├─────────────────────────────────────┤
│  CURRENT TASK                       │
│  Reviewing Ogedei's content draft   │
│  Progress: [████████░░] 80%         │
│  Started: 2 hours ago               │
├─────────────────────────────────────┤
│  RECENT ACTIVITY                    │
│  • Approved 3 content pieces        │
│  • Routed research to Mongke        │
│  • Security alert from Temujin      │
├─────────────────────────────────────┤
│  METRICS (Today)                    │
│  Tasks Completed: 12                │
│  Items Reviewed: 8                  │
│  Active Time: 6h 23m                │
└─────────────────────────────────────┘
```

## Visual Effects

### Environment
- **Terrain**: Rolling grasslands with subtle elevation
- **Sky**: Dynamic day/night cycle or fixed golden hour
- **Weather**: Gentle wind particles, occasional dust
- **Lighting**: Warm sunlight, agent campfires at night

### Agent Camps
Each agent has a themed workspace:
- **Kublai**: Command yurt with banners
- **Mongke**: Observatory with scrolls scattered
- **Ogedei**: Writing tent with paper stacks
- **Temujin**: Forge/workshop with tools
- **Jochi**: Counting house with abacuses
- **Chagatai**: Organizational tent with schedules

### Status Indicators
- **Working**: Subtle glow, animated tools
- **Idle**: Gentle breathing, looking around
- **Alert**: Red pulse, urgent animation
- **Reviewing**: Thoughtful pose, examining items

## Implementation Phases

### Phase 1: Foundation (Day 1)
- [ ] Set up Next.js 15 + React 19 + TypeScript project
- [ ] Install Three.js, React Three Fiber, Drei
- [ ] Create basic terrain geometry
- [ ] Add orbit camera controls
- [ ] Simple sky/sunset environment

### Phase 2: Agents (Day 2)
- [ ] Create Agent component with basic geometry
- [ ] Position all 6 agents on the steppe
- [ ] Add idle animations (breathing, subtle movement)
- [ ] Implement hover tooltips
- [ ] Click to focus camera on agent

### Phase 3: Data Integration (Day 3)
- [ ] Create file system watcher for deliverables
- [ ] Build agent data store (Zustand)
- [ ] Map file changes to agent activities
- [ ] Add status calculation logic
- [ ] Create API endpoint for agent status

### Phase 4: UI Polish (Day 4)
- [ ] Build AgentDetailPanel slide-out
- [ ] Create activity timeline component
- [ ] Add metrics display
- [ ] Implement MiniMap
- [ ] Add Legend/role key

### Phase 5: Visual Polish (Day 5)
- [ ] Agent camp details (yurts, tools, etc.)
- [ ] Particle effects (dust, wind)
- [ ] Lighting improvements
- [ ] Status glow effects
- [ ] Working animation states

### Phase 6: Deployment (Day 6)
- [ ] Build optimization
- [ ] Environment configuration
- [ ] Railway deployment
- [ ] Domain setup (steppe.kurult.ai)

## Technical Considerations

### Performance
- Use `InstancedMesh` for grass/terrain details
- Limit shadow quality on mobile
- Lazy load detail panel data
- Debounce file system watchers

### Accessibility
- Keyboard navigation (Tab between agents)
- Screen reader support for agent status
- High contrast mode option
- Reduced motion preference

### Mobile
- Touch controls for camera
- Simplified effects on low-power devices
- Bottom sheet for detail panel

## File Structure

```
agent-steppe-visualization/
├── app/
│   ├── page.tsx
│   ├── layout.tsx
│   ├── globals.css
│   ├── components/
│   │   ├── SteppeScene.tsx
│   │   ├── Terrain.tsx
│   │   ├── Agent.tsx
│   │   ├── AgentCamp.tsx
│   │   ├── CameraController.tsx
│   │   ├── SkyEnvironment.tsx
│   │   ├── ParticleEffects.tsx
│   │   └── UI/
│   │       ├── AgentDetailPanel.tsx
│   │       ├── AgentStatusBadge.tsx
│   │       ├── ActivityLog.tsx
│   │       ├── MiniMap.tsx
│   │       └── Legend.tsx
│   ├── hooks/
│   │   ├── useAgentData.ts
│   │   ├── useCamera.ts
│   │   └── useSteppeAudio.ts
│   ├── stores/
│   │   └── agentStore.ts
│   ├── types/
│   │   └── agents.ts
│   ├── lib/
│   │   ├── agents.ts
│   │   └── utils.ts
│   └── api/
│       └── agents/
│           └── route.ts
├── components/ui/          # shadcn components
├── public/
│   └── textures/           # Terrain textures (optional)
├── next.config.js
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

## Dependencies

```json
{
  "dependencies": {
    "next": "15.x",
    "react": "19.x",
    "react-dom": "19.x",
    "three": "^0.160.0",
    "@react-three/fiber": "^8.15.0",
    "@react-three/drei": "^9.92.0",
    "zustand": "^4.4.0",
    "framer-motion": "^10.16.0",
    "chokidar": "^3.5.3",
    "date-fns": "^3.0.0",
    "lucide-react": "latest"
  }
}
```

## Next Steps

1. **Review this plan** - Confirm scope and priorities
2. **Initialize project** - Run `npx shadcn@latest init`
3. **Install 3D dependencies** - Three.js, R3F, Drei
4. **Create terrain prototype** - Basic steppe landscape
5. **Add first agent** - Kublai in the center
6. **Iterate and expand** - Add remaining agents, data integration

## Future Enhancements

- **Real-time collaboration**: Show when multiple agents work together
- **Historical playback**: Rewind to see past activity
- **Task routing visualization**: Animated lines showing handoffs
- **Weather effects**: Rain, snow based on real weather
- **Day/night cycle**: Match user's local time
- **Sound design**: Ambient steppe sounds, agent-specific audio cues
- **VR support**: Immersive 3D experience

---

*This visualization transforms abstract agent work into a living, breathing scene - the Mongol empire of AI agents, each at their post on the endless steppe.*
