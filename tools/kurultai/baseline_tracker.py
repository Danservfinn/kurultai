#!/usr/bin/env python3
"""
Baseline Tracker for Improvement Validation
Ensures all improvements are measured against explicit baselines
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from neo4j import GraphDatabase

NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'myStrongPassword123')


@dataclass
class BaselineMeasurement:
    """Baseline metrics before an improvement."""
    change_id: str
    agent_id: str
    metric_name: str
    baseline_value: float
    timestamp: datetime
    context: Dict[str, Any]


class BaselineTracker:
    """Tracks metrics before and after improvements."""
    
    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
    
    def capture_baseline(self, agent_id: str, metric_name: str, 
                         change_id: str) -> BaselineMeasurement:
        """Capture 24-hour average baseline for a metric."""
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
                END) as baseline,
                count(to) as sample_size
            """, agent=agent_id, metric=metric_name)
            
            record = result.single()
            baseline_value = record['baseline'] or 0.0
            sample_size = record['sample_size'] or 0
            
            measurement = BaselineMeasurement(
                change_id=change_id,
                agent_id=agent_id,
                metric_name=metric_name,
                baseline_value=baseline_value,
                timestamp=datetime.now(),
                context={'sample_size': sample_size}
            )
            
            # Store baseline
            session.run("""
                CREATE (b:Baseline {
                    id: $id,
                    change_id: $change_id,
                    agent: $agent,
                    metric: $metric,
                    value: $value,
                    timestamp: datetime(),
                    sample_size: $sample_size
                })
            """,
            id=f"baseline-{change_id}-{metric_name}",
            change_id=change_id,
            agent=agent_id,
            metric=metric_name,
            value=baseline_value,
            sample_size=sample_size
            )
            
            return measurement
    
    def validate_improvement(self, change_id: str, agent_id: str,
                            metric_name: str) -> Dict[str, Any]:
        """
        Validate if an improvement worked.
        
        Returns decision: commit, rollback, keep, iterate
        """
        # Get baseline
        with self.driver.session() as session:
            result = session.run("""
                MATCH (b:Baseline {change_id: $change_id, metric: $metric})
                RETURN b.value as baseline, b.timestamp as baseline_time
            """, change_id=change_id, metric=metric_name)
            
            baseline_record = result.single()
            if not baseline_record:
                return {
                    "decision": "unknown",
                    "error": "No baseline found",
                    "change_id": change_id
                }
            
            baseline = baseline_record['baseline']
            baseline_time = baseline_record['baseline_time']
            
            # Get current metric
            result = session.run("""
                MATCH (to:TaskOutcome)
                WHERE to.agent = $agent
                  AND to.timestamp > $baseline_time
                RETURN avg(CASE WHEN $metric = 'success_rate' THEN 
                    CASE WHEN to.status = 'success' THEN 1.0 ELSE 0.0 END
                    WHEN $metric = 'avg_tokens' THEN to.tokens_used
                    WHEN $metric = 'avg_duration' THEN to.duration_ms
                    ELSE 0.0
                END) as current,
                count(to) as sample_size
            """, agent=agent_id, metric=metric_name, 
               baseline_time=baseline_time)
            
            current_record = result.single()
            current = current_record['current'] or 0.0
            sample_size = current_record['sample_size'] or 0
            
            # Calculate improvement
            if baseline == 0:
                improvement_pct = 100 if current > 0 else 0
            else:
                improvement_pct = ((current - baseline) / baseline) * 100
            
            # Decision logic
            if improvement_pct < -10:
                decision = "rollback"
                reason = f"Degraded by {abs(improvement_pct):.1f}%"
            elif improvement_pct > 10:
                decision = "commit"
                reason = f"Improved by {improvement_pct:.1f}%"
            elif improvement_pct > 0:
                decision = "keep"
                reason = f"Slight improvement: {improvement_pct:.1f}%"
            else:
                decision = "iterate"
                reason = f"No significant change: {improvement_pct:.1f}%"
            
            # Store validation result
            session.run("""
                MATCH (imp:ImplementationQueue {id: $change_id})
                CREATE (v:Validation {
                    id: $val_id,
                    timestamp: datetime(),
                    metric: $metric,
                    baseline: $baseline,
                    current: $current,
                    improvement_pct: $pct,
                    decision: $decision,
                    reason: $reason,
                    sample_size: $sample_size
                })
                CREATE (imp)-[:VALIDATED_BY]->(v)
                SET imp.validation_result = $decision,
                    imp.validated_at = datetime()
            """,
            change_id=f"imp-{change_id}",
            val_id=f"val-{change_id}-{metric_name}",
            metric=metric_name,
            baseline=baseline,
            current=current,
            pct=improvement_pct,
            decision=decision,
            reason=reason,
            sample_size=sample_size
            )
            
            return {
                "decision": decision,
                "improvement_pct": improvement_pct,
                "baseline": baseline,
                "current": current,
                "reason": reason,
                "sample_size": sample_size
            }
    
    def get_validation_summary(self, change_id: str) -> Dict[str, Any]:
        """Get complete validation summary for a change."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (imp:ImplementationQueue {id: $change_id})-[:VALIDATED_BY]->(v:Validation)
                RETURN v.metric as metric, v.decision as decision,
                       v.improvement_pct as pct, v.reason as reason
            """, change_id=f"imp-{change_id}")
            
            validations = [dict(r) for r in result]
            
            if not validations:
                return {"status": "pending", "validations": []}
            
            # Overall decision
            decisions = [v['decision'] for v in validations]
            if 'rollback' in decisions:
                overall = 'rollback'
            elif all(d == 'commit' for d in decisions):
                overall = 'commit'
            elif any(d == 'commit' for d in decisions):
                overall = 'keep'
            else:
                overall = 'iterate'
            
            return {
                "status": "validated",
                "overall_decision": overall,
                "validations": validations,
                "avg_improvement": sum(v['pct'] for v in validations) / len(validations)
            }
    
    def list_pending_validations(self) -> List[Dict[str, Any]]:
        """List all changes waiting for validation."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (imp:ImplementationQueue)
                WHERE imp.status = 'implemented'
                  AND imp.validation_result IS NULL
                  AND imp.implemented_at < datetime() - duration('PT24H')
                RETURN imp.id as change_id, imp.agent as agent,
                       imp.implemented_at as time
            """)
            return [dict(r) for r in result]
    
    def close(self):
        self.driver.close()


async def validate_improvements_task():
    """Heartbeat task: Validate pending improvements."""
    tracker = BaselineTracker()
    try:
        pending = tracker.list_pending_validations()
        results = []
        
        for change in pending:
            # Validate primary metric
            result = tracker.validate_improvement(
                change['change_id'].replace('imp-', ''),
                change['agent'],
                'success_rate'
            )
            results.append({
                'change_id': change['change_id'],
                'decision': result['decision'],
                'improvement': result['improvement_pct']
            })
        
        return {
            "status": "success",
            "validated_count": len(results),
            "results": results
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        tracker.close()


if __name__ == "__main__":
    print("Testing Baseline Tracker...")
    tracker = BaselineTracker()
    
    # Test capture
    baseline = tracker.capture_baseline("kublai", "success_rate", "test-change-001")
    print(f"Captured baseline: {baseline.baseline_value}")
    
    # Test validation
    result = tracker.validate_improvement("test-change-001", "kublai", "success_rate")
    print(f"Validation result: {result['decision']}")
    
    tracker.close()
    print("Test complete!")
