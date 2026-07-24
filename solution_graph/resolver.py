from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import datetime
from typing import Any

from .canonical import canonical_digest
from .validation import (
    ContractError,
    validate_contract_schema,
    validate_environment,
    validate_fixture,
    validate_objective,
)

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
_POLICY_VERSION = "solution-graph-policy/v0.2"
_SCORING_VERSION = "deterministic-evidence-fit/v0.2"
_MAX_ARTIFACTS = 3
_MAX_EDGES = 8
_MAX_EXPANSIONS = 1024


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _artifact_key(manifest: dict[str, Any]) -> tuple[str, str, str]:
    return manifest["artifact_id"], manifest["version"], manifest["digest"]


def _plan_id(plan_schema: str, objective_digest: str, environment_digest: str, registry_snapshot: str) -> str:
    identity = {
        "schema": plan_schema,
        "objective_digest": objective_digest,
        "environment_digest": environment_digest,
        "registry_snapshot": registry_snapshot,
        "policy_version": _POLICY_VERSION,
        "scoring_version": _SCORING_VERSION,
    }
    return "plan_" + canonical_digest(identity).removeprefix("sha256:")[:20]


def _evidence_state(
    manifest: dict[str, Any],
    capability_id: str,
    observations: list[dict[str, Any]],
    environment: dict[str, Any],
) -> dict[str, Any]:
    exact = [
        obs for obs in observations
        if obs["subject"]["artifact_id"] == manifest["artifact_id"]
        and obs["subject"]["version"] == manifest["version"]
        and obs["subject"]["digest"] == manifest["digest"]
        and obs["environment_ref"] == environment["environment_id"]
        and obs["claim"]["capability_id"] == capability_id
    ]
    if not exact:
        return {
            "state": "declared",
            "source_class": "publisher_declaration",
            "observation_ids": [],
            "evidence_refs": [],
        }

    evaluation_time = _time(environment["evaluation_time"])
    observed = [item for item in exact if _time(item["observed_at"]) <= evaluation_time]
    superseded_ids = {item["supersedes"] for item in observed if item["supersedes"] is not None}
    scoped = [item for item in exact if item["observation_id"] not in superseded_ids]

    active: list[dict[str, Any]] = []
    expired_observations: list[dict[str, Any]] = []
    for observation in scoped:
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
            return _evidence_result("stale", strongest_expired["source_class"], expired_observations)
        return {
            "state": "declared",
            "source_class": "publisher_declaration",
            "observation_ids": [],
            "evidence_refs": [],
        }

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
    return _evidence_result(state, strongest, relevant)


def _evidence_result(state: str, source_class: str, observations: list[dict[str, Any]]) -> dict[str, Any]:
    evidence_refs = sorted({ref for item in observations for ref in item["evidence_refs"]})
    observation_ids = sorted({item["observation_id"] for item in observations})
    return {
        "state": state,
        "source_class": source_class,
        "observation_ids": observation_ids,
        "evidence_refs": evidence_refs,
    }


def _weakest_evidence(evidences: list[dict[str, Any]]) -> dict[str, Any]:
    if not evidences:
        return {
            "state": "declared",
            "source_class": "publisher_declaration",
            "observation_ids": [],
            "evidence_refs": [],
        }
    return min(
        evidences,
        key=lambda item: (
            _EVIDENCE_RANK[item["state"]],
            _SOURCE_STRENGTH.get(item["source_class"], 0.0),
            item["source_class"],
        ),
    )


def _known_failure_blocks(
    manifest: dict[str, Any],
    environment: dict[str, Any],
    capability_ids: set[str] | None = None,
) -> bool:
    scoped = {
        environment["environment_id"],
        manifest["artifact_id"],
        manifest["digest"],
        f"artifact-version:{manifest['artifact_id']}@{manifest['version']}",
    }
    if capability_ids:
        scoped.update(f"capability:{item}" for item in capability_ids)
    return any(item.get("blocking", False) and item.get("scope") in scoped for item in manifest["known_failures"])


def _hard_gate(
    manifest: dict[str, Any],
    objective: dict[str, Any],
    environment: dict[str, Any],
    *,
    require_complete: bool,
    evidence_state: str | None = None,
    selected_capability_ids: set[str] | None = None,
    resource_individual: bool = True,
) -> list[str]:
    reasons: list[str] = []
    capabilities = {item["capability_id"] for item in manifest["capabilities"]}
    if require_complete and not set(objective["required_capabilities"]).issubset(capabilities):
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
    if resource_individual and estimate["max_runtime_seconds"] > constraints["max_runtime_seconds"]:
        reasons.append("runtime_ceiling_exceeded")
    if resource_individual and estimate["max_cost_usd"] > constraints["max_cost_usd"]:
        reasons.append("cost_ceiling_exceeded")
    missing_prerequisites = sorted(set(manifest["prerequisites"]) - set(environment["available_prerequisites"]))
    if missing_prerequisites:
        reasons.append("missing_prerequisites")
    if _known_failure_blocks(manifest, environment, selected_capability_ids):
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


def _selected_record(
    manifest: dict[str, Any],
    state: str,
    source_class: str,
    rank: float,
    capability_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_id": manifest["artifact_id"],
        "version": manifest["version"],
        "digest": manifest["digest"],
        "evidence_state": state,
        "evidence_source_class": source_class,
        "rank": rank,
        "capabilities": capability_ids or [item["capability_id"] for item in manifest["capabilities"]],
    }


def _context_packet_v1(plan: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
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


def _base_plan(
    schema: str,
    objective: dict[str, Any],
    environment: dict[str, Any],
    registry: dict[str, Any],
    eliminated: list[dict[str, Any]],
) -> dict[str, Any]:
    objective_digest = canonical_digest(objective)
    environment_digest = canonical_digest(environment)
    return {
        "schema": schema,
        "plan_id": _plan_id(schema, objective_digest, environment_digest, registry["snapshot_id"]),
        "objective_digest": objective_digest,
        "registry_snapshot": registry["snapshot_id"],
        "policy_version": _POLICY_VERSION,
        "scoring_version": _SCORING_VERSION,
        "environment_ref": environment["environment_id"],
        "environment_snapshot": {
            "digest": environment_digest,
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


def _required_evidence(
    manifest: dict[str, Any],
    objective: dict[str, Any],
    observations: list[dict[str, Any]],
    environment: dict[str, Any],
) -> dict[str, Any]:
    evidences = [
        _evidence_state(manifest, capability_id, observations, environment)
        for capability_id in objective["required_capabilities"]
        if capability_id in {item["capability_id"] for item in manifest["capabilities"]}
    ]
    return _weakest_evidence(evidences)


def _resolve_v1(objective: dict[str, Any], environment: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    candidates: list[tuple[dict[str, Any], dict[str, Any], float]] = []
    eliminated: list[dict[str, Any]] = []
    for manifest in registry["manifests"]:
        evidence = _required_evidence(manifest, objective, registry["observations"], environment)
        reasons = _hard_gate(
            manifest,
            objective,
            environment,
            require_complete=True,
            evidence_state=evidence["state"],
            selected_capability_ids=set(objective["required_capabilities"]),
        )
        if reasons:
            eliminated.append({
                "artifact_id": manifest["artifact_id"],
                "version": manifest["version"],
                "reason_codes": reasons,
                "evidence_state": evidence["state"],
                "evidence_source_class": evidence["source_class"],
            })
        else:
            candidates.append((
                manifest,
                evidence,
                _score(manifest, evidence["state"], evidence["source_class"], environment),
            ))
    candidates.sort(key=lambda row: (-row[2], row[0]["artifact_id"], row[0]["version"], row[0]["digest"]))
    eliminated.sort(key=lambda row: (row["artifact_id"], row["version"]))
    base = _base_plan("ResolutionPlan/v1", objective, environment, registry, eliminated)
    if not candidates:
        base["status"] = "no_admissible_plan"
        base["reason_codes"] = ["no_admissible_plan"]
        base["plan_digest"] = canonical_digest(base)
        validate_contract_schema(base)
        return base

    selected, evidence, rank = candidates[0]
    base["status"] = "resolved"
    base["selected_artifacts"] = [
        _selected_record(selected, evidence["state"], evidence["source_class"], rank)
    ]
    base["alternatives"] = [
        _selected_record(manifest, candidate_evidence["state"], candidate_evidence["source_class"], candidate_rank)
        for manifest, candidate_evidence, candidate_rank in candidates[1:]
    ]
    base["permission_union"] = sorted(selected["permissions"], key=lambda item: _PERMISSION_ORDER[item])
    base["network_plan"] = deepcopy(selected["network"])
    base["secret_slot_plan"] = deepcopy(selected["secret_slots"])
    base["prerequisites"] = deepcopy(selected["prerequisites"])
    base["verifier_dag"] = [{"step": "verify-output", "verifier_ref": selected["verifier_ref"]}]
    base["rollback"] = deepcopy(selected["rollback"])
    base["reason_codes"] = ["single_complete_artifact", "highest_deterministic_rank"]
    base["agent_context_packet"] = _context_packet_v1(base, selected)
    validate_contract_schema(base["agent_context_packet"])
    base["plan_digest"] = canonical_digest(base)
    validate_contract_schema(base)
    return base


def _edge_rows(
    manifests: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    environment: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for manifest in manifests:
        for capability in manifest["capabilities"]:
            evidence = _evidence_state(manifest, capability["capability_id"], observations, environment)
            rows.append({
                "manifest": manifest,
                "capability_id": capability["capability_id"],
                "input_schema": capability["input_schema"],
                "output_schema": capability["output_schema"],
                "evidence": evidence,
                "identity": (
                    manifest["artifact_id"],
                    manifest["version"],
                    manifest["digest"],
                    capability["capability_id"],
                    capability["input_schema"],
                    capability["output_schema"],
                ),
            })
    rows.sort(key=lambda item: item["identity"])
    return rows


def _network_plan(manifests: list[dict[str, Any]]) -> dict[str, Any]:
    destinations = sorted({destination for manifest in manifests for destination in manifest["network"]["destinations"]})
    return {"mode": "allowlist" if destinations else "deny", "destinations": destinations}


def _pack_reasons(steps: list[dict[str, Any]], objective: dict[str, Any], environment: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    required = set(objective["required_capabilities"])
    capability_ids = [step["capability_id"] for step in steps]
    if len(capability_ids) != len(set(capability_ids)):
        reasons.append("duplicate_capability_id")
    if not required.issubset(set(capability_ids)):
        reasons.append("missing_required_capability")
    if steps:
        input_refs = {item["schema_ref"] for item in objective["inputs"]}
        if steps[0]["input_schema"] not in input_refs:
            reasons.append("schema_start_mismatch")
        for left, right in zip(steps, steps[1:]):
            if left["output_schema"] != right["input_schema"]:
                reasons.append("schema_edge_mismatch")
        if steps[-1]["output_schema"] != objective["outcome"]["output_schema"]:
            reasons.append("terminal_schema_mismatch")
        if steps[-1]["manifest"]["verifier_ref"] not in set(objective["outcome"]["done_when"]):
            reasons.append("terminal_verifier_unavailable")
    if len(steps) > _MAX_EDGES:
        reasons.append("edge_limit_exceeded")
    unique_manifests = _unique_manifests(steps)
    if len(unique_manifests) > _MAX_ARTIFACTS:
        reasons.append("artifact_limit_exceeded")
    constraints = objective["constraints"]
    if sum(manifest["resource_estimate"]["max_runtime_seconds"] for manifest in unique_manifests) > constraints["max_runtime_seconds"]:
        reasons.append("runtime_ceiling_exceeded")
    if sum(manifest["resource_estimate"]["max_cost_usd"] for manifest in unique_manifests) > constraints["max_cost_usd"]:
        reasons.append("cost_ceiling_exceeded")
    permissions = {permission for manifest in unique_manifests for permission in manifest["permissions"]}
    ceiling = _PERMISSION_ORDER[constraints["max_permission_class"]]
    if any(_PERMISSION_ORDER[item] > ceiling for item in permissions):
        reasons.append("permission_ceiling_exceeded")
    destinations = {destination for manifest in unique_manifests for destination in manifest["network"]["destinations"]}
    if constraints["network"] == "deny" and destinations:
        reasons.append("network_denied")
    elif not destinations.issubset(set(constraints["network_allowlist"])):
        reasons.append("network_destination_denied")
    if destinations and environment["network"] == "deny":
        reasons.append("environment_network_denied")
    if destinations and any(item.get("sensitivity") in {"private", "hard-private"} for item in objective["inputs"]):
        reasons.append("private_data_egress_denied")
    secret_slots = {slot for manifest in unique_manifests for slot in manifest["secret_slots"]}
    if secret_slots and constraints["secret_policy"] == "none":
        reasons.append("secret_policy_denied")
    missing_prerequisites = {
        item for manifest in unique_manifests for item in manifest["prerequisites"]
    } - set(environment["available_prerequisites"])
    if missing_prerequisites:
        reasons.append("missing_prerequisites")
    if any(manifest["license_class"] not in constraints["license_allow"] for manifest in unique_manifests):
        reasons.append("license_denied")
    for manifest in unique_manifests:
        manifest_capabilities = {step["capability_id"] for step in steps if step["manifest"] is manifest}
        if _known_failure_blocks(manifest, environment, manifest_capabilities):
            reasons.append("blocking_known_failure")
            break
    if any(step["evidence"]["state"] in _BLOCKING_STATES for step in steps):
        reasons.append("blocking_evidence_state")
    return sorted(set(reasons))


def _unique_manifests(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for step in steps:
        manifest = step["manifest"]
        key = _artifact_key(manifest)
        if key not in seen:
            unique.append(manifest)
            seen.add(key)
    return unique


def _path_sort_key(steps: list[dict[str, Any]], environment: dict[str, Any]) -> tuple[Any, ...]:
    unique_manifests = _unique_manifests(steps)
    permission_breadth = max(
        (_PERMISSION_ORDER[permission] for manifest in unique_manifests for permission in manifest["permissions"]),
        default=0,
    )
    network_count = len({destination for manifest in unique_manifests for destination in manifest["network"]["destinations"]})
    prerequisite_count = len({item for manifest in unique_manifests for item in manifest["prerequisites"]})
    evidence_score = min(
        (_score(step["manifest"], step["evidence"]["state"], step["evidence"]["source_class"], environment) for step in steps),
        default=0.0,
    )
    lexical = tuple(step["identity"] for step in steps)
    return (
        len(unique_manifests),
        len(steps),
        permission_breadth,
        network_count,
        prerequisite_count,
        -evidence_score,
        lexical,
    )


def _compose_bounded(
    objective: dict[str, Any],
    manifests: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    environment: dict[str, Any],
) -> tuple[str, list[dict[str, Any]] | None]:
    edges = _edge_rows(manifests, observations, environment)
    input_schemas: list[str] = []
    for item in objective["inputs"]:
        if item["schema_ref"] not in input_schemas:
            input_schemas.append(item["schema_ref"])
    frontier: deque[dict[str, Any]] = deque(
        {
            "current_schema": schema_ref,
            "steps": [],
            "used_edges": set(),
            "used_capabilities": set(),
            "visited_schemas": {schema_ref},
        }
        for schema_ref in input_schemas
    )
    candidates: list[list[dict[str, Any]]] = []
    expansion_count = 0
    bounded_frontier = False

    while frontier:
        state = frontier.popleft()
        steps = state["steps"]
        if steps and not _pack_reasons(steps, objective, environment):
            candidates.append(steps)
            continue
        if len(steps) >= _MAX_EDGES:
            if any(edge["input_schema"] == state["current_schema"] for edge in edges):
                bounded_frontier = True
            continue
        next_edges = [edge for edge in edges if edge["input_schema"] == state["current_schema"]]
        for edge in next_edges:
            if expansion_count >= _MAX_EXPANSIONS:
                return "search_exhausted", None
            expansion_count += 1
            if edge["identity"] in state["used_edges"]:
                continue
            if edge["capability_id"] in state["used_capabilities"]:
                continue
            if edge["output_schema"] in state["visited_schemas"]:
                continue
            next_steps = steps + [edge]
            if len(_unique_manifests(next_steps)) > _MAX_ARTIFACTS:
                bounded_frontier = True
                continue
            frontier.append({
                "current_schema": edge["output_schema"],
                "steps": next_steps,
                "used_edges": state["used_edges"] | {edge["identity"]},
                "used_capabilities": state["used_capabilities"] | {edge["capability_id"]},
                "visited_schemas": state["visited_schemas"] | {edge["output_schema"]},
            })

    if candidates:
        candidates.sort(key=lambda steps: _path_sort_key(steps, environment))
        return "resolved", candidates[0]
    if bounded_frontier:
        return "search_exhausted", None
    return "no_admissible_plan", None


def _composition_path_records(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        manifest = step["manifest"]
        step_id = f"step_{index:04d}"
        records.append({
            "step_id": step_id,
            "artifact_id": manifest["artifact_id"],
            "version": manifest["version"],
            "digest": manifest["digest"],
            "capability_ids": [step["capability_id"]],
            "input_schema": step["input_schema"],
            "output_schema": step["output_schema"],
            "depends_on": [] if index == 1 else [f"step_{index - 1:04d}"],
            "verifier_ref": manifest["verifier_ref"],
            "evidence_state": step["evidence"]["state"],
            "evidence_source_class": step["evidence"]["source_class"],
            "evidence_refs": deepcopy(step["evidence"]["evidence_refs"]),
            "observation_ids": deepcopy(step["evidence"]["observation_ids"]),
        })
    return records


def _context_packet_v2(plan: dict[str, Any]) -> dict[str, Any]:
    steps = [
        {
            "step_id": step["step_id"],
            "artifact_id": step["artifact_id"],
            "version": step["version"],
            "digest": step["digest"],
            "capability_ids": deepcopy(step["capability_ids"]),
            "input_schema": step["input_schema"],
            "output_schema": step["output_schema"],
            "depends_on": deepcopy(step["depends_on"]),
            "verifier_ref": step["verifier_ref"],
        }
        for step in plan["composition_path"]
    ]
    return {
        "schema": "AgentContextPacket/v2",
        "plan_ref": plan["plan_id"],
        "steps": steps,
        "invocations": [
            {"step_id": step["step_id"], "adapter": "resolution-only/v1", "argv_template": []}
            for step in steps
        ],
        "failure_behavior": "Review only; no artifact invocation or authority grant is permitted.",
        "content_trust": "untrusted-structured-data",
        "authority": "none",
    }


def _selected_records_from_steps(steps: list[dict[str, Any]], environment: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for manifest in _unique_manifests(steps):
        manifest_steps = [step for step in steps if step["manifest"] is manifest]
        evidence = _weakest_evidence([step["evidence"] for step in manifest_steps])
        capability_ids = [step["capability_id"] for step in manifest_steps]
        rank = min(
            _score(manifest, step["evidence"]["state"], step["evidence"]["source_class"], environment)
            for step in manifest_steps
        )
        records.append(_selected_record(manifest, evidence["state"], evidence["source_class"], rank, capability_ids))
    return records


def _alternative_record(manifest: dict[str, Any], observations: list[dict[str, Any]], environment: dict[str, Any]) -> dict[str, Any]:
    evidences = [
        _evidence_state(manifest, capability["capability_id"], observations, environment)
        for capability in manifest["capabilities"]
    ]
    evidence = _weakest_evidence(evidences)
    return _selected_record(
        manifest,
        evidence["state"],
        evidence["source_class"],
        _score(manifest, evidence["state"], evidence["source_class"], environment),
    )


def _resolve_v2(objective: dict[str, Any], environment: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    fragments: list[dict[str, Any]] = []
    eliminated: list[dict[str, Any]] = []
    for manifest in registry["manifests"]:
        evidence = _alternative_record(manifest, registry["observations"], environment)
        reasons = _hard_gate(manifest, objective, environment, require_complete=False, resource_individual=False)
        if reasons:
            eliminated.append({
                "artifact_id": manifest["artifact_id"],
                "version": manifest["version"],
                "reason_codes": reasons,
                "evidence_state": evidence["evidence_state"],
                "evidence_source_class": evidence["evidence_source_class"],
            })
        else:
            fragments.append(manifest)
    eliminated.sort(key=lambda row: (row["artifact_id"], row["version"]))
    base = _base_plan("ResolutionPlan/v2", objective, environment, registry, eliminated)
    base["composition_path"] = []

    status, steps = _compose_bounded(objective, fragments, registry["observations"], environment)
    if status != "resolved" or steps is None:
        base["status"] = status
        base["reason_codes"] = (
            ["search_exhausted", "incomplete_frontier"]
            if status == "search_exhausted"
            else ["no_admissible_plan", "typed_composition_unavailable"]
        )
        base["plan_digest"] = canonical_digest(base)
        validate_contract_schema(base)
        return base

    selected_manifests = _unique_manifests(steps)
    selected_keys = {_artifact_key(manifest) for manifest in selected_manifests}
    base["status"] = "resolved"
    base["composition_path"] = _composition_path_records(steps)
    base["selected_artifacts"] = _selected_records_from_steps(steps, environment)
    base["alternatives"] = [
        _alternative_record(manifest, registry["observations"], environment)
        for manifest in fragments
        if _artifact_key(manifest) not in selected_keys
    ]
    base["permission_union"] = sorted(
        {permission for manifest in selected_manifests for permission in manifest["permissions"]},
        key=lambda item: _PERMISSION_ORDER[item],
    )
    base["network_plan"] = _network_plan(selected_manifests)
    base["secret_slot_plan"] = sorted({slot for manifest in selected_manifests for slot in manifest["secret_slots"]})
    base["prerequisites"] = sorted({item for manifest in selected_manifests for item in manifest["prerequisites"]})
    base["verifier_dag"] = [
        {
            "step": "verify-output",
            "step_id": step["step_id"],
            "artifact_id": step["artifact_id"],
            "verifier_ref": step["verifier_ref"],
        }
        for step in base["composition_path"]
    ]
    base["rollback"] = {"mode": "not-applicable-read-only-composition"}
    base["reason_codes"] = ["bounded_typed_composition", "smallest_complete_admissible_path"]
    base["agent_context_packet"] = _context_packet_v2(base)
    validate_contract_schema(base["agent_context_packet"])
    base["plan_digest"] = canonical_digest(base)
    validate_contract_schema(base)
    return base


def resolve_objective(
    objective: dict[str, Any], environment: dict[str, Any], registry: dict[str, Any]
) -> dict[str, Any]:
    objective = validate_objective(deepcopy(objective))
    environment = validate_environment(deepcopy(environment))
    registry = validate_fixture(deepcopy(registry))
    if objective["schema"] == "ObjectiveSpec/v1":
        return _resolve_v1(objective, environment, registry)
    return _resolve_v2(objective, environment, registry)


def _valid_plan_contract(plan: dict[str, Any]) -> bool:
    try:
        validate_contract_schema(plan)
        if plan.get("schema") not in {"ResolutionPlan/v1", "ResolutionPlan/v2"} or plan.get("status") != "resolved":
            return False
        if plan.get("policy_version") != _POLICY_VERSION or plan.get("scoring_version") != _SCORING_VERSION:
            return False
        selected_artifacts = plan.get("selected_artifacts")
        if not isinstance(selected_artifacts, list):
            return False
        if plan["schema"] == "ResolutionPlan/v1" and len(selected_artifacts) != 1:
            return False
        if plan["schema"] == "ResolutionPlan/v2" and not 1 <= len(selected_artifacts) <= _MAX_ARTIFACTS:
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
    except (AttributeError, ContractError, KeyError, TypeError):
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
    environment_snapshot = plan.get("environment_snapshot", {}) if contract_ok else {}
    dependency_ok = bool(
        contract_ok
        and set(plan.get("prerequisites", [])).issubset(set(environment_snapshot.get("available_prerequisites", [])))
    )
    secret_ok = bool(
        contract_ok
        and (constraints.get("secret_policy") == "brokered" or not plan.get("secret_slot_plan"))
    )
    verifier = plan.get("verifier_dag", []) if contract_ok else []
    if contract_ok and plan.get("schema") == "ResolutionPlan/v2":
        verifier_ok = len(verifier) == len(plan.get("composition_path", [])) and all(
            isinstance(item, dict)
            and item.get("step") == "verify-output"
            and str(item.get("verifier_ref", "")).startswith("verifier:")
            for item in verifier
        )
    else:
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
    simulation = {
        "schema": "PlanSimulation/v1",
        "status": "pass" if all(value == "pass" for value in checks.values()) else "fail",
        "artifact_invocation_count": 0,
        "checks": checks,
        "plan_digest": supplied_digest if isinstance(supplied_digest, str) else None,
    }
    validate_contract_schema(simulation)
    return simulation
