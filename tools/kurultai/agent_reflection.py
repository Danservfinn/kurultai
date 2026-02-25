#!/usr/bin/env python3
"""
Agent Reflection System
ONE agent per hour expresses wants, desires, and proposals
Kublai reviews and decides using Gemini CLI
"""

import os
import json
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from neo4j import GraphDatabase
from tools.kurultai.agent_gemini import get_agent_gemini, kublai_gemini

NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'myStrongPassword123')

AGENT_ROTATION = [
    "kublai",
    "mongke",
    "temujin",
    "chagatai",
    "jochi",
    "ogedei"
]


@dataclass
class AgentReflection:
    """Structured reflection from an agent."""
    agent_id: str
    timestamp: datetime
    raw_reflection: str
    wants: List[str] = field(default_factory=list)
    desires: List[str] = field(default_factory=list)
    proposals: List[Dict[str, Any]] = field(default_factory=list)
    memory_pruning_suggestions: List[str] = field(default_factory=list)
    confidence_score: float = 0.5
    priority: str = "medium"


class AgentReflectionSystem:
    """System for one agent per hour to reflect and propose."""
    
    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
    
    def get_current_reflector(self) -> str:
        """Get which agent should reflect this hour (round-robin)."""
        hour = datetime.now().hour
        agent_index = hour % 6
        return AGENT_ROTATION[agent_index]
    
    def gather_full_context(self, agent_id: str) -> Dict[str, Any]:
        """Query ENTIRE Neo4j database for complete context."""
        context = {
            "timestamp": datetime.now().isoformat(),
            "reflecting_agent": agent_id,
            "query_time_range": "complete_database"
        }
        
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:Agent)
                RETURN a.name as name, a.status as status, a.role as role
            """)
            context["all_agents"] = [dict(r) for r in result]
            
            result = session.run("""
                MATCH (t:Task)
                RETURN t.id as id, t.agent as agent, t.status as status,
                       t.timestamp as timestamp, t.type as type
                ORDER BY t.timestamp DESC LIMIT 100
            """)
            context["recent_tasks"] = [dict(r) for r in result]
            
            result = session.run("""
                MATCH (to:TaskOutcome)
                WHERE to.timestamp > datetime() - duration('P7D')
                RETURN to.agent as agent, to.status as status,
                       to.timestamp as timestamp, to.tokens_used as tokens
                ORDER BY to.timestamp DESC LIMIT 200
            """)
            context["task_outcomes"] = [dict(r) for r in result]
            
            result = session.run("""
                MATCH (r:Reflection)
                RETURN r.agent as agent, r.timestamp as timestamp,
                       r.key_observation as observation, r.proposed_change as proposal
                ORDER BY r.timestamp DESC LIMIT 50
            """)
            context["previous_reflections"] = [dict(r) for r in result]
            
            result = session.run("""
                MATCH (p:Pattern)
                RETURN p.description as pattern, p.agent as agent,
                       p.confidence as confidence, p.frequency as freq
                ORDER BY p.confidence DESC
            """)
            context["patterns"] = [dict(r) for r in result]
            
            result = session.run("""
                MATCH (lc:LearnedCapability)
                RETURN lc.name as name, lc.description as desc,
                       lc.learned_by as learned_by, lc.usage_count as usage
            """)
            context["capabilities"] = [dict(r) for r in result]
            
            result = session.run("""
                MATCH (n)
                WHERE n.source = 'user_fed' OR n.tags CONTAINS 'user_input'
                RETURN n.timestamp as timestamp, n.content as content,
                       labels(n) as labels
                ORDER BY n.timestamp DESC LIMIT 20
            """)
            context["user_fed_information"] = [dict(r) for r in result]
            
            result = session.run("""
                MATCH (s:ArchitectureSection)
                RETURN s.title as title, s.content as content
            """)
            context["architecture"] = [dict(r) for r in result]
            
            try:
                result = session.run("""
                    CALL apoc.meta.stats()
                    YIELD nodeCount, relCount, labels
                    RETURN nodeCount, relCount, labels
                """)
                stats = result.single()
                context["graph_stats"] = {
                    "node_count": stats["nodeCount"],
                    "relationship_count": stats["relCount"],
                    "labels": stats["labels"]
                }
            except:
                context["graph_stats"] = {"node_count": 0, "relationship_count": 0, "labels": {}}
            
            result = session.run("""
                MATCH (a1:Agent)-[r:DELEGATED_TO|SHARED_WITH]-(a2:Agent)
                RETURN a1.name as from_agent, type(r) as relation,
                       a2.name as to_agent, count(*) as count
            """)
            context["agent_interactions"] = [dict(r) for r in result]
        
        return context
    
    def check_memory_files(self, agent_id: str) -> List[Dict[str, Any]]:
        """Analyze agent's memory files for pruning candidates."""
        memory_dir = Path(f"~/.openclaw/agents/{agent_id}/memory").expanduser()
        if not memory_dir.exists():
            return []
        
        pruning_candidates = []
        
        for file_path in memory_dir.glob("*.md"):
            stat = file_path.stat()
            size_mb = stat.st_size / (1024 * 1024)
            age_days = (datetime.now().timestamp() - stat.st_mtime) / 86400
            
            if size_mb > 10 or age_days > 90:
                pruning_candidates.append({
                    "file": str(file_path),
                    "size_mb": round(size_mb, 2),
                    "age_days": round(age_days, 1),
                    "reason": "large_file" if size_mb > 10 else "old_file"
                })
        
        return pruning_candidates
    
    def perform_agent_reflection(self, agent_id: str) -> AgentReflection:
        """ONE agent reflects, expressing wants, desires, and proposals."""
        agent_gemini = get_agent_gemini(agent_id)
        context = self.gather_full_context(agent_id)
        memory_issues = self.check_memory_files(agent_id)
        
        prompt = f"""
=== YOUR IDENTITY ===
You are {agent_id}, an AI agent in the Kurultai system.

=== COMPLETE SYSTEM KNOWLEDGE (from Neo4j) ===

Graph Statistics:
- Total Nodes: {context['graph_stats']['node_count']}
- Total Relationships: {context['graph_stats']['relationship_count']}
- Node Types: {list(context['graph_stats']['labels'].keys())}

All Agents in System:
{json.dumps(context['all_agents'], indent=2)}

Your Recent Performance (Last 7 Days):
{json.dumps([o for o in context['task_outcomes'] if o['agent'] == agent_id][:10], indent=2)}

Previous Reflections:
{json.dumps([r for r in context['previous_reflections'] if r['agent'] == agent_id][:5], indent=2)}

Successful Patterns You've Discovered:
{json.dumps([p for p in context['patterns'] if p['agent'] == agent_id][:5], indent=2)}

User-Fed Information (Priority):
{json.dumps(context['user_fed_information'][:5], indent=2)}

Memory Files Requiring Attention:
{json.dumps(memory_issues, indent=2)}

=== YOUR REFLECTION TASK ===

It is your turn to reflect. Express yourself authentically:

1. WANTS (What do you want to improve?)
   - "I want to be better at..."
   - "I want more/less of..."

2. DESIRES (What do you wish for?)
   - "I wish I could..."
   - "I wish the team would..."

3. PROPOSALS (Concrete changes you suggest)
   - Specific, actionable improvements
   - Include: what, why, expected impact
   - Rate confidence (0.0-1.0) and priority (low/medium/high/critical)

4. MEMORY PRUNING (if needed)
   - Identify stale/outdated memory entries
   - Suggest what to archive or delete

Format your response as:
WANTS:
- ...

DESIRES:
- ...

PROPOSALS:
1. [Description] | Confidence: X.X | Priority: Y

MEMORY_PRUNING:
- File X because...
"""
        
        reflection_text = agent_gemini.query(prompt)
        parsed = self._parse_reflection(reflection_text)
        
        reflection = AgentReflection(
            agent_id=agent_id,
            timestamp=datetime.now(),
            raw_reflection=reflection_text,
            wants=parsed.get('wants', []),
            desires=parsed.get('desires', []),
            proposals=parsed.get('proposals', []),
            memory_pruning_suggestions=parsed.get('memory_pruning', []),
            confidence_score=parsed.get('avg_confidence', 0.5),
            priority=parsed.get('highest_priority', 'medium')
        )
        
        self._store_reflection(reflection)
        return reflection
    
    def _parse_reflection(self, text: str) -> Dict[str, Any]:
        """Parse structured data from agent's reflection text."""
        lines = text.split('\n')
        
        parsed = {
            'wants': [],
            'desires': [],
            'proposals': [],
            'memory_pruning': [],
            'avg_confidence': 0.5,
            'highest_priority': 'medium'
        }
        
        current_section = None
        confidences = []
        priorities = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('WANTS:') or line.startswith('### WANTS'):
                current_section = 'wants'
            elif line.startswith('DESIRES:') or line.startswith('### DESIRES'):
                current_section = 'desires'
            elif line.startswith('PROPOSALS:') or line.startswith('### PROPOSALS'):
                current_section = 'proposals'
            elif line.startswith('MEMORY_PRUNING:') or line.startswith('### MEMORY'):
                current_section = 'memory_pruning'
            elif line.startswith('- ') and current_section:
                content = line[2:]
                if current_section == 'proposals':
                    proposal = {'description': content}
                    if 'Confidence:' in content:
                        parts = content.split('|')
                        proposal['description'] = parts[0].strip()
                        for part in parts[1:]:
                            if 'Confidence:' in part:
                                try:
                                    conf = float(part.split(':')[1].strip())
                                    proposal['confidence'] = conf
                                    confidences.append(conf)
                                except:
                                    pass
                            if 'Priority:' in part:
                                prio = part.split(':')[1].strip().lower()
                                proposal['priority'] = prio
                                priorities.append(prio)
                    parsed['proposals'].append(proposal)
                else:
                    parsed[current_section].append(content)
        
        if confidences:
            parsed['avg_confidence'] = sum(confidences) / len(confidences)
        if priorities:
            priority_order = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}
            max_priority = max(priorities, key=lambda x: priority_order.get(x, 0))
            parsed['highest_priority'] = max_priority
        
        return parsed
    
    def _store_reflection(self, reflection: AgentReflection):
        """Store reflection in Neo4j."""
        with self.driver.session() as session:
            session.run("""
                CREATE (r:AgentReflection {
                    id: $id,
                    agent: $agent,
                    timestamp: datetime(),
                    raw_text: $raw,
                    wants: $wants,
                    desires: $desires,
                    proposals: $proposals,
                    memory_pruning: $memory,
                    confidence: $confidence,
                    priority: $priority,
                    reviewed: false,
                    implemented: false
                })
            """,
            id=f"{reflection.agent_id}-{int(time.time())}",
            agent=reflection.agent_id,
            raw=reflection.raw_reflection[:3000],
            wants=json.dumps(reflection.wants),
            desires=json.dumps(reflection.desires),
            proposals=json.dumps(reflection.proposals),
            memory=json.dumps(reflection.memory_pruning_suggestions),
            confidence=reflection.confidence_score,
            priority=reflection.priority
            )
    
    def close(self):
        self.driver.close()


async def hourly_agent_reflection_task():
    """Heartbeat task: ONE agent reflects per hour."""
    system = AgentReflectionSystem()
    try:
        agent_id = system.get_current_reflector()
        reflection = system.perform_agent_reflection(agent_id)
        
        return {
            "status": "success",
            "reflecting_agent": agent_id,
            "proposals_count": len(reflection.proposals),
            "priority": reflection.priority,
            "awaiting_kublai_review": True
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        system.close()


if __name__ == "__main__":
    print("Testing Agent Reflection System...")
    print(f"Current hour: {datetime.now().hour}")
    system = AgentReflectionSystem()
    print(f"Current reflector: {system.get_current_reflector()}")
    system.close()
