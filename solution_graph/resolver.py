from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from .canonical import canonical_digest
from .validation import ContractError, validate_environment, validate_fixture, validate_objective

_PERMISSION_ORDER = {
    "read-only": 0,
    "local-read": 1,
    "sandbox-local-write": 2,
    "host-write": 3,
    "external-effect": 4,
}
_EVIDENCE_RANK = {
    "revoked": 0.0,
    "observed-fail": 0.05,
    "conflicted": 0.20,
    "stale": 0.35,
    "unknown": 0.40,
    "declared": 0.55,
    "observed-pass": 0.95,
}
_BLOCKING_STATES = {"revoked", "observed-fail"}
_SOURCE_STRENGTH = {
    "publisher_declaration": 0.55,
    "publisher_self_test": 0.70,
    "registry_static_validation": 0.75,
    "registry_sandbox_fixture": 0.85,
    "independent_verifier": 0.95,
    "tenant_observed_run": 0.95,
    "receiver_attested_external_effect": 0.98,
    "incident": 1.0,
}
_POLICY_VERSION = "solution-graph-policy/v0.1"
_SCORING_VERSION = "deterministic-evidence-fit/v0.1"


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _evidence_state(
    manifest: dict[str, Any], observations: list[dict[str, Any]], environment: dict[str, Any]
) -> tuple[str, str]:
    declared_capabilities = {item["capability_id"] for item in manifest["capabilities"]}
    exact = [
        obs for obs in observations
        if obs["subject"]["artifact_id"] == manifest["artifact_id"]
        and obs["subject"]["version"] == manifest["version"]
        and obs["subject"]["digest"] == manifest["digest"]
        and obs["environment_ref"] == environment["environment_id"]
        and obs["claim"]["capability_id"] in declared_capabilities
    ]
    if not exact:
        return "declared", "publisher_declaration"
    evaluation_time = _time(environment["evaluation_time"])
    active: list[dict[str, Any]] = []
    expired_observations: list[dict[str, Any]] = []
    for observation in exact:
        if _time(observation["observed_at"]) > evaluation_time:
            continue
        if _time(observation["expires_at"]) < evaluation_time:
            expired_observations.append(observation)
            continue
        active.append(observation)
    if not active:
        if expired_observations:
            strongest_expired = max(
                expired_observations, key=lambda item: _SOURCE_STRENGTH[item["source_class"]]
            )
            return "stale", strongest_expired["source_class"]
        return "declared", "publisher_declaration"
    active_states = {item["compatibility_state"] for item in active}
    if "revoked" in active_states:
        state, relevant_states = "revoked", {"revoked"}
    elif "observed-pass" in active_states and "observed-fail" in active_states:
        state, relevant_states = "conflicted", {"observed-pass", "observed-fail"}
    elif "observed-fail" in active_states:
        state, relevant_states = "observed-fail", {"observed-fail"}
    elif "observed-pass" in active_states:
        state, relevant_states = "observed-pass", {"observed-pass"}
    elif "conflicted" in active_states:
        state, relevant_states = "conflicted", {"conflicted"}
    elif "stale" in active_states:
        state, relevant_states = "stale", {"stale"}
    elif "unknown" in active_states:
        state, relevant_states = "unknown", {"unknown"}
    else:
        state, relevant_states = "declared", {"declared"}
    relevant = [item for item in active if item["compatibility_state"] in relevant_states]
    strongest = max(relevant, key=lambda item: _SOURCE_STRENGTH[item["source_class"]])["source_class"]
    return state, strongest


def _hard_gate(
    manifest: dict[str, Any], objective: dict[str, Any], environment: dict[str, Any], evidence_state: str
) -> list[str]:
    reasons: list[str] = []
    capabilities = {item["capability_id"] for item in manifest["capabilities"]}
    if not set(objective["required_capabilities"]).issubset(capabilities):
        reasons.append("missing_required_capability")
    if environment["environment_id"] not in manifest["environments"]:
        reasons.append("environment_incompatible")
    environment_constraints = manifest["environment_constraints"]
    if environment_constraints["os"] != environment["os"] or environment_constraints["arch"] != environment["arch"]:
        if "environment_incompatible" not in reasons:
            reasons.append("environment_incompatible")
    if any(environment["runtimes"].get(name) != version for name, version in environment_constraints["runtimes"].items()):
        reasons.append("runtime_incompatible")

    constraints = objective["constraints"]
    network = manifest["network"]
    if constraints["network"] == "deny" and network["mode"] != "deny":
        reasons.append("network_denied")
        if any(item.get("sensitivity") in {"private", "hard-private"} for item in objective["inputs"]):
            reasons.append("private_data_egress_denied")
    elif network["mode"] == "allowlist":
        allowed = set(constraints.get("network_allowlist", []))
        if not set(network["destinations"]).issubset(allowed):
            reasons.append("network_destination_denied")
        if environment["network"] == "deny":
            reasons.append("environment_network_denied")

    ceiling = _PERMISSION_ORDER[constraints["max_permission_class"]]
    if any(_PERMISSION_ORDER[permission] > ceiling for permission in manifest["permissions"]):
        reasons.append("permission_ceiling_exceeded")
    if manifest["license_class"] not in constraints["license_allow"]:
        reasons.append("license_denied")
    if manifest["secret_slots"] and constraints["secret_policy"] == "none":
        reasons.append("secret_policy_denied")
    estimate = manifest["resource_estimate"]
    if estimate["max_runtime_seconds"] > constraints["max_runtime_seconds"]:
        reasons.append("runtime_ceiling_exceeded")
    if estimate["max_cost_usd"] > constraints["max_cost_usd"]:
        reasons.append("cost_ceiling_exceeded")
    missing_prerequisites = sorted(set(manifest["prerequisites"]) - set(environment["available_prerequisites"]))
    if missing_prerequisites:
        reasons.append("missing_prerequisites")
    if any(item.get("blocking", False) for item in manifest["known_failures"]):
        reasons.append("blocking_known_failure")
    if evidence_state in _BLOCKING_STATES:
        reasons.append("blocking_evidence_state")
    return reasons


def _score(manifest: dict[str, Any], state: str, source_class: str, environment: dict[str, Any]) -> float:
    evidence = _EVIDENCE_RANK[state]
    if state == "observed-pass":
        evidence = min(evidence, _SOURCE_STRENGTH[source_class])
    installed_bonus = 0.02 if manifest["artifact_id"] in environment["installed_artifacts"] else 0.0
    prerequisite_discount = min(len(manifest["prerequisites"]) * 0.01, 0.10)
    permission_discount = max(0, len(manifest["permissions"]) - 1) * 0.01
    return round(max(0.0, evidence + installed_bonus - prerequisite_discount - permission_discount), 6)


def _selected_record(manifest: dict[str, Any], state: str, source_class: str, rank: float) -> dict[str, Any]:
    return {
        "artifact_id": manifest["artifact_id"],
        "version": manifest["version"],
        "digest": manifest["digest"],
        "evidence_state": state,
        "evidence_source_class": source_class,
        "rank": rank,
        "capabilities": [item["capability_id"] for item in manifest["capabilities"]],
    }


def _context_packet(plan: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    # Every copied publisher field has already passed a narrow structural allowlist.
    # It remains explicitly untrusted data and never becomes an authority instruction.
    return {
        "schema": "AgentContextPacket/v1",
        "plan_ref": plan["plan_id"],
        "artifact": {
            "artifact_id": manifest["artifact_id"],
            "version": manifest["version"],
            "digest": manifest["digest"],
            "purpose": "Produce the objective's declared output under the plan constraints.",
        },
        "invocation": deepcopy(manifest["invocation"]),
        "prerequisites": deepcopy(manifest["prerequisites"]),
        "permissions": deepcopy(manifest["permissions"]),
        "network": deepcopy(manifest["network"]),
        "secret_slots": deepcopy(manifest["secret_slots"]),
        "failure_behavior": "Stop on non-zero adapter status; do not broaden authority.",
        "verifier_ref": manifest["verifier_ref"],
        "content_trust": "untrusted-structured-data",
    }


def resolve_objective(
    objective: dict[str, Any], environment: dict[str, Any], registry: dict[str, Any]
) -> dict[str, Any]:
    objective = validate_objective(deepcopy(objective))
    environment = validate_environment(deepcopy(environment))
    registry = validate_fixture(deepcopy(registry))
    objective_digest = canonical_digest(objective)
    candidates: list[tuple[dict[str, Any], str, str, float]] = []
    eliminated: list[dict[str, Any]] = []
    for manifest in registry["manifests"]:
        state, source_class = _evidence_state(manifest, registry["observations"], environment)
        reasons = _hard_gate(manifest, objective, environment, state)
        if reasons:
            eliminated.append({
                "artifact_id": manifest["artifact_id"],
                "version": manifest["version"],
                "reason_codes": reasons,
                "evidence_state": state,
                "evidence_source_class": source_class,
            })
        else:
            candidates.append((manifest, state, source_class, _score(manifest, state, source_class, environment)))
    candidates.sort(key=lambda row: (-row[3], row[0]["artifact_id"], row[0]["version"]))
    eliminated.sort(key=lambda row: row["artifact_id"])
    base: dict[str, Any] = {
        "schema": "ResolutionPlan/v1",
        "plan_id": "plan_" + objective_digest.removeprefix("sha256:")[:20],
        "objective_digest": objective_digest,
        "registry_snapshot": registry["snapshot_id"],
        "policy_version": _POLICY_VERSION,
        "scoring_version": _SCORING_VERSION,
        "environment_ref": environment["environment_id"],
        "environment_snapshot": {
            "digest": canonical_digest(environment),
            "os": environment["os"],
            "arch": environment["arch"],
            "runtimes": deepcopy(environment["runtimes"]),
            "available_prerequisites": deepcopy(environment["available_prerequisites"]),
        },
        "constraints_snapshot": deepcopy(objective["constraints"]),
        "selected_artifacts": [],
        "alternatives": [],
        "eliminated_candidates": eliminated,
        "permission_union": [],
        "network_plan": {"mode": objective["constraints"]["network"], "destinations": []},
        "secret_slot_plan": [],
        "prerequisites": [],
        "verifier_dag": [],
        "rollback": {"mode": "not-applicable-read-only-resolution"},
        "assumptions": deepcopy(objective.get("assumptions", [])),
        "unresolved_unknowns": deepcopy(objective.get("unresolved_unknowns", [])),
        "reason_codes": [],
    }
    if not candidates:
        base["status"] = "no_admissible_plan"
        base["reason_codes"] = ["no_admissible_plan"]
        base["plan_digest"] = canonical_digest(base)
        return base
    selected, state, source_class, rank = candidates[0]
    base["status"] = "resolved"
    base["selected_artifacts"] = [_selected_record(selected, state, source_class, rank)]
    base["alternatives"] = [
        _selected_record(manifest, candidate_state, candidate_source_class, candidate_rank)
        for manifest, candidate_state, candidate_source_class, candidate_rank in candidates[1:]
    ]
    base["permission_union"] = sorted(selected["permissions"], key=lambda item: _PERMISSION_ORDER[item])
    base["network_plan"] = deepcopy(selected["network"])
    base["secret_slot_plan"] = deepcopy(selected["secret_slots"])
    base["prerequisites"] = deepcopy(selected["prerequisites"])
    base["verifier_dag"] = [{"step": "verify-output", "verifier_ref": selected["verifier_ref"]}]
    base["rollback"] = deepcopy(selected["rollback"])
    base["reason_codes"] = ["smallest_complete_admissible_pack", "highest_deterministic_rank"]
    base["agent_context_packet"] = _context_packet(base, selected)
    base["plan_digest"] = canonical_digest(base)
    return base


def _valid_plan_contract(plan: dict[str, Any]) -> bool:
    try:
        if plan.get("schema") != "ResolutionPlan/v1" or plan.get("status") != "resolved":
            return False
        if plan.get("policy_version") != _POLICY_VERSION or plan.get("scoring_version") != _SCORING_VERSION:
            return False
        if not isinstance(plan.get("plan_id"), str) or not isinstance(plan.get("objective_digest"), str):
            return False
        if not isinstance(plan.get("registry_snapshot"), str) or not plan["registry_snapshot"].startswith("sha256:"):
            return False
        if not isinstance(plan.get("selected_artifacts"), list) or len(plan["selected_artifacts"]) != 1:
            return False
        selected = plan["selected_artifacts"][0]
        if not isinstance(selected, dict) or not selected.get("artifact_id", "").startswith("artifact:"):
            return False
        if not isinstance(selected.get("digest"), str) or len(selected["digest"]) != 71:
            return False
        if not isinstance(plan.get("constraints_snapshot"), dict) or not isinstance(plan.get("environment_snapshot"), dict):
            return False
        if not isinstance(plan.get("permission_union"), list) or not all(
            permission in _PERMISSION_ORDER for permission in plan["permission_union"]
        ):
            return False
        if not isinstance(plan.get("network_plan"), dict) or set(plan["network_plan"]) != {"mode", "destinations"}:
            return False
        return True
    except (AttributeError, KeyError, TypeError):
        return False


def simulate_plan(
    plan: dict[str, Any],
    objective: dict[str, Any],
    environment: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ContractError("plan must be an object")
    expected_plan = resolve_objective(objective, environment, registry)
    try:
        replay_ok = canonical_digest(plan) == canonical_digest(expected_plan)
    except (TypeError, ValueError):
        replay_ok = False
    supplied_digest = plan.get("plan_digest")
    digest_body = deepcopy(plan)
    digest_body.pop("plan_digest", None)
    try:
        digest_ok = canonical_digest(digest_body) == supplied_digest
    except (TypeError, ValueError):
        digest_ok = False
    contract_ok = _valid_plan_contract(plan)
    constraints = plan.get("constraints_snapshot", {}) if contract_ok else {}
    network = plan.get("network_plan", {}) if contract_ok else {}
    network_ok = bool(contract_ok)
    if contract_ok and constraints.get("network") == "deny":
        network_ok = network.get("mode") == "deny" and network.get("destinations") == []
    elif contract_ok and network.get("mode") == "allowlist":
        network_ok = set(network.get("destinations", [])).issubset(set(constraints.get("network_allowlist", [])))
    permissions = plan.get("permission_union", []) if contract_ok else []
    permission_ok = bool(contract_ok and permissions)
    if permission_ok:
        max_permission = constraints.get("max_permission_class")
        ceiling = _PERMISSION_ORDER.get(max_permission, -1) if isinstance(max_permission, str) else -1
        permission_ok = all(_PERMISSION_ORDER[item] <= ceiling for item in permissions)
    environment = plan.get("environment_snapshot", {}) if contract_ok else {}
    dependency_ok = bool(
        contract_ok
        and set(plan.get("prerequisites", [])).issubset(set(environment.get("available_prerequisites", [])))
    )
    secret_ok = bool(contract_ok and not plan.get("secret_slot_plan"))
    verifier = plan.get("verifier_dag", []) if contract_ok else []
    verifier_ok = bool(
        contract_ok and len(verifier) == 1 and isinstance(verifier[0], dict)
        and verifier[0].get("step") == "verify-output"
        and str(verifier[0].get("verifier_ref", "")).startswith("verifier:")
    )
    checks = {
        "plan_contract": "pass" if contract_ok else "fail",
        "plan_digest": "pass" if digest_ok else "fail",
        "resolution_replay": "pass" if replay_ok else "fail",
        "dependency_closure": "pass" if dependency_ok else "fail",
        "network_policy": "pass" if network_ok else "fail",
        "permission_ceiling": "pass" if permission_ok else "fail",
        "secret_slots": "pass" if secret_ok else "fail",
        "verifier_available": "pass" if verifier_ok else "fail",
    }
    return {
        "schema": "PlanSimulation/v1",
        "status": "pass" if all(value == "pass" for value in checks.values()) else "fail",
        "artifact_invocation_count": 0,
        "checks": checks,
        "plan_digest": supplied_digest,
    }
