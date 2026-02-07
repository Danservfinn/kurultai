"""
Interactive Chat Test Scenarios

Defines test scenarios that exercise key workflows and can be manually executed:
- Simple delegation to researcher
- Multi-agent collaboration
- Capability-based routing
- Fallback on specialist unavailable
- Complex DAG task coordination

Each scenario defines:
- User message to send
- Expected agents to participate
- Expected workflow steps
- Success criteria for validation
"""

import dataclasses as dc
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Scenario:
    """A test scenario for interactive chat validation (not a pytest test class)."""

    name: str
    description: str
    user_message: str
    expected_agents: List[str]
    expected_workflow_steps: List[str]
    expected_duration_range: tuple  # (min_seconds, max_seconds)
    success_criteria: List[str]
    complexity_score: float = 0.5
    expected_task_type: str = "generic"


# Interactive test scenarios covering key workflows
INTERACTIVE_TEST_SCENARIOS = [
    Scenario(
        name="Simple Delegation to Researcher",
        description="Kublai should delegate a research task to Mongke",
        user_message="Research the latest advances in large language model orchestration and summarize the key findings.",
        expected_agents=["kublai", "mongke"],
        expected_workflow_steps=[
            "kublai receives message",
            "kublai classifies as research task",
            "kublai delegates to mongke",
            "mongke processes research query",
            "mongke returns findings",
            "kublai synthesizes response",
        ],
        expected_duration_range=(5, 45),
        success_criteria=[
            "Response mentions research sources",
            "Summary is coherent and structured",
            "Mongke agent attribution visible",
            "Timing within expected range",
        ],
        complexity_score=0.4,
        expected_task_type="research",
    ),
    Scenario(
        name="Multi-Agent Collaboration",
        description="Task requires research, writing, and development",
        user_message="Create a FastAPI endpoint for user authentication with JWT tokens. Include the code, documentation, and security analysis.",
        expected_agents=["kublai", "mongke", "temujin", "chagatai", "jochi"],
        expected_workflow_steps=[
            "kublai receives message",
            "kublai classifies as complex multi-domain task",
            "kublai delegates to mongke (research auth patterns)",
            "kublai delegates to temujin (implement FastAPI)",
            "kublai delegates to chagatai (write documentation)",
            "kublai delegates to jochi (security analysis)",
            "kublai synthesizes combined response",
        ],
        expected_duration_range=(30, 180),
        success_criteria=[
            "FastAPI code provided",
            "Documentation included",
            "Security analysis covers JWT best practices",
            "All agents credited appropriately",
            "Response is cohesive, not disjointed",
        ],
        complexity_score=0.8,
        expected_task_type="code",
    ),
    Scenario(
        name="Delegation with Capability Check",
        description="Verify capability-based routing works correctly",
        user_message="Analyze the performance characteristics of our Neo4j database and recommend optimizations.",
        expected_agents=["kublai", "jochi"],
        expected_workflow_steps=[
            "kublai receives message",
            "kublai classifies as analysis task",
            "kublai checks Jochi's capabilities",
            "kublai delegates to jochi",
            "jochi performs analysis",
            "jochi returns recommendations",
        ],
        expected_duration_range=(10, 60),
        success_criteria=[
            "Analysis mentions Neo4j specific features",
            "Recommendations are actionable",
            "Jochi agent attribution visible",
        ],
        complexity_score=0.6,
        expected_task_type="analysis",
    ),
    Scenario(
        name="Fallback on Specialist Unavailable",
        description="Kublai should handle specialist unavailability gracefully",
        user_message="Write a poem about software testing.",
        expected_agents=["kublai", "chagatai"],
        expected_workflow_steps=[
            "kublai receives message",
            "kublai classifies as writing task",
            "kublai delegates to chagatai",
            "chagatai generates poem",
            "kublai returns poem",
        ],
        expected_duration_range=(5, 30),
        success_criteria=[
            "Poem is generated",
            "Chagatai agent attribution visible",
            "Response completes without error",
        ],
        complexity_score=0.2,
        expected_task_type="writing",
    ),
    Scenario(
        name="Complex DAG Task Coordination",
        description="Multiple tasks with dependencies execute correctly",
        user_message="Build a complete user management system: design the database schema, implement the API endpoints, write unit tests, and create API documentation.",
        expected_agents=["kublai", "temujin", "mongke", "chagatai", "jochi"],
        expected_workflow_steps=[
            "kublai receives message",
            "kublai breaks down into subtasks",
            "kublai creates task DAG in Neo4j",
            "Subtasks delegated based on capabilities",
            "Tasks execute respecting dependencies",
            "kublai synthesizes final result",
        ],
        expected_duration_range=(60, 300),
        success_criteria=[
            "Database schema provided",
            "API endpoints implemented",
            "Unit tests included",
            "Documentation complete",
            "Task dependencies respected",
        ],
        complexity_score=0.9,
        expected_task_type="code",
    ),
    Scenario(
        name="Security Audit Task",
        description="Security analysis task routes to Temüjin",
        user_message="Perform a security audit on our authentication system focusing on OWASP Top 10 vulnerabilities.",
        expected_agents=["kublai", "temujin"],
        expected_workflow_steps=[
            "kublai receives message",
            "kublai classifies as security task",
            "kublai delegates to temujin",
            "temujin performs security audit",
            "temujin returns findings",
        ],
        expected_duration_range=(15, 90),
        success_criteria=[
            "OWASP Top 10 mentioned",
            "Specific vulnerabilities identified",
            "Remediation recommendations provided",
            "Temüjin agent attribution visible",
        ],
        complexity_score=0.7,
        expected_task_type="security",
    ),
]


class ScenarioRunner:
    """Runner for executing test scenarios interactively."""

    @staticmethod
    def print_scenario(scenario: Scenario):
        """Print scenario details for the tester.

        Args:
            scenario: The test scenario to print
        """
        print(f"\n{'=' * 60}")
        print(f"SCENARIO: {scenario.name}")
        print(f"{'=' * 60}")
        print(f"Description: {scenario.description}")
        print(f"\nUser Message:")
        print(f"  {scenario.user_message}")
        print(f"\nExpected Agents: {', '.join(scenario.expected_agents)}")
        print(f"\nExpected Workflow:")
        for i, step in enumerate(scenario.expected_workflow_steps, 1):
            print(f"  {i}. {step}")
        print(f"\nSuccess Criteria:")
        for i, criterion in enumerate(scenario.success_criteria, 1):
            print(f"  [ ] {criterion}")
        print(
            f"\nExpected Duration: {scenario.expected_duration_range[0]}-{scenario.expected_duration_range[1]} seconds"
        )
        print(f"Complexity Score: {scenario.complexity_score}")
        print(f"{'=' * 60}\n")

    @staticmethod
    def create_validation_checklist(scenario: Scenario) -> Dict[str, Any]:
        """Create a validation checklist for the scenario.

        Args:
            scenario: The test scenario

        Returns:
            Dictionary with checklist structure
        """
        return {
            "scenario_name": scenario.name,
            "description": scenario.description,
            "checklist_items": [
                {"criterion": criterion, "passed": False, "notes": ""}
                for criterion in scenario.success_criteria
            ],
            "agents_observed": [],
            "workflow_steps_observed": [],
            "duration_seconds": None,
            "within_expected_range": False,
            "complexity_score": scenario.complexity_score,
        }

    @staticmethod
    def list_all_scenarios(scenarios: List[Scenario] = None):
        """List all available test scenarios.

        Args:
            scenarios: Optional list of scenarios (defaults to INTERACTIVE_TEST_SCENARIOS)
        """
        if scenarios is None:
            scenarios = INTERACTIVE_TEST_SCENARIOS

        print("\nAvailable Test Scenarios:")
        print("=" * 60)
        for i, scenario in enumerate(scenarios):
            print(f"{i}. {scenario.name}")
            print(f"   {scenario.description}")
            print(f"   Agents: {', '.join(scenario.expected_agents)}")
            print(f"   Duration: {scenario.expected_duration_range[0]}-{scenario.expected_duration_range[1]}s")
            print()
        print("=" * 60 + "\n")

    @staticmethod
    def get_scenario_by_index(index: int) -> Scenario:
        """Get a scenario by its index.

        Args:
            index: Scenario index

        Returns:
            Scenario instance

        Raises:
            IndexError: If index is out of range
        """
        if 0 <= index < len(INTERACTIVE_TEST_SCENARIOS):
            return INTERACTIVE_TEST_SCENARIOS[index]
        raise IndexError(
            f"Invalid scenario index {index}. Max is {len(INTERACTIVE_TEST_SCENARIOS) - 1}"
        )

    @staticmethod
    def get_scenario_by_name(name: str) -> Optional[Scenario]:
        """Get a scenario by its name.

        Args:
            name: Scenario name (partial match supported)

        Returns:
            Scenario instance or None if not found
        """
        name_lower = name.lower()
        for scenario in INTERACTIVE_TEST_SCENARIOS:
            if name_lower in scenario.name.lower():
                return scenario
        return None


@dataclass
class ScenarioResult:
    """Result of running a test scenario."""

    scenario_name: str
    passed: bool
    duration_seconds: float
    agents_observed: List[str] = field(default_factory=list)
    workflow_steps_observed: List[str] = field(default_factory=list)
    checklist_results: List[Dict[str, Any]] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return dc.asdict(self)

    def save(self, output_path: str):
        """Save scenario result to JSON file.

        Args:
            output_path: Path to save result
        """
        with open(output_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


def create_scenario_report(results: List[ScenarioResult]) -> Dict[str, Any]:
    """Create a summary report from multiple scenario results.

    Args:
        results: List of scenario results

    Returns:
        Summary report dictionary
    """
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    all_agents = set()
    for result in results:
        all_agents.update(result.agents_observed)

    avg_duration = sum(r.duration_seconds for r in results) / total if total > 0 else 0

    return {
        "total_scenarios": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / total if total > 0 else 0,
        "agents_observed": list(all_agents),
        "average_duration_seconds": avg_duration,
        "scenarios": [r.to_dict() for r in results],
    }


__all__ = [
    "Scenario",
    "INTERACTIVE_TEST_SCENARIOS",
    "ScenarioRunner",
    "ScenarioResult",
    "create_scenario_report",
]
