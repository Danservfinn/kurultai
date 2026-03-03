# Code Style Rules - Kublai

## Naming Conventions
- **Variables:** snake_case (e.g., task_id, agent_name)
- **Functions:** snake_case (e.g., process_task, check_status)
- **Constants:** UPPER_CASE (e.g., MAX_RETRIES, DEFAULT_TIMEOUT)
- **Files:** lowercase with hyphens (e.g., hourly-reflection.sh)

## Code Organization
- Functions under 50 lines
- One responsibility per function
- Early returns over nested conditionals
- Docstrings for all public functions

## Commenting
- Comment WHY, not WHAT
- Document assumptions
- Note edge cases
- Include examples for complex logic

## Error Handling
- Try/except for all external calls
- Log errors with context
- Fail gracefully with helpful messages
- Never silently swallow exceptions

## Formatting
- Use 4 spaces for indentation (Python)
- Use 2 spaces for indentation (Bash)
- Max line length: 100 characters
- Empty lines between logical blocks
