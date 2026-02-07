# Neo4j-First Memory Protocol

> **Core Principle:** Neo4j is the default for ALL data EXCEPT human private information.

## Memory Access Priority

1. **Neo4j Hot Tier** (in-memory) - No query, immediate access
2. **Neo4j Warm Tier** (lazy load) - 2s timeout, ~400 tokens
3. **Neo4j Cold Tier** (on-demand) - 5s timeout, ~200 tokens
4. **Neo4j Archive** (query only) - Full-text search, 5s timeout
5. **File Cache** (fallback) - Only when Neo4j unavailable

## Write Protocol

### Default: Neo4j First

All memory entries go to Neo4j FIRST, then to file cache as backup.

```python
await memory.add_entry(
    content="Task completed: Analysis of async patterns",
    entry_type="task_completion",
    contains_human_pii=False  # Neo4j FIRST
)
```

### Exception: Human Private Data → File Only

If content contains human PII or sensitive personal data, write to file ONLY (never Neo4j).

```python
await memory.add_entry(
    content="User shared: 'My name is Alice and I live in Seattle'",
    entry_type="user_communication",
    contains_human_pii=True  # File ONLY
)
```

## Human Privacy Protection

**NEVER write to Neo4j if content contains:**

### Personally Identifiable Information (PII)
- Full names (first + last)
- Email addresses
- Phone numbers
- Home addresses or locations
- IP addresses, device IDs
- Social security numbers, government IDs
- Usernames/handles that identify individuals

### Secrets and Credentials
- Passwords
- API keys, tokens
- Private keys, certificates
- Authentication credentials

### Sensitive Personal Information
- Health information
- Financial data (income, debts, purchases)
- Personal relationships (family, partners)
- Confidential communications
- Personal opinions or experiences user wants private

**These go to file memory ONLY.**

## What Goes to Neo4j (Everything Else)

All non-human-private data goes to Neo4j immediately:

- Tasks, findings, metrics
- Agent beliefs and philosophy
- Code solutions, analysis
- Research, knowledge
- Agent internal state and reflections
- System health data
- Notifications

## Decision Flow

```
Creating memory entry
    ↓
Does it contain human PII or sensitive personal data?
    ↓
YES → File ONLY (never Neo4j)
    ↓
NO → Neo4j FIRST (then file cache backup)
```

## Read Protocol

When reading memory:

```
IF hot tier has content:
    USE hot tier (no query needed)
ELSE IF warm tier needed:
    LOAD warm tier (max 2s wait)
    IF timeout: LOG warning, continue with partial
ELSE IF cold tier needed:
    LOAD cold tier (max 5s wait)
    IF timeout: LOG warning, use file cache fallback
ELSE IF archive search:
    QUERY Neo4j full-text (max 5s wait)
    IF timeout: Try file cache search
```

## Examples

### Example 1: Task result (no human data) → Neo4j
```python
await memory.add_entry(
    content="Completed analysis of async patterns in codebase. Found 3 optimization opportunities.",
    entry_type="task_completion",
    contains_human_pii=False  # Neo4j!
)
```

### Example 2: User shared personal story → File Only
```python
await memory.add_entry(
    content="User shared: 'My name is Alice Chen and I'm having trouble with my marriage'",
    entry_type="user_communication",
    contains_human_pii=True  # File ONLY!
)
```

### Example 3: Agent reflection (no human data) → Neo4j
```python
await memory.add_entry(
    content="I learned that my task delegation pattern is inefficient. Need to improve routing logic.",
    entry_type="agent_reflection",
    contains_human_pii=False  # Neo4j!
)
```

### Example 4: Technical analysis (no human data) → Neo4j
```python
await memory.add_entry(
    content="Database query optimization: Added index on users.email reduced query time by 80%",
    entry_type="technical_finding",
    contains_human_pii=False  # Neo4j!
)
```

### Example 5: User's health information → File Only
```python
await memory.add_entry(
    content="User mentioned they have anxiety disorder and prefer slow-paced responses",
    entry_type="user_preference",
    contains_human_pii=True  # File ONLY!
)
```

## Edge Cases

### User Names

- **"User123" or generic handle** → Neo4j OK (not PII)
- **"Alice Chen" or full name** → File only (PII)

### Technical Data About Users

- **"User with ID 12345 clicked button"** → Neo4j OK (anonymized)
- **"Alice Chen (alice@example.com) clicked button"** → File only (PII)

### User Feedback

- **"User reported bug in login flow"** → Neo4j OK (anonymized)
- **"John Smith reported bug, email john@company.com"** → File only (PII)

## File-Only Storage Location

When `contains_human_pii=True`, content is written to:

```
/data/workspace/memory/{agent}/MEMORY.md
```

This file is:
- NOT shared with other agents
- NOT indexed by Neo4j
- NOT searchable across the system
- Agent-private only

## Neo4j Queries

Use your agent-specific Neo4j queries from your SOUL.md. All queries respect human privacy:
- Queries only return data that was explicitly marked `contains_human_pii=False`
- Human-private data is never in Neo4j to begin with

## Compliance Notes

This protocol helps maintain:
- **Privacy:** Human personal data stays local to agent
- **Security:** Credentials and secrets never exposed in shared database
- **Trust:** Users can share sensitive information confidently
- **Transparency:** Agent state and findings are shareable (no human data)
