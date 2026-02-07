# Architectural Diagrams Implementation Guide

## Quick Start

This guide provides implementation steps for the 4 architectural diagrams specified in `architectural-diagrams-spec.md`.

---

## Prerequisites

```bash
# Install required dependencies
npm install framer-motion d3 @types/d3

# Existing dependencies to leverage
# - Tailwind CSS (styling)
# - Lucide React (icons)
# - Recharts (if needed for data viz)
```

---

## Diagram 1: System Overview

### Component Structure
```typescript
// app/control-panel/architecture/components/SystemOverviewDiagram.tsx
'use client';

import { motion } from 'framer-motion';
import { useMemo } from 'react';
import { AgentNode } from './shared/AgentNode';
import { ConnectionLine } from './shared/ConnectionLine';
import { useAgentStore } from '@/app/stores/agentStore';

interface NodePosition {
  id: string;
  x: number;
  y: number;
  isCenter: boolean;
}

export function SystemOverviewDiagram() {
  const { agents } = useAgentStore();

  // Calculate radial layout positions
  const positions = useMemo(() => {
    const centerX = 400;
    const centerY = 300;
    const radius = 200;

    const specialists = agents.filter(a => a.role !== 'coordinator');
    const kublai = agents.find(a => a.role === 'coordinator');

    const positions: NodePosition[] = [];

    // Center position for Kublai
    if (kublai) {
      positions.push({
        id: kublai.id,
        x: centerX,
        y: centerY,
        isCenter: true,
      });
    }

    // Pentagon positions for specialists
    specialists.forEach((agent, index) => {
      const angle = (index * 2 * Math.PI) / specialists.length - Math.PI / 2;
      positions.push({
        id: agent.id,
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
        isCenter: false,
      });
    });

    return positions;
  }, [agents]);

  return (
    <div className="relative w-full h-[600px] bg-slate-900 rounded-xl overflow-hidden">
      <svg className="w-full h-full">
        {/* Connection lines */}
        {positions.map((pos, i) => {
          if (pos.isCenter) return null;
          const center = positions.find(p => p.isCenter);
          if (!center) return null;

          return (
            <ConnectionLine
              key={`line-${pos.id}`}
              from={center}
              to={pos}
              color="#FFD700"
              animated
            />
          );
        })}

        {/* Agent nodes */}
        {positions.map((pos, index) => (
          <AgentNode
            key={pos.id}
            agentId={pos.id}
            x={pos.x}
            y={pos.y}
            isCenter={pos.isCenter}
            delay={index * 0.1}
          />
        ))}
      </svg>
    </div>
  );
}
```

### Key Implementation Details

1. **Layout Engine**: Use radial positioning with `Math.cos()`/`Math.sin()`
2. **Animations**: Staggered entrance with Framer Motion
3. **Responsiveness**: Recalculate positions on resize using `useEffect`
4. **Interactions**: Hover to scale, click to select agent

---

## Diagram 2: Two-Tier Memory

### Component Structure
```typescript
// app/control-panel/architecture/components/MemoryVisualization.tsx
'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { useState } from 'react';
import { Database, FileText, Lock, Share2 } from 'lucide-react';

type ViewMode = 'personal' | 'shared' | 'both';

export function MemoryVisualization() {
  const [viewMode, setViewMode] = useState<ViewMode>('both');

  return (
    <div className="w-full bg-slate-900 rounded-xl p-6">
      {/* Toggle controls */}
      <div className="flex gap-2 mb-6">
        {(['personal', 'shared', 'both'] as ViewMode[]).map((mode) => (
          <button
            key={mode}
            onClick={() => setViewMode(mode)}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              viewMode === mode
                ? 'bg-amber-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
            }`}
          >
            {mode.charAt(0).toUpperCase() + mode.slice(1)}
          </button>
        ))}
      </div>

      {/* Content area */}
      <div className="flex gap-6 min-h-[400px]">
        <AnimatePresence mode="wait">
          {(viewMode === 'personal' || viewMode === 'both') && (
            <PersonalMemoryPanel />
          )}
          {(viewMode === 'shared' || viewMode === 'both') && (
            <SharedMemoryPanel />
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function PersonalMemoryPanel() {
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      className="flex-1 bg-gradient-to-br from-amber-900/20 to-slate-800 rounded-xl p-6 border border-amber-700/30"
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 bg-amber-600/20 rounded-lg">
          <Lock className="w-5 h-5 text-amber-500" />
        </div>
        <div>
          <h3 className="font-semibold text-amber-200">Personal Memory</h3>
          <p className="text-sm text-amber-400/70">Kublai Only</p>
        </div>
      </div>

      {/* File visualization */}
      <div className="grid grid-cols-3 gap-3">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.05 }}
            className="aspect-square bg-slate-800/50 rounded-lg flex flex-col items-center justify-center gap-2 hover:bg-slate-700/50 transition-colors cursor-pointer"
          >
            <FileText className="w-8 h-8 text-amber-500/60" />
            <span className="text-xs text-slate-400">File {i}</span>
          </motion.div>
        ))}
      </div>

      {/* Stats */}
      <div className="mt-6 pt-4 border-t border-amber-700/20">
        <div className="flex justify-between text-sm">
          <span className="text-slate-400">Files</span>
          <span className="text-amber-200 font-mono">12</span>
        </div>
        <div className="flex justify-between text-sm mt-2">
          <span className="text-slate-400">Total Size</span>
          <span className="text-amber-200 font-mono">2.4 MB</span>
        </div>
      </div>
    </motion.div>
  );
}

function SharedMemoryPanel() {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      className="flex-1 bg-gradient-to-br from-blue-900/20 to-slate-800 rounded-xl p-6 border border-blue-700/30"
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 bg-blue-600/20 rounded-lg">
          <Share2 className="w-5 h-5 text-blue-500" />
        </div>
        <div>
          <h3 className="font-semibold text-blue-200">Shared Memory</h3>
          <p className="text-sm text-blue-400/70">All Agents</p>
        </div>
      </div>

      {/* Neo4j graph preview */}
      <div className="relative h-48 bg-slate-900/50 rounded-lg overflow-hidden">
        <svg className="w-full h-full">
          {/* Simplified node graph */}
          <circle cx="50%" cy="30%" r="8" fill="#3B82F6" />
          <circle cx="30%" cy="60%" r="6" fill="#8B5CF6" />
          <circle cx="70%" cy="60%" r="6" fill="#10B981" />
          <circle cx="50%" cy="80%" r="6" fill="#F59E0B" />

          <line x1="50%" y1="30%" x2="30%" y2="60%" stroke="#3B82F6" strokeWidth="2" />
          <line x1="50%" y1="30%" x2="70%" y2="60%" stroke="#3B82F6" strokeWidth="2" />
          <line x1="30%" y1="60%" x2="50%" y2="80%" stroke="#3B82F6" strokeWidth="2" />
          <line x1="70%" y1="60%" x2="50%" y2="80%" stroke="#3B82F6" strokeWidth="2" />
        </svg>
      </div>

      {/* Stats */}
      <div className="mt-6 pt-4 border-t border-blue-700/20">
        <div className="flex justify-between text-sm">
          <span className="text-slate-400">Nodes</span>
          <span className="text-blue-200 font-mono">1,247</span>
        </div>
        <div className="flex justify-between text-sm mt-2">
          <span className="text-slate-400">Relationships</span>
          <span className="text-blue-200 font-mono">3,892</span>
        </div>
      </div>
    </motion.div>
  );
}
```

---

## Diagram 3: Task Delegation Flow

### Component Structure
```typescript
// app/control-panel/architecture/components/TaskDelegationFlow.tsx
'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { useState, useCallback } from 'react';
import { Play, Pause, RotateCcw, ChevronRight } from 'lucide-react';

type FlowStep = {
  id: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  duration: number; // seconds
};

const FLOW_STEPS: FlowStep[] = [
  { id: 'input', title: 'User Request', description: 'Task enters system', duration: 1, icon: null },
  { id: 'kublai', title: 'Kublai Router', description: 'Analyzes and routes', duration: 1.5, icon: null },
  { id: 'delegate', title: 'Delegation', description: 'Assigns to specialists', duration: 1, icon: null },
  { id: 'execute', title: 'Execution', description: 'Specialists work in parallel', duration: 3, icon: null },
  { id: 'store', title: 'Neo4j Storage', description: 'Results persisted', duration: 1, icon: null },
  { id: 'synthesize', title: 'Synthesis', description: 'Kublai combines results', duration: 1.5, icon: null },
  { id: 'response', title: 'Response', description: 'Delivered to user', duration: 0.5, icon: null },
];

export function TaskDelegationFlow() {
  const [currentStep, setCurrentStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  const handlePlay = useCallback(() => {
    setIsPlaying(true);
  }, []);

  const handlePause = useCallback(() => {
    setIsPlaying(false);
  }, []);

  const handleReset = useCallback(() => {
    setIsPlaying(false);
    setCurrentStep(0);
  }, []);

  const handleStepClick = useCallback((index: number) => {
    setCurrentStep(index);
    setIsPlaying(false);
  }, []);

  return (
    <div className="w-full bg-slate-900 rounded-xl p-6">
      {/* Playback controls */}
      <div className="flex items-center gap-4 mb-8">
        <button
          onClick={isPlaying ? handlePause : handlePlay}
          className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg transition-colors"
        >
          {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
          {isPlaying ? 'Pause' : 'Play'}
        </button>
        <button
          onClick={handleReset}
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors"
        >
          <RotateCcw className="w-4 h-4" />
          Reset
        </button>
        <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-amber-500"
            initial={{ width: 0 }}
            animate={{ width: `${(currentStep / (FLOW_STEPS.length - 1)) * 100}%` }}
          />
        </div>
      </div>

      {/* Flow steps */}
      <div className="relative">
        {/* Connection line */}
        <div className="absolute top-8 left-0 right-0 h-0.5 bg-slate-700" />

        {/* Steps */}
        <div className="relative flex justify-between">
          {FLOW_STEPS.map((step, index) => (
            <FlowStepNode
              key={step.id}
              step={step}
              index={index}
              isActive={index === currentStep}
              isComplete={index < currentStep}
              onClick={() => handleStepClick(index)}
            />
          ))}
        </div>
      </div>

      {/* Step details */}
      <AnimatePresence mode="wait">
        <motion.div
          key={currentStep}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          className="mt-8 p-4 bg-slate-800/50 rounded-lg"
        >
          <h4 className="font-semibold text-white">{FLOW_STEPS[currentStep].title}</h4>
          <p className="text-slate-400 mt-1">{FLOW_STEPS[currentStep].description}</p>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

function FlowStepNode({
  step,
  index,
  isActive,
  isComplete,
  onClick,
}: {
  step: FlowStep;
  index: number;
  isActive: boolean;
  isComplete: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="relative flex flex-col items-center group"
    >
      {/* Node circle */}
      <motion.div
        className={`w-16 h-16 rounded-full flex items-center justify-center border-2 transition-colors ${
          isActive
            ? 'bg-amber-600 border-amber-500 shadow-lg shadow-amber-500/30'
            : isComplete
            ? 'bg-green-600 border-green-500'
            : 'bg-slate-800 border-slate-600 group-hover:border-slate-500'
        }`}
        animate={isActive ? { scale: [1, 1.1, 1] } : {}}
        transition={{ repeat: Infinity, duration: 1.5 }}
      >
        <span className="text-white font-semibold">{index + 1}</span>
      </motion.div>

      {/* Label */}
      <span className={`mt-2 text-sm font-medium ${
        isActive ? 'text-amber-400' : isComplete ? 'text-green-400' : 'text-slate-500'
      }`}>
        {step.title}
      </span>
    </button>
  );
}
```

---

## Diagram 4: Agent Messaging

### Component Structure
```typescript
// app/control-panel/architecture/components/AgentMessagingDiagram.tsx
'use client';

import { motion } from 'framer-motion';
import { useEffect, useState, useRef } from 'react';
import { AGENTS } from '@/app/lib/agents';

interface Message {
  id: string;
  type: 'delegation' | 'progress' | 'completion' | 'blocked' | 'insight';
  from: string;
  to: string;
  timestamp: Date;
  content: string;
}

const MESSAGE_COLORS = {
  delegation: '#FFD700',
  progress: '#3B82F6',
  completion: '#10B981',
  blocked: '#EF4444',
  insight: '#8B5CF6',
};

export function AgentMessagingDiagram() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isPlaying, setIsPlaying] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  // Simulate incoming messages
  useEffect(() => {
    if (!isPlaying) return;

    const interval = setInterval(() => {
      const newMessage: Message = {
        id: Math.random().toString(36),
        type: ['delegation', 'progress', 'completion'][Math.floor(Math.random() * 3)] as Message['type'],
        from: AGENTS[Math.floor(Math.random() * AGENTS.length)].id,
        to: AGENTS[Math.floor(Math.random() * AGENTS.length)].id,
        timestamp: new Date(),
        content: 'Sample message content',
      };

      setMessages((prev) => [...prev.slice(-20), newMessage]);
    }, 2000);

    return () => clearInterval(interval);
  }, [isPlaying]);

  const agentIds = AGENTS.map((a) => a.id);
  const laneHeight = 60;

  return (
    <div className="w-full bg-slate-900 rounded-xl p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-white">Agent Communication</h3>
        <div className="flex items-center gap-4">
          <div className="flex gap-2">
            {Object.entries(MESSAGE_COLORS).map(([type, color]) => (
              <div key={type} className="flex items-center gap-1">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                <span className="text-xs text-slate-400 capitalize">{type}</span>
              </div>
            ))}
          </div>
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-sm"
          >
            {isPlaying ? 'Pause' : 'Play'}
          </button>
        </div>
      </div>

      {/* Timeline */}
      <div ref={containerRef} className="relative overflow-hidden" style={{ height: AGENTS.length * laneHeight }}>
        {/* Agent lanes */}
        {AGENTS.map((agent, index) => (
          <div
            key={agent.id}
            className="absolute left-0 right-0 flex items-center px-4 border-b border-slate-800"
            style={{ top: index * laneHeight, height: laneHeight }}
          >
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold"
              style={{ backgroundColor: agent.theme.primary }}
            >
              {agent.name[0]}
            </div>
            <span className="ml-3 text-sm text-slate-300">{agent.name}</span>
          </div>
        ))}

        {/* Messages */}
        {messages.map((message, index) => {
          const fromIndex = agentIds.indexOf(message.from);
          const toIndex = agentIds.indexOf(message.to);

          if (fromIndex === -1 || toIndex === -1) return null;

          return (
            <MessagePacket
              key={message.id}
              message={message}
              fromY={fromIndex * laneHeight + laneHeight / 2}
              toY={toIndex * laneHeight + laneHeight / 2}
              delay={index * 0.1}
            />
          );
        })}
      </div>
    </div>
  );
}

function MessagePacket({
  message,
  fromY,
  toY,
  delay,
}: {
  message: Message;
  fromY: number;
  toY: number;
  delay: number;
}) {
  return (
    <motion.div
      className="absolute left-20 right-4 h-6 rounded-full flex items-center px-3 text-xs font-medium text-white"
      style={{ backgroundColor: MESSAGE_COLORS[message.type] }}
      initial={{ top: fromY, opacity: 0, scale: 0.8 }}
      animate={{ top: toY, opacity: 1, scale: 1 }}
      transition={{ duration: 1, delay, ease: 'easeInOut' }}
    >
      {message.type}
    </motion.div>
  );
}
```

---

## Shared Components

### AgentNode
```typescript
// app/control-panel/architecture/components/shared/AgentNode.tsx
'use client';

import { motion } from 'framer-motion';
import { useAgentStore } from '@/app/stores/agentStore';

interface AgentNodeProps {
  agentId: string;
  x: number;
  y: number;
  isCenter?: boolean;
  delay?: number;
}

export function AgentNode({ agentId, x, y, isCenter, delay = 0 }: AgentNodeProps) {
  const { agents, selectAgent } = useAgentStore();
  const agent = agents.find((a) => a.id === agentId);

  if (!agent) return null;

  const width = isCenter ? 160 : 120;
  const height = isCenter ? 100 : 80;

  return (
    <motion.g
      initial={{ opacity: 0, scale: 0 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay, type: 'spring', stiffness: 200 }}
      style={{ cursor: 'pointer' }}
      onClick={() => selectAgent(agentId)}
    >
      {/* Glow effect */}
      <defs>
        <filter id={`glow-${agentId}`}>
          <feGaussianBlur stdDeviation="4" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Card background */}
      <rect
        x={x - width / 2}
        y={y - height / 2}
        width={width}
        height={height}
        rx={16}
        fill="#1E293B"
        stroke={agent.theme.primary}
        strokeWidth={2}
        filter={`url(#glow-${agentId})`}
      />

      {/* Avatar circle */}
      <circle
        cx={x}
        cy={y - 15}
        r={20}
        fill={agent.theme.primary}
      />

      {/* Initial */}
      <text
        x={x}
        y={y - 10}
        textAnchor="middle"
        fill="white"
        fontSize="14"
        fontWeight="bold"
      >
        {agent.name[0]}
      </text>

      {/* Name */}
      <text
        x={x}
        y={y + 15}
        textAnchor="middle"
        fill="white"
        fontSize="12"
        fontWeight="600"
      >
        {agent.name}
      </text>

      {/* Role */}
      <text
        x={x}
        y={y + 30}
        textAnchor="middle"
        fill="#94A3B8"
        fontSize="10"
      >
        {agent.role}
      </text>
    </motion.g>
  );
}
```

### ConnectionLine
```typescript
// app/control-panel/architecture/components/shared/ConnectionLine.tsx
'use client';

import { motion } from 'framer-motion';

interface ConnectionLineProps {
  from: { x: number; y: number };
  to: { x: number; y: number };
  color: string;
  animated?: boolean;
}

export function ConnectionLine({ from, to, color, animated }: ConnectionLineProps) {
  const path = `M ${from.x} ${from.y} L ${to.x} ${to.y}`;

  return (
    <g>
      {/* Background line */}
      <path
        d={path}
        stroke={color}
        strokeWidth={2}
        opacity={0.3}
      />

      {/* Animated line */}
      {animated && (
        <motion.path
          d={path}
          stroke={color}
          strokeWidth={2}
          fill="none"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.5, ease: 'easeInOut' }}
        />
      )}

      {/* Pulse animation */}
      {animated && (
        <motion.circle
          r={4}
          fill={color}
        >
          <animateMotion
            dur="2s"
            repeatCount="indefinite"
            path={path}
          />
        </motion.circle>
      )}
    </g>
  );
}
```

---

## Integration

### Add to Control Panel
```typescript
// app/control-panel/architecture/page.tsx
import { SystemOverviewDiagram } from './components/SystemOverviewDiagram';
import { MemoryVisualization } from './components/MemoryVisualization';
import { TaskDelegationFlow } from './components/TaskDelegationFlow';
import { AgentMessagingDiagram } from './components/AgentMessagingDiagram';

export default function ArchitecturePage() {
  return (
    <div className="min-h-screen bg-slate-900 p-6">
      <h1 className="text-2xl font-bold text-white mb-6">System Architecture</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section>
          <h2 className="text-lg font-semibold text-slate-300 mb-3">System Overview</h2>
          <SystemOverviewDiagram />
        </section>

        <section>
          <h2 className="text-lg font-semibold text-slate-300 mb-3">Memory Architecture</h2>
          <MemoryVisualization />
        </section>

        <section className="lg:col-span-2">
          <h2 className="text-lg font-semibold text-slate-300 mb-3">Task Delegation Flow</h2>
          <TaskDelegationFlow />
        </section>

        <section className="lg:col-span-2">
          <h2 className="text-lg font-semibold text-slate-300 mb-3">Agent Messaging</h2>
          <AgentMessagingDiagram />
        </section>
      </div>
    </div>
  );
}
```

---

## Testing Checklist

### Visual
- [ ] All 4 diagrams render without errors
- [ ] Color scheme matches specification
- [ ] Responsive layout works on all breakpoints
- [ ] Animations are smooth (60fps)

### Interactivity
- [ ] Hover states work correctly
- [ ] Click actions trigger expected behavior
- [ ] Playback controls function properly
- [ ] Toggle switches update views

### Accessibility
- [ ] Keyboard navigation works
- [ ] Screen reader announces correctly
- [ ] Color contrast meets WCAG standards
- [ ] Reduced motion respected

### Performance
- [ ] Initial load under 2 seconds
- [ ] Animations don't cause jank
- [ ] Memory usage stable over time
- [ ] Cleanup on unmount

---

## Next Steps

1. **Create shared components** first (AgentNode, ConnectionLine)
2. **Implement diagrams** in order of complexity: System Overview → Memory Viz → Task Flow → Messaging
3. **Add to navigation** in control panel
4. **Test** across devices and browsers
5. **Optimize** based on performance metrics
