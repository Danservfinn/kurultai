#!/usr/bin/env python3
"""Compile a fail-closed Hulagu gate-policy admission decision."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

COMPILER_IDENTITY = "service:hulagu-policy-compiler:v1"

def canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def parse_time(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be UTC Z")
    parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.utcoffset() != dt.timedelta(0):
        raise ValueError("timestamp must be UTC")
    return parsed

def strict_json(path: Path) -> dict[str, Any]:
    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in rows:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing regular JSON file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError("top-level JSON must be an object")
    return value

def evaluate(policy: dict[str, Any], candidate: dict[str, Any], review: dict[str, Any], request: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
    reasons: list[str] = []
    deny = reasons.append
    if policy.get("policy_id") != "hulagu.autonomous-authority.v1" or policy.get("default_decision") != "DENY":
        deny("policy identity/default mismatch")
    if request.get("policy_id") != policy.get("policy_id"):
        deny("request policy mismatch")
    if request.get("policy_sha256") != canonical_sha(policy):
        deny("policy digest mismatch")
    if review.get("schema_version") != "hulagu-independent-policy-review-v1" or review.get("decision") != "APPROVE":
        deny("independent review is not APPROVE")
    if review.get("candidate_manifest_sha256") != canonical_sha(candidate):
        deny("independent review candidate digest mismatch")
    if request.get("candidate_manifest_sha256") != canonical_sha(candidate):
        deny("request candidate digest mismatch")
    if request.get("independent_review_sha256") != canonical_sha(review):
        deny("request review digest mismatch")
    if review.get("producer_identity") == review.get("reviewer_identity") or request.get("producer_identity") == request.get("independent_verifier_identity"):
        deny("producer and independent verifier must differ")
    if request.get("policy_compiler_identity") != COMPILER_IDENTITY:
        deny("policy compiler identity mismatch")
    if request.get("base_commit") != candidate.get("base_commit") or request.get("base_tree") != candidate.get("base_tree"):
        deny("base commit/tree mismatch")
    if request.get("prior_closure_sha256") != candidate.get("prior_closure_sha256"):
        deny("prior closure mismatch")
    if request.get("allowed_write_set_sha256") != candidate.get("allowed_write_set_sha256"):
        deny("allowed write set mismatch")
    if request.get("command_packet_sha256") != candidate.get("command_packet_sha256"):
        deny("command packet mismatch")
    if request.get("payload_manifest_sha256") != candidate.get("payload_manifest_sha256"):
        deny("payload manifest mismatch")
    required = set(policy.get("universal_predicates", []))
    results = request.get("predicate_results")
    if not isinstance(results, dict) or set(results) != required or not all(value is True for value in results.values()):
        deny("universal predicate closure is not exactly true")
    review_results = review.get("predicate_results")
    if not isinstance(review_results, dict) or not review_results or not all(value is True for value in review_results.values()):
        deny("independent review predicates incomplete")
    if review.get("unresolved_blocker_or_high") not in ([], None):
        deny("independent review has unresolved blocker/high")
    requested = request.get("requested_surfaces")
    forbidden = set(policy.get("permanent_forbidden_surfaces", []))
    known = set(request.get("known_effect_surfaces", [])) | forbidden
    if not isinstance(requested, list) or any(not isinstance(item, str) for item in requested):
        deny("requested surfaces malformed")
    else:
        if forbidden.intersection(requested):
            deny("permanent forbidden surface requested")
        if set(requested) - known:
            deny("unknown effect surface requested")
    if request.get("external_effect_class") not in {"none", "preauthorized"}:
        deny("external effect is not preauthorized")
    if request.get("credentials_isolated") is not True or request.get("credentials_absent_from_logs") is not True:
        deny("credential isolation/redaction predicate false")
    try:
        issued = parse_time(request.get("issued_at"))
        expires = parse_time(request.get("expires_at"))
        review_issued = parse_time(review.get("issued_at"))
        review_expires = parse_time(review.get("expires_at"))
        if issued > now or expires <= now or review_issued > now or review_expires <= now:
            deny("stale, future, or expired evidence")
        if expires - issued > dt.timedelta(hours=4) or review_expires - review_issued > dt.timedelta(hours=24):
            deny("freshness window too broad")
    except (TypeError, ValueError):
        deny("timestamp validation failed")
    nonce = request.get("nonce")
    if not isinstance(nonce, str) or len(nonce) < 32 or nonce in set(request.get("used_nonces", [])):
        deny("nonce missing or replayed")
    gate_id = request.get("gate_id")
    if gate_id not in policy.get("gates", {}):
        deny("unknown gate")
    if gate_id in {"G10", "G11"}:
        consent = request.get("pilot_consent")
        if not isinstance(consent, dict):
            deny("pilot consent missing")
        else:
            if consent.get("gate_id") != gate_id or consent.get("auto_invited") is not False:
                deny("pilot consent gate/auto-invite invalid")
            if not consent.get("communication_permission_ref"):
                deny("pilot communication permission missing")
            try:
                if parse_time(consent.get("expires_at")) <= now:
                    deny("pilot consent expired")
            except (TypeError, ValueError):
                deny("pilot consent timestamp invalid")
    return {
        "schema_version": "hulagu-gate-policy-admission-v1",
        "decision_id": request.get("decision_id", "hulagu.invalid.decision"),
        "gate_id": gate_id,
        "policy_id": policy.get("policy_id"),
        "policy_compiler_identity": COMPILER_IDENTITY,
        "decision": "DENY" if reasons else "ADMIT",
        "reasons": sorted(set(reasons)),
        "predicate_results": results if isinstance(results, dict) else {},
        "requested_surfaces": requested if isinstance(requested, list) else [],
        "issued_at": request.get("issued_at"),
        "expires_at": request.get("expires_at"),
        "nonce": nonce,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--independent-review", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        verdict = evaluate(strict_json(args.policy), strict_json(args.candidate_manifest), strict_json(args.independent_review), strict_json(args.request), dt.datetime.now(dt.timezone.utc))
    except Exception as exc:
        verdict = {"schema_version": "hulagu-gate-policy-admission-v1", "decision": "DENY", "reasons": [f"input validation failed: {type(exc).__name__}"]}
    payload = json.dumps(verdict, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)
    return 0 if verdict.get("decision") == "ADMIT" else 1

if __name__ == "__main__":
    raise SystemExit(main())
