#!/usr/bin/env python3
"""
Privacy Request Processor - Background processing for GDPR-style requests.

Functions:
  - process_export_request() - Generate and deliver export
  - process_deletion_request() - Delete user data with confirmation
  - monitor_sla() - Check for SLA breaches
  - notify_completion() - Send notifications

Usage:
  python3 privacy_request_processor.py --process
  python3 privacy_request_processor.py --monitor
"""

import os
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conversation_logger import ConversationLogger
from conversation_privacy import ConversationPrivacy
from human_profile_memory import HumanProfileMemory

# Paths
REQUESTS_DIR = Path.home() / ".openclaw" / "agents" / "main" / "privacy_requests"
REQUESTS_DIR.mkdir(parents=True, exist_ok=True)

SLA_HOURS = 24


class PrivacyRequestProcessor:
    """Process privacy requests in background."""

    def __init__(self):
        self.privacy = ConversationPrivacy()
        self.logger = ConversationLogger()
        self.memory = HumanProfileMemory("main")

    def process_export_request(self, request_id: str) -> Dict[str, Any]:
        """Generate export package and deliver to user."""

        # Load request
        request_file = REQUESTS_DIR / f"{request_id}.json"
        if not request_file.exists():
            return {"success": False, "error": "Request not found"}

        with open(request_file, "r") as f:
            request = json.load(f)

        phone_number = request["phone_number"]

        print(f"Processing export request {request_id} for {phone_number}")

        # Gather all data
        try:
            export_data = self.privacy.export_user_data(phone_number, phone_number)

            if not export_data:
                return {"success": False, "error": "Export failed"}

            # Create export package
            export_file = REQUESTS_DIR / f"{request_id}-export.json"
            export_file.write_text(json.dumps(export_data, indent=2, default=str))

            # Set secure permissions
            os.chmod(export_file, 0o600)

            # Update request status
            request["status"] = "completed"
            request["completed_at"] = datetime.now().isoformat()
            request["export_file"] = str(export_file)

            with open(request_file, "w") as f:
                json.dump(request, f, indent=2, default=str)

            # TODO: Deliver to user (email/Signal)
            print(f"Export complete: {export_file}")

            return {
                "success": True,
                "request_id": request_id,
                "export_file": str(export_file),
                "conversation_count": len(export_data.get("conversations", []))
            }

        except Exception as e:
            print(f"Error processing export: {e}", file=sys.stderr)
            return {"success": False, "error": str(e)}

    def process_deletion_request(self, request_id: str) -> Dict[str, Any]:
        """Delete all user data with confirmation."""

        # Load request
        request_file = REQUESTS_DIR / f"{request_id}.json"
        if not request_file.exists():
            return {"success": False, "error": "Request not found"}

        with open(request_file, "r") as f:
            request = json.load(f)

        phone_number = request["phone_number"]

        print(f"Processing deletion request {request_id} for {phone_number}")

        # Delete all data
        try:
            result = self.privacy.delete_user_data(
                phone_number,
                phone_number,
                confirm=True
            )

            if not result.get("success"):
                return {"success": False, "error": "Deletion failed"}

            # Update request status
            request["status"] = "completed"
            request["completed_at"] = datetime.now().isoformat()
            request["deletion_result"] = result

            with open(request_file, "w") as f:
                json.dump(request, f, indent=2, default=str)

            # TODO: Notify user
            print(f"Deletion complete: {result.get('conversations_deleted', 0)} conversations deleted")

            return {
                "success": True,
                "request_id": request_id,
                "conversations_deleted": result.get("conversations_deleted", 0)
            }

        except Exception as e:
            print(f"Error processing deletion: {e}", file=sys.stderr)
            return {"success": False, "error": str(e)}

    def monitor_sla(self) -> List[Dict[str, Any]]:
        """Check for SLA breaches and escalate."""

        breaches = []
        now = datetime.now()

        for request_file in REQUESTS_DIR.glob("*.json"):
            try:
                with open(request_file, "r") as f:
                    request = json.load(f)

                if request.get("status") != "pending":
                    continue

                created_at = datetime.fromisoformat(request["created_at"])
                sla_deadline = created_at + timedelta(hours=SLA_HOURS)

                if now > sla_deadline:
                    # SLA breached
                    breaches.append({
                        "request_id": request["request_id"],
                        "phone_number": request["phone_number"],
                        "type": request["type"],
                        "hours_overdue": (now - sla_deadline).total_seconds() / 3600
                    })

                    # TODO: Escalate to admin
                    print(f"SLA BREACH: {request['request_id']} is {(now - sla_deadline).total_seconds() / 3600:.1f} hours overdue")

            except Exception as e:
                print(f"Error checking request {request_file}: {e}", file=sys.stderr)

        return breaches

    def process_all_pending(self) -> Dict[str, Any]:
        """Process all pending requests."""

        results = {
            "export": [],
            "delete": [],
            "sla_breaches": []
        }

        # Process export requests (exclude already completed exports)
        for request_file in REQUESTS_DIR.glob("pr-*-export.json"):
            # Skip export result files (they have double -export in name)
            if "export-export" in request_file.stem:
                continue

            request_id = request_file.stem
            result = self.process_export_request(request_id)
            results["export"].append(result)

        # Process deletion requests
        for request_file in REQUESTS_DIR.glob("pr-*-delete.json"):
            request_id = request_file.stem
            result = self.process_deletion_request(request_id)
            results["delete"].append(result)

        # Check SLA
        breaches = self.monitor_sla()
        results["sla_breaches"] = breaches

        return results


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Privacy Request Processor")
    parser.add_argument("--process", action="store_true", help="Process all pending requests")
    parser.add_argument("--monitor", action="store_true", help="Check SLA compliance")
    parser.add_argument("--request", "-r", help="Process specific request")

    args = parser.parse_args()

    processor = PrivacyRequestProcessor()

    if args.process:
        results = processor.process_all_pending()
        print(json.dumps(results, indent=2, default=str))

    elif args.monitor:
        breaches = processor.monitor_sla()
        if breaches:
            print(f"Found {len(breaches)} SLA breaches:")
            for breach in breaches:
                print(f"  - {breach['request_id']}: {breach['hours_overdue']:.1f}h overdue")
        else:
            print("No SLA breaches")

    elif args.request:
        # Process specific request
        if "export" in args.request:
            result = processor.process_export_request(args.request)
        else:
            result = processor.process_deletion_request(args.request)
        print(json.dumps(result, indent=2, default=str))

    else:
        parser.print_help()
