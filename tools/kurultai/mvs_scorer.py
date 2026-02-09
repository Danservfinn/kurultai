#!/usr/bin/env python3
"""
Memory Value Score (MVS) Scorer for Kurultai

Implements the MVS formula from ARCHITECTURE.md:
MVS = (
    type_weight
    + recency_bonus
    + frequency_bonus
    + quality_bonus
    + centrality_bonus
    + cross_agent_bonus
    - bloat_penalty
) * safety_multiplier
"""

import os
import json
import math
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from neo4j import GraphDatabase

# Type weights from ARCHITECTURE.md
TYPE_WEIGHTS = {
    'Belief': 10.0,
    'Reflection': 8.0,
    'Analysis': 7.0,
    'Synthesis': 6.5,
    'Recommendation': 5.0,
    'CompressedContext': 4.0,
    'Task': 3.0,
    'MemoryEntry': 2.5,
    'SessionContext': 1.5,
    'Notification': 0.5
}

# Half-lives for recency calculation (in days)
HALF_LIVES = {
    'Belief': 180,
    'Reflection': 90,
    'Analysis': 60,
    'Synthesis': 120,
    'Recommendation': 30,
    'CompressedContext': 90,
    'Task': None,  # Protected
    'MemoryEntry': 45,
    'SessionContext': 1,
    'Notification': 0.5
}

# Token targets by tier
TIER_TARGETS = {
    'HOT': 1600,
    'WARM': 400,
    'COLD': 200
}


class MVSScorer:
    """Calculate Memory Value Scores for Neo4j nodes."""
    
    def __init__(self, neo4j_driver=None):
        if neo4j_driver:
            self.driver = neo4j_driver
        else:
            uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
            password = os.environ.get('NEO4J_PASSWORD')
            self.driver = GraphDatabase.driver(uri, auth=('neo4j', password))
    
    def calculate_recency_bonus(self, created_at: datetime, node_type: str) -> float:
        """Calculate recency bonus with exponential decay."""
        half_life_days = HALF_LIVES.get(node_type, 45)
        if half_life_days is None:
            return 3.0  # Protected types get max bonus
        
        age_days = (datetime.now() - created_at).days
        # Exponential decay: bonus = 3.0 * (0.5 ^ (age / half_life))
        bonus = 3.0 * math.pow(0.5, age_days / half_life_days)
        return min(bonus, 3.0)  # Cap at 3.0
    
    def calculate_frequency_bonus(self, access_count_7d: int) -> float:
        """Calculate frequency bonus based on 7-day access count."""
        # Log-scaled: bonus = 2.0 * log(1 + count) / log(100)
        if access_count_7d <= 0:
            return 0.0
        bonus = 2.0 * math.log1p(access_count_7d) / math.log(100)
        return min(bonus, 2.0)  # Cap at 2.0
    
    def calculate_quality_bonus(self, confidence: float, severity: str = None) -> float:
        """Calculate quality bonus from confidence and severity."""
        # Base bonus from confidence (0-1) scaled to 0-2
        bonus = confidence * 2.0
        
        # Severity boost for Analysis nodes
        if severity:
            severity_boost = {
                'critical': 0.5,
                'high': 0.3,
                'medium': 0.1,
                'low': 0.0
            }.get(severity, 0.0)
            bonus += severity_boost
        
        return min(bonus, 2.0)  # Cap at 2.0
    
    def calculate_centrality_bonus(self, relationship_count: int) -> float:
        """Calculate centrality bonus based on relationship count."""
        # Linear scaling: 1.5 * min(count / 10, 1.0)
        bonus = 1.5 * min(relationship_count / 10.0, 1.0)
        return bonus
    
    def calculate_cross_agent_bonus(self, agent_access_count: int) -> float:
        """Calculate cross-agent access bonus."""
        # Bonus for access by multiple agents
        bonus = min(agent_access_count * 0.5, 2.0)  # 0.5 per agent, max 2.0
        return bonus
    
    def calculate_bloat_penalty(self, token_count: int, tier: str) -> float:
        """Calculate bloat penalty for nodes over tier target."""
        target = TIER_TARGETS.get(tier, 400)
        if token_count <= target:
            return 0.0
        
        # Penalty increases as tokens exceed target
        excess_ratio = (token_count - target) / target
        penalty = min(excess_ratio * 1.5, 1.5)  # Cap at 1.5
        return penalty
    
    def calculate_mvs(self, node_data: Dict) -> float:
        """
        Calculate full MVS for a node.
        
        Args:
            node_data: Dictionary with node properties
        
        Returns:
            MVS score (float)
        """
        node_type = node_data.get('type', 'MemoryEntry')
        
        # Base type weight
        type_weight = TYPE_WEIGHTS.get(node_type, 2.5)
        
        # Recency bonus
        created_at = node_data.get('created_at', datetime.now())
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        recency_bonus = self.calculate_recency_bonus(created_at, node_type)
        
        # Frequency bonus
        access_count = node_data.get('access_count_7d', 0)
        frequency_bonus = self.calculate_frequency_bonus(access_count)
        
        # Quality bonus
        confidence = node_data.get('confidence', 0.5)
        severity = node_data.get('severity')
        quality_bonus = self.calculate_quality_bonus(confidence, severity)
        
        # Centrality bonus
        rel_count = node_data.get('relationship_count', 0)
        centrality_bonus = self.calculate_centrality_bonus(rel_count)
        
        # Cross-agent bonus
        agent_access = node_data.get('cross_agent_access', 0)
        cross_agent_bonus = self.calculate_cross_agent_bonus(agent_access)
        
        # Bloat penalty
        token_count = node_data.get('token_count', 0)
        tier = node_data.get('tier', 'WARM')
        bloat_penalty = self.calculate_bloat_penalty(token_count, tier)
        
        # Safety multiplier
        # Protect high-confidence beliefs, active tasks, entries < 24h
        safety_multiplier = 1.0
        if node_type == 'Belief' and confidence >= 0.9:
            safety_multiplier = 100.0
        elif node_type == 'Task' and node_data.get('status') in ['active', 'in_progress']:
            safety_multiplier = 100.0
        elif (datetime.now() - created_at).total_seconds() < 86400:  # < 24h
            safety_multiplier = 100.0
        
        # Calculate MVS
        mvs = (
            type_weight
            + recency_bonus
            + frequency_bonus
            + quality_bonus
            + centrality_bonus
            + cross_agent_bonus
            - bloat_penalty
        ) * safety_multiplier
        
        return round(mvs, 2)
    
    def score_all_nodes(self, limit: int = 100) -> int:
        """
        Score all memory nodes in Neo4j.
        
        Args:
            limit: Maximum nodes to score per run
        
        Returns:
            Number of nodes scored
        """
        scored = 0
        
        with self.driver.session() as session:
            # Get nodes without MVS or with stale MVS
            result = session.run('''
                MATCH (n)
                WHERE n.type IN ['Belief', 'Reflection', 'Analysis', 'Synthesis', 
                                 'Recommendation', 'MemoryEntry', 'SessionContext', 'Notification']
                  AND (n.mvs_score IS NULL OR n.last_mvs_update < datetime() - duration('PT1H'))
                RETURN n.id as id, n.type as type, n.created_at as created_at,
                       n.access_count_7d as access_count, n.confidence as confidence,
                       n.severity as severity, n.token_count as tokens, n.tier as tier
                LIMIT $limit
            ''', limit=limit)
            
            for record in result:
                node_data = {
                    'type': record['type'],
                    'created_at': record['created_at'],
                    'access_count_7d': record['access_count'] or 0,
                    'confidence': record['confidence'] or 0.5,
                    'severity': record['severity'],
                    'token_count': record['tokens'] or 0,
                    'tier': record['tier'] or 'WARM'
                }
                
                mvs = self.calculate_mvs(node_data)
                
                # Update node
                session.run('''
                    MATCH (n {id: $id})
                    SET n.mvs_score = $mvs,
                        n.last_mvs_update = datetime()
                ''', id=record['id'], mvs=mvs)
                
                scored += 1
        
        return scored
    
    def get_curation_action(self, mvs: float, node_type: str) -> str:
        """
        Determine curation action based on MVS.
        
        Returns:
            'KEEP', 'IMPROVE', 'MERGE', 'DEMOTE', 'PRUNE'
        """
        if mvs >= 50.0:
            return 'KEEP'  # Safety protected
        elif mvs >= 8.0:
            return 'KEEP'
        elif mvs >= 5.0:
            return 'IMPROVE'  # Flag for compression if bloated
        elif mvs >= 3.0:
            return 'IMPROVE'
        elif mvs >= 1.5:
            return 'DEMOTE'
        elif mvs >= 0.5:
            return 'PRUNE'  # Soft delete with tombstone
        else:
            return 'PRUNE'  # Immediate for Notifications/Sessions


def main():
    """Run MVS scoring pass."""
    import argparse
    
    parser = argparse.ArgumentParser(description='MVS Scorer')
    parser.add_argument('--pass', action='store_true', dest='run_pass',
                       help='Run scoring pass on all nodes')
    parser.add_argument('--limit', type=int, default=100,
                       help='Maximum nodes to score')
    parser.add_argument('--test', action='store_true',
                       help='Test calculation on sample data')
    
    args = parser.parse_args()
    
    scorer = MVSScorer()
    
    if args.test:
        # Test with sample data
        test_data = {
            'type': 'Belief',
            'created_at': datetime.now() - timedelta(days=30),
            'access_count_7d': 5,
            'confidence': 0.85,
            'token_count': 500,
            'tier': 'WARM',
            'relationship_count': 8
        }
        mvs = scorer.calculate_mvs(test_data)
        print(f"Test MVS: {mvs}")
        print(f"Action: {scorer.get_curation_action(mvs, 'Belief')}")
    
    elif args.run_pass:
        print("🧮 Running MVS scoring pass...")
        scored = scorer.score_all_nodes(args.limit)
        print(f"✅ Scored {scored} nodes")
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
