#!/usr/bin/env python3
"""Update Neo4j task status to completed."""
import os
import sys

# Neo4j connection details
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j.railway.internal:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# Task ID to update
TASK_ID = "0563b4da-26f3-4d5b-89a1-7309d134dd00"

def update_task_status():
    try:
        from neo4j import GraphDatabase
        
        if not NEO4J_PASSWORD:
            print("❌ NEO4J_PASSWORD not set")
            return False
        
        print(f"🔌 Connecting to Neo4j at {NEO4J_URI}...")
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
        # Check if task exists
        with driver.session() as session:
            result = session.run(
                "MATCH (t:Task {id: $task_id}) RETURN t.status as status, t.description as description",
                task_id=TASK_ID
            )
            record = result.single()
            
            if not record:
                print(f"⚠️  Task {TASK_ID} not found in Neo4j")
                driver.close()
                return False
            
            current_status = record["status"]
            description = record["description"]
            print(f"📋 Found task: {description}")
            print(f"   Current status: {current_status}")
            
            # Update task status to completed
            session.run(
                """
                MATCH (t:Task {id: $task_id})
                SET t.status = 'completed',
                    t.completed_at = datetime(),
                    t.updated_at = datetime()
                RETURN t.id as id
                """,
                task_id=TASK_ID
            )
            
            print(f"✅ Task status updated to 'completed'")
            
        driver.close()
        return True
        
    except ImportError:
        print("❌ neo4j driver not installed")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = update_task_status()
    sys.exit(0 if success else 1)
