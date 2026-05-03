import json

import pytest

from kublai.cache import cache_key
from kublai.graph_adapter import GraphifyAdapter
from kublai.schema_registry import SchemaError, SchemaRegistry


def test_cache_key_ignores_frontmatter_when_body_same():
    prompt_hash = "prompt"
    assert cache_key("body", "claude-opus", prompt_hash) == cache_key("body", "claude-opus", prompt_hash)
    assert cache_key("body", "claude-opus", prompt_hash) != cache_key("body", "claude-haiku", prompt_hash)


def test_graph_adapter_normalizes_nodes_and_edges(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text(
        json.dumps(
            {
                "nodes": [{"id": "a", "label": "A", "community": 1}],
                "links": [{"source": "a", "target": "b", "relation": "mentions", "weight": 0.5}],
            }
        ),
        encoding="utf-8",
    )
    normalized = GraphifyAdapter().normalize(graph)
    assert normalized.nodes[0].id == "a"
    assert normalized.edges[0].relation == "mentions"


def test_schema_registry_validates_required_flat_frontmatter(tmp_path):
    schema_dir = tmp_path / ".schemas" / "default"
    schema_dir.mkdir(parents=True)
    (schema_dir / "v1.schema.json").write_text(
        json.dumps({"required": ["type", "status", "updated", "created", "sources", "tags"], "flat_only": ["tags"]}),
        encoding="utf-8",
    )
    registry = SchemaRegistry(tmp_path / ".schemas")
    registry.validate_frontmatter(
        "concept",
        {
            "type": "concept",
            "status": "active",
            "updated": "2026-05-03",
            "created": "2026-05-03",
            "sources": 1,
            "tags": ["x"],
        },
    )
    with pytest.raises(SchemaError):
        registry.validate_frontmatter("concept", {"type": "concept"})
