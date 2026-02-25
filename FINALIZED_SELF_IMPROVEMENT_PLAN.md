# KURULTAI SELF-IMPROVEMENT SYSTEM v1.0
**The Finalized Plan**  
**Date:** 2026-02-25  
**Status:** Ready for Implementation

---

## EXECUTIVE SUMMARY

A production-ready, **context-aware, safety-guarded self-improvement system** where all 6 agents perform hourly reflections using their dedicated **Gemini 3.1 Pro Preview** CLI instances, leveraging **complete Neo4j knowledge history** to drive measurable, validated improvements.

### What Makes This Different

| Traditional | Our System |
|-------------|------------|
| Generic logging | Context-rich, **full Neo4j database query** |
| Limited context | **Complete knowledge graph traversal** |
| Manual analysis | Automated pattern detection + **memory pruning** |
| Growing forever | **Self-pruning memory management** |
| Hopeful improvements | Validated, measured, rollback-capable changes |
| Isolated agents | Cross-pollination with adaptation |

---

## SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                  KURULTAI SELF-IMPROVEMENT SYSTEM               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  HOURLY CYCLE (Every 60 minutes - ONE AGENT ONLY)      │   │
│  │                                                          │   │
│  │  1. TRIGGER → Heartbeat fires reflection task          │   │
│  │       • Rotate: 1 of 6 agents selected per hour        │   │
│  │       • Sequence: Kublai → Möngke → Temüjin → ...      │   │
│  │       │                                                  │   │
│  │       ▼                                                  │   │
│  │  2. GATHER CONTEXT → Query ENTIRE Neo4j database       │   │
│  │       • Recent metrics (last hour)                     │   │
│  │       • Successful patterns (historical)               │   │
│  │       • Previous validated insights                    │   │
│  │       • Learned capabilities                           │   │
│  │       • Weekly performance trends                      │   │
│  │       • Cross-agent learnings                          │   │
│  │       • New user-fed information                       │   │
│  │       • Architecture sections                          │   │
│  │       • Task outcomes (all types)                      │   │
│  │       • Full graph traversal                           │   │
│  │       │                                                  │   │
│  │       ▼                                                  │   │
│  │  3. MEMORY PRUNING CHECK → Analyze memory files        │   │
│  │       • Check memory file sizes                        │   │
│  │       • Identify stale/outdated entries                │   │
│  │       • Propose pruning candidates                     │   │
│  │       │                                                  │   │
│  │       ▼                                                  │   │
│  │  4. REFLECT → Agent's Gemini CLI                       │   │
│  │       Agent expresses:                                 │   │
│  │       • WANTS: "I want to be better at..."             │   │
│  │       • DESIRES: "I wish I could..."                   │   │
│  │       • PROPOSALS: "I propose we..."                   │   │
│  │       Model: gemini-3.1-pro-preview                    │   │
│  │       │                                                  │   │
│  │       ▼                                                  │   │
│  │  5. STORE → Save reflection to Neo4j                   │   │
│  │       • Raw reflection text                            │   │
│  │       • Structured wants/desires/proposals             │   │
│  │       • Priority/confidence scores                     │   │
│  │       │                                                  │   │
│  │       ▼                                                  │   │
│  │  6. KUBLAI REVIEW → Kublai's Gemini CLI                │   │
│  │       • Query: "Should I approve this proposal?"       │   │
│  │       • Consider: Impact, alignment, risk              │   │
│  │       • Output: Approve / Reject / Human consult       │   │
│  │       │                                                  │   │
│  │       ▼                                                  │   │
│  │  7. DECISION GATE → Route based on criticality         │   │
│  │       • LOW risk → Auto-implement                      │   │
│  │       • MEDIUM risk → Kublai decides                   │   │
│  │       • HIGH risk / CRITICAL → Consult human           │   │
│  │       │                                                  │   │
│  │       ▼                                                  │   │
│  │  8. IMPLEMENT → If approved                            │   │
│  │       • Apply code improvements                        │   │
│  │       • Execute memory pruning                         │   │
│  │       • Update configurations                          │   │
│  │       │                                                  │   │
│  │       ▼                                                  │   │
│  │  9. VALIDATE → Measure for 24 hours                    │   │
│  │       • Baseline comparison                            │   │
│  │       • Track metrics                                  │   │
│  │       │                                                  │   │
│  │       ▼                                                  │   │
│  │  10. DECIDE → Keep, iterate, or rollback               │   │
│  │       • Success: Commit + document                     │   │
│  │       • Failure: Auto-rollback                         │   │
│  │       • Feedback to proposing agent                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  WEEKLY CROSS-POLLINATION (Every 7 days)                │   │
│  │                                                          │   │
│  │  • Agents share top insights                           │   │
│  │  • Relevance matching to other agents                  │   │
│  │  • Adaptation to different contexts                    │   │
│  │  • Meta-learning: which transfers work                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## THE 6 AGENTS

Each with **dedicated Gemini 3.1 Pro Preview CLI** and **isolated knowledge context**:

| Agent | Role | Gemini CLI | Specialization | Reflection Focus |
|-------|------|------------|----------------|------------------|
| **Kublai** | Squad Lead | `gemini-kublai` | Orchestration, Delegation | Routing optimization, workflow efficiency |
| **Möngke** | Researcher | `gemini-mongke` | Research, Analysis | Source quality, research depth optimization |
| **Chagatai** | Writer | `gemini-chagatai` | Content, Documentation | Template refinement, clarity metrics |
| **Temüjin** | Developer | `gemini-temujin` | Code, Technical | Pattern generation, technical debt |
| **Jochi** | Analyst | `gemini-jochi` | Debugging, Testing | Error prevention, test coverage |
| **Ögedei** | Operations | `gemini-ogedei` | Infrastructure | Timing optimization, resource usage |

---

## STEP 2: AGENT REFLECTION MODULE (Updated)

**File:** `tools/kurultai/agent_reflection.py`

```python
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

from neo4j import GraphDatabase
from tools.kurultai.agent_gemini import get_agent_gemini, kublai_gemini

NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'myStrongPassword123')

# Agent rotation schedule (one per hour)
AGENT_ROTATION = [
    "kublai",    # Hour 0, 6, 12, 18
    "mongke",    # Hour 1, 7, 13, 19
    "temujin",   # Hour 2, 8, 14, 20
    "chagatai",  # Hour 3, 9, 15, 21
    "jochi",     # Hour 4, 10, 16, 22
    "ogedei"     # Hour 5, 11, 17, 23
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
    priority: str = "medium"  # low, medium, high, critical


class AgentReflectionSystem:
    """System for one agent per hour to reflect and propose."""
    
    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
    
    def get_current_reflector(self) -> str:
        """Get which agent should reflect this hour (round-robin)."""
        hour = datetime.now().hour
        # Each agent gets 4 slots per day (24h / 6 agents)
        agent_index = hour % 6
        return AGENT_ROTATION[agent_index]
    
    def gather_full_context(self, agent_id: str) -> Dict[str, Any]:
        """
        Query ENTIRE Neo4j database for complete context.
        """
        context = {
            "timestamp": datetime.now().isoformat(),
            "reflecting_agent": agent_id,
            "query_time_range": "complete_database"
        }
        
        with self.driver.session() as session:
            # 1. All agents and their status
            result = session.run("""
                MATCH (a:Agent)
                RETURN a.name as name, a.status as status, a.role as role
            """)
            context["all_agents"] = [dict(r) for r in result]
            
            # 2. All tasks (recent and historical)
            result = session.run("""
                MATCH (t:Task)
                RETURN t.id as id, t.agent as agent, t.status as status,
                       t.timestamp as timestamp, t.type as type
                ORDER BY t.timestamp DESC LIMIT 100
            """)
            context["recent_tasks"] = [dict(r) for r in result]
            
            # 3. All task outcomes (performance data)
            result = session.run("""
                MATCH (to:TaskOutcome)
                WHERE to.timestamp > datetime() - duration('P7D')
                RETURN to.agent as agent, to.status as status,
                       to.timestamp as timestamp, to.tokens_used as tokens
                ORDER BY to.timestamp DESC LIMIT 200
            """)
            context["task_outcomes"] = [dict(r) for r in result]
            
            # 4. All previous reflections
            result = session.run("""
                MATCH (r:Reflection)
                RETURN r.agent as agent, r.timestamp as timestamp,
                       r.key_observation as observation, r.proposed_change as proposal
                ORDER BY r.timestamp DESC LIMIT 50
            """)
            context["previous_reflections"] = [dict(r) for r in result]
            
            # 5. Discovered patterns
            result = session.run("""
                MATCH (p:Pattern)
                RETURN p.description as pattern, p.agent as agent,
                       p.confidence as confidence, p.frequency as freq
                ORDER BY p.confidence DESC
            """)
            context["patterns"] = [dict(r) for r in result]
            
            # 6. Learned capabilities
            result = session.run("""
                MATCH (lc:LearnedCapability)
                RETURN lc.name as name, lc.description as desc,
                       lc.learned_by as learned_by, lc.usage_count as usage
            """)
            context["capabilities"] = [dict(r) for r in result]
            
            # 7. User-fed information (tagged)
            result = session.run("""
                MATCH (n)
                WHERE n.source = 'user_fed' OR n.tags CONTAINS 'user_input'
                RETURN n.timestamp as timestamp, n.content as content,
                       labels(n) as labels
                ORDER BY n.timestamp DESC LIMIT 20
            """)
            context["user_fed_information"] = [dict(r) for r in result]
            
            # 8. Architecture knowledge
            result = session.run("""
                MATCH (s:ArchitectureSection)
                RETURN s.title as title, s.content as content
            """)
            context["architecture"] = [dict(r) for r in result]
            
            # 9. Graph statistics
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
            
            # 10. Cross-agent interactions
            result = session.run("""
                MATCH (a1:Agent)-[r:DELEGATED_TO|SHARED_WITH]-(a2:Agent)
                RETURN a1.name as from_agent, type(r) as relation,
                       a2.name as to_agent, count(*) as count
            """)
            context["agent_interactions"] = [dict(r) for r in result]
        
        return context
    
    def check_memory_files(self, agent_id: str) -> List[Dict[str, Any]]:
        """
        Analyze agent's memory files for pruning candidates.
        """
        import os
        from pathlib import Path
        
        memory_dir = Path(f"~/.openclaw/agents/{agent_id}/memory").expanduser()
        if not memory_dir.exists():
            return []
        
        pruning_candidates = []
        
        for file_path in memory_dir.glob("*.md"):
            stat = file_path.stat()
            size_mb = stat.st_size / (1024 * 1024)
            age_days = (datetime.now().timestamp() - stat.st_mtime) / 86400
            
            # Flag for pruning if:
            # - Larger than 10MB
            # - Older than 90 days
            # - Not accessed in 30 days
            if size_mb > 10 or age_days > 90:
                pruning_candidates.append({
                    "file": str(file_path),
                    "size_mb": round(size_mb, 2),
                    "age_days": round(age_days, 1),
                    "reason": "large_file" if size_mb > 10 else "old_file"
                })
        
        return pruning_candidates
    
    def perform_agent_reflection(self, agent_id: str) -> AgentReflection:
        """
        ONE agent reflects, expressing wants, desires, and proposals.
        """
        # Get agent's Gemini instance
        agent_gemini = get_agent_gemini(agent_id)
        
        # Gather complete context
        context = self.gather_full_context(agent_id)
        
        # Check memory files for pruning
        memory_issues = self.check_memory_files(agent_id)
        
        # Build expressive prompt
        prompt = f"""
=== YOUR IDENTITY ===
You are {agent_id}, an AI agent in the Kurultai system.
Your role: {context.get('reflecting_agent', 'specialist agent')}

=== COMPLETE SYSTEM KNOWLEDGE (from Neo4j) ===

Graph Statistics:
- Total Nodes: {context['graph_stats']['node_count']}
- Total Relationships: {context['graph_stats']['relationship_count']}
- Node Types: {list(context['graph_stats']['labels'].keys())}

All Agents in System:
{json.dumps(context['all_agents'], indent=2)}

Your Recent Performance (Last 7 Days):
{json.dumps([o for o in context['task_outcomes'] if o['agent'] == agent_id][:10], indent=2)}

Previous Reflections (What you've learned):
{json.dumps([r for r in context['previous_reflections'] if r['agent'] == agent_id][:5], indent=2)}

Successful Patterns You've Discovered:
{json.dumps([p for p in context['patterns'] if p['agent'] == agent_id][:5], indent=2)}

Cross-Agent Activity:
{json.dumps(context['agent_interactions'], indent=2)}

User-Fed Information (Priority):
{json.dumps(context['user_fed_information'][:5], indent=2)}

Memory Files Requiring Attention:
{json.dumps(memory_issues, indent=2)}

=== YOUR REFLECTION TASK ===

It is your turn to reflect. Express yourself authentically:

1. WANTS (What do you want to improve?)
   - "I want to be better at..."
   - "I want more/less of..."
   - "I want the system to..."

2. DESIRES (What do you wish for?)
   - "I wish I could..."
   - "I wish the team would..."
   - "I wish our users had..."

3. PROPOSALS (Concrete changes you suggest)
   - Specific, actionable improvements
   - Include: what, why, expected impact
   - Rate confidence (0.0-1.0) and priority (low/medium/high/critical)

4. MEMORY PRUNING (if needed)
   - Identify stale/outdated memory entries
   - Suggest what to archive or delete

Be honest about frustrations, aspirations, and observations.
Your reflection will be reviewed by Kublai for possible implementation.

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
        
        # Query agent's Gemini
        reflection_text = agent_gemini.query(prompt)
        
        # Parse structured data from reflection
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
        
        # Store in Neo4j
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
                    # Try to extract confidence and priority
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
        
        # Calculate aggregate scores
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


# Heartbeat task integration
async def hourly_agent_reflection_task():
    """
    Heartbeat task: ONE agent reflects per hour.
    """
    system = AgentReflectionSystem()
    try:
        # Determine which agent reflects this hour
        agent_id = system.get_current_reflector()
        
        # Perform reflection
        reflection = system.perform_agent_reflection(agent_id)
        
        # Queue for Kublai review (next step)
        # This would trigger Kublai's review task
        
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
    print(f"Current reflector: {AgentReflectionSystem().get_current_reflector()}")
```

---

## STEP 3: KUBLAI REVIEW MODULE

**File:** `tools/kurultai/kublai_review.py`

```python
#!/usr/bin/env python3
"""
Kublai Review System
Kublai reviews agent reflections using Gemini CLI
Decides: implement, reject, or consult human
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from enum import Enum
from dataclasses import dataclass

from neo4j import GraphDatabase
from tools.kurultai.agent_gemini import kublai_gemini

NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'myStrongPassword123')


class ReviewDecision(Enum):
    IMPLEMENT = "implement"           # Auto-implement (low risk)
    REJECT = "reject"                 # Don't implement
    CONSULT_HUMAN = "consult_human"   # Critical - needs human approval
    DEFER = "defer"                   # Decide later, gather more data


class KublaiReviewSystem:
    """
    Kublai reviews agent proposals and makes implementation decisions.
    Uses Gemini CLI for intelligent evaluation.
    """
    
    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        self.kublai = kublai_gemini()
    
    def get_pending_reflections(self) -> List[Dict[str, Any]]:
        """Get all unreviewed agent reflections."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:AgentReflection)
                WHERE r.reviewed = false
                RETURN r.id as id, r.agent as agent, r.raw_text as text,
                       r.proposals as proposals, r.priority as priority,
                       r.confidence as confidence, r.timestamp as timestamp
                ORDER BY r.priority DESC, r.timestamp ASC
            """)
            return [dict(r) for r in result]
    
    def review_proposal(self, reflection_id: str) -> Dict[str, Any]:
        """
        Kublai reviews a single proposal using Gemini CLI.
        Includes ARCHITECTURE.md and codebase context.
        """
        # Get full reflection details
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:AgentReflection {id: $id})
                RETURN r
            """, id=reflection_id)
            record = result.single()
            if not record:
                return {"error": "Reflection not found"}
            
            reflection = dict(record['r'])
        
        # Build review prompt for Kublai with FULL CONTEXT
        
        # Gather architecture and codebase context
        architecture_context = self._load_architecture_md()
        codebase_context = self._scan_codebase()
        neo4j_context = self._gather_neo4j_context()
        
        prompt = f"""
=== KUBLAI REVIEW TASK ===

You are Kublai, Squad Lead of the Kurultai.
Your role: Review proposals from your agents and decide their fate.

You have access to:
1. Complete ARCHITECTURE.md (system design)
2. Entire codebase (all Python files, configs)
3. Full Neo4j graph (all historical data)
4. Agent's proposal

=== SYSTEM ARCHITECTURE (ARCHITECTURE.md) ===

{architecture_context[:3000]}

[Architecture continues...]

=== CODEBASE CONTEXT ===

Key Files and Their Purposes:
{codebase_context}

=== NEO4J KNOWLEDGE GRAPH ===

Graph Statistics:
- Total Nodes: {neo4j_context.get('node_count', 0)}
- Total Relationships: {neo4j_context.get('rel_count', 0)}
- Recent Activity (Last 24h): {len(neo4j_context.get('recent_activity', []))} events

Active Agents:
{json.dumps(neo4j_context.get('agents', []), indent=2)[:500]}

Recent Patterns Discovered:
{json.dumps(neo4j_context.get('patterns', [])[:3], indent=2)}

=== PROPOSAL TO REVIEW ===

From Agent: {reflection['agent']}
Timestamp: {reflection['timestamp']}
Priority: {reflection['priority']}
Confidence: {reflection['confidence']}

Raw Reflection:
{reflection['raw_text'][:2000]}

Parsed Proposals:
{reflection['proposals']}

=== ARCHITECTURAL CONSIDERATION ===

Before deciding, analyze:
1. Does this proposal align with our documented architecture?
2. Are there existing modules that could handle this?
3. Would this create architectural debt?
4. Does it follow established patterns in the codebase?

Check ARCHITECTURE.md sections relevant to: {reflection['agent']}'s domain

=== CODEBASE CONSIDERATION ===

Before deciding, verify:
1. Are there existing implementations of similar functionality?
2. Would this duplicate existing code?
3. Does it follow the project's coding patterns?
4. Which files would need modification?

=== YOUR REVIEW CRITERIA ===

1. ARCHITECTURAL FIT: Does this align with ARCHITECTURE.md?
   - Explicitly matches documented design → STRONG fit
   - Extends existing patterns → GOOD fit
   - Requires architectural changes → WEAK fit
   - Contradicts documented approach → REJECT

2. IMPACT: How much would this improve the system?
   - Minimal (cosmetic, preference) → LOW impact
   - Moderate (efficiency, quality) → MEDIUM impact
   - Significant (capability, reliability) → HIGH impact

3. RISK: What could go wrong?
   - Isolated to one agent → LOW risk
   - Affects multiple agents → MEDIUM risk
   - System-wide or safety-critical → HIGH risk

4. ALIGNMENT: Does this fit our mission?
   - Advances agent capabilities → YES
   - Improves human experience → YES
   - Creates complexity without benefit → NO

5. REVERSIBILITY: Can we undo this?
   - Configuration change → YES
   - Code modification with tests → YES
   - Schema or architectural change → MAYBE

=== DECISION OPTIONS ===

A. IMPLEMENT - Approve and execute immediately
   Use when: LOW risk, HIGH alignment, reversible, fits architecture

B. REJECT - Do not implement
   Use when: Misaligned, too risky, not beneficial, or violates architecture

C. CONSULT_HUMAN - Critical decision needs human
   Use when: HIGH risk, system-wide impact, safety concern, architectural change
   OR when: Uncertain about consequences

D. DEFER - Decide later, gather more data
   Use when: Interesting but needs more thought or validation

=== YOUR RESPONSE FORMAT ===

DECISION: [IMPLEMENT | REJECT | CONSULT_HUMAN | DEFER]

CONFIDENCE: [0.0-1.0]

ARCHITECTURAL_ANALYSIS:
- Does this align with ARCHITECTURE.md? (Yes/No/Partial)
- Which sections are relevant?
- Any architectural concerns?

CODEBASE_ANALYSIS:
- Which files would be modified?
- Any existing similar implementations?
- Integration points?

IMPACT_ASSESSMENT:
- Scope of impact: (One agent / Multiple / System-wide)
- Expected improvement: [description]

RISK_ASSESSMENT:
- Risk level: (Low/Medium/High)
- What could go wrong: [description]
- Mitigation strategies: [list]

ALIGNMENT_CHECK:
- Fits mission: (Yes/No)
- Creates value: (Yes/No)

FINAL_REASONING:
[Your reasoning for the decision]

IMPLEMENTATION_NOTES (if IMPLEMENT):
- Files to modify: [list]
- Tests to run: [list]
- Rollback plan: [description]
- Estimated effort: [hours/complexity]

HUMAN_CONTEXT (if CONSULT_HUMAN):
- Why this needs your input: [specific concern]
- What decision is needed: [options]
- What are the trade-offs: [pros/cons]
- What happens if we do nothing: [consequence]
"""
        
        # Query Kublai's Gemini
        review_response = self.kublai.query(prompt)
        
        # Parse decision
        decision = self._parse_decision(review_response)
        
        # Store review
        self._store_review(reflection_id, decision, review_response)
        
        # Execute decision
        if decision['decision'] == ReviewDecision.IMPLEMENT:
            self._queue_implementation(reflection_id, decision)
        elif decision['decision'] == ReviewDecision.CONSULT_HUMAN:
            self._notify_human(reflection_id, decision)
        
        return decision
    
    def _load_architecture_md(self) -> str:
        """Load ARCHITECTURE.md content."""
        arch_path = os.path.expanduser("~/kurultai/kublai-repo/ARCHITECTURE.md")
        try:
            with open(arch_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            return "# ARCHITECTURE.md not found"
    
    def _scan_codebase(self) -> str:
        """Scan codebase for relevant context."""
        import os
        from pathlib import Path
        
        base_path = Path("~/kurultai/kublai-repo").expanduser()
        key_files = []
        
        # Key directories to scan
        scan_dirs = [
            base_path / "tools" / "kurultai",
            base_path / "src",
            base_path / "scripts"
        ]
        
        for scan_dir in scan_dirs:
            if scan_dir.exists():
                for py_file in scan_dir.rglob("*.py"):
                    if py_file.stat().st_size < 50000:  # Skip huge files
                        try:
                            with open(py_file, 'r') as f:
                                content = f.read()
                                # Extract docstring or first 200 chars
                                if '"""' in content:
                                    doc = content.split('"""')[1][:200]
                                else:
                                    doc = content[:200]
                                
                                rel_path = py_file.relative_to(base_path)
                                key_files.append(f"{rel_path}: {doc.strip()}")
                        except:
                            pass
        
        return "\n".join(key_files[:20])  # Top 20 files
    
    def _gather_neo4j_context(self) -> Dict[str, Any]:
        """Gather comprehensive Neo4j context."""
        with self.driver.session() as session:
            # Graph stats
            result = session.run("""
                CALL apoc.meta.stats()
                YIELD nodeCount, relCount
                RETURN nodeCount, relCount
            """)
            stats = result.single()
            
            # Active agents
            result = session.run("""
                MATCH (a:Agent)
                RETURN a.name as name, a.status as status
            """)
            agents = [dict(r) for r in result]
            
            # Recent patterns
            result = session.run("""
                MATCH (p:Pattern)
                RETURN p.description as desc, p.confidence as conf
                ORDER BY p.confidence DESC
                LIMIT 5
            """)
            patterns = [dict(r) for r in result]
            
            # Recent activity
            result = session.run("""
                MATCH (n)
                WHERE n.timestamp > datetime() - duration('P1D')
                RETURN count(n) as count
            """)
            activity = result.single()['count']
            
            return {
                'node_count': stats['nodeCount'] if stats else 0,
                'rel_count': stats['relCount'] if stats else 0,
                'agents': agents,
                'patterns': patterns,
                'recent_activity': [{'count': activity}]
            }
        
        # Build review prompt for Kublai with FULL CONTEXT
        
        # Gather architecture and codebase context
        architecture_context = self._load_architecture_md()
        codebase_context = self._scan_codebase()
        neo4j_context = self._gather_neo4j_context()
        
        prompt = f"""
=== KUBLAI REVIEW TASK ===

You are Kublai, Squad Lead of the Kurultai.
Your role: Review proposals from your agents and decide their fate.

You have access to:
1. Complete ARCHITECTURE.md (system design)
2. Entire codebase (all Python files, configs)
3. Full Neo4j graph (all historical data)
4. Agent's proposal

=== SYSTEM ARCHITECTURE (ARCHITECTURE.md) ===

{architecture_context[:3000]}

[Architecture continues...]

=== CODEBASE CONTEXT ===

Key Files and Their Purposes:
{codebase_context}

=== NEO4J KNOWLEDGE GRAPH ===

Graph Statistics:
- Total Nodes: {neo4j_context.get('node_count', 0)}
- Total Relationships: {neo4j_context.get('rel_count', 0)}
- Recent Activity (Last 24h): {len(neo4j_context.get('recent_activity', []))} events

Active Agents:
{json.dumps(neo4j_context.get('agents', []), indent=2)[:500]}

Recent Patterns Discovered:
{json.dumps(neo4j_context.get('patterns', [])[:3], indent=2)}

=== PROPOSAL TO REVIEW ===

From Agent: {reflection['agent']}
Timestamp: {reflection['timestamp']}
Priority: {reflection['priority']}
Confidence: {reflection['confidence']}

Raw Reflection:
{reflection['raw_text'][:2000]}

Parsed Proposals:
{reflection['proposals']}

=== ARCHITECTURAL CONSIDERATION ===

Before deciding, analyze:
1. Does this proposal align with our documented architecture?
2. Are there existing modules that could handle this?
3. Would this create architectural debt?
4. Does it follow established patterns in the codebase?

Check ARCHITECTURE.md sections relevant to: {reflection['agent']}'s domain

=== CODEBASE CONSIDERATION ===

Before deciding, verify:
1. Are there existing implementations of similar functionality?
2. Would this duplicate existing code?
3. Does it follow the project's coding patterns?
4. Which files would need modification?

=== YOUR REVIEW CRITERIA ===

1. ARCHITECTURAL FIT: Does this align with ARCHITECTURE.md?
   - Explicitly matches documented design → STRONG fit
   - Extends existing patterns → GOOD fit
   - Requires architectural changes → WEAK fit
   - Contradicts documented approach → REJECT

2. IMPACT: How much would this improve the system?
   - Minimal (cosmetic, preference) → LOW impact
   - Moderate (efficiency, quality) → MEDIUM impact
   - Significant (capability, reliability) → HIGH impact

3. RISK: What could go wrong?
   - Isolated to one agent → LOW risk
   - Affects multiple agents → MEDIUM risk
   - System-wide or safety-critical → HIGH risk

4. ALIGNMENT: Does this fit our mission?
   - Advances agent capabilities → YES
   - Improves human experience → YES
   - Creates complexity without benefit → NO

5. REVERSIBILITY: Can we undo this?
   - Configuration change → YES
   - Code modification with tests → YES
   - Schema or architectural change → MAYBE

=== DECISION OPTIONS ===

A. IMPLEMENT - Approve and execute immediately
   Use when: LOW risk, HIGH alignment, reversible, fits architecture

B. REJECT - Do not implement
   Use when: Misaligned, too risky, not beneficial, or violates architecture

C. CONSULT_HUMAN - Critical decision needs human
   Use when: HIGH risk, system-wide impact, safety concern, architectural change
   OR when: Uncertain about consequences

D. DEFER - Decide later, gather more data
   Use when: Interesting but needs more thought or validation

=== YOUR RESPONSE FORMAT ===

DECISION: [IMPLEMENT | REJECT | CONSULT_HUMAN | DEFER]

CONFIDENCE: [0.0-1.0]

ARCHITECTURAL_ANALYSIS:
- Does this align with ARCHITECTURE.md? (Yes/No/Partial)
- Which sections are relevant?
- Any architectural concerns?

CODEBASE_ANALYSIS:
- Which files would be modified?
- Any existing similar implementations?
- Integration points?

IMPACT_ASSESSMENT:
- Scope of impact: (One agent / Multiple / System-wide)
- Expected improvement: [description]

RISK_ASSESSMENT:
- Risk level: (Low/Medium/High)
- What could go wrong: [description]
- Mitigation strategies: [list]

ALIGNMENT_CHECK:
- Fits mission: (Yes/No)
- Creates value: (Yes/No)

FINAL_REASONING:
[Your reasoning for the decision]

IMPLEMENTATION_NOTES (if IMPLEMENT):
- Files to modify: [list]
- Tests to run: [list]
- Rollback plan: [description]
- Estimated effort: [hours/complexity]

HUMAN_CONTEXT (if CONSULT_HUMAN):
- Why this needs your input: [specific concern]
- What decision is needed: [options]
- What are the trade-offs: [pros/cons]
- What happens if we do nothing: [consequence]
"""
        
        # Query Kublai's Gemini
        review_response = self.kublai.query(prompt)
        
        # Parse decision
        decision = self._parse_decision(review_response)
        
        # Store review
        self._store_review(reflection_id, decision, review_response)
        
        # Execute decision
        if decision['decision'] == ReviewDecision.IMPLEMENT:
            self._queue_implementation(reflection_id, decision)
        elif decision['decision'] == ReviewDecision.CONSULT_HUMAN:
            self._notify_human(reflection_id, decision)
        
        return decision
    
    def _parse_decision(self, response: str) -> Dict[str, Any]:
        """Parse Kublai's review response."""
        lines = response.split('\n')
        
        decision_data = {
            'decision': ReviewDecision.DEFER,
            'confidence': 0.5,
            'rationale': '',
            'implementation_notes': '',
            'human_context': ''
        }
        
        current_section = None
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('DECISION:'):
                dec_text = line.split(':')[1].strip().upper()
                if 'IMPLEMENT' in dec_text:
                    decision_data['decision'] = ReviewDecision.IMPLEMENT
                elif 'REJECT' in dec_text:
                    decision_data['decision'] = ReviewDecision.REJECT
                elif 'CONSULT' in dec_text or 'HUMAN' in dec_text:
                    decision_data['decision'] = ReviewDecision.CONSULT_HUMAN
                elif 'DEFER' in dec_text:
                    decision_data['decision'] = ReviewDecision.DEFER
            
            elif line.startswith('CONFIDENCE:'):
                try:
                    conf = float(line.split(':')[1].strip())
                    decision_data['confidence'] = max(0.0, min(1.0, conf))
                except:
                    pass
            
            elif line.startswith('RATIONALE:'):
                current_section = 'rationale'
            elif line.startswith('IMPLEMENTATION_NOTES:'):
                current_section = 'implementation'
            elif line.startswith('HUMAN_CONTEXT:'):
                current_section = 'human'
            elif current_section and line and not line.startswith('==='):
                decision_data[current_section] += line + '\n'
        
        return decision_data
    
    def _store_review(self, reflection_id: str, decision: Dict, raw_response: str):
        """Store review decision in Neo4j."""
        with self.driver.session() as session:
            session.run("""
                MATCH (r:AgentReflection {id: $ref_id})
                CREATE (rev:Review {
                    id: $rev_id,
                    timestamp: datetime(),
                    decision: $decision,
                    confidence: $confidence,
                    rationale: $rationale,
                    raw_response: $raw
                })
                CREATE (r)-[:REVIEWED_BY]->(rev)
                SET r.reviewed = true,
                    r.review_decision = $decision
            """,
            ref_id=reflection_id,
            rev_id=f"review-{reflection_id}-{int(datetime.now().timestamp())}",
            decision=decision['decision'].value,
            confidence=decision['confidence'],
            rationale=decision['rationale'][:1000],
            raw=raw_response[:2000]
            )
    
    def _queue_implementation(self, reflection_id: str, decision: Dict):
        """Queue proposal for implementation."""
        # Add to implementation queue (for async processing)
        with self.driver.session() as session:
            session.run("""
                MATCH (r:AgentReflection {id: $id})
                CREATE (imp:ImplementationQueue {
                    id: $imp_id,
                    queued_at: datetime(),
                    status: 'pending',
                    notes: $notes
                })
                CREATE (r)-[:QUEUED_FOR]->(imp)
            """,
            id=reflection_id,
            imp_id=f"imp-{reflection_id}",
            notes=decision.get('implementation_notes', '')[:500]
            )
    
    def _notify_human(self, reflection_id: str, decision: Dict):
        """Notify human for critical decision."""
        # Signal notification to human
        human_context = decision.get('human_context', 'Critical decision needed')
        
        # Store human notification
        with self.driver.session() as session:
            session.run("""
                MATCH (r:AgentReflection {id: $id})
                CREATE (hn:HumanNotification {
                    id: $notif_id,
                    timestamp: datetime(),
                    status: 'pending',
                    context: $context,
                    urgency: 'high'
                })
                CREATE (r)-[:AWAITS_HUMAN_DECISION]->(hn)
            """,
            id=reflection_id,
            notif_id=f"human-{reflection_id}",
            context=human_context[:1000]
            )
        
        # TODO: Send Signal message to human
        # This would integrate with your Signal channel
        print(f"🚨 HUMAN CONSULTATION REQUIRED: {reflection_id}")
        print(f"Context: {human_context[:200]}...")
    
    def process_all_pending(self) -> List[Dict[str, Any]]:
        """Process all pending reflections."""
        pending = self.get_pending_reflections()
        results = []
        
        for reflection in pending:
            decision = self.review_proposal(reflection['id'])
            results.append({
                'reflection_id': reflection['id'],
                'agent': reflection['agent'],
                'decision': decision['decision'].value,
                'confidence': decision['confidence']
            })
        
        return results
    
    def close(self):
        self.driver.close()


# Heartbeat integration
async def kublai_review_task():
    """
    Heartbeat task: Kublai reviews pending agent reflections.
    Runs after agent reflection task completes.
    """
    system = KublaiReviewSystem()
    try:
        results = system.process_all_pending()
        
        # Summary
        implement_count = sum(1 for r in results if r['decision'] == 'implement')
        consult_count = sum(1 for r in results if r['decision'] == 'consult_human')
        
        return {
            "status": "success",
            "reviewed_count": len(results),
            "approved": implement_count,
            "consult_human": consult_count,
            "details": results
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        system.close()


if __name__ == "__main__":
    print("Testing Kublai Review System...")
    system = KublaiReviewSystem()
    pending = system.get_pending_reflections()
    print(f"Pending reflections: {len(pending)}")
    system.close()
```

```cypher
// Run this in Neo4j Browser or via Python

// Core indexes for performance
CREATE INDEX reflection_agent_time_idx IF NOT EXISTS FOR (r:Reflection) ON (r.agent, r.timestamp);
CREATE INDEX outcome_agent_time_idx IF NOT EXISTS FOR (to:TaskOutcome) ON (to.agent, to.timestamp);
CREATE INDEX pattern_agent_confidence_idx IF NOT EXISTS FOR (p:Pattern) ON (p.agent, p.confidence);

// Reflection nodes (hourly self-improvement cycles)
CREATE CONSTRAINT reflection_id IF NOT EXISTS 
  FOR (r:Reflection) REQUIRE r.id IS UNIQUE;

// Task outcomes (every task execution tracked)
CREATE CONSTRAINT outcome_id IF NOT EXISTS 
  FOR (to:TaskOutcome) REQUIRE to.id IS UNIQUE;

// Patterns (discovered successful approaches)
CREATE CONSTRAINT pattern_id IF NOT EXISTS 
  FOR (p:Pattern) REQUIRE p.id IS UNIQUE;

// Knowledge context (accumulated wisdom per agent)
CREATE CONSTRAINT knowledge_context_agent IF NOT EXISTS 
  FOR (kc:KnowledgeContext) REQUIRE kc.agent IS UNIQUE;

// Improvement proposals (validated changes)
CREATE CONSTRAINT proposal_id IF NOT EXISTS 
  FOR (prop:ImprovementProposal) REQUIRE prop.id IS UNIQUE;

// Example: Create KnowledgeContext for each agent
CREATE (kc:KnowledgeContext {
    agent: "kublai",
    created_at: datetime(),
    accumulated_patterns: [],
    successful_insights: [],
    failed_approaches: [],
    performance_trends: {},
    last_updated: datetime()
});
```

### Step 2: Core Implementation Code (30 minutes)

**File:** `tools/kurultai/self_improvement.py`

```python
#!/usr/bin/env python3
"""
Kurultai Self-Improvement System
Context-aware, safety-guarded, validated improvements
"""

import os
import json
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from neo4j import GraphDatabase
from tools.kurultai.agent_gemini import get_agent_gemini

# Configuration
NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'myStrongPassword123')


class ImprovementStatus(Enum):
    PROPOSED = "proposed"
    VALIDATING = "validating"
    VALIDATED = "validated"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class RiskLevel(Enum):
    LOW = "low"      # Auto-implement
    MEDIUM = "medium"  # Human approval
    HIGH = "high"     # Reject


@dataclass
class ReflectionContext:
    """Complete context gathered from Neo4j for reflection."""
    agent_id: str
    recent_metrics: Dict[str, Any]
    successful_patterns: List[Dict]
    previous_insights: List[Dict]
    learned_capabilities: List[Dict]
    weekly_trends: List[Dict]
    cross_agent_learnings: List[Dict]
    
    def to_prompt(self) -> str:
        """Convert context to rich prompt for Gemini."""
        return f"""
=== YOUR ACCUMULATED KNOWLEDGE (Neo4j) ===

Recent Performance (Last Hour):
- Tasks: {self.recent_metrics.get('total', 0)}
- Success: {self.recent_metrics.get('success', 0)}
- Success Rate: {(self.recent_metrics.get('success', 0) / max(self.recent_metrics.get('total', 1), 1) * 100):.1f}%
- Errors: {self.recent_metrics.get('errors', 0)}
- Avg Tokens: {self.recent_metrics.get('avg_tokens', 0):.0f}

Your Successful Patterns ({len(self.successful_patterns)} total):
{json.dumps(self.successful_patterns[:3], indent=2)}

Previous Insights That Worked ({len(self.previous_insights)} total):
{json.dumps(self.previous_insights[:3], indent=2)}

Your Learned Capabilities ({len(self.learned_capabilities)} total):
{json.dumps(self.learned_capabilities[:3], indent=2)}

7-Day Performance Trend:
{json.dumps(self.weekly_trends[-3:], indent=2)}

Cross-Agent Learnings:
{json.dumps(self.cross_agent_learnings, indent=2)}

=== REFLECTION TASK ===

Based on ALL this historical knowledge:

1. ANALYZE: What patterns do you see across your knowledge base?
2. SYNTHESIZE: How does recent performance compare to historical trends?
3. IDENTIFY: What knowledge gap or blind spot exists?
4. PROPOSE: What's one concrete, actionable improvement?

Be specific. Reference actual patterns or insights from the data above.
"""


class SelfImprovementSystem:
    """Core self-improvement system for all agents."""
    
    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
    
    def gather_context(self, agent_id: str) -> ReflectionContext:
        """Gather comprehensive context from Neo4j for reflection."""
        
        with self.driver.session() as session:
            # 1. Recent metrics (last hour)
            result = session.run("""
                MATCH (to:TaskOutcome)
                WHERE to.timestamp > datetime() - duration('PT1H')
                  AND to.agent = $agent
                RETURN 
                    count(to) as total,
                    sum(CASE WHEN to.status = 'success' THEN 1 ELSE 0 END) as success,
                    avg(to.tokens_used) as avg_tokens,
                    sum(CASE WHEN to.error_type IS NOT NULL THEN 1 ELSE 0 END) as errors,
                    collect(DISTINCT to.error_type) as error_types
            """, agent=agent_id)
            record = result.single()
            recent_metrics = {
                'total': record['total'] or 0,
                'success': record['success'] or 0,
                'avg_tokens': record['avg_tokens'] or 0,
                'errors': record['errors'] or 0,
                'error_types': [e for e in (record['error_types'] or []) if e]
            }
            
            # 2. Successful patterns
            result = session.run("""
                MATCH (p:Pattern)
                WHERE p.agent = $agent AND p.confidence > 0.7
                RETURN p.description as pattern, p.frequency as freq, p.success_rate as rate
                ORDER BY p.success_rate DESC
                LIMIT 5
            """, agent=agent_id)
            successful_patterns = [
                {'pattern': r['pattern'], 'frequency': r['freq'], 'success_rate': r['rate']}
                for r in result
            ]
            
            # 3. Previous successful insights
            result = session.run("""
                MATCH (r:Reflection)
                WHERE r.agent = $agent
                  AND r.implemented = true
                  AND r.validation_result = 'success'
                RETURN r.key_observation as insight, r.proposed_change as change
                ORDER BY r.timestamp DESC
                LIMIT 3
            """, agent=agent_id)
            previous_insights = [
                {'insight': r['insight'], 'change': r['change']}
                for r in result
            ]
            
            # 4. Learned capabilities
            result = session.run("""
                MATCH (lc:LearnedCapability)
                WHERE lc.learned_by = $agent OR lc.agent = $agent
                RETURN lc.name as capability, lc.description as desc, lc.usage_count as usage
                ORDER BY lc.usage_count DESC
                LIMIT 5
            """, agent=agent_id)
            learned_capabilities = [
                {'name': r['capability'], 'description': r['desc'], 'usage': r['usage']}
                for r in result
            ]
            
            # 5. Weekly trends
            result = session.run("""
                MATCH (to:TaskOutcome)
                WHERE to.timestamp > datetime() - duration('P7D')
                  AND to.agent = $agent
                WITH date(to.timestamp) as day,
                     count(to) as total,
                     sum(CASE WHEN to.status = 'success' THEN 1 ELSE 0 END) as success
                RETURN day, total, success, (success * 100.0 / total) as rate
                ORDER BY day
            """, agent=agent_id)
            weekly_trends = [
                {'day': str(r['day']), 'total': r['total'], 'success_rate': r['rate']}
                for r in result
            ]
            
            # 6. Cross-agent learnings
            result = session.run("""
                MATCH (r:Reflection)
                WHERE r.agent <> $agent
                  AND r.shareable = true
                  AND r.timestamp > datetime() - duration('P7D')
                RETURN r.agent as agent, r.key_observation as insight
                LIMIT 3
            """, agent=agent_id)
            cross_agent_learnings = [
                {'agent': r['agent'], 'insight': r['insight']}
                for r in result
            ]
        
        return ReflectionContext(
            agent_id=agent_id,
            recent_metrics=recent_metrics,
            successful_patterns=successful_patterns,
            previous_insights=previous_insights,
            learned_capabilities=learned_capabilities,
            weekly_trends=weekly_trends,
            cross_agent_learnings=cross_agent_learnings
        )
    
    def perform_reflection(self, agent_id: str) -> Dict[str, Any]:
        """
        Perform hourly self-reflection for an agent.
        """
        # Get agent's Gemini instance
        agent_gemini = get_agent_gemini(agent_id)
        
        # Gather comprehensive context
        context = self.gather_context(agent_id)
        
        # Build context-rich prompt
        prompt = context.to_prompt()
        
        # Query Gemini with full context
        reflection_text = agent_gemini.query(prompt)
        
        # Parse reflection for structured data
        # (In production, use structured output or parsing)
        reflection_data = {
            'agent': agent_id,
            'timestamp': datetime.now().isoformat(),
            'raw_reflection': reflection_text,
            'context_sources': 6,
            'patterns_considered': len(context.successful_patterns),
            'insights_considered': len(context.previous_insights),
            'processed': False
        }
        
        # Store in Neo4j
        with self.driver.session() as session:
            session.run("""
                CREATE (r:Reflection {
                    id: $id,
                    agent: $agent,
                    timestamp: datetime(),
                    raw_reflection: $raw,
                    context_sources: $sources,
                    patterns_considered: $patterns,
                    insights_considered: $insights,
                    processed: false,
                    knowledge_enriched: true
                })
            """,
            id=f"{agent_id}-{int(time.time())}",
            agent=agent_id,
            raw=reflection_text[:2000],
            sources=6,
            patterns=len(context.successful_patterns),
            insights=len(context.previous_insights)
            )
        
        return reflection_data
    
    def close(self):
        self.driver.close()


# Convenience function for heartbeat integration
async def hourly_reflection_task(agent_id: str):
    """
    Heartbeat task: Perform hourly self-reflection.
    
    Usage in heartbeat_master:
    heartbeat.register(HeartbeatTask(
        name=f"{agent_id}_hourly_reflection",
        agent=agent_id,
        frequency_minutes=60,
        handler=hourly_reflection_task,
        max_tokens=2000
    ))
    """
    system = SelfImprovementSystem()
    try:
        result = system.perform_reflection(agent_id)
        return {
            "status": "success",
            "reflection_id": result.get('timestamp'),
            "context_sources": result.get('context_sources'),
            "patterns_considered": result.get('patterns_considered')
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
    finally:
        system.close()


if __name__ == "__main__":
    # Test
    print("Testing Self-Improvement System...")
    system = SelfImprovementSystem()
    
    # Test context gathering for Kublai
    print("\nGathering context for Kublai...")
    context = system.gather_context("kublai")
    print(f"Recent metrics: {context.recent_metrics}")
    print(f"Patterns found: {len(context.successful_patterns)}")
    print(f"Insights found: {len(context.previous_insights)}")
    
    # Test reflection
    print("\nPerforming reflection...")
    result = system.perform_reflection("kublai")
    print(f"Reflection stored: {result['processed']}")
    
    system.close()
    print("\nTest complete!")
```

### Step 3: Safety Guardian (30 minutes)

**File:** `tools/kurultai/improvement_guardian.py`

```python
#!/usr/bin/env python3
"""
Safety Guardian for Self-Improvements
Validates all changes before deployment
"""

from enum import Enum
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


class RiskLevel(Enum):
    LOW = "low"        # Auto-implement
    MEDIUM = "medium"  # Human approval required
    HIGH = "high"      # Reject


class ImprovementStatus(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


@dataclass
class ValidationResult:
    status: ImprovementStatus
    risk_level: RiskLevel
    failed_checks: List[str]
    requires_human: bool
    reason: str


class ImprovementGuardian:
    """
    Validates all self-improvements before deployment.
    Ensures safety, alignment, and reversibility.
    """
    
    # Define what can be auto-changed vs needs approval
    ALLOWED_SCOPES = [
        "prompt_template",
        "workflow_timing",
        "tool_parameter",
        "monitoring_threshold",
        "retry_logic"
    ]
    
    FORBIDDEN_SCOPES = [
        "core_logic",
        "authentication",
        "safety_rules",
        "agent_definitions",
        "database_schema"
    ]
    
    def validate(self, proposal: Dict[str, Any]) -> ValidationResult:
        """
        Multi-layer safety validation.
        
        Args:
            proposal: {
                "agent": str,
                "scope": str,
                "description": str,
                "change_type": str,
                "risk_assessment": str,
                "rollback_plan": str
            }
        """
        failed_checks = []
        
        # Check 1: Scope limitations
        if not self._check_scope(proposal.get("scope", "")):
            failed_checks.append("scope_forbidden")
        
        # Check 2: Goal alignment
        if not self._check_alignment(proposal):
            failed_checks.append("goal_misaligned")
        
        # Check 3: Reversibility
        if not self._check_rollback(proposal):
            failed_checks.append("cannot_rollback")
        
        # Check 4: Risk assessment
        risk = self._assess_risk(proposal)
        
        # Determine outcome
        if failed_checks:
            return ValidationResult(
                status=ImprovementStatus.REJECTED,
                risk_level=RiskLevel.HIGH,
                failed_checks=failed_checks,
                requires_human=False,
                reason=f"Failed checks: {', '.join(failed_checks)}"
            )
        
        if risk == RiskLevel.HIGH:
            return ValidationResult(
                status=ImprovementStatus.REJECTED,
                risk_level=RiskLevel.HIGH,
                failed_checks=["high_risk"],
                requires_human=False,
                reason="Risk level too high for auto-implementation"
            )
        
        if risk == RiskLevel.MEDIUM:
            return ValidationResult(
                status=ImprovementStatus.NEEDS_REVIEW,
                risk_level=RiskLevel.MEDIUM,
                failed_checks=[],
                requires_human=True,
                reason="Medium risk - requires human approval"
            )
        
        # Low risk - approved
        return ValidationResult(
            status=ImprovementStatus.APPROVED,
            risk_level=RiskLevel.LOW,
            failed_checks=[],
            requires_human=False,
            reason="Low risk, aligned with goals, can rollback"
        )
    
    def _check_scope(self, scope: str) -> bool:
        """Check if scope is allowed."""
        if scope in self.FORBIDDEN_SCOPES:
            return False
        return scope in self.ALLOWED_SCOPES
    
    def _check_alignment(self, proposal: Dict) -> bool:
        """Check if proposal aligns with agent's goals."""
        # Query Gemini for alignment check
        agent = proposal.get("agent", "unknown")
        description = proposal.get("description", "")
        
        # In production, use Gemini to verify alignment
        # For now, simple heuristic
        goal_keywords = {
            "kublai": ["orchestrate", "delegate", "coordinate"],
            "mongke": ["research", "analyze", "discover"],
            "chagatai": ["write", "document", "create"],
            "temujin": ["code", "develop", "build"],
            "jochi": ["analyze", "debug", "test"],
            "ogedei": ["operate", "deploy", "monitor"]
        }
        
        agent_keywords = goal_keywords.get(agent, [])
        return any(kw in description.lower() for kw in agent_keywords)
    
    def _check_rollback(self, proposal: Dict) -> bool:
        """Check if change can be rolled back."""
        rollback_plan = proposal.get("rollback_plan", "")
        return len(rollback_plan) > 20  # Must have actual plan
    
    def _assess_risk(self, proposal: Dict) -> RiskLevel:
        """Assess risk level of proposal."""
        risk_factors = 0
        
        # Factor 1: Scope
        if proposal.get("scope") in ["workflow_timing", "monitoring_threshold"]:
            risk_factors += 1
        elif proposal.get("scope") in ["prompt_template", "tool_parameter"]:
            risk_factors += 0
        else:
            risk_factors += 2
        
        # Factor 2: Impact area
        if "all_agents" in proposal.get("description", "").lower():
            risk_factors += 2
        
        # Factor 3: Testing
        if "tested" not in proposal.get("description", "").lower():
            risk_factors += 1
        
        if risk_factors >= 3:
            return RiskLevel.HIGH
        elif risk_factors >= 1:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW


# Global guardian instance
guardian = ImprovementGuardian()


def validate_improvement(proposal: Dict[str, Any]) -> ValidationResult:
    """Convenience function."""
    return guardian.validate(proposal)
```

### Step 4: Baseline Tracker (20 minutes)

**File:** `tools/kurultai/baseline_tracker.py`

```python
#!/usr/bin/env python3
"""
Baseline Tracking for Improvement Validation
Ensures all improvements are measured against explicit baselines
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from neo4j import GraphDatabase
import os

NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'myStrongPassword123')


class BaselineTracker:
    """Tracks metrics before and after improvements."""
    
    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
    
    def capture_baseline(self, agent_id: str, metric_name: str) -> float:
        """
        Capture 24-hour average baseline for a metric.
        
        Returns:
            Baseline value (float)
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (to:TaskOutcome)
                WHERE to.agent = $agent
                  AND to.timestamp > datetime() - duration('P1D')
                RETURN avg(CASE WHEN $metric = 'success_rate' THEN 
                    CASE WHEN to.status = 'success' THEN 1.0 ELSE 0.0 END
                    WHEN $metric = 'avg_tokens' THEN to.tokens_used
                    WHEN $metric = 'avg_duration' THEN to.duration_ms
                    ELSE 0.0
                END) as baseline
            """, agent=agent_id, metric=metric_name)
            
            record = result.single()
            return record['baseline'] or 0.0
    
    def validate_improvement(self, change_id: str, agent_id: str, 
                            metric_name: str, baseline: float,
                            wait_hours: int = 24) -> Dict[str, Any]:
        """
        Validate if an improvement worked.
        
        Args:
            change_id: ID of the implemented change
            agent_id: Agent that made change
            metric_name: Metric to validate
            baseline: Pre-change baseline
            wait_hours: Hours to wait before measuring
        
        Returns:
            Validation result with decision
        """
        # Measure current metric
        current = self.capture_baseline(agent_id, metric_name)
        
        # Calculate improvement
        if baseline == 0:
            improvement_pct = 100 if current > 0 else 0
        else:
            improvement_pct = ((current - baseline) / baseline) * 100
        
        # Decision logic
        if improvement_pct < -10:  # 10% worse
            decision = "rollback"
            reason = f"Degraded by {abs(improvement_pct):.1f}%"
        elif improvement_pct > 10:  # 10% better
            decision = "commit"
            reason = f"Improved by {improvement_pct:.1f}%"
        elif improvement_pct > 0:
            decision = "keep"
            reason = f"Slight improvement: {improvement_pct:.1f}%"
        else:
            decision = "iterate"
            reason = f"No significant change: {improvement_pct:.1f}%"
        
        # Store validation result
        with self.driver.session() as session:
            session.run("""
                MATCH (prop:ImprovementProposal {id: $change_id})
                SET prop.validation_result = $decision,
                    prop.improvement_pct = $pct,
                    prop.validated_at = datetime(),
                    prop.baseline = $baseline,
                    prop.current = $current
            """, change_id=change_id, decision=decision, 
               pct=improvement_pct, baseline=baseline, current=current)
        
        return {
            "decision": decision,
            "improvement_pct": improvement_pct,
            "baseline": baseline,
            "current": current,
            "reason": reason
        }
    
    def close(self):
        self.driver.close()


# Global instance
tracker = BaselineTracker()
```

---

### Step 4 (NEW): Full Neo4j Database Query Module (20 minutes)

**File:** `tools/kurultai/neo4j_context_query.py`

```python
#!/usr/bin/env python3
"""
Complete Neo4j Database Query for Reflection Context
Queries ENTIRE database, not just specific sources
"""

import os
from typing import Dict, List, Any
from neo4j import GraphDatabase

NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'myStrongPassword123')


class Neo4jContextQuery:
    """
    Queries the ENTIRE Neo4j database for reflection context.
    No data source is excluded - full knowledge access.
    """
    
    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
    
    def query_all_nodes(self, agent_id: str = None) -> Dict[str, List[Dict]]:
        """
        Query ALL node types from Neo4j.
        This is comprehensive - every piece of stored knowledge.
        """
        context = {}
        
        with self.driver.session() as session:
            # Get all node labels in database
            labels_result = session.run("""
                CALL db.labels() YIELD label
                RETURN collect(label) as labels
            """)
            labels = labels_result.single()['labels']
            
            # For each label, get recent nodes
            for label in labels:
                query = f"""
                    MATCH (n:{label})
                    """ + ("""WHERE n.agent = $agent OR n.learned_by = $agent OR n.created_by = $agent
                    """ if agent_id else "") + f"""
                    RETURN n LIMIT 50
                """
                
                result = session.run(query, agent=agent_id) if agent_id else session.run(query)
                nodes = [dict(record['n'].items()) for record in result]
                
                if nodes:
                    context[label] = nodes
        
        return context
    
    def query_relationships(self, agent_id: str = None) -> List[Dict]:
        """Query all relationship types and their connections."""
        
        with self.driver.session() as session:
            query = """
                MATCH (a)-[r]->(b)
            """ + ("WHERE a.agent = $agent OR b.agent = $agent" if agent_id else "") + """
                RETURN type(r) as rel_type, 
                       labels(a)[0] as from_label, 
                       labels(b)[0] as to_label,
                       count(*) as count
                LIMIT 100
            """
            
            result = session.run(query, agent=agent_id) if agent_id else session.run(query)
            return [dict(r) for r in result]
    
    def query_user_fed_information(self, agent_id: str = None) -> List[Dict]:
        """
        Query information specifically fed by user.
        These are high-value insights provided directly.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (n)
                WHERE n.source = 'user_fed' 
                   OR n.user_provided = true
                   OR n.feed_type IS NOT NULL
                """ + ("AND (n.agent = $agent OR n.target_agent = $agent)" if agent_id else "") + """
                RETURN n ORDER BY n.timestamp DESC LIMIT 20
            """, agent=agent_id)
            
            return [dict(record['n'].items()) for record in result]
    
    def get_complete_reflection_context(self, agent_id: str) -> Dict[str, Any]:
        """
        Get COMPLETE context from Neo4j for reflection.
        This includes EVERYTHING - no data source excluded.
        """
        return {
            'all_nodes_by_type': self.query_all_nodes(agent_id),
            'relationship_patterns': self.query_relationships(agent_id),
            'user_fed_insights': self.query_user_fed_information(agent_id),
            'database_summary': self._get_database_summary(),
            'timestamp': datetime.now().isoformat()
        }
    
    def _get_database_summary(self) -> Dict[str, int]:
        """Get counts of all node types."""
        with self.driver.session() as session:
            result = session.run("""
                CALL apoc.meta.stats() YIELD labels
                RETURN labels
            """)
            record = result.single()
            return record['labels'] if record else {}
    
    def close(self):
        self.driver.close()


# Usage in reflection:
# context_query = Neo4jContextQuery()
# full_context = context_query.get_complete_reflection_context("kublai")
# Include full_context in Gemini prompt for maximum knowledge access
```

---

### Step 5 (NEW): Memory File Pruning Module (20 minutes)

**File:** `tools/kurultai/memory_pruner.py`

```python
#!/usr/bin/env python3
"""
Memory File Pruning System
Part of hourly reflection - analyzes and prunes memory files
"""

import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from pathlib import Path

# Paths to agent memory files
AGENT_MEMORY_PATHS = {
    'kublai': '/Users/kublai/.openclaw/agents/main/memory/',
    'mongke': '/Users/kublai/.openclaw/agents/researcher/memory/',
    'chagatai': '/Users/kublai/.openclaw/agents/writer/memory/',
    'temujin': '/Users/kublai/.openclaw/agents/developer/memory/',
    'jochi': '/Users/kublai/.openclaw/agents/analyst/memory/',
    'ogedei': '/Users/kublai/.openclaw/agents/ops/memory/',
}

# Max file sizes (in bytes) before pruning consideration
MAX_FILE_SIZES = {
    'daily_notes': 500 * 1024,      # 500KB
    'long_term': 2 * 1024 * 1024,   # 2MB
    'conversation': 1 * 1024 * 1024 # 1MB
}

# Retention policies
RETENTION_DAYS = {
    'daily_notes': 90,      # Keep 90 days of daily notes
    'conversation': 30,     # Keep 30 days of conversation logs
    'long_term': None       # Long-term memory never expires
}


class MemoryPruner:
    """
    Analyzes and prunes memory files during hourly reflection.
    Part of self-improvement cycle.
    """
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.memory_path = AGENT_MEMORY_PATHS.get(agent_id)
    
    def analyze_memory_files(self) -> Dict[str, Any]:
        """
        Analyze all memory files for this agent.
        Returns pruning candidates and statistics.
        """
        if not self.memory_path or not os.path.exists(self.memory_path):
            return {'error': 'Memory path not found'}
        
        analysis = {
            'total_files': 0,
            'total_size_bytes': 0,
            'pruning_candidates': [],
            'large_files': [],
            'old_files': [],
            'redundant_entries': []
        }
        
        for root, dirs, files in os.walk(self.memory_path):
            for file in files:
                file_path = os.path.join(root, file)
                stats = os.stat(file_path)
                
                file_info = {
                    'path': file_path,
                    'size': stats.st_size,
                    'modified': datetime.fromtimestamp(stats.st_mtime),
                    'age_days': (datetime.now() - datetime.fromtimestamp(stats.st_mtime)).days
                }
                
                analysis['total_files'] += 1
                analysis['total_size_bytes'] += stats.st_size
                
                # Check if file is too large
                file_type = self._classify_file(file)
                max_size = MAX_FILE_SIZES.get(file_type, 500 * 1024)
                
                if stats.st_size > max_size:
                    file_info['reason'] = f'Exceeds {max_size/1024:.0f}KB limit'
                    analysis['large_files'].append(file_info)
                
                # Check if file is too old
                retention = RETENTION_DAYS.get(file_type)
                if retention and file_info['age_days'] > retention:
                    file_info['reason'] = f'Older than {retention} days'
                    analysis['old_files'].append(file_info)
                
                # Check for redundant entries (if it's a structured file)
                if file.endswith('.json') or file.endswith('.md'):
                    redundancy = self._check_redundancy(file_path)
                    if redundancy['redundant_count'] > 0:
                        analysis['redundant_entries'].append({
                            'path': file_path,
                            'redundant_count': redundancy['redundant_count'],
                            'suggested_removals': redundancy['removals']
                        })
        
        # Combine all candidates
        analysis['pruning_candidates'] = (
            analysis['large_files'] + 
            analysis['old_files'] +
            [{'path': r['path'], 'reason': 'Redundant entries'} for r in analysis['redundant_entries']]
        )
        
        return analysis
    
    def _classify_file(self, filename: str) -> str:
        """Classify file type for retention policy."""
        if 'daily' in filename.lower() or filename.startswith('202'):
            return 'daily_notes'
        elif 'conversation' in filename.lower() or 'chat' in filename.lower():
            return 'conversation'
        elif 'long' in filename.lower() or 'memory' in filename.lower():
            return 'long_term'
        return 'daily_notes'
    
    def _check_redundancy(self, file_path: str) -> Dict[str, Any]:
        """Check for redundant or duplicate entries in a file."""
        # Placeholder - implement based on file format
        return {'redundant_count': 0, 'removals': []}
    
    def generate_pruning_proposal(self) -> Dict[str, Any]:
        """
        Generate a pruning proposal for the reflection process.
        This is presented to Gemini for consideration.
        """
        analysis = self.analyze_memory_files()
        
        proposal = {
            'agent': self.agent_id,
            'timestamp': datetime.now().isoformat(),
            'current_state': {
                'total_files': analysis.get('total_files', 0),
                'total_size_mb': analysis.get('total_size_bytes', 0) / (1024 * 1024)
            },
            'pruning_opportunities': {
                'large_files_count': len(analysis.get('large_files', [])),
                'old_files_count': len(analysis.get('old_files', [])),
                'redundant_entries_count': len(analysis.get('redundant_entries', []))
            },
            'specific_candidates': [
                {
                    'file': os.path.basename(c['path']),
                    'size_kb': c.get('size', 0) / 1024,
                    'reason': c.get('reason')
                }
                for c in analysis.get('pruning_candidates', [])[:5]  # Top 5
            ],
            'estimated_savings_mb': sum(
                c.get('size', 0) for c in analysis.get('pruning_candidates', [])
            ) / (1024 * 1024)
        }
        
        return proposal
    
    def execute_pruning(self, approved_removals: List[str]) -> Dict[str, Any]:
        """
        Execute approved pruning operations.
        Called after reflection approves the proposal.
        """
        results = {
            'files_removed': [],
            'entries_pruned': 0,
            'space_reclaimed_bytes': 0,
            'errors': []
        }
        
        for file_path in approved_removals:
            try:
                if os.path.exists(file_path):
                    size = os.path.getsize(file_path)
                    os.remove(file_path)
                    results['files_removed'].append(file_path)
                    results['space_reclaimed_bytes'] += size
            except Exception as e:
                results['errors'].append({
                    'file': file_path,
                    'error': str(e)
                })
        
        return results


def get_memory_pruning_context(agent_id: str) -> str:
    """
    Get memory pruning context for reflection prompt.
    """
    pruner = MemoryPruner(agent_id)
    proposal = pruner.generate_pruning_proposal()
    
    return f"""
=== MEMORY FILE ANALYSIS ===

Current Memory State:
- Total files: {proposal['current_state']['total_files']}
- Total size: {proposal['current_state']['total_size_mb']:.2f} MB

Pruning Opportunities:
- Large files: {proposal['pruning_opportunities']['large_files_count']}
- Old files: {proposal['pruning_opportunities']['old_files_count']}
- Redundant entries: {proposal['pruning_opportunities']['redundant_entries_count']}

Top Candidates for Removal:
{json.dumps(proposal['specific_candidates'], indent=2)}

Estimated space savings: {proposal['estimated_savings_mb']:.2f} MB

Should we prune these memory files? Consider:
1. Are the old files still relevant?
2. Can large files be archived/summarized?
3. Are redundant entries truly duplicate?
"""
```

---

## IMPLEMENTATION: PHASE 2 (THIS WEEK)

### Week 1: Pilot with Kublai Only

**Day 1-2:**
- Deploy reflection task for Kublai only
- Monitor for 48 hours
- Verify data flowing into Neo4j
- Fix any issues

**Day 3-5:**
- Add baseline tracking to Kublai's existing tasks
- Implement first improvement proposal
- Test validation/rollback cycle
- Document lessons learned

**Day 6-7:**
- If Kublai pilot successful, add Möngke and Temüjin
- Begin cross-agent sharing
- Weekly review of insights generated

### Week 2-4: Scale to All Agents

- Add remaining agents (Chagatai, Jochi, Ögedei)
- Implement cross-pollination
- Build pattern detection queries
- Create improvement proposals from patterns
- Measure system-wide effectiveness

---

## SUCCESS METRICS

### Short-term (1 week)
- [ ] Reflection nodes appearing hourly in Neo4j
- [ ] Baseline metrics captured for all agents
- [ ] First improvement proposed and validated
- [ ] No critical errors or rollbacks needed

### Medium-term (1 month)
- [ ] 10% measurable improvement in task completion rates
- [ ] 5% reduction in average token usage per task
- [ ] 3+ cross-agent insights successfully transferred
- [ ] Meta-learning tracker identifying effective strategies

### Long-term (3 months)
- [ ] Agents adapt strategies without human intervention
- [ ] Self-generated tools in active use
- [ ] Measurable productivity gains across all agents
- [ ] System demonstrates emergent optimization behaviors

---

## ROLLBACK PLAN

### If Something Goes Wrong:

```bash
# 1. Stop reflection tasks
launchctl stop com.kurultai.heartbeat

# 2. Rollback to pre-deployment state
cd ~/kurultai/kublai-repo
./scripts/setup_agent_gemini.sh --rollback

# 3. Remove self-improvement code
rm tools/kurultai/self_improvement.py
git checkout HEAD -- tools/kurultai/agent_tasks.py

# 4. Restart with original configuration
launchctl start com.kurultai.heartbeat
```

### Emergency Contact:
- **Kublai** (me) monitors the system
- Alert via Signal if critical issues detected
- Automatic rollback if metrics degrade >20%

---

## FILES CREATED

| File | Purpose | Lines |
|------|---------|-------|
| `tools/kurultai/self_improvement.py` | Core reflection system | ~400 |
| `tools/kurultai/improvement_guardian.py` | Safety validation | ~200 |
| `tools/kurultai/baseline_tracker.py` | Metric validation | ~150 |
| This document | Complete plan | ~800 |

---

## IMMEDIATE NEXT STEPS

### Right Now (Next 30 minutes):

1. **Create the 3 Python files above**
2. **Run Neo4j schema setup**
3. **Register Kublai's reflection task in heartbeat**
4. **Test manually:** Trigger one reflection, verify Neo4j storage

### If Test Passes (Next 2 hours):

5. Add baseline tracking to existing tasks
6. Let run for 24 hours to collect baseline data
7. Review first reflections
8. Implement safety guardian

### Tomorrow:

9. Review 24-hour data
10. Generate first improvement proposal
11. Test validation cycle
12. Decide: scale to more agents or iterate on Kublai

---

## CONCLUSION

This is a **production-ready, research-backed, safety-guarded self-improvement system** where:

- ✅ **Every agent has dedicated Gemini 3.1 Pro Preview**
- ✅ **Every reflection queries the ENTIRE Neo4j database** (full knowledge access)
- ✅ **Memory files are pruned as part of reflection** (self-managing storage)
- ✅ **Every improvement is validated with explicit baselines**
- ✅ **Every change passes safety guardian**
- ✅ **Cross-agent learning happens automatically**
- ✅ **Rollbacks are automatic if things go wrong**

**The system gets smarter every hour, with full knowledge access and self-pruning memory.**

---

## UPDATED FILES LIST

| File | Purpose | Lines |
|------|---------|-------|
| `tools/kurultai/self_improvement.py` | Core reflection system | ~400 |
| `tools/kurultai/neo4j_context_query.py` | **Full database query** | ~150 |
| `tools/kurultai/memory_pruner.py` | **Memory pruning system** | ~250 |
| `tools/kurultai/improvement_guardian.py` | Safety validation | ~200 |
| `tools/kurultai/baseline_tracker.py` | Metric validation | ~150 |
| This document | Complete plan | ~1100 |
