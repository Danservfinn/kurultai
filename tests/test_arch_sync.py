"""
Tests for ArchitectureSync

Author: Chagatai (Writer Agent)
Date: 2026-02-09
"""

import pytest
import os
import tempfile
from datetime import datetime
from unittest.mock import Mock, patch
from typing import Dict, List, Any

from tools.kurultai.arch_sync import (
    ArchitectureSync,
    ArchitectureSection,
    SyncDirection,
    SyncConflict,
    SyncResult,
    ChangeType,
)


class TestArchitectureSection:
    """Tests for ArchitectureSection dataclass."""
    
    def test_section_creation(self):
        """Test creating architecture section."""
        section = ArchitectureSection(
            id="sec-123",
            title="Test Section",
            category="technical",
            section_order=1,
            content="Test content here.",
            content_summary="Summary",
            version="1.0",
            last_updated=datetime.utcnow(),
            source="file",
        )
        
        assert section.title == "Test Section"
        assert section.category == "technical"
        assert section.hash != ""
    
    def test_section_hash_computation(self):
        """Test hash computation."""
        section1 = ArchitectureSection(
            id="sec-1",
            title="Test",
            category="tech",
            section_order=1,
            content="Content A",
            content_summary="Summary",
            version="1.0",
            last_updated=datetime.utcnow(),
            source="file",
        )
        
        section2 = ArchitectureSection(
            id="sec-2",
            title="Test",
            category="tech",
            section_order=1,
            content="Content A",
            content_summary="Summary",
            version="1.0",
            last_updated=datetime.utcnow(),
            source="file",
        )
        
        section3 = ArchitectureSection(
            id="sec-3",
            title="Test",
            category="tech",
            section_order=1,
            content="Content B",  # Different
            content_summary="Summary",
            version="1.0",
            last_updated=datetime.utcnow(),
            source="file",
        )
        
        # Same content = same hash
        assert section1.hash == section2.hash
        # Different content = different hash
        assert section1.hash != section3.hash
    
    def test_section_to_dict(self):
        """Test section serialization."""
        section = ArchitectureSection(
            id="sec-123",
            title="Test",
            category="tech",
            section_order=1,
            content="Content",
            content_summary="Summary",
            version="1.0",
            last_updated=datetime.utcnow(),
            source="file",
            proposal=True,
            proposal_author="tester",
            proposal_approved=False,
        )
        
        d = section.to_dict()
        assert d['title'] == "Test"
        assert d['proposal'] is True
        assert d['proposal_author'] == "tester"


class TestArchitectureSync:
    """Tests for ArchitectureSync class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def sample_architecture_content(self) -> str:
        """Sample ARCHITECTURE.md content."""
        return """---
title: Kurultai Unified Architecture
version: 3.1
---

# Kurultai Unified Architecture

## Executive Summary

This is the executive summary.

## System Architecture

This describes the system architecture.

### Subsection

More details here.

## Security Considerations

Security info.
"""
    
    @pytest.fixture
    def sync(self, temp_dir):
        """Create sync with mocked Neo4j."""
        with patch('tools.kurultai.arch_sync.GraphDatabase') as mock_db:
            mock_driver = Mock()
            mock_db.driver.return_value = mock_driver
            
            arch_path = os.path.join(temp_dir, "ARCHITECTURE.md")
            sync = ArchitectureSync(
                architecture_file_path=arch_path,
                neo4j_uri="bolt://test:7687",
                neo4j_password="testpass",
            )
            sync._driver = mock_driver
            yield sync
    
    def test_initialization(self, temp_dir):
        """Test sync initialization."""
        with patch('tools.kurultai.arch_sync.GraphDatabase') as mock_db:
            mock_db.driver.return_value = Mock()
            
            sync = ArchitectureSync(
                architecture_file_path=os.path.join(temp_dir, "ARCHITECTURE.md"),
                neo4j_uri="bolt://test:7687",
                neo4j_password="testpass",
                require_approval_for_proposals=True,
            )
            
            assert sync.require_approval_for_proposals is True
            assert "ARCHITECTURE.md" in sync.architecture_file_path
    
    def test_parse_architecture_file(self, sync, sample_architecture_content):
        """Test parsing architecture file."""
        # Write test file
        with open(sync.architecture_file_path, 'w') as f:
            f.write(sample_architecture_content)
        
        sections = sync.parse_architecture_file()
        
        assert len(sections) == 3
        
        titles = [s.title for s in sections]
        assert "Executive Summary" in titles
        assert "System Architecture" in titles
        assert "Security Considerations" in titles
    
    def test_parse_architecture_file_not_exists(self, sync):
        """Test parsing non-existent file."""
        with pytest.raises(FileNotFoundError):
            sync.parse_architecture_file()
    
    def test_parse_frontmatter(self, sync):
        """Test frontmatter parsing."""
        content = """---
title: Test
custom_key: custom_value
---

# Content
"""
        frontmatter = sync._parse_frontmatter(content)
        
        assert frontmatter.get('title') == "Test"
        assert frontmatter.get('custom_key') == "custom_value"
    
    def test_determine_category(self, sync):
        """Test category determination."""
        assert sync._determine_category("System Architecture", "") == "architecture"
        assert sync._determine_category("Security Model", "") == "security"
        assert sync._determine_category("Deployment Guide", "") == "deployment"
        assert sync._determine_category("Monitoring", "") == "operations"
        assert sync._determine_category("Random Section", "") == "general"
    
    def test_generate_summary(self, sync):
        """Test summary generation."""
        content = """
First paragraph of the section.

Second paragraph with `code` and [links](http://example.com).

```python
code block
```

More text here.
"""
        summary = sync._generate_summary(content, max_length=50)
        
        assert "First paragraph" in summary
        assert "`code`" not in summary  # Code removed
        assert "[links]" not in summary  # Links cleaned
        assert "```" not in summary  # Code blocks removed
    
    def test_detect_changes(self, sync):
        """Test change detection."""
        now = datetime.utcnow()
        
        file_sections = [
            ArchitectureSection(
                id="s1", title="Section A", category="tech",
                section_order=1, content="Content A",
                content_summary="Summary A", version="1.0",
                last_updated=now, source="file",
            ),
            ArchitectureSection(
                id="s2", title="Section B", category="tech",
                section_order=2, content="Content B",
                content_summary="Summary B", version="1.0",
                last_updated=now, source="file",
            ),
        ]
        
        neo4j_sections = [
            ArchitectureSection(
                id="s1", title="Section A", category="tech",
                section_order=1, content="Content A",
                content_summary="Summary A", version="1.0",
                last_updated=now, source="neo4j",
            ),
            ArchitectureSection(
                id="s3", title="Section C", category="tech",
                section_order=3, content="Content C",
                content_summary="Summary C", version="1.0",
                last_updated=now, source="neo4j",
            ),
        ]
        
        changes = sync.detect_changes(file_sections, neo4j_sections)
        
        assert len(changes['added']) == 1  # Section B
        assert len(changes['deleted']) == 1  # Section C
        assert len(changes['unchanged']) == 1  # Section A


class TestSyncOperations:
    """Tests for sync operations."""
    
    @pytest.fixture
    def mock_session(self):
        """Create mock Neo4j session."""
        return Mock()
    
    @pytest.fixture
    def sync_with_mocked_session(self, mock_session):
        """Create sync with fully mocked session."""
        with patch('tools.kurultai.arch_sync.GraphDatabase') as mock_db:
            mock_driver = Mock()
            mock_driver.session.return_value.__enter__ = Mock(return_value=mock_session)
            mock_driver.session.return_value.__exit__ = Mock(return_value=False)
            mock_db.driver.return_value = mock_driver
            
            with tempfile.TemporaryDirectory() as tmpdir:
                sync = ArchitectureSync(
                    architecture_file_path=os.path.join(tmpdir, "ARCHITECTURE.md"),
                )
                sync._driver = mock_driver
                yield sync, mock_session
    
    def test_sync_file_to_neo4j(self, sync_with_mocked_session):
        """Test syncing file to Neo4j."""
        sync, mock_session = sync_with_mocked_session
        
        # Create test sections
        now = datetime.utcnow()
        sections = [
            ArchitectureSection(
                id="s1", title="Section A", category="tech",
                section_order=1, content="Content A",
                content_summary="Summary A", version="1.0",
                last_updated=now, source="file",
            ),
        ]
        
        result = sync.sync_file_to_neo4j(sections=sections)
        
        assert result.success is True
        assert result.direction == SyncDirection.FILE_TO_NEO4J
        assert result.sections_synced == 1
        mock_session.run.assert_called()
    
    def test_sync_file_to_neo4j_dry_run(self, sync_with_mocked_session):
        """Test dry run sync."""
        sync, mock_session = sync_with_mocked_session
        
        now = datetime.utcnow()
        sections = [
            ArchitectureSection(
                id="s1", title="Section A", category="tech",
                section_order=1, content="Content A",
                content_summary="Summary A", version="1.0",
                last_updated=now, source="file",
            ),
        ]
        
        result = sync.sync_file_to_neo4j(sections=sections, dry_run=True)
        
        assert result.success is True
        # Should not actually write
        assert not mock_session.run.called
    
    def test_sync_neo4j_to_file(self, sync_with_mocked_session):
        """Test syncing Neo4j to file."""
        sync, mock_session = sync_with_mocked_session
        
        # Mock Neo4j results
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result
        
        # Write initial file
        with open(sync.architecture_file_path, 'w') as f:
            f.write("# Architecture\n\n## Section\n\nContent.\n")
        
        result = sync.sync_neo4j_to_file(dry_run=True)
        
        assert result.direction == SyncDirection.NEO4J_TO_FILE
    
    def test_create_proposal(self, sync_with_mocked_session):
        """Test creating proposal."""
        sync, mock_session = sync_with_mocked_session
        
        mock_result = Mock()
        mock_result.single.return_value = {'max_order': 5}
        mock_session.run.return_value = mock_result
        
        proposal_id = sync.create_proposal(
            title="New Section",
            content="New content",
            category="technical",
            author="kublai",
        )
        
        assert proposal_id is not None
        mock_session.run.assert_called()
    
    def test_create_proposal_unauthorized(self, sync_with_mocked_session):
        """Test creating proposal with unauthorized author."""
        sync, mock_session = sync_with_mocked_session
        
        proposal_id = sync.create_proposal(
            title="New Section",
            content="Content",
            category="tech",
            author="unauthorized_user",
        )
        
        assert proposal_id is None
    
    def test_approve_proposal(self, sync_with_mocked_session):
        """Test approving proposal."""
        sync, mock_session = sync_with_mocked_session
        
        mock_result = Mock()
        mock_result.single.return_value = {'id': 'proposal-123'}
        mock_session.run.return_value = mock_result
        
        result = sync.approve_proposal("proposal-123", approver="kublai")
        
        assert result is True
    
    def test_approve_proposal_unauthorized(self, sync_with_mocked_session):
        """Test approving with unauthorized user."""
        sync, _ = sync_with_mocked_session
        
        result = sync.approve_proposal("proposal-123", approver="unauthorized")
        
        assert result is False
    
    def test_reject_proposal(self, sync_with_mocked_session):
        """Test rejecting proposal."""
        sync, mock_session = sync_with_mocked_session
        
        mock_result = Mock()
        mock_result.single.return_value = {'id': 'proposal-123'}
        mock_session.run.return_value = mock_result
        
        result = sync.reject_proposal(
            "proposal-123",
            rejector="kublai",
            reason="Duplicate content",
        )
        
        assert result is True
    
    def test_sync_bidirectional_with_conflicts(self, sync_with_mocked_session):
        """Test bidirectional sync with conflicts."""
        sync, mock_session = sync_with_mocked_session
        
        now = datetime.utcnow()
        
        # Write file with sections
        with open(sync.architecture_file_path, 'w') as f:
            f.write("""# Architecture

## Section A

File content.

## Section B

More file content.
""")
        
        # Mock Neo4j returning modified sections
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([
            {'as': {
                'id': 's1', 'title': 'Section A', 'category': 'tech',
                'section_order': 1, 'content': 'Different content',
                'content_summary': 'Summary', 'version': '1.0',
                'last_updated': now, 'hash': 'different_hash',
                'proposal': False,
            }},
        ]))
        mock_session.run.return_value = mock_result
        
        result = sync.sync_bidirectional(conflict_resolution='manual')
        
        assert result.success is False
        assert len(result.conflicts) > 0
        assert result.error_message is not None


class TestSyncResult:
    """Tests for SyncResult dataclass."""
    
    def test_result_creation(self):
        """Test creating sync result."""
        result = SyncResult(
            success=True,
            direction=SyncDirection.FILE_TO_NEO4J,
            sections_synced=5,
            changes={'synced': [{'title': 'Test'}]},
        )
        
        assert result.success is True
        assert result.sections_synced == 5
    
    def test_result_with_conflicts(self):
        """Test result with conflicts."""
        now = datetime.utcnow()
        
        conflict = SyncConflict(
            section_title="Section A",
            file_version=ArchitectureSection(
                id="s1", title="Section A", category="tech",
                section_order=1, content="File content",
                content_summary="", version="1.0",
                last_updated=now, source="file",
            ),
            neo4j_version=ArchitectureSection(
                id="s1", title="Section A", category="tech",
                section_order=1, content="Neo4j content",
                content_summary="", version="1.0",
                last_updated=now, source="neo4j",
            ),
            conflict_type="both_modified",
        )
        
        result = SyncResult(
            success=False,
            direction=SyncDirection.BIDIRECTIONAL,
            conflicts=[conflict],
            error_message="Conflicts need resolution",
        )
        
        assert len(result.conflicts) == 1
        assert result.conflicts[0].section_title == "Section A"


class TestRebuildArchitectureFile:
    """Tests for rebuilding architecture file."""
    
    def test_rebuild_file(self):
        """Test rebuilding file from sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('tools.kurultai.arch_sync.GraphDatabase') as mock_db:
                mock_db.driver.return_value = Mock()
                
                sync = ArchitectureSync(
                    architecture_file_path=os.path.join(tmpdir, "ARCHITECTURE.md"),
                )
                
                now = datetime.utcnow()
                sections = [
                    ArchitectureSection(
                        id="s2", title="Section B", category="tech",
                        section_order=2, content="Content B",
                        content_summary="Summary B", version="1.0",
                        last_updated=now, source="neo4j",
                    ),
                    ArchitectureSection(
                        id="s1", title="Section A", category="tech",
                        section_order=1, content="Content A",
                        content_summary="Summary A", version="1.0",
                        last_updated=now, source="neo4j",
                    ),
                ]
                
                content = sync._rebuild_architecture_file(sections)
                
                # Should be sorted by order
                assert content.index("Section A") < content.index("Section B")
                assert "---" in content  # Frontmatter
                assert "# Kurultai Unified Architecture" in content


class TestGetSyncStatus:
    """Tests for get_sync_status method."""
    
    def test_get_status_synced(self):
        """Test status when synced."""
        with tempfile.TemporaryDirectory() as tmpdir:
            arch_path = os.path.join(tmpdir, "ARCHITECTURE.md")
            
            # Create file
            with open(arch_path, 'w') as f:
                f.write("""# Architecture

## Section A

Content.
""")
            
            with patch('tools.kurultai.arch_sync.GraphDatabase') as mock_db:
                mock_driver = Mock()
                mock_session = Mock()
                mock_result = Mock()
                mock_result.__iter__ = Mock(return_value=iter([
                    {'as': {
                        'id': 's1', 'title': 'Section A', 'category': 'tech',
                        'section_order': 1, 'content': 'Content.',
                        'content_summary': 'Content.', 'version': '1.0',
                        'hash': '', 'proposal': False,
                    }},
                ]))
                mock_session.run.return_value = mock_result
                mock_driver.session.return_value.__enter__ = Mock(return_value=mock_session)
                mock_driver.session.return_value.__exit__ = Mock(return_value=False)
                mock_db.driver.return_value = mock_driver
                
                sync = ArchitectureSync(architecture_file_path=arch_path)
                sync._driver = mock_driver
                
                status = sync.get_sync_status()
                
                assert status['file_exists'] is True
                assert status['file_sections'] == 1
                assert status['synced'] is False  # Hash mismatch


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
