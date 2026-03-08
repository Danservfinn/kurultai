#!/usr/bin/env python3
"""
Enforcement Gates - Structural quality gates for task completion.

Implements 6 configurable gates:
1. reviewGate - Require review score before completion
2. closingComments - Require deliverable summary
3. autoTelemetry - Auto-emit run.started/run.completed
4. autoTimeTracking - Auto-start/stop timers
5. orchestratorDelegation - Warn when Kublai does implementation
6. squadChat - Auto-post lifecycle events

Usage:
    python3 enforcement-gates.py --check-all <task_file>
    python3 enforcement-gates.py --check reviewGate <task_file>
    python3 enforcement-gates.py --status
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

# Kurultai paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import LOGS_DIR, AGENTS_DIR

# Configuration
GATES_CONFIG_PATH = AGENTS_DIR / "main" / "config" / "gates" / "enforcement-gates.json"
GATES_LOG = LOGS_DIR / "enforcement-gates.jsonl"


class GateResult(Enum):
    """Result of a gate check."""
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"
    SKIP = "skip"


@dataclass
class GateCheck:
    """Result of a single gate check."""
    gate_name: str
    result: GateResult
    message: str
    details: Dict[str, Any]
    timestamp: str

    def to_dict(self):
        return {
            "gate_name": self.gate_name,
            "result": self.result.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp
        }


class EnforcementGates:
    """Engine for enforcing structural quality gates."""

    def __init__(self, config_path: str = None):
        self.config_path = Path(config_path) if config_path else GATES_CONFIG_PATH
        self.config = self._load_config()
        self._gate_handlers = {
            "reviewGate": self._check_review_gate,
            "closingComments": self._check_closing_comments,
            "autoTelemetry": self._check_telemetry,
            "autoTimeTracking": self._check_time_tracking,
            "orchestratorDelegation": self._check_delegation,
            "squadChat": self._check_squad_chat,
        }

    def _load_config(self) -> dict:
        """Load gate configuration."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"WARNING: Failed to load gates config: {e}")
        return {"gates": {}, "global": {}}

    def _save_config(self):
        """Save gate configuration."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=2)

    def _log_check(self, check: GateCheck):
        """Log a gate check."""
        try:
            with open(GATES_LOG, "a") as f:
                f.write(json.dumps(check.to_dict()) + "\n")
        except OSError:
            pass

    def _extract_frontmatter(self, content: str) -> dict:
        """Extract YAML frontmatter from task content."""
        if not content.startswith("---"):
            return {}

        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}

        frontmatter = {}
        for line in parts[1].strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                frontmatter[key.strip()] = value.strip().strip('"').strip("'")

        return frontmatter

    def _is_trivial_task(self, task_content: str, task_id: str = None) -> bool:
        """Check if task is trivial (exempt from some gates)."""
        frontmatter = self._extract_frontmatter(task_content)

        # Check for optout
        if frontmatter.get("completion_gate_optout", "").lower() == "true":
            return True

        # Check trivial patterns
        trivial_patterns = self.config.get("gates", {}).get("reviewGate", {}).get("config", {}).get("trivial_patterns", [])
        content_lower = task_content.lower()
        for pattern in trivial_patterns:
            if pattern.lower() in content_lower:
                return True

        return False

    def _check_review_gate(self, task_id: str, context: dict) -> GateCheck:
        """Check if task has required review score."""
        gate_config = self.config.get("gates", {}).get("reviewGate", {})
        config = gate_config.get("config", {})

        # Skip if disabled
        if not gate_config.get("enabled", True):
            return GateCheck("reviewGate", GateResult.SKIP, "Gate disabled", {}, datetime.now().isoformat())

        # Skip trivial tasks
        task_content = context.get("task_content", "")
        if self._is_trivial_task(task_content, task_id):
            return GateCheck("reviewGate", GateResult.SKIP, "Trivial task exempt", {}, datetime.now().isoformat())

        # Check for review score
        min_score = config.get("min_review_score", 3)
        review_score = context.get("review_score", 0)
        has_review = context.get("has_review", False)

        if has_review and review_score >= min_score:
            return GateCheck(
                "reviewGate",
                GateResult.PASS,
                f"Review score {review_score} >= {min_score}",
                {"score": review_score, "min_required": min_score},
                datetime.now().isoformat()
            )
        elif has_review:
            return GateCheck(
                "reviewGate",
                GateResult.WARN,
                f"Review score {review_score} < {min_score}",
                {"score": review_score, "min_required": min_score},
                datetime.now().isoformat()
            )
        else:
            return GateCheck(
                "reviewGate",
                GateResult.WARN,  # Warn, don't block
                "No review found",
                {"has_review": False, "min_required": min_score},
                datetime.now().isoformat()
            )

    def _check_closing_comments(self, task_id: str, context: dict) -> GateCheck:
        """Check if task has required deliverable summary."""
        gate_config = self.config.get("gates", {}).get("closingComments", {})
        config = gate_config.get("config", {})

        # Skip if disabled
        if not gate_config.get("enabled", True):
            return GateCheck("closingComments", GateResult.SKIP, "Gate disabled", {}, datetime.now().isoformat())

        # Check exempt skills
        skill_hint = context.get("skill_hint", "")
        exempt_skills = config.get("exempt_skills", [])
        if skill_hint in exempt_skills:
            return GateCheck("closingComments", GateResult.SKIP, f"Skill {skill_hint} exempt", {}, datetime.now().isoformat())

        # Check for deliverable summary
        min_length = config.get("min_length", 20)
        output_content = context.get("output_content", "")

        # Look for deliverable summary section
        summary_patterns = [
            r"## (Deliverable|Summary|What (Was )?Changed|Output)",
            r"\*\*(Deliverable|Summary|What Changed)\*\*",
        ]

        has_summary = False
        summary_content = ""
        for pattern in summary_patterns:
            match = re.search(pattern, output_content, re.IGNORECASE)
            if match:
                # Extract content after the header
                start = match.end()
                end = output_content.find("##", start)
                if end == -1:
                    end = len(output_content)
                summary_content = output_content[start:end].strip()
                if len(summary_content) >= min_length:
                    has_summary = True
                    break

        if has_summary:
            return GateCheck(
                "closingComments",
                GateResult.PASS,
                f"Deliverable summary present ({len(summary_content)} chars)",
                {"summary_length": len(summary_content), "min_required": min_length},
                datetime.now().isoformat()
            )
        else:
            return GateCheck(
                "closingComments",
                GateResult.WARN,
                f"Missing deliverable summary (min {min_length} chars)",
                {"summary_length": len(summary_content), "min_required": min_length},
                datetime.now().isoformat()
            )

    def _check_telemetry(self, task_id: str, context: dict) -> GateCheck:
        """Check if telemetry events were emitted."""
        gate_config = self.config.get("gates", {}).get("autoTelemetry", {})
        config = gate_config.get("config", {})

        # Skip if disabled
        if not gate_config.get("enabled", True):
            return GateCheck("autoTelemetry", GateResult.SKIP, "Gate disabled", {}, datetime.now().isoformat())

        # Check for telemetry events
        events = config.get("events", ["run.started", "run.completed"])
        emitted_events = context.get("telemetry_events", [])

        missing_events = [e for e in events if e not in emitted_events]

        if not missing_events:
            return GateCheck(
                "autoTelemetry",
                GateResult.PASS,
                f"All telemetry events emitted: {events}",
                {"emitted": emitted_events},
                datetime.now().isoformat()
            )
        else:
            return GateCheck(
                "autoTelemetry",
                GateResult.WARN,
                f"Missing telemetry events: {missing_events}",
                {"missing": missing_events, "emitted": emitted_events},
                datetime.now().isoformat()
            )

    def _check_time_tracking(self, task_id: str, context: dict) -> GateCheck:
        """Check if time tracking is active."""
        gate_config = self.config.get("gates", {}).get("autoTimeTracking", {})
        config = gate_config.get("config", {})

        # Skip if disabled
        if not gate_config.get("enabled", True):
            return GateCheck("autoTimeTracking", GateResult.SKIP, "Gate disabled", {}, datetime.now().isoformat())

        # Check for time tracking
        has_start_time = context.get("start_time") is not None
        has_end_time = context.get("end_time") is not None
        duration = context.get("duration_s", 0)

        if has_start_time:
            if has_end_time or duration > 0:
                return GateCheck(
                    "autoTimeTracking",
                    GateResult.PASS,
                    f"Time tracked: {duration}s",
                    {"duration_s": duration, "has_start": has_start_time, "has_end": has_end_time},
                    datetime.now().isoformat()
                )
            else:
                return GateCheck(
                    "autoTimeTracking",
                    GateResult.WARN,
                    "Task started but not yet ended",
                    {"has_start": has_start_time, "has_end": has_end_time},
                    datetime.now().isoformat()
                )
        else:
            return GateCheck(
                "autoTimeTracking",
                GateResult.WARN,
                "No time tracking found",
                {"has_start": False},
                datetime.now().isoformat()
            )

    def _check_delegation(self, task_id: str, context: dict) -> GateCheck:
        """Check if orchestrator is doing implementation work."""
        gate_config = self.config.get("gates", {}).get("orchestratorDelegation", {})
        config = gate_config.get("config", {})

        # Skip if disabled
        if not gate_config.get("enabled", True):
            return GateCheck("orchestratorDelegation", GateResult.SKIP, "Gate disabled", {}, datetime.now().isoformat())

        agent = context.get("agent", "")
        skill_hint = context.get("skill_hint", "")

        # Only check for Kublai
        if agent != "kublai":
            return GateCheck("orchestratorDelegation", GateResult.SKIP, "Not orchestrator agent", {}, datetime.now().isoformat())

        # Check if using implementation skills
        impl_skills = config.get("implementation_skills", [])
        if skill_hint in impl_skills:
            warn_threshold = config.get("warn_threshold", 2)
            warning_msg = config.get("warning_message", "Orchestrator should delegate implementation")

            return GateCheck(
                "orchestratorDelegation",
                GateResult.WARN,
                warning_msg,
                {"agent": agent, "skill": skill_hint, "implementation_skills": impl_skills},
                datetime.now().isoformat()
            )
        else:
            return GateCheck(
                "orchestratorDelegation",
                GateResult.PASS,
                "Appropriate delegation",
                {"agent": agent, "skill": skill_hint},
                datetime.now().isoformat()
            )

    def _check_squad_chat(self, task_id: str, context: dict) -> GateCheck:
        """Check if lifecycle events were posted to squad chat."""
        gate_config = self.config.get("gates", {}).get("squadChat", {})
        config = gate_config.get("config", {})

        # Skip if disabled
        if not gate_config.get("enabled", True):
            return GateCheck("squadChat", GateResult.SKIP, "Gate disabled", {}, datetime.now().isoformat())

        # Check for squad chat events
        events_to_post = config.get("events_to_post", [])
        posted_events = context.get("squad_chat_events", [])

        missing_events = [e for e in events_to_post if e not in posted_events]

        if not missing_events:
            return GateCheck(
                "squadChat",
                GateResult.PASS,
                f"All lifecycle events posted: {events_to_post}",
                {"posted": posted_events},
                datetime.now().isoformat()
            )
        else:
            # This is a soft gate - warn but don't block
            return GateCheck(
                "squadChat",
                GateResult.WARN,
                f"Missing squad chat events: {missing_events}",
                {"missing": missing_events, "posted": posted_events},
                datetime.now().isoformat()
            )

    def check_gate(self, gate_name: str, task_id: str, context: dict) -> GateCheck:
        """Run a single gate check."""
        handler = self._gate_handlers.get(gate_name)
        if not handler:
            return GateCheck(
                gate_name,
                GateResult.SKIP,
                f"Unknown gate: {gate_name}",
                {},
                datetime.now().isoformat()
            )

        check = handler(task_id, context)
        self._log_check(check)
        return check

    def check_all(self, task_id: str, context: dict) -> List[GateCheck]:
        """Run all enabled gates."""
        results = []

        for gate_name in self._gate_handlers:
            gate_config = self.config.get("gates", {}).get(gate_name, {})
            if gate_config.get("enabled", True):
                check = self.check_gate(gate_name, task_id, context)
                results.append(check)

        return results

    def get_summary(self, results: List[GateCheck]) -> dict:
        """Get summary of gate check results."""
        summary = {
            "total": len(results),
            "passed": 0,
            "warnings": 0,
            "blocked": 0,
            "skipped": 0,
            "all_passed": True,
            "has_warnings": False,
            "is_blocked": False
        }

        for check in results:
            if check.result == GateResult.PASS:
                summary["passed"] += 1
            elif check.result == GateResult.WARN:
                summary["warnings"] += 1
                summary["has_warnings"] = True
            elif check.result == GateResult.BLOCK:
                summary["blocked"] += 1
                summary["is_blocked"] = True
                summary["all_passed"] = False
            elif check.result == GateResult.SKIP:
                summary["skipped"] += 1

        if summary["is_blocked"]:
            summary["all_passed"] = False

        return summary

    def enable_gate(self, gate_name: str) -> bool:
        """Enable a gate."""
        if gate_name not in self._gate_handlers:
            return False

        if "gates" not in self.config:
            self.config["gates"] = {}
        if gate_name not in self.config["gates"]:
            self.config["gates"][gate_name] = {}
        self.config["gates"][gate_name]["enabled"] = True
        self._save_config()
        return True

    def disable_gate(self, gate_name: str) -> bool:
        """Disable a gate."""
        if gate_name not in self._gate_handlers:
            return False

        if "gates" not in self.config:
            self.config["gates"] = {}
        if gate_name not in self.config["gates"]:
            self.config["gates"][gate_name] = {}
        self.config["gates"][gate_name]["enabled"] = False
        self._save_config()
        return True

    def set_gate_config(self, gate_name: str, key: str, value: Any) -> bool:
        """Set a gate configuration value."""
        if gate_name not in self._gate_handlers:
            return False

        if "gates" not in self.config:
            self.config["gates"] = {}
        if gate_name not in self.config["gates"]:
            self.config["gates"][gate_name] = {"config": {}}
        if "config" not in self.config["gates"][gate_name]:
            self.config["gates"][gate_name]["config"] = {}

        self.config["gates"][gate_name]["config"][key] = value
        self._save_config()
        return True

    def get_status(self) -> dict:
        """Get status of all gates."""
        status = {}
        for gate_name in self._gate_handlers:
            gate_config = self.config.get("gates", {}).get(gate_name, {})
            status[gate_name] = {
                "enabled": gate_config.get("enabled", True),
                "description": gate_config.get("description", ""),
                "config": gate_config.get("config", {})
            }
        return status


def main():
    parser = argparse.ArgumentParser(description="Enforcement Gates")
    parser.add_argument("--check-all", metavar="TASK_FILE", help="Check all gates for task")
    parser.add_argument("--check", nargs=2, metavar=("GATE", "TASK_FILE"), help="Check specific gate")
    parser.add_argument("--status", action="store_true", help="Show gate status")
    parser.add_argument("--enable", metavar="GATE", help="Enable a gate")
    parser.add_argument("--disable", metavar="GATE", help="Disable a gate")
    parser.add_argument("--set", nargs=3, metavar=("GATE", "KEY", "VALUE"), help="Set gate config")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    gates = EnforcementGates()

    if args.check_all:
        task_file = Path(args.check_all)
        if not task_file.exists():
            print(f"Task file not found: {task_file}")
            sys.exit(1)

        with open(task_file, "r") as f:
            content = f.read()

        context = {
            "task_content": content,
            "task_file": str(task_file),
            "agent": task_file.parent.parent.name,
        }

        results = gates.check_all(task_file.stem, context)
        summary = gates.get_summary(results)

        if args.json:
            print(json.dumps({
                "task_id": task_file.stem,
                "results": [r.to_dict() for r in results],
                "summary": summary
            }, indent=2))
        else:
            print(f"\nGate Check Results for {task_file.name}:")
            for check in results:
                status = f"[{check.result.value.upper()}]"
                print(f"  {status:10} {check.gate_name}: {check.message}")
            print(f"\nSummary: {summary['passed']} passed, {summary['warnings']} warnings, {summary['skipped']} skipped")

    elif args.check:
        gate_name, task_file = args.check
        task_file = Path(task_file)

        if not task_file.exists():
            print(f"Task file not found: {task_file}")
            sys.exit(1)

        with open(task_file, "r") as f:
            content = f.read()

        context = {
            "task_content": content,
            "task_file": str(task_file),
            "agent": task_file.parent.parent.name,
        }

        check = gates.check_gate(gate_name, task_file.stem, context)

        if args.json:
            print(json.dumps(check.to_dict(), indent=2))
        else:
            print(f"{check.gate_name}: [{check.result.value.upper()}] {check.message}")

    elif args.status:
        status = gates.get_status()
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print("\nEnforcement Gates Status:")
            for gate_name, info in status.items():
                status_str = "ENABLED" if info["enabled"] else "DISABLED"
                print(f"  [{status_str:8}] {gate_name}: {info['description']}")

    elif args.enable:
        if gates.enable_gate(args.enable):
            print(f"Enabled gate: {args.enable}")
        else:
            print(f"Unknown gate: {args.enable}")
            sys.exit(1)

    elif args.disable:
        if gates.disable_gate(args.disable):
            print(f"Disabled gate: {args.disable}")
        else:
            print(f"Unknown gate: {args.disable}")
            sys.exit(1)

    elif args.set:
        gate, key, value = args.set
        # Try to parse value as JSON, fall back to string
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass

        if gates.set_gate_config(gate, key, value):
            print(f"Set {gate}.{key} = {value}")
        else:
            print(f"Unknown gate: {gate}")
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
