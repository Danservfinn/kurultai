"use client";

import { useState, useEffect } from 'react';
import { ApiStateResponse } from '@/types';
import { AgentSprite } from '@/components/common/AgentSprite';
import { DialogBox } from '@/components/common/DialogBox';

interface PhaseCTribalProps {
  data: ApiStateResponse;
}

export function PhaseCTribal({ data }: PhaseCTribalProps) {
  const [revealedVoteIndex, setRevealedVoteIndex] = useState(-1);
  const [eliminatedAgent, setEliminatedAgent] = useState<string | null>(null);
  
  const activeAgents = data.agents.filter(a => a.status === 'active');
  const vulnerableAgents = activeAgents.filter(a => !a.has_immunity);
  const immuneAgents = activeAgents.filter(a => a.has_immunity);
  
  const votes = data.votes || [];
  
  useEffect(() => {
    if (votes.length === 0) return;
    
    // Start revealing votes
    if (revealedVoteIndex < votes.length - 1) {
      const timer = setTimeout(() => {
        setRevealedVoteIndex(prev => prev + 1);
      }, 4000);
      
      return () => clearTimeout(timer);
    } else if (revealedVoteIndex === votes.length - 1 && !eliminatedAgent) {
      // All votes revealed - determine eliminated agent
      const voteCounts: Record<string, number> = {};
      votes.forEach(vote => {
        voteCounts[vote.target_id] = (voteCounts[vote.target_id] || 0) + 1;
      });
      
      const maxVotes = Math.max(...Object.values(voteCounts));
      const eliminated = Object.entries(voteCounts)
        .filter(([_, count]) => count === maxVotes)
        .map(([id]) => id)[0];
      
      setEliminatedAgent(eliminated);
    }
  }, [revealedVoteIndex, votes, eliminatedAgent]);
  
  const currentVote = votes[revealedVoteIndex];
  const dialogText = currentVote 
    ? `JeffBot reads the vote... It's for... ${currentVote.target_pseudonym.toUpperCase()}.`
    : revealedVoteIndex >= 0 && eliminatedAgent
    ? `${eliminatedAgent.toUpperCase()} has been voted out!`
    : 'The tribe has spoken... Reading the votes...';

  return (
    <div className="h-full flex flex-col bg-gbc-black p-4">
      {/* Title */}
      <div className="text-center mb-4">
        <h2 className="text-pkmn-red text-lg font-bold tracking-widest">TRIBAL COUNCIL</h2>
      </div>
      
      {/* Vulnerable Agents (Center) */}
      <div className="flex-grow flex items-center justify-center gap-6">
        {vulnerableAgents.map(agent => (
          <AgentSprite 
            key={agent.agent_id} 
            agent={agent} 
            isFainting={eliminatedAgent === agent.pseudonym}
          />
        ))}
      </div>
      
      {/* Immune Agents (Faded, Background) */}
      {immuneAgents.length > 0 && (
        <div className="flex justify-center gap-4 mb-4 opacity-40">
          {immuneAgents.map(agent => (
            <AgentSprite key={agent.agent_id} agent={agent} />
          ))}
        </div>
      )}
      
      {/* Vote Counter */}
      {votes.length > 0 && (
        <div className="text-center mb-2">
          <span className="text-white text-[10px]">
            Vote {Math.min(revealedVoteIndex + 1, votes.length)} of {votes.length}
          </span>
        </div>
      )}
      
      {/* Dialog */}
      <DialogBox text={dialogText} />
    </div>
  );
}
