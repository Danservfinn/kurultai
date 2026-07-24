from __future__ import annotations

from copy import deepcopy
from typing import Any

from .resolver import resolve_objective, simulate_plan
from .schema_runtime import validate_contract_schema


def recommend_for_buildroom(
    *,
    room_id: str,
    objective: dict[str, Any],
    environment: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    """Return a recommendation projection only; never write, dispatch, or authorize."""
    plan = resolve_objective(deepcopy(objective), deepcopy(environment), deepcopy(registry))
    if plan["status"] == "resolved":
        simulation = simulate_plan(deepcopy(plan), deepcopy(objective), deepcopy(environment), deepcopy(registry))
        simulation_status = simulation["status"]
        plan_digest = plan["plan_digest"]
    else:
        simulation_status = "not_simulated"
        plan_digest = plan["plan_digest"]
    selected_artifacts = [item["artifact_id"] for item in plan["selected_artifacts"]]
    projection: dict[str, Any] = {
        "schema": "BuildroomRecommendationProjection/v1",
        "room_id": room_id,
        "mode": "recommendation_only",
        "plan_id": plan["plan_id"],
        "plan_digest": plan_digest,
        "selected_artifacts": selected_artifacts,
        "reason_codes": deepcopy(plan["reason_codes"]),
        "simulation_status": simulation_status,
        "artifact_invocation_count": 0,
        "authority": "none",
        "dispatch_allowed": False,
        "requires_operator_approval": True,
        "operator_needs_to_know": [
            "Solution Graph produced a read-only recommendation with no execution authority.",
            f"Selected artifact count: {len(selected_artifacts)}.",
        ],
        "operator_decisions_needed": [
            "Approve, modify, or reject the recommendation before any Buildroom implementation path uses it."
        ],
        "links": [f"solution-graph:{plan['plan_id']}@{plan_digest}"],
    }
    validate_contract_schema(projection)
    return projection
