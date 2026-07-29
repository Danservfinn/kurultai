"""Deterministic, inspectable candidate scoring shared by host and sandbox."""

from __future__ import annotations

from typing import cast

from hulagu.search.schemas import Candidate, RankedCandidate, RankingJobInput

_WEIGHTS = {
    "role_match": 30.0,
    "required_skill_match": 25.0,
    "location_match": 15.0,
    "seniority_match": 10.0,
    "freshness_signal": 10.0,
    "tenant_feedback_match": 10.0,
}


def _contains(text: str, terms: tuple[str, ...]) -> float:
    if not terms:
        return 1.0
    lowered = text.lower()
    return sum(term.lower() in lowered for term in terms) / len(terms)


def rank_candidates(
    candidates: tuple[Candidate, ...],
    *,
    role_terms: tuple[str, ...],
    location_terms: tuple[str, ...],
    required_terms: tuple[str, ...],
    excluded_terms: tuple[str, ...],
    max_ranked: int,
) -> tuple[RankedCandidate, ...]:
    if not 1 <= max_ranked <= 20:
        raise ValueError("invalid ranked candidate limit")
    seen: set[str] = set()
    ranked: list[RankedCandidate] = []
    for candidate in candidates:
        if candidate.normalized_url_hash in seen:
            raise ValueError("duplicate URL")
        seen.add(candidate.normalized_url_hash)
        evidence = f"{candidate.title} {candidate.location} {candidate.snippet}"
        excluded = tuple(term for term in excluded_terms if term.lower() in evidence.lower())
        required_matched = tuple(term for term in required_terms if term.lower() in evidence.lower())
        missing = tuple(term for term in required_terms if term not in required_matched)
        components = {
            "role_match": round(_WEIGHTS["role_match"] * _contains(candidate.title, role_terms), 4),
            "required_skill_match": round(_WEIGHTS["required_skill_match"] * _contains(evidence, required_terms), 4),
            "location_match": round(_WEIGHTS["location_match"] * _contains(candidate.location, location_terms), 4),
            "seniority_match": _WEIGHTS["seniority_match"] if "senior" in candidate.title.lower() else 0.0,
            "freshness_signal": _WEIGHTS["freshness_signal"],
            "tenant_feedback_match": 0.0,
            "hard_exclusion_penalties": -100.0 if excluded else 0.0,
        }
        total = round(sum(components.values()), 4)
        explanation = "Deterministic score: " + ", ".join(f"{name}={value:g}" for name, value in components.items())
        ranked.append(RankedCandidate(candidate, components, total, required_matched + excluded, missing, explanation))
    ranked.sort(key=lambda item: (-item.total_score, item.candidate.normalized_url_hash))
    return tuple(ranked[:max_ranked])


def rank_job_input(bundle: RankingJobInput) -> dict[str, object]:
    """Render the only accepted deterministic RankedCandidates/v1 representation."""
    ranked = rank_candidates(
        bundle.candidates,
        role_terms=bundle.role_terms,
        location_terms=bundle.location_terms,
        required_terms=bundle.required_terms,
        excluded_terms=bundle.excluded_terms,
        max_ranked=bundle.max_ranked,
    )
    return {
        "schema_version": "RankedCandidates/v1",
        "ranked": [
            {
                "canonical_url": item.candidate.canonical_url,
                "components": item.components,
                "total_score": item.total_score,
                "matched_constraints": list(item.matched_constraints),
                "missing_constraints": list(item.missing_constraints),
                "explanation": item.explanation,
            }
            for item in ranked
        ],
    }


def rank_input_payload(payload: object) -> dict[str, object]:
    """Validate RankerInput/v1 JSON and execute the host's domain ranker."""
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version", "run_id", "profile_version", "candidates", "intent", "max_ranked"
    }:
        raise ValueError("invalid RankerInput/v1")
    candidates_raw = payload.get("candidates")
    intent = payload.get("intent")
    run_id = payload.get("run_id")
    profile_version = payload.get("profile_version")
    max_ranked = payload.get("max_ranked")
    if (
        payload.get("schema_version") != "RankerInput/v1"
        or not isinstance(run_id, str)
        or not run_id
        or isinstance(profile_version, bool)
        or not isinstance(profile_version, int)
        or not isinstance(candidates_raw, list)
        or not isinstance(intent, dict)
        or set(intent) != {"role_terms", "location_terms", "required_terms", "excluded_terms"}
        or isinstance(max_ranked, bool)
        or not isinstance(max_ranked, int)
    ):
        raise ValueError("invalid RankerInput/v1")

    terms: dict[str, tuple[str, ...]] = {}
    for name in ("role_terms", "location_terms", "required_terms", "excluded_terms"):
        raw = intent.get(name)
        if not isinstance(raw, list) or any(not isinstance(term, str) or not term for term in raw):
            raise ValueError("invalid RankerInput/v1")
        terms[name] = tuple(cast(list[str], raw))

    candidates: list[Candidate] = []
    expected_keys = {
        "canonical_url", "title", "company", "location", "remote_signal", "source_provider",
        "retrieved_at", "snippet", "evidence_grade", "required_terms", "normalized_url_hash",
    }
    for raw_candidate in candidates_raw:
        if not isinstance(raw_candidate, dict) or set(raw_candidate) != expected_keys:
            raise ValueError("invalid RankerInput/v1")
        required = raw_candidate.get("required_terms")
        if not isinstance(required, list) or any(not isinstance(term, str) for term in required):
            raise ValueError("invalid RankerInput/v1")
        try:
            candidate = Candidate(
                canonical_url=cast(str, raw_candidate["canonical_url"]),
                title=cast(str, raw_candidate["title"]),
                company=cast(str, raw_candidate["company"]),
                location=cast(str, raw_candidate["location"]),
                remote_signal=cast(str, raw_candidate["remote_signal"]),
                source_provider=cast(str, raw_candidate["source_provider"]),
                retrieved_at=cast(str, raw_candidate["retrieved_at"]),
                snippet=cast(str, raw_candidate["snippet"]),
                evidence_grade=cast(str, raw_candidate["evidence_grade"]),
                required_terms=tuple(cast(list[str], required)),
            )
        except (TypeError, ValueError):
            raise ValueError("invalid RankerInput/v1") from None
        if raw_candidate.get("normalized_url_hash") != candidate.normalized_url_hash:
            raise ValueError("invalid RankerInput/v1")
        candidates.append(candidate)

    return rank_job_input(
        RankingJobInput(
            run_id=run_id,
            profile_version=profile_version,
            candidates=tuple(candidates),
            role_terms=terms["role_terms"],
            location_terms=terms["location_terms"],
            required_terms=terms["required_terms"],
            excluded_terms=terms["excluded_terms"],
            max_ranked=max_ranked,
        )
    )
