#!/usr/bin/env python3
"""
cast_structured_vote.py — Agent voting on pipeline proposals.

Each agent evaluates proposals from a reflection pipeline and casts
structured APPROVE/REJECT votes with reasoning.

Usage:
    python3 cast_structured_vote.py --agent temujin --pipeline reflection-2026-03-23

Input:
    --agent {name}     Agent casting votes (kublai, temujin, mongke, chagatai, jochi, ogedei)
    --pipeline {pid}   Pipeline ID to vote on (e.g., reflection-2026-03-23)

Output:
    JSON to stdout with pipeline_id, voter, and votes dict:
    {
      "pipeline_id": "reflection-2026-03-23",
      "voter": "temujin",
      "votes": {
        "task-id-1": {"vote": "APPROVE", "reason": "..."},
        "task-id-2": {"vote": "REJECT", "reason": "..."}
      }
    }
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_v2_core import TaskStore
from kurultai_paths import LOGS_DIR

# Valid agents (all Kurultai Khans)
VALID_AGENTS = frozenset(["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"])

# Agent domain expertise for evaluation context
AGENT_DOMAINS = {
    "kublai": {
        "keywords": ["routing", "coordination", "orchestration", "queue", "task", "dispatch", "agent"],
        "expertise": "Agent coordination, task routing, system orchestration",
        "perspective": "cross-agent impact and system-wide effects"
    },
    "temujin": {
        "keywords": ["code", "development", "infrastructure", "api", "technical", "architecture", "implementation"],
        "expertise": "Software development, infrastructure, APIs",
        "perspective": "implementation feasibility and code quality"
    },
    "mongke": {
        "keywords": ["research", "market", "analysis", "data", "knowledge", "information", "discovery"],
        "expertise": "Research, market analysis, knowledge discovery",
        "perspective": "research value and information quality"
    },
    "chagatai": {
        "keywords": ["documentation", "content", "marketing", "communication", "style", "writing", "clarity"],
        "expertise": "Documentation, content, communication",
        "perspective": "clarity, user experience, and communication quality"
    },
    "jochi": {
        "keywords": ["testing", "security", "review", "quality", "audit", "detection", "monitoring"],
        "expertise": "Testing, security, quality assurance",
        "perspective": "security implications and quality risks"
    },
    "ogedei": {
        "keywords": ["operations", "monitoring", "incident", "health", "infrastructure", "alert", "reliability"],
        "expertise": "Operations, monitoring, incident response",
        "perspective": "operational impact and reliability concerns"
    }
}

# LLM evaluation timeout in seconds
LLM_TIMEOUT = 120


def log_event(event_type: str, data: dict):
    """Log voting events to voting.jsonl."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    voting_log = LOGS_DIR / "voting.jsonl"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        **data
    }
    with open(voting_log, "a") as f:
        f.write(json.dumps(entry) + "\n")


def fetch_proposal_outputs(pipeline_id: str) -> List[dict]:
    """Fetch all proposal task outputs from Neo4j for a pipeline.

    Proposal tasks have phase=3 in the pipeline architecture.
    Returns list of dicts with task_id, title, prompt, and output.
    """
    store = TaskStore()
    with store.driver.session() as session:
        # Query for proposal tasks (phase=3) with their outputs
        result = session.run("""
            MATCH (t:Task {pipeline_id: $pipeline_id, phase: 3, domain: 'proposal', status: 'COMPLETED'})
            OPTIONAL MATCH (t)-[:HAS_OUTPUT]->(o:TaskOutput)
            RETURN t.task_id AS task_id,
                   t.title AS title,
                   t.prompt AS prompt,
                   t.assigned_to AS proposer,
                   o.text AS output_text,
                   o.problem AS problem,
                   o.solution AS solution,
                   o.rationale AS rationale
            ORDER BY t.task_id
        """, pipeline_id=pipeline_id)

        proposals = []
        for record in result:
            proposals.append({
                "task_id": record["task_id"],
                "title": record["title"] or "",
                "prompt": record["prompt"] or "",
                "proposer": record["proposer"] or "unknown",
                "output_text": record["output_text"] or "",
                "problem": record["problem"] or "",
                "solution": record["solution"] or "",
                "rationale": record["rationale"] or ""
            })

        # Validate proposals belong to correct pipeline
        valid = [p for p in proposals if p["task_id"].startswith(pipeline_id)]
        if len(valid) < len(proposals):
            logger.warning(
                f"Discarded {len(proposals) - len(valid)} cross-pipeline proposals"
            )
        return valid


def evaluate_proposal_via_llm(agent: str, proposal: dict) -> dict:
    """Use LLM to evaluate a proposal and return vote + reason.

    Returns: {"vote": "APPROVE"|"REJECT", "reason": "..."}
    """
    domain = AGENT_DOMAINS.get(agent, AGENT_DOMAINS["kublai"])

    # Build proposal context
    proposal_context = f"""## Proposal: {proposal['title']}
**Proposer:** {proposal['proposer']}
**Task ID:** {proposal['task_id']}

### Problem
{proposal['problem'] or proposal['prompt'][:500]}

### Proposed Solution
{proposal['solution'] or proposal['output_text'][:1000] or 'No solution text available'}

### Rationale
{proposal['rationale'] or 'No rationale provided'}
"""

    prompt = f"""You are {agent.upper()}, a Khan of the Kurultai with expertise in: {domain['expertise']}.

Your role is to evaluate proposals from your perspective, focusing on {domain['perspective']}.

{proposal_context}

---

## Your Evaluation

As {agent.upper()}, evaluate this proposal considering:
1. **Domain alignment** — Does this align with your expertise area?
2. **Impact vs effort** — Is the expected value worth the implementation cost?
3. **Cross-agent impact** — How does this affect other agents or system-wide concerns?

**IMPORTANT:** Output EXACTLY two lines:
- Line 1: VOTE: APPROVE or VOTE: REJECT (nothing else)
- Line 2: REASON: One sentence explaining your decision (max 120 chars)

Example output:
VOTE: APPROVE
REASON: High-impact monitoring improvement with low implementation effort.
"""

    try:
        result = subprocess.run(
            ["/Users/kublai/.local/bin/claude-agent", "--model", "sonnet", prompt],
            capture_output=True,
            text=True,
            timeout=LLM_TIMEOUT,
            env={**os.environ, "ANOY": "1"}  # Suppress interactive prompts
        )

        output = result.stdout.strip() if result.returncode == 0 else ""

        # Parse the output
        vote = "ABSTAIN"  # Default to abstain on parse failure
        reason = "LLM evaluation completed"

        for line in output.split("\n"):
            line = line.strip()
            if line.upper().startswith("VOTE:"):
                vote_str = line.split(":", 1)[1].strip().upper()
                if vote_str in ("APPROVE", "REJECT"):
                    vote = vote_str
            elif line.upper().startswith("REASON:"):
                reason = line.split(":", 1)[1].strip()[:120]

        return {"vote": vote, "reason": reason}

    except subprocess.TimeoutExpired:
        return {"vote": "ABSTAIN", "reason": "LLM timeout - vote withheld"}
    except Exception as e:
        return {"vote": "ABSTAIN", "reason": f"LLM error - vote withheld: {str(e)[:50]}"}


def cast_structured_vote(agent: str, pipeline_id: str, dry_run: bool = False) -> dict:
    """Main function to cast structured votes on all proposals in a pipeline.

    Returns the structured vote output.
    """
    # Fetch proposals
    proposals = fetch_proposal_outputs(pipeline_id)

    if not proposals:
        return {
            "pipeline_id": pipeline_id,
            "voter": agent,
            "votes": {},
            "error": "No completed proposal tasks found for this pipeline"
        }

    # Evaluate each proposal
    votes = {}
    for proposal in proposals:
        task_id = proposal["task_id"]

        if dry_run:
            # Use heuristic voting in dry-run mode
            votes[task_id] = _heuristic_vote(agent, proposal)
        else:
            # Use LLM evaluation
            votes[task_id] = evaluate_proposal_via_llm(agent, proposal)

    # Build output
    output = {
        "pipeline_id": pipeline_id,
        "voter": agent,
        "votes": votes,
        "evaluated_at": datetime.now().isoformat(),
        "proposal_count": len(proposals)
    }

    # Log the voting event
    log_event("structured_vote_cast", {
        "agent": agent,
        "pipeline_id": pipeline_id,
        "proposals_evaluated": len(proposals),
        "approve_count": sum(1 for v in votes.values() if v["vote"] == "APPROVE"),
        "reject_count": sum(1 for v in votes.values() if v["vote"] == "REJECT"),
        "dry_run": dry_run
    })

    return output


def _heuristic_vote(agent: str, proposal: dict) -> dict:
    """Heuristic voting for dry-run mode.

    Approves if:
    - Domain keywords match agent expertise
    - Solution text exists (not empty)
    Otherwise rejects.
    """
    domain = AGENT_DOMAINS.get(agent, AGENT_DOMAINS["kublai"])

    # Check domain alignment
    content = f"{proposal['title']} {proposal['prompt']} {proposal['solution']}".lower()
    domain_match = any(kw in content for kw in domain["keywords"])

    # Check if proposal has substance
    has_solution = len(proposal.get("solution", "") or "") > 50

    if domain_match and has_solution:
        return {"vote": "APPROVE", "reason": "Domain-aligned proposal with clear solution"}
    elif has_solution:
        return {"vote": "APPROVE", "reason": "Clear proposal outside primary domain"}
    else:
        return {"vote": "REJECT", "reason": "Insufficient detail in proposal"}


def main():
    parser = argparse.ArgumentParser(
        description="Cast structured votes on pipeline proposals"
    )
    parser.add_argument("--agent", required=True,
                       help="Agent casting votes (kublai, temujin, mongke, chagatai, jochi, ogedei)")
    parser.add_argument("--pipeline", required=True,
                       help="Pipeline ID to vote on (e.g., reflection-2026-03-23)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Use heuristic voting instead of LLM")
    parser.add_argument("--output", "-o", help="Write result to file instead of stdout")

    args = parser.parse_args()

    # Validate agent
    if args.agent not in VALID_AGENTS:
        print(f"Error: Invalid agent '{args.agent}'. Valid agents: {', '.join(sorted(VALID_AGENTS))}",
              file=sys.stderr)
        sys.exit(2)

    # Cast votes
    result = cast_structured_vote(args.agent, args.pipeline, dry_run=args.dry_run)

    # Output
    output_json = json.dumps(result, indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_json)
        print(f"Votes written to {args.output}")
    else:
        print(output_json)

    # Exit with success
    sys.exit(0)


if __name__ == "__main__":
    main()
