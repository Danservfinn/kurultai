#!/usr/bin/env python3
"""
Entity Resolution Engine — Merge candidate detection and confidence-based merge policy.

Detects potential duplicate Human nodes via:
1. Name similarity (Jaro-Winkler on displayName / NAME_VARIANT identifiers)
2. Phone match (shared SIGNAL_PHONE identifier)
3. Shared KNOWN_THROUGH connections

Merge policy:
- >= 0.9 confidence → auto-merge
- 0.5–0.9 → flag for human review
- < 0.5 → keep separate

Usage:
    from entity_resolution import EntityResolver
    resolver = EntityResolver()
    candidates = resolver.find_merge_candidates("uuid-of-human")
    resolver.auto_merge_if_confident(candidates)
"""

import logging
import uuid as uuid_mod
from typing import Optional, List, Dict, Any, Tuple
from difflib import SequenceMatcher

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver

logger = logging.getLogger(__name__)


def _jaro_winkler(s1: str, s2: str) -> float:
    """Approximate Jaro-Winkler similarity using SequenceMatcher."""
    if not s1 or not s2:
        return 0.0
    s1 = s1.lower().strip()
    s2 = s2.lower().strip()
    if s1 == s2:
        return 1.0
    ratio = SequenceMatcher(None, s1, s2).ratio()
    # Boost for common prefix (Winkler modification)
    prefix_len = 0
    for c1, c2 in zip(s1[:4], s2[:4]):
        if c1 == c2:
            prefix_len += 1
        else:
            break
    return ratio + (prefix_len * 0.1 * (1 - ratio))


class MergeCandidate:
    """A potential merge between two Human nodes."""

    def __init__(
        self,
        human_a_id: str,
        human_b_id: str,
        confidence: float,
        signals: List[Dict[str, Any]],
    ):
        self.human_a_id = human_a_id
        self.human_b_id = human_b_id
        self.confidence = min(1.0, max(0.0, confidence))
        self.signals = signals

    @property
    def should_auto_merge(self) -> bool:
        return self.confidence >= 0.9

    @property
    def needs_review(self) -> bool:
        return 0.5 <= self.confidence < 0.9

    @property
    def keep_separate(self) -> bool:
        return self.confidence < 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "human_a_id": self.human_a_id,
            "human_b_id": self.human_b_id,
            "confidence": self.confidence,
            "action": (
                "auto_merge" if self.should_auto_merge
                else "review" if self.needs_review
                else "separate"
            ),
            "signals": self.signals,
        }


class EntityResolver:
    """Detects and resolves duplicate Human nodes."""

    def __init__(self):
        self.driver = get_driver()

    def close(self):
        if self.driver:
            close_driver()
            self.driver = None

    def find_merge_candidates(
        self, human_id: str, threshold: float = 0.3
    ) -> List[MergeCandidate]:
        """Find potential merge candidates for a Human.

        Checks:
        1. Exact phone match (different Human same phone) → 0.95
        2. Name similarity (Jaro-Winkler > 0.85) → scaled score
        3. Shared KNOWN_THROUGH connections → 0.1 per shared connection

        Args:
            human_id: UUID of the Human to check
            threshold: Minimum confidence to return

        Returns:
            List of MergeCandidate objects, sorted by confidence desc
        """
        candidates: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

        # 1. Phone match — same phone on different Humans
        self._check_phone_match(human_id, candidates)

        # 2. Name similarity
        self._check_name_similarity(human_id, candidates)

        # 3. Shared connections
        self._check_shared_connections(human_id, candidates)

        # Build MergeCandidate objects
        results = []
        for other_id, (score, signals) in candidates.items():
            if score >= threshold:
                results.append(MergeCandidate(human_id, other_id, score, signals))

        results.sort(key=lambda c: c.confidence, reverse=True)
        return results

    def _check_phone_match(
        self, human_id: str, candidates: Dict[str, Tuple[float, list]]
    ) -> None:
        """Find other Humans with matching phone identifiers."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})-[:IDENTIFIED_BY]->(i:Identifier {type: 'SIGNAL_PHONE'})
                WITH i.value AS phone
                MATCH (other:Human)-[:IDENTIFIED_BY]->(oi:Identifier {type: 'SIGNAL_PHONE', value: phone})
                WHERE other.id <> $human_id
                RETURN other.id AS otherId, phone
                """,
                human_id=human_id,
            )
            for record in result:
                other_id = record["otherId"]
                signal = {"type": "phone_match", "value": record["phone"], "weight": 0.95}
                if other_id in candidates:
                    score, signals = candidates[other_id]
                    signals.append(signal)
                    candidates[other_id] = (min(1.0, score + 0.95), signals)
                else:
                    candidates[other_id] = (0.95, [signal])

    def _check_name_similarity(
        self, human_id: str, candidates: Dict[str, Tuple[float, list]]
    ) -> None:
        """Find other Humans with similar names."""
        with self.driver.session() as session:
            # Get this human's names
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})
                OPTIONAL MATCH (h)-[:IDENTIFIED_BY]->(nv:Identifier {type: 'NAME_VARIANT'})
                RETURN h.displayName AS name,
                       collect(nv.value) AS variants
                """,
                human_id=human_id,
            )
            record = result.single()
            if not record:
                return

            my_names = [record["name"]] + (record["variants"] or [])
            my_names = [n for n in my_names if n]

            if not my_names:
                return

            # Get all other humans' names
            result = session.run(
                """
                MATCH (other:Human)
                WHERE other.id <> $human_id AND other.status = 'active'
                OPTIONAL MATCH (other)-[:IDENTIFIED_BY]->(nv:Identifier {type: 'NAME_VARIANT'})
                RETURN other.id AS otherId,
                       other.displayName AS name,
                       collect(nv.value) AS variants
                """,
                human_id=human_id,
            )

            for other_record in result:
                other_id = other_record["otherId"]
                other_names = [other_record["name"]] + (other_record["variants"] or [])
                other_names = [n for n in other_names if n]

                # Find best name match
                best_score = 0.0
                best_pair = ("", "")
                for my_name in my_names:
                    for other_name in other_names:
                        score = _jaro_winkler(my_name, other_name)
                        if score > best_score:
                            best_score = score
                            best_pair = (my_name, other_name)

                if best_score > 0.85:
                    weight = best_score * 0.6  # Name alone caps at 0.6
                    signal = {
                        "type": "name_similarity",
                        "names": list(best_pair),
                        "similarity": round(best_score, 3),
                        "weight": round(weight, 3),
                    }
                    if other_id in candidates:
                        score, signals = candidates[other_id]
                        signals.append(signal)
                        candidates[other_id] = (min(1.0, score + weight), signals)
                    else:
                        candidates[other_id] = (weight, [signal])

    def _check_shared_connections(
        self, human_id: str, candidates: Dict[str, Tuple[float, list]]
    ) -> None:
        """Find other Humans sharing KNOWN_THROUGH connections."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (h:Human {id: $human_id})-[:KNOWN_THROUGH]->(shared:Human)<-[:KNOWN_THROUGH]-(other:Human)
                WHERE other.id <> $human_id
                RETURN other.id AS otherId,
                       count(shared) AS sharedCount,
                       collect(shared.displayName) AS sharedNames
                """,
                human_id=human_id,
            )
            for record in result:
                other_id = record["otherId"]
                shared_count = record["sharedCount"]
                weight = min(0.3, shared_count * 0.1)
                signal = {
                    "type": "shared_connections",
                    "count": shared_count,
                    "names": record["sharedNames"][:5],
                    "weight": round(weight, 3),
                }
                if other_id in candidates:
                    score, signals = candidates[other_id]
                    signals.append(signal)
                    candidates[other_id] = (min(1.0, score + weight), signals)
                else:
                    candidates[other_id] = (weight, [signal])

    def merge_humans(
        self, keep_id: str, absorb_id: str, reason: str = "auto"
    ) -> Dict[str, Any]:
        """Merge absorb_id into keep_id.

        Transfers all Identifiers, relationships, and content edges
        from absorb_id to keep_id. Sets absorb_id status to 'merged'.

        Args:
            keep_id: UUID of the Human to keep
            absorb_id: UUID of the Human to absorb
            reason: Why the merge is happening

        Returns:
            Dict with merge results
        """
        with self.driver.session() as session:
            result = session.run(
                """
                // Transfer identifiers
                MATCH (absorb:Human {id: $absorb_id})-[r:IDENTIFIED_BY]->(i:Identifier)
                MATCH (keep:Human {id: $keep_id})
                MERGE (keep)-[:IDENTIFIED_BY]->(i)
                DELETE r
                WITH count(*) AS ids_transferred, keep, absorb

                // Transfer KNOWN_THROUGH (outgoing)
                OPTIONAL MATCH (absorb)-[r:KNOWN_THROUGH]->(other:Human)
                WHERE other.id <> $keep_id
                FOREACH (_ IN CASE WHEN r IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (keep)-[:KNOWN_THROUGH]->(other)
                )
                WITH ids_transferred, keep, absorb, count(r) AS kt_out
                OPTIONAL MATCH (absorb)-[r:KNOWN_THROUGH]->(other:Human)
                DELETE r
                WITH ids_transferred, kt_out, keep, absorb

                // Transfer KNOWN_THROUGH (incoming)
                OPTIONAL MATCH (other:Human)-[r:KNOWN_THROUGH]->(absorb)
                WHERE other.id <> $keep_id
                FOREACH (_ IN CASE WHEN r IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (other)-[:KNOWN_THROUGH]->(keep)
                )
                WITH ids_transferred, kt_out, keep, absorb, count(r) AS kt_in
                OPTIONAL MATCH (other:Human)-[r:KNOWN_THROUGH]->(absorb)
                DELETE r
                WITH ids_transferred, kt_out + kt_in AS connections_transferred, keep, absorb

                // Transfer Messages
                OPTIONAL MATCH (absorb)<-[r:SENT]-(m:Message)
                SET m.humanId = $keep_id
                DELETE r
                WITH ids_transferred, connections_transferred, keep, absorb, count(m) AS msgs_transferred
                OPTIONAL MATCH (m:Message {humanId: $keep_id})
                WHERE NOT exists((m)-[:SENT]->())
                MERGE (m)-[:SENT]->(keep)
                WITH ids_transferred, connections_transferred, msgs_transferred, keep, absorb

                // Transfer consent
                OPTIONAL MATCH (absorb)-[r:HAS_CONSENT]->(c:ConsentCategory)
                WHERE r.revokedAt IS NULL
                MERGE (keep)-[:HAS_CONSENT]->(c)
                DELETE r
                WITH ids_transferred, connections_transferred, msgs_transferred, keep, absorb

                // Mark absorbed human
                SET absorb.status = 'merged',
                    absorb.mergedInto = $keep_id,
                    absorb.mergedAt = datetime(),
                    absorb.mergeReason = $reason

                RETURN ids_transferred, connections_transferred, msgs_transferred
                """,
                keep_id=keep_id,
                absorb_id=absorb_id,
                reason=reason,
            )
            record = result.single()
            return {
                "keep_id": keep_id,
                "absorbed_id": absorb_id,
                "ids_transferred": record["ids_transferred"] if record else 0,
                "connections_transferred": record["connections_transferred"] if record else 0,
                "msgs_transferred": record["msgs_transferred"] if record else 0,
                "reason": reason,
            }

    def auto_merge_if_confident(
        self, candidates: List[MergeCandidate]
    ) -> List[Dict[str, Any]]:
        """Auto-merge candidates with confidence >= 0.9."""
        results = []
        for candidate in candidates:
            if candidate.should_auto_merge:
                result = self.merge_humans(
                    keep_id=candidate.human_a_id,
                    absorb_id=candidate.human_b_id,
                    reason=f"auto-merge (confidence={candidate.confidence:.2f})",
                )
                results.append(result)
                logger.info(
                    f"Auto-merged {candidate.human_b_id} → {candidate.human_a_id} "
                    f"(confidence={candidate.confidence:.2f})"
                )
        return results

    def create_mentioned_human(
        self,
        name: str,
        mentioned_by_id: str,
        context: str = "mentioned in conversation",
    ) -> Dict[str, Any]:
        """Create a Human node from a mention in conversation.

        Creates with source='MENTIONED' and low confidence, then
        triggers entity resolution to find potential matches.

        Returns:
            Dict with created human and any merge candidates found
        """
        human_id = str(uuid_mod.uuid4())
        with self.driver.session() as session:
            session.run(
                """
                CREATE (h:Human {
                    id: $id,
                    displayName: $name,
                    confidence: 0.3,
                    firstKnown: datetime(),
                    source: 'MENTIONED',
                    lastContact: null,
                    status: 'active',
                    createdAt: datetime(),
                    updatedAt: datetime()
                })
                WITH h
                MERGE (nv:Identifier {type: 'NAME_VARIANT', value: $name})
                ON CREATE SET nv.addedAt = datetime(), nv.source = 'mention', nv.verified = false
                MERGE (h)-[:IDENTIFIED_BY]->(nv)
                WITH h
                MATCH (mentioner:Human {id: $mentioned_by})
                MERGE (mentioner)-[:KNOWN_THROUGH {context: $context, since: datetime()}]->(h)
                """,
                id=human_id,
                name=name,
                mentioned_by=mentioned_by_id,
                context=context,
            )

        # Check for merge candidates
        candidates = self.find_merge_candidates(human_id, threshold=0.5)
        auto_merged = self.auto_merge_if_confident(candidates)

        return {
            "human_id": human_id,
            "displayName": name,
            "source": "MENTIONED",
            "merge_candidates": [c.to_dict() for c in candidates if not c.should_auto_merge],
            "auto_merged": auto_merged,
        }


if __name__ == "__main__":
    resolver = EntityResolver()

    # Test name similarity
    print("Name similarity tests:")
    pairs = [
        ("Danny", "Daniel"),
        ("Danny", "Danny K"),
        ("John", "Jonathan"),
        ("Alex", "Alexander"),
        ("Danny", "Bob"),
    ]
    for a, b in pairs:
        score = _jaro_winkler(a, b)
        print(f"  {a} vs {b}: {score:.3f}")

    resolver.close()
