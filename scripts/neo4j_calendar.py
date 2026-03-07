#!/usr/bin/env python3
"""
Neo4j Calendar - Graph CRUD operations for Signal calendar system

Schema:
- (:Person {phone_number, name, aliases, signal_id})
- (:Event {event_id, name, start_datetime, end_datetime, status})
- (:Location {name_key, name, address})
- (:Reminder {reminder_id, remind_at, sent})
- (:RecurrenceSeries {series_id, rrule, frequency})

Relationships:
- (Event)-[:CREATED_BY]->(Person)
- (Person)-[:ATTENDING {rsvp}]->(Event)
- (Event)-[:AT_LOCATION]->(Location)
- (Reminder)-[:REMINDER_FOR]->(Event)
- (Reminder)-[:REMIND]->(Person)
- (Event)-[:INSTANCE_OF]->(RecurrenceSeries)
"""

import os
import sys
import json
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver

LOCAL_TZ = ZoneInfo("America/New_York")
DEFAULT_DURATION_HOURS = 2


# =============================================================================
# Schema Setup
# =============================================================================

def init_schema():
    """Create all constraints and indexes for the calendar schema."""
    driver = get_driver()

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

    with driver.session() as session:
        for constraint in constraints:
            session.run(constraint)
        for index in indexes:
            session.run(index)

        # Fulltext index for event search
        session.run("CREATE FULLTEXT INDEX event_search IF NOT EXISTS FOR (e:Event) ON EACH [e.name, e.description]")

    driver.close()
    return True


def seed_persons():
    """Seed Person nodes for group members."""
    driver = get_driver()

    persons = [
        {"phone": "+19194133445", "name": "Danny", "role": "admin"},
        {"phone": "+16624580725", "name": "Liz", "role": "member"},
    ]

    with driver.session() as session:
        for p in persons:
            session.run("""
                MERGE (person:Person {phone_number: $phone})
                ON CREATE SET
                    person.name = $name,
                    person.role = $role,
                    person.active = true,
                    person.aliases = [],
                    person.created_at = datetime(),
                    person.updated_at = datetime()
            """, **p)

    driver.close()
    return True


# =============================================================================
# Person Operations
# =============================================================================

def get_or_create_person(phone_number: str, name: str = None, aliases: List[str] = None) -> Dict[str, Any]:
    """Get existing person or create new one."""
    driver = get_driver()

    with driver.session() as session:
        result = session.run("""
            MERGE (p:Person {phone_number: $phone_number})
            ON CREATE SET
                p.name = COALESCE($name, 'Unknown'),
                p.aliases = COALESCE($aliases, []),
                p.active = true,
                p.created_at = datetime(),
                p.updated_at = datetime()
            ON MATCH SET
                p.name = COALESCE($name, p.name),
                p.updated_at = datetime()
            RETURN p
        """, phone_number=phone_number, name=name, aliases=aliases or [])

        record = result.single()
        person = dict(record["p"]) if record else None

    driver.close()
    return person


def find_person_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Find person by name or alias (case-insensitive)."""
    driver = get_driver()

    with driver.session() as session:
        result = session.run("""
            MATCH (p:Person)
            WHERE toLower(p.name) = toLower($name)
               OR toLower($name) IN [x IN p.aliases | toLower(x)]
            RETURN p
            LIMIT 1
        """, name=name)

        record = result.single()
        person = dict(record["p"]) if record else None

    driver.close()
    return person


# =============================================================================
# Event Operations
# =============================================================================

def create_event(
    name: str,
    start_datetime: datetime,
    end_datetime: datetime = None,
    creator_phone: str = None,
    description: str = None,
    location_name: str = None,
    location_address: str = None,
    source_message: str = None,
    all_day: bool = False
) -> Dict[str, Any]:
    """Create a new event with creator and optional location."""
    driver = get_driver()
    event_id = f"evt-{uuid.uuid4().hex[:8]}"

    # Default end time
    if end_datetime is None:
        end_datetime = start_datetime + timedelta(hours=DEFAULT_DURATION_HOURS)

    with driver.session() as session:
        # Match or create creator
        if creator_phone:
            session.run("""
                MERGE (p:Person {phone_number: $phone})
                ON CREATE SET
                    p.name = 'Unknown',
                    p.created_at = datetime()
            """, phone=creator_phone)

        result = session.run("""
            MATCH (creator:Person {phone_number: $creator_phone})
            CREATE (e:Event {
                event_id: $event_id,
                name: $name,
                description: $description,
                start_datetime: datetime($start),
                end_datetime: datetime($end),
                all_day: $all_day,
                status: 'active',
                visibility: 'group',
                source_message: $source_message,
                created_at: datetime(),
                updated_at: datetime()
            })
            CREATE (e)-[:CREATED_BY {created_at: datetime()}]->(creator)
            CREATE (creator)-[:ATTENDING {
                rsvp: 'going',
                rsvp_at: datetime(),
                added_by: 'self'
            }]->(e)
            WITH e, creator
            FOREACH (_ IN CASE WHEN $location_name IS NOT NULL THEN [1] ELSE [] END |
                MERGE (l:Location {name_key: $location_key})
                ON CREATE SET
                    l.name = $location_name,
                    l.address = $location_address,
                    l.created_at = datetime()
                CREATE (e)-[:AT_LOCATION]->(l)
            )
            RETURN e
        """,
            event_id=event_id,
            name=name,
            description=description,
            start=start_datetime.isoformat(),
            end=end_datetime.isoformat() if end_datetime else None,
            all_day=all_day,
            source_message=source_message,
            creator_phone=creator_phone,
            location_name=location_name,
            location_key=location_name.lower().replace(' ', '-') if location_name else None,
            location_address=location_address
        )

        record = result.single()
        event = dict(record["e"]) if record else None

    driver.close()
    return event


def get_upcoming_events(hours: int = 168) -> List[Dict[str, Any]]:
    """Get all active events in the next N hours (default 7 days)."""
    driver = get_driver()

    with driver.session() as session:
        result = session.run("""
            MATCH (e:Event)
            WHERE e.status = 'active'
              AND e.start_datetime >= datetime()
              AND e.start_datetime < datetime() + duration({hours: $hours})
            OPTIONAL MATCH (e)-[:AT_LOCATION]->(l:Location)
            OPTIONAL MATCH (p:Person)-[att:ATTENDING]->(e)
            WHERE att.rsvp = 'going'
            WITH e, l, collect(p.name) AS attendees
            RETURN e, l, attendees
            ORDER BY e.start_datetime ASC
        """, hours=hours)

        events = []
        for record in result:
            event = dict(record["e"])
            event["location"] = dict(record["l"]) if record["l"] else None
            event["attendees"] = record["attendees"]
            events.append(event)

    driver.close()
    return events


def get_events_for_person(person_name: str) -> List[Dict[str, Any]]:
    """Get all upcoming events a person is attending."""
    driver = get_driver()

    with driver.session() as session:
        result = session.run("""
            MATCH (p:Person)-[att:ATTENDING]->(e:Event)
            WHERE toLower(p.name) = toLower($person_name)
              AND att.rsvp IN ['going', 'maybe']
              AND e.status = 'active'
              AND e.start_datetime >= datetime()
            OPTIONAL MATCH (e)-[:AT_LOCATION]->(l:Location)
            RETURN e, l, att.rsvp AS rsvp
            ORDER BY e.start_datetime ASC
        """, person_name=person_name)

        events = []
        for record in result:
            event = dict(record["e"])
            event["location"] = dict(record["l"]) if record["l"] else None
            event["rsvp"] = record["rsvp"]
            events.append(event)

    driver.close()
    return events


def search_events(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Fulltext search for events by name/description."""
    driver = get_driver()

    with driver.session() as session:
        result = session.run("""
            CALL db.index.fulltext.queryNodes('event_search', $search_term)
            YIELD node AS e, score
            WHERE e.status = 'active' AND e.start_datetime >= datetime()
            WITH e, score ORDER BY score DESC LIMIT $limit
            OPTIONAL MATCH (e)-[:AT_LOCATION]->(l:Location)
            OPTIONAL MATCH (p:Person)-[att:ATTENDING]->(e) WHERE att.rsvp = 'going'
            WITH e, l, collect(p.name) AS attendees
            RETURN e, l, attendees
        """, search_term=query, limit=limit)

        events = []
        for record in result:
            event = dict(record["e"])
            event["location"] = dict(record["l"]) if record["l"] else None
            event["attendees"] = record["attendees"]
            events.append(event)

    driver.close()
    return events


def get_event_attendees(event_query: str) -> List[Dict[str, Any]]:
    """Get all attendees for an event."""
    driver = get_driver()

    with driver.session() as session:
        result = session.run("""
            CALL db.index.fulltext.queryNodes('event_search', $search_term)
            YIELD node AS e, score
            WHERE e.status = 'active'
            WITH e ORDER BY score DESC LIMIT 1
            MATCH (p:Person)-[att:ATTENDING]->(e)
            RETURN e.name AS event_name, p.name AS person, att.rsvp AS rsvp
            ORDER BY att.rsvp ASC, p.name ASC
        """, search_term=event_query)

        attendees = []
        for record in result:
            attendees.append({
                "event_name": record["event_name"],
                "person": record["person"],
                "rsvp": record["rsvp"]
            })

    driver.close()
    return attendees


# =============================================================================
# RSVP Operations
# =============================================================================

def rsvp_to_event(
    person_phone: str,
    event_query: str,
    rsvp_status: str,
    added_by: str = "self"
) -> Dict[str, Any]:
    """RSVP to an event (yes/no/maybe)."""
    driver = get_driver()

    with driver.session() as session:
        result = session.run("""
            CALL db.index.fulltext.queryNodes('event_search', $search_term)
            YIELD node AS e, score
            WHERE e.status = 'active' AND e.start_datetime >= datetime()
            WITH e ORDER BY score DESC LIMIT 1
            MATCH (p:Person {phone_number: $person_phone})
            MERGE (p)-[att:ATTENDING]->(e)
            ON CREATE SET
                att.rsvp = $rsvp,
                att.rsvp_at = datetime(),
                att.added_by = $added_by
            ON MATCH SET
                att.rsvp = $rsvp,
                att.rsvp_at = datetime()
            RETURN e.name AS event_name, e.start_datetime AS starts, p.name AS person, att.rsvp AS rsvp
        """,
            person_phone=person_phone,
            search_term=event_query,
            rsvp=rsvp_status,
            added_by=added_by
        )

        record = result.single()
        if record:
            return {
                "event_name": record["event_name"],
                "starts": record["starts"],
                "person": record["person"],
                "rsvp": record["rsvp"]
            }

    driver.close()
    return None


def add_person_to_event(
    adder_phone: str,
    target_name: str,
    event_query: str
) -> Dict[str, Any]:
    """Add another person to an event."""
    driver = get_driver()

    with driver.session() as session:
        result = session.run("""
            CALL db.index.fulltext.queryNodes('event_search', $search_term)
            YIELD node AS e, score
            WHERE e.status = 'active' AND e.start_datetime >= datetime()
            WITH e ORDER BY score DESC LIMIT 1
            MATCH (target:Person)
            WHERE toLower(target.name) = toLower($target_name)
               OR toLower($target_name) IN [x IN target.aliases | toLower(x)]
            WITH e, target LIMIT 1
            MATCH (adder:Person {phone_number: $adder_phone})
            MERGE (target)-[att:ATTENDING]->(e)
            ON CREATE SET
                att.rsvp = 'going',
                att.rsvp_at = datetime(),
                att.added_by = adder.phone_number
            RETURN e.name AS event_name, target.name AS added, adder.name AS added_by
        """,
            adder_phone=adder_phone,
            target_name=target_name,
            search_term=event_query
        )

        record = result.single()
        if record:
            return {
                "event_name": record["event_name"],
                "added": record["added"],
                "added_by": record["added_by"]
            }

    driver.close()
    return None


def remove_person_from_event(person_phone: str, event_query: str) -> Dict[str, Any]:
    """Remove self from event (decline)."""
    driver = get_driver()

    with driver.session() as session:
        result = session.run("""
            CALL db.index.fulltext.queryNodes('event_search', $search_term)
            YIELD node AS e, score
            WHERE e.status = 'active'
            WITH e ORDER BY score DESC LIMIT 1
            MATCH (p:Person {phone_number: $person_phone})-[att:ATTENDING]->(e)
            SET att.rsvp = 'declined', att.rsvp_at = datetime()
            RETURN e.name AS event_name, p.name AS person, 'declined' AS rsvp
        """, person_phone=person_phone, search_term=event_query)

        record = result.single()
        if record:
            return {
                "event_name": record["event_name"],
                "person": record["person"],
                "rsvp": record["rsvp"]
            }

    driver.close()
    return None


# =============================================================================
# Event Modification
# =============================================================================

def cancel_event(creator_phone: str, event_query: str) -> Dict[str, Any]:
    """Cancel an event (creator only)."""
    driver = get_driver()

    with driver.session() as session:
        result = session.run("""
            CALL db.index.fulltext.queryNodes('event_search', $search_term)
            YIELD node AS e, score
            WHERE e.status = 'active'
            WITH e ORDER BY score DESC LIMIT 1
            MATCH (e)-[:CREATED_BY]->(creator:Person {phone_number: $creator_phone})
            SET e.status = 'cancelled', e.updated_at = datetime()
            RETURN e.name AS event_name, e.start_datetime AS starts, 'cancelled' AS status
        """, creator_phone=creator_phone, search_term=event_query)

        record = result.single()
        if record:
            return {
                "event_name": record["event_name"],
                "starts": record["starts"],
                "status": record["status"]
            }

    driver.close()
    return None


def modify_event_time(creator_phone: str, event_query: str, new_start: datetime, new_end: datetime = None) -> Dict[str, Any]:
    """Modify event time (creator only)."""
    driver = get_driver()

    if new_end is None:
        new_end = new_start + timedelta(hours=DEFAULT_DURATION_HOURS)

    with driver.session() as session:
        result = session.run("""
            CALL db.index.fulltext.queryNodes('event_search', $search_term)
            YIELD node AS e, score
            WHERE e.status = 'active'
            WITH e ORDER BY score DESC LIMIT 1
            MATCH (e)-[:CREATED_BY]->(creator:Person {phone_number: $creator_phone})
            SET e.start_datetime = datetime($new_start),
                e.end_datetime = datetime($new_end),
                e.updated_at = datetime()
            RETURN e.name AS event_name, e.start_datetime AS new_start, e.end_datetime AS new_end
        """,
            creator_phone=creator_phone,
            search_term=event_query,
            new_start=new_start.isoformat(),
            new_end=new_end.isoformat()
        )

        record = result.single()
        if record:
            return {
                "event_name": record["event_name"],
                "new_start": record["new_start"],
                "new_end": record["new_end"]
            }

    driver.close()
    return None


# =============================================================================
# Reminder Operations
# =============================================================================

def create_reminder(
    person_phone: str,
    event_query: str,
    remind_at: datetime,
    offset_desc: str = "custom",
    channel: str = "signal"
) -> Dict[str, Any]:
    """Create a reminder for an event."""
    driver = get_driver()
    reminder_id = f"rem-{uuid.uuid4().hex[:8]}"

    with driver.session() as session:
        result = session.run("""
            CALL db.index.fulltext.queryNodes('event_search', $search_term)
            YIELD node AS e, score
            WHERE e.status = 'active' AND e.start_datetime >= datetime()
            WITH e ORDER BY score DESC LIMIT 1
            MATCH (p:Person {phone_number: $person_phone})
            CREATE (r:Reminder {
                reminder_id: $reminder_id,
                remind_at: datetime($remind_at),
                offset_desc: $offset_desc,
                sent: false,
                channel: $channel,
                created_at: datetime()
            })
            CREATE (r)-[:REMINDER_FOR]->(e)
            CREATE (r)-[:REMIND]->(p)
            RETURN e.name AS event_name, r.remind_at AS remind_at, p.name AS person
        """,
            reminder_id=reminder_id,
            person_phone=person_phone,
            search_term=event_query,
            remind_at=remind_at.isoformat(),
            offset_desc=offset_desc,
            channel=channel
        )

        record = result.single()
        if record:
            return {
                "event_name": record["event_name"],
                "remind_at": record["remind_at"],
                "person": record["person"],
                "reminder_id": reminder_id
            }

    driver.close()
    return None


def get_due_reminders() -> List[Dict[str, Any]]:
    """Get all unsent reminders that are due now."""
    driver = get_driver()

    with driver.session() as session:
        result = session.run("""
            MATCH (r:Reminder)-[:REMINDER_FOR]->(e:Event),
                  (r)-[:REMIND]->(p:Person)
            WHERE r.sent = false
              AND r.remind_at <= datetime()
              AND e.status = 'active'
            RETURN r.reminder_id AS reminder_id,
                   e.name AS event_name,
                   e.start_datetime AS event_start,
                   p.phone_number AS phone,
                   p.name AS person_name,
                   r.channel AS channel,
                   r.offset_desc AS offset
            ORDER BY r.remind_at ASC
        """)

        reminders = []
        for record in result:
            reminders.append({
                "reminder_id": record["reminder_id"],
                "event_name": record["event_name"],
                "event_start": record["event_start"],
                "phone": record["phone"],
                "person_name": record["person_name"],
                "channel": record["channel"],
                "offset": record["offset"]
            })

    driver.close()
    return reminders


def mark_reminder_sent(reminder_id: str):
    """Mark a reminder as sent."""
    driver = get_driver()

    with driver.session() as session:
        session.run("""
            MATCH (r:Reminder {reminder_id: $reminder_id})
            SET r.sent = true, r.sent_at = datetime()
        """, reminder_id=reminder_id)

    driver.close()


# =============================================================================
# Query Helpers
# =============================================================================

def get_todays_events() -> List[Dict[str, Any]]:
    """Get all events happening today."""
    driver = get_driver()

    with driver.session() as session:
        result = session.run("""
            MATCH (e:Event)
            WHERE e.status = 'active'
              AND (
                  (e.all_day = true AND date(e.start_datetime) = date())
                  OR
                  (e.start_datetime >= datetime({year: date().year, month: date().month, day: date().day})
                   AND e.start_datetime < datetime({year: date().year, month: date().month, day: date().day}) + duration('P1D'))
              )
            OPTIONAL MATCH (e)-[:AT_LOCATION]->(l:Location)
            OPTIONAL MATCH (p:Person)-[att:ATTENDING]->(e) WHERE att.rsvp = 'going'
            WITH e, l, collect(p.name) AS attendees
            RETURN e, l, attendees
            ORDER BY e.start_datetime ASC
        """)

        events = []
        for record in result:
            event = dict(record["e"])
            event["location"] = dict(record["l"]) if record["l"] else None
            event["attendees"] = record["attendees"]
            events.append(event)

    driver.close()
    return events


def get_daily_digest(days: int = 3) -> List[Dict[str, Any]]:
    """Get events for the next N days (for daily digest)."""
    driver = get_driver()

    with driver.session() as session:
        result = session.run("""
            MATCH (e:Event)
            WHERE e.status = 'active'
              AND e.start_datetime >= datetime()
              AND e.start_datetime < datetime() + duration({days: $days})
            OPTIONAL MATCH (e)-[:AT_LOCATION]->(l:Location)
            OPTIONAL MATCH (p:Person)-[att:ATTENDING]->(e) WHERE att.rsvp = 'going'
            WITH e, l, collect(p.name) AS attendees
            ORDER BY e.start_datetime ASC
            RETURN e, l, attendees
            LIMIT 10
        """, days=days)

        events = []
        for record in result:
            event = dict(record["e"])
            event["location"] = dict(record["l"]) if record["l"] else None
            event["attendees"] = record["attendees"]
            events.append(event)

    driver.close()
    return events


def check_time_conflicts(start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Check for time conflicts with existing events."""
    driver = get_driver()

    with driver.session() as session:
        result = session.run("""
            MATCH (e:Event)
            WHERE e.status = 'active'
              AND e.start_datetime < datetime($proposed_end)
              AND e.end_datetime > datetime($proposed_start)
            RETURN e.name AS event_name, e.start_datetime AS starts, e.end_datetime AS ends
        """,
            proposed_start=start.isoformat(),
            proposed_end=end.isoformat()
        )

        conflicts = []
        for record in result:
            conflicts.append({
                "event_name": record["event_name"],
                "starts": record["starts"],
                "ends": record["ends"]
            })

    driver.close()
    return conflicts


if __name__ == "__main__":
    # Test initialization
    print("Initializing calendar schema...")
    init_schema()
    print("Schema initialized")

    print("\nSeeding persons...")
    seed_persons()
    print("Persons seeded")

    print("\nCalendar module ready")
