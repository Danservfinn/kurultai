#!/usr/bin/env python3
"""
cast_structured_vote_parallel.py — Parallel agent voting on pipeline proposals.

OPTIMIZED VERSION: Evaluates all proposals concurrently instead of sequentially.
Reduces Phase 4 voting time from 42 minutes to ~7 minutes per agent.

Usage:
    python3 cast_structured_vote_parallel.py --agent temujin --pipeline reflection-2026-03-23

Performance:
    Sequential (old): 6 proposals × 7 minutes = 42 minutes per agent
    Parallel (new):   6 proposals concurrent = 7 minutes per agent
    Improvement:      83% reduction in voting time

Migration:
    1. Test with dry-run mode: --dry-run
    2. Replace cast_structured_vote.py with this version
    3. Monitor first pipeline run for timing
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List

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

# Parallel workers - same as proposal count for maximum parallelization
MAX_WORKERS = 6


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
        return proposals


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


async def evaluate_proposals_parallel(agent: str, proposals: List[dict]) -> Dict[str, dict]:
    """Evaluate all proposals in parallel using ThreadPoolExecutor.

    Args:
        agent: Agent name casting votes
        proposals: List of proposal dicts

    Returns:
        Dict mapping task_id to vote results
    """
    loop = asyncio.get_event_loop()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Create all tasks
        tasks = [
            loop.run_in_executor(
                executor,
                evaluate_proposal_via_llm,
                agent,
                proposal
            )
            for proposal in proposals
        ]

        # Wait for all to complete
        log_event("parallel_evaluation_started", {
            "agent": agent,
            "proposal_count": len(proposals),
            "workers": MAX_WORKERS
        })

        results = await asyncio.gather(*tasks)

        log_event("parallel_evaluation_completed", {
            "agent": agent,
            "proposal_count": len(proposals),
            "results": len(results)
        })

    # Map results to task_ids
    return {
        proposal["task_id"]: result
        for proposal, result in zip(proposals, results)
    }


def _heuristic_vote(agent: str, proposal: dict) -> dict:
    """Heuristic voting for dry-run mode (no LLM calls)."""
    # Simple heuristic: approve if proposal contains domain keywords
    domain = AGENT_DOMAINS.get(agent, AGENT_DOMAINS["kublai"])
    text = (proposal.get("problem", "") + " " +
            proposal.get("solution", "") + " " +
            proposal.get("rationale", "")).lower()

    matches = sum(1 for kw in domain["keywords"] if kw.lower() in text)

    if matches >= 2:
        return {"vote": "APPROVE", "reason": f"Domain match: {matches} keywords"}
    else:
        return {"vote": "REJECT", "reason": f"Low domain relevance: {matches} keywords"}


def cast_structured_vote(agent: str, pipeline_id: str, dry_run: bool = False, parallel: bool = True) -> dict:
    """Main function to cast structured votes on all proposals in a pipeline.

    Args:
        agent: Agent casting votes
        pipeline_id: Pipeline ID to vote on
        dry_run: Use heuristic voting instead of LLM
        parallel: Use parallel evaluation (default: true)

    Returns:
        The structured vote output
    """
    start_time = datetime.now()

    # Fetch proposals
    proposals = fetch_proposal_outputs(pipeline_id)

    if not proposals:
        return {
            "pipeline_id": pipeline_id,
            "voter": agent,
            "votes": {},
            "error": "No completed proposal tasks found for this pipeline"
        }

    # Evaluate proposals
    if parallel and not dry_run:
        # Use async parallel evaluation
        loop = asyncio.get_event_loop()
        votes = loop.run_until_complete(evaluate_proposals_parallel(agent, proposals))
    elif dry_run:
        # Use heuristic voting
        votes = {}
        for proposal in proposals:
            task_id = proposal["task_id"]
            votes[task_id] = _heuristic_vote(agent, proposal)
    else:
        # Use sequential LLM evaluation (legacy)
        votes = {}
        for proposal in proposals:
            task_id = proposal["task_id"]
            votes[task_id] = evaluate_proposal_via_llm(agent, proposal)

    elapsed = (datetime.now() - start_time).total_seconds()

    # Build output
    output = {
        "pipeline_id": pipeline_id,
        "voter": agent,
        "votes": votes,
        "evaluated_at": datetime.now().isoformat(),
        "proposal_count": len(proposals),
        "evaluation_mode": "parallel" if (parallel and not dry_run) else ("sequential" if not dry_run else "heuristic"),
        "elapsed_seconds": elapsed
    }

    # Log the voting event
    log_event("structured_vote_cast", {
        "pipeline_id": pipeline_id,
        "voter": agent,
        "proposal_count": len(proposals),
        "mode": output["evaluation_mode"],
        "elapsed_s": elapsed
    })

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Cast structured votes on pipeline proposals (PARALLEL VERSION)"
    )
    parser.add_argument("--agent", required=True, choices=list(VALID_AGENTS),
                        help="Agent casting votes")
    parser.add_argument("--pipeline", required=True,
                        help="Pipeline ID to vote on (e.g., reflection-2026-03-23)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use heuristic voting instead of LLM (for testing)")
    parser.add_argument("--sequential", action="store_true",
                        help="Use sequential evaluation instead of parallel (legacy mode)")
    args = parser.parse_args()

    result = cast_structured_vote(
        agent=args.agent,
        pipeline_id=args.pipeline,
        dry_run=args.dry_run,
        parallel=not args.sequential
    )

    # Output JSON
    print(json.dumps(result, indent=2))

    # Exit with error if no proposals found
    if result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
