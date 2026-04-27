"""Export Neo4j knowledge nodes to the brain wiki operational schema.

Phase 2 keeps telemetry in Neo4j but moves durable knowledge records into
markdown. This exporter is intentionally conservative: it only reads Neo4j,
only writes through KnowledgeStore, and supports --dry-run before materializing.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from kublai.knowledge import KnowledgeStore, body_hash, slugify


KNOWLEDGE_QUERIES = {
    "reflection": """
        MATCH (n)
        WHERE any(label IN labels(n) WHERE label IN ['Reflection', 'AgentReflection'])
        RETURN n, labels(n) AS labels
        ORDER BY coalesce(n.created_at, n.created, n.updated_at, n.updated, '') ASC
    """,
    "capability": """
        MATCH (n)
        WHERE any(label IN labels(n) WHERE label IN ['LearnedCapability', 'Capability'])
        RETURN n, labels(n) AS labels
        ORDER BY coalesce(n.created_at, n.created, n.updated_at, n.updated, '') ASC
    """,
    "decision": """
        MATCH (n:AgentTeam)
        WHERE n.decision IS NOT NULL
           OR n.rationale IS NOT NULL
           OR n.summary IS NOT NULL
           OR n.description IS NOT NULL
        RETURN n, labels(n) AS labels
        ORDER BY coalesce(n.created_at, n.created, n.updated_at, n.updated, '') ASC
    """,
    "task": """
        MATCH (n:Task)
        WHERE toLower(toString(n.status)) = 'completed'
        RETURN n, labels(n) AS labels
        ORDER BY coalesce(n.completed_at, n.updated_at, n.created_at, '') ASC
    """,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    rows = export_knowledge(
        wiki_root=args.wiki_root,
        uri=args.uri,
        user=args.user,
        password=args.password,
        database=args.database,
        kinds=args.kind,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print(json.dumps({"dry_run": args.dry_run, "rows": rows}, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="neo4j-knowledge-export")
    parser.add_argument("--wiki-root", default=os.getenv("BRAIN_WIKI_ROOT", str(Path.home() / "brain")))
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--database", default=os.getenv("NEO4J_DATABASE", "neo4j"))
    parser.add_argument("--kind", action="append", choices=sorted(KNOWLEDGE_QUERIES), help="export only this kind")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def export_knowledge(
    *,
    wiki_root: str | Path,
    uri: str,
    user: str,
    password: str | None,
    database: str,
    kinds: list[str] | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    from neo4j import GraphDatabase

    selected = kinds or list(KNOWLEDGE_QUERIES)
    store = KnowledgeStore(wiki_root)
    counts: dict[str, int] = {}
    auth = (user, password or "")
    with GraphDatabase.driver(uri, auth=auth) as driver:
        for kind in selected:
            query = KNOWLEDGE_QUERIES[kind]
            if limit is not None:
                query = f"{query}\nLIMIT {int(limit)}"
            with driver.session(database=database) as session:
                records = list(session.run(query))
            counts[kind] = len(records)
            if dry_run:
                continue
            for record in records:
                node = dict(record["n"])
                labels = [str(label) for label in record["labels"]]
                materialize_record(store, kind, node, labels)
    return counts


def materialize_record(store: KnowledgeStore, kind: str, node: dict[str, Any], labels: Iterable[str]) -> Path:
    if kind == "reflection":
        reflection_id = str(first(node, "reflection_id", "id", "uuid") or stable_id("reflection", node))
        agent = str(first(node, "agent", "agent_id", "created_by", "author") or "unknown")
        return store.write_page(
            f"operations/reflections/{date_part(node)}-{slugify(agent)}-{slugify(reflection_id)}.md",
            base_frontmatter(node, "reflection", "reflection_id", reflection_id, labels) | {
                "agent": agent,
                "historical": True,
            },
            reflection_body(node),
            typed_field="reflection_id",
            typed_id=reflection_id,
        )
    if kind == "capability":
        capability_id = str(first(node, "capability_id", "id", "name", "title") or stable_id("capability", node))
        return store.write_page(
            f"operations/capabilities/{slugify(capability_id)}.md",
            base_frontmatter(node, "capability", "capability_id", capability_id, labels) | {
                "learned_by": str(first(node, "learned_by", "agent", "agent_id") or ""),
                "historical": True,
            },
            generic_body("Capability", node),
            typed_field="capability_id",
            typed_id=capability_id,
        )
    if kind == "decision":
        decision_id = str(first(node, "decision_id", "id", "name") or stable_id("decision", node))
        return store.write_page(
            f"operations/decisions/{date_part(node)}-{slugify(decision_id)}.md",
            base_frontmatter(node, "decision", "decision_id", decision_id, labels) | {
                "agent": str(first(node, "agent", "agent_id", "owner") or "agent-team"),
                "historical": True,
            },
            generic_body("Decision", node),
            typed_field="decision_id",
            typed_id=decision_id,
        )
    if kind == "task":
        task_id = str(first(node, "task_id", "id", "uuid") or stable_id("task", node))
        completed_at_ms = timestamp_ms(first(node, "completed_at", "updated_at", "created_at"))
        return store.record_completed_task(
            task_id=task_id,
            agent=str(first(node, "agent", "assigned_to", "claimed_by") or "unknown"),
            delegated_by=str(first(node, "delegated_by", "created_by", "source") or "neo4j-import"),
            completed_at_ms=completed_at_ms,
            deliverable=str(first(node, "deliverable", "summary", "description", "title") or "Imported completed task"),
            results=safe_json(first(node, "results", "result", "payload") or {}),
            historical=True,
        )
    raise ValueError(f"unknown export kind: {kind}")


def base_frontmatter(
    node: dict[str, Any],
    node_type: str,
    id_field: str,
    typed_id: str,
    labels: Iterable[str],
) -> dict[str, Any]:
    date = date_part(node)
    body = generic_body(node_type.title(), node)
    return {
        "type": node_type,
        id_field: typed_id,
        "title": str(first(node, "title", "name", "summary", "description") or typed_id)[:120],
        "status": str(first(node, "status") or "active").lower(),
        "created": date,
        "updated": date,
        "sources": 1,
        "neo4j_labels": sorted(labels),
        "completion_body_hash": body_hash(body),
        "tags": ["kublai", node_type, "historical"],
    }


def reflection_body(node: dict[str, Any]) -> str:
    fields = [
        ("Context", first(node, "context", "description", "summary")),
        ("Expected Behavior", first(node, "expected_behavior")),
        ("Actual Behavior", first(node, "actual_behavior")),
        ("Root Cause", first(node, "root_cause")),
        ("Lesson", first(node, "lesson", "content", "body")),
    ]
    return sections("Historical Reflection", fields, node)


def generic_body(title: str, node: dict[str, Any]) -> str:
    preferred = [
        ("Summary", first(node, "summary", "description", "content", "body")),
        ("Decision", first(node, "decision")),
        ("Rationale", first(node, "rationale", "reason")),
        ("Result", first(node, "result", "results", "outcome")),
    ]
    return sections(title, preferred, node)


def sections(title: str, fields: list[tuple[str, Any]], node: dict[str, Any]) -> str:
    chunks = [f"# {title}\n"]
    for heading, value in fields:
        if value in (None, "", [], {}):
            continue
        chunks.append(f"## {heading}\n\n{stringify(value)}\n")
    chunks.append("## Neo4j Properties\n")
    chunks.append("```json\n")
    chunks.append(json.dumps({k: stringify(v) for k, v in sorted(node.items())}, indent=2, sort_keys=True))
    chunks.append("\n```\n")
    return "\n".join(chunks)


def first(node: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = node.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def stable_id(prefix: str, node: dict[str, Any]) -> str:
    payload = json.dumps({k: stringify(v) for k, v in sorted(node.items())}, sort_keys=True)
    import hashlib

    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def date_part(node: dict[str, Any]) -> str:
    value = first(node, "created_at", "created", "completed_at", "updated_at", "updated")
    dt = parse_datetime(value)
    return dt.date().isoformat()


def timestamp_ms(value: Any) -> int:
    return int(parse_datetime(value).timestamp() * 1000)


def parse_datetime(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)


def safe_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
            return loaded if isinstance(loaded, dict) else {"value": loaded}
        except json.JSONDecodeError:
            return {"value": value}
    return {"value": stringify(value)}


def stringify(value: Any) -> str:
    if hasattr(value, "iso_format"):
        return value.iso_format()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
