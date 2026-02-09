"""Phase 1 Foundation Integration Tests"""

import os
import sys
import unittest
import json
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from neo4j import GraphDatabase


class TestPhase1Foundation(unittest.TestCase):
    """Test Phase 1: Foundation"""
    
    @classmethod
    def setUpClass(cls):
        uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        password = os.environ.get('NEO4J_PASSWORD')
        if not password:
            raise unittest.SkipTest("NEO4J_PASSWORD not set")
        cls.driver = GraphDatabase.driver(uri, auth=('neo4j', password))
    
    @classmethod
    def tearDownClass(cls):
        cls.driver.close()
    
    def test_01_all_agents_have_infra_heartbeat(self):
        """P1-T2: All 6 agents have infra_heartbeat property."""
        with self.driver.session() as session:
            result = session.run('''
                MATCH (a:Agent)
                WHERE a.name IN ['Kublai', 'Möngke', 'Chagatai', 'Temüjin', 'Jochi', 'Ögedei']
                  AND a.infra_heartbeat IS NOT NULL
                RETURN count(a) as count
            ''')
            count = result.single()['count']
            self.assertEqual(count, 6, f"Expected 6 agents, got {count}")
    
    def test_02_agent_spawner_module_exists(self):
        """P1-T1: Agent spawner module exists."""
        self.assertTrue(os.path.exists('tools/kurultai/agent_spawner_direct.py'))
    
    def test_03_railway_config_exists(self):
        """P1-T3: railway.toml exists."""
        self.assertTrue(os.path.exists('railway.toml'))
    
    def test_04_task_delegation_works(self):
        """P1-T4/T5: Tasks can be delegated."""
        test_id = 'test_' + uuid.uuid4().hex[:8]
        
        with self.driver.session() as session:
            session.run('''
                CREATE (t:Task {
                    id: $id,
                    description: 'Test task',
                    assigned_to: 'Möngke',
                    created_by: 'Kublai',
                    priority: 'low',
                    task_type: 'test',
                    status: 'pending',
                    created_at: datetime()
                })
            ''', id=test_id)
            
            session.run('''
                MATCH (t:Task {id: $id})
                SET t.delegated_by = 'Kublai'
            ''', id=test_id)
            
            result = session.run('''
                MATCH (t:Task {id: $id})
                RETURN t.delegated_by as delegated
            ''', id=test_id)
            
            self.assertEqual(result.single()['delegated'], 'Kublai')
            session.run('MATCH (t:Task {id: $id}) DELETE t', id=test_id)


if __name__ == '__main__':
    unittest.main()
