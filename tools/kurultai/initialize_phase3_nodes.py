#!/usr/bin/env python3
"""
Phase 3 Node Initializer

Creates initial instances of missing node types for complete Neo4j schema.
"""

import os
import uuid
from datetime import datetime
from neo4j import GraphDatabase


def get_driver():
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    password = os.environ.get('NEO4J_PASSWORD')
    return GraphDatabase.driver(uri, auth=('neo4j', password))


def create_sample_heartbeat_cycle(driver):
    """Create sample HeartbeatCycle node."""
    with driver.session() as session:
        session.run('''
            CREATE (hc:HeartbeatCycle {
                id: $id,
                cycle_number: 1,
                started_at: datetime(),
                completed_at: datetime(),
                tasks_run: 3,
                tasks_succeeded: 3,
                tasks_failed: 0,
                total_tokens: 650,
                duration_seconds: 45.5
            })
        ''', id=str(uuid.uuid4()))
        print("  ✅ Created HeartbeatCycle sample")


def create_sample_task_result(driver):
    """Create sample TaskResult node."""
    with driver.session() as session:
        session.run('''
            CREATE (tr:TaskResult {
                id: $id,
                agent: 'kublai',
                task_name: 'status_synthesis',
                status: 'success',
                started_at: datetime(),
                completed_at: datetime(),
                summary: 'Status synthesis completed successfully',
                error_message: null,
                tokens_used: 200
            })
        ''', id=str(uuid.uuid4()))
        print("  ✅ Created TaskResult sample")


def create_sample_research(driver):
    """Create sample Research node."""
    with driver.session() as session:
        session.run('''
            CREATE (r:Research {
                id: $id,
                research_type: 'capability_learning',
                title: 'OpenClaw Gateway API Research',
                findings: '{"endpoints": ["/health", "/api/agents"], "auth": "Bearer token"}',
                sources: ['https://docs.openclaw.ai'],
                reliability_score: 0.85,
                agent: 'möngke',
                access_tier: 'PUBLIC',
                created_at: datetime()
            })
        ''', id=str(uuid.uuid4()))
        print("  ✅ Created Research sample")


def create_sample_learned_capability(driver):
    """Create sample LearnedCapability node."""
    with driver.session() as session:
        session.run('''
            CREATE (lc:LearnedCapability {
                id: $id,
                name: 'Neo4jQueryOptimization',
                agent: 'temüjin',
                tool_path: 'tools/generated/neo4j_optimizer.py',
                version: '1.0.0',
                learned_at: datetime(),
                cost: 0.50,
                mastery_score: 0.92,
                risk_level: 'LOW',
                signature: 'sha256:abc123...',
                required_capabilities: [],
                min_trust_level: 'MEDIUM',
                status: 'active'
            })
        ''', id=str(uuid.uuid4()))
        print("  ✅ Created LearnedCapability sample")


def create_sample_capability(driver):
    """Create sample Capability node (CBAC)."""
    with driver.session() as session:
        caps = [
            ('neo4j_read', 'Read from Neo4j database', 'LOW'),
            ('neo4j_write', 'Write to Neo4j database', 'MEDIUM'),
            ('file_access', 'Access workspace files', 'MEDIUM'),
            ('network_request', 'Make HTTP requests', 'HIGH'),
            ('code_execution', 'Execute generated code', 'HIGH')
        ]
        
        for name, desc, risk in caps:
            session.run('''
                MERGE (c:Capability {name: $name})
                ON CREATE SET 
                    c.id = $id,
                    c.description = $desc,
                    c.risk_level = $risk,
                    c.created_at = datetime()
            ''', name=name, desc=desc, risk=risk, id=str(uuid.uuid4()))
        
        print(f"  ✅ Created {len(caps)} Capability nodes")


def create_sample_analysis(driver):
    """Create sample Analysis node."""
    with driver.session() as session:
        session.run('''
            CREATE (a:Analysis {
                id: $id,
                agent: 'jochi',
                target_agent: 'kublai',
                analysis_type: 'performance',
                category: 'query_optimization',
                severity: 'medium',
                description: 'Neo4j query missing index on Task.created_at',
                findings: '{"missing_index": "task_created_at_idx", "impact": "high"}',
                recommendations: '["CREATE INDEX task_created_at_idx..."]',
                assigned_to: 'temüjin',
                status: 'open',
                created_at: datetime()
            })
        ''', id=str(uuid.uuid4()))
        print("  ✅ Created Analysis sample")


def create_architecture_sections(driver):
    """Create ArchitectureSection nodes from ARCHITECTURE.md."""
    sections = [
        ('Executive Summary', 'overview', 1),
        ('System Architecture Overview', 'architecture', 2),
        ('Unified Heartbeat Architecture', 'architecture', 3),
        ('Agent Background Task Registry', 'operations', 4),
        ('Memory Value Score (MVS) Integration', 'memory', 5),
        ('Agent Task Details', 'operations', 6),
        ('Core Components', 'technical', 7),
        ('Neo4j Schema', 'technical', 8),
        ('Security Architecture', 'security', 9),
        ('Deployment Configuration', 'deployment', 10),
        ('Monitoring and Observability', 'operations', 11),
        ('Integration Points', 'technical', 12),
        ('Kublai Self-Awareness System', 'advanced', 13),
        ('Scaling Considerations', 'technical', 14)
    ]
    
    with driver.session() as session:
        for title, category, order in sections:
            session.run('''
                MERGE (as:ArchitectureSection {title: $title})
                ON CREATE SET 
                    as.id = $id,
                    as.category = $category,
                    as.section_order = $order,
                    as.content_summary = $summary,
                    last_updated = datetime(),
                    version = '3.1'
            ''', 
                title=title,
                category=category,
                order=order,
                summary=f'Section {order}: {title}',
                id=str(uuid.uuid4())
            )
        
        print(f"  ✅ Created {len(sections)} ArchitectureSection nodes")


def create_improvement_opportunities(driver):
    """Create sample ImprovementOpportunity nodes."""
    opportunities = [
        ('missing_section', 'Add API endpoint documentation section', 'medium'),
        ('stale_sync', 'Update architecture diagram', 'low'),
        ('api_gap', 'Document agent spawn API', 'high'),
        ('security_gap', 'Add rate limiting documentation', 'medium')
    ]
    
    with driver.session() as session:
        for opp_type, desc, priority in opportunities:
            session.run('''
                CREATE (io:ImprovementOpportunity {
                    id: $id,
                    type: $type,
                    description: $desc,
                    priority: $priority,
                    status: 'proposed',
                    proposed_by: 'kublai',
                    created_at: datetime()
                })
            ''', 
                type=opp_type,
                desc=desc,
                priority=priority,
                id=str(uuid.uuid4())
            )
        
        print(f"  ✅ Created {len(opportunities)} ImprovementOpportunity nodes")


def create_health_checks(driver):
    """Create initial HealthCheck nodes."""
    with driver.session() as session:
        for i in range(3):
            session.run('''
                CREATE (hc:HealthCheck {
                    id: $id,
                    timestamp: datetime() - duration('PT$hoursH'),
                    issues: '[]',
                    issue_count: 0,
                    status: 'healthy'
                })
            ''', id=str(uuid.uuid4()), hours=i*5)
        
        print("  ✅ Created 3 HealthCheck nodes")


def initialize_all_nodes():
    """Initialize all missing node types."""
    print("🗄️  Phase 3: Creating Missing Node Types")
    print("=" * 60)
    
    driver = get_driver()
    
    try:
        create_sample_heartbeat_cycle(driver)
        create_sample_task_result(driver)
        create_sample_research(driver)
        create_sample_learned_capability(driver)
        create_sample_capability(driver)
        create_sample_analysis(driver)
        create_architecture_sections(driver)
        create_improvement_opportunities(driver)
        create_health_checks(driver)
        
        print("=" * 60)
        print("✅ All node types initialized")
        
    finally:
        driver.close()


if __name__ == '__main__':
    initialize_all_nodes()
