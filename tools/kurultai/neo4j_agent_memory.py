"""
Kurultai Neo4j Agent Memory System with Fallback Support
Each agent has their own memory graph feeding into task context.

FALLBACK MODE:
When Neo4j is unavailable, the system automatically falls back to SQLite storage.
Data is automatically synchronized back to Neo4j when connection is restored.
"""

import os
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field, asdict

# Import resilient connection
from .resilient_neo4j import (
    ResilientNeo4jConnection, 
    FallbackStorage,
    get_resilient_connection
)

# Neo4j connection settings
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
    Neo4j-based agent memory system with SQLite fallback.
    Each agent has their own memory graph that feeds into task context.
    
    When Neo4j is unavailable, automatically falls back to SQLite storage.
    All data is synchronized back to Neo4j when connection is restored.
    """
    
    def __init__(self, fallback_enabled: bool = True):
        """
        Initialize agent memory system.
        
        Args:
            fallback_enabled: Whether to enable SQLite fallback when Neo4j is unavailable
        """
        self.fallback_enabled = fallback_enabled
        self._connection: Optional[ResilientNeo4jConnection] = None
        self._fallback: Optional[FallbackStorage] = None
        
        self._connect()
    
    def _connect(self):
        """Connect to Neo4j with fallback support."""
        try:
            self._connection = get_resilient_connection(
                uri=NEO4J_URI,
                username=NEO4J_USER,
                password=NEO4J_PASSWORD,
                fallback_enabled=self.fallback_enabled
            )
            
            self._fallback = self._connection.fallback if self.fallback_enabled else None
            
            # Only ensure schema if we're not in fallback mode
            if not self._connection.is_fallback_mode():
                self._ensure_schema()
                print("✅ Neo4j Agent Memory connected")
            else:
                print("⚠️ Neo4j unavailable - using SQLite fallback storage")
                
        except Exception as e:
            print(f"❌ Failed to initialize agent memory: {e}")
            if not self.fallback_enabled:
                raise
            # Create standalone fallback
            self._fallback = FallbackStorage()
            print("📦 Using standalone SQLite fallback storage")
    
    def _ensure_schema(self):
        """Ensure memory schema exists in Neo4j."""
        def do_ensure_schema(driver):
            with driver.session() as session:
                # Create constraints
                try:
                    session.run("""
                        CREATE CONSTRAINT agent_memory_id IF NOT EXISTS
                        FOR (m:AgentMemory) REQUIRE m.id IS UNIQUE
                    """)
                except Exception as e:
                    # Constraint might already exist or not supported
                    pass
                
                # Create indexes
                try:
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
                except Exception as e:
                    pass
        
        if self._connection and not self._connection.is_fallback_mode():
            self._connection.execute(do_ensure_schema)
    
    def _is_fallback_mode(self) -> bool:
        """Check if we're operating in fallback mode."""
        if self._connection:
            return self._connection.is_fallback_mode()
        return self._fallback is not None
    
    def add_memory(self, entry: AgentMemoryEntry) -> bool:
        """
        Add a memory entry for an agent.
        Links to source task if provided.
        
        Works in both Neo4j and fallback modes.
        """
        if self._is_fallback_mode():
            return self._add_memory_fallback(entry)
        
        def do_add_memory(driver):
            with driver.session() as session:
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
        
        try:
            result = self._connection.execute(do_add_memory)
            if isinstance(result, dict) and result.get('_fallback'):
                # Neo4j failed, use fallback
                return self._add_memory_fallback(entry)
            return result if isinstance(result, bool) else True
        except Exception as e:
            print(f"⚠️ Neo4j add_memory failed, using fallback: {e}")
            return self._add_memory_fallback(entry)
    
    def _add_memory_fallback(self, entry: AgentMemoryEntry) -> bool:
        """Add memory using fallback storage."""
        if not self._fallback:
            print("❌ Fallback storage not available")
            return False
        
        return self._fallback.add_memory(entry.to_dict())
    
    def get_agent_memories(self, agent_name: str, 
                          memory_type: Optional[str] = None,
                          limit: int = 10) -> List[Dict]:
        """
        Get memories for a specific agent.
        Used to populate agent context for new tasks.
        
        Works in both Neo4j and fallback modes.
        """
        if self._is_fallback_mode():
            return self._get_agent_memories_fallback(agent_name, memory_type, limit)
        
        def do_get_memories(driver):
            with driver.session() as session:
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
        
        try:
            result = self._connection.execute(do_get_memories)
            if isinstance(result, dict) and result.get('_fallback'):
                return self._get_agent_memories_fallback(agent_name, memory_type, limit)
            return result if isinstance(result, list) else []
        except Exception as e:
            print(f"⚠️ Neo4j get_agent_memories failed, using fallback: {e}")
            return self._get_agent_memories_fallback(agent_name, memory_type, limit)
    
    def _get_agent_memories_fallback(self, agent_name: str,
                                     memory_type: Optional[str] = None,
                                     limit: int = 10) -> List[Dict]:
        """Get memories using fallback storage."""
        if not self._fallback:
            return []
        
        return self._fallback.get_agent_memories(agent_name, memory_type, limit)
    
    def get_relevant_memories_for_task(self, agent_name: str, 
                                       task_description: str,
                                       task_tags: List[str] = None) -> List[Dict]:
        """
        Get memories relevant to a specific task.
        Uses tag matching and importance scoring.
        
        Limited support in fallback mode (only importance-based filtering).
        """
        if self._is_fallback_mode():
            # Fallback mode: just get recent high-importance memories
            return self._get_agent_memories_fallback(agent_name, None, 5)
        
        def do_get_relevant(driver):
            with driver.session() as session:
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
        
        try:
            result = self._connection.execute(do_get_relevant)
            if isinstance(result, dict) and result.get('_fallback'):
                return self._get_agent_memories_fallback(agent_name, None, 5)
            return result if isinstance(result, list) else []
        except Exception as e:
            print(f"⚠️ Neo4j get_relevant_memories failed, using fallback: {e}")
            return self._get_agent_memories_fallback(agent_name, None, 5)
    
    def get_agent_context_for_task(self, agent_name: str, task_id: str) -> Dict[str, Any]:
        """
        Build complete context for an agent working on a task.
        Returns memories, related tasks, and agent state.
        
        Limited support in fallback mode (memories only, no graph relationships).
        """
        context = {
            "agent_name": agent_name,
            "memories": [],
            "related_tasks": [],
            "insights": [],
            "learnings": [],
            "fallback_mode": self._is_fallback_mode()
        }
        
        if self._is_fallback_mode():
            # Fallback mode: get basic memories only
            context["memories"] = self._get_agent_memories_fallback(agent_name, None, 5)
            context["insights"] = self._get_agent_memories_fallback(agent_name, "insight", 3)
            context["learnings"] = self._get_agent_memories_fallback(agent_name, "learning", 3)
            return context
        
        def do_get_context(driver):
            ctx = {
                "agent_name": agent_name,
                "memories": [],
                "related_tasks": [],
                "insights": [],
                "learnings": [],
                "fallback_mode": False
            }
            
            with driver.session() as session:
                # Get recent memories
                ctx["memories"] = self.get_agent_memories(agent_name, limit=5)
                
                # Get insights specifically
                ctx["insights"] = self.get_agent_memories(
                    agent_name, memory_type="insight", limit=3
                )
                
                # Get learnings
                ctx["learnings"] = self.get_agent_memories(
                    agent_name, memory_type="learning", limit=3
                )
                
                # Get related tasks (tasks this agent has memories of)
                result = session.run("""
                    MATCH (m:AgentMemory)-[:GENERATED_FROM]->(t:Task)
                    WHERE m.agent_name = $agent_name
                    RETURN DISTINCT t.id as task_id, t.description as description
                    LIMIT 5
                """, {"agent_name": agent_name})
                ctx["related_tasks"] = [
                    {"id": r["task_id"], "description": r["description"]}
                    for r in result
                ]
            
            return ctx
        
        try:
            result = self._connection.execute(do_get_context)
            if isinstance(result, dict) and result.get('_fallback'):
                # Use fallback
                context["memories"] = self._get_agent_memories_fallback(agent_name, None, 5)
                context["insights"] = self._get_agent_memories_fallback(agent_name, "insight", 3)
                context["learnings"] = self._get_agent_memories_fallback(agent_name, "learning", 3)
                return context
            return result if isinstance(result, dict) else context
        except Exception as e:
            print(f"⚠️ Neo4j get_agent_context failed, using fallback: {e}")
            context["memories"] = self._get_agent_memories_fallback(agent_name, None, 5)
            context["insights"] = self._get_agent_memories_fallback(agent_name, "insight", 3)
            context["learnings"] = self._get_agent_memories_fallback(agent_name, "learning", 3)
            return context
    
    def record_task_completion_memory(self, agent_name: str, task_id: str,
                                     task_description: str, 
                                     completion_notes: str):
        """Record memory when an agent completes a task."""
        entry = AgentMemoryEntry(
            id=f"{agent_name.lower()}-task-{task_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            agent_name=agent_name,
            memory_type="learning",
            content=f"Completed task '{task_description}': {completion_notes}",
            source_task_id=task_id,
            importance=0.8
        )
        return self.add_memory(entry)
    
    def record_interaction_memory(self, agent_name: str, 
                                 interacted_with: str,
                                 interaction_summary: str,
                                 source_task_id: Optional[str] = None):
        """Record memory of interaction with another agent."""
        entry = AgentMemoryEntry(
            id=f"{agent_name.lower()}-interaction-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            agent_name=agent_name,
            memory_type="interaction",
            content=interaction_summary,
            source_task_id=source_task_id,
            related_agents=[interacted_with],
            importance=0.6
        )
        return self.add_memory(entry)
    
    def get_agent_relationships(self, agent_name: str) -> Dict[str, List[str]]:
        """
        Get all relationships an agent has with other agents.
        
        NOT SUPPORTED IN FALLBACK MODE - returns empty dict.
        """
        if self._is_fallback_mode():
            print("⚠️ Agent relationships not available in fallback mode")
            return {}
        
        def do_get_relationships(driver):
            with driver.session() as session:
                result = session.run("""
                    MATCH (m:AgentMemory)-[:INVOLVES]->(a:Agent)
                    WHERE m.agent_name = $agent_name
                    AND a.name <> $agent_name
                    RETURN a.name as other_agent, 
                           collect(m.content) as interactions
                """, {"agent_name": agent_name})
                
                return {r["other_agent"]: r["interactions"] for r in result}
        
        try:
            result = self._connection.execute(do_get_relationships)
            if isinstance(result, dict) and result.get('_fallback'):
                return {}
            return result if isinstance(result, dict) else {}
        except Exception as e:
            print(f"⚠️ Neo4j get_agent_relationships failed: {e}")
            return {}
    
    def migrate_from_markdown(self, agent_name: str) -> Dict[str, int]:
        """
        Migrate existing markdown memories to Neo4j.
        
        Works in both modes (stores to Neo4j if available, fallback if not).
        """
        markdown_path = f"/data/workspace/souls/main/memory/agents/{agent_name}.md"
        
        if not os.path.exists(markdown_path):
            print(f"No markdown file for {agent_name}")
            return {"observations": 0, "learnings": 0, "insights": 0}
        
        with open(markdown_path, 'r') as f:
            content = f.read()
        
        # Parse simple markdown structure
        observations = []
        learnings = []
        insights = []
        
        current_section = None
        for line in content.split('\n'):
            if '## 🔍 Personal Observations' in line:
                current_section = 'observations'
            elif '## 📚 Key Learnings' in line:
                current_section = 'learnings'
            elif '## 💡 Signature Insights' in line:
                current_section = 'insights'
            elif line.startswith('- ') and current_section:
                text = line[2:].strip()
                if text and text != '*No observations yet*' and not text.startswith('*'):
                    if current_section == 'observations':
                        observations.append(text)
                    elif current_section == 'learnings':
                        learnings.append(text)
                    elif current_section == 'insights':
                        insights.append(text)
        
        # Add to storage
        success_count = {"observations": 0, "learnings": 0, "insights": 0}
        
        for obs in observations:
            entry = AgentMemoryEntry(
                id=f"{agent_name.lower()}-obs-{hashlib.md5(obs.encode()).hexdigest()[:8]}",
                agent_name=agent_name,
                memory_type="observation",
                content=obs,
                importance=0.5
            )
            if self.add_memory(entry):
                success_count["observations"] += 1
        
        for learn in learnings:
            entry = AgentMemoryEntry(
                id=f"{agent_name.lower()}-learn-{hashlib.md5(learn.encode()).hexdigest()[:8]}",
                agent_name=agent_name,
                memory_type="learning",
                content=learn,
                importance=0.7
            )
            if self.add_memory(entry):
                success_count["learnings"] += 1
        
        for ins in insights:
            entry = AgentMemoryEntry(
                id=f"{agent_name.lower()}-insight-{hashlib.md5(ins.encode()).hexdigest()[:8]}",
                agent_name=agent_name,
                memory_type="insight",
                content=ins,
                importance=0.9
            )
            if self.add_memory(entry):
                success_count["insights"] += 1
        
        print(f"✅ Migrated {success_count['observations']} observations, "
              f"{success_count['learnings']} learnings, "
              f"{success_count['insights']} insights for {agent_name}")
        
        return success_count
    
    def get_status(self) -> Dict[str, Any]:
        """Get memory system status including connection info."""
        status = {
            "fallback_mode": self._is_fallback_mode(),
            "fallback_enabled": self.fallback_enabled,
        }
        
        if self._connection:
            status["connection"] = self._connection.get_status()
        
        if self._fallback:
            status["fallback_stats"] = self._fallback.get_stats()
        
        return status
    
    def sync_fallback_to_neo4j(self) -> Dict[str, int]:
        """
        Manually trigger sync of fallback data to Neo4j.
        
        Returns:
            Dict with sync statistics
        """
        if not self._connection or not self._fallback:
            return {"synced": 0, "error": "Fallback or connection not available"}
        
        if self._connection.is_fallback_mode():
            return {"synced": 0, "error": "Neo4j still unavailable"}
        
        # Trigger sync via connection
        pending = self._fallback.get_pending_sync_items(limit=1000)
        
        synced = 0
        for item in pending:
            try:
                # Get full record
                conn = self._fallback._get_connection()
                cursor = conn.cursor()
                cursor.execute(f"SELECT * FROM {item['table_name']} WHERE id = ?", 
                             (item['record_id'],))
                row = cursor.fetchone()
                
                if row:
                    # Sync to Neo4j
                    self._sync_item_to_neo4j(item['table_name'], 
                                            self._fallback._row_to_dict(row))
                    self._fallback.mark_synced(item['table_name'], item['record_id'])
                    synced += 1
            except Exception as e:
                print(f"Failed to sync item {item['id']}: {e}")
        
        return {"synced": synced, "total_pending": len(pending)}
    
    def _sync_item_to_neo4j(self, table_name: str, data: Dict[str, Any]):
        """Sync a single item to Neo4j."""
        if table_name == 'agent_memories':
            def do_sync(driver):
                with driver.session() as session:
                    session.run("""
                        MERGE (m:AgentMemory {id: $id})
                        SET m.agent_name = $agent_name,
                            m.memory_type = $memory_type,
                            m.content = $content,
                            m.source_task_id = $source_task_id,
                            m.importance = $importance,
                            m.created_at = $created_at
                    """, **data)
            
            self._connection.execute(do_sync)
    
    def close(self):
        """Close connections."""
        if self._connection:
            self._connection.close()


# ============================================================================
# Convenience functions
# ============================================================================

def record_agent_memory(agent_name: str, memory_type: str, content: str,
                       source_task_id: Optional[str] = None,
                       importance: float = 0.5) -> bool:
    """
    Quick function to record a memory for an agent.
    
    Works in both Neo4j and fallback modes.
    """
    memory = Neo4jAgentMemory()
    entry = AgentMemoryEntry(
        id=f"{agent_name.lower()}-{memory_type}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        agent_name=agent_name,
        memory_type=memory_type,
        content=content,
        source_task_id=source_task_id,
        importance=importance
    )
    result = memory.add_memory(entry)
    memory.close()
    return result


def get_task_context(agent_name: str, task_id: str) -> Dict:
    """
    Get context for an agent working on a task.
    
    Works in both Neo4j and fallback modes.
    """
    memory = Neo4jAgentMemory()
    context = memory.get_agent_context_for_task(agent_name, task_id)
    memory.close()
    return context


def get_memory_status() -> Dict[str, Any]:
    """Get memory system status."""
    memory = Neo4jAgentMemory()
    status = memory.get_status()
    memory.close()
    return status
