#!/usr/bin/env python3
"""Kurultai v0.2 Agent Key Generation - Railway-compatible version."""
import os
import sys
import secrets
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from neo4j import GraphDatabase
except ImportError:
    print("ERROR: neo4j module not installed")
    sys.exit(1)

# Neo4j connection
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://neo4j.railway.internal:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")

if not NEO4J_PASSWORD:
    print("ERROR: NEO4J_PASSWORD environment variable not set")
    sys.exit(1)

print("=== Kurultai v0.2 Agent Key Generation ===")
print(f"Connecting to Neo4j at {NEO4J_URI}...")
print("")

# Define the 6 agents
agents = [
    ('main', 'Kublai'),
    ('researcher', 'Möngke'),
    ('writer', 'Chagatai'),
    ('developer', 'Temüjin'),
    ('analyst', 'Jochi'),
    ('ops', 'Ögedei')
]

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

try:
    with driver.session() as session:
        # First check if Agent nodes exist
        result = session.run("MATCH (a:Agent) RETURN count(a) as count")
        agent_count = result.single()["count"]
        print(f"Found {agent_count} Agent nodes in Neo4j")

        if agent_count == 0:
            print("ERROR: No Agent nodes found. Run migrations first!")
            sys.exit(1)

        # Check existing keys
        result = session.run("""
            MATCH (a:Agent)-[:HAS_KEY]->(k:AgentKey)
            WHERE k.is_active = true
            RETURN count(k) as count
        """)
        existing_keys = result.single()["count"]
        print(f"Found {existing_keys} existing active keys")

        if existing_keys >= 6:
            print("All agent keys already exist. Skipping generation.")
            print("")
            # List existing keys
            result = session.run("""
                MATCH (a:Agent)-[:HAS_KEY]->(k:AgentKey)
                WHERE k.is_active = true
                RETURN a.name as agent_name, a.id as agent_id,
                       k.id as key_id, k.expires_at as expires
                ORDER BY a.id
            """)
            print("=== Existing Agent Keys ===")
            for record in result:
                expires_days = (record['expires'].replace(tzinfo=None) - datetime.now()).days
                print(f"  {record['agent_name']:12} ({record['agent_id']})")
                print(f"    key_id:  {record['key_id']}")
                print(f"    expires in {expires_days} days")
            sys.exit(0)

        # Generate keys for agents that don't have them
        print("")
        print("=== Generating Agent Keys ===")
        for agent_id, agent_name in agents:
            # Check if agent already has a key
            result = session.run("""
                MATCH (a:Agent {id: $agent_id})-[:HAS_KEY]->(k:AgentKey)
                WHERE k.is_active = true
                RETURN count(k) as count
            """, agent_id=agent_id)
            has_key = result.single()["count"] > 0

            if has_key:
                print(f"  {agent_name:12} ({agent_id}) - already has key, skipping")
                continue

            # Generate new key
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

            result = session.run(cypher, agent_id=agent_id, key_hash=key_hash)
            record = result.single()
            if record:
                expires_str = record['expires'].isoformat()
                print(f"  {agent_name:12} ({agent_id})")
                print(f"    key_id:  {record['key_id']}")
                print(f"    expires: {expires_str}")
            else:
                print(f"  {agent_name}: Agent node not found in Neo4j")

        print("")
        print("=== Verifying keys ===")

        verify_cypher = '''
            MATCH (a:Agent)-[:HAS_KEY]->(k:AgentKey)
            WHERE k.is_active = true
            RETURN a.id as agent_id, a.name as agent_name,
                   k.id as key_id, k.expires_at as expires
            ORDER BY a.id
        '''

        results = session.run(verify_cypher)
        count = 0
        print("")
        print("Active Agent Keys:")
        print("------------------")
        for record in results:
            count += 1
            expires_days = (record['expires'].replace(tzinfo=None) - datetime.now()).days
            print(f"  {record['agent_name']:12} ({record['agent_id']})")
            print(f"    key_id:  {record['key_id']}")
            print(f"    expires in {expires_days} days")

        print("")
        print(f"Total active keys: {count}/6")

        if count == 6:
            print("")
            print("  All agent keys generated successfully!")
        else:
            print("")
            print(f"  Warning: Only {count}/6 keys found.")
            sys.exit(1)

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    driver.close()
