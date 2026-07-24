from __future__ import annotations

from copy import deepcopy
from typing import Any

from .resolver import resolve_objective, simulate_plan
from .schema_runtime import ContractError, validate_contract_schema

_REVIEWED_ACCEPTANCE = {"accepted", "overridden", "rejected"}


def _recommendation_projection(
    *,
    room_id: str,
    mode: str,
    plan: dict[str, Any],
    simulation_status: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_artifacts = [item["artifact_id"] for item in plan["selected_artifacts"]]
    projection: dict[str, Any] = {
        "schema": "BuildroomRecommendationProjection/v1",
        "room_id": room_id,
        "mode": mode,
        "plan_id": plan["plan_id"],
        "plan_digest": plan["plan_digest"],
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
        "links": [f"solution-graph:{plan['plan_id']}@{plan['plan_digest']}"],
    }
    if extra:
        projection.update(deepcopy(extra))
    validate_contract_schema(projection)
    return projection


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
    else:
        simulation_status = "not_simulated"
    return _recommendation_projection(
        room_id=room_id,
        mode="recommendation_only",
        plan=plan,
        simulation_status=simulation_status,
    )


def _review_state(review: dict[str, Any]) -> str:
    acceptance = review.get("acceptance", "unknown")
    agreement = review.get("post_build_verification_agreement", "unknown")
    if acceptance in _REVIEWED_ACCEPTANCE or agreement in {"agree", "disagree"}:
        return "reviewed"
    if acceptance == "not_yet_reviewed" or agreement == "not_yet_reviewed":
        return "not_yet_reviewed"
    return "unknown"


def _search_resource_ceiling(plan: dict[str, Any]) -> str:
    if plan.get("status") == "search_exhausted":
        return "exhausted"
    if plan.get("status") == "resolved":
        return "within_bounds"
    return "unknown"


def translate_buildroom_shadow_case(
    *,
    case: dict[str, Any],
    objective: dict[str, Any],
    environment: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    """Project one Buildroom shadow case into existing Buildroom receipt surfaces.

    This is a pure projection. It resolves and simulates the supplied contracts but
    never installs artifacts, writes receipts, dispatches work, accesses secrets, or
    retrieves network state.
    """
    plan = resolve_objective(deepcopy(objective), deepcopy(environment), deepcopy(registry))
    if plan["status"] == "resolved":
        simulation = simulate_plan(deepcopy(plan), deepcopy(objective), deepcopy(environment), deepcopy(registry))
        simulation_status = simulation["status"]
        deterministic_replay = simulation["checks"]["resolution_replay"]
    else:
        simulation_status = "not_simulated"
        deterministic_replay = "unknown"
    review = deepcopy(case.get("review", {}))
    evaluation = {
        "review_state": _review_state(review),
        "acceptance": review.get("acceptance", "unknown"),
        "correct_no_plan": review.get("correct_no_plan", "unknown"),
        "false_rejection": review.get("false_rejection", "unknown"),
        "proof_debt": review.get("proof_debt", "unknown"),
        "deterministic_replay": deterministic_replay,
        "search_resource_ceiling": _search_resource_ceiling(plan),
        "post_build_verification_agreement": review.get("post_build_verification_agreement", "unknown"),
    }
    extra = {
        "buildroom_refs": deepcopy(case["source_refs"]),
        "evaluation": evaluation,
        "links": [
            f"solution-graph:{plan['plan_id']}@{plan['plan_digest']}",
            f"shadow-case:{case['case_id']}",
        ],
        "operator_needs_to_know": [
            "Shadow dogfood projection only; no Buildroom state was mutated.",
            "Buildroom refs reuse operator-summary, implementation-receipt, verification-delta, trust, and retention paths.",
        ],
        "operator_decisions_needed": [
            "Review the recommendation against the existing Buildroom receipt chain before any implementation path uses it.",
            "Record acceptance, override, proof debt, and post-build verification agreement in the shadow corpus.",
        ],
    }
    return _recommendation_projection(
        room_id=case["room_id"],
        mode="shadow_dogfood",
        plan=plan,
        simulation_status=simulation_status,
        extra=extra,
    )


def _validate_shadow_case_metrics(case: dict[str, Any]) -> None:
    case_id = case.get("case_id", "<unknown>")
    plan_status = case.get("plan_status")
    simulation_status = case.get("simulation_status")
    review = case.get("review", {})
    if not isinstance(review, dict):
        raise ContractError(f"shadow case {case_id} review contract is invalid")

    if plan_status == "resolved":
        if simulation_status == "not_simulated":
            raise ContractError(f"shadow case {case_id} resolved plan_status requires simulation_status pass or fail")
        if review.get("search_resource_ceiling") != "within_bounds":
            raise ContractError(f"shadow case {case_id} resolved plan_status requires search_resource_ceiling within_bounds")
        return

    if simulation_status != "not_simulated":
        raise ContractError(f"shadow case {case_id} unresolved plan_status requires simulation_status not_simulated")
    if review.get("deterministic_replay") != "unknown":
        raise ContractError(f"shadow case {case_id} not_simulated requires deterministic_replay unknown")
    expected_resource_ceiling = "exhausted" if plan_status == "search_exhausted" else "unknown"
    if review.get("search_resource_ceiling") != expected_resource_ceiling:
        raise ContractError(
            f"shadow case {case_id} {plan_status} requires search_resource_ceiling {expected_resource_ceiling}"
        )


def validate_shadow_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    cases = corpus.get("cases", [])
    case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if len(case_ids) != len(set(case_ids)):
        raise ContractError("append-only case_id values must be unique")
    target = corpus.get("case_target", {})
    if isinstance(target, dict) and len(cases) > target.get("maximum", 50):
        raise ContractError("shadow corpus is bounded to 25-50 reviewed cases")
    validate_contract_schema(corpus)
    target = corpus["case_target"]
    if target != {"minimum": 25, "maximum": 50}:
        raise ContractError("shadow corpus target must remain 25-50 reviewed cases")
    for case in corpus["cases"]:
        _validate_shadow_case_metrics(case)
    return corpus


def _count(values: list[str], keys: list[str], *, unknown_values: set[str] | None = None) -> dict[str, int]:
    counts = {key: 0 for key in keys}
    unknown_values = unknown_values or set()
    for value in values:
        key = "unknown" if value in unknown_values else value
        if key not in counts:
            key = "unknown"
        counts[key] += 1
    return counts


def evaluate_shadow_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    corpus = validate_shadow_corpus(corpus)
    reviews = [case["review"] for case in corpus["cases"]]
    reviewed = [review for review in reviews if review.get("acceptance") in _REVIEWED_ACCEPTANCE]
    target = corpus["case_target"]
    soak_gate = "ready_for_review_gate" if target["minimum"] <= len(reviewed) <= target["maximum"] else "insufficient_reviewed_cases"
    return {
        "schema": "ShadowEvaluationSummary/v1",
        "case_count": len(corpus["cases"]),
        "reviewed_case_count": len(reviewed),
        "soak_gate": soak_gate,
        "acceptance": _count(
            [review.get("acceptance", "unknown") for review in reviews],
            ["accepted", "overridden", "rejected", "unknown"],
            unknown_values={"not_yet_reviewed"},
        ),
        "correct_no_plan": _count(
            [review.get("correct_no_plan", "unknown") for review in reviews],
            ["yes", "no", "not_applicable", "unknown"],
        ),
        "false_rejection": _count(
            [review.get("false_rejection", "unknown") for review in reviews],
            ["yes", "no", "not_applicable", "unknown"],
        ),
        "proof_debt": _count(
            [review.get("proof_debt", "unknown") for review in reviews],
            ["none", "low", "medium", "high", "unknown"],
        ),
        "deterministic_replay": _count(
            [review.get("deterministic_replay", "unknown") for review in reviews],
            ["pass", "fail", "unknown"],
        ),
        "search_resource_ceiling": _count(
            [review.get("search_resource_ceiling", "unknown") for review in reviews],
            ["within_bounds", "exhausted", "unknown"],
        ),
        "post_build_verification_agreement": _count(
            [review.get("post_build_verification_agreement", "unknown") for review in reviews],
            ["agree", "disagree", "not_yet_reviewed", "unknown"],
        ),
    }
