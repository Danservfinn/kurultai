'use client';

import { useMemo } from 'react';
import { Agent } from '@/app/types/agents';
import { cn } from '@/lib/utils';

interface MiniMapProps {
  agents: Agent[];
  selectedAgentId: string | null;
  onSelectAgent: (agentId: string) => void;
}

// Map bounds for conversion
const MAP_BOUNDS = {
  minLat: 35,
  maxLat: 55,
  minLng: 20,
  maxLng: 130,
};

function latLngToMiniMap(lat: number, lng: number): { x: number; y: number } {
  const x = ((lng - MAP_BOUNDS.minLng) / (MAP_BOUNDS.maxLng - MAP_BOUNDS.minLng)) * 100;
  const y = ((lat - MAP_BOUNDS.minLat) / (MAP_BOUNDS.maxLat - MAP_BOUNDS.minLat)) * 100;
  return { x, y: 100 - y }; // Invert Y so north is up
}

export function MiniMap({ agents, selectedAgentId, onSelectAgent }: MiniMapProps) {
  const agentPositions = useMemo(() => {
    return agents.map((agent) => ({
      ...agent,
      miniMapPos: latLngToMiniMap(agent.coordinates.lat, agent.coordinates.lng),
    }));
  }, [agents]);

  return (
    <div className="fixed bottom-6 left-6 z-40 w-72 h-56 bg-black/80 backdrop-blur-sm rounded-xl border border-white/10 shadow-2xl overflow-hidden">
      <div className="absolute top-3 left-3 text-sm font-semibold text-white/80">
        Empire Map
      </div>

      {/* Map background - simplified terrain */}
      <div className="absolute inset-0 mt-8 mb-2 mx-2 rounded-lg bg-gradient-to-br from-[#4a6741] via-[#5c4a3d] to-[#8b7355]">
        {/* Mountain ranges */}
        <div className="absolute top-[20%] left-[10%] w-[15%] h-[20%] bg-[#6b5b4f] rounded-full opacity-50 blur-sm" />
        <div className="absolute top-[40%] left-[25%] w-[12%] h-[15%] bg-[#6b5b4f] rounded-full opacity-50 blur-sm" />

        {/* Rivers */}
        <svg className="absolute inset-0 w-full h-full" viewBox="0 0 100 100" preserveAspectRatio="none">
          {/* Volga */}
          <path d="M 25 15 Q 23 25 25 35" stroke="#1e3a5f" strokeWidth="1.5" fill="none" opacity="0.6" />
          {/* Orkhon */}
          <path d="M 75 35 Q 73 40 76 45" stroke="#1e3a5f" strokeWidth="1.5" fill="none" opacity="0.6" />
          {/* Ili */}
          <path d="M 60 45 Q 62 50 64 52" stroke="#1e3a5f" strokeWidth="1.5" fill="none" opacity="0.6" />
        </svg>

        {/* Agent markers */}
        {agentPositions.map((agent) => (
          <button
            key={agent.id}
            onClick={() => onSelectAgent(agent.id)}
            className={cn(
              "absolute w-4 h-4 -ml-2 -mt-2 rounded-full border-2 transition-all duration-200",
              selectedAgentId === agent.id
                ? "scale-150 border-white shadow-lg shadow-white/50"
                : "scale-100 border-white/50 hover:scale-125"
            )}
            style={{
              left: `${agent.miniMapPos.x}%`,
              top: `${agent.miniMapPos.y}%`,
              backgroundColor: agent.theme.primary,
            }}
            title={`${agent.displayName} - ${agent.historicalCapital}`}
          />
        ))}
      </div>

      {/* Legend */}
      <div className="absolute bottom-2 right-2 flex flex-col gap-1 text-xs text-white/60">
        <span>★ Capital</span>
        <span>═ River</span>
      </div>
    </div>
  );
}
