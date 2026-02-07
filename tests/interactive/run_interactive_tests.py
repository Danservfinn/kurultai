#!/usr/bin/env python3
"""
Interactive Chat Test Runner - Guides manual testing and automates validation.

This script provides a command-line interface for:
- Listing available test scenarios
- Running scenarios interactively
- Comparing sessions for regression detection
- Generating validation checklists

Usage:
    python run_interactive_tests.py list
    python run_interactive_tests.py run <scenario_index>
    python run_interactive_tests.py compare <session1> <session2>
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.interactive.chat_session_recorder import ChatSessionRecorder
from tests.interactive.test_scenarios import (
    INTERACTIVE_TEST_SCENARIOS,
    ScenarioRunner,
    ScenarioResult,
    create_scenario_report,
)


class InteractiveTestRunner:
    """Interactive test runner for manual chat-based testing."""

    def __init__(
        self,
        output_dir: str = "tests/interactive/sessions",
        checklist_dir: str = "tests/interactive/checklists",
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checklist_dir = Path(checklist_dir)
        self.checklist_dir.mkdir(parents=True, exist_ok=True)

    async def run_scenario(self, scenario_index: int) -> ScenarioResult:
        """Run a specific test scenario interactively.

        Args:
            scenario_index: Index of scenario to run

        Returns:
            ScenarioResult with test outcome
        """
        if scenario_index >= len(INTERACTIVE_TEST_SCENARIOS):
            print(f"Invalid scenario index. Max is {len(INTERACTIVE_TEST_SCENARIOS) - 1}")
            return ScenarioResult(
                scenario_name="invalid",
                passed=False,
                duration_seconds=0,
            )

        scenario = INTERACTIVE_TEST_SCENARIOS[scenario_index]

        # Print scenario details
        ScenarioRunner.print_scenario(scenario)

        # Create session recorder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_name = f"{scenario.name.replace(' ', '_')}_{timestamp}"
        recorder = ChatSessionRecorder(
            session_name=session_name,
            architecture_spec_path="ARCHITECTURE.md",
            output_dir=str(self.output_dir),
        )

        await recorder.start_session()

        # Record the user message
        await recorder.record_message("user", scenario.user_message)
        print("\n[User message recorded]")

        # Prompt for actual response
        print("\n--- Paste Kublai's Response ---")
        print("[Paste the response, then press Ctrl+D (Unix) or Ctrl+Z (Windows)]")
        print("[Or press Enter twice to skip manual recording]")

        response_lines = []
        try:
            while True:
                line = input()
                if line == "" and not response_lines:
                    # Empty input at start - skip
                    continue
                response_lines.append(line)
        except (EOFError, KeyboardInterrupt):
            pass

        if response_lines:
            response = "\n".join(response_lines)
            await recorder.record_message("assistant", response, agent_responding="kublai")
            print(f"\n[Recorded {len(response)} character response]")

        # Prompt for manual observations
        print("\n--- Manual Observations ---")
        print("Enter agents you observed (comma-separated, e.g., kublai,mongke):")
        agents_input = input().strip()
        if agents_input:
            recorder.agents_observed = [a.strip() for a in agents_input.split(",")]

        print("Enter total duration in seconds:")
        try:
            duration = float(input().strip())
            recorder.duration_seconds = duration
        except (ValueError, EOFError):
            duration = None

        await recorder.end_session()

        # Validate against architecture
        findings = await recorder.validate_against_architecture()

        # Save session
        session_path = recorder.save_session()
        print(f"\n[Session saved to {session_path}]")

        # Print findings
        self._print_findings(findings)

        # Create and save validation checklist
        checklist = ScenarioRunner.create_validation_checklist(scenario)
        checklist["agents_observed"] = recorder.agents_observed
        checklist["duration_seconds"] = duration
        checklist["within_expected_range"] = (
            duration is not None
            and scenario.expected_duration_range[0] <= duration <= scenario.expected_duration_range[1]
        )

        # Save checklist
        checklist_path = self.checklist_dir / f"{session_name}_checklist.json"
        with open(checklist_path, "w") as f:
            json.dump(checklist, f, indent=2)
        print(f"[Checklist saved to {checklist_path}]")

        # Create result
        result = ScenarioResult(
            scenario_name=scenario.name,
            passed=checklist["within_expected_range"],
            duration_seconds=duration or 0,
            agents_observed=recorder.agents_observed.copy(),
            checklist_results=checklist["checklist_items"],
        )

        # Prompt for checklist completion
        self._complete_checklist_interactive(checklist)

        return result

    def _complete_checklist_interactive(self, checklist: dict):
        """Interactive checklist completion.

        Args:
            checklist: Checklist dictionary to update
        """
        print("\n--- Complete Validation Checklist ---")
        for i, item in enumerate(checklist["checklist_items"]):
            while True:
                response = input(f"  [{i+1}/{len(checklist['checklist_items'])}] {item['criterion']}: (P)ass/(F)ail/(S)kip? ").strip().upper()
                if response in ("P", "PASS"):
                    item["passed"] = True
                    item["notes"] = input("    Notes (optional): ").strip()
                    break
                elif response in ("F", "FAIL"):
                    item["passed"] = False
                    item["notes"] = input("    Notes (required): ").strip()
                    break
                elif response in ("S", "SKIP"):
                    break
                else:
                    print("    Invalid input. Enter P, F, or S.")

        # Count passed items
        passed_items = sum(1 for item in checklist["checklist_items"] if item.get("passed", False))
        total_items = len(checklist["checklist_items"])
        print(f"\n  Checklist: {passed_items}/{total_items} items passed")

    def _print_findings(self, findings: dict):
        """Print validation findings.

        Args:
            findings: Findings dictionary from validate_against_architecture
        """
        print("\n" + "=" * 60)
        print("VALIDATION FINDINGS")
        print("=" * 60)

        if findings.get("validations"):
            print(f"\n✓ Validations ({len(findings['validations'])}):")
            for v in findings["validations"]:
                print(f"  ✓ {v}")

        if findings.get("warnings"):
            print(f"\n⚠ Warnings ({len(findings['warnings'])}):")
            for w in findings["warnings"]:
                print(f"  ⚠ {w}")

        if findings.get("violations"):
            print(f"\n✗ Violations ({len(findings['violations'])}):")
            for v in findings["violations"]:
                print(f"  ✗ {v}")

        if findings.get("metrics"):
            print(f"\n📊 Metrics:")
            for name, values in findings["metrics"].items():
                if isinstance(values, dict):
                    print(f"  {name}:")
                    for k, v in values.items():
                        print(f"    {k}: {v}")
                else:
                    print(f"  {name}: {values}")

        print("=" * 60 + "\n")

    def list_scenarios(self):
        """List all available test scenarios."""
        ScenarioRunner.list_all_scenarios()

    def compare_sessions(self, session1_path: str, session2_path: str):
        """Compare two sessions for regression detection.

        Args:
            session1_path: Path to baseline session
            session2_path: Path to current session
        """
        recorder1 = ChatSessionRecorder.load_session(session1_path)
        recorder2 = ChatSessionRecorder.load_session(session2_path)

        print(f"\nComparing sessions:")
        print(f"  Baseline: {session1_path}")
        print(f"  Current:  {session2_path}")
        print()

        comparison = recorder1.compare_with(recorder2)

        # Print comparison results
        if comparison["duration_self"] and comparison["duration_other"]:
            diff = comparison["duration_diff"]
            sign = "+" if diff >= 0 else ""
            print(f"Duration difference: {sign}{diff:.2f}s ({comparison['duration_self']:.2f}s → {comparison['duration_other']:.2f}s)")

        if comparison["agent_participation_changed"]:
            print(f"Agent participation changed:")
            print(f"  Before: {', '.join(comparison['agents_self']) or 'none'}")
            print(f"  After:  {', '.join(comparison['agents_other']) or 'none'}")

        msg_diff = comparison["message_count_diff"]
        sign = "+" if msg_diff >= 0 else ""
        print(f"Message count difference: {sign}{msg_diff}")

        query_diff = comparison["neo4j_query_count_diff"]
        sign = "+" if query_diff >= 0 else ""
        print(f"Neo4j query difference: {sign}{query_diff}")

    def run_all_scenarios(self) -> create_scenario_report:
        """Run all scenarios sequentially.

        Returns:
            Summary report of all scenario runs
        """
        results = []
        for i in range(len(INTERACTIVE_TEST_SCENARIOS)):
            print(f"\n\n{'#'*60}")
            print(f"# Running scenario {i+1}/{len(INTERACTIVE_TEST_SCENARIOS)}")
            print(f"{'#'*60}\n")
            result = await self.run_scenario(i)
            results.append(result)

        report = create_scenario_report(results)

        # Save report
        report_path = self.checklist_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n[Report saved to {report_path}]")

        return report


async def main():
    """Main entry point for interactive test runner."""
    runner = InteractiveTestRunner()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python run_interactive_tests.py list                    # List scenarios")
        print("  python run_interactive_tests.py run <scenario_index>    # Run a scenario")
        print("  python run_interactive_tests.py run-all                 # Run all scenarios")
        print("  python run_interactive_tests.py compare <session1> <session2>  # Compare sessions")
        print()
        print("Available scenarios:")
        runner.list_scenarios()
        return

    command = sys.argv[1]

    if command == "list":
        runner.list_scenarios()
    elif command == "run":
        if len(sys.argv) < 3:
            print("Please provide scenario index")
            runner.list_scenarios()
            return
        scenario_index = int(sys.argv[2])
        await runner.run_scenario(scenario_index)
    elif command == "run-all":
        await runner.run_all_scenarios()
    elif command == "compare":
        if len(sys.argv) < 4:
            print("Please provide two session paths to compare")
            return
        runner.compare_sessions(sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown command: {command}")
        print("Available commands: list, run, run-all, compare")


if __name__ == "__main__":
    asyncio.run(main())
