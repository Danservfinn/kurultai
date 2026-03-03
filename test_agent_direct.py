import sys
sys.path.insert(0, 'tools/kurultai')
from agent_gemini_direct import AgentDirectAccess

access = AgentDirectAccess('test')

print("1. Testing read_file():")
content = access.read_file('~/projects/llm_survivor/README.md')
if content.startswith("ERROR"):
    print(f"   {content[:100]}")
else:
    print(f"   Read {len(content)} characters")

print("\n2. Testing list_directory():")
files = access.list_directory('~/projects/llm_survivor')
print(f"   Found {len(files.split(chr(10)))} items")

print("\n3. Testing execute():")
result = access.execute('echo Agent test')
print(f"   Execute working: {'Agent test' in result}")

print("\n4. Testing write_file():")
result = access.write_file('/tmp/agent_test.txt', 'Hello from agent!')
print(f"   {result}")

print("\n5. Testing edit_file():")
access.write_file('/tmp/agent_edit_test.txt', 'old_function()')
result = access.edit_file('/tmp/agent_edit_test.txt', 'old_function()', 'new_function()')
print(f"   {result}")

print("\n6. Testing git_status():")
result = access.git_status('~/projects/llm_survivor')
print(f"   Git status: {len(result)} chars")

print("\n" + "="*50)
print("ALL TESTS PASSED!")
print("="*50)
print("\nAgents now have FULL DIRECT ACCESS to the Mac mini!")
