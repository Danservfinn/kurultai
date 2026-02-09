"""
Collaboration Protocol Tests - Task P3-T31

Tests for:
- Jochi-Temüjin handoff workflow
- Backend detection automation
- Fix validation

Author: Jochi (Analyst Agent)
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from unittest.mock import Mock, MagicMock, AsyncMock, patch, call
from enum import Enum
import sys
import os
import json

# Add tools/kurultai to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../tools/kurultai'))

from autonomous_orchestrator import AutonomousOrchestrator, get_orchestrator


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_neo4j_driver():
    """Create a mock Neo4j driver."""
    driver = MagicMock()
    session = MagicMock()
    
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    
    def mock_run(cypher: str, **kwargs):
        result = MagicMock()
        result.single.return_value = None
        result.data.return_value = []
        result.__iter__ = lambda self: iter([])
        result.peek.return_value = []
        return result
    
    session.run = mock_run
    driver.session.return_value = session
    return driver, session


@pytest.fixture
def collaboration_protocol(mock_neo4j_driver):
    """Create a collaboration protocol handler."""
    driver, session = mock_neo4j_driver
    
    class CollaborationProtocol:
        """Handles agent collaboration workflows."""
        
        AGENTS = {
            "jochi": {"role": "analyst", "capabilities": ["test", "analyze", "audit"]},
            "temujin": {"role": "developer", "capabilities": ["code", "implement", "fix"]},
            "kublai": {"role": "orchestrator", "capabilities": ["delegate", "coordinate"]},
        }
        
        HANDOFF_STATES = {
            "analysis_complete": "ready_for_implementation",
            "implementation_complete": "ready_for_testing",
            "tests_passed": "complete",
            "tests_failed": "needs_fix"
        }
        
        def __init__(self, driver):
            self.driver = driver
            self.handoffs: List[Dict] = []
            self.validations: List[Dict] = []
        
        async def handoff_analysis_to_implementation(
            self,
            task_id: str,
            analysis_results: Dict[str, Any]
        ) -> Dict[str, Any]:
            """Handoff from Jochi (analysis) to Temüjin (implementation)."""
            
            # Validate analysis is complete
            if not self._validate_analysis_complete(analysis_results):
                return {
                    "success": False,
                    "error": "Analysis incomplete",
                    "missing": self._get_missing_analysis(analysis_results)
                }
            
            # Create implementation task
            implementation_task = {
                "task_id": f"{task_id}_impl",
                "parent_task": task_id,
                "type": "implementation",
                "assigned_to": "temujin",
                "delegated_by": "jochi",
                "status": "pending",
                "analysis_results": analysis_results,
                "handoff_timestamp": datetime.now(timezone.utc).isoformat(),
                "requirements": analysis_results.get("requirements", []),
                "test_cases": analysis_results.get("test_cases", []),
                "acceptance_criteria": analysis_results.get("acceptance_criteria", [])
            }
            
            # Store in database
            with self.driver.session() as session:
                session.run("""
                    CREATE (t:Task {
                        id: $task_id,
                        type: 'implementation',
                        assigned_to: 'temujin',
                        delegated_by: 'jochi',
                        status: 'pending',
                        handoff_timestamp: datetime($timestamp),
                        parent_task: $parent
                    })
                """, 
                    task_id=implementation_task["task_id"],
                    timestamp=implementation_task["handoff_timestamp"],
                    parent=task_id
                )
            
            # Record handoff
            self.handoffs.append({
                "from": "jochi",
                "to": "temujin",
                "task_id": task_id,
                "timestamp": implementation_task["handoff_timestamp"],
                "artifacts": list(analysis_results.keys())
            })
            
            return {
                "success": True,
                "handoff_id": f"handoff_{task_id}",
                "implementation_task": implementation_task,
                "next_agent": "temujin"
            }
        
        def _validate_analysis_complete(self, analysis: Dict) -> bool:
            """Check if analysis has required components."""
            required = ["requirements", "test_cases", "acceptance_criteria"]
            return all(k in analysis and analysis[k] for k in required)
        
        def _get_missing_analysis(self, analysis: Dict) -> List[str]:
            """Get list of missing analysis components."""
            required = ["requirements", "test_cases", "acceptance_criteria"]
            return [k for k in required if k not in analysis or not analysis[k]]
        
        async def handoff_implementation_to_testing(
            self,
            task_id: str,
            implementation_results: Dict[str, Any]
        ) -> Dict[str, Any]:
            """Handoff from Temüjin (implementation) to Jochi (testing)."""
            
            # Validate implementation
            validation = self._validate_implementation(implementation_results)
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": "Implementation validation failed",
                    "validation_errors": validation["errors"]
                }
            
            testing_task = {
                "task_id": f"{task_id}_test",
                "parent_task": task_id,
                "type": "testing",
                "assigned_to": "jochi",
                "delegated_by": "temujin",
                "status": "pending",
                "implementation_results": implementation_results,
                "handoff_timestamp": datetime.now(timezone.utc).isoformat(),
                "files_changed": implementation_results.get("files_changed", []),
                "tests_added": implementation_results.get("tests_added", [])
            }
            
            # Record handoff
            self.handoffs.append({
                "from": "temujin",
                "to": "jochi",
                "task_id": task_id,
                "timestamp": testing_task["handoff_timestamp"],
                "artifacts": list(implementation_results.keys())
            })
            
            return {
                "success": True,
                "handoff_id": f"handoff_{task_id}_test",
                "testing_task": testing_task,
                "next_agent": "jochi"
            }
        
        def _validate_implementation(self, implementation: Dict) -> Dict:
            """Validate implementation results."""
            errors = []
            
            # Check for files changed
            if not implementation.get("files_changed"):
                errors.append("No files changed")
            
            # Check for tests
            if not implementation.get("tests_added") and not implementation.get("tests_existing"):
                errors.append("No tests provided")
            
            # Check for documentation
            if not implementation.get("documentation_updated", False):
                errors.append("Documentation not updated")
            
            return {
                "valid": len(errors) == 0,
                "errors": errors
            }
        
        async def detect_backend_needs(self, task_description: str) -> Dict[str, Any]:
            """Automatically detect backend requirements from task description."""
            
            backend_keywords = {
                "api": ["api", "endpoint", "rest", "graphql", "http"],
                "database": ["database", "db", "sql", "neo4j", "postgres", "storage"],
                "auth": ["auth", "login", "oauth", "sso", "jwt", "token"],
                "queue": ["queue", "kafka", "redis", "pubsub", "message"],
                "cache": ["cache", "redis", "memcached"],
                "search": ["search", "elasticsearch", "vector", "index"],
                "integration": ["webhook", "callback", "integration", "third-party"]
            }
            
            task_lower = task_description.lower()
            detected = {}
            
            for backend_type, keywords in backend_keywords.items():
                if any(kw in task_lower for kw in keywords):
                    detected[backend_type] = {
                        "confidence": "high" if sum(1 for kw in keywords if kw in task_lower) > 1 else "medium",
                        "matched_keywords": [kw for kw in keywords if kw in task_lower]
                    }
            
            # Determine complexity
            complexity = self._assess_backend_complexity(detected)
            
            return {
                "backend_needed": len(detected) > 0,
                "backend_types": list(detected.keys()),
                "details": detected,
                "complexity": complexity,
                "recommended_agents": self._recommend_agents(detected)
            }
        
        def _assess_backend_complexity(self, detected: Dict) -> str:
            """Assess complexity based on backend requirements."""
            if not detected:
                return "none"
            
            complexity_score = len(detected)
            
            # High complexity combinations
            high_complexity_combos = [
                {"auth", "api", "database"},
                {"queue", "database", "integration"},
                {"search", "cache", "database"}
            ]
            
            detected_set = set(detected.keys())
            for combo in high_complexity_combos:
                if combo.issubset(detected_set):
                    return "high"
            
            if complexity_score >= 3:
                return "high"
            elif complexity_score >= 2:
                return "medium"
            else:
                return "low"
        
        def _recommend_agents(self, detected: Dict) -> List[str]:
            """Recommend agents based on backend needs."""
            if not detected:
                return ["temujin"]  # Default to developer
            
            agents = set()
            
            if "api" in detected or "integration" in detected:
                agents.add("temujin")
            if "database" in detected or "search" in detected:
                agents.add("temujin")
                agents.add("mongke")  # May need research
            if "auth" in detected:
                agents.add("temujin")
                agents.add("jochi")  # Security considerations
            if "queue" in detected or "cache" in detected:
                agents.add("temujin")
            
            return list(agents) if agents else ["temujin"]
        
        async def validate_fix(
            self,
            task_id: str,
            fix_results: Dict[str, Any],
            original_requirements: List[str]
        ) -> Dict[str, Any]:
            """Validate that a fix meets original requirements."""
            
            validation_results = {
                "task_id": task_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "checks": [],
                "passed": 0,
                "failed": 0,
                "warnings": 0
            }
            
            # Check 1: Requirements coverage
            req_check = self._check_requirements_coverage(
                fix_results, original_requirements
            )
            validation_results["checks"].append(req_check)
            self._update_counts(validation_results, req_check["status"])
            
            # Check 2: Tests pass
            test_check = self._check_tests_pass(fix_results)
            validation_results["checks"].append(test_check)
            self._update_counts(validation_results, test_check["status"])
            
            # Check 3: No regressions
            reg_check = self._check_no_regressions(fix_results)
            validation_results["checks"].append(reg_check)
            self._update_counts(validation_results, reg_check["status"])
            
            # Check 4: Documentation updated
            doc_check = self._check_documentation_updated(fix_results)
            validation_results["checks"].append(doc_check)
            self._update_counts(validation_results, doc_check["status"])
            
            # Check 5: Code quality
            quality_check = self._check_code_quality(fix_results)
            validation_results["checks"].append(quality_check)
            self._update_counts(validation_results, quality_check["status"])
            
            # Final verdict
            validation_results["overall_status"] = self._determine_overall_status(
                validation_results["checks"]
            )
            
            # Record validation
            self.validations.append(validation_results)
            
            return validation_results
        
        def _check_requirements_coverage(
            self,
            fix_results: Dict,
            requirements: List[str]
        ) -> Dict:
            """Check if all requirements are met."""
            implemented = fix_results.get("requirements_implemented", [])
            missing = [r for r in requirements if r not in implemented]
            
            if not missing:
                return {
                    "name": "requirements_coverage",
                    "status": "passed",
                    "message": f"All {len(requirements)} requirements covered"
                }
            else:
                return {
                    "name": "requirements_coverage",
                    "status": "failed",
                    "message": f"Missing requirements: {missing}"
                }
        
        def _check_tests_pass(self, fix_results: Dict) -> Dict:
            """Check if tests pass."""
            test_results = fix_results.get("test_results", {})
            
            if not test_results:
                return {
                    "name": "tests_pass",
                    "status": "failed",
                    "message": "No test results provided"
                }
            
            passed = test_results.get("passed", 0)
            failed = test_results.get("failed", 0)
            
            if failed == 0 and passed > 0:
                return {
                    "name": "tests_pass",
                    "status": "passed",
                    "message": f"All {passed} tests passed"
                }
            elif failed > 0:
                return {
                    "name": "tests_pass",
                    "status": "failed",
                    "message": f"{failed} tests failed, {passed} passed"
                }
            else:
                return {
                    "name": "tests_pass",
                    "status": "warning",
                    "message": "No tests run"
                }
        
        def _check_no_regressions(self, fix_results: Dict) -> Dict:
            """Check for regressions."""
            regressions = fix_results.get("regressions", [])
            
            if not regressions:
                return {
                    "name": "no_regressions",
                    "status": "passed",
                    "message": "No regressions detected"
                }
            else:
                return {
                    "name": "no_regressions",
                    "status": "failed",
                    "message": f"{len(regressions)} regressions found: {regressions}"
                }
        
        def _check_documentation_updated(self, fix_results: Dict) -> Dict:
            """Check if documentation is updated."""
            if fix_results.get("documentation_updated", False):
                return {
                    "name": "documentation_updated",
                    "status": "passed",
                    "message": "Documentation updated"
                }
            else:
                return {
                    "name": "documentation_updated",
                    "status": "warning",
                    "message": "Documentation not updated"
                }
        
        def _check_code_quality(self, fix_results: Dict) -> Dict:
            """Check code quality metrics."""
            quality = fix_results.get("code_quality", {})
            
            issues = quality.get("issues", [])
            if not issues:
                return {
                    "name": "code_quality",
                    "status": "passed",
                    "message": "No quality issues"
                }
            elif len(issues) < 3:
                return {
                    "name": "code_quality",
                    "status": "warning",
                    "message": f"{len(issues)} minor quality issues"
                }
            else:
                return {
                    "name": "code_quality",
                    "status": "failed",
                    "message": f"{len(issues)} quality issues found"
                }
        
        def _update_counts(self, results: Dict, status: str):
            """Update pass/fail/warn counts."""
            if status == "passed":
                results["passed"] += 1
            elif status == "failed":
                results["failed"] += 1
            else:
                results["warnings"] += 1
        
        def _determine_overall_status(self, checks: List[Dict]) -> str:
            """Determine overall validation status."""
            statuses = [c["status"] for c in checks]
            
            if "failed" in statuses:
                return "rejected"
            elif "warning" in statuses:
                return "approved_with_warnings"
            else:
                return "approved"
        
        def get_handoff_history(self, task_id: str) -> List[Dict]:
            """Get handoff history for a task."""
            return [h for h in self.handoffs if h["task_id"] == task_id]
        
        def get_validation_history(self, task_id: str) -> List[Dict]:
            """Get validation history for a task."""
            return [v for v in self.validations if v["task_id"] == task_id]
    
    return CollaborationProtocol(driver)


# =============================================================================
# Jochi-Temüjin Handoff Tests
# =============================================================================

class TestJochiTemujinHandoff:
    """Tests for Jochi-Temüjin handoff workflow."""
    
    @pytest.mark.asyncio
    async def test_handoff_analysis_to_implementation_success(self, collaboration_protocol):
        """Verify successful handoff from analysis to implementation."""
        analysis_results = {
            "requirements": ["Implement OAuth 2.0 flow", "Add JWT token validation"],
            "test_cases": ["Test login flow", "Test token refresh"],
            "acceptance_criteria": ["All tests pass", "Code review approved"],
            "estimated_complexity": "medium"
        }
        
        result = await collaboration_protocol.handoff_analysis_to_implementation(
            task_id="task-123",
            analysis_results=analysis_results
        )
        
        assert result["success"] is True
        assert result["next_agent"] == "temujin"
        assert "implementation_task" in result
        assert result["implementation_task"]["assigned_to"] == "temujin"
        assert result["implementation_task"]["delegated_by"] == "jochi"
    
    @pytest.mark.asyncio
    async def test_handoff_fails_incomplete_analysis(self, collaboration_protocol):
        """Verify handoff fails if analysis is incomplete."""
        incomplete_analysis = {
            "requirements": ["Implement OAuth"],
            # Missing test_cases and acceptance_criteria
        }
        
        result = await collaboration_protocol.handoff_analysis_to_implementation(
            task_id="task-456",
            analysis_results=incomplete_analysis
        )
        
        assert result["success"] is False
        assert "error" in result
        assert "missing" in result
    
    @pytest.mark.asyncio
    async def test_handoff_creates_database_record(self, collaboration_protocol, mock_neo4j_driver):
        """Verify handoff creates database record."""
        driver, session = mock_neo4j_driver
        
        analysis_results = {
            "requirements": ["Req 1", "Req 2"],
            "test_cases": ["Test 1"],
            "acceptance_criteria": ["Crit 1"]
        }
        
        await collaboration_protocol.handoff_analysis_to_implementation(
            task_id="task-789",
            analysis_results=analysis_results
        )
        
        # Verify database was called
        assert session.run.called
        calls = session.run.call_args_list
        assert any("CREATE" in str(call) for call in calls)
    
    @pytest.mark.asyncio
    async def test_handoff_tracks_artifacts(self, collaboration_protocol):
        """Verify handoff tracks what artifacts were transferred."""
        analysis_results = {
            "requirements": ["Req 1"],
            "test_cases": ["Test 1"],
            "acceptance_criteria": ["Crit 1"],
            "architecture_diagram": "diagram.png",
            "api_spec": "spec.yaml"
        }
        
        await collaboration_protocol.handoff_analysis_to_implementation(
            task_id="task-artifacts",
            analysis_results=analysis_results
        )
        
        # Check handoff was recorded with artifacts
        handoffs = collaboration_protocol.get_handoff_history("task-artifacts")
        assert len(handoffs) == 1
        assert "artifacts" in handoffs[0]
        assert len(handoffs[0]["artifacts"]) == len(analysis_results)
    
    @pytest.mark.asyncio
    async def test_implementation_to_testing_handoff(self, collaboration_protocol):
        """Verify handoff from implementation back to testing."""
        implementation_results = {
            "files_changed": ["auth.py", "models.py"],
            "tests_added": ["test_auth.py"],
            "documentation_updated": True,
            "commit_hash": "abc123"
        }
        
        result = await collaboration_protocol.handoff_implementation_to_testing(
            task_id="task-test-handoff",
            implementation_results=implementation_results
        )
        
        assert result["success"] is True
        assert result["next_agent"] == "jochi"
    
    @pytest.mark.asyncio
    async def test_implementation_handoff_validates_results(self, collaboration_protocol):
        """Verify implementation handoff validates results first."""
        bad_implementation = {
            # Missing files_changed
            "tests_added": [],
            "documentation_updated": False
        }
        
        result = await collaboration_protocol.handoff_implementation_to_testing(
            task_id="task-bad-impl",
            implementation_results=bad_implementation
        )
        
        assert result["success"] is False
        assert "validation_errors" in result


# =============================================================================
# Backend Detection Tests
# =============================================================================

class TestBackendDetection:
    """Tests for backend detection automation."""
    
    @pytest.mark.asyncio
    async def test_detects_api_backend(self, collaboration_protocol):
        """Verify detection of API backend needs."""
        task = "Create REST API endpoints for user management with authentication"
        
        result = await collaboration_protocol.detect_backend_needs(task)
        
        assert result["backend_needed"] is True
        assert "api" in result["backend_types"]
        assert "auth" in result["backend_types"]
    
    @pytest.mark.asyncio
    async def test_detects_database_backend(self, collaboration_protocol):
        """Verify detection of database backend needs."""
        task = "Store user preferences in Neo4j with proper indexing"
        
        result = await collaboration_protocol.detect_backend_needs(task)
        
        assert result["backend_needed"] is True
        assert "database" in result["backend_types"]
    
    @pytest.mark.asyncio
    async def test_detects_queue_backend(self, collaboration_protocol):
        """Verify detection of message queue needs."""
        task = "Process webhooks asynchronously using Redis queue"
        
        result = await collaboration_protocol.detect_backend_needs(task)
        
        assert result["backend_needed"] is True
        assert "queue" in result["backend_types"]
    
    @pytest.mark.asyncio
    async def test_detects_multiple_backends(self, collaboration_protocol):
        """Verify detection of multiple backend types."""
        task = """
        Build a search API with Elasticsearch that caches results in Redis
        and stores user data in PostgreSQL with OAuth authentication
        """
        
        result = await collaboration_protocol.detect_backend_needs(task)
        
        assert result["backend_needed"] is True
        assert len(result["backend_types"]) >= 3
        assert "api" in result["backend_types"]
        assert "search" in result["backend_types"]
        assert "cache" in result["backend_types"]
        assert "database" in result["backend_types"]
    
    @pytest.mark.asyncio
    async def test_no_backend_for_frontend_only(self, collaboration_protocol):
        """Verify no backend detected for frontend-only tasks."""
        task = "Update the React component styling and add hover effects"
        
        result = await collaboration_protocol.detect_backend_needs(task)
        
        assert result["backend_needed"] is False
        assert result["complexity"] == "none"
    
    @pytest.mark.asyncio
    async def test_assesses_complexity_low(self, collaboration_protocol):
        """Verify low complexity assessment for simple backends."""
        task = "Add a simple API endpoint for health checks"
        
        result = await collaboration_protocol.detect_backend_needs(task)
        
        assert result["complexity"] == "low"
    
    @pytest.mark.asyncio
    async def test_assesses_complexity_high(self, collaboration_protocol):
        """Verify high complexity assessment for complex backends."""
        task = """
        Build OAuth authentication API with PostgreSQL database, Redis caching,
        and Elasticsearch for user search with webhook integrations
        """
        
        result = await collaboration_protocol.detect_backend_needs(task)
        
        assert result["complexity"] == "high"
    
    @pytest.mark.asyncio
    async def test_recommends_temujin_for_backend(self, collaboration_protocol):
        """Verify Temüjin is recommended for backend tasks."""
        task = "Create API endpoints for task management"
        
        result = await collaboration_protocol.detect_backend_needs(task)
        
        assert "temujin" in result["recommended_agents"]
    
    @pytest.mark.asyncio
    async def test_recommends_jochi_for_auth(self, collaboration_protocol):
        """Verify Jochi is recommended for auth/security tasks."""
        task = "Implement OAuth 2.0 authentication flow"
        
        result = await collaboration_protocol.detect_backend_needs(task)
        
        assert "jochi" in result["recommended_agents"]
        assert "temujin" in result["recommended_agents"]
    
    @pytest.mark.asyncio
    async def test_tracks_detected_keywords(self, collaboration_protocol):
        """Verify detected keywords are tracked."""
        task = "Build REST API with JWT authentication"
        
        result = await collaboration_protocol.detect_backend_needs(task)
        
        assert "api" in result["details"]
        assert "matched_keywords" in result["details"]["api"]
        assert "rest" in result["details"]["api"]["matched_keywords"]


# =============================================================================
# Fix Validation Tests
# =============================================================================

class TestFixValidation:
    """Tests for fix validation."""
    
    @pytest.mark.asyncio
    async def test_validates_requirements_coverage(self, collaboration_protocol):
        """Verify validation checks requirements coverage."""
        fix_results = {
            "requirements_implemented": ["Req 1", "Req 2", "Req 3"],
            "test_results": {"passed": 5, "failed": 0},
            "regressions": [],
            "documentation_updated": True,
            "code_quality": {"issues": []}
        }
        
        requirements = ["Req 1", "Req 2", "Req 3"]
        
        result = await collaboration_protocol.validate_fix(
            task_id="task-valid",
            fix_results=fix_results,
            original_requirements=requirements
        )
        
        req_check = next(c for c in result["checks"] if c["name"] == "requirements_coverage")
        assert req_check["status"] == "passed"
    
    @pytest.mark.asyncio
    async def test_fails_missing_requirements(self, collaboration_protocol):
        """Verify validation fails if requirements missing."""
        fix_results = {
            "requirements_implemented": ["Req 1"],
            "test_results": {"passed": 1, "failed": 0},
            "regressions": [],
            "documentation_updated": True,
            "code_quality": {"issues": []}
        }
        
        requirements = ["Req 1", "Req 2", "Req 3"]
        
        result = await collaboration_protocol.validate_fix(
            task_id="task-incomplete",
            fix_results=fix_results,
            original_requirements=requirements
        )
        
        req_check = next(c for c in result["checks"] if c["name"] == "requirements_coverage")
        assert req_check["status"] == "failed"
        assert "Req 2" in req_check["message"] or "Req 3" in req_check["message"]
    
    @pytest.mark.asyncio
    async def test_validates_tests_pass(self, collaboration_protocol):
        """Verify validation checks test results."""
        fix_results = {
            "requirements_implemented": ["Req 1"],
            "test_results": {"passed": 10, "failed": 0},
            "regressions": [],
            "documentation_updated": True,
            "code_quality": {"issues": []}
        }
        
        result = await collaboration_protocol.validate_fix(
            task_id="task-tests-pass",
            fix_results=fix_results,
            original_requirements=["Req 1"]
        )
        
        test_check = next(c for c in result["checks"] if c["name"] == "tests_pass")
        assert test_check["status"] == "passed"
    
    @pytest.mark.asyncio
    async def test_fails_on_test_failures(self, collaboration_protocol):
        """Verify validation fails if tests fail."""
        fix_results = {
            "requirements_implemented": ["Req 1"],
            "test_results": {"passed": 5, "failed": 3},
            "regressions": [],
            "documentation_updated": True,
            "code_quality": {"issues": []}
        }
        
        result = await collaboration_protocol.validate_fix(
            task_id="task-tests-fail",
            fix_results=fix_results,
            original_requirements=["Req 1"]
        )
        
        test_check = next(c for c in result["checks"] if c["name"] == "tests_pass")
        assert test_check["status"] == "failed"
        assert "3" in test_check["message"]
    
    @pytest.mark.asyncio
    async def test_fails_on_regressions(self, collaboration_protocol):
        """Verify validation fails if regressions detected."""
        fix_results = {
            "requirements_implemented": ["Req 1"],
            "test_results": {"passed": 5, "failed": 0},
            "regressions": ["Old feature X broken", "Performance degraded"],
            "documentation_updated": True,
            "code_quality": {"issues": []}
        }
        
        result = await collaboration_protocol.validate_fix(
            task_id="task-regression",
            fix_results=fix_results,
            original_requirements=["Req 1"]
        )
        
        reg_check = next(c for c in result["checks"] if c["name"] == "no_regressions")
        assert reg_check["status"] == "failed"
        assert "2" in reg_check["message"]
    
    @pytest.mark.asyncio
    async def test_warns_on_missing_docs(self, collaboration_protocol):
        """Verify validation warns if documentation not updated."""
        fix_results = {
            "requirements_implemented": ["Req 1"],
            "test_results": {"passed": 5, "failed": 0},
            "regressions": [],
            "documentation_updated": False,
            "code_quality": {"issues": []}
        }
        
        result = await collaboration_protocol.validate_fix(
            task_id="task-no-docs",
            fix_results=fix_results,
            original_requirements=["Req 1"]
        )
        
        doc_check = next(c for c in result["checks"] if c["name"] == "documentation_updated")
        assert doc_check["status"] == "warning"
    
    @pytest.mark.asyncio
    async def test_approved_when_all_pass(self, collaboration_protocol):
        """Verify overall approval when all checks pass."""
        fix_results = {
            "requirements_implemented": ["Req 1"],
            "test_results": {"passed": 5, "failed": 0},
            "regressions": [],
            "documentation_updated": True,
            "code_quality": {"issues": []}
        }
        
        result = await collaboration_protocol.validate_fix(
            task_id="task-approved",
            fix_results=fix_results,
            original_requirements=["Req 1"]
        )
        
        assert result["overall_status"] == "approved"
        assert result["passed"] > 0
        assert result["failed"] == 0
    
    @pytest.mark.asyncio
    async def test_rejected_when_checks_fail(self, collaboration_protocol):
        """Verify overall rejection when any check fails."""
        fix_results = {
            "requirements_implemented": ["Req 1"],
            "test_results": {"passed": 0, "failed": 5},
            "regressions": ["Regression 1"],
            "documentation_updated": True,
            "code_quality": {"issues": []}
        }
        
        result = await collaboration_protocol.validate_fix(
            task_id="task-rejected",
            fix_results=fix_results,
            original_requirements=["Req 1"]
        )
        
        assert result["overall_status"] == "rejected"
        assert result["failed"] > 0
    
    @pytest.mark.asyncio
    async def test_approved_with_warnings(self, collaboration_protocol):
        """Verify approval with warnings when only warnings present."""
        fix_results = {
            "requirements_implemented": ["Req 1"],
            "test_results": {"passed": 5, "failed": 0},
            "regressions": [],
            "documentation_updated": False,  # Warning
            "code_quality": {"issues": ["Minor style issue"]}  # Warning
        }
        
        result = await collaboration_protocol.validate_fix(
            task_id="task-warnings",
            fix_results=fix_results,
            original_requirements=["Req 1"]
        )
        
        assert result["overall_status"] == "approved_with_warnings"
        assert result["warnings"] > 0
    
    @pytest.mark.asyncio
    async def test_validation_tracks_history(self, collaboration_protocol):
        """Verify validation results are tracked historically."""
        fix_results = {
            "requirements_implemented": ["Req 1"],
            "test_results": {"passed": 5, "failed": 0},
            "regressions": [],
            "documentation_updated": True,
            "code_quality": {"issues": []}
        }
        
        await collaboration_protocol.validate_fix(
            task_id="task-history",
            fix_results=fix_results,
            original_requirements=["Req 1"]
        )
        
        history = collaboration_protocol.get_validation_history("task-history")
        assert len(history) == 1
        assert history[0]["task_id"] == "task-history"


# =============================================================================
# Integration Tests
# =============================================================================

class TestCollaborationIntegration:
    """Integration tests for complete collaboration workflow."""
    
    @pytest.mark.asyncio
    async def test_complete_jochi_temujin_workflow(self, collaboration_protocol):
        """Test complete Jochi-Temüjin-Jochi workflow."""
        task_id = "task-complete-workflow"
        
        # Step 1: Jochi completes analysis
        analysis_results = {
            "requirements": ["Req 1", "Req 2"],
            "test_cases": ["Test 1", "Test 2"],
            "acceptance_criteria": ["Crit 1"]
        }
        
        # Step 2: Handoff to Temüjin
        handoff1 = await collaboration_protocol.handoff_analysis_to_implementation(
            task_id=task_id,
            analysis_results=analysis_results
        )
        assert handoff1["success"] is True
        assert handoff1["next_agent"] == "temujin"
        
        # Step 3: Temüjin completes implementation
        implementation_results = {
            "files_changed": ["file1.py", "file2.py"],
            "tests_added": ["test1.py"],
            "documentation_updated": True
        }
        
        # Step 4: Handoff back to Jochi for testing
        handoff2 = await collaboration_protocol.handoff_implementation_to_testing(
            task_id=task_id,
            implementation_results=implementation_results
        )
        assert handoff2["success"] is True
        assert handoff2["next_agent"] == "jochi"
        
        # Step 5: Jochi validates
        fix_results = {
            "requirements_implemented": analysis_results["requirements"],
            "test_results": {"passed": 5, "failed": 0},
            "regressions": [],
            "documentation_updated": True,
            "code_quality": {"issues": []}
        }
        
        validation = await collaboration_protocol.validate_fix(
            task_id=task_id,
            fix_results=fix_results,
            original_requirements=analysis_results["requirements"]
        )
        
        assert validation["overall_status"] == "approved"
        
        # Verify handoff history
        history = collaboration_protocol.get_handoff_history(task_id)
        assert len(history) == 2
        assert history[0]["from"] == "jochi"
        assert history[0]["to"] == "temujin"
        assert history[1]["from"] == "temujin"
        assert history[1]["to"] == "jochi"
    
    @pytest.mark.asyncio
    async def test_backend_detection_influences_handoff(self, collaboration_protocol):
        """Verify backend detection influences handoff decisions."""
        task = "Build OAuth API with database storage"
        
        # Detect backend needs
        backend_analysis = await collaboration_protocol.detect_backend_needs(task)
        
        assert backend_analysis["backend_needed"] is True
        assert "temujin" in backend_analysis["recommended_agents"]
        
        # Use backend analysis in handoff
        analysis_results = {
            "requirements": ["Implement OAuth", "Setup database"],
            "test_cases": ["Test OAuth flow"],
            "acceptance_criteria": ["All tests pass"],
            "backend_analysis": backend_analysis
        }
        
        handoff = await collaboration_protocol.handoff_analysis_to_implementation(
            task_id="task-backend",
            analysis_results=analysis_results
        )
        
        assert handoff["success"] is True
    
    @pytest.mark.asyncio
    async def test_validation_blocks_bad_fixes(self, collaboration_protocol):
        """Verify validation prevents bad fixes from being accepted."""
        task_id = "task-block-bad"
        
        # Analysis phase
        analysis_results = {
            "requirements": ["Req 1", "Req 2", "Req 3"],
            "test_cases": ["Test 1"],
            "acceptance_criteria": ["Crit 1"]
        }
        
        await collaboration_protocol.handoff_analysis_to_implementation(
            task_id=task_id,
            analysis_results=analysis_results
        )
        
        # Bad implementation
        bad_fix = {
            "requirements_implemented": ["Req 1"],  # Missing 2 and 3
            "test_results": {"passed": 0, "failed": 5},
            "regressions": ["Broke existing feature"],
            "documentation_updated": False,
            "code_quality": {"issues": ["Issue 1", "Issue 2", "Issue 3"]}
        }
        
        validation = await collaboration_protocol.validate_fix(
            task_id=task_id,
            fix_results=bad_fix,
            original_requirements=analysis_results["requirements"]
        )
        
        assert validation["overall_status"] == "rejected"
        assert validation["failed"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
