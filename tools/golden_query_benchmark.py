"""Golden-query benchmark for brain-service index parity.

The Phase 2 soak keeps a fixed query set and compares rank overlap against a
checked-in or captured baseline. The baseline is JSON so it can be generated on
the Mac Mini before cutover and replayed during the 7-day soak.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from kublai.brain_service import BrainService


DEFAULT_QUERIES = [
    "agent reflection mistake lesson",
    "capability acquisition pipeline",
    "completed task deliverable",
    "architecture decision rationale",
    "recursive self improvement cycle",
    "Kublai orchestrator delegation",
    "Mongke research synthesis",
    "Temujin implementation testing",
    "Jochi analysis security audit",
    "Ogedei operations health",
    "Signal integration failure",
    "Neo4j retry overshoot",
    "provider health patrol",
    "gateway stderr warning",
    "proposal decree backlog",
    "Tailscale Mac mini",
    "Hermes gateway restore",
    "brain wiki schema",
    "knowledge migration",
    "telemetry claim lock",
    "rate limit counter",
    "notification unread",
    "heartbeat sidecar",
    "online backup snapshot",
    "vector orphan check",
    "Obsidian wikilink",
    "human curation branch",
    "Railway out of scope",
    "AuraDB out of scope",
    "Homebrew Neo4j",
    "agent profile capabilities",
    "learned capability mastery",
    "decision supersedes",
    "historical completed task",
    "dual write reconciliation",
    "operation id idempotency",
    "completion body hash",
    "file watcher reindex",
    "WAL checkpoint monitor",
    "brain service healthcheck",
    "reflection consolidation metarule",
    "security mistake root cause",
    "architecture introspection",
    "proactive reflection opportunity",
    "delegation protocol",
    "task dependency engine",
    "capability based access control",
    "knowledge source of truth",
    "Mac mini canonical brain",
    "this Mac curation replica",
]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = BrainService(args.wiki_root, args.telemetry_db, args.index_db)
    if args.reindex:
        service.reindex()
    report = run_benchmark(
        service=service,
        queries=load_queries(args.queries),
        baseline_path=args.baseline,
        top_k=args.top_k,
        write_baseline=args.write_baseline,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    threshold = args.min_overlap
    return 0 if report["average_rank_overlap"] >= threshold else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="golden-query-benchmark")
    parser.add_argument("--wiki-root", default=str(Path.home() / "brain"))
    parser.add_argument("--telemetry-db", default=str(Path.home() / ".kublai/telemetry.db"))
    parser.add_argument("--index-db", default=str(Path.home() / ".brain-index/brain.db"))
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--min-overlap", type=float, default=0.8)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--reindex", action="store_true")
    return parser


def run_benchmark(
    *,
    service: BrainService,
    queries: list[str],
    baseline_path: Path,
    top_k: int,
    write_baseline: bool,
) -> dict[str, Any]:
    current = {
        query: [row.get("typed_id") or row["id"] for row in service.search(query=query, limit=top_k)]
        for query in queries
    }
    metadata = {
        "embedding_model": "all-MiniLM-L6-v2",
        "embedding_dim": 384,
        "preprocessing_hash": hashlib.sha256("\n".join(queries).encode("utf-8")).hexdigest(),
        "top_k": top_k,
    }
    if write_baseline or not baseline_path.exists():
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps({"metadata": metadata, "results": current}, indent=2, sort_keys=True))
        return {
            "ok": True,
            "mode": "baseline-written",
            "queries": len(queries),
            "average_rank_overlap": 1.0,
            "metadata": metadata,
        }

    baseline = json.loads(baseline_path.read_text())
    expected = baseline["results"]
    overlaps = []
    details = []
    for query in queries:
        old = expected.get(query, [])
        new = current.get(query, [])
        if not old and not new:
            overlap = 1.0
        else:
            denom = max(1, min(len(old), top_k))
            overlap = len(set(old[:top_k]) & set(new[:top_k])) / denom
        overlaps.append(overlap)
        details.append({"query": query, "rank_overlap": overlap, "expected": old[:top_k], "actual": new[:top_k]})
    average = sum(overlaps) / max(1, len(overlaps))
    return {
        "ok": average >= 0.8,
        "mode": "compare",
        "queries": len(queries),
        "average_rank_overlap": average,
        "metadata": metadata,
        "details": details,
    }


def load_queries(path: Path | None) -> list[str]:
    if path is None:
        return DEFAULT_QUERIES
    return [line.strip() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]


if __name__ == "__main__":
    raise SystemExit(main())
