#!/usr/bin/env python3
"""
Kublai Review System
Kublai reviews agent reflections using Gemini CLI with full context
Decides: implement, reject, or consult human
"""
from __future__ import annotations

import os
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from enum import Enum
from dataclasses import dataclass
from pathlib import Path

from neo4j import GraphDatabase
from tools.kurultai.agent_gemini import kublai_gemini

NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'myStrongPassword123')


class ReviewDecision(Enum):
    IMPLEMENT = "implement"
    REJECT = "reject"
    CONSULT_HUMAN = "consult_human"
    DEFER = "defer"


class KublaiReviewSystem:
    """Kublai reviews agent proposals with full system context."""
    
    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        self.kublai = kublai_gemini()
        self.base_path = Path("~/kurultai/kublai-repo").expanduser()
    
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
    
    def _load_architecture_md(self) -> str:
        """Load ARCHITECTURE.md content."""
        arch_path = self.base_path / "ARCHITECTURE.md"
        try:
            with open(arch_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            return "# ARCHITECTURE.md not found"
    
    def _scan_codebase(self) -> str:
        """Scan codebase for relevant context."""
        key_files = []
        scan_dirs = [
            self.base_path / "tools" / "kurultai",
            self.base_path / "src",
            self.base_path / "scripts"
        ]
        
        for scan_dir in scan_dirs:
            if scan_dir.exists():
                for py_file in scan_dir.rglob("*.py"):
                    if py_file.stat().st_size < 50000:
                        try:
                            with open(py_file, 'r') as f:
                                content = f.read()
                                if '"""' in content:
                                    doc = content.split('"""')[1][:200]
                                else:
                                    doc = content[:200]
                                
                                rel_path = py_file.relative_to(self.base_path)
                                key_files.append(f"{rel_path}: {doc.strip()}")
                        except:
                            pass
        
        return "\n".join(key_files[:20])
    
    def _gather_neo4j_context(self) -> Dict[str, Any]:
        """Gather comprehensive Neo4j context."""
        with self.driver.session() as session:
            try:
                result = session.run("""
                    CALL apoc.meta.stats()
                    YIELD nodeCount, relCount
                    RETURN nodeCount, relCount
                """)
                stats = result.single()
            except:
                stats = None
            
            result = session.run("""
                MATCH (a:Agent)
                RETURN a.name as name, a.status as status
            """)
            agents = [dict(r) for r in result]
            
            result = session.run("""
                MATCH (p:Pattern)
                RETURN p.description as desc, p.confidence as conf
                ORDER BY p.confidence DESC
                LIMIT 5
            """)
            patterns = [dict(r) for r in result]
            
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
    
    def review_proposal(self, reflection_id: str) -> Dict[str, Any]:
        """Kublai reviews a single proposal with full context."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:AgentReflection {id: $id})
                RETURN r
            """, id=reflection_id)
            record = result.single()
            if not record:
                return {"error": "Reflection not found"}
            
            reflection = dict(record['r'])
        
        architecture_context = self._load_architecture_md()
        codebase_context = self._scan_codebase()
        neo4j_context = self._gather_neo4j_context()
        
        prompt = f"""
=== KUBLAI REVIEW TASK ===

You are Kublai, Squad Lead of the Kurultai.
Review this proposal with full system context.

=== SYSTEM ARCHITECTURE (ARCHITECTURE.md) ===

{architecture_context[:4000]}

=== CODEBASE CONTEXT ===

{codebase_context}

=== NEO4J KNOWLEDGE GRAPH ===

Graph Statistics:
- Total Nodes: {neo4j_context.get('node_count', 0)}
- Total Relationships: {neo4j_context.get('rel_count', 0)}
- Active Agents: {len(neo4j_context.get('agents', []))}

=== PROPOSAL TO REVIEW ===

From Agent: {reflection['agent']}
Timestamp: {reflection['timestamp']}
Priority: {reflection['priority']}
Confidence: {reflection['confidence']}

Raw Reflection:
{reflection['raw_text'][:2500]}

Parsed Proposals:
{reflection['proposals']}

=== ARCHITECTURAL CONSIDERATION ===

1. Does this align with ARCHITECTURE.md?
2. Are there existing modules for this?
3. Would this create architectural debt?
4. Which sections are relevant to {reflection['agent']}?

=== CODEBASE CONSIDERATION ===

1. Existing implementations of similar functionality?
2. Would this duplicate existing code?
3. Which files would need modification?
4. Integration points?

=== REVIEW CRITERIA ===

1. ARCHITECTURAL FIT:
   - Matches design → STRONG
   - Extends patterns → GOOD
   - Requires changes → WEAK
   - Contradicts → REJECT

2. IMPACT: (Minimal/Moderate/Significant)
3. RISK: (Low/Medium/High)
4. ALIGNMENT with mission
5. REVERSIBILITY

=== DECISION OPTIONS ===

A. IMPLEMENT - Low risk, fits architecture, reversible
B. REJECT - Misaligned, risky, or violates architecture
C. CONSULT_HUMAN - High risk, system-wide, architectural change
D. DEFER - Needs more validation

=== RESPONSE FORMAT ===

DECISION: [IMPLEMENT | REJECT | CONSULT_HUMAN | DEFER]
CONFIDENCE: [0.0-1.0]

ARCHITECTURAL_ANALYSIS:
- Aligns with ARCHITECTURE.md? (Yes/No/Partial)
- Relevant sections: [list]
- Concerns: [list]

CODEBASE_ANALYSIS:
- Files to modify: [list]
- Existing implementations: [list]
- Integration points: [list]

IMPACT_ASSESSMENT:
- Scope: (One agent/Multiple/System-wide)
- Expected improvement: [description]

RISK_ASSESSMENT:
- Level: (Low/Medium/High)
- What could go wrong: [description]
- Mitigation: [list]

ALIGNMENT:
- Fits mission: (Yes/No)
- Creates value: (Yes/No)

FINAL_REASONING:
[Your reasoning]

IMPLEMENTATION_NOTES (if IMPLEMENT):
- Files: [list]
- Tests: [list]
- Rollback: [description]
- Effort: [estimate]

HUMAN_CONTEXT (if CONSULT_HUMAN):
- Why human needed: [concern]
- Decision needed: [options]
- Trade-offs: [pros/cons]
- If nothing done: [consequence]
"""
        
        review_response = self.kublai.query(prompt)
        decision = self._parse_decision(review_response)
        self._store_review(reflection_id, decision, review_response)
        
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
            'architectural_analysis': '',
            'codebase_analysis': '',
            'impact_assessment': '',
            'risk_assessment': '',
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
            
            elif line.startswith('ARCHITECTURAL_ANALYSIS:'):
                current_section = 'architectural_analysis'
            elif line.startswith('CODEBASE_ANALYSIS:'):
                current_section = 'codebase_analysis'
            elif line.startswith('IMPACT_ASSESSMENT:'):
                current_section = 'impact_assessment'
            elif line.startswith('RISK_ASSESSMENT:'):
                current_section = 'risk_assessment'
            elif line.startswith('FINAL_REASONING:'):
                current_section = 'rationale'
            elif line.startswith('IMPLEMENTATION_NOTES:'):
                current_section = 'implementation_notes'
            elif line.startswith('HUMAN_CONTEXT:'):
                current_section = 'human_context'
            elif current_section and line and not line.startswith('==='):
                decision_data[current_section] += line + '\n'
        
        return decision_data
    
    def _store_review(self, reflection_id: str, decision: Dict, raw_response: str):
        """Store review decision in brain (Neo4j)."""
        with self.driver.session() as session:
            session.run("""
                MATCH (r:AgentReflection {id: $ref_id})
                CREATE (rev:Review {
                    id: $rev_id,
                    timestamp: datetime(),
                    decision: $decision,
                    confidence: $confidence,
                    architectural_analysis: $arch,
                    codebase_analysis: $code,
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
            arch=decision.get('architectural_analysis', '')[:500],
            code=decision.get('codebase_analysis', '')[:500],
            rationale=decision.get('rationale', '')[:1000],
            raw=raw_response[:2000]
            )
    
    def _queue_implementation(self, reflection_id: str, decision: Dict):
        """Queue proposal for implementation."""
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
        human_context = decision.get('human_context', 'Critical decision needed')
        
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


async def kublai_review_task():
    """Heartbeat task: Kublai reviews pending agent reflections."""
    system = KublaiReviewSystem()
    try:
        results = system.process_all_pending()
        
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
