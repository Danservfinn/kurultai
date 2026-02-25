#!/usr/bin/env python3
"""
Self-Improvement Heartbeat Tasks
Integrate agent reflection and Kublai review into heartbeat system
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.kurultai.agent_reflection import hourly_agent_reflection_task
from tools.kurultai.kublai_review import kublai_review_task
from tools.kurultai.baseline_tracker import validate_improvements_task


class HeartbeatTask:
    """Simple heartbeat task definition."""
    def __init__(self, name, frequency_minutes, handler, 
                 offset_minutes=0, max_tokens=2000, description=""):
        self.name = name
        self.frequency_minutes = frequency_minutes
        self.handler = handler
        self.offset_minutes = offset_minutes
        self.max_tokens = max_tokens
        self.description = description


# Self-improvement task registry
SELF_IMPROVEMENT_TASKS = [
    HeartbeatTask(
        name="agent_reflection",
        frequency_minutes=60,
        handler=hourly_agent_reflection_task,
        offset_minutes=0,
        max_tokens=3000,
        description="One agent reflects per hour (round-robin)"
    ),
    
    HeartbeatTask(
        name="kublai_review",
        frequency_minutes=60,
        handler=kublai_review_task,
        offset_minutes=10,  # Run 10 min after reflection
        max_tokens=4000,
        description="Kublai reviews pending proposals with full context"
    ),
    
    HeartbeatTask(
        name="validate_improvements",
        frequency_minutes=60,
        handler=validate_improvements_task,
        offset_minutes=30,  # Run 30 min after hour
        max_tokens=1500,
        description="Validate improvements after 24h measurement"
    )
]


async def run_all_tasks():
    """Run all self-improvement tasks (for testing)."""
    print("🔄 Running all self-improvement tasks...\n")
    
    for task in SELF_IMPROVEMENT_TASKS:
        print(f"▶️  {task.name}: {task.description}")
        try:
            result = await task.handler()
            print(f"   Result: {result}\n")
        except Exception as e:
            print(f"   ❌ Error: {e}\n")


if __name__ == "__main__":
    # Test all tasks
    asyncio.run(run_all_tasks())
