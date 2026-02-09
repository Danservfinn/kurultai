"""
Tests for SOULInjector

Author: Chagatai (Writer Agent)
Date: 2026-02-09
"""

import pytest
import os
import tempfile
from datetime import datetime
from unittest.mock import Mock, patch, mock_open
from typing import Dict, List, Any

from tools.kurultai.soul_injector import (
    SOULInjector,
    InjectionRecord,
    InjectionStatus,
)


class TestSOULInjector:
    """Tests for SOULInjector class."""
    
    @pytest.fixture
    def temp_souls_dir(self):
        """Create temporary souls directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create agent directories
            for agent in ['main', 'writer', 'developer', 'researcher', 'analyst', 'ops']:
                os.makedirs(os.path.join(tmpdir, agent), exist_ok=True)
            yield tmpdir
    
    @pytest.fixture
    def injector(self, temp_souls_dir):
        """Create injector with temp directory."""
        return SOULInjector(
            souls_base_path=temp_souls_dir,
            enable_git=False,  # Disable git for testing
        )
    
    @pytest.fixture
    def sample_soul_content(self) -> str:
        """Sample SOUL.md content."""
        return """# SOUL.md - Test Agent

## Identity

- **Name**: Test Agent
- **Role**: Testing

## Operational Context

Test context here.

## Responsibilities

Test responsibilities.
"""
    
    @pytest.fixture
    def sample_rule(self) -> Dict[str, Any]:
        """Sample rule dict."""
        return {
            'id': 'rule-123',
            'name': 'test_error_handling',
            'description': 'Always handle errors properly',
            'rule_type': 'error_handling',
            'priority': 3,
            'effectiveness_score': 0.85,
            'conditions': ['error_rate > 0.1'],
            'actions': ['Add try-except blocks', 'Log errors'],
        }
    
    def test_initialization(self, temp_souls_dir):
        """Test injector initialization."""
        injector = SOULInjector(
            souls_base_path=temp_souls_dir,
            enable_git=False,
        )
        
        assert injector.souls_base_path == temp_souls_dir
        assert injector.enable_git is False
    
    def test_get_soul_file_path(self, injector):
        """Test soul file path resolution."""
        # Test various agent names
        paths = {
            'kublai': injector._get_soul_file_path('kublai'),
            'temujin': injector._get_soul_file_path('temujin'),
            'chagatai': injector._get_soul_file_path('chagatai'),
            'mongke': injector._get_soul_file_path('mongke'),
            'jochi': injector._get_soul_file_path('jochi'),
            'ogedei': injector._get_soul_file_path('ogedei'),
        }
        
        assert 'main' in paths['kublai']
        assert 'developer' in paths['temujin']
        assert 'writer' in paths['chagatai']
        assert 'researcher' in paths['mongke']
        assert 'analyst' in paths['jochi']
        assert 'ops' in paths['ogedei']
    
    def test_parse_soul_file_not_exists(self, injector):
        """Test parsing non-existent file."""
        result = injector.parse_soul_file('nonexistent')
        
        assert result['exists'] is False
        assert result['content'] == ''
    
    def test_parse_soul_file_exists(self, injector, sample_soul_content):
        """Test parsing existing file."""
        # Create test file
        agent_id = 'test_agent'
        agent_dir = os.path.join(injector.souls_base_path, agent_id)
        os.makedirs(agent_dir, exist_ok=True)
        
        file_path = os.path.join(agent_dir, 'SOUL.md')
        with open(file_path, 'w') as f:
            f.write(sample_soul_content)
        
        result = injector.parse_soul_file(agent_id)
        
        assert result['exists'] is True
        assert 'Identity' in result['sections']
        assert 'Operational Context' in result['sections']
        assert result['has_learned_rules_section'] is False
    
    def test_parse_soul_file_with_learned_rules(self, injector):
        """Test parsing file with learned rules section."""
        content = f"""# SOUL.md

## Identity

Test agent.

{injector.LEARNED_RULES_START}

## Learned Rules

### test_rule

Test rule content.

{injector.LEARNED_RULES_END}

## Other Section

More content.
"""
        # Create test file
        agent_id = 'test_agent'
        agent_dir = os.path.join(injector.souls_base_path, agent_id)
        os.makedirs(agent_dir, exist_ok=True)
        
        file_path = os.path.join(agent_dir, 'SOUL.md')
        with open(file_path, 'w') as f:
            f.write(content)
        
        result = injector.parse_soul_file(agent_id)
        
        assert result['exists'] is True
        assert result['has_learned_rules_section'] is True
        assert 'test_rule' in result['learned_rules_content']
    
    def test_format_rule_for_injection(self, injector, sample_rule):
        """Test rule formatting."""
        formatted = injector.format_rule_for_injection(sample_rule)
        
        assert 'test_error_handling' in formatted
        assert 'error_handling' in formatted
        assert '85%' in formatted
        assert 'error_rate > 0.1' in formatted
        assert 'Add try-except blocks' in formatted
        assert 'rule-123' in formatted
    
    def test_inject_rules_new_section(self, injector, sample_soul_content, sample_rule):
        """Test injecting rules into file without learned rules section."""
        # Create test file
        agent_id = 'test_agent'
        agent_dir = os.path.join(injector.souls_base_path, agent_id)
        os.makedirs(agent_dir, exist_ok=True)
        
        file_path = os.path.join(agent_dir, 'SOUL.md')
        with open(file_path, 'w') as f:
            f.write(sample_soul_content)
        
        # Inject rules
        record = injector.inject_rules(agent_id, [sample_rule])
        
        assert record.status == InjectionStatus.INJECTED
        
        # Verify file was updated
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert injector.LEARNED_RULES_START in content
        assert injector.LEARNED_RULES_END in content
        assert 'test_error_handling' in content
    
    def test_inject_rules_replace_section(self, injector, sample_rule):
        """Test replacing existing learned rules section."""
        content = f"""# SOUL.md

## Identity

Test agent.

{injector.LEARNED_RULES_START}

## Learned Rules

### old_rule

Old rule content.

{injector.LEARNED_RULES_END}
"""
        # Create test file
        agent_id = 'test_agent'
        agent_dir = os.path.join(injector.souls_base_path, agent_id)
        os.makedirs(agent_dir, exist_ok=True)
        
        file_path = os.path.join(agent_dir, 'SOUL.md')
        with open(file_path, 'w') as f:
            f.write(content)
        
        # Inject rules
        record = injector.inject_rules(agent_id, [sample_rule])
        
        assert record.status == InjectionStatus.INJECTED
        
        # Verify old rule was replaced
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert 'test_error_handling' in content
        assert 'old_rule' not in content
    
    def test_inject_rules_dry_run(self, injector, sample_soul_content, sample_rule):
        """Test dry run injection."""
        # Create test file
        agent_id = 'test_agent'
        agent_dir = os.path.join(injector.souls_base_path, agent_id)
        os.makedirs(agent_dir, exist_ok=True)
        
        file_path = os.path.join(agent_dir, 'SOUL.md')
        with open(file_path, 'w') as f:
            f.write(sample_soul_content)
        
        # Dry run injection
        record = injector.inject_rules(agent_id, [sample_rule], dry_run=True)
        
        assert record.status == InjectionStatus.PENDING
        
        # Verify file was NOT changed
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert injector.LEARNED_RULES_START not in content
    
    def test_inject_rules_file_not_found(self, injector, sample_rule):
        """Test injection when file doesn't exist."""
        record = injector.inject_rules('nonexistent', [sample_rule])
        
        assert record.status == InjectionStatus.FAILED
        assert 'not found' in record.error_message.lower()
    
    def test_hash_content(self, injector):
        """Test content hashing."""
        hash1 = injector._hash_content("test content")
        hash2 = injector._hash_content("test content")
        hash3 = injector._hash_content("different content")
        
        # Same content = same hash
        assert hash1 == hash2
        # Different content = different hash
        assert hash1 != hash3
        # Hash is truncated
        assert len(hash1) == 16
    
    def test_validate_soul_file_valid(self, injector, sample_soul_content):
        """Test validation of valid SOUL.md."""
        # Create test file
        agent_id = 'test_agent'
        agent_dir = os.path.join(injector.souls_base_path, agent_id)
        os.makedirs(agent_dir, exist_ok=True)
        
        file_path = os.path.join(agent_dir, 'SOUL.md')
        with open(file_path, 'w') as f:
            f.write(sample_soul_content)
        
        validation = injector.validate_soul_file(agent_id)
        
        assert validation['valid'] is True
        assert len(validation['issues']) == 0
        assert 'Identity' in validation['sections_found']
    
    def test_validate_soul_file_missing_section(self, injector):
        """Test validation with missing required section."""
        content = """# SOUL.md

## Identity

Test agent.
"""
        # Create test file
        agent_id = 'test_agent'
        agent_dir = os.path.join(injector.souls_base_path, agent_id)
        os.makedirs(agent_dir, exist_ok=True)
        
        file_path = os.path.join(agent_dir, 'SOUL.md')
        with open(file_path, 'w') as f:
            f.write(content)
        
        validation = injector.validate_soul_file(agent_id)
        
        assert validation['valid'] is False
        assert any('Operational Context' in issue for issue in validation['issues'])
    
    def test_validate_soul_file_not_exists(self, injector):
        """Test validation when file doesn't exist."""
        validation = injector.validate_soul_file('nonexistent')
        
        assert validation['valid'] is False
        assert any('does not exist' in issue for issue in validation['issues'])
    
    def test_get_injection_history(self, injector, sample_rule):
        """Test retrieving injection history."""
        # Create test file and inject
        agent_id = 'test_agent'
        agent_dir = os.path.join(injector.souls_base_path, agent_id)
        os.makedirs(agent_dir, exist_ok=True)
        
        file_path = os.path.join(agent_dir, 'SOUL.md')
        with open(file_path, 'w') as f:
            f.write("# SOUL.md\n\n## Identity\n\nTest.")
        
        record = injector.inject_rules(agent_id, [sample_rule])
        
        # Get history
        history = injector.get_injection_history()
        
        assert len(history) == 1
        assert history[0].id == record.id
        
        # Filter by agent
        filtered = injector.get_injection_history(agent_id=agent_id)
        assert len(filtered) == 1
        
        # Filter by status
        filtered = injector.get_injection_history(status=InjectionStatus.INJECTED)
        assert len(filtered) == 1
    
    def test_bulk_inject(self, injector, sample_rule):
        """Test bulk injection for multiple agents."""
        # Create test files for multiple agents
        for agent_id in ['agent1', 'agent2']:
            agent_dir = os.path.join(injector.souls_base_path, agent_id)
            os.makedirs(agent_dir, exist_ok=True)
            
            file_path = os.path.join(agent_dir, 'SOUL.md')
            with open(file_path, 'w') as f:
                f.write(f"# SOUL.md\n\n## Identity\n\n{agent_id}.")
        
        # Bulk inject
        injection_plan = {
            'agent1': [sample_rule],
            'agent2': [sample_rule],
        }
        
        results = injector.bulk_inject(injection_plan)
        
        assert len(results) == 2
        assert results['agent1'].status == InjectionStatus.INJECTED
        assert results['agent2'].status == InjectionStatus.INJECTED


class TestInjectionRecord:
    """Tests for InjectionRecord dataclass."""
    
    def test_record_creation(self):
        """Test creating injection record."""
        record = InjectionRecord(
            id="record-123",
            rule_id="rule-456",
            agent_id="temujin",
            soul_file_path="/path/to/SOUL.md",
            injected_at=datetime.utcnow(),
            status=InjectionStatus.INJECTED,
            original_content_hash="abc123",
            injected_content="new content",
            git_commit_hash="def789",
        )
        
        assert record.id == "record-123"
        assert record.status == InjectionStatus.INJECTED
        assert record.git_commit_hash == "def789"
    
    def test_record_without_git(self):
        """Test record without git commit."""
        record = InjectionRecord(
            id="record-123",
            rule_id="rule-456",
            agent_id="temujin",
            soul_file_path="/path/to/SOUL.md",
            injected_at=datetime.utcnow(),
            status=InjectionStatus.PENDING,
            original_content_hash="abc123",
            injected_content="content",
        )
        
        assert record.git_commit_hash is None


class TestGitIntegration:
    """Tests for git integration."""
    
    @patch('tools.kurultai.soul_injector.subprocess.run')
    def test_verify_git_available(self, mock_run):
        """Test git verification when available."""
        mock_run.return_value = Mock(returncode=0)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            injector = SOULInjector(
                souls_base_path=tmpdir,
                enable_git=True,
            )
            
            assert injector.enable_git is True
    
    @patch('tools.kurultai.soul_injector.subprocess.run')
    def test_verify_git_not_available(self, mock_run):
        """Test git verification when not available."""
        mock_run.side_effect = FileNotFoundError()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            injector = SOULInjector(
                souls_base_path=tmpdir,
                enable_git=True,
            )
            
            assert injector.enable_git is False
    
    @patch('tools.kurultai.soul_injector.subprocess.run')
    def test_git_commit(self, mock_run):
        """Test git commit functionality."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="abc123def456\n",
        )
        
        sample_rule = {
            'id': 'rule-123',
            'name': 'test_error_handling',
            'description': 'Always handle errors properly',
            'rule_type': 'error_handling',
            'priority': 3,
            'effectiveness_score': 0.85,
            'conditions': ['error_rate > 0.1'],
            'actions': ['Add try-except blocks', 'Log errors'],
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            injector = SOULInjector(
                souls_base_path=tmpdir,
                enable_git=True,
            )
            
            # Create test file
            agent_id = 'test_agent'
            agent_dir = os.path.join(injector.souls_base_path, agent_id)
            os.makedirs(agent_dir, exist_ok=True)
            
            file_path = os.path.join(agent_dir, 'SOUL.md')
            with open(file_path, 'w') as f:
                f.write("# SOUL.md\n\n## Identity\n\nTest.")
            
            # Inject with git
            record = injector.inject_rules(agent_id, [sample_rule])
            
            assert record.git_commit_hash is not None
            assert record.git_commit_hash == "abc123def456"


class TestSyncWithMetaLearning:
    """Tests for integration with MetaLearningEngine."""
    
    def test_sync_with_meta_learning_engine(self):
        """Test syncing with meta learning engine."""
        from tools.kurultai.meta_learning_engine import MetaLearningEngine, MetaRule
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create mock engine
            mock_engine = Mock(spec=MetaLearningEngine)
            
            # Create test rules
            rule1 = MetaRule(
                id="rule-1",
                name="rule_one",
                description="Test rule one",
                rule_type="general",
                source_cluster_id="c1",
                target_agents=["temujin"],
                conditions=[],
                actions=[],
            )
            rule2 = MetaRule(
                id="rule-2",
                name="rule_two",
                description="Test rule two",
                rule_type="general",
                source_cluster_id="c2",
                target_agents=["chagatai"],
                conditions=[],
                actions=[],
            )
            
            mock_engine.rules = {
                "rule-1": rule1,
                "rule-2": rule2,
            }
            mock_engine.inject_rules.return_value = {
                "temujin": ["rule-1"],
                "chagatai": ["rule-2"],
            }
            
            # Create injector
            injector = SOULInjector(
                souls_base_path=tmpdir,
                enable_git=False,
            )
            
            # Create test files
            for agent_id, mapped_dir in [('temujin', 'developer'), ('chagatai', 'writer')]:
                agent_dir = os.path.join(injector.souls_base_path, mapped_dir)
                os.makedirs(agent_dir, exist_ok=True)
                
                file_path = os.path.join(agent_dir, 'SOUL.md')
                with open(file_path, 'w') as f:
                    f.write(f"# SOUL.md\n\n## Identity\n\n{agent_id}.")
            
            # Sync
            result = injector.sync_with_meta_learning_engine(mock_engine)
            
            assert result['agents_processed'] == 2
            assert result['rules_injected'] == 2
            assert 'temujin' in result['records']
            assert 'chagatai' in result['records']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
