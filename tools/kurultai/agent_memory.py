"""
Kurultai Agent Memory System
Individual memory for each agent with shared context.
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

# Agent-specific memory files
AGENT_MEMORY_PATHS = {
    "Kublai": "memory/agents/Kublai.md",
    "Möngke": "memory/agents/Möngke.md",
    "Chagatai": "memory/agents/Chagatai.md",
    "Temüjin": "memory/agents/Temüjin.md",
    "Jochi": "memory/agents/Jochi.md",
    "Ögedei": "memory/agents/Ögedei.md",
}

@dataclass
class AgentMemory:
    """Individual agent memory structure."""
    agent_name: str
    observations: List[str] = field(default_factory=list)
    learnings: List[str] = field(default_factory=list)
    relationships: Dict[str, str] = field(default_factory=dict)
    decisions: List[str] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    
    def add_observation(self, observation: str):
        """Add something the agent noticed."""
        self.observations.append({
            "text": observation,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def add_learning(self, learning: str):
        """Add something the agent learned."""
        self.learnings.append({
            "text": learning,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def update_relationship(self, other_agent: str, perspective: str):
        """Update how this agent views another agent."""
        self.relationships[other_agent] = {
            "perspective": perspective,
            "updated": datetime.utcnow().isoformat()
        }
    
    def add_decision(self, decision: str):
        """Record a decision this agent contributed to."""
        self.decisions.append({
            "text": decision,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def add_insight(self, insight: str):
        """Add a signature insight unique to this agent."""
        self.insights.append({
            "text": insight,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def to_markdown(self) -> str:
        """Convert memory to markdown for storage."""
        md = f"# {self.agent_name}'s Memory\n\n"
        md += f"*Last updated: {datetime.utcnow().isoformat()}*\n\n"
        
        md += "## 🔍 Personal Observations\n"
        for obs in self.observations[-10:]:  # Last 10
            md += f"- {obs['text']}\n"
        if not self.observations:
            md += "*No observations yet*\n"
        md += "\n"
        
        md += "## 📚 Key Learnings\n"
        for learn in self.learnings[-10:]:
            md += f"- {learn['text']}\n"
        if not self.learnings:
            md += "*No learnings yet*\n"
        md += "\n"
        
        md += "## 👥 Relationships\n"
        for agent, rel in self.relationships.items():
            md += f"- **{agent}**: {rel['perspective']}\n"
        if not self.relationships:
            md += "*Relationship perspectives not yet formed*\n"
        md += "\n"
        
        md += "## ✅ Decisions Made\n"
        for dec in self.decisions[-10:]:
            md += f"- {dec['text']}\n"
        if not self.decisions:
            md += "*No major decisions yet*\n"
        md += "\n"
        
        md += "## 💡 Signature Insights\n"
        for ins in self.insights[-5:]:
            md += f"- {ins['text']}\n"
        if not self.insights:
            md += "*Insights developing*\n"
        
        return md
    
    def save(self):
        """Save memory to file."""
        path = AGENT_MEMORY_PATHS.get(self.agent_name)
        if path:
            full_path = f"/data/workspace/souls/main/{path}"
            with open(full_path, 'w') as f:
                f.write(self.to_markdown())
    
    @classmethod
    def load(cls, agent_name: str) -> 'AgentMemory':
        """Load agent memory from file."""
        memory = cls(agent_name=agent_name)
        path = AGENT_MEMORY_PATHS.get(agent_name)
        if path:
            full_path = f"/data/workspace/souls/main/{path}"
            if os.path.exists(full_path):
                # Parse existing markdown (simplified)
                with open(full_path, 'r') as f:
                    content = f.read()
                # Could parse sections here if needed
        return memory


class AgentMemoryManager:
    """Manages all agent memories."""
    
    def __init__(self):
        self.memories: Dict[str, AgentMemory] = {}
        self._load_all()
    
    def _load_all(self):
        """Load all agent memories."""
        for agent_name in AGENT_MEMORY_PATHS.keys():
            self.memories[agent_name] = AgentMemory.load(agent_name)
    
    def get_memory(self, agent_name: str) -> AgentMemory:
        """Get a specific agent's memory."""
        if agent_name not in self.memories:
            self.memories[agent_name] = AgentMemory(agent_name=agent_name)
        return self.memories[agent_name]
    
    def record_shared_event(self, event: str, participants: List[str]):
        """Record an event from each participant's perspective."""
        for agent_name in participants:
            memory = self.get_memory(agent_name)
            memory.add_observation(f"Participated in: {event}")
            memory.save()
    
    def record_agent_learning(self, agent_name: str, learning: str):
        """Record something an agent learned."""
        memory = self.get_memory(agent_name)
        memory.add_learning(learning)
        memory.save()
    
    def get_all_memories_summary(self) -> str:
        """Get summary of all agent memories."""
        summary = "## Agent Memory Summary\n\n"
        for agent_name, memory in self.memories.items():
            summary += f"### {agent_name}\n"
            summary += f"- Observations: {len(memory.observations)}\n"
            summary += f"- Learnings: {len(memory.learnings)}\n"
            summary += f"- Insights: {len(memory.insights)}\n\n"
        return summary


# Singleton instance
_memory_manager: Optional[AgentMemoryManager] = None

def get_memory_manager() -> AgentMemoryManager:
    """Get the global memory manager instance."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = AgentMemoryManager()
    return _memory_manager


# Convenience functions
def record_observation(agent_name: str, observation: str):
    """Record an observation for an agent."""
    manager = get_memory_manager()
    memory = manager.get_memory(agent_name)
    memory.add_observation(observation)
    memory.save()

def record_learning(agent_name: str, learning: str):
    """Record a learning for an agent."""
    manager = get_memory_manager()
    memory = manager.get_memory(agent_name)
    memory.add_learning(learning)
    memory.save()

def record_insight(agent_name: str, insight: str):
    """Record a signature insight for an agent."""
    manager = get_memory_manager()
    memory = manager.get_memory(agent_name)
    memory.add_insight(insight)
    memory.save()

def update_relationship(agent_name: str, other_agent: str, perspective: str):
    """Update how one agent views another."""
    manager = get_memory_manager()
    memory = manager.get_memory(agent_name)
    memory.update_relationship(other_agent, perspective)
    memory.save()
