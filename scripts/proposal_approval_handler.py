#!/usr/bin/env python3
"""
proposal_approval_handler.py - Kublai's handler for unanimously approved proposals.

When a proposal receives 6/6 YES votes, this script:
1. Reads the proposal from Neo4j
2. Parses implementation requirements
3. Creates tasks via task_intake.py
4. Links task IDs back to the Proposal node
5. Updates Proposal.status = "implementing"
6. Announces approval to all agents

Usage:
    python proposal_approval_handler.py --check    # Check for unanimous proposals
    python proposal_approval_handler.py --process  # Process all unanimous proposals
"""

import os
import sys
import re
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proposal_manager import ProposalManager
from neo4j_task_tracker import neo4j_session
from kurultai_paths import AGENTS_DIR

KURULTAI_AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]


class ProposalApprovalHandler:
    def __init__(self):
        self.pm = ProposalManager()
        self.base = AGENTS_DIR

    def check_unanimous(self) -> list:
        """Return list of proposals with 6/6 YES votes."""
        return self.pm.check_unanimous_approval()

    def parse_implementation_tasks(self, proposal: dict) -> list:
        """Parse proposal description into implementation tasks.

        Strategy:
        1. Look for explicit "## Implementation Steps" section
        2. Parse numbered list items
        3. Map to agent based on content keywords
        4. If no explicit section, create single task assigned to proposing agent
        """
        description = proposal.get("description", "")
        title = proposal.get("title", "")
        proposing_agent = proposal.get("proposing_agent", "kublai")
        category = proposal.get("category", "feature")
        priority = proposal.get("priority", "normal")

        tasks = []

        # Look for implementation steps section
        impl_match = re.search(
            r'##\s*(?:Implementation\s*(?:Steps|Plan)|Tasks?)\s*\n+(.*?)(?=\n##\s|\Z)',
            description,
            re.DOTALL | re.IGNORECASE
        )

        if impl_match:
            steps_text = impl_match.group(1)
            # Parse numbered or bulleted list
            step_pattern = r'^\s*(?:[\d\-\*]+\.?)\s+(.+)$'
            for line in steps_text.split('\n'):
                match = re.match(step_pattern, line.strip())
                if match:
                    step_text = match.group(1).strip()
                    if step_text:
                        tasks.append({
                            "title": step_text[:80],  # Truncate long titles
                            "body": f"Implementation step for approved proposal: {title}\n\nStep: {step_text}",
                            "agent": self._assign_agent(step_text, proposing_agent, category),
                            "priority": priority,
                            "category": category
                        })
        else:
            # No explicit implementation plan - create single task
            tasks.append({
                "title": f"Implement: {title[:60]}",
                "body": f"Approved proposal requires implementation.\n\n## Proposal\n{description}",
                "agent": self._assign_agent(title, proposing_agent, category),
                "priority": priority,
                "category": category
            })

        return tasks

    def _assign_agent(self, task_text: str, proposing_agent: str, category: str) -> str:
        """Assign task to appropriate agent based on content and category."""
        text_lower = task_text.lower()

        # Category-based defaults
        category_agents = {
            "routing": "temujin",
            "performance": "temujin",
            "reliability": "ogedei",
            "feature": "temujin",
            "refactoring": "temujin",
            "monitoring": "ogedei"
        }

        # Keyword-based overrides
        if any(kw in text_lower for kw in ["code", "script", "function", "implement", "refactor"]):
            return "temujin"
        if any(kw in text_lower for kw in ["infra", "deploy", "cron", "health", "monitor"]):
            return "ogedei"
        if any(kw in text_lower for kw in ["debug", "test", "verify", "audit"]):
            return "jochi"
        if any(kw in text_lower for kw in ["document", "docs", "readme", "guide"]):
            return "chagatai"
        if any(kw in text_lower for kw in ["research", "investigate", "analyze"]):
            return "mongke"

        # Fall back to category default
        return category_agents.get(category, proposing_agent)

    def process_approval(self, proposal_id: str) -> dict:
        """Process a unanimously approved proposal."""
        # Get proposal details
        proposal_data = self.pm.get_proposal(proposal_id)
        if not proposal_data:
            return {"success": False, "error": f"Proposal {proposal_id} not found"}

        proposal = proposal_data["proposal"]

        # Parse implementation tasks
        tasks = self.parse_implementation_tasks(proposal)

        if not tasks:
            return {"success": False, "error": "No implementation tasks parsed"}

        # Create tasks via task_intake.py
        task_ids = []
        for task_spec in tasks:
            try:
                # Import task_intake to create tasks
                from task_intake import create_task_from_dict

                task_id = create_task_from_dict({
                    "agent": task_spec["agent"],
                    "title": task_spec["title"],
                    "body": task_spec["body"],
                    "priority": task_spec["priority"],
                    "source": f"proposal:{proposal_id}",
                    "bucket": "TODAY" if task_spec["priority"] in ("high", "critical") else "WEEK"
                })
                task_ids.append(task_id)
            except Exception as e:
                # Fallback: create task file directly
                task_id = self._create_task_file(task_spec, proposal_id)
                task_ids.append(task_id)

        # Link tasks to proposal
        self.pm.link_implementation_tasks(proposal_id, task_ids)

        # Move proposal file to approved/
        self.pm._move_proposal_file(proposal_id, "pending", "approved")

        return {
            "success": True,
            "proposal_id": proposal_id,
            "title": proposal["title"],
            "tasks_created": len(task_ids),
            "task_ids": task_ids
        }

    def _create_task_file(self, task_spec: dict, proposal_id: str) -> str:
        """Fallback: create task file directly if task_intake fails."""
        import uuid
        from datetime import datetime

        task_id = str(uuid.uuid4())[:12]
        agent = task_spec["agent"]
        priority = task_spec["priority"]
        title = task_spec["title"]
        body = task_spec["body"]

        task_dir = self.base / agent / "tasks"
        task_dir.mkdir(parents=True, exist_ok=True)

        epoch = int(datetime.now().timestamp())
        filepath = task_dir / f"{priority}-{epoch}.md"

        content = f"""---
agent: {agent}
priority: {priority}
created: {datetime.now().isoformat()}
source: proposal:{proposal_id}
depth: 0
task_id: {task_id}
bucket: TODAY
timeout: 7200
---

# Task: {title}

{body}
"""
        filepath.write_text(content)
        return task_id

    def process_all_unanimous(self) -> list:
        """Process all unanimously approved proposals."""
        unanimous = self.check_unanimous()
        results = []

        for proposal in unanimous:
            proposal_id = proposal["proposal_id"]
            print(f"[PROCESSING] {proposal_id}: {proposal['title']}")

            result = self.process_approval(proposal_id)
            results.append(result)

            if result.get("success"):
                print(f"  -> Created {result['tasks_created']} tasks: {result['task_ids']}")
            else:
                print(f"  -> ERROR: {result.get('error')}")

        return results

    def announce_approval(self, proposal: dict, tasks: list):
        """Announce approval to all agents via their notification channels."""
        announcement = f"""## Proposal Approved: {proposal['title']}

**Proposal ID:** {proposal['proposal_id']}
**Category:** {proposal['category']}
**Priority:** {proposal['priority']}

**Votes:** 6/6 unanimous

**Implementation Tasks Created:** {len(tasks)}
{chr(10).join(f"- {tid}" for tid in tasks)}

**Next Steps:**
Assigned agents should check their task queues and begin implementation.

---

*This proposal was automatically approved by unanimous vote of all Kurultai agents.*
"""

        # Write to kurultai announcement file
        announce_file = self.base / "main" / "logs" / "proposal-approvals.log"
        announce_file.parent.mkdir(parents=True, exist_ok=True)

        with open(announce_file, "a") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"[{datetime.now().isoformat()}] APPROVED: {proposal['proposal_id']}\n")
            f.write(announcement)
            f.write(f"\n{'='*60}\n")


def main():
    import argparse
    handler = ProposalApprovalHandler()
    parser = argparse.ArgumentParser(description="Handle approved proposals")
    parser.add_argument("--check", action="store_true", help="Check for unanimous proposals")
    parser.add_argument("--process", action="store_true", help="Process unanimous proposals")
    args = parser.parse_args()

    try:
        if args.check:
            unanimous = handler.check_unanimous()
            if unanimous:
                print(f"Found {len(unanimous)} unanimous proposal(s):")
                for p in unanimous:
                    print(f"  - {p['proposal_id']}: {p['title']}")
            else:
                print("No unanimous proposals found.")

        elif args.process:
            results = handler.process_all_unanimous()
            print(f"\nProcessed {len(results)} proposal(s)")
            success_count = sum(1 for r in results if r.get("success"))
            print(f"Success: {success_count}, Errors: {len(results) - success_count}")

        else:
            # Default: check and report
            unanimous = handler.check_unanimous()
            if unanimous:
                print(f"ACTION_REQUIRED: {len(unanimous)} proposal(s) ready for approval")
                for p in unanimous:
                    print(f"  {p['proposal_id']}: {p['title']}")
                return 1  # Exit code 1 = action needed
            else:
                print("OK: No proposals requiring approval")
                return 0
    finally:
        handler.pm.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
