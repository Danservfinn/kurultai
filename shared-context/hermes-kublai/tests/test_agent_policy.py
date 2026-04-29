from __future__ import annotations

import importlib.util
from pathlib import Path


def load_policy():
    path = Path(__file__).resolve().parents[1] / "agent_policy.py"
    spec = importlib.util.spec_from_file_location("agent_policy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_explicit_kublai_mention_no_collab():
    p = load_policy()
    intent = {"explicit_owner": "kublai", "requires_collaboration": False, "domain": "routing"}
    assert p.select_owner(intent) == "kublai"


def test_explicit_hermes_mention_no_collab():
    p = load_policy()
    intent = {"explicit_owner": "hermes", "requires_collaboration": False, "domain": "routing"}
    assert p.select_owner(intent) == "hermes"


def test_system_health_domain_routes_to_hermes():
    p = load_policy()
    intent = {"explicit_owner": None, "requires_collaboration": False, "domain": "system_health"}
    assert p.select_owner(intent) == "hermes"


def test_agent_malfunction_domain_routes_to_hermes():
    p = load_policy()
    intent = {"explicit_owner": None, "requires_collaboration": False, "domain": "agent_malfunction"}
    assert p.select_owner(intent) == "hermes"


def test_routing_domain_routes_to_kublai():
    p = load_policy()
    intent = {"explicit_owner": None, "requires_collaboration": False, "domain": "routing"}
    assert p.select_owner(intent) == "kublai"


def test_protocol_proposal_routes_to_kublai():
    p = load_policy()
    intent = {"explicit_owner": None, "requires_collaboration": False, "domain": "protocol_proposal"}
    assert p.select_owner(intent) == "kublai"


def test_collab_with_routing_domain_routes_to_kublai():
    p = load_policy()
    intent = {"explicit_owner": None, "requires_collaboration": True, "domain": "routing"}
    assert p.select_owner(intent) == "kublai"


def test_collab_with_health_domain_routes_to_hermes():
    p = load_policy()
    intent = {"explicit_owner": None, "requires_collaboration": True, "domain": "system_health"}
    assert p.select_owner(intent) == "hermes"


def test_collab_generic_domain_defaults_to_kublai():
    p = load_policy()
    intent = {"requires_collaboration": True, "domain": ""}
    assert p.select_owner(intent) == "kublai"


def test_no_context_defaults_to_kublai():
    p = load_policy()
    assert p.select_owner({}) == "kublai"


def test_specialist_routing_required_goes_to_kublai():
    p = load_policy()
    intent = {"requires_specialist_routing": True, "domain": ""}
    assert p.select_owner(intent) == "kublai"


def test_explicit_mention_overrides_domain_for_hermes():
    p = load_policy()
    intent = {"explicit_owner": "hermes", "requires_collaboration": False, "domain": "routing"}
    assert p.select_owner(intent) == "hermes"


def test_explicit_mention_overrides_domain_for_kublai():
    p = load_policy()
    intent = {"explicit_owner": "kublai", "requires_collaboration": False, "domain": "system_health"}
    assert p.select_owner(intent) == "kublai"


def test_support_agents_for_kublai_owner_collab():
    p = load_policy()
    intent = {"requires_collaboration": True, "tier": "tier2"}
    agents = p.select_support_agents("kublai", intent)
    assert agents == ["hermes"]


def test_support_agents_for_hermes_owner_collab():
    p = load_policy()
    intent = {"requires_collaboration": True, "tier": "tier2"}
    agents = p.select_support_agents("hermes", intent)
    assert agents == ["kublai"]


def test_no_support_agents_for_tier1():
    p = load_policy()
    intent = {"requires_collaboration": False, "tier": "tier1"}
    agents = p.select_support_agents("kublai", intent)
    assert agents == []


def test_score_claim_explicit_owner_wins():
    p = load_policy()
    intent = {"explicit_owner": "kublai", "domain": "system_health"}
    kublai_score = p.score_claim("kublai", intent)
    hermes_score = p.score_claim("hermes", intent)
    assert kublai_score > hermes_score


def test_score_claim_domain_primary_beats_fallback():
    p = load_policy()
    intent = {"explicit_owner": None, "domain": "system_health"}
    hermes_score = p.score_claim("hermes", intent)
    kublai_score = p.score_claim("kublai", intent)
    assert hermes_score > kublai_score


def test_kublai_wins_tiebreak_on_collab_with_unknown_domain():
    p = load_policy()
    intent = {"requires_collaboration": True, "domain": ""}
    kublai_score = p.score_claim("kublai", intent)
    hermes_score = p.score_claim("hermes", intent)
    assert kublai_score > hermes_score


def test_runtime_debugging_routes_to_hermes():
    p = load_policy()
    intent = {"domain": "runtime_debugging"}
    assert p.select_owner(intent) == "hermes"


def test_collab_with_kublai_repair_routes_to_hermes():
    p = load_policy()
    intent = {"requires_collaboration": True, "domain": "kublai_repair"}
    assert p.select_owner(intent) == "hermes"
