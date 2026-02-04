'use client';

import { SteppeScene } from './components/scene/SteppeScene';
import { Header } from './components/ui/Header';
import { MiniMap } from './components/ui/MiniMap';
import { AgentDetailPanel } from './components/ui/AgentDetailPanel';
import { useAgentStore } from './stores/agentStore';
import { useFileWatcher } from './hooks/useFileWatcher';
import { useAgentData } from './hooks/useAgentData';

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

  // Initialize file watcher and live data connection
  useFileWatcher();
  const { isConnected } = useAgentData();

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
          <div className="flex items-center justify-between gap-4 mb-2">
            <p className="font-semibold text-lg">Controls</p>
            <div className="flex items-center gap-2 text-sm">
              <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-yellow-500'}`}></span>
              <span className="text-white/60">{isConnected ? 'Live' : 'Demo Mode'}</span>
            </div>
          </div>
          <p className="py-0.5">🖱️ Click + Drag to orbit/pivot</p>
          <p className="py-0.5">🖱️ Click agent to view details</p>
          <p className="py-0.5">📜 Scroll / Pinch to zoom</p>
          <p className="py-0.5">⌨️ WASD / Arrow keys to pan</p>
          <p className="py-0.5">👆 2-finger drag to pan map</p>
          <div className="mt-3 pt-3 border-t border-white/20">
            <a
              href="/control-panel"
              className="inline-flex items-center gap-2 px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white text-sm rounded transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              Mission Control
            </a>
          </div>
        </div>
      </div>
    </main>
  );
}
