#!/usr/bin/env python3
"""
neo4j_v2_seed.py — Seed Agent, Domain, Skill nodes and relationships.

Sources data from existing canonical configs:
  - agents_config.py: AGENTS, AGENT_ROLES
  - kurultai_paths.py: AGENT_KEYWORDS
  - task_intake.py: DOMAIN_AGENT_COMPATIBILITY, SKILL_DOMAIN_MAP, DOMAIN_KEYWORDS

Idempotent — uses MERGE for all creates.

Usage:
    python3 neo4j_v2_seed.py           # Seed all nodes
    python3 neo4j_v2_seed.py --verify  # Verify seed data
"""

import os
import sys
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver, close_driver
from agents_config import AGENTS, AGENT_ROLES
from kurultai_paths import AGENT_KEYWORDS, DISPATCH_AGENTS
from task_intake import (
    DOMAIN_AGENT_COMPATIBILITY,
    SKILL_DOMAIN_MAP,
    DOMAIN_KEYWORDS,
)

logger = logging.getLogger(__name__)

# Agent dispatchability
DISPATCHABLE_AGENTS = set(DISPATCH_AGENTS)


def seed_agents(session, verbose=True):
    """Seed Agent nodes with roles and dispatchability."""
    count = 0
    for agent in AGENTS:
        role = AGENT_ROLES.get(agent, "Unknown")
        dispatchable = agent in DISPATCHABLE_AGENTS
        session.run("""
            MERGE (a:Agent {name: $name})
            SET a.role = $role,
                a.display_name = $name,
                a.dispatchable = $dispatchable,
                a.last_heartbeat = coalesce(a.last_heartbeat, datetime())
        """, name=agent, role=role, dispatchable=dispatchable)
        count += 1
        if verbose:
            d = "dispatchable" if dispatchable else "router-only"
            print(f"  [AGENT] {agent}: {role} ({d})")
    return count


def seed_domains(session, verbose=True):
    """Seed Domain nodes with keywords."""
    count = 0
    for domain, keywords in DOMAIN_KEYWORDS.items():
        # Store top keywords (Neo4j property, not the full list)
        top_keywords = keywords[:20]
        session.run("""
            MERGE (d:Domain {name: $name})
            SET d.keywords = $keywords
        """, name=domain, keywords=top_keywords)
        count += 1
        if verbose:
            print(f"  [DOMAIN] {domain} ({len(keywords)} keywords)")
    return count


def seed_skills(session, verbose=True):
    """Seed Skill nodes from SKILL_DOMAIN_MAP."""
    count = 0
    for skill, domain in SKILL_DOMAIN_MAP.items():
        session.run("""
            MERGE (s:Skill {name: $name})
            SET s.domain = $domain
        """, name=skill, domain=domain)

        # Link Skill -> Domain
        session.run("""
            MATCH (s:Skill {name: $skill})
            MATCH (d:Domain {name: $domain})
            MERGE (s)-[:BELONGS_TO]->(d)
        """, skill=skill, domain=domain)

        count += 1
        if verbose:
            print(f"  [SKILL] {skill} -> {domain}")
    return count


def seed_agent_domain_relationships(session, verbose=True):
    """Seed OWNS_DOMAIN and CAN_HANDLE relationships.

    First agent in DOMAIN_AGENT_COMPATIBILITY list OWNS the domain (weight 1.0).
    Subsequent agents CAN_HANDLE it (weight 0.5-0.7 based on position).
    """
    owns = 0
    handles = 0
    for domain, agents in DOMAIN_AGENT_COMPATIBILITY.items():
        for i, agent in enumerate(agents):
            if i == 0:
                # Primary owner
                session.run("""
                    MATCH (a:Agent {name: $agent})
                    MATCH (d:Domain {name: $domain})
                    MERGE (a)-[r:OWNS_DOMAIN]->(d)
                    SET r.weight = 1.0
                """, agent=agent, domain=domain)
                owns += 1
                if verbose:
                    print(f"  [OWNS] {agent} -> {domain} (1.0)")
            else:
                # Secondary handler — weight decreases with position
                weight = round(0.7 - (i - 1) * 0.1, 1)
                weight = max(weight, 0.3)  # Floor at 0.3
                session.run("""
                    MATCH (a:Agent {name: $agent})
                    MATCH (d:Domain {name: $domain})
                    MERGE (a)-[r:CAN_HANDLE]->(d)
                    SET r.weight = $weight
                """, agent=agent, domain=domain, weight=weight)
                handles += 1
                if verbose:
                    print(f"  [CAN_HANDLE] {agent} -> {domain} ({weight})")
    return owns, handles


def seed_agent_skill_relationships(session, verbose=True):
    """Seed PROFICIENT_IN relationships from AGENT_KEYWORDS + SKILL_DOMAIN_MAP.

    Maps agents to skills via their domain overlap.
    """
    count = 0
    # Build agent -> domains map from DOMAIN_AGENT_COMPATIBILITY
    agent_domains = {}
    for domain, agents in DOMAIN_AGENT_COMPATIBILITY.items():
        for agent in agents:
            agent_domains.setdefault(agent, set()).add(domain)

    for skill, skill_domain in SKILL_DOMAIN_MAP.items():
        for agent, domains in agent_domains.items():
            if skill_domain in domains:
                # Determine weight based on whether agent owns or can-handle
                compat_list = DOMAIN_AGENT_COMPATIBILITY.get(skill_domain, [])
                if agent == compat_list[0] if compat_list else False:
                    weight = 0.8  # Domain owner -> high skill affinity
                else:
                    weight = 0.4  # Can-handle -> moderate skill affinity
                session.run("""
                    MATCH (a:Agent {name: $agent})
                    MATCH (s:Skill {name: $skill})
                    MERGE (a)-[r:PROFICIENT_IN]->(s)
                    SET r.weight = $weight,
                        r.success_rate = coalesce(r.success_rate, 0.8),
                        r.use_count = coalesce(r.use_count, 0)
                """, agent=agent, skill=skill, weight=weight)
                count += 1
                if verbose:
                    print(f"  [PROFICIENT] {agent} -> {skill} ({weight})")
    return count


def seed_all(driver, verbose=True):
    """Run all seed operations."""
    results = {}
    with driver.session() as session:
        if verbose:
            print("\n--- Agents ---")
        results["agents"] = seed_agents(session, verbose)

        if verbose:
            print("\n--- Domains ---")
        results["domains"] = seed_domains(session, verbose)

        if verbose:
            print("\n--- Skills ---")
        results["skills"] = seed_skills(session, verbose)

        if verbose:
            print("\n--- Agent-Domain Relationships ---")
        owns, handles = seed_agent_domain_relationships(session, verbose)
        results["owns_domain"] = owns
        results["can_handle"] = handles

        if verbose:
            print("\n--- Agent-Skill Relationships ---")
        results["proficient_in"] = seed_agent_skill_relationships(session, verbose)

    return results


def verify_seed(driver, verbose=True):
    """Verify seed data exists in Neo4j."""
    ok = True
    with driver.session() as session:
        # Check agents
        result = session.run("MATCH (a:Agent) RETURN count(a) AS cnt")
        cnt = result.single()["cnt"]
        if verbose:
            print(f"  Agents: {cnt} (expected {len(AGENTS)})")
        if cnt < len(AGENTS):
            ok = False

        # Check domains
        result = session.run("MATCH (d:Domain) RETURN count(d) AS cnt")
        cnt = result.single()["cnt"]
        expected_domains = len(DOMAIN_KEYWORDS)
        if verbose:
            print(f"  Domains: {cnt} (expected {expected_domains})")
        if cnt < expected_domains:
            ok = False

        # Check skills
        result = session.run("MATCH (s:Skill) RETURN count(s) AS cnt")
        cnt = result.single()["cnt"]
        expected_skills = len(SKILL_DOMAIN_MAP)
        if verbose:
            print(f"  Skills: {cnt} (expected {expected_skills})")
        if cnt < expected_skills:
            ok = False

        # Check relationships
        for rel_type in ("OWNS_DOMAIN", "CAN_HANDLE", "PROFICIENT_IN", "BELONGS_TO"):
            result = session.run(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS cnt")
            cnt = result.single()["cnt"]
            if verbose:
                print(f"  {rel_type}: {cnt}")
            if cnt == 0:
                ok = False

    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Seed Neo4j v2 graph data")
    parser.add_argument("--verify", action="store_true", help="Verify seed data only")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    verbose = not args.quiet
    if verbose:
        print("=== Neo4j v2 Seed Data ===")

    driver = get_driver()
    try:
        if args.verify:
            ok = verify_seed(driver, verbose)
            if verbose:
                print(f"\n  {'All seed data present.' if ok else 'Missing seed data!'}")
            sys.exit(0 if ok else 1)
        else:
            results = seed_all(driver, verbose)
            if verbose:
                print(f"\n  Seeded: {results}")
    finally:
        close_driver()


if __name__ == "__main__":
    main()
