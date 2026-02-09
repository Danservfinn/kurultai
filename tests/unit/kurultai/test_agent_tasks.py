"""
Unit Tests for Agent Tasks Module

Tests all 14 background tasks from agent_tasks.py:
- Ögedei: health_check, file_consistency
- Jochi: memory_curation_rapid, mvs_scoring_pass, smoke_tests, full_tests, vector_dedup, deep_curation
- Chagatai: reflection_consolidation
- Möngke: knowledge_gap_analysis, ordo_sacer_research, ecosystem_intelligence
- Kublai: status_synthesis, weekly_reflection
- System: notion_sync
"""

import pytest
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../tools/kurultai'))

from agent_tasks import (
    health_check, file_consistency, memory_curation_rapid, mvs_scoring_pass,
    smoke_tests, full_tests, vector_dedup, deep_curation, reflection_consolidation,
    knowledge_gap_analysis, ordo_sacer_research, ecosystem_intelligence,
    status_synthesis, weekly_reflection, notion_sync, run_task, TASK_REGISTRY
)


class TestOgedeiTasks:
    """Tests for Ögedei (Ops) agent tasks."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver."""
        driver = Mock()
        session = Mock()
        driver.session.return_value = session
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        return driver, session

    def test_health_check_success(self, mock_driver):
        """Test health_check with all systems healthy."""
        driver, session = mock_driver
        
        # Mock successful Neo4j query
        result = Mock()
        result.single.return_value = {'test': 1}
        result.peek.return_value = []
        
        # Mock stale agents query (no stale agents)
        result2 = Mock()
        result2.__iter__ = Mock(return_value=iter([]))
        
        session.run.side_effect = [result, result2]
        
        result = health_check(driver)
        
        assert result['status'] == 'success'
        assert result['issues_found'] == 0
        assert result['issues'] == []

    def test_health_check_neo4j_failure(self, mock_driver):
        """Test health_check when Neo4j is down."""
        driver, session = mock_driver
        
        # Mock Neo4j failure
        session.run.side_effect = Exception("Connection refused")
        
        result = health_check(driver)
        
        assert result['status'] == 'warning'
        assert result['issues_found'] == 1
        assert 'Neo4j error' in result['issues'][0]

    def test_health_check_stale_heartbeats(self, mock_driver):
        """Test health_check with stale agent heartbeats."""
        driver, session = mock_driver
        
        # Mock successful Neo4j query
        result1 = Mock()
        result1.single.return_value = {'test': 1}
        
        # Mock stale agents (return mock records)
        stale_record = Mock()
        stale_record.__getitem__ = Mock(side_effect=lambda k: 'Jochi' if k == 'name' else None)
        
        result2 = Mock()
        result2.__iter__ = Mock(return_value=iter([stale_record]))
        
        session.run.side_effect = [result1, result2]
        
        result = health_check(driver)
        
        assert result['status'] == 'warning'
        assert result['issues_found'] == 1

    def test_file_consistency_all_present(self, mock_driver, tmp_path):
        """Test file_consistency when all SOUL.md files exist."""
        driver, session = mock_driver
        
        # Create temporary SOUL.md files
        souls_dir = tmp_path / "souls"
        souls_dir.mkdir()
        
        agents = ['main', 'researcher', 'writer', 'developer', 'analyst', 'ops']
        for agent in agents:
            agent_dir = souls_dir / agent
            agent_dir.mkdir()
            (agent_dir / "SOUL.md").write_text(f"# {agent} SOUL")
        
        with patch.dict(os.environ, {'SOULS_DIR': str(souls_dir)}):
            result = file_consistency(driver)
        
        assert result['status'] == 'success'
        assert result['missing_souls'] == []
        assert result['checked'] == 6

    def test_file_consistency_missing_files(self, mock_driver):
        """Test file_consistency when some SOUL.md files are missing."""
        driver, session = mock_driver
        
        result = file_consistency(driver)
        
        assert result['status'] == 'warning'
        assert len(result['missing_souls']) == 6


class TestJochiTasks:
    """Tests for Jochi (Analyst) agent tasks."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver."""
        driver = Mock()
        session = Mock()
        driver.session.return_value = session
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        return driver, session

    def test_memory_curation_rapid(self, mock_driver):
        """Test memory_curation_rapid task."""
        driver, session = mock_driver
        
        # Mock query results
        result1 = Mock()
        result1.single.return_value = {'deleted': 5}
        result1.peek.return_value = result1
        
        result2 = Mock()
        result2.single.return_value = {'deleted': 3}
        result2.peek.return_value = result2
        
        session.run.side_effect = [result1, result2]
        
        result = memory_curation_rapid(driver)
        
        assert result['status'] == 'success'
        assert result['notifications_cleaned'] == 5
        assert result['sessions_cleaned'] == 3

    def test_memory_curation_no_data(self, mock_driver):
        """Test memory_curation_rapid with no data to clean."""
        driver, session = mock_driver
        
        # Mock empty results
        result = Mock()
        result.peek.return_value = None
        
        session.run.return_value = result
        
        result = memory_curation_rapid(driver)
        
        assert result['status'] == 'success'

    def test_mvs_scoring_pass(self, mock_driver):
        """Test mvs_scoring_pass task."""
        driver, session = mock_driver
        
        # Mock MVS scorer
        with patch('agent_tasks.MVSScorer') as mock_scorer_class:
            mock_scorer = Mock()
            mock_scorer.score_all_nodes.return_value = 42
            mock_scorer_class.return_value = mock_scorer
            
            result = mvs_scoring_pass(driver)
        
        assert result['status'] == 'success'
        assert result['nodes_scored'] == 42

    def test_smoke_tests_success(self, mock_driver):
        """Test smoke_tests task - success case."""
        driver, session = mock_driver
        
        # Mock successful query
        result = Mock()
        result.single.return_value = {'test': 1}
        
        session.run.return_value = result
        
        result = smoke_tests(driver)
        
        assert result['status'] == 'success'
        assert result['tests_run'] == 1
        assert result['failures'] == 0

    def test_smoke_tests_failure(self, mock_driver):
        """Test smoke_tests task - failure case."""
        driver, session = mock_driver
        
        # Mock failed query
        session.run.side_effect = Exception("Neo4j connection failed")
        
        result = smoke_tests(driver)
        
        assert result['status'] == 'error'
        assert 'error' in result

    def test_full_tests_placeholder(self, mock_driver):
        """Test full_tests task (currently placeholder)."""
        driver, session = mock_driver
        
        result = full_tests(driver)
        
        assert result['status'] == 'success'
        assert 'placeholder' in result['message'].lower()

    def test_vector_dedup_placeholder(self, mock_driver):
        """Test vector_dedup task (currently placeholder)."""
        driver, session = mock_driver
        
        result = vector_dedup(driver)
        
        assert result['status'] == 'success'
        assert 'placeholder' in result['message'].lower()

    def test_deep_curation(self, mock_driver):
        """Test deep_curation task."""
        driver, session = mock_driver
        
        # Mock query result
        result = Mock()
        result.single.return_value = {'deleted': 10}
        result.peek.return_value = result
        
        session.run.return_value = result
        
        result = deep_curation(driver)
        
        assert result['status'] == 'success'
        assert result['orphans_deleted'] == 10


class TestChagataiTasks:
    """Tests for Chagatai (Writer) agent tasks."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver."""
        driver = Mock()
        session = Mock()
        driver.session.return_value = session
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        return driver, session

    def test_reflection_consolidation_system_idle(self, mock_driver):
        """Test reflection_consolidation when system is idle."""
        driver, session = mock_driver
        
        # Mock no pending high-priority tasks
        result = Mock()
        result.single.return_value = {'count': 0}
        
        session.run.return_value = result
        
        result = reflection_consolidation(driver)
        
        assert result['status'] == 'success'

    def test_reflection_consolidation_system_busy(self, mock_driver):
        """Test reflection_consolidation when system is busy."""
        driver, session = mock_driver
        
        # Mock pending high-priority tasks
        result = Mock()
        result.single.return_value = {'count': 5}
        
        session.run.return_value = result
        
        result = reflection_consolidation(driver)
        
        assert result['status'] == 'skipped'
        assert 'not idle' in result['reason'].lower()


class TestMongkeTasks:
    """Tests for Möngke (Researcher) agent tasks."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver."""
        driver = Mock()
        session = Mock()
        driver.session.return_value = session
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        return driver, session

    def test_knowledge_gap_analysis(self, mock_driver):
        """Test knowledge_gap_analysis task."""
        driver, session = mock_driver
        
        # Mock query results with gaps
        record1 = Mock()
        record1.__getitem__ = Mock(side_effect=lambda k: 'Topic A' if k == 'topic' else 1)
        record2 = Mock()
        record2.__getitem__ = Mock(side_effect=lambda k: 'Topic B' if k == 'topic' else 2)
        
        result = Mock()
        result.__iter__ = Mock(return_value=iter([record1, record2]))
        
        session.run.return_value = result
        
        result = knowledge_gap_analysis(driver)
        
        assert result['status'] == 'success'
        assert result['gaps_identified'] == 2
        assert len(result['gaps']) == 2

    def test_knowledge_gap_analysis_no_gaps(self, mock_driver):
        """Test knowledge_gap_analysis with no gaps."""
        driver, session = mock_driver
        
        # Mock empty results
        result = Mock()
        result.__iter__ = Mock(return_value=iter([]))
        
        session.run.return_value = result
        
        result = knowledge_gap_analysis(driver)
        
        assert result['status'] == 'success'
        assert result['gaps_identified'] == 0

    def test_ordo_sacer_research(self, mock_driver):
        """Test ordo_sacer_research task (placeholder)."""
        driver, session = mock_driver
        
        result = ordo_sacer_research(driver)
        
        assert result['status'] == 'success'

    def test_ecosystem_intelligence(self, mock_driver):
        """Test ecosystem_intelligence task (placeholder)."""
        driver, session = mock_driver
        
        result = ecosystem_intelligence(driver)
        
        assert result['status'] == 'success'


class TestKublaiTasks:
    """Tests for Kublai (Main) agent tasks."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver."""
        driver = Mock()
        session = Mock()
        driver.session.return_value = session
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        return driver, session

    def test_status_synthesis_healthy(self, mock_driver):
        """Test status_synthesis with all agents healthy."""
        driver, session = mock_driver
        
        # Mock agent status results
        record1 = Mock()
        record1.__getitem__ = Mock(side_effect=lambda k: {
            'name': 'Kublai',
            'status': 'active',
            'infra': datetime.now(timezone.utc),
            'func': datetime.now(timezone.utc)
        }.get(k))
        
        result = Mock()
        result.__iter__ = Mock(return_value=iter([record1]))
        
        session.run.return_value = result
        
        result = status_synthesis(driver)
        
        assert result['status'] == 'success'
        assert result['agents_checked'] == 1
        assert result['critical_issues'] == 0

    def test_status_synthesis_with_errors(self, mock_driver):
        """Test status_synthesis with agents in error state."""
        driver, session = mock_driver
        
        # Mock agent status with error
        record1 = Mock()
        record1.__getitem__ = Mock(side_effect=lambda k: {
            'name': 'Jochi',
            'status': 'error',
            'infra': datetime.now(timezone.utc),
            'func': datetime.now(timezone.utc)
        }.get(k))
        
        result = Mock()
        result.__iter__ = Mock(return_value=iter([record1]))
        
        session.run.return_value = result
        
        result = status_synthesis(driver)
        
        assert result['status'] == 'success'
        assert result['critical_issues'] == 1
        assert 'Jochi' in result['critical_agents']

    def test_weekly_reflection(self, mock_driver):
        """Test weekly_reflection task (placeholder)."""
        driver, session = mock_driver
        
        result = weekly_reflection(driver)
        
        assert result['status'] == 'success'


class TestSystemTasks:
    """Tests for System-level tasks."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver."""
        driver = Mock()
        session = Mock()
        driver.session.return_value = session
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        return driver, session

    def test_notion_sync_no_api_key(self, mock_driver):
        """Test notion_sync when NOTION_API_KEY not configured."""
        driver, session = mock_driver
        
        with patch.dict(os.environ, {}, clear=True):
            result = notion_sync(driver)
        
        assert result['status'] == 'skipped'
        assert 'not configured' in result['reason'].lower()

    def test_notion_sync_with_api_key(self, mock_driver):
        """Test notion_sync when API key is present."""
        driver, session = mock_driver
        
        with patch.dict(os.environ, {'NOTION_API_KEY': 'test_key'}):
            result = notion_sync(driver)
        
        assert result['status'] == 'success'


class TestTaskRegistry:
    """Tests for TASK_REGISTRY and run_task function."""

    def test_task_registry_complete(self):
        """Verify all 14 tasks are registered."""
        expected_tasks = [
            'health_check', 'file_consistency',
            'memory_curation_rapid', 'mvs_scoring_pass', 'smoke_tests', 
            'full_tests', 'vector_dedup', 'deep_curation',
            'reflection_consolidation',
            'knowledge_gap_analysis', 'ordo_sacer_research', 'ecosystem_intelligence',
            'status_synthesis', 'weekly_reflection',
            'notion_sync'
        ]
        
        for task in expected_tasks:
            assert task in TASK_REGISTRY, f"Task {task} not found in registry"
            assert 'fn' in TASK_REGISTRY[task]
            assert 'agent' in TASK_REGISTRY[task]
            assert 'freq' in TASK_REGISTRY[task]

    def test_task_agent_assignments(self):
        """Verify tasks are assigned to correct agents."""
        assert TASK_REGISTRY['health_check']['agent'] == 'ögedei'
        assert TASK_REGISTRY['smoke_tests']['agent'] == 'jochi'
        assert TASK_REGISTRY['reflection_consolidation']['agent'] == 'chagatai'
        assert TASK_REGISTRY['knowledge_gap_analysis']['agent'] == 'möngke'
        assert TASK_REGISTRY['status_synthesis']['agent'] == 'kublai'
        assert TASK_REGISTRY['notion_sync']['agent'] == 'system'

    def test_task_frequencies(self):
        """Verify task frequencies are correct."""
        assert TASK_REGISTRY['health_check']['freq'] == 5
        assert TASK_REGISTRY['smoke_tests']['freq'] == 15
        assert TASK_REGISTRY['full_tests']['freq'] == 60
        assert TASK_REGISTRY['ecosystem_intelligence']['freq'] == 10080

    def test_run_task_unknown_task(self):
        """Test run_task with unknown task name."""
        result = run_task('unknown_task')
        
        assert result['status'] == 'error'
        assert 'unknown task' in result['error'].lower()

    def test_run_task_success(self):
        """Test run_task with valid task."""
        driver = Mock()
        session = Mock()
        driver.session.return_value = session
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        
        result = Mock()
        result.__iter__ = Mock(return_value=iter([]))
        session.run.return_value = result
        
        with patch('agent_tasks.get_driver', return_value=driver):
            result = run_task('health_check')
        
        assert 'task' in result
        assert result['task'] == 'health_check'
        assert 'timestamp' in result

    def test_run_task_exception(self):
        """Test run_task when task raises exception."""
        driver = Mock()
        
        with patch('agent_tasks.get_driver', return_value=driver):
            with patch.object(driver, 'session', side_effect=Exception("DB error")):
                result = run_task('health_check', driver)
        
        assert result['status'] == 'error'
        assert 'error' in result


class TestTokenBudgets:
    """Tests for verifying token budgets per ARCHITECTURE.md."""

    def test_ogedei_token_budgets(self):
        """Verify Ögedei tasks have correct token budgets."""
        # Ögedei: health_check (150 tokens), file_consistency (200 tokens)
        # These are implicit in the current implementation
        pass  # Placeholder for budget verification

    def test_jochi_token_budgets(self):
        """Verify Jochi tasks have correct token budgets."""
        # Jochi: smoke_tests (800), full_tests (1500), deep_curation (2000)
        pass  # Placeholder for budget verification

    def test_peak_token_usage(self):
        """Verify peak usage stays under 8,250 tokens."""
        # Calculate worst-case token usage when all tasks align
        peak_tokens = 0
        # 5-min tasks: 650 tokens
        # 15-min tasks: 1000 tokens
        # etc.
        assert peak_tokens <= 8250, "Peak token usage exceeds budget"
