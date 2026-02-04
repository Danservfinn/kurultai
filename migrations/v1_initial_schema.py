"""
v1_initial_schema - Initial Neo4j Schema Migration for OpenClaw Multi-Agent Platform

Creates the foundational schema including:
- Indexes for performance
- Constraints for data integrity
- Migration tracking infrastructure
- Agent nodes for all 6 agents
"""

from typing import Optional
from migrations.migration_manager import MigrationManager


class V1InitialSchema:
    """
    Initial schema migration (version 1).

    Creates indexes, constraints, and initial agent nodes for the
    OpenClaw 6-agent system.
    """

    VERSION = 1
    NAME = "initial_schema"
    DESCRIPTION = "Create initial schema with indexes, constraints, and 6 agent nodes"

    # Cypher queries for applying the migration
    UP_CYPHER = """
    // =====================================================
    // V1 Initial Schema Migration
    // OpenClaw Multi-Agent Platform
    // =====================================================

    // -----------------------------------------------------
    // 1. Create Constraints (for data integrity)
    // -----------------------------------------------------

    // Agent.id must be unique
    CREATE CONSTRAINT agent_id_unique IF NOT EXISTS
    FOR (a:Agent) REQUIRE a.id IS UNIQUE;

    // Task.id must be unique
    CREATE CONSTRAINT task_id_unique IF NOT EXISTS
    FOR (t:Task) REQUIRE t.id IS UNIQUE;

    // Migration.version must be unique
    CREATE CONSTRAINT migration_version_unique IF NOT EXISTS
    FOR (m:Migration) REQUIRE m.version IS UNIQUE;

    // Notification.id must be unique
    CREATE CONSTRAINT notification_id_unique IF NOT EXISTS
    FOR (n:Notification) REQUIRE n.id IS UNIQUE;

    // -----------------------------------------------------
    // 2. Create Indexes (for query performance)
    // -----------------------------------------------------

    // Agent lookups by id and status
    CREATE INDEX agent_id_index IF NOT EXISTS
    FOR (a:Agent) ON (a.id);

    CREATE INDEX agent_status_index IF NOT EXISTS
    FOR (a:Agent) ON (a.status);

    CREATE INDEX agent_role_index IF NOT EXISTS
    FOR (a:Agent) ON (a.role);

    // Task lookups
    CREATE INDEX task_id_index IF NOT EXISTS
    FOR (t:Task) ON (t.id);

    CREATE INDEX task_status_index IF NOT EXISTS
    FOR (t:Task) ON (t.status);

    CREATE INDEX task_agent_index IF NOT EXISTS
    FOR (t:Task) ON (t.agent);

    CREATE INDEX task_created_at_index IF NOT EXISTS
    FOR (t:Task) ON (t.created_at);

    // Notification lookups
    CREATE INDEX notification_id_index IF NOT EXISTS
    FOR (n:Notification) ON (n.id);

    CREATE INDEX notification_status_index IF NOT EXISTS
    FOR (n:Notification) ON (n.status);

    CREATE INDEX notification_agent_index IF NOT EXISTS
    FOR (n:Notification) ON (n.agent);

    CREATE INDEX notification_timestamp_index IF NOT EXISTS
    FOR (n:Notification) ON (n.timestamp);

    // Rate limit lookups (composite for rate limiting queries)
    CREATE INDEX ratelimit_agent_operation_date_hour_index IF NOT EXISTS
    FOR (r:RateLimit) ON (r.agent, r.operation, r.date, r.hour);

    CREATE INDEX ratelimit_agent_index IF NOT EXISTS
    FOR (r:RateLimit) ON (r.agent);

    // Migration lookups
    CREATE INDEX migration_version_index IF NOT EXISTS
    FOR (m:Migration) ON (m.version);

    // Memory/Context lookups
    CREATE INDEX memory_agent_index IF NOT EXISTS
    FOR (m:Memory) ON (m.agent);

    CREATE INDEX memory_type_index IF NOT EXISTS
    FOR (m:Memory) ON (m.type);

    CREATE INDEX memory_timestamp_index IF NOT EXISTS
    FOR (m:Memory) ON (m.timestamp);

    // Collaboration lookups
    CREATE INDEX collaboration_task_index IF NOT EXISTS
    FOR (c:Collaboration) ON (c.task_id);

    CREATE INDEX collaboration_status_index IF NOT EXISTS
    FOR (c:Collaboration) ON (c.status);

    // -----------------------------------------------------
    // 3. Create Migration Control Node
    // -----------------------------------------------------

    MERGE (mc:MigrationControl {id: 'main'})
    ON CREATE SET
        mc.version = 1,
        mc.last_updated = datetime(),
        mc.created_at = datetime()
    ON MATCH SET
        mc.version = 1,
        mc.last_updated = datetime();

    // -----------------------------------------------------
    // 4. Create Agent Nodes (All 6 Agents)
    // -----------------------------------------------------

    // Main Agent - Kublai (Squad Lead)
    MERGE (a1:Agent {id: 'main'})
    ON CREATE SET
        a1.name = 'Kublai',
        a1.role = 'Squad Lead',
        a1.description = 'Orchestrates the squad, delegates tasks, synthesizes responses',
        a1.status = 'active',
        a1.created_at = datetime(),
        a1.capabilities = ['orchestration', 'delegation', 'synthesis', 'coordination'],
        a1.priority = 1
    ON MATCH SET
        a1.name = 'Kublai',
        a1.role = 'Squad Lead',
        a1.description = 'Orchestrates the squad, delegates tasks, synthesizes responses',
        a1.last_updated = datetime();

    // Research Agent - Möngke
    MERGE (a2:Agent {id: 'researcher'})
    ON CREATE SET
        a2.name = 'Möngke',
        a2.role = 'Research Specialist',
        a2.description = 'Deep research, information gathering, knowledge synthesis',
        a2.status = 'active',
        a2.created_at = datetime(),
        a2.capabilities = ['research', 'analysis', 'information_gathering', 'knowledge_synthesis'],
        a2.priority = 2
    ON MATCH SET
        a2.name = 'Möngke',
        a2.role = 'Research Specialist',
        a2.description = 'Deep research, information gathering, knowledge synthesis',
        a2.last_updated = datetime();

    // Writer Agent - Chagatai
    MERGE (a3:Agent {id: 'writer'})
    ON CREATE SET
        a3.name = 'Chagatai',
        a3.role = 'Content Writer',
        a3.description = 'Documentation, writing, editing, content creation',
        a3.status = 'active',
        a3.created_at = datetime(),
        a3.capabilities = ['writing', 'editing', 'documentation', 'content_creation'],
        a3.priority = 3
    ON MATCH SET
        a3.name = 'Chagatai',
        a3.role = 'Content Writer',
        a3.description = 'Documentation, writing, editing, content creation',
        a3.last_updated = datetime();

    // Developer Agent - Temüjin
    MERGE (a4:Agent {id: 'developer'})
    ON CREATE SET
        a4.name = 'Temüjin',
        a4.role = 'Software Developer',
        a4.description = 'Code implementation, debugging, technical solutions',
        a4.status = 'active',
        a4.created_at = datetime(),
        a4.capabilities = ['coding', 'debugging', 'architecture', 'technical_design'],
        a4.priority = 4
    ON MATCH SET
        a4.name = 'Temüjin',
        a4.role = 'Software Developer',
        a4.description = 'Code implementation, debugging, technical solutions',
        a4.last_updated = datetime();

    // Analyst Agent - Jochi
    MERGE (a5:Agent {id: 'analyst'})
    ON CREATE SET
        a5.name = 'Jochi',
        a5.role = 'Data Analyst',
        a5.description = 'Data analysis, insights, pattern recognition, reporting',
        a5.status = 'active',
        a5.created_at = datetime(),
        a5.capabilities = ['analysis', 'data_processing', 'pattern_recognition', 'reporting'],
        a5.priority = 5
    ON MATCH SET
        a5.name = 'Jochi',
        a5.role = 'Data Analyst',
        a5.description = 'Data analysis, insights, pattern recognition, reporting',
        a5.last_updated = datetime();

    // Operations Agent - Ögedei
    MERGE (a6:Agent {id: 'ops'})
    ON CREATE SET
        a6.name = 'Ögedei',
        a6.role = 'DevOps Engineer',
        a6.description = 'Infrastructure, deployment, monitoring, system operations',
        a6.status = 'active',
        a6.created_at = datetime(),
        a6.capabilities = ['infrastructure', 'deployment', 'monitoring', 'automation'],
        a6.priority = 6
    ON MATCH SET
        a6.name = 'Ögedei',
        a6.role = 'DevOps Engineer',
        a6.description = 'Infrastructure, deployment, monitoring, system operations',
        a6.last_updated = datetime();

    // -----------------------------------------------------
    // 5. Create Agent Relationships (Delegation Chain)
    // -----------------------------------------------------

    MATCH (main:Agent {id: 'main'})
    MATCH (researcher:Agent {id: 'researcher'})
    MATCH (writer:Agent {id: 'writer'})
    MATCH (developer:Agent {id: 'developer'})
    MATCH (analyst:Agent {id: 'analyst'})
    MATCH (ops:Agent {id: 'ops'})

    // Main delegates to all specialists
    MERGE (main)-[r1:DELEGATES_TO]->(researcher)
    ON CREATE SET r1.created_at = datetime()
    ON MATCH SET r1.last_updated = datetime()

    MERGE (main)-[r2:DELEGATES_TO]->(writer)
    ON CREATE SET r2.created_at = datetime()
    ON MATCH SET r2.last_updated = datetime()

    MERGE (main)-[r3:DELEGATES_TO]->(developer)
    ON CREATE SET r3.created_at = datetime()
    ON MATCH SET r3.last_updated = datetime()

    MERGE (main)-[r4:DELEGATES_TO]->(analyst)
    ON CREATE SET r4.created_at = datetime()
    ON MATCH SET r4.last_updated = datetime()

    MERGE (main)-[r5:DELEGATES_TO]->(ops)
    ON CREATE SET r5.created_at = datetime()
    ON MATCH SET r5.last_updated = datetime()

    // Cross-agent collaboration relationships
    MERGE (researcher)-[c1:COLLABORATES_WITH]->(writer)
    ON CREATE SET c1.relationship = 'research_to_content', c1.created_at = datetime()

    MERGE (developer)-[c2:COLLABORATES_WITH]->(ops)
    ON CREATE SET c2.relationship = 'code_to_deploy', c2.created_at = datetime()

    MERGE (analyst)-[c3:COLLABORATES_WITH]->(researcher)
    ON CREATE SET c3.relationship = 'data_to_research', c3.created_at = datetime()

    MERGE (developer)-[c4:COLLABORATES_WITH]->(analyst)
    ON CREATE SET c4.relationship = 'code_to_analysis', c4.created_at = datetime()

    // -----------------------------------------------------
    // 6. Create System Configuration Node
    // -----------------------------------------------------

    MERGE (sc:SystemConfig {id: 'default'})
    ON CREATE SET
        sc.max_task_retries = 3,
        sc.task_timeout_seconds = 300,
        sc.rate_limit_requests_per_hour = 1000,
        sc.enable_notifications = true,
        sc.created_at = datetime()
    ON MATCH SET
        sc.last_updated = datetime();

    // -----------------------------------------------------
    // 7. Record Migration Success
    // -----------------------------------------------------

    MERGE (m:Migration {version: 1})
    ON CREATE SET
        m.name = 'initial_schema',
        m.description = 'Create initial schema with indexes, constraints, and 6 agent nodes',
        m.applied_at = datetime(),
        m.success = true,
        m.execution_time_ms = 0
    ON MATCH SET
        m.applied_at = datetime(),
        m.success = true;
    """

    # Cypher queries for rolling back the migration
    DOWN_CYPHER = """
    // =====================================================
    // V1 Initial Schema Rollback
    // Removes all schema elements created in v1
    // =====================================================

    // -----------------------------------------------------
    // 1. Remove Agent Relationships
    // -----------------------------------------------------
    MATCH (:Agent)-[r:DELEGATES_TO]->(:Agent) DELETE r;
    MATCH (:Agent)-[r:COLLABORATES_WITH]->(:Agent) DELETE r;

    // -----------------------------------------------------
    // 2. Remove Agent Nodes
    // -----------------------------------------------------
    MATCH (a:Agent) DELETE a;

    // -----------------------------------------------------
    // 3. Remove System Config
    // -----------------------------------------------------
    MATCH (sc:SystemConfig) DELETE sc;

    // -----------------------------------------------------
    // 4. Drop Constraints
    // -----------------------------------------------------
    DROP CONSTRAINT agent_id_unique IF EXISTS;
    DROP CONSTRAINT task_id_unique IF EXISTS;
    DROP CONSTRAINT migration_version_unique IF EXISTS;
    DROP CONSTRAINT notification_id_unique IF EXISTS;

    // -----------------------------------------------------
    // 5. Drop Indexes
    // -----------------------------------------------------
    DROP INDEX agent_id_index IF EXISTS;
    DROP INDEX agent_status_index IF EXISTS;
    DROP INDEX agent_role_index IF EXISTS;
    DROP INDEX task_id_index IF EXISTS;
    DROP INDEX task_status_index IF EXISTS;
    DROP INDEX task_agent_index IF EXISTS;
    DROP INDEX task_created_at_index IF EXISTS;
    DROP INDEX notification_id_index IF EXISTS;
    DROP INDEX notification_status_index IF EXISTS;
    DROP INDEX notification_agent_index IF EXISTS;
    DROP INDEX notification_timestamp_index IF EXISTS;
    DROP INDEX ratelimit_agent_operation_date_hour_index IF EXISTS;
    DROP INDEX ratelimit_agent_index IF EXISTS;
    DROP INDEX migration_version_index IF EXISTS;
    DROP INDEX memory_agent_index IF EXISTS;
    DROP INDEX memory_type_index IF EXISTS;
    DROP INDEX memory_timestamp_index IF EXISTS;
    DROP INDEX collaboration_task_index IF EXISTS;
    DROP INDEX collaboration_status_index IF EXISTS;

    // -----------------------------------------------------
    // 6. Remove Migration Record
    // -----------------------------------------------------
    MATCH (m:Migration {version: 1}) DELETE m;
    """

    @classmethod
    def register(cls, manager: MigrationManager) -> None:
        """
        Register this migration with a MigrationManager.

        Args:
            manager: MigrationManager instance to register with
        """
        manager.register_migration(
            version=cls.VERSION,
            name=cls.NAME,
            up_cypher=cls.UP_CYPHER,
            down_cypher=cls.DOWN_CYPHER,
            description=cls.DESCRIPTION
        )

    @classmethod
    def get_summary(cls) -> dict:
        """
        Get a summary of what this migration creates.

        Returns:
            Dictionary with migration summary
        """
        return {
            "version": cls.VERSION,
            "name": cls.NAME,
            "description": cls.DESCRIPTION,
            "constraints_created": 4,
            "indexes_created": 17,
            "agents_created": [
                {"id": "main", "name": "Kublai", "role": "Squad Lead"},
                {"id": "researcher", "name": "Möngke", "role": "Research Specialist"},
                {"id": "writer", "name": "Chagatai", "role": "Content Writer"},
                {"id": "developer", "name": "Temüjin", "role": "Software Developer"},
                {"id": "analyst", "name": "Jochi", "role": "Data Analyst"},
                {"id": "ops", "name": "Ögedei", "role": "DevOps Engineer"},
            ],
            "relationships_created": [
                "main DELEGATES_TO all specialists",
                "researcher COLLABORATES_WITH writer",
                "developer COLLABORATES_WITH ops",
                "analyst COLLABORATES_WITH researcher",
                "developer COLLABORATES_WITH analyst",
            ]
        }


# Convenience function for running this migration
def run_initial_schema_migration(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str
) -> bool:
    """
    Convenience function to run the initial schema migration.

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Neo4j username
        neo4j_password: Neo4j password

    Returns:
        True if migration successful
    """
    with MigrationManager(neo4j_uri, neo4j_user, neo4j_password) as manager:
        V1InitialSchema.register(manager)
        return manager.migrate(target_version=1)


if __name__ == "__main__":
    import os
    import sys

    # Allow running directly with environment variables
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")

    if not password:
        print("Error: NEO4J_PASSWORD environment variable required")
        sys.exit(1)

    print(f"Running initial schema migration to {uri}...")

    try:
        success = run_initial_schema_migration(uri, user, password)
        if success:
            print("Migration completed successfully!")
            sys.exit(0)
        else:
            print("Migration failed!")
            sys.exit(1)
    except Exception as e:
        print(f"Migration error: {e}")
        sys.exit(1)
