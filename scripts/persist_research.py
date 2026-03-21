#!/usr/bin/env python3
"""
Post-completion hook: persist mongke research task results to Neo4j.

Called by agent-task-handler.py after a mongke task completes successfully.
Extracts topic, keywords, and summary from the task result content and
stores them via ResearchStorage for cross-session retrieval.

Also provides lookup_prior_research() for pre-task context injection.
"""

import os
import re
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE = Path.home() / ".openclaw/agents"


def extract_research_metadata(task_description: str, output_content: str) -> Dict[str, Any]:
    """Extract structured metadata from task description and output content.

    Returns dict with: topic, category, keywords, summary, source_urls
    """
    # Topic: use the task description, cleaned up
    topic = task_description.strip()
    if topic.startswith("Research "):
        topic = topic[9:]
    topic = topic[:200]  # cap length

    # Category: infer from content keywords
    content_lower = output_content.lower()
    category = "other"
    category_signals = {
        "security": ["security", "vulnerability", "injection", "attack", "exploit", "cve", "threat"],
        "performance": ["performance", "optimization", "latency", "throughput", "benchmark"],
        "ops": ["deploy", "infrastructure", "monitoring", "devops", "ci/cd", "docker"],
        "dev": ["api", "sdk", "library", "framework", "implementation", "code"],
        "content": ["blog", "article", "writing", "content", "seo", "marketing"],
        "architecture": ["architecture", "design", "pattern", "schema", "system design"],
    }
    best_score = 0
    for cat, signals in category_signals.items():
        score = sum(1 for s in signals if s in content_lower)
        if score > best_score:
            best_score = score
            category = cat

    # Keywords: extract from headings and bold text
    keywords = set()
    # From markdown headings
    for match in re.finditer(r'^#{1,4}\s+(.+)$', output_content, re.MULTILINE):
        for word in match.group(1).split():
            cleaned = re.sub(r'[^a-zA-Z0-9-]', '', word).lower()
            if len(cleaned) > 3:
                keywords.add(cleaned)
    # From bold text
    for match in re.finditer(r'\*\*([^*]+)\*\*', output_content):
        for word in match.group(1).split():
            cleaned = re.sub(r'[^a-zA-Z0-9-]', '', word).lower()
            if len(cleaned) > 3:
                keywords.add(cleaned)
    # From task description
    for word in task_description.split():
        cleaned = re.sub(r'[^a-zA-Z0-9-]', '', word).lower()
        if len(cleaned) > 3:
            keywords.add(cleaned)

    keywords = list(keywords)[:30]  # cap at 30

    # Summary: first non-heading, non-empty paragraph (up to 500 chars)
    summary = ""
    for line in output_content.split('\n'):
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('**Task:') and not line.startswith('**Model:') and not line.startswith('---'):
            summary = line[:500]
            break
    if not summary:
        summary = topic[:500]

    # Source URLs: extract from content
    source_urls = re.findall(r'https?://[^\s\)>\]]+', output_content)
    source_urls = list(set(source_urls))[:20]  # dedupe, cap

    return {
        "topic": topic,
        "category": category,
        "keywords": keywords,
        "summary": summary,
        "source_urls": source_urls,
    }


def persist_task_research(
    agent_name: str,
    task_description: str,
    output_content: str,
    task_id: Optional[str] = None
) -> Optional[str]:
    """Persist a completed research task's findings to Neo4j.

    Args:
        agent_name: Agent that completed the task (only persists for mongke)
        task_description: Original task description
        output_content: Full output content from task execution
        task_id: Optional task ID for linking

    Returns:
        research_id if persisted, None if skipped
    """
    # Only persist for research agent
    if agent_name != "mongke":
        return None

    # Skip very short outputs (likely failures or trivial results)
    if len(output_content.strip()) < 100:
        return None

    try:
        from research_storage import ResearchStorage

        meta = extract_research_metadata(task_description, output_content)

        storage = ResearchStorage()
        try:
            research_id = storage.create_research(
                topic=meta["topic"],
                category=meta["category"],
                keywords=meta["keywords"],
                summary=meta["summary"],
                content=output_content[:10000],  # cap content at 10k chars
                researched_by=agent_name,
                priority="normal",
                source_urls=meta["source_urls"],
                tags=[f"task:{task_id}"] if task_id else [],
            )
            print(f"  [research] Persisted to Neo4j: {research_id} (topic={meta['topic'][:60]})")
            return research_id
        finally:
            storage.close()

    except Exception as e:
        # Non-fatal: don't break task completion flow
        print(f"  [research] Persistence failed (non-fatal): {e}")
        return None


def lookup_prior_research(topic: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Look up prior research on a topic before starting a new research task.

    Returns list of relevant prior research summaries for context injection.
    """
    try:
        from research_storage import ResearchStorage

        storage = ResearchStorage()
        try:
            # Try fulltext search first
            try:
                results = storage.search_by_keyword(topic, limit=limit)
                if results:
                    return [{"topic": r.get("topic", ""), "summary": r.get("summary", ""),
                             "category": r.get("category", ""), "researchId": r.get("researchId", "")}
                            for r in results]
            except Exception:
                pass  # fulltext index may not exist yet

            # Fallback: keyword match on topic field
            results = storage.search_by_topic(topic)
            return [{"topic": r.get("topic", ""), "summary": r.get("summary", ""),
                     "category": r.get("category", ""), "researchId": r.get("researchId", "")}
                    for r in results[:limit]]
        finally:
            storage.close()

    except Exception as e:
        print(f"  [research] Lookup failed: {e}")
        return []


def persist_reflection_research(agent_name: str = "mongke") -> Optional[str]:
    """Extract and persist research insights from an agent's latest reflection.

    Reads the agent's latest reflection file from Claude project memory,
    extracts research findings, and persists them to Neo4j for cross-session retrieval.

    Completed reflections are stored in Claude project memory, not agent memory.

    Args:
        agent_name: Agent to process (default: mongke, only agent with research insights)

    Returns:
        research_id if persisted, None if skipped
    """
    # Only process mongke's reflections (other agents don't generate research insights)
    if agent_name != "mongke":
        return None

    from pathlib import Path

    # Claude project memory where completed reflections are stored
    claude_memory = Path.home() / ".claude/projects/-Users-kublai--openclaw-agents-main/memory"
    if not claude_memory.exists():
        return None

    # Find reflection files for this agent
    reflection_files = sorted(
        claude_memory.glob(f"{agent_name}-reflection-*.md"),
        reverse=True
    )
    if not reflection_files:
        return None

    latest_reflection = reflection_files[0]

    try:
        content = latest_reflection.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    # Skip if content is too short
    if len(content) < 200:
        return None

    try:
        content = latest_reflection.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    # Extract research-relevant sections
    # Look for KEY_FINDING, ISSUE, and brainstorming proposals
    key_finding = ""
    issue = ""
    brainstorming_section = ""
    topic = f"Reflection Insights: {latest_reflection.stem}"

    # Extract KEY_FINDING from REPORT_LOG
    report_match = re.search(r"KEY_FINDING:\s*(.+?)(?:\n|$)", content)
    if report_match:
        key_finding = report_match.group(1).strip()[:500]

    # Extract ISSUE
    issue_match = re.search(r"ISSUE:\s*(.+?)(?:\n|$)", content)
    if issue_match:
        issue = issue_match.group(1).strip()[:500]

    # Extract brainstorming proposals (after "## Brainstorming Focus" or similar)
    brainstorm_match = re.search(
        r"#{1,4}\s*(?:Brainstorming|PROPOSAL|Domain Focus).*?\n(.*?)(?:\n#{1,4}|\Z)",
        content,
        re.DOTALL | re.IGNORECASE
    )
    if brainstorm_match:
        brainstorming_section = brainstorm_match.group(1).strip()[:2000]

    # Extract rule changes as research insights
    rule_matches = re.findall(
        r"NEW RULE:\s*(WHEN.+?THEN.+?)(?=\n\n|\n\*\*|\n##|\Z)",
        content,
        re.DOTALL
    )
    rules_text = "\n".join(rule_matches[:3]) if rule_matches else ""

    # Combine all research content
    research_content = f"""# Reflection Research Insights

**Date:** {latest_reflection.stem}

## Key Finding
{key_finding if key_finding else "No specific key finding documented."}

## Issue Identified
{issue if issue else "No specific issue documented."}

## Behavioral Rules
{rules_text if rules_text else "No new rules proposed."}

## Brainstorming Proposals
{brainstorming_section if brainstorming_section else "No brainstorming section found."}

## Full Reflection Context
{content[:3000]}
"""

    # Skip if content is too short or appears to be a template file
    # A template file has placeholder patterns like [trigger], [action], [default]
    template_indicators = [
        r"\[trigger\]", r"\[action\]", r"\[old default\]", r"\[default\]",
        "ENTER YOUR", "FILL IN", "REPLACE WITH"
    ]
    is_template = any(re.search(pattern, content, re.IGNORECASE) for pattern in template_indicators)

    if len(research_content.strip()) < 200 or is_template:
        return None

    # Extract keywords from reflection
    keywords = set()
    keyword_patterns = [
        r"(?:research|methodology|coverage|accuracy|source|diversity|triangulation|validation|retention|knowledge)",
        r"(?:reflection|pipeline|throughput|bottleneck|optimization)",
    ]
    for pattern in keyword_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        keywords.update([m.lower() for m in matches])

    # Also extract from headings
    for match in re.finditer(r'^#{1,4}\s+(.+)$', content, re.MULTILINE):
        for word in match.group(1).split():
            cleaned = re.sub(r'[^a-zA-Z0-9-]', '', word).lower()
            if len(cleaned) > 3:
                keywords.add(cleaned)

    keyword_list = list(keywords)[:30]

    # Build summary from available data
    summary_parts = []
    if key_finding:
        summary_parts.append(f"Key: {key_finding[:200]}")
    if issue:
        summary_parts.append(f"Issue: {issue[:200]}")
    if rules_text:
        summary_parts.append(f"Rules: {len(rule_matches)} new behaviors proposed")

    summary = " | ".join(summary_parts) if summary_parts else f"Reflection insights from {latest_reflection.stem}"

    try:
        from research_storage import ResearchStorage

        storage = ResearchStorage()
        try:
            # Check if this reflection was already persisted (avoid duplicates)
            existing = storage.search_by_topic(topic, status="active")
            for ex in existing:
                if ex.get("summary", "")[:100] == summary[:100]:
                    # Already persisted
                    return None

            research_id = storage.create_research(
                topic=topic,
                category="architecture",  # Reflections are about system architecture
                keywords=keyword_list,
                summary=summary,
                content=research_content,
                researched_by=agent_name,
                priority="normal",
                source_urls=[],  # No external sources for reflections
                tags=[f"reflection:{latest_reflection.stem}", "self-improvement", "meta-research"],
            )
            print(f"  [research] Persisted reflection research: {research_id} ({topic[:60]})")
            return research_id
        finally:
            storage.close()

    except Exception as e:
        # Non-fatal: don't break reflection pipeline
        print(f"  [research] Reflection persistence failed (non-fatal): {e}")
        return None


def ensure_fulltext_index():
    """Create the Neo4j fulltext index for Research nodes if it doesn't exist."""
    try:
        from neo4j_task_tracker import neo4j_session
        with neo4j_session() as session:
            session.run("""
                CREATE FULLTEXT INDEX research_search IF NOT EXISTS
                FOR (r:Research)
                ON EACH [r.topic, r.summary, r.content, r.keywords]
            """)
            print("[research] Fulltext index ensured")
    except Exception as e:
        print(f"[research] Index creation failed: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Research persistence utilities")
    parser.add_argument("--init-index", action="store_true", help="Create fulltext index")
    parser.add_argument("--stats", action="store_true", help="Show research stats")
    parser.add_argument("--lookup", type=str, help="Look up prior research on topic")
    parser.add_argument("--persist-reflection", action="store_true", help="Persist latest reflection research to Neo4j")
    parser.add_argument("--agent", type=str, default="mongke", help="Agent name for --persist-reflection (default: mongke)")
    args = parser.parse_args()

    if args.init_index:
        ensure_fulltext_index()
    elif args.stats:
        from research_storage import ResearchStorage
        storage = ResearchStorage()
        print(json.dumps(storage.get_stats(), indent=2, default=str))
        storage.close()
    elif args.lookup:
        results = lookup_prior_research(args.lookup)
        for r in results:
            print(f"  [{r['category']}] {r['topic']}: {r['summary'][:100]}")
        if not results:
            print("  No prior research found.")
    elif args.persist_reflection:
        research_id = persist_reflection_research(args.agent)
        if research_id:
            print(f"Persisted reflection research: {research_id}")
        else:
            print("No reflection research persisted (already exists or no new insights)")
    else:
        parser.print_help()
