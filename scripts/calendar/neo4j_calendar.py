"""
Signal Calendar - Neo4j Graph Operations

CRUD operations for Event, Person, Location, Reminder nodes
and ATTENDING, CREATED_BY, AT_LOCATION relationships.

Based on schema: signal-calendar-neo4j-schema.cypher
"""

import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
from enum import Enum

# Use centralized Neo4j driver with connection pooling
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from neo4j_task_tracker import get_driver, close_driver
from neo4j import Driver


class RSVPStatus(str, Enum):
    GOING = "going"
    MAYBE = "maybe"
    DECLINED = "declined"


class EventStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


@dataclass
class Event:
    event_id: str
    name: str
    start_datetime: datetime
    end_datetime: Optional[datetime] = None
    description: Optional[str] = None
    location: Optional[str] = None
    status: EventStatus = EventStatus.ACTIVE
    created_by: Optional[str] = None
    source_message: Optional[str] = None


@dataclass
class Person:
    phone_number: str
    name: str
    signal_id: Optional[str] = None
    aliases: Optional[list] = None


@dataclass
class Attendee:
    name: str
    phone: str
    rsvp: RSVPStatus


class CalendarNeo4j:
    """Neo4j operations for Signal Calendar."""

    def __init__(self, driver: Optional[Driver] = None):
        self.driver = driver or get_driver()

    def close(self):
        """Close driver using centralized cleanup."""
        close_driver()

    # =============================================================================
    # SCHEMA SETUP
    # =============================================================================

    def init_schema(self):
        """Initialize schema constraints and indexes."""
        constraints = [
            "CREATE CONSTRAINT person_phone_unique IF NOT EXISTS FOR (p:Person) REQUIRE p.phone_number IS UNIQUE",
            "CREATE CONSTRAINT person_signal_id_unique IF NOT EXISTS FOR (p:Person) REQUIRE p.signal_id IS UNIQUE",
            "CREATE CONSTRAINT event_id_unique IF NOT EXISTS FOR (e:Event) REQUIRE e.event_id IS UNIQUE",
            "CREATE CONSTRAINT location_name_unique IF NOT EXISTS FOR (l:Location) REQUIRE l.name_key IS UNIQUE",
            "CREATE CONSTRAINT reminder_id_unique IF NOT EXISTS FOR (r:Reminder) REQUIRE r.reminder_id IS UNIQUE",
            "CREATE CONSTRAINT series_id_unique IF NOT EXISTS FOR (s:RecurrenceSeries) REQUIRE s.series_id IS UNIQUE",
        ]

        indexes = [
            "CREATE INDEX event_start_idx IF NOT EXISTS FOR (e:Event) ON (e.start_datetime)",
            "CREATE INDEX event_status_idx IF NOT EXISTS FOR (e:Event) ON (e.status)",
            "CREATE INDEX event_name_idx IF NOT EXISTS FOR (e:Event) ON (e.name)",
            "CREATE INDEX person_name_idx IF NOT EXISTS FOR (p:Person) ON (p.name)",
            "CREATE INDEX reminder_due_idx IF NOT EXISTS FOR (r:Reminder) ON (r.remind_at)",
            "CREATE INDEX reminder_sent_idx IF NOT EXISTS FOR (r:Reminder) ON (r.sent)",
            "CREATE INDEX location_name_idx IF NOT EXISTS FOR (l:Location) ON (l.name)",
        ]

        fulltext = [
            "CREATE FULLTEXT INDEX event_search IF NOT EXISTS FOR (e:Event) ON EACH [e.name, e.description]",
        ]

        with self.driver.session() as session:
            for cypher in constraints + indexes + fulltext:
                try:
                    session.run(cypher)
                except Exception as e:
                    print(f"Schema init warning (may already exist): {e}")

    def seed_persons(self, persons: list[dict]):
        """Seed initial group members."""
        cypher = """
        MERGE (p:Person {phone_number: $phone})
        ON CREATE SET p.name = $name, p.aliases = $aliases, p.role = $role,
                      p.active = true, p.created_at = datetime(), p.updated_at = datetime()
        ON MATCH SET p.name = $name, p.aliases = $aliases, p.updated_at = datetime()
        RETURN p.name as name
        """
        with self.driver.session() as session:
            for person in persons:
                session.run(cypher, **person)

    # =============================================================================
    # PERSON OPERATIONS
    # =============================================================================

    def get_person_by_phone(self, phone: str) -> Optional[Person]:
        """Get person by phone number."""
        cypher = "MATCH (p:Person {phone_number: $phone}) RETURN p"
        with self.driver.session() as session:
            result = session.run(cypher, phone=phone)
            record = result.single()
            if record:
                p = record["p"]
                return Person(
                    phone_number=p["phone_number"],
                    name=p["name"],
                    signal_id=p.get("signal_id"),
                    aliases=p.get("aliases", []),
                )
            return None

    def get_person_by_name(self, name: str) -> Optional[Person]:
        """Get person by name (case-insensitive, also checks aliases)."""
        cypher = """
        MATCH (p:Person)
        WHERE toLower(p.name) = toLower($name)
           OR toLower($name) IN [x IN p.aliases | toLower(x)]
        RETURN p LIMIT 1
        """
        with self.driver.session() as session:
            result = session.run(cypher, name=name)
            record = result.single()
            if record:
                p = record["p"]
                return Person(
                    phone_number=p["phone_number"],
                    name=p["name"],
                    signal_id=p.get("signal_id"),
                    aliases=p.get("aliases", []),
                )
            return None

    # =============================================================================
    # EVENT OPERATIONS
    # =============================================================================

    def create_event(
        self,
        name: str,
        start: datetime,
        end: Optional[datetime] = None,
        creator_phone: str = "",
        location: Optional[str] = None,
        description: Optional[str] = None,
        source_message: str = "",
    ) -> Event:
        """Create a new event."""
        event_id = f"evt-{uuid.uuid4().hex[:8]}"

        # Build location key if provided
        location_key = None
        location_name = None
        if location:
            location_key = location.lower().replace(" ", "-")
            location_name = location

        cypher = """
        MATCH (creator:Person {phone_number: $creator_phone})
        CREATE (e:Event {
            event_id: $event_id,
            name: $name,
            description: $description,
            start_datetime: datetime($start),
            end_datetime: CASE WHEN $end IS NOT NULL THEN datetime($end) ELSE null END,
            all_day: false,
            status: "active",
            visibility: "group",
            source_message: $source_message,
            created_at: datetime(),
            updated_at: datetime()
        })
        CREATE (e)-[:CREATED_BY]->(creator)
        CREATE (creator)-[:ATTENDING {rsvp: "going", rsvp_at: datetime(), added_by: "self"}]->(e)
        WITH e
        FOREACH (_ IN CASE WHEN $location_key IS NOT NULL THEN [1] ELSE [] END |
            MERGE (l:Location {name_key: $location_key})
            ON CREATE SET l.name = $location_name, l.created_at = datetime()
            CREATE (e)-[:AT_LOCATION]->(l)
        )
        RETURN e
        """

        with self.driver.session() as session:
            result = session.run(
                cypher,
                event_id=event_id,
                name=name,
                description=description,
                start=start.isoformat(),
                end=end.isoformat() if end else None,
                creator_phone=creator_phone,
                source_message=source_message,
                location_key=location_key,
                location_name=location_name,
            )
            record = result.single()
            e = record["e"]
            return Event(
                event_id=e["event_id"],
                name=e["name"],
                start_datetime=e["start_datetime"],
                end_datetime=e.get("end_datetime"),
                description=e.get("description"),
                location=location,
                status=EventStatus(e["status"]),
                created_by=creator_phone,
                source_message=e.get("source_message"),
            )

    def get_event_by_id(self, event_id: str) -> Optional[Event]:
        """Get event by ID."""
        cypher = """
        MATCH (e:Event {event_id: $event_id})
        OPTIONAL MATCH (e)-[:AT_LOCATION]->(l:Location)
        OPTIONAL MATCH (e)-[:CREATED_BY]->(creator:Person)
        RETURN e, l.name as location, creator.phone_number as creator_phone
        """
        with self.driver.session() as session:
            result = session.run(cypher, event_id=event_id)
            record = result.single()
            if record:
                e = record["e"]
                return Event(
                    event_id=e["event_id"],
                    name=e["name"],
                    start_datetime=e["start_datetime"],
                    end_datetime=e.get("end_datetime"),
                    description=e.get("description"),
                    location=record.get("location"),
                    status=EventStatus(e["status"]),
                    created_by=record.get("creator_phone"),
                    source_message=e.get("source_message"),
                )
            return None

    def search_events(self, query: str, limit: int = 5) -> list[Event]:
        """Fulltext search for events."""
        cypher = """
        CALL db.index.fulltext.queryNodes("event_search", $query) YIELD node AS e, score
        WHERE e.status = "active" AND e.start_datetime >= datetime()
        WITH e, score ORDER BY score DESC LIMIT $limit
        OPTIONAL MATCH (e)-[:AT_LOCATION]->(l:Location)
        RETURN e, l.name as location
        """
        events = []
        with self.driver.session() as session:
            result = session.run(cypher, query=query, limit=limit)
            for record in result:
                e = record["e"]
                events.append(Event(
                    event_id=e["event_id"],
                    name=e["name"],
                    start_datetime=e["start_datetime"],
                    end_datetime=e.get("end_datetime"),
                    description=e.get("description"),
                    location=record.get("location"),
                    status=EventStatus(e["status"]),
                    source_message=e.get("source_message"),
                ))
        return events

    def cancel_event(self, event_id: str, requester_phone: str) -> bool:
        """Cancel an event (only creator can cancel)."""
        cypher = """
        MATCH (e:Event {event_id: $event_id})-[:CREATED_BY]->(creator:Person {phone_number: $phone})
        SET e.status = "cancelled", e.updated_at = datetime()
        RETURN e.event_id as id
        """
        with self.driver.session() as session:
            result = session.run(cypher, event_id=event_id, phone=requester_phone)
            return result.single() is not None

    def update_event_time(
        self, event_id: str, new_start: datetime, new_end: Optional[datetime] = None
    ) -> bool:
        """Update event time."""
        cypher = """
        MATCH (e:Event {event_id: $event_id})
        SET e.start_datetime = datetime($start),
            e.end_datetime = CASE WHEN $end IS NOT NULL THEN datetime($end) ELSE null END,
            e.updated_at = datetime()
        RETURN e.event_id as id
        """
        with self.driver.session() as session:
            result = session.run(
                cypher,
                event_id=event_id,
                start=new_start.isoformat(),
                end=new_end.isoformat() if new_end else None,
            )
            return result.single() is not None

    def get_upcoming_events(self, days: int = 7) -> list[dict]:
        """Get events in the next N days with attendee counts."""
        cypher = """
        MATCH (e:Event)
        WHERE e.status = "active"
          AND e.start_datetime >= datetime()
          AND e.start_datetime < datetime() + duration({days: $days})
        OPTIONAL MATCH (e)-[:AT_LOCATION]->(l:Location)
        OPTIONAL MATCH (p:Person)-[att:ATTENDING]->(e)
        WHERE att.rsvp = "going"
        WITH e, l, collect(p.name) AS attendees
        RETURN e.name AS name,
               e.start_datetime AS starts,
               e.end_datetime AS ends,
               l.name AS location,
               attendees
        ORDER BY e.start_datetime ASC
        """
        with self.driver.session() as session:
            result = session.run(cypher, days=days)
            return [dict(record) for record in result]

    def get_events_today(self) -> list[dict]:
        """Get today's events."""
        cypher = """
        MATCH (e:Event)
        WHERE e.status = "active"
          AND (
              (e.all_day = true AND date(e.start_datetime) = date())
              OR
              (e.start_datetime >= datetime({year: date().year, month: date().month, day: date().day})
               AND e.start_datetime < datetime({year: date().year, month: date().month, day: date().day}) + duration("P1D"))
          )
        OPTIONAL MATCH (e)-[:AT_LOCATION]->(l:Location)
        OPTIONAL MATCH (p:Person)-[att:ATTENDING]->(e) WHERE att.rsvp = "going"
        WITH e, l, collect(p.name) AS attendees
        RETURN e.name AS name,
               e.start_datetime AS starts,
               l.name AS location,
               attendees
        ORDER BY e.start_datetime ASC
        """
        with self.driver.session() as session:
            result = session.run(cypher)
            return [dict(record) for record in result]

    def check_conflicts(
        self, start: datetime, end: datetime, exclude_event_id: Optional[str] = None
    ) -> list[dict]:
        """Check for conflicting events."""
        cypher = """
        MATCH (e:Event)
        WHERE e.status = "active"
          AND e.start_datetime < datetime($end)
          AND e.end_datetime > datetime($start)
        """
        if exclude_event_id:
            cypher += " AND e.event_id <> $exclude_id"
        cypher += " RETURN e.name as name, e.start_datetime as starts, e.end_datetime as ends"

        with self.driver.session() as session:
            result = session.run(
                cypher,
                start=start.isoformat(),
                end=end.isoformat(),
                exclude_id=exclude_event_id,
            )
            return [dict(record) for record in result]

    # =============================================================================
    # ATTENDANCE/RSVP OPERATIONS
    # =============================================================================

    def rsvp_to_event(
        self, person_phone: str, event_id: str, status: RSVPStatus
    ) -> Optional[dict]:
        """RSVP a person to an event."""
        cypher = """
        MATCH (p:Person {phone_number: $phone})
        MATCH (e:Event {event_id: $event_id})
        MERGE (p)-[att:ATTENDING]->(e)
        ON CREATE SET att.rsvp = $status, att.rsvp_at = datetime(), att.added_by = "self"
        ON MATCH SET att.rsvp = $status, att.rsvp_at = datetime()
        RETURN e.name AS event, p.name AS person, att.rsvp AS rsvp
        """
        with self.driver.session() as session:
            result = session.run(
                cypher, phone=person_phone, event_id=event_id, status=status.value
            )
            record = result.single()
            return dict(record) if record else None

    def add_person_to_event(
        self, adder_phone: str, target_name: str, event_id: str
    ) -> Optional[dict]:
        """Add someone else to an event (creator or admin only)."""
        cypher = """
        MATCH (target:Person)
        WHERE toLower(target.name) = toLower($target_name)
           OR toLower($target_name) IN [x IN target.aliases | toLower(x)]
        WITH target LIMIT 1
        MATCH (e:Event {event_id: $event_id})
        MATCH (adder:Person {phone_number: $adder_phone})
        MERGE (target)-[att:ATTENDING]->(e)
        ON CREATE SET att.rsvp = "going", att.rsvp_at = datetime(), att.added_by = adder.phone_number
        RETURN e.name AS event, target.name AS added, adder.name AS added_by
        """
        with self.driver.session() as session:
            result = session.run(
                cypher, adder_phone=adder_phone, target_name=target_name, event_id=event_id
            )
            record = result.single()
            return dict(record) if record else None

    def get_event_attendees(self, event_id: str) -> list[Attendee]:
        """Get all attendees for an event with RSVP status."""
        cypher = """
        MATCH (p:Person)-[att:ATTENDING]->(e:Event {event_id: $event_id})
        RETURN p.name AS name, p.phone_number AS phone, att.rsvp AS rsvp
        ORDER BY att.rsvp ASC, p.name ASC
        """
        attendees = []
        with self.driver.session() as session:
            result = session.run(cypher, event_id=event_id)
            for record in result:
                attendees.append(Attendee(
                    name=record["name"],
                    phone=record["phone"],
                    rsvp=RSVPStatus(record["rsvp"]),
                ))
        return attendees

    def get_person_events(self, person_phone: str) -> list[dict]:
        """Get all upcoming events for a person."""
        cypher = """
        MATCH (p:Person {phone_number: $phone})-[att:ATTENDING]->(e:Event)
        WHERE att.rsvp IN ["going", "maybe"]
          AND e.status = "active"
          AND e.start_datetime >= datetime()
        OPTIONAL MATCH (e)-[:AT_LOCATION]->(l:Location)
        RETURN e.name AS event,
               e.start_datetime AS starts,
               l.name AS location,
               att.rsvp AS rsvp
        ORDER BY e.start_datetime ASC
        """
        with self.driver.session() as session:
            result = session.run(cypher, phone=person_phone)
            return [dict(record) for record in result]

    # =============================================================================
    # REMINDER OPERATIONS
    # =============================================================================

    def create_reminder(
        self, event_id: str, person_phone: str, remind_at: datetime, offset_desc: str
    ) -> str:
        """Create a reminder for an event."""
        reminder_id = f"rem-{uuid.uuid4().hex[:8]}"
        cypher = """
        MATCH (e:Event {event_id: $event_id})
        MATCH (p:Person {phone_number: $phone})
        CREATE (r:Reminder {
            reminder_id: $reminder_id,
            remind_at: datetime($remind_at),
            offset_desc: $offset_desc,
            sent: false,
            channel: "signal",
            created_at: datetime()
        })
        CREATE (r)-[:REMINDER_FOR]->(e)
        CREATE (r)-[:REMIND]->(p)
        RETURN r.reminder_id AS id
        """
        with self.driver.session() as session:
            result = session.run(
                cypher,
                event_id=event_id,
                phone=person_phone,
                reminder_id=reminder_id,
                remind_at=remind_at.isoformat(),
                offset_desc=offset_desc,
            )
            record = result.single()
            return record["id"] if record else ""

    def get_due_reminders(self) -> list[dict]:
        """Get all due reminders that haven't been sent."""
        cypher = """
        MATCH (r:Reminder)-[:REMINDER_FOR]->(e:Event),
              (r)-[:REMIND]->(p:Person)
        WHERE r.sent = false
          AND r.remind_at <= datetime()
          AND e.status = "active"
        RETURN r.reminder_id AS reminder_id,
               e.name AS event,
               e.start_datetime AS event_starts,
               p.name AS person,
               p.phone_number AS phone,
               r.channel AS channel
        ORDER BY r.remind_at ASC
        """
        with self.driver.session() as session:
            result = session.run(cypher)
            return [dict(record) for record in result]

    def mark_reminder_sent(self, reminder_id: str):
        """Mark a reminder as sent."""
        cypher = """
        MATCH (r:Reminder {reminder_id: $id})
        SET r.sent = true, r.sent_at = datetime()
        """
        with self.driver.session() as session:
            session.run(cypher, id=reminder_id)

    def auto_create_reminder(self, event_id: str, person_phone: str, hours_before: int = 1):
        """Auto-create a reminder N hours before event."""
        cypher = """
        MATCH (e:Event {event_id: $event_id})
        WITH e, e.start_datetime - duration({hours: $hours}) AS remind_time
        MATCH (p:Person {phone_number: $phone})
        CREATE (r:Reminder {
            reminder_id: $reminder_id,
            remind_at: remind_time,
            offset_desc: $offset_desc,
            sent: false,
            channel: "signal",
            created_at: datetime()
        })
        CREATE (r)-[:REMINDER_FOR]->(e)
        CREATE (r)-[:REMIND]->(p)
        RETURN r.reminder_id AS id
        """
        reminder_id = f"rem-{uuid.uuid4().hex[:8]}"
        with self.driver.session() as session:
            result = session.run(
                cypher,
                event_id=event_id,
                phone=person_phone,
                hours=hours_before,
                reminder_id=reminder_id,
                offset_desc=f"{hours_before} hour before",
            )
            record = result.single()
            return record["id"] if record else ""


# Singleton instance
_calendar_db: Optional[CalendarNeo4j] = None


def get_calendar_db() -> CalendarNeo4j:
    """Get or create singleton CalendarNeo4j instance."""
    global _calendar_db
    if _calendar_db is None:
        _calendar_db = CalendarNeo4j()
    return _calendar_db
