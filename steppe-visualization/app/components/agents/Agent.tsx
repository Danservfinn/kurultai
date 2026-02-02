'use client';

import { useState } from 'react';
import { Agent as AgentType } from '@/app/types/agents';
import { AgentMesh } from './AgentMesh';
import { AgentCamp } from './AgentCamp';
import { StatusIndicator } from './StatusIndicator';
import { AgentTaskLabel } from './AgentTaskLabel';

interface AgentProps {
  agent: AgentType;
  isSelected: boolean;
  onSelect: (agent: AgentType) => void;
}

export function Agent({ agent, isSelected, onSelect }: AgentProps) {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <group
      onClick={(e) => {
        e.stopPropagation();
        onSelect(agent);
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        setIsHovered(true);
        document.body.style.cursor = 'pointer';
      }}
      onPointerOut={() => {
        setIsHovered(false);
        document.body.style.cursor = 'auto';
      }}
    >
      {/* Camp environment */}
      <AgentCamp agent={agent} />

      {/* Agent character */}
      <AgentMesh
        agent={agent}
        isSelected={isSelected}
        isHovered={isHovered}
      />

      {/* Status indicator */}
      <StatusIndicator
        status={agent.status}
        position={{
          x: agent.position.x,
          y: agent.position.elevation,
          z: agent.position.z,
        }}
      />

      {/* Task and Queue Label */}
      <AgentTaskLabel agent={agent} />
    </group>
  );
}
