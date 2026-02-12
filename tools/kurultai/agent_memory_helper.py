"""
Agent Memory Helper
Convenient functions for agents to record memories to Neo4j.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kurultai.neo4j_agent_memory import Neo4jAgentMemory, AgentMemoryEntry

# Global memory instance
_memory = None

def get_memory():
    """Get or create the Neo4jAgentMemory singleton."""
    global _memory
    if _memory is None:
        _memory = Neo4jAgentMemory()
    return _memory


def record_observation(agent_name: str, content: str, importance: float = 0.6, task_id: str = None):
    """
    Record an observation for an agent.
    
    Example:
        record_observation("Möngke", "Discovered pattern in agent response times")
    """
    memory = get_memory()
    entry = AgentMemoryEntry(
        id=f"{agent_name}_obs_{int(datetime.utcnow().timestamp())}",
        agent_name=agent_name,
        memory_type="observation",
        content=content,
        source_task_id=task_id,
        importance=importance
    )
    return memory.add_memory(entry)


def record_learning(agent_name: str, content: str, importance: float = 0.7, task_id: str = None):
    """
    Record something an agent learned.
    
    Example:
        record_learning("Temüjin", "Webhook rate limits are 30req/min")
    """
    memory = get_memory()
    entry = AgentMemoryEntry(
        id=f"{agent_name}_learn_{int(datetime.utcnow().timestamp())}",
        agent_name=agent_name,
        memory_type="learning",
        content=content,
        source_task_id=task_id,
        importance=importance
    )
    return memory.add_memory(entry)


def record_insight(agent_name: str, content: str, importance: float = 0.9, task_id: str = None):
    """
    Record a deep insight from an agent.
    
    Example:
        record_insight("Chagatai", "The Council becomes alive when agents converse")
    """
    memory = get_memory()
    entry = AgentMemoryEntry(
        id=f"{agent_name}_insight_{int(datetime.utcnow().timestamp())}",
        agent_name=agent_name,
        memory_type="insight",
        content=content,
        source_task_id=task_id,
        importance=importance
    )
    return memory.add_memory(entry)


def record_interaction(agent_name: str, other_agent: str, content: str, importance: float = 0.5, task_id: str = None):
    """
    Record an interaction between agents.
    
    Example:
        record_interaction("Kublai", "Möngke", "Received critical research on Clawnch ecosystem")
    """
    memory = get_memory()
    entry = AgentMemoryEntry(
        id=f"{agent_name}_interact_{other_agent}_{int(datetime.utcnow().timestamp())}",
        agent_name=agent_name,
        memory_type="interaction",
        content=content,
        source_task_id=task_id,
        related_agents=[other_agent],
        importance=importance
    )
    return memory.add_memory(entry)


def record_decision(agent_name: str, content: str, importance: float = 0.8, task_id: str = None):
    """
    Record a decision made by an agent.
    
    Example:
        record_decision("Kublai", "Prioritized Discord integration over Parse completion")
    """
    memory = get_memory()
    entry = AgentMemoryEntry(
        id=f"{agent_name}_dec_{int(datetime.utcnow().timestamp())}",
        agent_name=agent_name,
        memory_type="decision",
        content=content,
        source_task_id=task_id,
        importance=importance
    )
    return memory.add_memory(entry)


def get_my_memories(agent_name: str, limit: int = 10):
    """Get an agent's recent memories."""
    memory = get_memory()
    return memory.get_agent_memories(agent_name, limit)


def get_my_insights(agent_name: str, limit: int = 5):
    """Get an agent's high-importance insights."""
    memory = get_memory()
    return memory.get_agent_insights(agent_name, limit)


def get_task_context(agent_name: str, task_description: str):
    """Get contextual memories for a task."""
    memory = get_memory()
    return memory.get_task_context(agent_name, task_description)


if __name__ == "__main__":
    # Test
    print("Testing agent memory system...")
    
    # Test recording
    record_observation("TestAgent", "Testing the memory system")
    record_insight("TestAgent", "This system will help agents learn and grow")
    
    # Test retrieval
    memories = get_my_memories("TestAgent")
    print(f"Recorded {len(memories)} test memories")
    
    print("✅ Agent memory system ready!")
