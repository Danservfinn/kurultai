#!/usr/bin/env python3
"""
Demo: Agent with Full Direct Access
Shows how agents can now read/write/execute anywhere on the system.
"""

import sys
sys.path.insert(0, 'tools/kurultai')
from agent_gemini_direct import temujin_gemini_direct

def demo():
    print("="*60)
    print("AGENT FULL DIRECT ACCESS DEMO")
    print("="*60)
    print()
    print("This demonstrates Temujin (developer agent) with full access")
    print("to the Mac mini file system.")
    print()
    
    # Initialize agent
    print("1. Initializing Temujin agent...")
    temujin = temujin_gemini_direct()
    print("   ✅ Agent ready")
    print()
    
    # Example task: Analyze and fix a file
    print("2. Giving agent a task...")
    print("   Task: Analyze the LLM Survivor database.py file")
    print()
    
    # Agent can now directly read files
    result = temujin.access.read_file('~/projects/llm_survivor/backend/database.py')
    print(f"3. Agent read database.py: {len(result)} characters")
    print("   (First 200 chars):")
    print("   " + result[:200].replace('\n', '\n   '))
    print()
    
    # Agent can list directories
    files = temujin.access.list_directory('~/projects/llm_survivor/backend')
    print("4. Agent listed backend directory:")
    for line in files.split('\n')[:5]:
        print(f"   {line}")
    print()
    
    # Agent can execute commands
    result = temujin.access.execute('find ~/projects/llm_survivor -name "*.py" | wc -l')
    print("5. Agent counted Python files:")
    print("   " + result.split('\n')[-1])
    print()
    
    # Show execution log
    print("6. Execution log:")
    for entry in temujin.access.get_execution_log()[-3:]:
        status = "✅" if entry['success'] else "❌"
        print(f"   {status} {entry['action']}: {entry['target']}")
    print()
    
    print("="*60)
    print("DEMO COMPLETE")
    print("="*60)
    print()
    print("Agents now have FULL DIRECT ACCESS to:")
    print("  ✅ Read any file on the system")
    print("  ✅ Write to any location")
    print("  ✅ Execute any command")
    print("  ✅ Edit files directly")
    print("  ✅ Use git")
    print()
    print("Example usage:")
    print('  temujin = temujin_gemini_direct()')
    print('  result = temujin.query("Fix the bug in database.py")')
    print('  # Agent reads, edits, tests, and commits automatically')
    print()

if __name__ == "__main__":
    demo()
