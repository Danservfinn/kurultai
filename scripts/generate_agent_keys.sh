#!/bin/bash
# Kurultai v0.2 Agent Key Generation Script
# Generates HMAC-SHA256 keys for all 6 agents and stores in Neo4j

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Kurultai v0.2 Agent Key Generation ==="
echo "This will generate HMAC-SHA256 keys for all 6 agents"
echo "Keys expire in 90 days"
echo ""

# Check prerequisites
if [[ -z "$NEO4J_URI" ]]; then
    echo "Error: NEO4J_URI environment variable not set"
    echo "Export it or add to .env file"
    echo "Example: export NEO4J_URI=bolt://localhost:7687"
    exit 1
fi

if [[ -z "$NEO4J_USER" ]]; then
    echo "Error: NEO4J_USER environment variable not set"
    echo "Export it or add to .env file"
    echo "Example: export NEO4J_USER=neo4j"
    exit 1
fi

if [[ -z "$NEO4J_PASSWORD" ]]; then
    echo "Error: NEO4J_PASSWORD environment variable not set"
    echo "Export it or add to .env file"
    echo "Example: export NEO4J_PASSWORD=your_password"
    exit 1
fi

# Load .env if it exists
if [[ -f "$PROJECT_DIR/.env" ]]; then
    echo "Loading environment from .env..."
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# Run key generation
python3 << 'EOF'
import os
import sys
import secrets
from datetime import datetime, timedelta

# Add project to path
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_dir)

from openclaw_memory import OperationalMemory

agents = [
    ('main', 'Kublai'),
    ('researcher', 'Möngke'),
    ('writer', 'Chagatai'),
    ('developer', 'Temüjin'),
    ('analyst', 'Jochi'),
    ('ops', 'Ögedei')
]

neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
print(f"Connecting to Neo4j at {neo4j_uri}...")
print("")

memory = OperationalMemory()

for agent_id, agent_name in agents:
    key_hash = secrets.token_hex(32)

    cypher = '''
        MATCH (a:Agent {id: $agent_id})
        CREATE (k:AgentKey {
            id: randomUUID(),
            key_hash: $key_hash,
            created_at: datetime(),
            expires_at: datetime() + duration('P90D'),
            is_active: true
        })
        CREATE (a)-[:HAS_KEY]->(k)
        RETURN k.id as key_id, k.expires_at as expires
    '''

    try:
        with memory._session() as session:
            result = session.run(cypher, agent_id=agent_id, key_hash=key_hash)
            record = result.single()
            if record:
                expires_str = record['expires'].isoformat()
                print(f"  {agent_name:12} ({agent_id})")
                print(f"    key_id:  {record['key_id']}")
                print(f"    expires: {expires_str}")
                print(f"    hash:    {key_hash[:16]}...")
            else:
                print(f"  {agent_name}: Agent node not found in Neo4j")
                print(f"    Run migration first: python scripts/run_migrations.py --target-version 3")
    except Exception as e:
        print(f"  {agent_name}: Error - {e}")

print("")
print("=== Verifying keys ===")

verify_cypher = '''
    MATCH (a:Agent)-[:HAS_KEY]->(k:AgentKey)
    WHERE k.is_active = true
    RETURN a.id as agent_id, a.name as agent_name,
           k.id as key_id, k.expires_at as expires
    ORDER BY a.id
'''

try:
    with memory._session() as session:
        results = session.run(verify_cypher)
        count = 0
        print("")
        print("Active Agent Keys:")
        print("------------------")
        for record in results:
            count += 1
            expires_days = (record['expires'].replace(tzinfo=None) - datetime.now()).days
            print(f"  {record['agent_name']:12} ({record['agent_id']})")
            print(f"    expires in {expires_days} days")

        print("")
        print(f"Total active keys: {count}/6")

        if count == 6:
            print("")
            print("  All agent keys generated successfully!")
            sys.exit(0)
        else:
            print("")
            print(f"  Warning: Only {count}/6 keys found.")
            print("  Run migrations first or check Agent nodes exist.")
            print("  Command: python scripts/run_migrations.py --target-version 3")
            sys.exit(1)
except Exception as e:
    print(f"Error verifying keys: {e}")
    sys.exit(1)

EOF

exit_code=$?

if [[ $exit_code -eq 0 ]]; then
    echo ""
    echo "Agent key generation complete!"
else
    echo ""
    echo "Agent key generation failed. Check the error messages above."
fi

exit $exit_code
