#!/usr/bin/env python3
"""
Simple Ticket Manager - Create tickets for issues found.

Lightweight ticket system for tracking issues found by agents.
Tickets are stored as JSON files in data/workspace/tickets/

Usage:
    from ticket_manager import TicketManager
    tm = TicketManager(project_root)

    # Create ticket
    ticket_id = tm.create_ticket(
        title="Critical security issue",
        description="Details...",
        severity="critical",
        category="security",
        source_agent="jochi",
        assign_to="temüjin"
    )

    # Get open tickets
    open_tickets = tm.get_open_tickets(assign_to="temüjin")

    # Close ticket
    tm.close_ticket(ticket_id, resolution="Fixed in commit abc123")
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("kurultai.ticket_manager")


class TicketManager:
    """Manage tickets for issues found by agents."""

    SEVERITY_ORDER = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
        "info": 4
    }

    VALID_SEVERITIES = set(SEVERITY_ORDER.keys())
    VALID_CATEGORIES = {
        "security", "performance", "correctness",
        "infrastructure", "bug", "feature", "documentation"
    }

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.tickets_dir = self.project_root / "data" / "workspace" / "tickets"
        self.tickets_dir.mkdir(parents=True, exist_ok=True)

    def create_ticket(
        self,
        title: str,
        description: str,
        severity: str,
        category: str,
        source_agent: str,
        assign_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new ticket.

        Args:
            title: Brief ticket title
            description: Detailed description
            severity: critical, high, medium, low, or info
            category: security, performance, correctness, infrastructure, bug, feature
            source_agent: Agent that created the ticket (e.g., 'jochi')
            assign_to: Agent to assign ticket to (e.g., 'temüjin')
            metadata: Additional metadata (evidence, references, etc.)

        Returns:
            Ticket ID
        """
        # Validate inputs
        severity = severity.lower()
        if severity not in self.VALID_SEVERITIES:
            raise ValueError(f"Invalid severity: {severity}. Must be one of {self.VALID_SEVERITIES}")

        category = category.lower()
        if category not in self.VALID_CATEGORIES:
            category = "bug"  # Default fallback

        # Generate ticket ID
        timestamp = datetime.now(timezone.utc)
        ticket_id = f"TICKET-{timestamp.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

        ticket = {
            "id": ticket_id,
            "title": title,
            "description": description,
            "severity": severity,
            "category": category,
            "source_agent": source_agent,
            "assign_to": assign_to,
            "status": "open",
            "created_at": timestamp.isoformat(),
            "updated_at": timestamp.isoformat(),
            "closed_at": None,
            "resolution": None,
            "metadata": metadata or {}
        }

        # Save ticket
        ticket_file = self.tickets_dir / f"{ticket_id}.json"
        with open(ticket_file, 'w') as f:
            json.dump(ticket, f, indent=2)

        logger.info(f"Created ticket {ticket_id}: {title[:60]}...")
        return ticket_id

    def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific ticket by ID."""
        ticket_file = self.tickets_dir / f"{ticket_id}.json"
        if not ticket_file.exists():
            return None

        with open(ticket_file) as f:
            return json.load(f)

    def get_open_tickets(
        self,
        assign_to: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        source_agent: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get open tickets with optional filtering.

        Args:
            assign_to: Filter by assigned agent
            severity: Filter by severity
            category: Filter by category
            source_agent: Filter by source agent

        Returns:
            List of ticket dictionaries, sorted by severity (critical first)
        """
        tickets = []

        for ticket_file in self.tickets_dir.glob("TICKET-*.json"):
            try:
                with open(ticket_file) as f:
                    ticket = json.load(f)

                if ticket.get("status") != "open":
                    continue

                # Apply filters
                if assign_to and ticket.get("assign_to") != assign_to:
                    continue
                if severity and ticket.get("severity") != severity:
                    continue
                if category and ticket.get("category") != category:
                    continue
                if source_agent and ticket.get("source_agent") != source_agent:
                    continue

                tickets.append(ticket)

            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load ticket {ticket_file}: {e}")
                continue

        # Sort by severity (critical first)
        tickets.sort(key=lambda t: self.SEVERITY_ORDER.get(t.get("severity", "info"), 99))

        return tickets

    def get_all_tickets(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get all tickets with optional status filter.

        Args:
            status: Filter by status (open, closed, in_progress)
            limit: Maximum number of tickets to return

        Returns:
            List of tickets, sorted by creation date (newest first)
        """
        tickets = []

        for ticket_file in self.tickets_dir.glob("TICKET-*.json"):
            try:
                with open(ticket_file) as f:
                    ticket = json.load(f)

                if status and ticket.get("status") != status:
                    continue

                tickets.append(ticket)

            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load ticket {ticket_file}: {e}")
                continue

        # Sort by creation date (newest first)
        tickets.sort(key=lambda t: t.get("created_at", ""), reverse=True)

        return tickets[:limit]

    def update_ticket(
        self,
        ticket_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update a ticket with new values.

        Args:
            ticket_id: Ticket ID to update
            updates: Dictionary of fields to update

        Returns:
            Updated ticket or None if not found
        """
        ticket_file = self.tickets_dir / f"{ticket_id}.json"
        if not ticket_file.exists():
            return None

        with open(ticket_file) as f:
            ticket = json.load(f)

        # Apply updates
        allowed_fields = {"title", "description", "severity", "category",
                         "assign_to", "status", "metadata"}

        for field, value in updates.items():
            if field in allowed_fields:
                ticket[field] = value

        ticket["updated_at"] = datetime.now(timezone.utc).isoformat()

        with open(ticket_file, 'w') as f:
            json.dump(ticket, f, indent=2)

        logger.info(f"Updated ticket {ticket_id}")
        return ticket

    def close_ticket(
        self,
        ticket_id: str,
        resolution: str,
        status: str = "closed"
    ) -> Optional[Dict[str, Any]]:
        """
        Close a ticket with resolution.

        Args:
            ticket_id: Ticket ID to close
            resolution: Resolution description
            status: Final status (closed, resolved, wont_fix)

        Returns:
            Closed ticket or None if not found
        """
        ticket_file = self.tickets_dir / f"{ticket_id}.json"
        if not ticket_file.exists():
            return None

        with open(ticket_file) as f:
            ticket = json.load(f)

        ticket["status"] = status
        ticket["resolution"] = resolution
        ticket["closed_at"] = datetime.now(timezone.utc).isoformat()
        ticket["updated_at"] = ticket["closed_at"]

        with open(ticket_file, 'w') as f:
            json.dump(ticket, f, indent=2)

        logger.info(f"Closed ticket {ticket_id}: {resolution[:60]}...")
        return ticket

    def assign_ticket(
        self,
        ticket_id: str,
        assign_to: str
    ) -> Optional[Dict[str, Any]]:
        """Assign a ticket to an agent."""
        return self.update_ticket(ticket_id, {"assign_to": assign_to})

    def get_ticket_stats(self) -> Dict[str, Any]:
        """Get statistics about tickets."""
        all_tickets = self.get_all_tickets(limit=10000)

        stats = {
            "total": len(all_tickets),
            "by_status": {},
            "by_severity": {},
            "by_category": {},
            "by_assignee": {},
            "open_critical": 0,
            "open_high": 0
        }

        for ticket in all_tickets:
            status = ticket.get("status", "unknown")
            severity = ticket.get("severity", "unknown")
            category = ticket.get("category", "unknown")
            assignee = ticket.get("assign_to", "unassigned")

            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1

            if status == "open":
                stats["by_assignee"][assignee] = stats["by_assignee"].get(assignee, 0) + 1
                if severity == "critical":
                    stats["open_critical"] += 1
                elif severity == "high":
                    stats["open_high"] += 1

        return stats

    def create_tickets_from_findings(
        self,
        findings: List[Dict[str, Any]],
        source_agent: str,
        max_tickets: int = 5
    ) -> List[str]:
        """
        Create tickets from test findings.

        Args:
            findings: List of finding dictionaries
            source_agent: Agent creating tickets
            max_tickets: Maximum number of tickets to create

        Returns:
            List of created ticket IDs
        """
        created = []

        for finding in findings[:max_tickets]:
            try:
                # Map severity
                severity = finding.get("severity", "medium").lower()
                if severity not in self.VALID_SEVERITIES:
                    severity = "medium"

                # Map category
                category = finding.get("category", "bug").lower()
                if category not in self.VALID_CATEGORIES:
                    category = "bug"

                # Determine assignee based on category
                assignee_map = {
                    "security": "temüjin",
                    "performance": "jochi",
                    "correctness": "temüjin",
                    "infrastructure": "ögedei",
                    "bug": "temüjin",
                    "feature": "kublai"
                }
                assign_to = assignee_map.get(category, "kublai")

                ticket_id = self.create_ticket(
                    title=finding.get("title", "Issue found"),
                    description=finding.get("description", ""),
                    severity=severity,
                    category=category,
                    source_agent=source_agent,
                    assign_to=assign_to,
                    metadata={
                        "evidence": finding.get("evidence", {}),
                        "source_phase": finding.get("source_phase", ""),
                        "source_test": finding.get("source_test", ""),
                        "remediation": finding.get("remediation", "")
                    }
                )

                created.append(ticket_id)

            except Exception as e:
                logger.error(f"Failed to create ticket for finding: {e}")
                continue

        return created


# ============================================================================
# CLI for testing
# ============================================================================

def main():
    """CLI for ticket manager."""
    import argparse

    parser = argparse.ArgumentParser(description="Ticket manager CLI")
    parser.add_argument("command", choices=[
        "create", "list", "show", "close", "assign", "stats"
    ])
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--title", help="Ticket title")
    parser.add_argument("--description", help="Ticket description")
    parser.add_argument("--severity", choices=TicketManager.VALID_SEVERITIES, default="medium")
    parser.add_argument("--category", choices=TicketManager.VALID_CATEGORIES, default="bug")
    parser.add_argument("--source-agent", default="cli")
    parser.add_argument("--assign-to", help="Agent to assign")
    parser.add_argument("--ticket-id", help="Ticket ID")
    parser.add_argument("--resolution", help="Resolution when closing")
    parser.add_argument("--status", choices=["open", "closed", "in_progress"])

    args = parser.parse_args()

    tm = TicketManager(args.project_root)

    if args.command == "create":
        if not args.title or not args.description:
            print("--title and --description required")
            return

        ticket_id = tm.create_ticket(
            title=args.title,
            description=args.description,
            severity=args.severity,
            category=args.category,
            source_agent=args.source_agent,
            assign_to=args.assign_to
        )
        print(f"Created ticket: {ticket_id}")

    elif args.command == "list":
        tickets = tm.get_open_tickets(
            assign_to=args.assign_to,
            severity=args.severity,
            category=args.category
        )
        print(f"Found {len(tickets)} open tickets:")
        for t in tickets:
            print(f"  [{t['severity'].upper():8}] {t['id']}: {t['title'][:50]}...")
            if t['assign_to']:
                print(f"           Assigned to: {t['assign_to']}")

    elif args.command == "show":
        if not args.ticket_id:
            print("--ticket-id required")
            return

        ticket = tm.get_ticket(args.ticket_id)
        if ticket:
            print(json.dumps(ticket, indent=2))
        else:
            print(f"Ticket {args.ticket_id} not found")

    elif args.command == "close":
        if not args.ticket_id:
            print("--ticket-id required")
            return

        if not args.resolution:
            print("--resolution required")
            return

        ticket = tm.close_ticket(args.ticket_id, args.resolution)
        if ticket:
            print(f"Closed ticket {args.ticket_id}")
        else:
            print(f"Ticket {args.ticket_id} not found")

    elif args.command == "assign":
        if not args.ticket_id or not args.assign_to:
            print("--ticket-id and --assign-to required")
            return

        ticket = tm.assign_ticket(args.ticket_id, args.assign_to)
        if ticket:
            print(f"Assigned ticket {args.ticket_id} to {args.assign_to}")
        else:
            print(f"Ticket {args.ticket_id} not found")

    elif args.command == "stats":
        stats = tm.get_ticket_stats()
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
