import json
from datetime import datetime, timezone

from kublai.brain_service import BrainService
from kublai.knowledge import KnowledgeStore
from tools.golden_query_benchmark import run_benchmark
from tools.neo4j_knowledge_export import materialize_record


def test_exporter_materializes_historical_reflection_and_task(tmp_path):
    store = KnowledgeStore(tmp_path / "brain")

    reflection = materialize_record(
        store,
        "reflection",
        {
            "id": "reflection-1",
            "agent": "temujin",
            "context": "bad deploy",
            "lesson": "run fixtures first",
            "created_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
        },
        ["Reflection"],
    )
    task = materialize_record(
        store,
        "task",
        {
            "id": "task-1",
            "status": "completed",
            "assigned_to": "jochi",
            "delegated_by": "kublai",
            "summary": "done",
            "completed_at": datetime(2026, 4, 2, tzinfo=timezone.utc),
            "results": {"ok": True},
        },
        ["Task"],
    )

    assert "historical: true" in reflection.read_text()
    assert "reflection_id: reflection-1" in reflection.read_text()
    assert task.relative_to(tmp_path / "brain").as_posix() == "operations/tasks/2026/04/task-task-1.md"
    assert "historical: true" in task.read_text()


def test_golden_query_benchmark_writes_and_compares_baseline(tmp_path):
    service = BrainService(tmp_path / "brain", tmp_path / "telemetry.db", tmp_path / "index.db")
    service.knowledge.record_reflection(agent="jochi", reflection_id="r1", body="security audit lesson")
    service.reindex()

    baseline = tmp_path / "golden.json"
    written = run_benchmark(
        service=service,
        queries=["security audit"],
        baseline_path=baseline,
        top_k=10,
        write_baseline=True,
    )
    compared = run_benchmark(
        service=service,
        queries=["security audit"],
        baseline_path=baseline,
        top_k=10,
        write_baseline=False,
    )

    assert written["mode"] == "baseline-written"
    assert compared["average_rank_overlap"] == 1.0
    assert json.loads(baseline.read_text())["results"]["security audit"] == ["r1"]
