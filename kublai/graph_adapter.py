"""Narrow adapter for graphify JSON artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class GraphAdapterError(ValueError):
    """Raised when graphify output cannot be normalized."""


@dataclass(frozen=True)
class GraphNode:
    id: str
    label: str
    community: int | None = None
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    relation: str
    weight: float = 1.0
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class NormalizedGraph:
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GraphifyAdapter:
    GRAPHIFY_VERSION_RANGE = ("0.5.0", "0.7.0")
    GRAPHIFY_OUT_DIR = Path("/Users/kublai/brain/graphify-out")

    def normalize(self, graph_json_path: str | Path | None = None) -> NormalizedGraph:
        path = Path(graph_json_path) if graph_json_path else self.GRAPHIFY_OUT_DIR / "graph.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "nodes" not in data or "links" not in data:
            raise GraphAdapterError("expected graphify JSON with nodes and links")
        nodes = [
            GraphNode(
                id=str(node.get("id")),
                label=str(node.get("label") or node.get("id")),
                community=node.get("community"),
                data=dict(node),
            )
            for node in data.get("nodes", [])
        ]
        edges = [
            GraphEdge(
                source=str(edge.get("source") or edge.get("_src")),
                target=str(edge.get("target") or edge.get("_tgt")),
                relation=str(edge.get("relation") or "related"),
                weight=float(edge.get("weight") or edge.get("confidence_score") or 1.0),
                data=dict(edge),
            )
            for edge in data.get("links", [])
        ]
        return NormalizedGraph(nodes=nodes, edges=edges)
