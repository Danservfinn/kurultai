import sys
sys.path.insert(0, 'tools/kurultai')
from agent_gemini_direct import temujin_gemini_direct

# Initialize Temujin with full direct access
temujin = temujin_gemini_direct()

print("="*60)
print("GEMINI CLI DEPLOYMENT TASK")
print("="*60)
print()
print("Agent: Temujin (Developer)")
print("Task: Deploy LLM Survivor to Docker")
print("Access Level: FULL (read/write/execute anywhere)")
print()

# Give comprehensive deployment task
task = """
Deploy the LLM Survivor application using Docker.

PROJECT LOCATION: ~/projects/llm_survivor/

YOUR TASK:
1. Navigate to the project directory
2. Check the current Docker configuration
3. Identify and fix any build issues
4. Build and start the containers
5. Verify the deployment works
6. Report the working URLs

FILES TO CHECK:
- docker-compose.yml
- Dockerfile.backend
- frontend/Dockerfile.frontend
- frontend/package.json
- frontend/src/ (for TypeScript errors)

COMMON ISSUES TO FIX:
- Missing dependencies in package.json
- TypeScript type errors
- PostCSS/Tailwind configuration
- Import path issues

USE YOUR TOOLS:
- read_file() to check current files
- list_directory() to explore structure
- execute() to run docker commands
- edit_file() to fix issues

Be proactive. Check files, identify problems, fix them, then deploy.
"""

print("Sending task to Temujin...")
print()

result = temujin.query(task)

print("="*60)
print("TEMUJIN'S RESPONSE")
print("="*60)
print()
print(result['response'])
print()

if result.get('tools_executed'):
    print("="*60)
    print("TOOLS EXECUTED")
    print("="*60)
    for tool in result['tools_executed']:
        print(f"  • {tool}")
    print()

if result.get('execution_log'):
    print("="*60)
    print("EXECUTION LOG")
    print("="*60)
    for entry in result['execution_log'][-5:]:
        status = "✅" if entry['success'] else "❌"
        print(f"  {status} {entry['action']}: {entry['target']}")
    print()

print("="*60)
print("DELEGATION COMPLETE")
print("="*60)
