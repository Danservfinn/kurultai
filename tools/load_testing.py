#!/usr/bin/env python3
"""
Load Testing for Kurultai v4.0 Async System

Tests queue throughput, worker scaling, and system stability.
"""

import time
import asyncio
import random
from datetime import datetime
from typing import List, Dict

from redis import Redis
from rq import Queue
from neo4j import GraphDatabase


class LoadTester:
    """Load testing suite for Kurultai."""
    
    def __init__(self):
        self.redis = Redis()
        self.queue = Queue('kurultai-tasks', connection=self.redis)
        self.results: List[Dict] = []
    
    def generate_test_tasks(self, count: int = 100) -> List[str]:
        """Generate test tasks for load testing."""
        job_ids = []
        
        for i in range(count):
            # Simulate different task types
            task_type = random.choice(['quick', 'medium', 'slow'])
            
            if task_type == 'quick':
                # Fast task (~100ms)
                job = self.queue.enqueue(
                    'tools.load_test_tasks.quick_task',
                    job_id=f"test-quick-{i}",
                    job_timeout='1m'
                )
            elif task_type == 'medium':
                # Medium task (~1s)
                job = self.queue.enqueue(
                    'tools.load_test_tasks.medium_task',
                    job_id=f"test-medium-{i}",
                    job_timeout='2m'
                )
            else:
                # Slow task (~5s)
                job = self.queue.enqueue(
                    'tools.load_test_tasks.slow_task',
                    job_id=f"test-slow-{i}",
                    job_timeout='5m'
                )
            
            job_ids.append(job.id)
        
        return job_ids
    
    def run_load_test(self, task_count: int = 100, max_wait: int = 300) -> Dict:
        """
        Run load test and measure throughput.
        
        Args:
            task_count: Number of tasks to enqueue
            max_wait: Maximum seconds to wait for completion
        
        Returns:
            Test results
        """
        print(f"🚀 Load Test: {task_count} tasks")
        print("=" * 50)
        
        # Clear queue first
        self.queue.empty()
        
        # Record start
        start_time = time.time()
        
        # Enqueue tasks
        print(f"Enqueuing {task_count} tasks...")
        job_ids = self.generate_test_tasks(task_count)
        enqueue_time = time.time() - start_time
        
        print(f"✅ Enqueued in {enqueue_time:.2f}s ({task_count/enqueue_time:.1f} tasks/sec)")
        
        # Wait for completion
        print(f"Waiting up to {max_wait}s for completion...")
        completed = 0
        failed = 0
        
        check_interval = 5
        elapsed = 0
        
        while elapsed < max_wait:
            time.sleep(check_interval)
            elapsed += check_interval
            
            # Check status
            queue_count = self.queue.count
            started = len(self.queue.started_job_registry)
            failed_now = len(self.queue.failed_job_registry)
            finished = len(self.queue.finished_job_registry)
            
            completed = finished + failed_now
            failed = failed_now
            
            print(f"  [{elapsed}s] Queue: {queue_count}, Started: {started}, "
                  f"Finished: {finished}, Failed: {failed_now}")
            
            if completed >= task_count:
                break
        
        total_time = time.time() - start_time
        
        # Calculate throughput
        throughput = completed / total_time if total_time > 0 else 0
        
        results = {
            "test_date": datetime.now().isoformat(),
            "tasks_enqueued": task_count,
            "tasks_completed": completed,
            "tasks_failed": failed,
            "enqueue_time_seconds": enqueue_time,
            "total_time_seconds": total_time,
            "throughput_tasks_per_second": throughput,
            "avg_time_per_task": total_time / completed if completed > 0 else 0
        }
        
        print("\n" + "=" * 50)
        print("📊 RESULTS")
        print("=" * 50)
        print(f"Tasks: {completed}/{task_count} completed ({failed} failed)")
        print(f"Total time: {total_time:.2f}s")
        print(f"Throughput: {throughput:.2f} tasks/sec")
        print(f"Avg time/task: {results['avg_time_per_task']:.3f}s")
        
        return results


# Test task functions
def quick_task():
    """Fast test task (~100ms)."""
    time.sleep(0.1)
    return {"status": "ok", "duration": "100ms"}


def medium_task():
    """Medium test task (~1s)."""
    time.sleep(1.0)
    return {"status": "ok", "duration": "1s"}


def slow_task():
    """Slow test task (~5s)."""
    time.sleep(5.0)
    return {"status": "ok", "duration": "5s"}


if __name__ == "__main__":
    print("Kurultai v4.0 Load Testing")
    print("==========================\n")
    
    tester = LoadTester()
    
    # Small test first
    print("\n🔬 Small Test (10 tasks)")
    results_small = tester.run_load_test(task_count=10, max_wait=60)
    
    # Medium test
    print("\n🔬 Medium Test (50 tasks)")
    results_medium = tester.run_load_test(task_count=50, max_wait=120)
    
    # Large test (if previous succeeded)
    if results_medium['tasks_failed'] == 0:
        print("\n🔬 Large Test (100 tasks)")
        results_large = tester.run_load_test(task_count=100, max_wait=300)
    
    print("\n✅ Load testing complete")
