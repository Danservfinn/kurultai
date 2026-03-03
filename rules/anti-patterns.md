# Anti-Patterns - Kublai

## What NOT to Do

### ❌ Don't Hardcode Paths
```python
# BAD
path = "/Users/kublai/.openclaw/agents/main"

# GOOD
path = os.environ.get('AGENT_WORKSPACE')
```

### ❌ Don't Ignore Errors
```python
# BAD
try:
    do_something()
except:
    pass

# GOOD
try:
    do_something()
except SpecificError as e:
    logger.error(f"Failed: {e}")
    raise
```

### ❌ Don't Use Global State
```python
# BAD
global_counter = 0

# GOOD
class Counter:
    def __init__(self):
        self.count = 0
```

### ❌ Don't Make Assumptions
- Don't assume files exist (check first)
- Don't assume APIs are available (handle failures)
- Don't assume data format (validate inputs)

### ❌ Don't Duplicate Code
- Extract common logic to functions
- Use imports from shared modules
- Keep DRY (Don't Repeat Yourself)

### ❌ Don't Over-Engineer
- Start simple, add complexity when needed
- YAGNI (You Ain't Gonna Need It)
- Premature optimization is the root of all evil
