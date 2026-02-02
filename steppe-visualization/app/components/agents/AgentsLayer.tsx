'use client';

import { useMemo } from 'react';
import { Agent } from '@/app/types/agents';
import { Agent as AgentComponent } from './Agent';

interface AgentsLayerProps {
  agents: Agent[];
  selectedAgentId: string | null;
  onSelectAgent: (agent: Agent) => void;
}

export function AgentsLayer({ agents, selectedAgentId, onSelectAgent }: AgentsLayerProps) {
  // Sort agents by z-position for proper rendering order
  const sortedAgents = useMemo(() => {
    return [...agents].sort((a, b) => a.position.z - b.position.z);
  }, [agents]);

  return (
    <group>
      {sortedAgents.map((agent) => (
        <AgentComponent
          key={agent.id}
          agent={agent}
          isSelected={selectedAgentId === agent.id}
          onSelect={onSelectAgent}
        />
      ))}
    </group>
  );
}
