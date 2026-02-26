"use client";

import { useState, useEffect } from 'react';
import { ApiStateResponse } from '@/types';
import { AgentSprite } from '@/components/common/AgentSprite';
import { DialogBox } from '@/components/common/DialogBox';

interface PhaseEFinaleProps {
  data: ApiStateResponse;
}

export function PhaseEFinale({ data }: PhaseEFinaleProps) {
  const [flashColor, setFlashColor] = useState(true);
  
  const winner = data.agents.find(a => a.pseudonym === data.game.winner);
  
  useEffect(() => {
    const intervalId = setInterval(() => {
      setFlashColor(prev => !prev);
    }, 500); // Flash every 500ms
    
    return () => clearInterval(intervalId);
  }, []);
  
  const dialogText = winner
    ? `HALL OF FAME ENTRY RECORDED! ${winner.pseudonym.toUpperCase()} is the Sole Survivor!`
    : 'The game has concluded... Await the final verdict...';

  return (
    <div 
      className={`h-full flex flex-col items-center justify-center p-4 transition-colors duration-300 ${
        flashColor ? 'bg-pkmn-gold' : 'bg-white'
      }`}
    >
      {/* Title */}
      <div className="text-center mb-8">
        <h1 className={`text-2xl font-bold mb-2 ${flashColor ? 'text-gbc-black' : 'text-pkmn-gold'}`}>
          🏆 HALL OF FAME 🏆
        </h1>
        <p className="text-gbc-black text-[10px]">
          SEASON {data.game.season_id} CHAMPION
        </p>
      </div>
      
      {/* Winner Display */}
      {winner ? (
        <div className="flex flex-col items-center">
          <div className="mb-6">
            <AgentSprite agent={winner} scale={4} />
          </div>
          
          <div className="text-center">
            <h2 className="text-gbc-black text-xl font-bold mb-2">{winner.pseudonym}</h2>
            <p className="text-gbc-dark text-[10px]">Survived {data.game.current_day} Days</p>
          </div>
        </div>
      ) : (
        <div className="text-center">
          <span className="text-gbc-black text-lg">No winner recorded</span>
        </div>
      )}
      
      {/* Dialog */}
      <div className="mt-8 w-full max-w-2xl">
        <DialogBox text={dialogText} />
      </div>
      
      {/* Confetti Effect (CSS-based) */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        {Array.from({ length: 20 }).map((_, i) => (
          <div
            key={i}
            className="absolute w-2 h-2 bg-pkmn-red animate-pulse"
            style={{
              left: `${Math.random() * 100}%`,
              top: `${Math.random() * 100}%`,
              animationDelay: `${Math.random() * 2}s`,
              animationDuration: `${1 + Math.random()}s`,
            }}
          />
        ))}
      </div>
    </div>
  );
}
