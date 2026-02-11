"""
Kurultai Neo4j Agent Memory System
Each agent has their own memory graph feeding into task context.
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

# Neo4j connection (reuse existing connection pattern)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://switchback.proxy.rlwy.net:38561")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

@dataclass
class AgentMemoryEntry:
    """A single memory entry for an agent."""
    id: str
    agent_name: str
    memory_type: str  # observation, learning, insight, interaction
    content: str
    source_task_id: Optional[str] = None
    related_agents: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    importance: float = 0.5  # 0.0 to 1.0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict:
        return asdict(self)


class Neo4jAgentMemory:
    """
    Neo4j-based agent memory system.
    Each agent has their own memory graph that feeds into task context.
    """
    
    def __init__(self):
        self.driver = None
        self._connect()
        self._ensure_schema()
    
    def _connect(self):
        """Connect to Neo4j."""
        try:
            from neo4j import GraphDatabase
            self.driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            print("✅ Neo4j Agent Memory connected")
        except ImportError:
            print("❌ neo4j package not installed")
            raise
        except Exception as e:
            print(f"❌ Neo4j connection error: {e}")
            raise
    
    def _ensure_schema(self):
        """Ensure memory schema exists."""
        with self.driver.session() as session:
            # Create constraints
            session.run("""
                CREATE CONSTRAINT agent_memory_id IF NOT EXISTS
                FOR (m:AgentMemory) REQUIRE m.id IS UNIQUE
            """)
            
            # Create indexes
            session.run("""
                CREATE INDEX agent_memory_agent IF NOT EXISTS
                FOR (m:AgentMemory) ON (m.agent_name)
            """)
            
            session.run("""
                CREATE INDEX agent_memory_type IF NOT EXISTS
                FOR (m:AgentMemory) ON (m.memory_type)
            """)
            
            session.run("""
                CREATE INDEX agent_memory_task IF NOT EXISTS
                FOR (m:AgentMemory) ON (m.source_task_id)
            """)
    
    def add_memory(self, entry: AgentMemoryEntry) -> bool:
        """
        Add a memory entry for an agent.
        Links to source task if provided.
        """
        with self.driver.session() as session:
            # Create memory node
            result = session.run("""
                MERGE (m:AgentMemory {id: $id})
                SET m.agent_name = $agent_name,
                    m.memory_type = $memory_type,
                    m.content = $content,
                    m.source_task_id = $source_task_id,
                    m.importance = $importance,
                    m.created_at = $created_at
                WITH m
                UNWIND $related_agents as related_agent
                MERGE (a:Agent {name: related_agent})
                MERGE (m)-[:INVOLVES]->(a)
                WITH m
                UNWIND $tags as tag
                MERGE (t:Tag {name: tag})
                MERGE (m)-[:TAGGED]->(t)
                RETURN m.id as memory_id
            """, {
                "id": entry.id,
                "agent_name": entry.agent_name,
                "memory_type": entry.memory_type,
                "content": entry.content,
                "source_task_id": entry.source_task_id or "",
                "importance": entry.importance,
                "created_at": entry.created_at,
                "related_agents": entry.related_agents,
                "tags": entry.tags
            })
            
            # Link to source task if provided
            if entry.source_task_id:
                session.run("""
                    MATCH (m:AgentMemory {id: $memory_id})
                    MATCH (t:Task {id: $task_id})
                    MERGE (m)-[:GENERATED_FROM]->(t)
                """, {"memory_id": entry.id, "task_id": entry.source_task_id})
            
            return True
    
    def get_agent_memories(self, agent_name: str, 
                          memory_type: Optional[str] = None,
                          limit: int = 10) -> List[Dict]:
        """
        Get memories for a specific agent.
        Used to populate agent context for new tasks.
        """
        with self.driver.session() as session:
            if memory_type:
                result = session.run("""
                    MATCH (m:AgentMemory)
                    WHERE m.agent_name = $agent_name
                    AND m.memory_type = $memory_type
                    RETURN m {
                        .id, .agent_name, .memory_type, .content,
                        .source_task_id, .importance, .created_at
                    } as memory
                    ORDER BY m.importance DESC, m.created_at DESC
                    LIMIT $limit
                """, {"agent_name": agent_name, "memory_type": memory_type, "limit": limit})
            else:
                result = session.run("""
                    MATCH (m:AgentMemory)
                    WHERE m.agent_name = $agent_name
                    RETURN m {
                        .id, .agent_name, .memory_type, .content,
                        .source_task_id, .importance, .created_at
                    } as memory
                    ORDER BY m.importance DESC, m.created_at DESC
                    LIMIT $limit
                """, {"agent_name": agent_name, "limit": limit})
            
            return [record["memory"] for record in result]
    
    def get_relevant_memories_for_task(self, agent_name: str, 
                                       task_description: str,
                                       task_tags: List[str] = None) -> List[Dict]:
        """
        Get memories relevant to a specific task.
        Uses tag matching and importance scoring.
        """
        with self.driver.session() as session:
            # Get memories with matching tags or high importance
            result = session.run("""
                MATCH (m:AgentMemory)-[:TAGGED]->(t:Tag)
                WHERE m.agent_name = $agent_name
                AND (t.name IN $task_tags OR m.importance > 0.7)
                RETURN DISTINCT m {
                    .id, .agent_name, .memory_type, .content,
                    .source_task_id, .importance, .created_at
                } as memory
                ORDER BY m.importance DESC, m.created_at DESC
                LIMIT 5
            """, {"agent_name": agent_name, "task_tags": task_tags or []})
            
            memories = [record["memory"] for record in result]
            
            # If no tag matches, get most recent high-importance memories
            if not memories:
                result = session.run("""
                    MATCH (m:AgentMemory)
                    WHERE m.agent_name = $agent_name
                    RETURN m {
                        .id, .agent_name, .memory_type, .content,
                        .source_task_id, .importance, .created_at
                    } as memory
                    ORDER BY m.created_at DESC
                    LIMIT 3
                """, {"agent_name": agent_name})
                memories = [record["memory"] for record in result]
            
            return memories
    
    def get_agent_context_for_task(self, agent_name: str, task_id: str) -> Dict[str, Any]:
        """
        Build complete context for an agent working on a task.
        Returns memories, related tasks, and agent state.
        """
        context = {
            "agent_name": agent_name,
            "memories": [],
            "related_tasks": [],
            "insights": [],
            "learnings": []
        }
        
        with self.driver.session() as session:
            # Get recent memories
            context["memories"] = self.get_agent_memories(agent_name, limit=5)
            
            # Get insights specifically
            context["insights"] = self.get_agent_memories(
                agent_name, memory_type="insight", limit=3
            )
            
            # Get learnings
            context["learnings"] = self.get_agent_memories(
                agent_name, memory_type="learning", limit=3
            )
            
            # Get related tasks (tasks this agent has memories of)
            result = session.run("""
                MATCH (m:AgentMemory)-[:GENERATED_FROM]->(t:Task)
                WHERE m.agent_name = $agent_name
                RETURN DISTINCT t.id as task_id, t.description as description
                LIMIT 5
            """, {"agent_name": agent_name})
            context["related_tasks"] = [
                {"id": r["task_id"], "description": r["description"]}
                for r in result
            ]
        
        return context
    
    def record_task_completion_memory(self, agent_name: str, task_id: str,
                                     task_description: str, 
                                     completion_notes: str):
        """
        Record memory when an agent completes a task.
        Links the learning to the task.
        """
        entry = AgentMemoryEntry(
            id=f"{agent_name.lower()}-task-{task_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            agent_name=agent_name,
            memory_type="learning",
            content=f"Completed task '{task_description}': {completion_notes}",
            source_task_id=task_id,
            importance=0.8
        )
        self.add_memory(entry)
    
    def record_interaction_memory(self, agent_name: str, 
                                 interacted_with: str,
                                 interaction_summary: str,
                                 source_task_id: Optional[str] = None):
        """
        Record memory of interaction with another agent.
        """
        entry = AgentMemoryEntry(
            id=f"{agent_name.lower()}-interaction-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            agent_name=agent_name,
            memory_type="interaction",
            content=interaction_summary,
            source_task_id=source_task_id,
            related_agents=[interacted_with],
            importance=0.6
        )
        self.add_memory(entry)
    
    def get_agent_relationships(self, agent_name: str) -> Dict[str, List[str]]:
        """
        Get all relationships an agent has with other agents.
        Returns dict of agent_name -> list of interaction memories.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (m:AgentMemory)-[:INVOLVES]->(a:Agent)
                WHERE m.agent_name = $agent_name
                AND a.name <> $agent_name
                RETURN a.name as other_agent, 
                       collect(m.content) as interactions
            """, {"agent_name": agent_name})
            
            return {r["other_agent"]: r["interactions"] for r in result}
    
    def migrate_from_markdown(self, agent_name: str):
        """
        Migrate existing markdown memories to Neo4j.
        """
        markdown_path = f"/data/workspace/souls/main/memory/agents/{agent_name}.md"
        
        if not os.path.exists(markdown_path):
            print(f"No markdown file for {agent_name}")
            return
        
        with open(markdown_path, 'r') as f:
            content = f.read()
        
        # Parse simple markdown structure
        # This is a basic parser - could be enhanced
        current_section = None
        observations = []
        learnings = []
        insights = []
        
        for line in content.split('\n'):
            if '## 🔍 Personal Observations' in line:
                current_section = 'observations'
            elif '## 📚 Key Learnings' in line:
                current_section = 'learnings'
            elif '## 💡 Signature Insights' in line:
                current_section = 'insights'
            elif line.startswith('- ') and current_section:
                text = line[2:].strip()
                if text and text != '*No observations yet*':
                    if current_section == 'observations':
                        observations.append(text)
                    elif current_section == 'learnings':
                        learnings.append(text)
                    elif current_section == 'insights':
                        insights.append(text)
        
        # Add to Neo4j
        for obs in observations:
            entry = AgentMemoryEntry(
                id=f"{agent_name.lower()}-obs-{hash(obs) % 1000000}",
                agent_name=agent_name,
                memory_type="observation",
                content=obs,
                importance=0.5
            )
            self.add_memory(entry)
        
        for learn in learnings:
            entry = AgentMemoryEntry(
                id=f"{agent_name.lower()}-learn-{hash(learn) % 1000000}",
                agent_name=agent_name,
                memory_type="learning",
                content=learn,
                importance=0.7
            )
            self.add_memory(entry)
        
        for ins in insights:
            entry = AgentMemoryEntry(
                id=f"{agent_name.lower()}-insight-{hash(ins) % 1000000}",
                agent_name=agent_name,
                memory_type="insight",
                content=ins,
                importance=0.9
            )
            self.add_memory(entry)
        
        print(f"✅ Migrated {len(observations)} observations, {len(learnings)} learnings, {len(insights)} insights for {agent_name}")
    
    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()


# Convenience functions for use in agents
def record_agent_memory(agent_name: str, memory_type: str, content: str,
                       source_task_id: Optional[str] = None,
                       importance: float = 0.5):
    """Quick function to record a memory for an agent."""
    memory = Neo4jAgentMemory()
    entry = AgentMemoryEntry(
        id=f"{agent_name.lower()}-{memory_type}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        agent_name=agent_name,
        memory_type=memory_type,
        content=content,
        source_task_id=source_task_id,
        importance=importance
    )
    memory.add_memory(entry)
    memory.close()


def get_task_context(agent_name: str, task_id: str) -> Dict:
    """Get context for an agent working on a task."""
    memory = Neo4jAgentMemory()
    context = memory.get_agent_context_for_task(agent_name, task_id)
    memory.close()
    return context
