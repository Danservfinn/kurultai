#!/usr/bin/env python3
"""
proposal_expiration.py - Cron job to check and expire pending proposals.

Runs every 5 minutes via cron scheduler.

Usage:
    python proposal_expiration.py --check    # Check and report expired proposals
    python proposal_expiration.py --apply    # Mark expired proposals as expired
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proposal_manager import ProposalManager


def check_expiration(apply: bool = False) -> dict:
    """Check for expired proposals and optionally update their status."""
    pm = ProposalManager()
    expired = pm.get_expired_proposals()

    results = {
        "checked_at": datetime.now().isoformat(),
        "expired_count": len(expired),
        "expired_proposals": expired,
        "marked_expired": 0,
        "errors": 0
    }

    for proposal in expired:
        proposal_id = proposal["proposal_id"]
        title = proposal["title"]
        print(f"[EXPIRED] {proposal_id}: {title} (expired at {proposal['expires_at']})")

        if apply:
            try:
                pm.update_status(proposal_id, "expired")
                results["marked_expired"] += 1
                print(f"  -> Marked as expired")
            except Exception as e:
                results["errors"] += 1
                print(f"  -> ERROR: {e}")

    pm.close()
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check proposal expiration")
    parser.add_argument("--check", action="store_true", help="Check for expired proposals (default)")
    parser.add_argument("--apply", action="store_true", help="Mark expired proposals")
    args = parser.parse_args()

    results = check_expiration(apply=args.apply)
    print(f"\nChecked at: {results['checked_at']}")
    print(f"Expired: {results['expired_count']}")
    if args.apply:
        print(f"Marked expired: {results['marked_expired']}")
        print(f"Errors: {results['errors']}")


if __name__ == "__main__":
    main()
