"use client";

import { useGameState } from "@/hooks/useGameState";
import { GodModeFeed } from "@/components/spectator/GodModeFeed";
import { PhaseAChallenge } from "@/components/phases/PhaseAChallenge";
import { PhaseBScramble } from "@/components/phases/PhaseBScramble";
import { PhaseCTribal } from "@/components/phases/PhaseCTribal";
import { PhaseDMemory } from "@/components/phases/PhaseDMemory";
import { PhaseEFinale } from "@/components/phases/PhaseEFinale";

export default function Home() {
  const { data } = useGameState();

  if (!data) {
    return (
      <div className="w-full h-screen bg-[#2c2c2c] text-white flex items-center justify-center font-pixel animate-pulse">
        PRESS START...
      </div>
    );
  }

  const activeCount = data.agents.filter(a => a.status === 'active').length;

  return (
    <main className="flex w-full h-screen bg-[#2c2c2c] p-6 gap-6 font-pixel text-[10px] leading-relaxed overflow-hidden">
      {/* LEFT PANE - EMULATOR (65%) */}
      <div className="w-[65%] h-full flex flex-col">
        {/* HEADER BAR */}
        <div className="gbc-box p-3 mb-4 flex justify-between bg-white uppercase text-gbc-black z-10">
          <span>DAY {data.game.current_day}</span>
          <span>{data.game.phase}</span>
          <span>ALIVE: {activeCount}/16</span>
        </div>

        {/* PHASE ROUTER */}
        <div className="flex-grow gbc-box relative overflow-hidden flex flex-col bg-gbc-bg">
          <div className="flex-grow relative p-4">
            {data.game.phase === 'challenge' && <PhaseAChallenge data={data} />}
            {data.game.phase === 'scramble' && <PhaseBScramble data={data} />}
            {data.game.phase === 'tribal' && <PhaseCTribal data={data} />}
            {data.game.phase === 'memory' && <PhaseDMemory data={data} />}
            {(data.game.phase === 'completed' || data.game.phase === 'finale_running') && <PhaseEFinale data={data} />}
          </div>
        </div>
      </div>

      {/* RIGHT PANE - GOD FEED (35%) */}
      <div className="w-[35%] h-full bg-[#1a1a1a] p-4 rounded-lg overflow-hidden border-4 border-black box-border">
        <GodModeFeed messages={data.messages} />
      </div>
    </main>
  );
}
