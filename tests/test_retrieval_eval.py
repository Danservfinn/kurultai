import json
import subprocess
import sys
from pathlib import Path

import pytest

from kublai import retrieval_eval as reval


def _result(rank: int, rel_path: str, body: str = "body", score: float = 1.0) -> dict:
    return {"rank": rank, "rel_path": rel_path, "body_text": body, "score": score}


def test_scrub_query_hashes_and_redacts_sensitive_values() -> None:
    scrubbed = reval.scrub_query(
        "Find x402 notes for operator@example.invalid with Bearer abcdef123456789abcdef and "
        + "/".join(["", "Users", "kublai", "brain", "hard-private", "foo"]),
    )

    assert scrubbed.query_hash.startswith("sha256:")
    assert "operator@example.invalid" not in scrubbed.query_redacted
    assert "Bearer" not in scrubbed.query_redacted
    assert "/".join(["", "Users", "kublai"]) not in scrubbed.query_redacted
    assert scrubbed.query_redacted.endswith("[PRIVATE_PATH]")
    assert {"email", "bearer_token", "path_private"}.issubset(set(scrubbed.redactions))


def test_capture_case_drops_body_text_and_full_scores() -> None:
    case = reval.capture_case(
        case_id="retrieval_eval_test_0001",
        query="gbrain v0.36 skillpack",
        method="knowledge.public_search",
        privacy_scope="public",
        source="fixture",
        results=[_result(1, "analyses/gbrain.md", body="raw private-ish body", score=0.9876)],
        expected={"must_include_rel_paths": ["analyses/gbrain.md"], "notes": "fixture"},
        latency_ms=12.0,
    )

    encoded = json.dumps(case)
    assert "body_text" not in encoded
    assert "raw private-ish body" not in encoded
    assert '"score"' not in encoded
    assert case["baseline"]["results"] == [
        {
            "rank": 1,
            "rel_path": "analyses/gbrain.md",
            "body_hash": reval.sha256_text("raw private-ish body"),
            "score_bucket": "top",
        }
    ]
    reval.validate_case(case)


def test_validate_case_rejects_secret_like_or_body_text_fields() -> None:
    case = reval.capture_case(
        case_id="retrieval_eval_test_0002",
        query="parse agents x402",
        method="knowledge.public_search",
        privacy_scope="public",
        source="fixture",
        results=[_result(1, "entities/parse-agents.md")],
    )
    case["baseline"]["results"][0]["body_text"] = "leak"

    with pytest.raises(ValueError, match="body_text"):
        reval.validate_case(case)

    case["baseline"]["results"][0].pop("body_text")
    case["request"]["query_redacted"] = "api_key=sk-abc123"
    with pytest.raises(ValueError, match="secret-like"):
        reval.validate_case(case)


def test_metric_report_calculates_overlap_stability_latency_and_failures() -> None:
    case = reval.capture_case(
        case_id="retrieval_eval_test_0003",
        query="ogedei bridge capture_all silent ack",
        method="knowledge.public_search",
        privacy_scope="public",
        source="fixture",
        results=[_result(1, "entities/hermes.md"), _result(2, "operations/report.md")],
        expected={"must_include_rel_paths": ["entities/hermes.md", "missing.md"]},
        latency_ms=10,
    )
    replay_results = [
        {"rank": 1, "rel_path": "entities/hermes.md", "body_text": "new", "score": 0.9},
        {"rank": 2, "rel_path": "other.md", "body_text": "new", "score": 0.2},
    ]

    report = reval.evaluate_cases([case], {case["case_id"]: reval.ReplayResult(replay_results, latency_ms=17)})

    assert report["case_count"] == 1
    assert report["mean_jaccard_at_k"] == pytest.approx(1 / 3)
    assert report["top_1_stability_rate"] == 1.0
    assert report["latency_delta_ms_p50"] == 7
    assert report["cases"][0]["must_include_pass"] is False
    assert report["failures"][0]["missing_must_include"] == ["missing.md"]


def test_ndjson_round_trip_and_public_fixture_privacy_gate(tmp_path: Path) -> None:
    case = reval.capture_case(
        case_id="retrieval_eval_test_0004",
        query="Hermes Brain retrieval",
        method="knowledge.public_search",
        privacy_scope="public",
        source="fixture",
        results=[_result(1, "entities/hermes.md")],
    )
    out = tmp_path / "public-smoke.ndjson"

    reval.write_ndjson(out, [case], privacy_scope="public")
    loaded = reval.read_ndjson(out)

    assert loaded == [case]
    assert "body_text" not in out.read_text()


def test_hard_private_fixture_cannot_be_written_to_repo_path(tmp_path: Path) -> None:
    case = reval.capture_case(
        case_id="retrieval_eval_test_0005",
        query="private thing",
        method="knowledge.search_private",
        privacy_scope="hard-private",
        source="fixture",
        results=[_result(1, "hard-private/example.md")],
    )

    with pytest.raises(ValueError, match="hard-private fixtures"):
        reval.write_ndjson(tmp_path / "private.ndjson", [case], privacy_scope="hard-private")


def test_classify_brain_source_policy_tiers() -> None:
    assert reval.classify_brain_source("entities/hermes.md").as_dict() == {
        "tier": 1,
        "source_type": "canonical",
        "default_behavior": "default",
    }
    assert reval.classify_brain_source("operations/reports/run.md").as_dict() == {
        "tier": 2,
        "source_type": "explicit",
        "default_behavior": "fallback",
    }
    assert reval.classify_brain_source("raw/2026-05-22-source.md").as_dict() == {
        "tier": 3,
        "source_type": "forensic",
        "default_behavior": "forensic_only",
    }
    assert reval.classify_brain_source("operations/backups/old/entities/hermes.md").as_dict() == {
        "tier": 3,
        "source_type": "excluded",
        "default_behavior": "forensic_only",
    }
    assert reval.classify_brain_source("hard-private/people/alice/context-card.md").as_dict() == {
        "tier": 4,
        "source_type": "hard_private",
        "default_behavior": "hard_exclude",
    }


def test_local_markdown_search_prefers_canonical_and_excludes_raw_by_default(tmp_path: Path) -> None:
    (tmp_path / "entities").mkdir()
    (tmp_path / "raw").mkdir()
    (tmp_path / "operations" / "backups" / "20260522").mkdir(parents=True)
    (tmp_path / "entities" / "hermes.md").write_text("# Hermes\nbrain-service retrieval policy", encoding="utf-8")
    (tmp_path / "raw" / "huge.md").write_text(("brain-service retrieval policy " * 100), encoding="utf-8")
    (tmp_path / "operations" / "backups" / "20260522" / "old.md").write_text(
        ("brain-service retrieval policy " * 100),
        encoding="utf-8",
    )

    result = reval.LocalMarkdownSearchIndex(tmp_path).search("brain-service retrieval policy", limit=10)

    paths = [row["rel_path"] for row in result.results]
    assert paths[0] == "entities/hermes.md"
    assert "raw/huge.md" not in paths
    assert "operations/backups/20260522/old.md" not in paths


def test_local_markdown_search_can_include_forensic_sources_explicitly(tmp_path: Path) -> None:
    (tmp_path / "entities").mkdir()
    (tmp_path / "raw").mkdir()
    (tmp_path / "entities" / "hermes.md").write_text("# Hermes\nbrain-service retrieval policy", encoding="utf-8")
    (tmp_path / "raw" / "huge.md").write_text(("brain-service retrieval policy " * 100), encoding="utf-8")

    result = reval.LocalMarkdownSearchIndex(tmp_path).search(
        "brain-service retrieval policy",
        limit=10,
        filters={"source_policy": "include-forensic"},
    )

    paths = [row["rel_path"] for row in result.results]
    assert "entities/hermes.md" in paths
    assert "raw/huge.md" in paths


def test_source_policy_report_counts_tiers(tmp_path: Path) -> None:
    for rel in ["entities/hermes.md", "raw/source.md", "operations/backups/old.md", "hard-private/x.md"]:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("brain", encoding="utf-8")

    report = reval.source_policy_report(tmp_path)

    assert report["total_markdown"] == 4
    assert report["tier_counts"] == {
        "tier_1_canonical": 1,
        "tier_3_excluded": 1,
        "tier_3_forensic": 1,
        "tier_4_hard_private": 1,
    }
    assert report["default_included"] == 1


def test_cli_status_reports_capture_disabled_by_default() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "kublai.retrieval_eval", "status"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(proc.stdout)
    assert payload["capture_enabled"] is False
    assert payload["production_capture"] == "disabled"


def test_retrieval_report_includes_source_policy_summary_and_explain_receipt() -> None:
    case = reval.capture_case(
        case_id="retrieval_eval_policy_0001",
        query="source aware retrieval policy",
        method="knowledge.public_search",
        privacy_scope="public",
        source="fixture",
        results=[_result(1, "projects/hermes.md")],
        expected={"must_include_rel_paths": ["projects/hermes.md"]},
    )
    replay_results = [
        {
            "rank": 1,
            "rel_path": "projects/hermes.md",
            "body_text": "source aware retrieval policy canonical answer",
            "score": 42,
            "source_policy": reval.classify_brain_source("projects/hermes.md").as_dict(),
        }
    ]

    report = reval.evaluate_cases([case], {case["case_id"]: reval.ReplayResult(replay_results, latency_ms=3)})

    assert report["source_policy_summary"] == {"tier_1": 1}
    assert report["cases"][0]["replay_results"][0]["source_policy"] == {
        "tier": 1,
        "source_type": "canonical",
        "default_behavior": "default",
    }
    assert reval.build_explain_receipt(report)["policy_enforced"] is True


def test_cli_replay_writes_source_policy_explain_receipt(tmp_path: Path) -> None:
    brain_root = tmp_path / "brain"
    fixture_path = tmp_path / "fixtures.ndjson"
    report_path = tmp_path / "report.json"
    explain_path = tmp_path / "explain.json"
    (brain_root / "projects").mkdir(parents=True)
    (brain_root / "projects" / "hermes.md").write_text("source aware retrieval policy canonical answer", encoding="utf-8")
    case = reval.capture_case(
        case_id="retrieval_eval_policy_cli_0001",
        query="source aware retrieval policy",
        method="knowledge.public_search",
        privacy_scope="public",
        source="fixture",
        results=[_result(1, "projects/hermes.md")],
        expected={"must_include_rel_paths": ["projects/hermes.md"]},
    )
    reval.write_ndjson(fixture_path, [case], privacy_scope="public")

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "kublai.retrieval_eval",
            "replay",
            "--fixtures",
            str(fixture_path),
            "--brain-root",
            str(brain_root),
            "--privacy-scope",
            "public",
            "--report-json",
            str(report_path),
            "--explain-json",
            str(explain_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert json.loads(report_path.read_text())["source_policy_summary"] == {"tier_1": 1}
    explain = json.loads(explain_path.read_text())
    assert explain["policy_enforced"] is True
    assert explain["source_policy_summary"] == {"tier_1": 1}
