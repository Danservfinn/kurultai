"""
Phase 7: Optimization Engine
Continuous improvement system for Kurultai
"""
import os
import json
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from neo4j import GraphDatabase

@dataclass
class OptimizationTask:
    """An ongoing optimization task"""
    name: str
    agent: str
    trigger: str  # 'monthly', 'quarterly', 'bi-weekly', 'continuous', 'cve'
    handler: Callable
    description: str
    last_run: Optional[datetime] = None
    
class OptimizationEngine:
    """
    Phase 7: Continuous Optimization
    
    Tasks:
    - P9-T1: Token Budget Optimization (Monthly)
    - P9-T2: MVS Formula Tuning (Quarterly)  
    - P9-T3: Agent Performance Profiling (Bi-weekly)
    - P9-T4: Security Layer Updates (CVE announcements)
    - P9-T5: Architecture Self-Improvement (Continuous)
    """
    
    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver
        self.tasks: List[OptimizationTask] = []
        self._register_default_tasks()
        
    def _register_default_tasks(self):
        """Register Phase 7 optimization tasks"""
        self.register(OptimizationTask(
            name="token_budget_optimization",
            agent="Jochi",
            trigger="monthly",
            handler=self._optimize_token_budgets,
            description="Review token usage patterns; optimize task budgets"
        ))
        
        self.register(OptimizationTask(
            name="mvs_formula_tuning",
            agent="Jochi", 
            trigger="quarterly",
            handler=self._tune_mvs_formula,
            description="Analyze MVS effectiveness; tune weights and bonuses"
        ))
        
        self.register(OptimizationTask(
            name="agent_performance_profiling",
            agent="Jochi",
            trigger="bi-weekly",
            handler=self._profile_agents,
            description="Profile agent performance; identify bottlenecks"
        ))
        
        self.register(OptimizationTask(
            name="security_layer_updates",
            agent="Jochi",
            trigger="cve",
            handler=self._check_security_updates,
            description="Monitor CVEs; update security layers as needed"
        ))
        
        self.register(OptimizationTask(
            name="architecture_self_improvement",
            agent="Kublai",
            trigger="continuous",
            handler=self._self_improve,
            description="Continuous architecture introspection; propose improvements"
        ))
        
    def register(self, task: OptimizationTask):
        """Register an optimization task"""
        self.tasks.append(task)
        
    async def run_optimization_cycle(self):
        """Run all due optimization tasks"""
        now = datetime.utcnow()
        results = []
        
        for task in self.tasks:
            if self._is_due(task, now):
                try:
                    result = await task.handler()
                    task.last_run = now
                    results.append({
                        "task": task.name,
                        "status": "success",
                        "result": result
                    })
                    self._log_result(task, "success", result)
                except Exception as e:
                    results.append({
                        "task": task.name,
                        "status": "error",
                        "error": str(e)
                    })
                    self._log_result(task, "error", None, str(e))
                    
        return results
        
    def _is_due(self, task: OptimizationTask, now: datetime) -> bool:
        """Check if a task is due to run"""
        if task.last_run is None:
            return True
            
        intervals = {
            "continuous": timedelta(minutes=5),
            "bi-weekly": timedelta(weeks=2),
            "monthly": timedelta(days=30),
            "quarterly": timedelta(days=90),
            "cve": timedelta(hours=24)  # Check daily for CVEs
        }
        
        return now - task.last_run >= intervals.get(task.trigger, timedelta(days=1))
        
    async def _optimize_token_budgets(self):
        """P9-T1: Analyze and optimize token budgets"""
        with self.driver.session() as session:
            # Analyze token usage patterns
            result = session.run("""
                MATCH (tr:TaskResult)
                WHERE tr.tokens_used IS NOT NULL
                RETURN tr.task_name as task,
                       avg(tr.tokens_used) as avg_tokens,
                       max(tr.tokens_used) as max_tokens,
                       count(*) as executions
                ORDER BY avg_tokens DESC
            """)
            
            analysis = []
            for record in result:
                task_name = record["task"]
                avg_tokens = record["avg_tokens"]
                max_tokens = record["max_tokens"]
                executions = record["executions"]
                
                # Identify over-budget tasks
                if avg_tokens > 1000:
                    analysis.append({
                        "task": task_name,
                        "avg_tokens": avg_tokens,
                        "max_tokens": max_tokens,
                        "executions": executions,
                        "recommendation": "Consider optimization or budget increase"
                    })
                    
            return {
                "type": "token_budget_analysis",
                "over_budget_tasks": len(analysis),
                "recommendations": analysis
            }
            
    async def _tune_mvs_formula(self):
        """P9-T2: Analyze MVS effectiveness and tune formula"""
        with self.driver.session() as session:
            # Check MVS distribution
            result = session.run("""
                MATCH (n)
                WHERE n.mvs_score IS NOT NULL
                RETURN 
                    count(*) as total,
                    avg(n.mvs_score) as avg_score,
                    percentileCont(n.mvs_score, 0.5) as median,
                    min(n.mvs_score) as min_score,
                    max(n.mvs_score) as max_score
            """)
            
            record = result.single()
            return {
                "type": "mvs_tuning",
                "distribution": {
                    "total_nodes": record["total"],
                    "average": record["avg_score"],
                    "median": record["median"],
                    "range": [record["min_score"], record["max_score"]]
                },
                "recommendations": [
                    "Monitor distribution quarterly",
                    "Adjust type weights if certain types dominate",
                    "Review bloat penalty effectiveness"
                ]
            }
            
    async def _profile_agents(self):
        """P9-T3: Profile agent performance"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (tr:TaskResult)-[:EXECUTED_BY]->(a:Agent)
                RETURN a.name as agent,
                       count(tr) as total_tasks,
                       avg(tr.duration_ms) as avg_duration,
                       sum(CASE WHEN tr.status = 'success' THEN 1 ELSE 0 END) as successes
                ORDER BY avg_duration DESC
            """)
            
            profiles = []
            for record in result:
                total = record["total_tasks"]
                successes = record["successes"]
                rate = (successes / total * 100) if total > 0 else 0
                
                profiles.append({
                    "agent": record["agent"],
                    "tasks_completed": total,
                    "avg_duration_ms": record["avg_duration"],
                    "success_rate": f"{rate:.1f}%"
                })
                
            return {
                "type": "agent_profiling",
                "profiles": profiles
            }
            
    async def _check_security_updates(self):
        """P9-T4: Check for security updates"""
        # In production, this would check CVE databases
        return {
            "type": "security_check",
            "status": "nominal",
            "last_cve_check": datetime.utcnow().isoformat(),
            "recommendations": [
                "Monitor https://cve.mitre.org/ for Python/Neo4j updates",
                "Review security layer test coverage quarterly"
            ]
        }
        
    async def _self_improve(self):
        """P9-T5: Continuous architecture self-improvement"""
        with self.driver.session() as session:
            # Check for improvement opportunities
            result = session.run("""
                MATCH (i:ImprovementProposal {status: 'pending'})
                RETURN count(*) as pending,
                       avg(i.confidence) as avg_confidence
            """)
            
            record = result.single()
            return {
                "type": "self_improvement",
                "pending_proposals": record["pending"],
                "avg_confidence": record["avg_confidence"],
                "actions": [
                    "Review pending proposals",
                    "Generate new proposals from recent TaskResults"
                ]
            }
            
    def _log_result(self, task: OptimizationTask, status: str, result=None, error=None):
        """Log optimization result to Neo4j"""
        with self.driver.session() as session:
            session.run("""
                CREATE (o:OptimizationResult {
                    id: randomUUID(),
                    task_name: $task_name,
                    agent: $agent,
                    status: $status,
                    result: $result,
                    error: $error,
                    created_at: datetime()
                })
            """, task_name=task.name, agent=task.agent, 
                 status=status, result=json.dumps(result) if result else None,
                 error=error)

# Singleton instance
_optimization_engine: Optional[OptimizationEngine] = None

def get_optimization_engine(neo4j_driver=None):
    """Get or create the optimization engine singleton"""
    global _optimization_engine
    if _optimization_engine is None:
        if neo4j_driver is None:
            raise ValueError("Neo4j driver required for initial setup")
        _optimization_engine = OptimizationEngine(neo4j_driver)
    return _optimization_engine
