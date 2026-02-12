#!/usr/bin/env python3
"""
Migrate agent memories from Markdown files to Neo4j.
Also sets up sync for ongoing memory updates.
"""

import os
import sys
import re
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'kurultai'))

from neo4j_agent_memory import Neo4jAgentMemory, AgentMemoryEntry

MEMORY_DIR = Path("/data/workspace/souls/main/memory/agents")


def parse_agent_memory_file(filepath: Path) -> dict:
    """Parse an agent's markdown memory file."""
    content = filepath.read_text()
    agent_name = filepath.stem
    
    memories = {
        'agent_name': agent_name,
        'observations': [],
        'learnings': [],
        'insights': [],
        'relationships': [],
        'decisions': []
    }
    
    # Extract observations
    obs_match = re.search(r'## 🔍 Personal Observations\n(.*?)(?=##|\Z)', content, re.DOTALL)
    if obs_match:
        for line in obs_match.group(1).strip().split('\n'):
            line = line.strip()
            if line.startswith('- '):
                memories['observations'].append(line[2:])
    
    # Extract learnings
    learn_match = re.search(r'## 📚 Key Learnings\n(.*?)(?=##|\Z)', content, re.DOTALL)
    if learn_match:
        for line in learn_match.group(1).strip().split('\n'):
            line = line.strip()
            if line.startswith('- ') and 'No learnings' not in line:
                memories['learnings'].append(line[2:])
    
    # Extract insights
    insight_match = re.search(r'## 💡 Signature Insights\n(.*?)(?=##|\Z)', content, re.DOTALL)
    if insight_match:
        for line in insight_match.group(1).strip().split('\n'):
            line = line.strip()
            if line.startswith('- '):
                memories['insights'].append(line[2:])
    
    # Extract relationships
    rel_match = re.search(r'## 👥 Relationships\n(.*?)(?=##|\Z)', content, re.DOTALL)
    if rel_match:
        for line in rel_match.group(1).strip().split('\n'):
            line = line.strip()
            if line.startswith('- **'):
                # Parse "- **Agent**: description"
                match = re.match(r'- \*\*(.+?)\*\*: (.+)', line)
                if match:
                    memories['relationships'].append({
                        'agent': match.group(1),
                        'description': match.group(2)
                    })
    
    # Extract decisions
    dec_match = re.search(r'## ✅ Decisions Made\n(.*?)(?=##|\Z)', content, re.DOTALL)
    if dec_match:
        for line in dec_match.group(1).strip().split('\n'):
            line = line.strip()
            if line.startswith('- ') and 'No major decisions' not in line:
                memories['decisions'].append(line[2:])
    
    return memories


def migrate_to_neo4j():
    """Migrate all agent memory files to Neo4j."""
    neo4j = Neo4jAgentMemory()
    
    print("🔄 Migrating agent memories to Neo4j...\n")
    
    total_memories = 0
    
    for memory_file in MEMORY_DIR.glob("*.md"):
        agent_name = memory_file.stem
        print(f"📄 Processing {agent_name}...")
        
        memories = parse_agent_memory_file(memory_file)
        agent_memories_count = 0
        
        # Migrate observations
        for obs in memories['observations']:
            entry = AgentMemoryEntry(
                id=f"{agent_name}_obs_{hash(obs) % 10000}",
                agent_name=agent_name,
                memory_type="observation",
                content=obs,
                importance=0.6
            )
            if neo4j.add_memory(entry):
                agent_memories_count += 1
        
        # Migrate learnings
        for learning in memories['learnings']:
            entry = AgentMemoryEntry(
                id=f"{agent_name}_learn_{hash(learning) % 10000}",
                agent_name=agent_name,
                memory_type="learning",
                content=learning,
                importance=0.7
            )
            if neo4j.add_memory(entry):
                agent_memories_count += 1
        
        # Migrate insights
        for insight in memories['insights']:
            entry = AgentMemoryEntry(
                id=f"{agent_name}_insight_{hash(insight) % 10000}",
                agent_name=agent_name,
                memory_type="insight",
                content=insight,
                importance=0.9
            )
            if neo4j.add_memory(entry):
                agent_memories_count += 1
        
        # Migrate relationships as interactions
        for rel in memories['relationships']:
            content = f"Relationship with {rel['agent']}: {rel['description']}"
            entry = AgentMemoryEntry(
                id=f"{agent_name}_rel_{rel['agent']}_{hash(content) % 10000}",
                agent_name=agent_name,
                memory_type="interaction",
                content=content,
                related_agents=[rel['agent']],
                importance=0.5
            )
            if neo4j.add_memory(entry):
                agent_memories_count += 1
        
        # Migrate decisions
        for decision in memories['decisions']:
            entry = AgentMemoryEntry(
                id=f"{agent_name}_dec_{hash(decision) % 10000}",
                agent_name=agent_name,
                memory_type="decision",
                content=decision,
                importance=0.8
            )
            if neo4j.add_memory(entry):
                agent_memories_count += 1
        
        print(f"   ✅ Migrated {agent_memories_count} memories\n")
        total_memories += agent_memories_count
    
    print(f"🎉 Migration complete! Total memories: {total_memories}")
    
    # Verify
    print("\n📊 Verification:")
    with neo4j.driver.session() as session:
        result = session.run('MATCH (m:AgentMemory) RETURN count(m) as count')
        count = result.single()['count']
        print(f"   Total AgentMemory nodes in Neo4j: {count}")
        
        result = session.run('''
            MATCH (m:AgentMemory) 
            RETURN m.agent_name as agent, count(m) as count 
            ORDER BY count DESC
        ''')
        for record in result:
            print(f"   - {record['agent']}: {record['count']} memories")


if __name__ == "__main__":
    migrate_to_neo4j()
