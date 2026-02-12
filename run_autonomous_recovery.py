#!/usr/bin/env python3
"""
Autonomous Recovery Runner

Starts the autonomous health monitoring and recovery system.
This script integrates health checks with automatic failure recovery.

Usage:
    python3 run_autonomous_recovery.py
    python3 run_autonomous_recovery.py --daemon
    python3 run_autonomous_recovery.py --once
"""

import os
import sys
import asyncio
import logging
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from tools.kurultai.health_recovery_integration import (
    create_autonomous_recovery_system,
    AutonomousRecoverySystem
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/autonomous_recovery.log')
    ]
)

logger = logging.getLogger(__name__)


async def run_recovery_system(args):
    """Run the autonomous recovery system."""
    
    logger.info("=" * 60)
    logger.info("Autonomous Recovery System Starting")
    logger.info("=" * 60)
    
    # Create the integrated system
    system = create_autonomous_recovery_system(
        auto_recover=not args.no_recovery
    )
    
    logger.info(f"Auto-recovery enabled: {not args.no_recovery}")
    logger.info(f"Check interval: {args.interval} seconds")
    
    if args.once:
        # Run single check
        logger.info("Running single health check with recovery...")
        result = await system.run_health_check_with_recovery()
        
        # Print results
        health = result['health_summary']
        recoveries = result['recovery_actions']
        
        print("\n" + "=" * 60)
        print("HEALTH CHECK RESULT")
        print("=" * 60)
        print(f"Overall Status: {health.get('overall_status', 'unknown').upper()}")
        print(f"Healthy: {health.get('healthy_count', 0)}/{health.get('total_count', 0)}")
        print(f"Warnings: {health.get('warning_count', 0)}")
        print(f"Critical: {health.get('critical_count', 0)}")
        print(f"Recovery Actions: {len(recoveries)}")
        
        for action in recoveries:
            print(f"\n  - {action.get('component')}: {action.get('status')}")
            if action.get('error'):
                print(f"    Error: {action.get('error')}")
        
        print("=" * 60)
        
        # Exit with appropriate code
        if health.get('critical_count', 0) > 0:
            sys.exit(1)
        sys.exit(0)
        
    else:
        # Run as daemon
        logger.info("Starting continuous monitoring...")
        logger.info("Press Ctrl+C to stop")
        
        try:
            await system.run_continuous_monitoring(interval_seconds=args.interval)
        except KeyboardInterrupt:
            logger.info("\nShutdown requested by user")
            logger.info("Autonomous recovery system stopped")


def main():
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(
        description='Autonomous Health Monitoring and Recovery System'
    )
    parser.add_argument(
        '--once', 
        action='store_true',
        help='Run single check and exit (default: continuous daemon)'
    )
    parser.add_argument(
        '--interval', 
        type=int, 
        default=300,
        help='Check interval in seconds (default: 300 = 5 min)'
    )
    parser.add_argument(
        '--no-recovery',
        action='store_true',
        help='Disable automatic recovery (detection only)'
    )
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run as daemon (continuous monitoring)'
    )
    
    args = parser.parse_args()
    
    # Run
    try:
        asyncio.run(run_recovery_system(args))
    except Exception as e:
        logger.exception("Fatal error in recovery system")
        sys.exit(1)


if __name__ == "__main__":
    main()
