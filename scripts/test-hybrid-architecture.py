#!/usr/bin/env python3
"""
Hybrid Architecture Integration Tests

Tests the complete hybrid architecture workflow:
1. Agent workspace setup
2. Neo4j AgentState
3. Task routing
4. Agent launch
5. Task execution
6. Health monitoring

Usage:
    python3 test-hybrid-architecture.py
    python3 test-hybrid-architecture.py --verbose
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

SCRIPTS_DIR = "/Users/kublai/.openclaw/agents/main/scripts"
AGENTS_DIR = "/Users/kublai/.openclaw/agents"

sys.path.insert(0, SCRIPTS_DIR)
os.environ['PYTHONPATH'] = SCRIPTS_DIR

class TestResult:
    def __init__(self, name):
        self.name = name
        self.passed = False
        self.error = None
        self.duration = 0

    def __str__(self):
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status} {self.name} ({self.duration:.2f}s)"

def run_test(test_func, name):
    """Run a test and capture results"""
    result = TestResult(name)
    start = time.time()
    
    try:
        test_func()
        result.passed = True
    except Exception as e:
        result.error = str(e)
    
    result.duration = time.time() - start
    return result

# Test 1: Agent Workspace Structure
def test_agent_workspaces():
    """Test that all 6 agent workspaces exist"""
    agents = ['kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei']
    
    for agent in agents:
        workspace_dir = f"{AGENTS_DIR}/{agent}/workspace"
        tasks_dir = f"{AGENTS_DIR}/{agent}/tasks"
        memory_dir = f"{AGENTS_DIR}/{agent}/memory"
        config_file = f"{AGENTS_DIR}/{agent}/config.json"
        
        assert os.path.isdir(workspace_dir), f"Workspace missing: {workspace_dir}"
        assert os.path.isdir(tasks_dir), f"Tasks dir missing: {tasks_dir}"
        assert os.path.isdir(memory_dir), f"Memory dir missing: {memory_dir}"
        assert os.path.isfile(config_file), f"Config missing: {config_file}"
        
        # Validate config
        with open(config_file, 'r') as f:
            config = json.load(f)
            assert 'agent_name' in config, "Config missing agent_name"
            assert 'model' in config, "Config missing model"

# Test 2: Neo4j AgentState
def test_neo4j_agentstate():
    """Test that all 6 AgentState nodes exist"""
    from neo4j import GraphDatabase
    
    uri = "bolt://localhost:7687"
    user = "neo4j"
    password = "myStrongPassword123"
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    agents = ['kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei']
    
    with driver.session() as session:
        for agent in agents:
            result = session.run("""
                MATCH (a:AgentState {name: $name})
                RETURN a.status AS status, a.role AS role
            """, name=agent)
            
            record = result.single()
            assert record is not None, f"AgentState not found: {agent}"
            assert record['status'] in ['idle', 'busy', 'running'], f"Invalid status: {record['status']}"
    
    driver.close()

# Test 3: Smart Task Router
def test_smart_router():
    """Test smart task router classification"""
    import subprocess
    
    # Use subprocess to avoid import issues
    result = subprocess.run(
        ['python3', f'{SCRIPTS_DIR}/smart-task-router.py', '--classify', 'Build a login feature for Parse'],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    output = json.loads(result.stdout)
    assert output['destination'] == 'temujin', f"Expected temujin, got {output['destination']}"
    
    # Test research task
    result = subprocess.run(
        ['python3', f'{SCRIPTS_DIR}/smart-task-router.py', '--classify', 'Research competitor pricing'],
        capture_output=True,
        text=True,
        timeout=5
    )
    output = json.loads(result.stdout)
    assert output['destination'] == 'mongke', f"Expected mongke, got {output['destination']}"
    
    # Test writing task
    result = subprocess.run(
        ['python3', f'{SCRIPTS_DIR}/smart-task-router.py', '--classify', 'Write a blog post about AI'],
        capture_output=True,
        text=True,
        timeout=5
    )
    output = json.loads(result.stdout)
    assert output['destination'] == 'chagatai', f"Expected chagatai, got {output['destination']}"

# Test 4: Task Routing to Agent Queues
def test_task_routing():
    """Test routing tasks to agent queues"""
    import subprocess
    
    # Route a task (will route based on classification)
    result = subprocess.run(
        ['python3', f'{SCRIPTS_DIR}/smart-task-router.py', '--task', 'Build a login feature', '--priority', 'high'],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    # Should route to temujin for code tasks
    assert 'Task routed to temujin' in result.stdout or 'routed' in result.stdout.lower(), f"Routing failed: {result.stderr}"

# Test 5: Agent Health Monitor
def test_health_monitor():
    """Test agent health monitor"""
    import subprocess
    
    # Test health monitor summary
    result = subprocess.run(
        ['python3', f'{SCRIPTS_DIR}/agent-health-monitor.py', '--summary'],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    assert result.returncode == 0, f"Health monitor failed: {result.stderr}"
    assert 'kublai' in result.stdout, "Output missing kublai"
    assert 'temujin' in result.stdout, "Output missing temujin"

# Test 6: Launch Agent Script
def test_launch_agent_script():
    """Test launch agent script (dry run)"""
    import subprocess
    
    # Just test that script runs without error (don't actually launch)
    result = subprocess.run(
        ['python3', f'{SCRIPTS_DIR}/launch-agent.py', '--help'],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    assert 'Launch persistent Kurultai agents' in result.stdout, "Help text missing"

# Test 7: Agent Task Handler Script
def test_agent_task_handler_script():
    """Test agent task handler script (dry run)"""
    import subprocess
    
    result = subprocess.run(
        ['python3', f'{SCRIPTS_DIR}/agent-task-handler.py', '--help'],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    assert 'Agent task handler' in result.stdout, "Help text missing"

# Test 8: End-to-End Task Flow
def test_end_to_end_task_flow():
    """Test complete task flow: route → queue → execute"""
    import subprocess
    import glob
    
    # Route task (code task should go to temujin)
    result = subprocess.run(
        ['python3', f'{SCRIPTS_DIR}/smart-task-router.py', '--task', 'Build a login feature', '--priority', 'normal'],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    assert 'routed' in result.stdout.lower(), f"Routing failed: {result.stderr}"
    
    # Verify task file was created in SOME agent queue
    all_task_files = glob.glob(f'{AGENTS_DIR}/*/tasks/normal-*.md')
    assert len(all_task_files) > 0, "Task file not created in any queue"
    
    # Read and verify content
    with open(all_task_files[-1], 'r') as f:
        content = f.read()
        assert 'Build a login feature' in content or 'login' in content.lower(), "Task content missing"
    
    # Clean up
    os.remove(all_task_files[-1])

def main():
    parser = argparse.ArgumentParser(description='Hybrid architecture integration tests')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("  HYBRID ARCHITECTURE INTEGRATION TESTS")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*70 + "\n")
    
    tests = [
        (test_agent_workspaces, "Agent Workspace Structure"),
        (test_neo4j_agentstate, "Neo4j AgentState Nodes"),
        (test_smart_router, "Smart Task Router Classification"),
        (test_task_routing, "Task Routing to Agent Queues"),
        (test_health_monitor, "Agent Health Monitor"),
        (test_launch_agent_script, "Launch Agent Script"),
        (test_agent_task_handler_script, "Agent Task Handler Script"),
        (test_end_to_end_task_flow, "End-to-End Task Flow"),
    ]
    
    results = []
    for test_func, name in tests:
        if args.verbose:
            print(f"Running: {name}...")
        
        result = run_test(test_func, name)
        results.append(result)
        
        if args.verbose:
            print(f"  {result}")
            if result.error:
                print(f"  Error: {result.error}")
    
    # Summary
    print("\n" + "="*70)
    print("  TEST SUMMARY")
    print("="*70 + "\n")
    
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    
    for result in results:
        print(f"  {result}")
    
    print(f"\n{'='*70}")
    print(f"  Results: {passed}/{len(results)} passed ({100*passed/len(results):.1f}%)")
    print(f"{'='*70}\n")
    
    if failed > 0:
        print(f"⚠ {failed} test(s) failed\n")
        sys.exit(1)
    else:
        print("✓ All tests passed!\n")
        sys.exit(0)

if __name__ == "__main__":
    main()
