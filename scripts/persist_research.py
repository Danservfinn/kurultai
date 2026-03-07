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
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


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


def ensure_fulltext_index():
    """Create the Neo4j fulltext index for Research nodes if it doesn't exist."""
    try:
        from neo4j_task_tracker import get_driver
        driver = get_driver()
        with driver.session() as session:
            session.run("""
                CREATE FULLTEXT INDEX research_search IF NOT EXISTS
                FOR (r:Research)
                ON EACH [r.topic, r.summary, r.content, r.keywords]
            """)
            print("[research] Fulltext index ensured")
        driver.close()
    except Exception as e:
        print(f"[research] Index creation failed: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Research persistence utilities")
    parser.add_argument("--init-index", action="store_true", help="Create fulltext index")
    parser.add_argument("--stats", action="store_true", help="Show research stats")
    parser.add_argument("--lookup", type=str, help="Look up prior research on topic")
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
    else:
        parser.print_help()
