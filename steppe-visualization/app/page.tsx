'use client';

import { SteppeScene } from './components/scene/SteppeScene';
import { Header } from './components/ui/Header';
import { MiniMap } from './components/ui/MiniMap';
import { AgentDetailPanel } from './components/ui/AgentDetailPanel';
import { useAgentStore } from './stores/agentStore';
import { useFileWatcher } from './hooks/useFileWatcher';

export default function Home() {
  const {
    agents,
    selectedAgentId,
    isDetailPanelOpen,
    selectAgent,
    toggleDetailPanel,
    getSelectedAgent,
    getAgentActivities,
  } = useAgentStore();

  // Initialize file watcher
  useFileWatcher();

  const selectedAgent = getSelectedAgent();
  const selectedAgentActivities = selectedAgentId
    ? getAgentActivities(selectedAgentId)
    : [];

  return (
    <main className="relative w-screen h-screen bg-black overflow-hidden">
      {/* 3D Scene */}
      <SteppeScene />

      {/* UI Overlay */}
      <Header
        onToggleMap={() => {}}
        onToggleSettings={() => {}}
        onToggleHelp={() => {}}
      />

      {/* Mini Map */}
      <MiniMap
        agents={agents}
        selectedAgentId={selectedAgentId}
        onSelectAgent={(id) => {
          selectAgent(id);
          toggleDetailPanel(true);
        }}
      />

      {/* Agent Detail Panel */}
      <AgentDetailPanel
        agent={selectedAgent || null}
        activities={selectedAgentActivities}
        isOpen={isDetailPanelOpen}
        onClose={() => {
          selectAgent(null);
          toggleDetailPanel(false);
        }}
      />

      {/* Instructions overlay */}
      <div className="fixed bottom-6 right-6 z-40 text-right">
        <div className="bg-black/70 backdrop-blur-sm rounded-lg px-5 py-4 text-white/80 text-base">
          <p className="font-semibold mb-2 text-lg">Controls</p>
          <p className="py-0.5">🖱️ Click + Drag to orbit/pivot</p>
          <p className="py-0.5">🖱️ Click agent to view details</p>
          <p className="py-0.5">📜 Scroll / Pinch to zoom</p>
          <p className="py-0.5">⌨️ WASD / Arrow keys to pan</p>
          <p className="py-0.5">👆 2-finger drag to pan map</p>
        </div>
      </div>
    </main>
  );
}
