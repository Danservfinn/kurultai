"""
Health Recovery Integration

Integrates HealthOrchestrator with ErrorRecoveryManager for autonomous failure recovery.

When health checks detect failures, automatically triggers recovery procedures.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from tools.kurultai.health.health_orchestrator import HealthOrchestrator, HealthStatus
from tools.error_recovery import ErrorRecoveryManager, ScenarioCode, RecoveryStatus

logger = logging.getLogger(__name__)


class AutonomousRecoverySystem:
    """
    Bridges health checks and error recovery for autonomous healing.
    
    Monitors health check results and automatically triggers recovery
    procedures when critical failures are detected.
    """
    
    # Map health check components to recovery scenarios
    COMPONENT_SCENARIO_MAP = {
        'neo4j': ScenarioCode.NEO_001,
        'neo4j_connection': ScenarioCode.NEO_001,
        'agent': ScenarioCode.AGT_001,
        'agent_heartbeats': ScenarioCode.AGT_001,
        'signal': ScenarioCode.SIG_001,
        'signal_daemon': ScenarioCode.SIG_001,
        'task': ScenarioCode.TSK_001,
        'memory': ScenarioCode.MEM_001,
    }
    
    def __init__(
        self,
        health_orchestrator: HealthOrchestrator,
        recovery_manager: ErrorRecoveryManager,
        auto_recover: bool = True
    ):
        self.health = health_orchestrator
        self.recovery = recovery_manager
        self.auto_recover = auto_recover
        self._recovery_in_progress: Dict[str, datetime] = {}
        self._recovery_cooldown_minutes = 5  # Don't retry same recovery for 5 min
        
    async def run_health_check_with_recovery(self) -> Dict[str, Any]:
        """
        Run health checks and automatically recover from failures.
        
        Returns:
            Dict with health summary and recovery results
        """
        # Run health checks
        summary = await self.health.run_and_log()
        
        result = {
            'health_summary': summary.to_dict(),
            'recovery_actions': [],
            'auto_recovery_enabled': self.auto_recover,
        }
        
        # Check if recovery needed
        if summary.overall_status == HealthStatus.CRITICAL and self.auto_recover:
            logger.warning(f"Critical health status detected: {summary.critical_count} critical issues")
            
            # Get critical issues
            critical_issues = self.health.get_critical_issues(summary)
            
            for issue in critical_issues:
                # Check if we should attempt recovery
                if self._should_attempt_recovery(issue.component):
                    logger.info(f"Attempting autonomous recovery for: {issue.component}")
                    
                    recovery_result = await self._trigger_recovery(issue)
                    result['recovery_actions'].append(recovery_result)
                    
                    # Mark recovery as attempted
                    self._recovery_in_progress[issue.component] = datetime.utcnow()
                else:
                    logger.info(f"Recovery for {issue.component} on cooldown or disabled")
                    
        elif summary.overall_status == HealthStatus.WARNING:
            logger.warning(f"Warning health status: {summary.warning_count} warnings")
            # Could trigger preventive recovery here
            
        return result
    
    def _should_attempt_recovery(self, component: str) -> bool:
        """Check if we should attempt recovery for this component."""
        # Check cooldown
        if component in self._recovery_in_progress:
            last_attempt = self._recovery_in_progress[component]
            minutes_since = (datetime.utcnow() - last_attempt).total_seconds() / 60
            
            if minutes_since < self._recovery_cooldown_minutes:
                logger.debug(f"Recovery for {component} on cooldown ({minutes_since:.1f} min)")
                return False
                
        # Check if we have a recovery scenario for this component
        scenario = self._get_scenario_for_component(component)
        if not scenario:
            logger.debug(f"No recovery scenario for component: {component}")
            return False
            
        return True
    
    def _get_scenario_for_component(self, component: str) -> Optional[str]:
        """Map health component to recovery scenario code."""
        # Direct mapping
        if component in self.COMPONENT_SCENARIO_MAP:
            return self.COMPONENT_SCENARIO_MAP[component]
            
        # Fuzzy matching
        component_lower = component.lower()
        for key, scenario in self.COMPONENT_SCENARIO_MAP.items():
            if key in component_lower or component_lower in key:
                return scenario
                
        return None
    
    async def _trigger_recovery(self, issue) -> Dict[str, Any]:
        """Trigger appropriate recovery for a health issue."""
        component = issue.component
        scenario = self._get_scenario_for_component(component)
        
        if not scenario:
            return {
                'component': component,
                'status': 'skipped',
                'reason': 'No recovery scenario available'
            }
            
        logger.info(f"Triggering recovery for {component} using scenario {scenario}")
        
        try:
            # Execute scenario-specific recovery
            if scenario == ScenarioCode.NEO_001:
                recovery_result = await self.recovery.recover_neo4j_connection_loss()
                
            elif scenario == ScenarioCode.AGT_001:
                # Extract agent name from component if possible
                agent = self._extract_agent_from_component(component)
                recovery_result = await self.recovery.recover_agent_unresponsive(agent)
                
            elif scenario == ScenarioCode.SIG_001:
                recovery_result = await self.recovery.recover_signal_failure()
                
            elif scenario == ScenarioCode.TSK_001:
                recovery_result = await self.recovery.recover_queue_overflow()
                
            else:
                # Generic recovery
                actions = self.recovery.get_recovery_actions(scenario)
                recovery_result = {
                    'scenario': scenario,
                    'actions_available': len(actions),
                    'status': RecoveryStatus.PENDING.value,
                    'note': 'Generic recovery not yet implemented'
                }
                
            return {
                'component': component,
                'scenario': scenario,
                'status': recovery_result.get('status', 'unknown'),
                'result': recovery_result,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Recovery failed for {component}: {e}")
            return {
                'component': component,
                'scenario': scenario,
                'status': 'failed',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def _extract_agent_from_component(self, component: str) -> str:
        """Extract agent name from component string."""
        # Try to parse agent name from component
        # e.g., "agent_mongke_heartbeat" -> "mongke"
        
        parts = component.lower().split('_')
        
        # Known agent names
        agents = ['kublai', 'mongke', 'chagatai', 'temujin', 'jochi', 'ogedei', 
                  'researcher', 'writer', 'developer', 'analyst', 'ops', 'main']
        
        for agent in agents:
            if agent in parts:
                return agent
                
        # Default to main
        return 'main'
    
    async def run_continuous_monitoring(self, interval_seconds: int = 300):
        """
        Run continuous health monitoring with auto-recovery.
        
        Args:
            interval_seconds: Seconds between health checks (default: 5 min)
        """
        logger.info(f"Starting autonomous recovery monitoring (interval: {interval_seconds}s)")
        
        while True:
            try:
                result = await self.run_health_check_with_recovery()
                
                # Log summary
                health = result['health_summary']
                status = health.get('overall_status', 'unknown')
                recoveries = len(result['recovery_actions'])
                
                if recoveries > 0:
                    logger.info(f"Health: {status} | Auto-recoveries attempted: {recoveries}")
                else:
                    logger.debug(f"Health: {status} | No recovery needed")
                    
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                
            await asyncio.sleep(interval_seconds)


# Convenience function for easy setup
def create_autonomous_recovery_system(
    neo4j_uri: str = None,
    neo4j_password: str = None,
    auto_recover: bool = True
) -> AutonomousRecoverySystem:
    """
    Create and configure the autonomous recovery system.
    
    Usage:
        recovery_system = create_autonomous_recovery_system()
        
        # Run once
        result = await recovery_system.run_health_check_with_recovery()
        
        # Or run continuously
        await recovery_system.run_continuous_monitoring()
    """
    import os
    
    # Get Neo4j config from environment
    uri = neo4j_uri or os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    password = neo4j_password or os.getenv('NEO4J_PASSWORD', '')
    
    # Create components
    health_orchestrator = HealthOrchestrator(
        neo4j_uri=uri,
        neo4j_password=password
    )
    
    # Import memory for recovery manager
    try:
        from openclaw_memory import OperationalMemory
        memory = OperationalMemory()
    except ImportError:
        # Fallback - recovery manager can work without memory
        memory = None
        
    recovery_manager = ErrorRecoveryManager(memory=memory)
    
    # Create integrated system
    system = AutonomousRecoverySystem(
        health_orchestrator=health_orchestrator,
        recovery_manager=recovery_manager,
        auto_recover=auto_recover
    )
    
    return system


# CLI entry point
async def main():
    """Run autonomous recovery monitoring."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Autonomous Health Recovery System')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--interval', type=int, default=300, help='Check interval in seconds')
    parser.add_argument('--no-recovery', action='store_true', help='Disable auto-recovery')
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create system
    system = create_autonomous_recovery_system(
        auto_recover=not args.no_recovery
    )
    
    if args.once:
        # Run once
        result = await system.run_health_check_with_recovery()
        print(json.dumps(result, indent=2, default=str))
    else:
        # Run continuously
        await system.run_continuous_monitoring(interval_seconds=args.interval)


if __name__ == "__main__":
    import json
    asyncio.run(main())
