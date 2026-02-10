#!/usr/bin/env python3
"""
Kurultai Production Test Suite
Validates all 15 background tasks and v2.0 modules
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from kurultai.agent_tasks import TASK_REGISTRY, run_task

def test_all_tasks():
    """Test all 15 background tasks."""
    print("Testing all 15 background tasks...")
    
    results = {}
    for task_name in TASK_REGISTRY.keys():
        print(f"  Testing {task_name}...", end=" ")
        try:
            result = run_task(task_name)
            status = result.get('status', 'unknown')
            results[task_name] = status
            print(f"✅ {status}")
        except Exception as e:
            results[task_name] = f"error: {e}"
            print(f"❌ error")
    
    # Summary
    success = sum(1 for r in results.values() if r == 'success')
    print(f"
Results: {success}/{len(results)} tasks successful")
    return results

def test_v2_modules():
    """Test v2.0 module imports."""
    print("
Testing v2.0 modules...")
    
    modules = [
        ('dynamic_task_generator', 'Dynamic Task Generator'),
        ('agent_collaboration', 'Agent Collaboration'),
        ('cost_monitor', 'Cost Monitor'),
        ('workspace_curator', 'Workspace Curator'),
        ('context_aware_router', 'Context-Aware Router')
    ]
    
    results = {}
    for module, name in modules:
        try:
            __import__(module)
            results[name] = 'imported'
            print(f"  ✅ {name}")
        except Exception as e:
            results[name] = f'failed: {e}'
            print(f"  ❌ {name}")
    
    return results

if __name__ == '__main__':
    print("=" * 60)
    print("KURULTAI PRODUCTION TEST SUITE")
    print("=" * 60)
    
    task_results = test_all_tasks()
    module_results = test_v2_modules()
    
    print("
" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
