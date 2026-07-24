from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, Iterable

from .canonical import canonical_digest
from .schema_runtime import (
    ContractError,
    check_shipped_schemas,
    load_json_file,
    loads_strict_json,
    validate_contract_schema,
)


_ARTIFACT_KEYS = {
    "schema", "artifact_id", "version", "digest", "description", "capabilities",
    "environments", "environment_constraints", "permissions", "network", "secret_slots",
    "license_class", "prerequisites", "resource_estimate", "invocation", "verifier_ref",
    "rollback", "known_failures", "source_refs", "publisher",
}
_OBJECTIVE_KEYS = {
    "schema", "objective_id", "outcome", "inputs", "required_capabilities", "constraints",
    "assumptions", "unresolved_unknowns",
}
_ENVIRONMENT_KEYS = {
    "schema", "environment_id", "os", "arch", "runtimes", "installed_artifacts", "network",
    "evaluation_time", "available_prerequisites",
}
_OBSERVATION_KEYS = {
    "schema", "observation_id", "subject", "claim", "source_class", "verifier_ref",
    "fixture_digest", "environment_ref", "result", "compatibility_state", "observed_at",
    "expires_at", "evidence_refs", "limitations", "supersedes",
}
_SECRET_KEY = re.compile(r"(?:password|passwd|secret|token|api[_-]?key|authorization|cookie)", re.I)
_SECRET_VALUE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+\S+|-----BEGIN [A-Z ]+PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,})"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_REF = re.compile(r"^[a-z][a-z0-9_-]*:[A-Za-z0-9._/@:+-]+$")
_SCHEMA_REF = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*/v[0-9]+$")
_CAPABILITY = re.compile(r"^[a-z0-9][a-z0-9._-]+$")
_SLOT = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_PREREQUISITE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._+-]+$")
_ARG = re.compile(r"^(?:--[a-z0-9][a-z0-9-]*|\{(?:input|output):[a-z0-9_-]+\})$")
_STATES = {"unknown", "declared", "observed-pass", "observed-fail", "stale", "conflicted", "revoked"}
_RESULTS = {"pass", "fail", "unknown"}
_SOURCE_CLASSES = {
    "publisher_declaration", "publisher_self_test", "registry_static_validation",
    "registry_sandbox_fixture", "independent_verifier", "tenant_observed_run",
    "receiver_attested_external_effect", "incident",
}
_SOURCE_AUTHORITY = {
    "publisher_declaration": 0.55,
    "publisher_self_test": 0.70,
    "registry_static_validation": 0.75,
    "registry_sandbox_fixture": 0.85,
    "independent_verifier": 0.95,
    "tenant_observed_run": 0.95,
    "receiver_attested_external_effect": 0.98,
    "incident": 1.0,
}
_PERMISSION_CLASSES = {"read-only", "local-read", "sandbox-local-write", "host-write", "external-effect"}


def _walk(value: Any, path: str = "$") -> Iterable[tuple[str, str | None, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield child_path, str(key), child
            yield from _walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            yield child_path, None, child
            yield from _walk(child, child_path)


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContractError(f"{label} must be a string array")
    return value


def _finite_number(value: Any, label: str) -> float | int:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ContractError(f"{label} must be a finite number")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ContractError(f"{label} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{label} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{label} must include a timezone")
    return parsed


def _reject_unknown(document: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise ContractError(f"unknown {label} fields: {', '.join(unknown)}")


def _reject_duplicates(items: list[str], label: str) -> None:
    if len(items) != len(set(items)):
        raise ContractError(f"duplicate {label} values are forbidden")


def reject_secret_values(value: Any) -> None:
    for path, key, child in _walk(value):
        if key and _SECRET_KEY.search(key) and key not in {"secret_policy", "secret_slots"}:
            if child not in (None, [], {}, "none"):
                raise ContractError(f"secret value fields are forbidden at {path}")
        if isinstance(child, str) and _SECRET_VALUE.search(child):
            raise ContractError(f"secret value detected at {path}")


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    manifest = _object(manifest, "manifest")
    validate_contract_schema(manifest)
    reject_secret_values(manifest)
    _reject_unknown(manifest, _ARTIFACT_KEYS, "manifest")
    if manifest["schema"] != "ArtifactManifest/v1":
        raise ContractError("unsupported manifest schema")
    if not isinstance(manifest["artifact_id"], str) or not manifest["artifact_id"].startswith("artifact:"):
        raise ContractError("artifact_id must use artifact: namespace")
    if not isinstance(manifest["version"], str) or not manifest["version"]:
        raise ContractError("version must be a non-empty string")
    if not isinstance(manifest["digest"], str) or not _SHA256.fullmatch(manifest["digest"]):
        raise ContractError("artifact digest must be an immutable lowercase sha256 digest")

    capabilities = manifest["capabilities"]
    if not isinstance(capabilities, list) or not capabilities:
        raise ContractError("at least one declared capability is required")
    capability_ids: list[str] = []
    for capability in capabilities:
        capability = _object(capability, "capability")
        if set(capability) != {"capability_id", "input_schema", "output_schema"}:
            raise ContractError("capability fields must be capability_id, input_schema, and output_schema")
        if not isinstance(capability["capability_id"], str) or not _CAPABILITY.fullmatch(capability["capability_id"]):
            raise ContractError("capability_id must be normalized")
        if not isinstance(capability["input_schema"], str) or not _SCHEMA_REF.fullmatch(capability["input_schema"]):
            raise ContractError("capability input_schema must be an exact schema ref")
        if not isinstance(capability["output_schema"], str) or not _SCHEMA_REF.fullmatch(capability["output_schema"]):
            raise ContractError("capability output_schema must be an exact schema ref")
        capability_ids.append(capability["capability_id"])
    _reject_duplicates(capability_ids, "capability_id")

    _string_list(manifest["environments"], "environments")
    constraints = _object(manifest["environment_constraints"], "environment_constraints")
    if set(constraints) != {"os", "arch", "runtimes"} or not all(
        isinstance(constraints.get(key), str) and constraints[key] for key in ("os", "arch")
    ) or not isinstance(constraints["runtimes"], dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in constraints["runtimes"].items()
    ):
        raise ContractError("environment_constraints must contain os, arch, and string runtimes")

    permissions = _string_list(manifest["permissions"], "permissions")
    if not permissions or not set(permissions).issubset(_PERMISSION_CLASSES):
        raise ContractError("permissions contain an unsupported permission class")
    network = _object(manifest["network"], "network")
    if set(network) != {"mode", "destinations"} or network["mode"] not in {"deny", "allowlist"}:
        raise ContractError("network must contain mode deny/allowlist and destinations")
    destinations = _string_list(network["destinations"], "network destinations")
    if network["mode"] == "deny" and destinations:
        raise ContractError("network deny cannot declare destinations")
    if any(not re.fullmatch(r"[A-Za-z0-9.-]+", destination) for destination in destinations):
        raise ContractError("network destinations must be normalized hostnames")
    _reject_duplicates(destinations, "network destination")

    slots = _string_list(manifest["secret_slots"], "secret_slots")
    for slot in slots:
        if _SECRET_VALUE.search(slot):
            raise ContractError("secret value detected in secret_slots")
        if not _SLOT.fullmatch(slot):
            raise ContractError("secret slot names must be uppercase identifiers")
    _reject_duplicates(slots, "secret slot")
    prerequisites = _string_list(manifest["prerequisites"], "prerequisites")
    if any(not _PREREQUISITE.fullmatch(item) for item in prerequisites):
        raise ContractError("prerequisites must be exact name@version refs")
    _reject_duplicates(prerequisites, "prerequisite")

    estimate = _object(manifest["resource_estimate"], "resource_estimate")
    for key in ("max_runtime_seconds", "max_cost_usd"):
        if _finite_number(estimate.get(key), key) < 0:
            raise ContractError(f"{key} must be non-negative")

    invocation = _object(manifest["invocation"], "invocation")
    if any(key in invocation for key in ("shell", "command", "script")):
        raise ContractError("shell command strings are forbidden in manifests")
    if set(invocation) != {"adapter", "argv_template"} or invocation.get("adapter") != "argv/v1":
        raise ContractError("invocation must contain only adapter=argv/v1 and argv_template")
    argv = _string_list(invocation["argv_template"], "argv_template")
    if not argv or any(not _ARG.fullmatch(arg) for arg in argv):
        raise ContractError("argv_template contains non-allowlisted structured arguments")

    if not isinstance(manifest["verifier_ref"], str) or not _REF.fullmatch(manifest["verifier_ref"]):
        raise ContractError("verifier_ref must be a normalized ref")
    rollback = _object(manifest["rollback"], "rollback")
    if set(rollback) != {"mode"} or not isinstance(rollback["mode"], str):
        raise ContractError("rollback must contain one mode string")
    failures = manifest["known_failures"]
    if not isinstance(failures, list) or any(not isinstance(item, dict) for item in failures):
        raise ContractError("known_failures must be an object array")
    failure_ids: list[str] = []
    for failure in failures:
        if set(failure) != {"failure_id", "scope", "blocking"}:
            raise ContractError("known failure fields must be failure_id, scope, and blocking")
        if not isinstance(failure["failure_id"], str) or not _REF.fullmatch(failure["failure_id"]):
            raise ContractError("known failure id must be a normalized ref")
        if not isinstance(failure["scope"], str) or not _REF.fullmatch(failure["scope"]):
            raise ContractError("known failure scope must be a normalized ref")
        if not isinstance(failure["blocking"], bool):
            raise ContractError("known failure blocking must be boolean")
        failure_ids.append(failure["failure_id"])
    _reject_duplicates(failure_ids, "known failure")
    source_refs = _string_list(manifest.get("source_refs", []), "source_refs")
    if any(not _REF.fullmatch(ref) for ref in source_refs):
        raise ContractError("source ref must be a normalized opaque ref")
    return manifest


def validate_objective(objective: dict[str, Any]) -> dict[str, Any]:
    objective = _object(objective, "objective")
    validate_contract_schema(objective)
    reject_secret_values(objective)
    _reject_unknown(objective, _OBJECTIVE_KEYS, "objective")
    if objective["schema"] not in {"ObjectiveSpec/v1", "ObjectiveSpec/v2"}:
        raise ContractError("unsupported objective schema")
    if not isinstance(objective["objective_id"], str) or not objective["objective_id"]:
        raise ContractError("objective_id must be a non-empty string")
    outcome = _object(objective["outcome"], "outcome")
    if set(outcome) != {"description", "output_schema", "done_when"}:
        raise ContractError("outcome fields are invalid")
    if not isinstance(outcome["description"], str) or not outcome["description"]:
        raise ContractError("outcome description must be a non-empty string")
    if not isinstance(outcome["output_schema"], str) or not _SCHEMA_REF.fullmatch(outcome["output_schema"]):
        raise ContractError("outcome output_schema must be an exact schema ref")
    _string_list(outcome["done_when"], "done_when")
    inputs = objective["inputs"]
    if not isinstance(inputs, list) or not inputs or any(not isinstance(item, dict) for item in inputs):
        raise ContractError("inputs must be a non-empty object array")
    expected_input_keys = {"ref", "media_type", "sensitivity"}
    if objective["schema"] == "ObjectiveSpec/v2":
        expected_input_keys = expected_input_keys | {"schema_ref"}
    for item in inputs:
        if set(item) != expected_input_keys:
            raise ContractError("objective input fields are invalid for schema version")
        if not isinstance(item["ref"], str) or not _REF.fullmatch(item["ref"]):
            raise ContractError("objective input ref must be normalized")
        if not isinstance(item["media_type"], str) or not re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", item["media_type"]):
            raise ContractError("objective input media_type is invalid")
        if not isinstance(item["sensitivity"], str) or item["sensitivity"] not in {"public", "private", "hard-private"}:
            raise ContractError("objective input sensitivity is invalid")
        if objective["schema"] == "ObjectiveSpec/v2" and not _SCHEMA_REF.fullmatch(item["schema_ref"]):
            raise ContractError("objective input schema_ref must be an exact schema ref")
    required_capabilities = _string_list(objective["required_capabilities"], "required_capabilities")
    if not required_capabilities:
        raise ContractError("required_capabilities cannot be empty")
    if any(not _CAPABILITY.fullmatch(item) for item in required_capabilities):
        raise ContractError("required_capabilities must be normalized capability IDs")
    _reject_duplicates(required_capabilities, "required capability")
    constraints = _object(objective["constraints"], "constraints")
    expected = {"network", "network_allowlist", "secret_policy", "license_allow", "max_runtime_seconds", "max_cost_usd", "max_permission_class"}
    if set(constraints) != expected:
        raise ContractError("objective constraints fields are invalid")
    if constraints["network"] not in {"deny", "allowlist"} or constraints["secret_policy"] not in {"none", "brokered"}:
        raise ContractError("objective network or secret policy is invalid")
    network_allowlist = _string_list(constraints["network_allowlist"], "network_allowlist")
    if constraints["network"] == "deny" and network_allowlist:
        raise ContractError("network deny cannot include an allowlist")
    if any(not re.fullmatch(r"[A-Za-z0-9.-]+", destination) for destination in network_allowlist):
        raise ContractError("network_allowlist must contain normalized hostnames")
    _reject_duplicates(network_allowlist, "network allowlist")
    if constraints["max_permission_class"] not in _PERMISSION_CLASSES:
        raise ContractError("max_permission_class is invalid")
    _string_list(constraints["license_allow"], "license_allow")
    for key in ("max_runtime_seconds", "max_cost_usd"):
        if _finite_number(constraints[key], key) < 0:
            raise ContractError(f"{key} must be non-negative")
    return objective


def validate_environment(environment: dict[str, Any]) -> dict[str, Any]:
    environment = _object(environment, "environment")
    validate_contract_schema(environment)
    reject_secret_values(environment)
    _reject_unknown(environment, _ENVIRONMENT_KEYS, "environment")
    if environment["schema"] != "EnvironmentProfile/v1":
        raise ContractError("unsupported environment schema")
    if not isinstance(environment["environment_id"], str) or not environment["environment_id"]:
        raise ContractError("environment_id is required")
    if not all(isinstance(environment[key], str) and environment[key] for key in ("os", "arch")):
        raise ContractError("environment os and arch are required strings")
    if not isinstance(environment["runtimes"], dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in environment["runtimes"].items()
    ):
        raise ContractError("environment runtimes must be a string map")
    _string_list(environment["installed_artifacts"], "installed_artifacts")
    prerequisites = _string_list(environment["available_prerequisites"], "available_prerequisites")
    if any(not _PREREQUISITE.fullmatch(item) for item in prerequisites):
        raise ContractError("available_prerequisites must be exact refs")
    _reject_duplicates(prerequisites, "available prerequisite")
    if environment["network"] not in {"deny", "allowlist"}:
        raise ContractError("environment network is invalid")
    _timestamp(environment["evaluation_time"], "evaluation_time")
    return environment


def validate_observation(observation: dict[str, Any]) -> dict[str, Any]:
    observation = _object(observation, "observation")
    validate_contract_schema(observation)
    reject_secret_values(observation)
    _reject_unknown(observation, _OBSERVATION_KEYS, "observation")
    if observation["schema"] != "EvidenceObservation/v1":
        raise ContractError("unsupported observation schema")
    if not isinstance(observation["observation_id"], str) or not re.fullmatch(r"obs_[A-Za-z0-9_-]+", observation["observation_id"]):
        raise ContractError("observation_id must use the obs_ namespace")
    claim = _object(observation["claim"], "observation claim")
    if set(claim) != {"capability_id", "type"}:
        raise ContractError("observation claim fields must be capability_id and type")
    if not isinstance(claim["capability_id"], str) or not _CAPABILITY.fullmatch(claim["capability_id"]):
        raise ContractError("observation claim capability_id is invalid")
    if not isinstance(claim["type"], str) or claim["type"] not in {"fixture_outcome", "runtime_observation", "incident"}:
        raise ContractError("observation claim type is invalid")
    subject = _object(observation["subject"], "observation subject")
    if set(subject) != {"artifact_id", "version", "digest"} or not _SHA256.fullmatch(str(subject.get("digest", ""))):
        raise ContractError("observation subject must bind artifact, version, and sha256 digest")
    if observation["source_class"] not in _SOURCE_CLASSES:
        raise ContractError("unsupported observation source_class")
    state = observation["compatibility_state"]
    result = observation["result"]
    if state not in _STATES or result not in _RESULTS:
        raise ContractError("unsupported observation state or result")
    if (state == "observed-pass" and result != "pass") or (state in {"observed-fail", "revoked"} and result != "fail"):
        raise ContractError("observation result and compatibility state are inconsistent")
    if not _REF.fullmatch(str(observation["verifier_ref"])) or not _SHA256.fullmatch(str(observation["fixture_digest"])):
        raise ContractError("observation verifier or fixture digest is invalid")
    if not isinstance(observation["environment_ref"], str) or not observation["environment_ref"]:
        raise ContractError("observation environment_ref is required")
    observed_at = _timestamp(observation["observed_at"], "observed_at")
    expires_at = _timestamp(observation["expires_at"], "expires_at")
    if expires_at < observed_at:
        raise ContractError("observation expires_at cannot precede observed_at")
    evidence_refs = _string_list(observation["evidence_refs"], "evidence_refs")
    if any(not _REF.fullmatch(ref) for ref in evidence_refs):
        raise ContractError("evidence_refs must be normalized refs")
    _reject_duplicates(evidence_refs, "evidence ref")
    _string_list(observation["limitations"], "limitations")
    supersedes = observation["supersedes"]
    if supersedes is not None and (not isinstance(supersedes, str) or not re.fullmatch(r"obs_[A-Za-z0-9_-]+", supersedes)):
        raise ContractError("supersedes must be null or an observation ID")
    return observation


def validate_observation_set(document: dict[str, Any]) -> dict[str, Any]:
    document = _object(document, "observation set")
    validate_contract_schema(document)
    observations = document.get("observations")
    if not isinstance(observations, list):
        raise ContractError("observations must be an array")
    for observation in observations:
        validate_observation(observation)
    observation_ids = [item["observation_id"] for item in observations]
    _reject_duplicates(observation_ids, "observation_id")
    return document


def _same_observation_scope(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left["subject"] == right["subject"]
        and left["claim"] == right["claim"]
        and left["environment_ref"] == right["environment_ref"]
    )


def validate_fixture(registry: dict[str, Any]) -> dict[str, Any]:
    registry = _object(registry, "registry")
    validate_contract_schema(registry)
    if set(registry) != {"schema", "manifests", "observations", "snapshot_id"} or registry["schema"] != "FixtureRegistry/v1":
        raise ContractError("fixture registry contract is invalid")
    manifests = registry.get("manifests")
    observations = registry.get("observations")
    if not isinstance(manifests, list) or not isinstance(observations, list):
        raise ContractError("registry manifests and observations must be arrays")
    if len(manifests) > 128 or len(observations) > 512:
        raise ContractError("registry snapshot exceeds bounded fixture limits")
    for manifest in manifests:
        validate_manifest(manifest)
    for observation in observations:
        validate_observation(observation)
    ids = [item["artifact_id"] for item in manifests]
    _reject_duplicates(ids, "artifact_id in registry snapshot")
    observation_ids = [item["observation_id"] for item in observations]
    _reject_duplicates(observation_ids, "observation_id in registry snapshot")
    by_observation_id = {item["observation_id"]: item for item in observations}
    for observation in observations:
        supersedes = observation.get("supersedes")
        if supersedes is None:
            continue
        previous = by_observation_id.get(supersedes)
        if previous is None:
            raise ContractError("supersedes must reference an observation in the registry snapshot")
        if not _same_observation_scope(observation, previous):
            raise ContractError("supersedes must preserve observation subject, claim, and environment scope")
        if _timestamp(observation["observed_at"], "observed_at") < _timestamp(previous["observed_at"], "observed_at"):
            raise ContractError("supersedes must be chronological")
        if _SOURCE_AUTHORITY[observation["source_class"]] < _SOURCE_AUTHORITY[previous["source_class"]]:
            raise ContractError("supersedes cannot reduce evidence source authority")
    for observation_id in by_observation_id:
        seen: set[str] = set()
        current_id: str | None = observation_id
        while current_id is not None:
            if current_id in seen:
                raise ContractError("supersedes graph must be acyclic and cannot self-reference")
            seen.add(current_id)
            current_id = by_observation_id[current_id].get("supersedes")
    expected = canonical_digest({"manifests": manifests, "observations": observations})
    if registry.get("snapshot_id") != expected:
        raise ContractError("registry snapshot digest mismatch")
    return registry
