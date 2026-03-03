# Architecture Rules - Kublai

## Tech Stack
- **Language:** Python 3.9+, Bash
- **Runtime:** OpenClaw Gateway
- **Memory:** Neo4j (bolt://localhost:7687)
- **File Structure:** Modular, organized by concern

## Architecture Patterns
- Use modular file structure (rules/, skills/, memory/)
- Keep configuration separate from logic
- Use environment variables for secrets
- Log all operations to Neo4j and files

## Directory Structure
```
/Users/kublai/.openclaw/agents/main/
├── rules/          # Modular rules files
├── skills/         # Executable skills
├── memory/         # Daily reflections
├── scripts/        # Automation scripts
└── *.md           # Core identity files
```

## Design Principles
- Separation of concerns
- Single responsibility per module
- Explicit dependencies
- Fail-fast error handling
