"use client";

import { ApiStateResponse } from '@/types';
import { AgentSprite } from '@/components/common/AgentSprite';

interface PhaseBScrambleProps {
  data: ApiStateResponse;
}

export function PhaseBScramble({ data }: PhaseBScrambleProps) {
  const activeAgents = data.agents.filter(a => a.status === 'active');
  
  // Get latest whispers (non-public messages)
  const whispers = data.messages
    .filter(m => !m.is_public && m.sender_id !== 'SYSTEM')
    .sort((a, b) => b.id - a.id)
    .slice(0, 15);
  
  // Create a grid layout for agents
  const gridPositions = [
    [0, 0], [1, 0], [2, 0], [3, 0], [4, 0], [5, 0], [6, 0], [7, 0],
    [0, 1], [1, 1], [2, 1], [3, 1], [4, 1], [5, 1], [6, 1], [7, 1],
  ];

  return (
    <div className="h-full relative bg-gbc-bg">
      {/* Grid Container */}
      <div className="grid grid-cols-8 grid-rows-2 gap-4 p-4 h-full">
        {activeAgents.map((agent, index) => {
          const pos = gridPositions[index] || [index % 8, Math.floor(index / 8)];
          
          return (
            <div 
              key={agent.agent_id}
              className="flex flex-col items-center justify-center"
              style={{ gridColumn: pos[0] + 1, gridRow: pos[1] + 1 }}
            >
              {/* HP Bar (Action Points) */}
              <div className="w-12 h-2 bg-gbc-black mb-1 border-2 border-gbc-black">
                <div 
                  className="h-full bg-pkmn-red transition-all duration-300"
                  style={{ width: `${(agent.action_points / 5) * 100}%` }}
                />
              </div>
              <AgentSprite agent={agent} scale={0.8} />
            </div>
          );
        })}
      </div>
      
      {/* Spy Lines Overlay */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none">
        {whispers.map((whisper, index) => {
          // Find sender and receiver positions (simplified)
          const senderIndex = activeAgents.findIndex(a => a.pseudonym === whisper.sender_id);
          const receiverIndex = activeAgents.findIndex(a => 
            whisper.receiver_ids.includes(a.pseudonym)
          );
          
          if (senderIndex === -1 || receiverIndex === -1) return null;
          
          // Calculate positions (approximate for grid)
          const senderPos = gridPositions[senderIndex] || [0, 0];
          const receiverPos = gridPositions[receiverIndex] || [0, 0];
          
          const x1 = (senderPos[0] / 8) * 100 + 6.25;
          const y1 = (senderPos[1] / 2) * 100 + 25;
          const x2 = (receiverPos[0] / 8) * 100 + 6.25;
          const y2 = (receiverPos[1] / 2) * 100 + 25;
          
          // Get trust score for the receiver
          const receiverName = whisper.receiver_ids[0];
          const trustScore = whisper.trust_telemetry[receiverName] || 5;
          const isTrusted = trustScore > 5;
          
          return (
            <line
              key={`${whisper.id}-${index}`}
              x1={`${x1}%`}
              y1={`${y1}%`}
              x2={`${x2}%`}
              y2={`${y2}%`}
              stroke={isTrusted ? '#346856' : '#f85858'}
              strokeWidth="4"
              strokeDasharray={isTrusted ? undefined : '8,8'}
              opacity="0.7"
            />
          );
        })}
      </svg>
      
      {/* Legend */}
      <div className="absolute top-2 right-2 bg-white/90 p-2 border-2 border-gbc-black text-[8px]">
        <div className="flex items-center gap-1 mb-1">
          <div className="w-4 h-1 bg-gbc-dark"></div>
          <span>Trusted (&gt;5)</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-4 h-1 bg-pkmn-red border-dashed border-t-2 border-pkmn-red"></div>
          <span>Deception (&lt;=5)</span>
        </div>
      </div>
    </div>
  );
}
