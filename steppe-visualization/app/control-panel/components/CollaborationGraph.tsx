'use client';

import { useRef, useEffect, useState } from 'react';

interface Agent {
  id: string;
  name: string;
  color: string;
}

interface Collaboration {
  from: string;
  to: string;
  type: 'LEARNED' | 'COLLABORATES_WITH' | 'CREATED';
  timestamp: string;
}

interface CollaborationGraphProps {
  agents: Agent[];
  collaborations: Collaboration[];
  selectedAgent: string | null;
}

export function CollaborationGraph({ agents, collaborations, selectedAgent }: CollaborationGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hoveredAgent, setHoveredAgent] = useState<string | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * window.devicePixelRatio;
    canvas.height = rect.height * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    const width = rect.width;
    const height = rect.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.35;

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Calculate agent positions (hexagon layout)
    const agentPositions: Record<string, { x: number; y: number }> = {};
    agents.forEach((agent, index) => {
      const angle = (index * 2 * Math.PI) / agents.length - Math.PI / 2;
      agentPositions[agent.id] = {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      };
    });

    // Draw collaboration lines
    collaborations.forEach(collab => {
      const from = agentPositions[collab.from];
      const to = agentPositions[collab.to];
      if (!from || !to) return;

      ctx.beginPath();
      ctx.moveTo(from.x, from.y);

      // Curved lines for LEARNED, straight for COLLABORATES_WITH
      if (collab.type === 'LEARNED') {
        const midX = (from.x + to.x) / 2;
        const midY = (from.y + to.y) / 2;
        const controlX = midX + (to.y - from.y) * 0.2;
        const controlY = midY - (to.x - from.x) * 0.2;
        ctx.quadraticCurveTo(controlX, controlY, to.x, to.y);
      } else {
        ctx.lineTo(to.x, to.y);
      }

      // Line style based on type
      if (collab.type === 'LEARNED') {
        ctx.strokeStyle = 'rgba(74, 144, 217, 0.4)';
        ctx.lineWidth = 2;
      } else if (collab.type === 'COLLABORATES_WITH') {
        ctx.strokeStyle = 'rgba(155, 89, 182, 0.4)';
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 5]);
      } else {
        ctx.strokeStyle = 'rgba(39, 174, 96, 0.3)';
        ctx.lineWidth = 1;
      }

      ctx.stroke();
      ctx.setLineDash([]);

      // Draw arrow for LEARNED relationships
      if (collab.type === 'LEARNED') {
        const angle = Math.atan2(to.y - from.y, to.x - from.x);
        const arrowLength = 10;
        const arrowAngle = Math.PI / 6;

        ctx.beginPath();
        ctx.moveTo(to.x - 25 * Math.cos(angle), to.y - 25 * Math.sin(angle));
        ctx.lineTo(
          to.x - 25 * Math.cos(angle) - arrowLength * Math.cos(angle - arrowAngle),
          to.y - 25 * Math.sin(angle) - arrowLength * Math.sin(angle - arrowAngle)
        );
        ctx.moveTo(to.x - 25 * Math.cos(angle), to.y - 25 * Math.sin(angle));
        ctx.lineTo(
          to.x - 25 * Math.cos(angle) - arrowLength * Math.cos(angle + arrowAngle),
          to.y - 25 * Math.sin(angle) - arrowLength * Math.sin(angle + arrowAngle)
        );
        ctx.strokeStyle = 'rgba(74, 144, 217, 0.6)';
        ctx.stroke();
      }
    });

    // Draw agent nodes
    agents.forEach(agent => {
      const pos = agentPositions[agent.id];
      const isSelected = selectedAgent === agent.id;
      const isHovered = hoveredAgent === agent.id;

      // Glow effect for selected/hovered
      if (isSelected || isHovered) {
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, 30, 0, 2 * Math.PI);
        ctx.fillStyle = `${agent.color}20`;
        ctx.fill();
      }

      // Node circle
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, 20, 0, 2 * Math.PI);
      ctx.fillStyle = agent.color;
      ctx.fill();

      // Border
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, 20, 0, 2 * Math.PI);
      ctx.strokeStyle = isSelected ? '#FFD700' : 'rgba(255,255,255,0.3)';
      ctx.lineWidth = isSelected ? 3 : 2;
      ctx.stroke();

      // Initial
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 14px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(agent.name[0], pos.x, pos.y);

      // Name label
      ctx.fillStyle = isSelected || isHovered ? '#fff' : '#94a3b8';
      ctx.font = isSelected || isHovered ? 'bold 12px sans-serif' : '12px sans-serif';
      ctx.fillText(agent.name, pos.x, pos.y + 32);
    });
  }, [agents, collaborations, selectedAgent, hoveredAgent]);

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const width = rect.width;
    const height = rect.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.35;

    // Check if hovering over any agent
    let hovered: string | null = null;
    agents.forEach((agent, index) => {
      const angle = (index * 2 * Math.PI) / agents.length - Math.PI / 2;
      const posX = centerX + radius * Math.cos(angle);
      const posY = centerY + radius * Math.sin(angle);

      const distance = Math.sqrt((x - posX) ** 2 + (y - posY) ** 2);
      if (distance < 25) {
        hovered = agent.id;
      }
    });

    setHoveredAgent(hovered);
  };

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <svg className="w-5 h-5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          Collaboration Graph
        </h3>
        <div className="flex items-center gap-3 text-xs">
          <div className="flex items-center gap-1">
            <span className="w-3 h-0.5 bg-blue-400"></span>
            <span className="text-slate-400">Learned</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-3 h-0.5 bg-purple-400 border-dashed"></span>
            <span className="text-slate-400">Collaborates</span>
          </div>
        </div>
      </div>

      <canvas
        ref={canvasRef}
        className="w-full h-64 cursor-pointer"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoveredAgent(null)}
      />

      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <div className="bg-slate-900/50 rounded-lg p-2">
          <p className="text-2xl font-bold text-blue-400">
            {collaborations.filter(c => c.type === 'LEARNED').length}
          </p>
          <p className="text-xs text-slate-500">Knowledge Transfers</p>
        </div>
        <div className="bg-slate-900/50 rounded-lg p-2">
          <p className="text-2xl font-bold text-purple-400">
            {collaborations.filter(c => c.type === 'COLLABORATES_WITH').length}
          </p>
          <p className="text-xs text-slate-500">Active Collaborations</p>
        </div>
        <div className="bg-slate-900/50 rounded-lg p-2">
          <p className="text-2xl font-bold text-green-400">
            {collaborations.filter(c => c.type === 'CREATED').length}
          </p>
          <p className="text-xs text-slate-500">Knowledge Created</p>
        </div>
      </div>
    </div>
  );
}
