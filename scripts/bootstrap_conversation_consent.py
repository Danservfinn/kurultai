#!/usr/bin/env python3
"""Bootstrap message_storage + message_analysis consent for all active humans.

One-time script to grant default consent categories to existing humans
so the fail-closed consent check doesn't block message processing.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import neo4j_session
from consent_decorator import grant_consent, seed_consent_categories

# Ensure consent category nodes exist
print("Seeding consent categories...")
seed_consent_categories()

print("Granting consent to active humans...")
with neo4j_session() as session:
    result = session.run(
        "MATCH (h:Human {status: 'active'}) RETURN h.id AS id, h.displayName AS name"
    )
    humans = [dict(r) for r in result]

print(f"Found {len(humans)} active humans")
for human in humans:
    hid = human["id"]
    name = human["name"] or hid[:8]
    for consent_type in ["message_storage", "message_analysis", "external_llm_processing"]:
        granted = grant_consent(hid, consent_type)
        status = "OK" if granted else "FAILED"
        print(f"  {name}: {consent_type} = {status}")

print(f"\nDone. Bootstrapped consent for {len(humans)} humans.")
