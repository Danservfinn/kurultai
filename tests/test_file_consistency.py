"""
Test Suite for Ögedei File Consistency Protocol

Tests the file consistency functionality including:
- Checksum computation
- File version recording
- Conflict detection
- Escalation to Kublai
- Resolution workflows
"""

import pytest
import hashlib
import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock, PropertyMock

import sys
sys.path.insert(0, '/Users/kurultai/molt')

from tools.file_consistency import (
    FileConsistencyChecker,
    FileConsistencyError,
    ConflictNotFoundError,
    create_file_consistency_checker,
    detect_and_escalate,
    record_file_version
)


class MockContextManager:
    """Helper class to mock context managers properly."""
    def __init__(self, return_value):
        self.return_value = return_value

    def __enter__(self):
        return self.return_value

    def __exit__(self, *args):
        pass


class TestFileConsistencyCheckerInit:
    """Tests for FileConsistencyChecker initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        memory = Mock()
        checker = FileConsistencyChecker(memory)

        assert checker.memory == memory
        assert checker.monitored_files == FileConsistencyChecker.DEFAULT_MONITORED_FILES
        assert checker.escalation_threshold == 3
        assert checker.escalation_window_seconds == 300
        assert checker.content_preview_length == 200
        assert checker._checksum_cache == {}

    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        memory = Mock()
        custom_files = ["/custom/file1.md", "/custom/file2.md"]

        checker = FileConsistencyChecker(
            memory=memory,
            monitored_files=custom_files,
            escalation_threshold=5,
            escalation_window_seconds=600,
            content_preview_length=500
        )

        assert checker.monitored_files == custom_files
        assert checker.escalation_threshold == 5
        assert checker.escalation_window_seconds == 600
        assert checker.content_preview_length == 500

    def test_init_copies_default_list(self):
        """Test that default list is copied, not referenced."""
        memory = Mock()
        checker1 = FileConsistencyChecker(memory)
        checker2 = FileConsistencyChecker(memory)

        checker1.monitored_files.append("/new/file.md")

        assert "/new/file.md" not in checker2.monitored_files


class TestComputeChecksum:
    """Tests for checksum computation."""

    def test_compute_checksum_success(self):
        """Test successful checksum computation."""
        memory = Mock()
        checker = FileConsistencyChecker(memory)

        # Create a temporary file with known content
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            checksum = checker.compute_checksum(temp_path)
            expected = hashlib.sha256("test content".encode()).hexdigest()
            assert checksum == expected
        finally:
            os.unlink(temp_path)

    def test_compute_checksum_binary_content(self):
        """Test checksum computation with binary content."""
        memory = Mock()
        checker = FileConsistencyChecker(memory)

        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(b"\x00\x01\x02\x03")
            temp_path = f.name

        try:
            checksum = checker.compute_checksum(temp_path)
            expected = hashlib.sha256(b"\x00\x01\x02\x03").hexdigest()
            assert checksum == expected
        finally:
            os.unlink(temp_path)

    def test_compute_checksum_file_not_found(self):
        """Test checksum computation for non-existent file."""
        memory = Mock()
        checker = FileConsistencyChecker(memory)

        result = checker.compute_checksum("/nonexistent/path/file.txt")
        assert result is None

    def test_compute_checksum_large_file(self):
        """Test checksum computation for large file (chunked reading)."""
        memory = Mock()
        checker = FileConsistencyChecker(memory)

        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            # Write 100KB of data
            f.write(b"x" * (100 * 1024))
            temp_path = f.name

        try:
            checksum = checker.compute_checksum(temp_path)
            expected = hashlib.sha256(b"x" * (100 * 1024)).hexdigest()
            assert checksum == expected
        finally:
            os.unlink(temp_path)


class TestReadContentPreview:
    """Tests for content preview reading."""

    def test_read_content_preview_success(self):
        """Test successful content preview reading."""
        memory = Mock()
        checker = FileConsistencyChecker(memory, content_preview_length=50)

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("a" * 100)
            temp_path = f.name

        try:
            preview = checker._read_content_preview(temp_path)
            assert preview == "a" * 50
        finally:
            os.unlink(temp_path)

    def test_read_content_preview_shorter_than_limit(self):
        """Test preview when content is shorter than limit."""
        memory = Mock()
        checker = FileConsistencyChecker(memory, content_preview_length=100)

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("short")
            temp_path = f.name

        try:
            preview = checker._read_content_preview(temp_path)
            assert preview == "short"
        finally:
            os.unlink(temp_path)

    def test_read_content_preview_file_not_found(self):
        """Test preview for non-existent file."""
        memory = Mock()
        checker = FileConsistencyChecker(memory)

        preview = checker._read_content_preview("/nonexistent/file.txt")
        assert preview == ""

    def test_read_content_preview_unicode(self):
        """Test preview with unicode content."""
        memory = Mock()
        checker = FileConsistencyChecker(memory, content_preview_length=50)

        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as f:
            f.write("Hello 世界 🌍")
            temp_path = f.name

        try:
            preview = checker._read_content_preview(temp_path)
            assert "Hello 世界" in preview
        finally:
            os.unlink(temp_path)


class TestRecordVersion:
    """Tests for recording file versions."""

    def test_record_version_success(self):
        """Test successful version recording."""
        memory = Mock()
        memory._generate_id = Mock(return_value="test-version-id")
        memory._now = Mock(return_value=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"version_id": "test-version-id"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        checker = FileConsistencyChecker(memory)

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            version_id = checker.record_version(temp_path, "developer")

            assert version_id == "test-version-id"
            mock_session.run.assert_called_once()

            # Verify cache was updated
            assert temp_path in checker._checksum_cache
            assert "developer" in checker._checksum_cache[temp_path]
        finally:
            os.unlink(temp_path)

    def test_record_version_file_not_found(self):
        """Test version recording for non-existent file."""
        memory = Mock()
        checker = FileConsistencyChecker(memory)

        version_id = checker.record_version("/nonexistent/file.txt", "developer")
        assert version_id is None

    def test_record_version_fallback_mode(self):
        """Test version recording in fallback mode (no session)."""
        memory = Mock()
        memory._generate_id = Mock(return_value="fallback-version-id")
        memory._now = Mock(return_value=datetime.now(timezone.utc))
        memory._session = Mock(return_value=MockContextManager(None))

        checker = FileConsistencyChecker(memory)

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            version_id = checker.record_version(temp_path, "developer")
            assert version_id == "fallback-version-id"
        finally:
            os.unlink(temp_path)


class TestCheckConsistency:
    """Tests for consistency checking."""

    def test_check_consistency_no_conflict(self):
        """Test consistency check with no conflicts."""
        memory = Mock()
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        checker = FileConsistencyChecker(memory)

        # Mock get_file_history to return single version
        checker.get_file_history = Mock(return_value=[
            {
                "id": "v1",
                "file_path": "/test/file.md",
                "agent": "developer",
                "checksum": "abc123",
                "created_at": datetime.now(timezone.utc)
            }
        ])

        result = checker.check_consistency("/test/file.md")
        assert result is None

    def test_check_consistency_conflict_detected(self):
        """Test conflict detection with different checksums."""
        memory = Mock()
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        checker = FileConsistencyChecker(memory)

        # Mock get_file_history to return conflicting versions
        checker.get_file_history = Mock(return_value=[
            {
                "id": "v2",
                "file_path": "/test/file.md",
                "agent": "writer",
                "checksum": "def456",
                "created_at": datetime.now(timezone.utc)
            },
            {
                "id": "v1",
                "file_path": "/test/file.md",
                "agent": "developer",
                "checksum": "abc123",
                "created_at": datetime.now(timezone.utc) - timedelta(minutes=5)
            }
        ])

        result = checker.check_consistency("/test/file.md")

        assert result is not None
        assert result["file_path"] == "/test/file.md"
        assert "developer" in result["agents_involved"]
        assert "writer" in result["agents_involved"]
        assert "abc123" in result["checksums"]
        assert "def456" in result["checksums"]

    def test_check_consistency_single_version(self):
        """Test consistency with only one version."""
        memory = Mock()
        checker = FileConsistencyChecker(memory)

        checker.get_file_history = Mock(return_value=[
            {"id": "v1", "agent": "developer", "checksum": "abc123"}
        ])

        result = checker.check_consistency("/test/file.md")
        assert result is None


class TestCalculateConflictSeverity:
    """Tests for conflict severity calculation."""

    def test_calculate_severity_critical_many_agents(self):
        """Test critical severity with 4+ agents."""
        memory = Mock()
        checker = FileConsistencyChecker(memory)

        versions = [
            {"agent": f"agent{i}", "created_at": datetime.now(timezone.utc)}
            for i in range(4)
        ]

        severity = checker._calculate_conflict_severity(4, versions)
        assert severity == "critical"

    def test_calculate_severity_high_three_agents(self):
        """Test high severity with 3 agents."""
        memory = Mock()
        now = datetime.now(timezone.utc)
        memory._now = Mock(return_value=now)
        checker = FileConsistencyChecker(memory)

        versions = [
            {"agent": f"agent{i}", "created_at": now - timedelta(minutes=i*10)}
            for i in range(3)
        ]

        severity = checker._calculate_conflict_severity(3, versions)
        assert severity == "high"

    def test_calculate_severity_medium_two_agents(self):
        """Test medium severity with 2 agents."""
        memory = Mock()
        now = datetime.now(timezone.utc)
        memory._now = Mock(return_value=now)
        checker = FileConsistencyChecker(memory)

        versions = [
            {"agent": "agent1", "created_at": now - timedelta(minutes=10)},
            {"agent": "agent2", "created_at": now - timedelta(minutes=5)}
        ]

        severity = checker._calculate_conflict_severity(2, versions)
        assert severity == "medium"

    def test_calculate_severity_critical_recent_conflicts(self):
        """Test critical severity with many recent conflicts."""
        memory = Mock()
        now = datetime.now(timezone.utc)
        memory._now = Mock(return_value=now)
        checker = FileConsistencyChecker(memory)

        versions = [
            {"agent": f"agent{i}", "created_at": now - timedelta(seconds=30)}
            for i in range(3)
        ]

        severity = checker._calculate_conflict_severity(3, versions)
        assert severity == "critical"


class TestDetectConflicts:
    """Tests for conflict detection across monitored files."""

    def test_detect_conflicts_no_conflicts(self):
        """Test detection with no conflicts."""
        memory = Mock()
        checker = FileConsistencyChecker(memory, monitored_files=["/test/file1.md"])

        checker.check_consistency = Mock(return_value=None)

        conflicts = checker.detect_conflicts()
        assert conflicts == []

    def test_detect_conflicts_with_conflict(self):
        """Test detection with conflicts."""
        memory = Mock()
        checker = FileConsistencyChecker(memory, monitored_files=["/test/file1.md"])

        conflict = {
            "file_path": "/test/file1.md",
            "agents_involved": ["agent1", "agent2"],
            "severity": "medium"
        }

        checker.check_consistency = Mock(return_value=conflict)
        checker._create_conflict_record = Mock(return_value="conflict-id-123")

        conflicts = checker.detect_conflicts()

        assert len(conflicts) == 1
        assert conflicts[0]["id"] == "conflict-id-123"

    def test_detect_conflicts_expands_wildcards(self):
        """Test detection with wildcard expansion."""
        memory = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            for i in range(3):
                with open(os.path.join(tmpdir, f"file{i}.md"), 'w') as f:
                    f.write(f"content {i}")

            checker = FileConsistencyChecker(
                memory,
                monitored_files=[os.path.join(tmpdir, "*.md")]
            )

            checker.check_consistency = Mock(return_value=None)

            conflicts = checker.detect_conflicts()

            # Should have checked 3 files
            assert checker.check_consistency.call_count == 3


class TestEscalateConflict:
    """Tests for conflict escalation."""

    def test_escalate_conflict_success(self):
        """Test successful conflict escalation."""
        memory = Mock()
        memory._now = Mock(return_value=datetime.now(timezone.utc))
        memory.create_notification = Mock()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"conflict_id": "conflict-123"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        checker = FileConsistencyChecker(memory)
        checker.get_conflict = Mock(return_value={
            "id": "conflict-123",
            "file_path": "/test/file.md"
        })

        result = checker.escalate_conflict("conflict-123", "Test escalation reason")

        assert result is True
        mock_session.run.assert_called_once()
        memory.create_notification.assert_called_once()

    def test_escalate_conflict_not_found(self):
        """Test escalation for non-existent conflict."""
        memory = Mock()
        checker = FileConsistencyChecker(memory)
        checker.get_conflict = Mock(return_value=None)

        with pytest.raises(ConflictNotFoundError):
            checker.escalate_conflict("nonexistent-id", "reason")

    def test_escalate_conflict_fallback_mode(self):
        """Test escalation in fallback mode."""
        memory = Mock()
        memory._session = Mock(return_value=MockContextManager(None))

        checker = FileConsistencyChecker(memory)
        checker.get_conflict = Mock(return_value={
            "id": "conflict-123",
            "file_path": "/test/file.md"
        })

        result = checker.escalate_conflict("conflict-123", "reason")
        assert result is True


class TestResolveConflict:
    """Tests for conflict resolution."""

    def test_resolve_conflict_success(self):
        """Test successful conflict resolution."""
        memory = Mock()
        memory._now = Mock(return_value=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"conflict_id": "conflict-123"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        checker = FileConsistencyChecker(memory)

        result = checker.resolve_conflict(
            "conflict-123",
            "developer",
            "Fixed the conflict"
        )

        assert result is True
        mock_session.run.assert_called_once()

    def test_resolve_conflict_not_found(self):
        """Test resolution for non-existent conflict."""
        memory = Mock()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        checker = FileConsistencyChecker(memory)

        with pytest.raises(ConflictNotFoundError):
            checker.resolve_conflict("nonexistent-id", "developer")

    def test_resolve_conflict_fallback_mode(self):
        """Test resolution in fallback mode."""
        memory = Mock()
        memory._session = Mock(return_value=MockContextManager(None))

        checker = FileConsistencyChecker(memory)

        result = checker.resolve_conflict("conflict-123", "developer")
        assert result is True


class TestGetFileHistory:
    """Tests for retrieving file version history."""

    def test_get_file_history_success(self):
        """Test successful history retrieval."""
        memory = Mock()

        mock_session = MagicMock()
        mock_result = [
            {"v": {"id": "v1", "agent": "developer", "checksum": "abc123"}},
            {"v": {"id": "v2", "agent": "writer", "checksum": "def456"}}
        ]
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        checker = FileConsistencyChecker(memory)
        history = checker.get_file_history("/test/file.md")

        assert len(history) == 2
        assert history[0]["id"] == "v1"
        assert history[1]["id"] == "v2"

    def test_get_file_history_empty(self):
        """Test history retrieval with no versions."""
        memory = Mock()

        mock_session = MagicMock()
        mock_session.run.return_value = []

        memory._session = Mock(return_value=MockContextManager(mock_session))

        checker = FileConsistencyChecker(memory)
        history = checker.get_file_history("/test/file.md")

        assert history == []

    def test_get_file_history_fallback_mode(self):
        """Test history retrieval in fallback mode."""
        memory = Mock()
        memory._session = Mock(return_value=MockContextManager(None))

        checker = FileConsistencyChecker(memory)
        history = checker.get_file_history("/test/file.md")

        assert history == []


class TestListConflicts:
    """Tests for listing conflicts."""

    def test_list_conflicts_no_filters(self):
        """Test listing all conflicts."""
        memory = Mock()

        mock_session = MagicMock()
        mock_result = [
            {"c": {"id": "c1", "status": "detected", "severity": "high"}},
            {"c": {"id": "c2", "status": "resolved", "severity": "low"}}
        ]
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        checker = FileConsistencyChecker(memory)
        conflicts = checker.list_conflicts()

        assert len(conflicts) == 2

    def test_list_conflicts_with_status_filter(self):
        """Test listing conflicts with status filter."""
        memory = Mock()

        mock_session = MagicMock()
        mock_result = [{"c": {"id": "c1", "status": "detected"}}]
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        checker = FileConsistencyChecker(memory)
        conflicts = checker.list_conflicts(status="detected")

        assert len(conflicts) == 1
        # Verify the filter was applied in query
        call_args = mock_session.run.call_args
        assert "status" in str(call_args)

    def test_list_conflicts_fallback_mode(self):
        """Test listing conflicts in fallback mode."""
        memory = Mock()
        memory._session = Mock(return_value=MockContextManager(None))

        checker = FileConsistencyChecker(memory)
        conflicts = checker.list_conflicts()

        assert conflicts == []


class TestConflictSummary:
    """Tests for conflict summary."""

    def test_get_conflict_summary_success(self):
        """Test successful summary retrieval."""
        memory = Mock()

        mock_session = MagicMock()
        mock_result = [
            {"status": "detected", "severity": "high", "count": 2},
            {"status": "resolved", "severity": "low", "count": 1}
        ]
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        checker = FileConsistencyChecker(memory)
        summary = checker.get_conflict_summary()

        assert summary["total"] == 3
        assert summary["by_status"]["detected"] == 2
        assert summary["by_status"]["resolved"] == 1
        assert summary["by_severity"]["high"] == 2
        assert summary["by_severity"]["low"] == 1

    def test_get_conflict_summary_fallback_mode(self):
        """Test summary in fallback mode."""
        memory = Mock()
        memory._session = Mock(return_value=MockContextManager(None))

        checker = FileConsistencyChecker(memory)
        summary = checker.get_conflict_summary()

        assert summary["total"] == 0
        assert summary["by_status"]["detected"] == 0
        assert summary["by_severity"]["critical"] == 0


class TestCheckAndEscalateThreshold:
    """Tests for threshold checking and escalation."""

    def test_check_threshold_not_exceeded(self):
        """Test when threshold is not exceeded."""
        memory = Mock()
        checker = FileConsistencyChecker(memory, escalation_threshold=5)

        # Return fewer conflicts than threshold
        checker.get_recent_conflicts = Mock(return_value=[
            {"id": "c1", "status": "detected"},
            {"id": "c2", "status": "detected"}
        ])

        escalated = checker.check_and_escalate_threshold()

        assert escalated == []

    def test_check_threshold_exceeded(self):
        """Test when threshold is exceeded."""
        memory = Mock()
        checker = FileConsistencyChecker(memory, escalation_threshold=2)

        checker.get_recent_conflicts = Mock(return_value=[
            {"id": "c1", "status": "detected"},
            {"id": "c2", "status": "detected"},
            {"id": "c3", "status": "detected"}
        ])
        checker.escalate_conflict = Mock(return_value=True)

        escalated = checker.check_and_escalate_threshold()

        assert len(escalated) == 3
        assert checker.escalate_conflict.call_count == 3

    def test_check_threshold_skips_resolved(self):
        """Test that resolved conflicts are not escalated."""
        memory = Mock()
        checker = FileConsistencyChecker(memory, escalation_threshold=2)

        checker.get_recent_conflicts = Mock(return_value=[
            {"id": "c1", "status": "detected"},
            {"id": "c2", "status": "resolved"},  # Should not escalate
            {"id": "c3", "status": "escalated"}  # Should not escalate
        ])
        checker.escalate_conflict = Mock(return_value=True)

        escalated = checker.check_and_escalate_threshold()

        assert len(escalated) == 1
        checker.escalate_conflict.assert_called_once_with("c1", "Threshold exceeded: 3 conflicts in window")


class TestMonitoredFilesManagement:
    """Tests for managing monitored files list."""

    def test_add_monitored_file(self):
        """Test adding a file to monitored list."""
        memory = Mock()
        checker = FileConsistencyChecker(memory)

        checker.add_monitored_file("/new/file.md")

        assert "/new/file.md" in checker.monitored_files

    def test_add_duplicate_file(self):
        """Test adding duplicate file is ignored."""
        memory = Mock()
        checker = FileConsistencyChecker(memory, monitored_files=["/existing/file.md"])

        initial_count = len(checker.monitored_files)
        checker.add_monitored_file("/existing/file.md")

        assert len(checker.monitored_files) == initial_count

    def test_remove_monitored_file(self):
        """Test removing a file from monitored list."""
        memory = Mock()
        checker = FileConsistencyChecker(memory, monitored_files=["/file1.md", "/file2.md"])

        result = checker.remove_monitored_file("/file1.md")

        assert result is True
        assert "/file1.md" not in checker.monitored_files
        assert "/file2.md" in checker.monitored_files

    def test_remove_nonexistent_file(self):
        """Test removing a file not in the list."""
        memory = Mock()
        checker = FileConsistencyChecker(memory)

        result = checker.remove_monitored_file("/nonexistent/file.md")

        assert result is False

    def test_get_monitored_files_expands_wildcards(self):
        """Test that get_monitored_files expands wildcards."""
        memory = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                with open(os.path.join(tmpdir, f"file{i}.md"), 'w') as f:
                    f.write("content")

            checker = FileConsistencyChecker(
                memory,
                monitored_files=[os.path.join(tmpdir, "*.md")]
            )

            files = checker.get_monitored_files()

            assert len(files) == 3


class TestCreateIndexes:
    """Tests for index creation."""

    def test_create_indexes_success(self):
        """Test successful index creation."""
        memory = Mock()

        mock_session = MagicMock()
        mock_session.run.return_value = None

        memory._session = Mock(return_value=MockContextManager(mock_session))

        checker = FileConsistencyChecker(memory)
        created = checker.create_indexes()

        assert len(created) == 9  # 9 indexes defined
        assert mock_session.run.call_count == 9

    def test_create_indexes_fallback_mode(self):
        """Test index creation in fallback mode."""
        memory = Mock()
        memory._session = Mock(return_value=MockContextManager(None))

        checker = FileConsistencyChecker(memory)
        created = checker.create_indexes()

        assert created == []


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_file_consistency_checker(self):
        """Test factory function."""
        memory = Mock()
        checker = create_file_consistency_checker(
            memory,
            monitored_files=["/test/file.md"],
            escalation_threshold=5
        )

        assert isinstance(checker, FileConsistencyChecker)
        assert checker.monitored_files == ["/test/file.md"]
        assert checker.escalation_threshold == 5

    def test_record_file_version(self):
        """Test record_file_version convenience function."""
        checker = Mock()
        checker.record_version.return_value = "version-123"

        result = record_file_version(checker, "/test/file.md", "developer")

        assert result == "version-123"
        checker.record_version.assert_called_once_with("/test/file.md", "developer")

    def test_detect_and_escalate(self):
        """Test detect_and_escalate convenience function."""
        checker = Mock()
        checker.detect_conflicts.return_value = [
            {"id": "c1"},
            {"id": "c2"}
        ]
        checker.check_and_escalate_threshold.return_value = ["c1"]

        result = detect_and_escalate(checker)

        assert result["conflicts_detected"] == 2
        assert result["conflict_ids"] == ["c1", "c2"]
        assert result["escalated_ids"] == ["c1"]
        assert result["threshold_exceeded"] is True


class TestExpandWildcardPath:
    """Tests for wildcard path expansion."""

    def test_expand_wildcard(self):
        """Test wildcard expansion."""
        memory = Mock()
        checker = FileConsistencyChecker(memory)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            for i in range(3):
                with open(os.path.join(tmpdir, f"file{i}.md"), 'w') as f:
                    f.write("content")

            pattern = os.path.join(tmpdir, "*.md")
            expanded = checker._expand_wildcard_path(pattern)

            assert len(expanded) == 3

    def test_expand_no_matches(self):
        """Test wildcard with no matches."""
        memory = Mock()
        checker = FileConsistencyChecker(memory)

        expanded = checker._expand_wildcard_path("/nonexistent/*.xyz")

        assert expanded == []


class TestGetRecentConflicts:
    """Tests for getting recent conflicts."""

    def test_get_recent_conflicts_success(self):
        """Test successful retrieval of recent conflicts."""
        memory = Mock()
        memory._now = Mock(return_value=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc))

        mock_session = MagicMock()
        mock_result = [
            {"c": {"id": "c1", "created_at": datetime(2025, 1, 1, 11, 55, 0, tzinfo=timezone.utc)}},
            {"c": {"id": "c2", "created_at": datetime(2025, 1, 1, 11, 58, 0, tzinfo=timezone.utc)}}
        ]
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        checker = FileConsistencyChecker(memory)
        conflicts = checker.get_recent_conflicts(window_seconds=600)

        assert len(conflicts) == 2

    def test_get_recent_conflicts_fallback_mode(self):
        """Test recent conflicts in fallback mode."""
        memory = Mock()
        memory._session = Mock(return_value=MockContextManager(None))
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        checker = FileConsistencyChecker(memory)
        conflicts = checker.get_recent_conflicts()

        assert conflicts == []


class TestGetConflict:
    """Tests for getting a single conflict."""

    def test_get_conflict_success(self):
        """Test successful conflict retrieval."""
        memory = Mock()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"c": {"id": "c1", "status": "detected"}}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        checker = FileConsistencyChecker(memory)
        conflict = checker.get_conflict("c1")

        assert conflict is not None
        assert conflict["id"] == "c1"

    def test_get_conflict_not_found(self):
        """Test getting non-existent conflict."""
        memory = Mock()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        checker = FileConsistencyChecker(memory)
        conflict = checker.get_conflict("nonexistent")

        assert conflict is None

    def test_get_conflict_fallback_mode(self):
        """Test getting conflict in fallback mode."""
        memory = Mock()
        memory._session = Mock(return_value=MockContextManager(None))

        checker = FileConsistencyChecker(memory)
        conflict = checker.get_conflict("c1")

        assert conflict is None


class TestCreateConflictRecord:
    """Tests for creating conflict records."""

    def test_create_conflict_record_success(self):
        """Test successful conflict record creation."""
        memory = Mock()
        memory._generate_id = Mock(return_value="conflict-123")
        memory._now = Mock(return_value=datetime.now(timezone.utc))

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"conflict_id": "conflict-123"}
        mock_session.run.return_value = mock_result

        memory._session = Mock(return_value=MockContextManager(mock_session))

        checker = FileConsistencyChecker(memory)
        conflict_id = checker._create_conflict_record({
            "file_path": "/test/file.md",
            "agents_involved": ["agent1", "agent2"],
            "severity": "medium"
        })

        assert conflict_id == "conflict-123"

    def test_create_conflict_record_fallback_mode(self):
        """Test conflict record creation in fallback mode."""
        memory = Mock()
        memory._generate_id = Mock(return_value="conflict-123")
        memory._session = Mock(return_value=MockContextManager(None))

        checker = FileConsistencyChecker(memory)
        conflict_id = checker._create_conflict_record({
            "file_path": "/test/file.md",
            "agents_involved": ["agent1"],
            "severity": "low"
        })

        assert conflict_id == "conflict-123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
