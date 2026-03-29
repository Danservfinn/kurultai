#!/usr/bin/env python3
"""Test script for post_completion_hook.py acceptance criteria."""

from post_completion_hook import parse_followups, FollowUpDeclaration

# Test 1: Empty content returns empty list
result = parse_followups('No YAML here')
assert result == [], f'Expected empty list, got {result}'
print('✓ Test 1 passed: Empty content returns empty list')

# Test 2: Valid YAML block parsed correctly
sample = '''
## Resolution

Done.

```yaml
follow_ups:
  - title: "Test task"
    agent: temujin
    priority: high
    context: "Test context"
```
'''
result = parse_followups(sample)
assert len(result) == 1, f'Expected 1 follow-up, got {len(result)}'
assert result[0].title == 'Test task', f'Expected title="Test task", got {result[0].title}'
assert result[0].agent == 'temujin', f'Expected agent="temujin", got {result[0].agent}'
assert result[0].priority == 'high', f'Expected priority="high", got {result[0].priority}'
print('✓ Test 2 passed: Valid YAML parsed correctly')

# Test 3: Caps at 5 follow-ups
items = '\n'.join([f'  - title: "Task {i}"\n    agent: temujin' for i in range(10)])
many_followups = f'''
```yaml
follow_ups:
{items}
```
'''
result = parse_followups(many_followups)
assert len(result) == 5, f'Expected 5 follow-ups (capped), got {len(result)}'
print('✓ Test 3 passed: Caps at MAX_FOLLOWUPS=5')

print('\n✅ All acceptance criteria tests passed!')
