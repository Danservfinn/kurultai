---
title: Kurultai CLI Commands Reference
link: kurultai-commands
type: cheatsheets
tags: [cli, commands, reference, kurultai]
ontological_relations:
  - relates_to: [[kurultai-project-overview]]
uuid: 550e8400-e29b-41d4-a716-446655440003
created_at: 2026-02-07T12:00:00Z
updated_at: 2026-02-07T12:00:00Z
---

# Kurultai CLI Commands Reference

## Railway Commands

### Project Management
```bash
# Link to Railway project
railway link -p <project-id> -s <service-name> -e <environment>

# List services
railway services

# View logs
railway logs

# Deploy
railway up
railway deploy
```

### Custom Domains
```bash
# Add custom domain
railway domain add kublai.kurult.ai

# List domains
railway domain

# Remove domain (careful!)
railway domain rm <domain-id>
```

### Variables
```bash
# List variables
railway variables

# Get variable value (JSON output)
railway variables --json

# Set variable
railway variable set KEY=value

# Link variable from service
railway variable link KEY <service-name>
```

## Docker Commands

### Development
```bash
# Build and run all services
docker-compose up --build

# Run specific service
docker-compose up moltbot

# View logs
docker-compose logs -f moltbot

# Stop all
docker-compose down
```

## Testing Commands

### Pytest
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/integration/test_agent_messaging.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run performance benchmarks
pytest tests/performance/test_benchmarks.py --benchmark-json=output.json

# Run interactive tests
python tests/interactive/run_interactive_tests.py list
python tests/interactive/run_interactive_tests.py run <scenario-index>
```

### Jochi Test Orchestrator
```bash
# Run test orchestrator
python tools/kurultai/test_runner_orchestrator.py

# Schedule: Smoke tests every 15min, full tests hourly
```

## OpenClaw Commands

### Health Check
```bash
# Check gateway health
curl -f http://localhost:18789/health

# Test WebSocket connection
wscat -c ws://localhost:18789
```

### Configuration
```bash
# View OpenClaw config
cat /data/.openclaw/openclaw.json5

# Test gateway in dev mode
node dist/index.js gateway --bind lan --port 18789 --allow-unconfigured
```

## Neo4j Commands

### Cypher Queries
```bash
# Connect to Neo4j
cypher-shell -u neo4j -p password

# Quick query
echo "MATCH (n) RETURN count(n)" | cypher-shell -u neo4j -p password
```

## Git Workflow

### Commits
```bash
# Standard commit format
git commit -m "feat: add feature description"

# Sign-off (for ship-it)
git commit -m "feat: description" -m "Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

## Signal Integration

### Daemon Commands
```bash
# Start signal-cli-daemon
signal-cli-daemon --host 0.0.0.0 --port 8080

# Test send
curl -X POST http://localhost:8080/send \
  -H "Content-Type: application/json" \
  -d '{"number": "+1234567890", "message": "test"}'
```
