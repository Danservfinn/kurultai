"""RSI tracking helpers backed by typed wiki pages."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from .knowledge import KnowledgeStore, slugify, utc_date


@dataclass(frozen=True)
class RsiCycle:
    rsi_id: str
    hypothesis: str
    intervention: str
    outcome: str
    path: Path


class RsiStore:
    """Records recursive-improvement cycles as operational wiki pages."""

    def __init__(self, knowledge: KnowledgeStore):
        self.knowledge = knowledge

    def record_cycle(
        self,
        *,
        hypothesis: str,
        intervention: str,
        outcome: str = "pending",
        agent: str = "kublai",
        rsi_id: str | None = None,
        cycle_number: int | None = None,
    ) -> RsiCycle:
        rsi_id = rsi_id or str(uuid.uuid4())
        cycle = cycle_number or 1
        date = utc_date()
        body = (
            f"# RSI Cycle {cycle}\n\n"
            f"## Hypothesis\n\n{hypothesis}\n\n"
            f"## Intervention\n\n{intervention}\n\n"
            f"## Outcome\n\n{outcome}\n"
        )
        path = self.knowledge.write_page(
            f"operations/rsi-cycles/cycle-{cycle:03d}-{slugify(rsi_id)}.md",
            {
                "type": "rsi-cycle",
                "rsi_id": rsi_id,
                "agent": agent,
                "hypothesis": hypothesis,
                "status": "active" if outcome == "pending" else "completed",
                "created": date,
                "updated": date,
                "sources": 1,
                "tags": ["kublai", "rsi"],
            },
            body,
            typed_field="rsi_id",
            typed_id=rsi_id,
        )
        return RsiCycle(rsi_id, hypothesis, intervention, outcome, path)
