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
        "Find x402 notes for danny@example.com with Bearer abcdef1234567890 and /Users/kublai/brain/hard-private/foo",
    )

    assert scrubbed.query_hash.startswith("sha256:")
    assert "danny@example.com" not in scrubbed.query_redacted
    assert "Bearer" not in scrubbed.query_redacted
    assert "/Users/kublai" not in scrubbed.query_redacted
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
