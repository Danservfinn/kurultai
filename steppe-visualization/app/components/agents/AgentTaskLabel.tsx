'use client';

import { useRef, useMemo } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { Agent } from '@/app/types/agents';

interface AgentTaskLabelProps {
  agent: Agent;
}

const STATUS_COLORS: Record<Agent['status'], string> = {
  idle: '#22c55e',
  working: '#3b82f6',
  reviewing: '#f59e0b',
  alert: '#ef4444',
  offline: '#6b7280',
};

export function AgentTaskLabel({ agent }: AgentTaskLabelProps) {
  const groupRef = useRef<THREE.Group>(null);

  // Animation - float above agent
  useFrame((state) => {
    if (groupRef.current) {
      const time = state.clock.getElapsedTime();
      groupRef.current.position.y = agent.position.elevation + 3.5 + Math.sin(time * 2) * 0.1;
    }
  });

  const statusColor = STATUS_COLORS[agent.status];
  const queueCount = agent.queue?.length || 0;
  const hasTask = !!agent.currentTask;

  return (
    <group
      ref={groupRef}
      position={[agent.position.x, agent.position.elevation + 3.5, agent.position.z]}
    >
      <Html
        center
        distanceFactor={12}
        style={{
          pointerEvents: 'none',
          userSelect: 'none',
        }}
      >
        <div className="flex flex-col items-center gap-2">
          {/* Status Badge */}
          <div
            className="px-3 py-1 rounded-full text-sm font-bold uppercase tracking-wider text-white shadow-lg"
            style={{
              backgroundColor: statusColor,
              boxShadow: `0 0 15px ${statusColor}`,
            }}
          >
            {agent.status}
          </div>

          {/* Current Task */}
          {hasTask && (
            <div className="bg-black/80 backdrop-blur-sm rounded-lg px-4 py-3 text-center min-w-[220px] border border-white/20">
              <div className="text-white text-base font-medium truncate">
                {agent.currentTask?.title}
              </div>
              <div className="text-white/60 text-sm mt-1">
                {agent.currentTask?.progress}%
              </div>
              {/* Progress Bar */}
              <div className="w-full h-2 bg-white/20 rounded-full mt-2 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${agent.currentTask?.progress}%`,
                    backgroundColor: agent.theme.glow,
                  }}
                />
              </div>
            </div>
          )}

          {/* Queue Indicator */}
          {queueCount > 0 && (
            <div className="flex items-center gap-2 bg-black/60 backdrop-blur-sm rounded-full px-3 py-1.5 border border-white/10">
              <span className="text-white/80 text-sm">Queue:</span>
              <span
                className="text-base font-bold"
                style={{ color: agent.theme.glow }}
              >
                {queueCount}
              </span>
              {agent.queue?.slice(0, 3).map((task, i) => (
                <div
                  key={task.id}
                  className="w-2 h-2 rounded-full"
                  style={{
                    backgroundColor:
                      task.priority === 'high'
                        ? '#ef4444'
                        : task.priority === 'medium'
                        ? '#f59e0b'
                        : '#22c55e',
                  }}
                  title={task.title}
                />
              ))}
              {queueCount > 3 && (
                <span className="text-white/50 text-xs">+{queueCount - 3}</span>
              )}
            </div>
          )}

          {/* Idle State */}
          {!hasTask && queueCount === 0 && (
            <div className="bg-black/60 backdrop-blur-sm rounded-full px-4 py-2 text-white/50 text-base">
              Awaiting orders
            </div>
          )}

          {/* Agent Name */}
          <div
            className="mt-1 px-3 py-1 rounded text-base font-semibold text-white/90 bg-black/40 backdrop-blur-sm border border-white/10 whitespace-nowrap"
            style={{ textShadow: '0 2px 4px rgba(0,0,0,0.8)' }}
          >
            {agent.displayName}
          </div>
        </div>
      </Html>
    </group>
  );
}
