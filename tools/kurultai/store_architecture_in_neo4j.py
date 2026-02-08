#!/usr/bin/env python3
"""Store ARCHITECTURE.md in Neo4j as Kublai's operational memory.

This script reads the ARCHITECTURE.md file and stores it in Neo4j
as an ArchitectureDocument node linked to the Kublai agent.

Usage:
    python store_architecture_in_neo4j.py

Environment Variables:
    NEO4J_URI - Neo4j connection URI (default: bolt://localhost:7687)
    NEO4J_USER - Neo4j username (default: neo4j)
    NEO4J_PASSWORD - Neo4j password (required)
"""
import os
import sys
from datetime import datetime
from pathlib import Path

def store_architecture():
    """Store architecture.md in Neo4j."""
    # Read architecture.md
    project_root = Path(__file__).parent.parent.parent
    arch_path = project_root / 'ARCHITECTURE.md'

    if not arch_path.exists():
        print(f"ERROR: {arch_path} not found")
        return False

    content = arch_path.read_text()
    print(f"✓ Read architecture document ({len(content)} characters)")

    # Connect to Neo4j
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USER', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD')

    if not password:
        print("ERROR: NEO4J_PASSWORD environment variable not set")
        print("Set it with: export NEO4J_PASSWORD='your-password'")
        return False

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("ERROR: neo4j-driver not installed")
        print("Install with: pip install neo4j")
        return False

    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        with driver.session() as session:
            # Create or update the architecture document node
            result = session.run("""
                MERGE (a:ArchitectureDocument {id: 'kurultai-unified-architecture'})
                SET a.title = 'Kurultai Unified Architecture',
                    a.version = '3.0',
                    a.content = $content,
                    a.updated_at = datetime(),
                    a.updated_by = 'claude-code',
                    a.file_path = $file_path
                RETURN a.id as id
            """, content=content, file_path=str(arch_path))

            record = result.single()
            if record:
                print(f"✓ Architecture document stored in Neo4j: {record['id']}")

            # Ensure Kublai agent exists
            session.run("""
                MERGE (agent:Agent {id: 'main'})
                SET agent.name = 'Kublai',
                    agent.type = 'orchestrator',
                    agent.updated_at = datetime()
            """)
            print("✓ Kublai agent verified")

            # Create relationship to Kublai agent
            session.run("""
                MATCH (a:ArchitectureDocument {id: 'kurultai-unified-architecture'})
                MATCH (agent:Agent {id: 'main'})
                MERGE (agent)-[r:HAS_ARCHITECTURE]->(a)
                SET r.updated_at = datetime()
            """)
            print("✓ Linked to Kublai agent (main)")

            # Also store as OperationalMemory for quick access
            session.run("""
                MERGE (o:OperationalMemory {agent: 'kublai', key: 'architecture'})
                SET o.value = 'Kurultai Unified Architecture v3.0',
                    o.file_path = $file_path,
                    o.last_updated = datetime(),
                    o.document_id = 'kurultai-unified-architecture'
            """, file_path=str(arch_path))
            print("✓ Stored in OperationalMemory")

            # Create summary node for quick reference
            session.run("""
                MERGE (s:ArchitectureSummary {id: 'kurultai-v3-summary'})
                SET s.version = '3.0',
                    s.components = [
                        'Unified Heartbeat Engine',
                        'OpenClaw Gateway',
                        'Neo4j Memory Layer',
                        '6-Agent System'
                    ],
                    s.heartbeat_tasks = 13,
                    s.agents = ['kublai', 'mongke', 'chagatai', 'temujin', 'jochi', 'ogedei'],
                    s.updated_at = datetime()
            """)
            print("✓ Created architecture summary node")

            print("\n✅ Architecture successfully stored in Neo4j!")
            return True

    except Exception as e:
        print(f"ERROR: Failed to store architecture: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        driver.close()

if __name__ == "__main__":
    success = store_architecture()
    sys.exit(0 if success else 1)
