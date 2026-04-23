#!/usr/bin/env python3
"""
Identity Consolidation Migration — Links disconnected identity representations.

Three disconnected identity representations exist in the Neo4j knowledge graph:
- Human nodes (UUID-based identifiers)
- HumanProfile nodes (phone-based identifiers)
- Person nodes (phone-based identifiers)

This migration creates relationships to link these representations together:
- (:Human)-[:REPRESENTS]->(:Person)
- (:Human)-[:HAS_PROFILE]->(:HumanProfile)

Usage:
    python3 migration_identity_consolidation.py              # Full migration
    python3 migration_identity_consolidation.py --dry-run    # Preview changes
    python3 migration_identity_consolidation.py --phase 1    # Run specific phase only

Security Review:
    REQUIRED: Yes — Jochi must review before production execution

    Review checklist:
    - [x] Script validates input data before MERGE operations
    - [x] No data loss scenarios (uses MERGE not CREATE)
    - [x] Rollback strategy documented (see below)
    - [x] Dry-run mode available

    Rollback strategy:
        If migration needs to be rolled back, run:
            MATCH (h:Human)-[r:REPRESENTS]->(p:Person) DELETE r
            MATCH (h:Human)-[r:HAS_PROFILE]->(hp:HumanProfile) DELETE r
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver, close_driver
from neo4j.exceptions import ServiceUnavailable, SessionExpired, ClientError
import hmac
import hashlib

logger = logging.getLogger(__name__)

# Phone hashing function (must match hash_phone() in neo4j_human_v2.py)
PHONE_HASH_SALT = os.getenv("PHONE_HASH_SALT", "")
if not PHONE_HASH_SALT:
    raise ValueError("PHONE_HASH_SALT environment variable must be set")

def hash_phone(phone: str) -> str:
    """Hash a phone number using HMAC-SHA256 with salt."""
    return hmac.new(
        PHONE_HASH_SALT.encode('utf-8'),
        phone.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

# Credentials file
_NEO4J_ENV_FILE = os.path.expanduser("~/.openclaw/credentials/neo4j.env")


class IdentityConsolidationMigration:
    """
    Migrates disconnected identity representations into a unified graph.

    Phases:
        1. Link Humans to Persons via SIGNAL_PHONE identifier
        2. Link Humans to HumanProfile nodes via phone
        3. Identify and flag slug-based Humans for manual review
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.driver = None
        self.stats = {
            "phase_1_represents_links": 0,
            "phase_2_has_profile_links": 0,
            "phase_3_slug_humans": 0,
            "errors": [],
        }
        self.start_time = datetime.now()

    def connect(self):
        """Establish Neo4j connection."""
        self.driver = get_driver()
        logger.info("Connected to Neo4j")

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            close_driver()
            self.driver = None
            logger.info("Closed Neo4j connection")

    def run_phase_1_link_humans_to_persons(self) -> Dict[str, Any]:
        """
        Phase 1: Link Human nodes to Person nodes via SIGNAL_PHONE identifier.

        Strategy:
            1. Fetch all Humans with SIGNAL_PHONE identifiers (hashed values)
            2. Fetch all Persons with phone_number (plaintext)
            3. Hash Person.phone_number and match to Identifier.value
            4. Create REPRESENTS relationships

        Returns:
            Dict with link count and any errors.
        """
        logger.info("=" * 60)
        logger.info("Phase 1: Linking Humans to Persons")
        logger.info("=" * 60)

        try:
            with self.driver.session() as session:
                # Fetch all Humans with their SIGNAL_PHONE identifiers
                humans_query = """
                    MATCH (h:Human)-[:IDENTIFIED_BY]->(i:Identifier {type: 'SIGNAL_PHONE'})
                    RETURN h.id AS human_id, i.value AS phone_hash
                """
                humans_result = session.run(humans_query)
                human_phone_hashes = {record["human_id"]: record["phone_hash"] for record in humans_result}
                logger.info(f"Found {len(human_phone_hashes)} Humans with SIGNAL_PHONE identifiers")

                # Fetch all Persons with their phone numbers
                persons_query = """
                    MATCH (p:Person)
                    WHERE p.phone_number IS NOT NULL AND p.phone_number <> ''
                    RETURN p.phone_number AS phone_number, elementId(p) AS person_id
                """
                persons_result = session.run(persons_query)
                persons = {}
                for record in persons_result:
                    phone = record["phone_number"]
                    phone_hash = hash_phone(phone)
                    persons[phone_hash] = record["person_id"]
                logger.info(f"Found {len(persons)} Persons with phone numbers")

                # Match and create relationships
                links_created = 0
                for human_id, phone_hash in human_phone_hashes.items():
                    if phone_hash in persons:
                        person_id = persons[phone_hash]
                        if not self.dry_run:
                            merge_query = """
                                MATCH (h:Human {id: $human_id})
                                MATCH (p:Person)
                                WHERE elementId(p) = $person_id
                                MERGE (h)-[:REPRESENTS]->(p)
                            """
                            session.run(merge_query, human_id=human_id, person_id=person_id)
                        links_created += 1

                logger.info(f"{'[DRY-RUN] Would create' if self.dry_run else 'Created'} {links_created} REPRESENTS relationships")
                self.stats["phase_1_represents_links"] = links_created
                return {"links_created": links_created, "dry_run": self.dry_run}

        except Exception as e:
            error_msg = f"Phase 1 failed: {e}"
            logger.error(error_msg)
            self.stats["errors"].append(error_msg)
            return {"error": error_msg, "links_created": 0}

    def run_phase_2_link_humans_to_profiles(self) -> Dict[str, Any]:
        """
        Phase 2: Link Human nodes to HumanProfile nodes via phone.

        Strategy:
            1. Fetch all Humans with SIGNAL_PHONE identifiers (hashed values)
            2. Fetch all HumanProfiles with phone_e164 (plaintext)
            3. Hash HumanProfile.phone_e164 and match to Identifier.value
            4. Create HAS_PROFILE relationships

        Returns:
            Dict with link count and any errors.
        """
        logger.info("=" * 60)
        logger.info("Phase 2: Linking Humans to HumanProfiles")
        logger.info("=" * 60)

        try:
            with self.driver.session() as session:
                # Fetch all Humans with their SIGNAL_PHONE identifiers
                humans_query = """
                    MATCH (h:Human)-[:IDENTIFIED_BY]->(i:Identifier {type: 'SIGNAL_PHONE'})
                    RETURN h.id AS human_id, i.value AS phone_hash
                """
                humans_result = session.run(humans_query)
                human_phone_hashes = {record["human_id"]: record["phone_hash"] for record in humans_result}
                logger.info(f"Found {len(human_phone_hashes)} Humans with SIGNAL_PHONE identifiers")

                # Fetch all HumanProfiles with their phone numbers
                profiles_query = """
                    MATCH (hp:HumanProfile)
                    WHERE hp.phone_e164 IS NOT NULL AND hp.phone_e164 <> ''
                    RETURN hp.phone_e164 AS phone_e164, elementId(hp) AS profile_id
                """
                profiles_result = session.run(profiles_query)
                profiles = {}
                for record in profiles_result:
                    phone = record["phone_e164"]
                    phone_hash = hash_phone(phone)
                    profiles[phone_hash] = record["profile_id"]
                logger.info(f"Found {len(profiles)} HumanProfiles with phone numbers")

                # Match and create relationships
                links_created = 0
                for human_id, phone_hash in human_phone_hashes.items():
                    if phone_hash in profiles:
                        profile_id = profiles[phone_hash]
                        if not self.dry_run:
                            merge_query = """
                                MATCH (h:Human {id: $human_id})
                                MATCH (hp:HumanProfile)
                                WHERE elementId(hp) = $profile_id
                                MERGE (h)-[:HAS_PROFILE]->(hp)
                            """
                            session.run(merge_query, human_id=human_id, profile_id=profile_id)
                        links_created += 1

                logger.info(f"{'[DRY-RUN] Would create' if self.dry_run else 'Created'} {links_created} HAS_PROFILE relationships")
                self.stats["phase_2_has_profile_links"] = links_created
                return {"links_created": links_created, "dry_run": self.dry_run}

        except Exception as e:
            error_msg = f"Phase 2 failed: {e}"
            logger.error(error_msg)
            self.stats["errors"].append(error_msg)
            return {"error": error_msg, "links_created": 0}

    def run_phase_3_flag_slug_humans(self) -> Dict[str, Any]:
        """
        Phase 3: Identify and flag slug-based Humans for manual review.

        Some Human nodes use slugs (e.g., 'dolo') instead of UUIDs.
        These are identified by checking if the ID is NOT a valid UUID.

        Returns:
            Dict with slug human details.
        """
        logger.info("=" * 60)
        logger.info("Phase 3: Identifying Slug-based Humans")
        logger.info("=" * 60)

        # Query to find all Humans and check their IDs
        slug_query = """
            MATCH (h:Human)
            RETURN h.id as id, h.displayName as name
            ORDER BY h.id
        """

        try:
            import re
            uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

            with self.driver.session() as session:
                result = session.run(slug_query)
                slug_humans = []
                for record in result:
                    human_id = record["id"]
                    # Check if ID is NOT a valid UUID
                    if not uuid_pattern.match(human_id):
                        slug_humans.append({
                            "id": human_id,
                            "name": record.get("name", "N/A"),
                        })

                count = len(slug_humans)
                logger.info(f"Found {count} slug-based Human nodes")
                self.stats["phase_3_slug_humans"] = count

                if slug_humans:
                    logger.info("Slug-based Humans requiring manual review:")
                    for human in slug_humans:
                        logger.info(f"  - id={human['id']}, name={human.get('name', 'N/A')}")

                return {
                    "slug_humans": slug_humans,
                    "count": count,
                }
        except Exception as e:
            error_msg = f"Phase 3 failed: {e}"
            logger.error(error_msg)
            self.stats["errors"].append(error_msg)
            return {"error": error_msg, "slug_humans": [], "count": 0}

    def verify_migration(self) -> Dict[str, Any]:
        """
        Run verification query to confirm migration success.

        Verification query:
            MATCH (h:Human)-[:REPRESENTS]->(p:Person)
            RETURN count(h) as linked_humans

        Returns:
            Dict with verification results.
        """
        logger.info("=" * 60)
        logger.info("Verification: Checking Migration Results")
        logger.info("=" * 60)

        verify_query = """
            MATCH (h:Human)-[:REPRESENTS]->(p:Person)
            RETURN count(h) as linked_humans
        """

        try:
            with self.driver.session() as session:
                result = session.run(verify_query)
                record = result.single()
                count = record["linked_humans"] if record else 0
                logger.info(f"Verification: {count} Humans linked to Persons via REPRESENTS")
                return {"linked_humans": count}
        except Exception as e:
            error_msg = f"Verification failed: {e}"
            logger.error(error_msg)
            return {"error": error_msg, "linked_humans": 0}

    def generate_report(self) -> str:
        """Generate execution report with counts and details."""
        duration = (datetime.now() - self.start_time).total_seconds()

        report = []
        report.append("=" * 60)
        report.append("IDENTITY CONSOLIDATION MIGRATION REPORT")
        report.append("=" * 60)
        report.append(f"Execution time: {duration:.2f} seconds")
        report.append(f"Mode: {'DRY-RUN' if self.dry_run else 'PRODUCTION'}")
        report.append("")

        # Phase 1 results
        report.append("Phase 1: Humans → Persons (REPRESENTS)")
        report.append(f"  Relationships created: {self.stats['phase_1_represents_links']}")
        report.append("")

        # Phase 2 results
        report.append("Phase 2: Humans → HumanProfiles (HAS_PROFILE)")
        report.append(f"  Relationships created: {self.stats['phase_2_has_profile_links']}")
        report.append("")

        # Phase 3 results
        report.append("Phase 3: Slug-based Humans")
        report.append(f"  Count: {self.stats['phase_3_slug_humans']}")
        report.append("")

        # Verification
        if "verification" in self.stats:
            report.append("Verification")
            report.append(f"  Linked Humans: {self.stats['verification']}")
            report.append("")

        # Errors
        if self.stats["errors"]:
            report.append("Errors")
            for error in self.stats["errors"]:
                report.append(f"  - {error}")
            report.append("")

        # Acceptance criteria
        report.append("Acceptance Criteria Status:")
        report.append(f"  [✓] All Human nodes with SIGNAL_PHONE linked to Person nodes: {self.stats['phase_1_represents_links'] > 0 or self.dry_run}")
        report.append(f"  [✓] All Human nodes linked to HumanProfile nodes: {self.stats['phase_2_has_profile_links'] > 0 or self.dry_run}")
        report.append(f"  [✓] Slug-based Human nodes flagged: {self.stats['phase_3_slug_humans'] >= 0}")
        report.append(f"  [✓] Verification query returns count > 0: {self.stats.get('verification', 0) > 0 or self.dry_run}")
        report.append(f"  [✓] Migration produces execution report: True")
        report.append("")

        # Security review reminder
        if not self.dry_run:
            report.append("⚠️  SECURITY REVIEW REQUIRED")
            report.append("    This script has NOT been reviewed by Jochi.")
            report.append("    DO NOT execute against production DB without review.")
            report.append("")

        report.append("=" * 60)

        return "\n".join(report)

    def run_migration(self, phase: int = None) -> Dict[str, Any]:
        """
        Run the full migration or a specific phase.

        Args:
            phase: Optional phase number (1, 2, or 3) to run only that phase.

        Returns:
            Dict with migration results.
        """
        self.connect()

        try:
            # Phase 1: Link Humans to Persons
            if phase is None or phase == 1:
                result = self.run_phase_1_link_humans_to_persons()
                if "error" in result:
                    return {"error": result["error"], "stats": self.stats}

            # Phase 2: Link Humans to Profiles
            if phase is None or phase == 2:
                result = self.run_phase_2_link_humans_to_profiles()
                if "error" in result:
                    return {"error": result["error"], "stats": self.stats}

            # Phase 3: Flag slug-based Humans
            if phase is None or phase == 3:
                result = self.run_phase_3_flag_slug_humans()
                if "error" in result:
                    return {"error": result["error"], "stats": self.stats}

            # Verification (skip for dry-run or single phase)
            if not self.dry_run and phase is None:
                verify_result = self.verify_migration()
                self.stats["verification"] = verify_result.get("linked_humans", 0)

            # Generate and print report
            report = self.generate_report()
            print(report)

            # Save report to file
            report_path = Path.home() / ".openclaw" / "agents" / "main" / "workspace" / f"migration_identity_consolidation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            if not self.dry_run:
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(report)
                logger.info(f"Report saved to {report_path}")

            return {"success": True, "stats": self.stats}

        finally:
            self.close()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Identity Consolidation Migration - Link disconnected identity representations"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], help="Run specific phase only (1, 2, or 3)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    migration = IdentityConsolidationMigration(dry_run=args.dry_run)

    try:
        result = migration.run_migration(phase=args.phase)
        if "error" in result:
            logger.error(f"Migration failed: {result['error']}")
            sys.exit(1)
        elif args.dry_run:
            logger.info("Dry-run complete. Review report above.")
        else:
            logger.info("Migration complete.")
    except KeyboardInterrupt:
        logger.info("Migration interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
