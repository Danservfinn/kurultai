#!/usr/bin/env python3
"""
Kurultai Task Scheduler

Executes background tasks from TASK_REGISTRY at their defined frequencies.
Runs continuously, tracks last execution times, and spawns agents to execute tasks.

Usage:
    python task_scheduler.py              # Run scheduler loop
    python task_scheduler.py --once       # Run one check cycle
    python task_scheduler.py --daemon     # Run as daemon
"""

import os
import sys
import time
import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

sys.path.insert(0, os.path.dirname(__file__))
from kurultai.agent_tasks import TASK_REGISTRY, run_task

# Track last execution times
STATE_FILE = "/tmp/task_scheduler_state.json"


@dataclass
class TaskState:
    """Track task execution state."""
    task_name: str
    last_run: Optional[str] = None
    run_count: int = 0
    error_count: int = 0
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "TaskState":
        return cls(**data)


class TaskScheduler:
    """Schedules and executes background tasks."""
    
    def __init__(self, check_interval: int = 60):
        self.check_interval = check_interval
        self.states: Dict[str, TaskState] = {}
        self.running = False
        self.load_state()
    
    def load_state(self):
        """Load persisted state."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    for name, state_data in data.items():
                        self.states[name] = TaskState.from_dict(state_data)
                print(f"📂 Loaded state for {len(self.states)} tasks")
            except Exception as e:
                print(f"⚠️ Could not load state: {e}")
    
    def save_state(self):
        """Persist state to disk."""
        try:
            data = {name: state.to_dict() for name, state in self.states.items()}
            with open(STATE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save state: {e}")
    
    def is_task_due(self, task_name: str, frequency_minutes: int) -> bool:
        """Check if a task is due to run."""
        if task_name not in self.states:
            # Never run before - initialize
            self.states[task_name] = TaskState(task_name=task_name)
            return True
        
        state = self.states[task_name]
        if not state.last_run:
            return True
        
        last_run = datetime.fromisoformat(state.last_run)
        next_run = last_run + timedelta(minutes=frequency_minutes)
        
        return datetime.now() >= next_run
    
    def get_due_tasks(self) -> List[tuple]:
        """Get list of tasks that are due to run."""
        due = []
        for task_name, config in TASK_REGISTRY.items():
            freq = config.get('freq', 60)  # Default 60 min
            if self.is_task_due(task_name, freq):
                due.append((task_name, config))
        return due
    
    def execute_task(self, task_name: str) -> Dict:
        """Execute a single task."""
        print(f"\n🔧 Executing: {task_name}")
        start_time = datetime.now()
        
        try:
            result = run_task(task_name)
            duration = (datetime.now() - start_time).total_seconds()
            
            # Update state
            if task_name not in self.states:
                self.states[task_name] = TaskState(task_name=task_name)
            
            state = self.states[task_name]
            state.last_run = datetime.now().isoformat()
            state.run_count += 1
            
            if result.get('status') == 'error':
                state.error_count += 1
                print(f"  ❌ Failed: {result.get('error', 'Unknown error')}")
            else:
                print(f"  ✅ Completed in {duration:.1f}s")
            
            return result
            
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            if task_name in self.states:
                self.states[task_name].error_count += 1
            return {'status': 'error', 'error': str(e)}
    
    def run_once(self):
        """Run one check cycle."""
        due_tasks = self.get_due_tasks()
        
        if not due_tasks:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] No tasks due")
            return
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Running {len(due_tasks)} due tasks...")
        
        for task_name, config in due_tasks:
            agent = config.get('agent', 'unknown')
            freq = config.get('freq', 60)
            print(f"\n  📋 {task_name} (agent: {agent}, freq: {freq}m)")
            self.execute_task(task_name)
        
        self.save_state()
        print(f"\n✅ Cycle complete. Saved state.")
    
    def run_continuous(self):
        """Run scheduler continuously."""
        print(f"🚀 Task Scheduler started")
        print(f"   Check interval: {self.check_interval}s")
        print(f"   Tasks registered: {len(TASK_REGISTRY)}")
        print(f"   Press Ctrl+C to stop\n")
        
        self.running = True
        
        try:
            while self.running:
                self.run_once()
                
                # Sleep with interrupt handling
                for _ in range(self.check_interval):
                    if not self.running:
                        break
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping scheduler...")
        finally:
            self.save_state()
            print("💾 State saved. Goodbye!")
    
    def stop(self):
        """Stop the scheduler."""
        self.running = False
    
    def get_status(self) -> Dict:
        """Get current scheduler status."""
        return {
            'running': self.running,
            'tasks_registered': len(TASK_REGISTRY),
            'tasks_tracked': len(self.states),
            'check_interval': self.check_interval,
            'next_tasks': [
                {
                    'name': name,
                    'agent': config['agent'],
                    'freq': config['freq'],
                    'last_run': self.states.get(name, TaskState(name)).last_run
                }
                for name, config in TASK_REGISTRY.items()
            ]
        }


def main():
    parser = argparse.ArgumentParser(description='Kurultai Task Scheduler')
    parser.add_argument('--once', action='store_true', help='Run one cycle and exit')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    parser.add_argument('--interval', type=int, default=60, help='Check interval in seconds (default: 60)')
    parser.add_argument('--status', action='store_true', help='Show status and exit')
    args = parser.parse_args()
    
    scheduler = TaskScheduler(check_interval=args.interval)
    
    if args.status:
        status = scheduler.get_status()
        print(json.dumps(status, indent=2))
        return
    
    if args.once:
        scheduler.run_once()
    else:
        scheduler.run_continuous()


if __name__ == '__main__':
    main()
