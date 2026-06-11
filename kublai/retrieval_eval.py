from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

SCHEMA_VERSION = 1
SCRUBBER_VERSION = 1
MAX_QUERY_REDACTED_CHARS = 240
ALLOWED_SOURCES = {"fixture", "dev_cli", "approved_operator_sample"}
ALLOWED_PRIVACY_SCOPES = {"public", "hard-private"}
ALLOWED_METHODS = {"knowledge.search", "knowledge.public_search", "knowledge.search_private"}
PRIVATE_FIXTURE_ROOT = Path.home() / ".kublai" / "retrieval-eval" / "private"
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer\s+[a-z0-9._~+/-]{8,}|password|secret|token\s*[:=]|sk-[a-z0-9_-]{6,})"
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)")
BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/-]{8,}")
TOKEN_ASSIGN_RE = re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+")
PRIVATE_PATH_RE = re.compile(r"/(?:Users|home)/[^\s,;]+(?:hard-private|\.hermes|\.kublai|brain/hard-private)[^\s,;]*")
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
RAW_FORBIDDEN_KEYS = {"body_text", "text", "content", "snippet", "frontmatter", "score"}


@dataclass(frozen=True)
class ScrubbedQuery:
    query_hash: str
    query_redacted: str
    redactions: list[str]


@dataclass(frozen=True)
class ReplayResult:
    results: list[dict[str, Any]]
    latency_ms: float


@dataclass(frozen=True)
class BrainSourceClassification:
    rel_path: str
    tier: int
    source_type: str
    default_behavior: str
    default_include: bool
    rank_bias: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "source_type": self.source_type,
            "default_behavior": self.default_behavior,
        }


CANONICAL_PREFIXES = (
    "entities/",
    "projects/",
    "infrastructure/",
    "concepts/",
    "runbooks/",
    "status/",
    "analyses/",
    "docs/research/",
    "docs/plans/",
)
EXPLICIT_PREFIXES = (
    "operations/reports/",
    "operations/tasks/",
    "operations/verification/",
    "operations/telemetry/",
    "operations/runs/",
    "content/",
    "receipts/",
    "synthesis/",
    "proposals/",
)
FORENSIC_PREFIXES = ("raw/", "captures/", "graphify-out/")
EXCLUDED_PREFIXES = (
    "operations/backups/",
    "_archive/",
    "archive/",
    "node_modules/",
    ".git/",
    ".qmd/",
    "__pycache__/",
)
CANONICAL_FILES = {"index.md", "home.md", "hot.md", "log.md"}


def _normalize_rel_path(rel_path: str | Path) -> str:
    rel = Path(str(rel_path)).as_posix().lstrip("/")
    if Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise ValueError(f"unsafe Brain relative path: {rel_path}")
    return rel


def classify_brain_source(rel_path: str | Path) -> BrainSourceClassification:
    """Classify a Brain markdown path according to the native retrieval policy.

    The classifier is intentionally deterministic and local: it makes the
    documented [[brain-retrieval-policy]] executable for dev/eval tools without
    changing live brain-service or QMD runtime behavior.
    """

    rel = _normalize_rel_path(rel_path)
    if rel.startswith("hard-private/") or "/hard-private/" in rel:
        return BrainSourceClassification(rel, 4, "hard_private", "hard_exclude", False, -1000.0, "hard-private requires explicit private retrieval")
    if rel.startswith(EXCLUDED_PREFIXES):
        return BrainSourceClassification(rel, 3, "excluded", "forensic_only", False, -1000.0, "backup/archive/generated dependency noise")
    if rel in CANONICAL_FILES or rel.startswith(CANONICAL_PREFIXES):
        return BrainSourceClassification(rel, 1, "canonical", "default", True, 100.0, "canonical Brain retrieval surface")
    if rel.startswith(EXPLICIT_PREFIXES):
        return BrainSourceClassification(rel, 2, "explicit", "fallback", True, 10.0, "explicit/down-ranked operational surface")
    if rel.startswith(FORENSIC_PREFIXES):
        return BrainSourceClassification(rel, 3, "forensic", "forensic_only", False, -50.0, "raw/generated forensic evidence surface")
    return BrainSourceClassification(rel, 2, "explicit", "fallback", True, 0.0, "uncategorized markdown; include cautiously")


def _source_policy_mode(filters: Mapping[str, Any] | None) -> str:
    if not filters:
        return "default"
    mode = filters.get("source_policy") or filters.get("retrieval_policy") or "default"
    return str(mode)


def _source_allowed(classification: BrainSourceClassification, *, privacy_scope: str, mode: str) -> bool:
    if classification.source_type == "hard_private":
        return privacy_scope == "hard-private"
    if privacy_scope == "hard-private":
        return False
    if classification.source_type == "excluded":
        return mode in {"include-excluded", "forensic", "forensic-all"}
    if classification.source_type == "forensic":
        return mode in {"include-forensic", "include-excluded", "forensic", "forensic-all"}
    return classification.default_include


def source_policy_report(root: str | Path) -> dict[str, Any]:
    root_path = Path(root)
    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    total = 0
    default_included = 0
    for path in root_path.rglob("*.md"):
        if any(part in {".git", "node_modules", ".qmd", "__pycache__"} for part in path.parts):
            continue
        rel = path.relative_to(root_path).as_posix()
        classification = classify_brain_source(rel)
        key = f"tier_{classification.tier}_{classification.source_type}"
        total += 1
        counts[key] = counts.get(key, 0) + 1
        examples.setdefault(key, [])
        if len(examples[key]) < 5:
            examples[key].append(rel)
        if _source_allowed(classification, privacy_scope="public", mode="default"):
            default_included += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "root": str(root_path),
        "total_markdown": total,
        "tier_counts": dict(sorted(counts.items())),
        "default_included": default_included,
        "default_excluded": total - default_included,
        "examples": {key: examples[key] for key in sorted(examples)},
    }


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _redact(pattern: re.Pattern[str], replacement: str, text: str, redactions: list[str], label: str) -> str:
    if pattern.search(text):
        redactions.append(label)
        return pattern.sub(replacement, text)
    return text


def scrub_query(query: str) -> ScrubbedQuery:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    redactions: list[str] = []
    redacted = query.strip()
    redacted = _redact(EMAIL_RE, "[EMAIL]", redacted, redactions, "email")
    redacted = _redact(BEARER_RE, "[BEARER_TOKEN]", redacted, redactions, "bearer_token")
    redacted = _redact(TOKEN_ASSIGN_RE, lambda m: f"{m.group(1)}=[REDACTED]", redacted, redactions, "token_like")  # type: ignore[arg-type]
    redacted = _redact(PRIVATE_PATH_RE, "[PRIVATE_PATH]", redacted, redactions, "path_private")
    redacted = _redact(PHONE_RE, "[PHONE]", redacted, redactions, "phone")
    redacted = _redact(UUID_RE, "[UUID]", redacted, redactions, "uuid")
    if len(redacted) > MAX_QUERY_REDACTED_CHARS:
        redactions.append("truncated")
        redacted = redacted[:MAX_QUERY_REDACTED_CHARS].rstrip()
    return ScrubbedQuery(query_hash=sha256_text(query), query_redacted=redacted, redactions=sorted(set(redactions)))


def _score_bucket(rank: int, score: float | None = None) -> str:
    if rank <= 1:
        return "top"
    if rank <= 3:
        return "high"
    if rank <= 10:
        return "mid"
    return "low"


def _result_rel_path(result: Mapping[str, Any]) -> str:
    rel = result.get("rel_path") or result.get("path") or result.get("file")
    if not isinstance(rel, str) or not rel.strip():
        raise ValueError("result is missing rel_path")
    rel = rel.strip()
    if Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise ValueError(f"result rel_path must be relative and safe: {rel}")
    return rel


def _result_body(result: Mapping[str, Any]) -> str:
    body = result.get("body_text", result.get("text", result.get("content", "")))
    return body if isinstance(body, str) else json.dumps(body, sort_keys=True, ensure_ascii=False)


def scrub_result(result: Mapping[str, Any], fallback_rank: int) -> dict[str, Any]:
    rank = int(result.get("rank") or fallback_rank)
    rel_path = _result_rel_path(result)
    body_hash = result.get("body_hash") if isinstance(result.get("body_hash"), str) else sha256_text(_result_body(result))
    score = result.get("score") if isinstance(result.get("score"), (int, float)) else None
    out = {"rank": rank, "rel_path": rel_path, "body_hash": body_hash, "score_bucket": _score_bucket(rank, score)}
    source_policy = result.get("source_policy")
    if isinstance(source_policy, Mapping):
        out["source_policy"] = {
            "tier": int(source_policy.get("tier", classify_brain_source(rel_path).tier)),
            "source_type": str(source_policy.get("source_type", classify_brain_source(rel_path).source_type)),
            "default_behavior": str(source_policy.get("default_behavior", classify_brain_source(rel_path).default_behavior)),
        }
    return out


def capture_case(
    *,
    case_id: str,
    query: str,
    method: str,
    privacy_scope: str,
    source: str,
    results: Sequence[Mapping[str, Any]],
    expected: Mapping[str, Any] | None = None,
    latency_ms: float = 0.0,
    filters: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    scrubbed = scrub_query(query)
    case = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "created_at": created_at or _now_iso(),
        "source": source,
        "privacy_scope": privacy_scope,
        "request": {
            "method": method,
            "query_hash": scrubbed.query_hash,
            "query_redacted": scrubbed.query_redacted,
            "limit": len(results) or 10,
            "filters": dict(filters or {"node_type": None}),
        },
        "expected": {
            "top_k_rel_paths": list((expected or {}).get("top_k_rel_paths", [_result_rel_path(r) for r in results])),
            "must_include_rel_paths": list((expected or {}).get("must_include_rel_paths", [])),
            "notes": str((expected or {}).get("notes", "")),
        },
        "baseline": {
            "captured_at": created_at or _now_iso(),
            "index_db_hash": None,
            "results": [scrub_result(result, i + 1) for i, result in enumerate(results)],
            "latency_ms": float(latency_ms),
        },
        "scrub": {
            "scrubber_version": SCRUBBER_VERSION,
            "query_redactions": scrubbed.redactions,
            "raw_body_persisted": False,
        },
    }
    validate_case(case)
    return case


def _walk_keys(obj: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(obj, dict):
        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else str(key)
            yield new_path, value
            yield from _walk_keys(value, new_path)
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            yield from _walk_keys(value, f"{path}[{idx}]")


def _validate_rel_paths(paths: Sequence[Any], field: str, privacy_scope: str) -> None:
    for value in paths:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field} must contain non-empty strings")
        p = Path(value)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError(f"{field} contains unsafe path: {value}")
        if privacy_scope == "public" and (value.startswith("hard-private/") or "/hard-private/" in value):
            raise ValueError("public fixtures may not reference hard-private paths")


def validate_case(case: Mapping[str, Any]) -> None:
    for key in ["schema_version", "case_id", "created_at", "source", "privacy_scope", "request", "expected", "baseline", "scrub"]:
        if key not in case:
            raise ValueError(f"missing required field: {key}")
    if case["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")
    if case["source"] not in ALLOWED_SOURCES:
        raise ValueError("invalid source")
    privacy_scope = str(case["privacy_scope"])
    if privacy_scope not in ALLOWED_PRIVACY_SCOPES:
        raise ValueError("invalid privacy_scope")
    req = case["request"]
    if not isinstance(req, Mapping):
        raise ValueError("request must be an object")
    if req.get("method") not in ALLOWED_METHODS:
        raise ValueError("invalid request.method")
    if privacy_scope == "public" and req.get("method") == "knowledge.search_private":
        raise ValueError("public fixtures cannot use search_private")
    if privacy_scope == "hard-private" and req.get("method") == "knowledge.public_search":
        raise ValueError("hard-private fixtures cannot use public_search")
    qh = req.get("query_hash")
    if not isinstance(qh, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", qh):
        raise ValueError("request.query_hash must be sha256:<64 hex>")
    qr = req.get("query_redacted", "")
    if not isinstance(qr, str) or len(qr) > MAX_QUERY_REDACTED_CHARS:
        raise ValueError("request.query_redacted must be a string <= 240 chars")
    if SECRET_RE.search(qr):
        raise ValueError("request.query_redacted contains secret-like text")
    for path, value in _walk_keys(case):
        key = path.rsplit(".", 1)[-1]
        if key in {"body_text", "content", "snippet", "frontmatter"}:
            raise ValueError(f"fixture contains forbidden raw field: {key}")
        if isinstance(value, str) and SECRET_RE.search(value):
            raise ValueError(f"fixture contains secret-like text at {path}")
    expected = case.get("expected", {})
    if not isinstance(expected, Mapping):
        raise ValueError("expected must be an object")
    _validate_rel_paths(list(expected.get("top_k_rel_paths", [])), "expected.top_k_rel_paths", privacy_scope)
    _validate_rel_paths(list(expected.get("must_include_rel_paths", [])), "expected.must_include_rel_paths", privacy_scope)
    baseline = case["baseline"]
    if not isinstance(baseline, Mapping):
        raise ValueError("baseline must be an object")
    results = baseline.get("results")
    if not isinstance(results, list):
        raise ValueError("baseline.results must be a list")
    for result in results:
        if not isinstance(result, Mapping):
            raise ValueError("baseline.results entries must be objects")
        allowed = {"rank", "rel_path", "body_hash", "score_bucket", "source_policy"}
        extras = set(result) - allowed
        if extras:
            raise ValueError(f"baseline result contains forbidden fields: {sorted(extras)}")
        _validate_rel_paths([result.get("rel_path")], "baseline.results.rel_path", privacy_scope)
        source_policy = result.get("source_policy")
        if source_policy is not None:
            if not isinstance(source_policy, Mapping):
                raise ValueError("baseline result source_policy must be an object")
            if set(source_policy) - {"tier", "source_type", "default_behavior"}:
                raise ValueError("baseline result source_policy contains forbidden fields")
        bh = result.get("body_hash")
        if not isinstance(bh, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", bh):
            raise ValueError("baseline result body_hash must be sha256:<64 hex>")
    scrub = case.get("scrub")
    if not isinstance(scrub, Mapping) or scrub.get("raw_body_persisted") is not False:
        raise ValueError("scrub.raw_body_persisted must be false")


def read_ndjson(path: str | Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            case = json.loads(line)
            try:
                validate_case(case)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_no}: {exc}") from exc
            cases.append(case)
    return cases


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def write_ndjson(path: str | Path, cases: Sequence[Mapping[str, Any]], *, privacy_scope: str) -> None:
    out = Path(path)
    if privacy_scope == "hard-private" and not _is_under(out, PRIVATE_FIXTURE_ROOT):
        raise ValueError(f"hard-private fixtures must be written under {PRIVATE_FIXTURE_ROOT}")
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for case in cases:
        validate_case(case)
        if case["privacy_scope"] != privacy_scope:
            raise ValueError("case privacy_scope does not match output privacy_scope")
        lines.append(json.dumps(case, sort_keys=True, ensure_ascii=False))
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def jaccard_at_k(a: Sequence[str], b: Sequence[str], k: int | None = None) -> float:
    aa = set(a[:k] if k else a)
    bb = set(b[:k] if k else b)
    if not aa and not bb:
        return 1.0
    return len(aa & bb) / len(aa | bb)


def _percentile(values: Sequence[float], pct: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    idx = (len(ordered) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def evaluate_cases(cases: Sequence[Mapping[str, Any]], replay_by_case_id: Mapping[str, ReplayResult], *, k: int | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for case in cases:
        validate_case(case)
        cid = str(case["case_id"])
        replay = replay_by_case_id[cid]
        baseline_paths = [r["rel_path"] for r in case["baseline"]["results"]]
        replay_scrubbed = [scrub_result(r, i + 1) for i, r in enumerate(replay.results)]
        replay_paths = [r["rel_path"] for r in replay_scrubbed]
        kk = k or max(len(baseline_paths), len(replay_paths), 1)
        must = list(case.get("expected", {}).get("must_include_rel_paths", []))
        missing = [path for path in must if path not in replay_paths[:kk]]
        row = {
            "case_id": cid,
            "privacy_scope": case["privacy_scope"],
            "source": case["source"],
            "jaccard_at_k": jaccard_at_k(baseline_paths, replay_paths, kk),
            "top_1_stable": bool(baseline_paths and replay_paths and baseline_paths[0] == replay_paths[0]),
            "latency_delta_ms": float(replay.latency_ms) - float(case["baseline"].get("latency_ms", 0.0)),
            "must_include_pass": not missing,
            "replay_results": replay_scrubbed,
        }
        rows.append(row)
        if missing:
            failures.append({"case_id": cid, "missing_must_include": missing})
    jaccards = [r["jaccard_at_k"] for r in rows]
    latencies = [r["latency_delta_ms"] for r in rows]
    stable = [r["top_1_stable"] for r in rows]
    scopes: dict[str, int] = {}
    sources: dict[str, int] = {}
    policy_summary: dict[str, int] = {}
    for row in rows:
        scopes[row["privacy_scope"]] = scopes.get(row["privacy_scope"], 0) + 1
        sources[row["source"]] = sources.get(row["source"], 0) + 1
        for result in row["replay_results"]:
            policy = result.get("source_policy") if isinstance(result, Mapping) else None
            if isinstance(policy, Mapping):
                key = f"tier_{policy.get('tier')}"
                policy_summary[key] = policy_summary.get(key, 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "case_count": len(rows),
        "fixture_count_by_privacy_scope": scopes,
        "fixture_count_by_source": sources,
        "mean_jaccard_at_k": statistics.fmean(jaccards) if jaccards else None,
        "median_jaccard_at_k": statistics.median(jaccards) if jaccards else None,
        "top_1_stability_rate": (sum(1 for x in stable) / len(stable)) if stable else None,
        "latency_delta_ms_p50": _percentile(latencies, 0.50),
        "latency_delta_ms_p95": _percentile(latencies, 0.95),
        "failures": failures,
        "source_policy_summary": dict(sorted(policy_summary.items())),
        "cases": rows,
    }


def build_explain_receipt(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return a compact, scrubbed source-policy explain receipt for eval reports."""
    summary = report.get("source_policy_summary") if isinstance(report, Mapping) else {}
    failures = report.get("failures") if isinstance(report, Mapping) else []
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "case_count": int(report.get("case_count", 0)) if isinstance(report, Mapping) else 0,
        "policy_enforced": bool(summary is not None),
        "source_policy_summary": dict(summary) if isinstance(summary, Mapping) else {},
        "failure_count": len(failures) if isinstance(failures, Sequence) else 0,
    }


class LocalMarkdownSearchIndex:
    """Small deterministic dev-only searcher for explicit fixture replay.

    It is intentionally not wired into live brain-service traffic. It scans markdown
    files under a supplied Brain root and ranks by simple token occurrence.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        privacy_scope: str = "public",
        filters: Mapping[str, Any] | None = None,
        retrieval_mode: str | None = None,
    ) -> ReplayResult:
        started = time.perf_counter()
        tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]+", query) if len(t) > 1]
        rows: list[tuple[float, str, str]] = []
        source_policy = retrieval_mode or _source_policy_mode(filters)
        for path in self.root.rglob("*.md"):
            if any(part in {".git", "node_modules", ".qmd", "__pycache__"} for part in path.parts):
                continue
            rel = path.relative_to(self.root).as_posix()
            classification = classify_brain_source(rel)
            if not _source_allowed(classification, privacy_scope=privacy_scope, mode=source_policy):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            hay = (rel + "\n" + text).lower()
            score = sum(hay.count(tok) for tok in tokens) if tokens else 0
            if score:
                score = float(score) + classification.rank_bias
                if classification.tier == 2:
                    score *= 0.5
                rows.append((float(score), rel, text, classification))
        rows.sort(key=lambda item: (-item[0], item[1]))
        results = [
            {"rank": i + 1, "rel_path": rel, "body_text": text, "score": score, "source_policy": classification.as_dict()}
            for i, (score, rel, text, classification) in enumerate(rows[:limit])
        ]
        return ReplayResult(results=results, latency_ms=(time.perf_counter() - started) * 1000)


def replay_cases(cases: Sequence[Mapping[str, Any]], searcher: Any) -> dict[str, ReplayResult]:
    out: dict[str, ReplayResult] = {}
    for case in cases:
        validate_case(case)
        req = case["request"]
        query = req.get("query_redacted", "")
        if not query:
            raise ValueError(f"case {case['case_id']} has empty query_redacted; cannot replay without query text")
        scope = str(case["privacy_scope"])
        result = searcher.search(query, limit=int(req.get("limit") or 10), privacy_scope=scope, filters=req.get("filters") or {})
        out[str(case["case_id"])] = result
    return out


def write_manifest(path: str | Path, *, fixture_file: str | Path, privacy_scope: str, case_count: int, created_by: str = "kublai") -> None:
    manifest = {
        "fixture_file": str(fixture_file),
        "schema_version": SCHEMA_VERSION,
        "privacy_scope": privacy_scope,
        "case_count": case_count,
        "created_by": created_by,
        "created_at": _now_iso(),
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _cmd_status(args: argparse.Namespace) -> int:
    print(json.dumps({"capture_enabled": False, "production_capture": "disabled", "schema_version": SCHEMA_VERSION}, indent=2))
    return 0


def _cmd_source_policy(args: argparse.Namespace) -> int:
    report = source_policy_report(args.brain_root)
    if args.report_json:
        Path(args.report_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_json).write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    cases = read_ndjson(args.fixtures)
    print(json.dumps({"ok": True, "case_count": len(cases), "fixtures": args.fixtures}, indent=2))
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    cases = read_ndjson(args.fixtures)
    if args.privacy_scope:
        cases = [c for c in cases if c["privacy_scope"] == args.privacy_scope]
    searcher = LocalMarkdownSearchIndex(args.brain_root)
    replay = replay_cases(cases, searcher)
    report = evaluate_cases(cases, replay, k=args.k)
    if args.report_json:
        Path(args.report_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_json).write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    if args.explain_json:
        receipt = build_explain_receipt(report)
        Path(args.explain_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.explain_json).write_text(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if not report["failures"] else 2


def _load_captured_jsonl(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            try:
                case = capture_case(
                    case_id=row["case_id"],
                    query=row["query"],
                    method=row.get("method", "knowledge.public_search"),
                    privacy_scope=row.get("privacy_scope", "public"),
                    source=row.get("source", "dev_cli"),
                    results=row.get("results", []),
                    expected=row.get("expected", {}),
                    latency_ms=float(row.get("latency_ms", 0.0)),
                    filters=row.get("filters") or {"node_type": None},
                )
            except Exception as exc:
                raise ValueError(f"{path}:{line_no}: {exc}") from exc
            cases.append(case)
    return cases


def _cmd_export(args: argparse.Namespace) -> int:
    if args.privacy_scope == "hard-private" and not args.capture_opt_in:
        raise SystemExit("hard-private export requires --capture-opt-in")
    cases = _load_captured_jsonl(Path(args.input))
    selected = [c for c in cases if c["privacy_scope"] == args.privacy_scope]
    write_ndjson(args.output, selected, privacy_scope=args.privacy_scope)
    if args.manifest:
        write_manifest(args.manifest, fixture_file=args.output, privacy_scope=args.privacy_scope, case_count=len(selected))
    print(json.dumps({"ok": True, "output": args.output, "case_count": len(selected), "capture_enabled": bool(args.capture_opt_in)}, indent=2))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dev-only Brain retrieval eval capture/replay harness")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("status", help="Show safety status; capture is disabled by default")
    p.set_defaults(func=_cmd_status)
    p = sub.add_parser("source-policy", help="Report Brain markdown source-policy tiers for a local Brain root")
    p.add_argument("--brain-root", default=str(Path.home() / "brain"))
    p.add_argument("--report-json")
    p.set_defaults(func=_cmd_source_policy)
    p = sub.add_parser("validate", help="Validate a scrubbed NDJSON fixture file")
    p.add_argument("--fixtures", required=True)
    p.set_defaults(func=_cmd_validate)
    p = sub.add_parser("replay", help="Replay fixtures against a local markdown Brain root")
    p.add_argument("--fixtures", required=True)
    p.add_argument("--brain-root", default=str(Path.home() / "brain"))
    p.add_argument("--report-json")
    p.add_argument("--explain-json", help="Write a compact source-policy explain receipt for replay output")
    p.add_argument("--privacy-scope", choices=sorted(ALLOWED_PRIVACY_SCOPES))
    p.add_argument("--k", type=int)
    p.set_defaults(func=_cmd_replay)
    p = sub.add_parser("export", help="Convert explicit dev-captured JSONL rows into scrubbed fixture NDJSON")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--privacy-scope", choices=sorted(ALLOWED_PRIVACY_SCOPES), required=True)
    p.add_argument("--capture-opt-in", action="store_true")
    p.add_argument("--manifest")
    p.set_defaults(func=_cmd_export)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
