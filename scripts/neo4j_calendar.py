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
from neo4j_task_tracker import neo4j_session

LOCAL_TZ = ZoneInfo("America/New_York")
DEFAULT_DURATION_HOURS = 2


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for Neo4j datetime objects."""
    def default(self, obj):
        # Handle Neo4j DateTime objects
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        # Handle regular datetime
        if isinstance(obj, (datetime, timedelta)):
            return obj.isoformat()
        return super().default(obj)


def json_dumps(obj, **kwargs):
    """JSON dumps with Neo4j datetime support."""
    return json.dumps(obj, cls=DateTimeEncoder, **kwargs)


# =============================================================================
# Schema Setup
# =============================================================================

def init_schema():
    """Create all constraints and indexes for the calendar schema."""
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

    with neo4j_session() as session:
        for constraint in constraints:
            session.run(constraint)
        for index in indexes:
            session.run(index)

        # Fulltext index for event search
        session.run("CREATE FULLTEXT INDEX event_search IF NOT EXISTS FOR (e:Event) ON EACH [e.name, e.description]")

    return True


def seed_persons():
    """Seed Person nodes for group members."""
    persons = [
        {"phone": "+19194133445", "name": "Danny", "role": "admin"},
        {"phone": "+16624580725", "name": "Liz", "role": "member"},
    ]

    with neo4j_session() as session:
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

    return True


# =============================================================================
# Person Operations
# =============================================================================

def get_or_create_person(phone_number: str, name: str = None, aliases: List[str] = None) -> Dict[str, Any]:
    """Get existing person or create new one."""
    with neo4j_session() as session:
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

    return person


def find_person_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Find person by name or alias (case-insensitive)."""
    with neo4j_session() as session:
        result = session.run("""
            MATCH (p:Person)
            WHERE toLower(p.name) = toLower($name)
               OR toLower($name) IN [x IN p.aliases | toLower(x)]
            RETURN p
            LIMIT 1
        """, name=name)

        record = result.single()
        person = dict(record["p"]) if record else None

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
    all_day: bool = False,
    # --- Enriched fields ---
    cost: str = None,
    dress_code: str = None,
    parking_info: str = None,
    transport_notes: str = None,
    what_to_bring: str = None,
    prep_time_minutes: int = None,
    category: str = None,
    vibe: str = None,
    expected_group_size: int = None,
    indoor_outdoor: str = None,
    noise_level: str = None,
    alcohol: str = None,
    age_range: str = None,
    event_url: str = None,
    ticket_url: str = None,
    menu_url: str = None,
    venue_photo_url: str = None,
    playlist_url: str = None,
    weather_note: str = None,
    rain_plan: str = None,
    dietary_notes: str = None,
    gift_registry_url: str = None,
    rsvp_deadline: str = None,
    post_event_followup: str = None,
    conversation_starters: str = None,
) -> Dict[str, Any]:
    """Create a new event with creator and optional location."""
    event_id = f"evt-{uuid.uuid4().hex[:8]}"

    # Default end time
    if end_datetime is None:
        end_datetime = start_datetime + timedelta(hours=DEFAULT_DURATION_HOURS)

    # Build enriched properties (only non-None values)
    enriched = {}
    for k, v in [
        ("cost", cost), ("dress_code", dress_code), ("parking_info", parking_info),
        ("transport_notes", transport_notes), ("what_to_bring", what_to_bring),
        ("prep_time_minutes", prep_time_minutes), ("category", category),
        ("vibe", vibe), ("expected_group_size", expected_group_size),
        ("indoor_outdoor", indoor_outdoor), ("noise_level", noise_level),
        ("alcohol", alcohol), ("age_range", age_range), ("event_url", event_url),
        ("ticket_url", ticket_url), ("menu_url", menu_url),
        ("venue_photo_url", venue_photo_url), ("playlist_url", playlist_url),
        ("weather_note", weather_note), ("rain_plan", rain_plan),
        ("dietary_notes", dietary_notes), ("gift_registry_url", gift_registry_url),
        ("rsvp_deadline", rsvp_deadline), ("post_event_followup", post_event_followup),
        ("conversation_starters", conversation_starters),
    ]:
        if v is not None:
            enriched[k] = v

    with neo4j_session() as session:
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
                creator_phone: $creator_phone,
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
            WITH e
            SET e += $enriched
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
            location_address=location_address,
            enriched=enriched
        )

        record = result.single()
        event = dict(record["e"]) if record else None

    return event


def get_upcoming_events(hours: int = 168) -> List[Dict[str, Any]]:
    """Get all active events in the next N hours (default 7 days)."""
    with neo4j_session() as session:
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

    return events


def get_events_for_person(person_name: str) -> List[Dict[str, Any]]:
    """Get all upcoming events a person is attending."""
    with neo4j_session() as session:
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

    return events


def search_events(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Fulltext search for events by name/description."""
    with neo4j_session() as session:
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

    return events


def get_event_attendees(event_query: str) -> List[Dict[str, Any]]:
    """Get all attendees for an event."""
    with neo4j_session() as session:
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
    with neo4j_session() as session:
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

    return None


def add_person_to_event(
    adder_phone: str,
    target_name: str,
    event_query: str
) -> Dict[str, Any]:
    """Add another person to an event."""
    with neo4j_session() as session:
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

    return None


def remove_person_from_event(person_phone: str, event_query: str) -> Dict[str, Any]:
    """Remove self from event (decline)."""
    with neo4j_session() as session:
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

    return None


# =============================================================================
# Event Modification
# =============================================================================

def cancel_event(creator_phone: str, event_query: str) -> Dict[str, Any]:
    """Cancel an event (creator only)."""
    with neo4j_session() as session:
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

    return None


def modify_event_time(creator_phone: str, event_query: str, new_start: datetime, new_end: datetime = None) -> Dict[str, Any]:
    """Modify event time (creator only)."""
    if new_end is None:
        new_end = new_start + timedelta(hours=DEFAULT_DURATION_HOURS)

    with neo4j_session() as session:
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
    reminder_id = f"rem-{uuid.uuid4().hex[:8]}"

    with neo4j_session() as session:
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

    return None


def get_due_reminders() -> List[Dict[str, Any]]:
    """Get all unsent reminders that are due now."""
    with neo4j_session() as session:
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

    return reminders


def mark_reminder_sent(reminder_id: str):
    """Mark a reminder as sent."""
    with neo4j_session() as session:
        session.run("""
            MATCH (r:Reminder {reminder_id: $reminder_id})
            SET r.sent = true, r.sent_at = datetime()
        """, reminder_id=reminder_id)


# =============================================================================
# Notification Rules Operations (Advanced)
# =============================================================================

def init_notification_rules_schema():
    """Create constraints and indexes for notification rules."""
    constraints = [
        "CREATE CONSTRAINT notification_rule_id_unique IF NOT EXISTS FOR (r:NotificationRule) REQUIRE r.rule_id IS UNIQUE",
        "CREATE CONSTRAINT notification_id_unique IF NOT EXISTS FOR (n:Notification) REQUIRE n.notification_id IS UNIQUE",
    ]

    indexes = [
        "CREATE INDEX notification_rule_event_idx IF NOT EXISTS FOR ()-[r:HAS_NOTIFICATION_RULE]->() ON r.event_id",
        "CREATE INDEX notification_due_idx IF NOT EXISTS FOR (n:Notification) ON (n.scheduled_at)",
        "CREATE INDEX notification_status_idx IF NOT EXISTS FOR (n:Notification) ON (n.status)",
    ]

    with neo4j_session() as session:
        for constraint in constraints:
            session.run(constraint)
        for index in indexes:
            session.run(index)

    return True


def create_notification_rule(
    event_id: str,
    person_phone: str,
    name: str,
    offset_minutes: int = None,
    offset_type: str = "before",
    repeat_type: str = "single",
    repeat_count: int = 1,
    interval_minutes: int = None,
    channel: str = "signal",
    template: str = "meeting",
    custom_schedule: List[str] = None,
    escalating_intervals: List[int] = None,
    message_template: str = None
) -> Dict[str, Any]:
    """Create a notification rule for an event."""
    rule_id = f"rule-{uuid.uuid4().hex[:8]}"

    with neo4j_session() as session:
        # Ensure person exists
        session.run("""
            MERGE (p:Person {phone_number: $phone})
            ON CREATE SET p.name = 'Unknown', p.created_at = datetime()
        """, phone=person_phone)

        result = session.run("""
            MATCH (e:Event {event_id: $event_id})
            MATCH (p:Person {phone_number: $phone})
            CREATE (e)-[r:HAS_NOTIFICATION_RULE {
                rule_id: $rule_id,
                name: $name,
                offset_minutes: $offset_minutes,
                offset_type: $offset_type,
                repeat_type: $repeat_type,
                repeat_count: $repeat_count,
                interval_minutes: $interval_minutes,
                channel: $channel,
                template: $template,
                custom_schedule: $custom_schedule,
                escalating_intervals: $escalating_intervals,
                message_template: $message_template,
                is_active: true,
                created_at: datetime()
            }]->(p)
            RETURN r, e.name as event_name, p.name as person_name
        """,
            rule_id=rule_id,
            event_id=event_id,
            phone=person_phone,
            name=name,
            offset_minutes=offset_minutes,
            offset_type=offset_type,
            repeat_type=repeat_type,
            repeat_count=repeat_count,
            interval_minutes=interval_minutes,
            channel=channel,
            template=template,
            custom_schedule=custom_schedule,
            escalating_intervals=escalating_intervals,
            message_template=message_template
        )

        record = result.single()
        if record:
            return {
                "rule_id": rule_id,
                "event_id": event_id,
                "person_phone": person_phone,
                "name": record["person_name"],
                "event_name": record["event_name"]
            }

    return None


def get_event_notification_rules(event_id: str) -> List[Dict[str, Any]]:
    """Get all active notification rules for an event."""
    with neo4j_session() as session:
        result = session.run("""
            MATCH (e:Event {event_id: $event_id})-[r:HAS_NOTIFICATION_RULE]->(p:Person)
            WHERE r.is_active = true
            RETURN r, p.name as person_name, p.phone_number as person_phone, e.name as event_name
            ORDER BY r.offset_minutes ASC
        """, event_id=event_id)

        rules = []
        for record in result:
            rule = dict(record["r"])
            rule["person_name"] = record["person_name"]
            rule["person_phone"] = record["person_phone"]
            rule["event_name"] = record["event_name"]
            rules.append(rule)

    return rules


def update_notification_rule(
    event_id: str,
    rule_id: str,
    person_phone: str,
    offset_minutes: int = None,
    interval_minutes: int = None,
    is_active: bool = None,
    name: str = None
) -> Dict[str, Any]:
    """Update an existing notification rule."""
    with neo4j_session() as session:
        set_clauses = []
        params = {"event_id": event_id, "rule_id": rule_id, "phone": person_phone}

        if offset_minutes is not None:
            set_clauses.append("r.offset_minutes = $offset_minutes")
            params["offset_minutes"] = offset_minutes
        if interval_minutes is not None:
            set_clauses.append("r.interval_minutes = $interval_minutes")
            params["interval_minutes"] = interval_minutes
        if is_active is not None:
            set_clauses.append("r.is_active = $is_active")
            params["is_active"] = is_active
        if name is not None:
            set_clauses.append("r.name = $name")
            params["name"] = name

        if not set_clauses:
            return {"error": "No fields to update"}

        set_clauses.append("r.updated_at = datetime()")

        result = session.run(f"""
            MATCH (e:Event {{event_id: $event_id}})-[r:HAS_NOTIFICATION_RULE]->(p:Person {{phone_number: $phone}})
            WHERE r.rule_id = $rule_id
            SET {', '.join(set_clauses)}
            RETURN r, p.name as person_name
        """, **params)

        record = result.single()
        if record:
            return {
                "rule_id": rule_id,
                "updated": True,
                "person_name": record["person_name"]
            }

    return None


def delete_notification_rule(event_id: str, rule_id: str, person_phone: str) -> Dict[str, Any]:
    """Delete a notification rule."""
    with neo4j_session() as session:
        result = session.run("""
            MATCH (e:Event {event_id: $event_id})-[r:HAS_NOTIFICATION_RULE]->(p:Person {phone_number: $phone})
            WHERE r.rule_id = $rule_id
            DELETE r
            RETURN r.rule_id as deleted_rule_id
        """, event_id=event_id, rule_id=rule_id, phone=person_phone)

        record = result.single()
        if record:
            return {"rule_id": record["deleted_rule_id"], "deleted": True}

    return None


def create_notification_instances_from_rules(event_id: str) -> List[Dict[str, Any]]:
    """Create notification instances from active rules for an event."""
    created = []

    with neo4j_session() as session:
        # Get all active rules for the event
        rules_result = session.run("""
            MATCH (e:Event {event_id: $event_id})-[r:HAS_NOTIFICATION_RULE]->(p:Person)
            WHERE r.is_active = true
            RETURN e, r, p
        """, event_id=event_id)

        for rule_record in rules_result:
            e = rule_record["e"]
            r = rule_record["r"]
            p = rule_record["p"]

            # Calculate notification times based on rule type
            notification_times = []

            if r["offset_type"] == "escalating" and r["escalating_intervals"]:
                # Escalating: create notifications at each interval before event
                for interval in r["escalating_intervals"]:
                    notification_times.append(-interval)
            elif r["repeat_type"] == "multiple" and r["interval_minutes"]:
                # Fixed intervals: start from offset, repeat every interval_minutes
                for i in range(r["repeat_count"]):
                    notification_times.append(r["offset_minutes"] + (i * r["interval_minutes"]))
            elif r["offset_type"] == "custom_schedule" and r["custom_schedule"]:
                # Custom schedule: use provided ISO datetime strings
                for iso_dt in r["custom_schedule"]:
                    notification_times.append(("absolute", iso_dt))
            else:
                # Single notification
                notification_times.append(r["offset_minutes"])

            # Create notification instances
            for notif_time in notification_times:
                notification_id = f"notif-{uuid.uuid4().hex[:8]}"

                if isinstance(notif_time, tuple) and notif_time[0] == "absolute":
                    # Absolute time from custom schedule
                    session.run("""
                        MATCH (e:Event {event_id: $event_id})
                        MATCH (p:Person {phone_number: $phone})
                        CREATE (n:Notification {
                            notification_id: $notification_id,
                            rule_id: $rule_id,
                            scheduled_at: datetime($scheduled_at),
                            status: 'pending',
                            channel: $channel,
                            template: $template,
                            created_at: datetime()
                        })
                        CREATE (n)-[:NOTIFICATION_FOR]->(e)
                        CREATE (p)-[:RECEIVES_NOTIFICATION]->(n)
                    """,
                        notification_id=notification_id,
                        rule_id=r["rule_id"],
                        event_id=event_id,
                        phone=p["phone_number"],
                        scheduled_at=notif_time[1],
                        channel=r["channel"],
                        template=r["template"]
                    )
                else:
                    # Relative time (minutes from event start)
                    session.run("""
                        MATCH (e:Event {event_id: $event_id})
                        MATCH (p:Person {phone_number: $phone})
                        WITH e, p, e.start_datetime + duration({minutes: $offset}) AS scheduled_at
                        CREATE (n:Notification {
                            notification_id: $notification_id,
                            rule_id: $rule_id,
                            scheduled_at: scheduled_at,
                            status: 'pending',
                            channel: $channel,
                            template: $template,
                            created_at: datetime()
                        })
                        CREATE (n)-[:NOTIFICATION_FOR]->(e)
                        CREATE (p)-[:RECEIVES_NOTIFICATION]->(n)
                    """,
                        notification_id=notification_id,
                        rule_id=r["rule_id"],
                        event_id=event_id,
                        phone=p["phone_number"],
                        offset=notif_time,
                        channel=r["channel"],
                        template=r["template"]
                    )

                created.append({
                    "notification_id": notification_id,
                    "rule_id": r["rule_id"],
                    "person_phone": p["phone_number"]
                })

    return created


def get_due_notifications() -> List[Dict[str, Any]]:
    """Get all due notifications that haven't been sent."""
    with neo4j_session() as session:
        result = session.run("""
            MATCH (n:Notification)-[:NOTIFICATION_FOR]->(e:Event)
            MATCH (p:Person)-[:RECEIVES_NOTIFICATION]->(n)
            WHERE n.status = 'pending'
              AND n.scheduled_at <= datetime()
              AND e.status = 'active'
            RETURN n.notification_id, n.rule_id, n.channel, n.template,
                   e.name as event_name, e.start_datetime as event_start,
                   p.name as person_name, p.phone_number as person_phone
            ORDER BY n.scheduled_at ASC
        """)

        notifications = []
        for record in result:
            notifications.append({
                "notification_id": record["n.notification_id"],
                "rule_id": record["n.rule_id"],
                "channel": record["n.channel"],
                "template": record["n.template"],
                "event_name": record["event_name"],
                "event_start": record["event_start"],
                "person_name": record["person_name"],
                "person_phone": record["person_phone"]
            })

    return notifications


def mark_notification_sent(notification_id: str):
    """Mark a notification as sent."""
    with neo4j_session() as session:
        session.run("""
            MATCH (n:Notification {notification_id: $notification_id})
            SET n.status = 'sent', n.sent_at = datetime()
        """, notification_id=notification_id)


def delete_notification_rule_instances(event_id: str, rule_id: str) -> Dict[str, Any]:
    """Delete all notification instances for a rule."""
    with neo4j_session() as session:
        result = session.run("""
            MATCH (n:Notification {rule_id: $rule_id})-[:NOTIFICATION_FOR]->(e:Event {event_id: $event_id})
            DELETE n
            RETURN count(n) as deleted_count
        """, event_id=event_id, rule_id=rule_id)

        record = result.single()
        if record:
            return {"deleted_count": record["deleted_count"]}

    return None


# Preset templates for common notification patterns
NOTIFICATION_PRESETS = {
    "meeting": {
        "name": "Meeting Reminders",
        "rules": [
            {"offset_minutes": -15, "offset_type": "before", "repeat_type": "single", "name": "15 min before"},
        ]
    },
    "deadline": {
        "name": "Deadline Reminders",
        "rules": [
            {"offset_minutes": -1440, "offset_type": "before", "repeat_type": "multiple", "repeat_count": 4,
             "interval_minutes": None, "escalating_intervals": [1440, 720, 120, 30], "name": "Escalating reminders"},
        ]
    },
    "travel": {
        "name": "Travel Reminders",
        "rules": [
            {"offset_minutes": -2880, "offset_type": "before", "repeat_type": "single", "name": "2 days before"},
            {"offset_minutes": -1440, "offset_type": "before", "repeat_type": "single", "name": "1 day before"},
            {"offset_minutes": -120, "offset_type": "before", "repeat_type": "single", "name": "2 hours before"},
        ]
    }
}


def apply_notification_preset(event_id: str, person_phone: str, preset_name: str) -> List[Dict[str, Any]]:
    """Apply a notification preset to an event."""
    if preset_name not in NOTIFICATION_PRESETS:
        return {"error": f"Unknown preset: {preset_name}"}

    preset = NOTIFICATION_PRESETS[preset_name]
    created_rules = []

    for rule_config in preset["rules"]:
        result = create_notification_rule(
            event_id=event_id,
            person_phone=person_phone,
            name=rule_config["name"],
            offset_minutes=rule_config.get("offset_minutes"),
            offset_type=rule_config.get("offset_type", "before"),
            repeat_type=rule_config.get("repeat_type", "single"),
            repeat_count=rule_config.get("repeat_count", 1),
            interval_minutes=rule_config.get("interval_minutes"),
            escalating_intervals=rule_config.get("escalating_intervals"),
            template=preset_name
        )
        if result:
            created_rules.append(result)

    # Create notification instances from the rules
    created_notifications = create_notification_instances_from_rules(event_id)

    return {"rules": created_rules, "notifications": created_notifications}


# =============================================================================
# Query Helpers
# =============================================================================

def get_todays_events() -> List[Dict[str, Any]]:
    """Get all events happening today."""
    with neo4j_session() as session:
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

    return events


def get_daily_digest(days: int = 3) -> List[Dict[str, Any]]:
    """Get events for the next N days (for daily digest)."""
    with neo4j_session() as session:
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

    return events


def check_time_conflicts(start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Check for time conflicts with existing events."""
    with neo4j_session() as session:
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

    return conflicts


# =============================================================================
# JSON API for Web Interface
# =============================================================================

def handle_json_api(operation: str, params: dict) -> dict:
    """Handle JSON API requests from the web interface."""
    try:
        if operation == "get_events":
            start = params.get("start")
            end = params.get("end")
            person = params.get("person")
            limit = params.get("limit", 50)

            with neo4j_session() as session:
                # Build query based on filters
                query_parts = ["MATCH (e:Event)", "WHERE e.status = 'active'"]
                query_params = {}

                if start:
                    query_parts.append("AND e.start_datetime >= datetime($start)")
                    query_params["start"] = start
                if end:
                    query_parts.append("AND e.start_datetime <= datetime($end)")
                    query_params["end"] = end

                if person:
                    query_parts.extend([
                        "MATCH (p:Person {name: $person})-[att:ATTENDING]->(e)",
                        "WHERE att.rsvp IN ['going', 'maybe']"
                    ])
                    query_params["person"] = person

                query_parts.extend([
                    "OPTIONAL MATCH (e)-[:AT_LOCATION]->(l:Location)",
                    "OPTIONAL MATCH (attendee:Person)-[a:ATTENDING]->(e)",
                    "WITH e, l, collect({name: attendee.name, rsvp: a.rsvp}) AS attendees",
                    "RETURN e, l, attendees",
                    "ORDER BY e.start_datetime ASC",
                    "LIMIT $limit"
                ])
                query_params["limit"] = limit

                result = session.run(" ".join(query_parts), **query_params)
                events = []
                for record in result:
                    event = dict(record["e"])
                    event["location"] = dict(record["l"]) if record["l"] else None
                    event["attendees"] = record["attendees"]
                    events.append(event)

            return {"events": events, "count": len(events)}

        elif operation == "get_event":
            event_id = params.get("event_id")
            with neo4j_session() as session:
                result = session.run("""
                    MATCH (e:Event {event_id: $event_id})
                    OPTIONAL MATCH (e)-[:AT_LOCATION]->(l:Location)
                    OPTIONAL MATCH (creator:Person)-[:CREATED_BY]-(e)
                    OPTIONAL MATCH (attendee:Person)-[a:ATTENDING]->(e)
                    RETURN e, l, creator, collect({name: attendee.name, rsvp: a.rsvp, added_by: a.added_by}) AS attendees
                """, event_id=event_id)

                record = result.single()
                if record:
                    event = dict(record["e"])
                    event["location"] = dict(record["l"]) if record["l"] else None
                    event["creator"] = dict(record["creator"]) if record["creator"] else None
                    event["attendees"] = record["attendees"]
                    return {"event": event}
                return {"event": None}

        elif operation == "create_event":
            event = create_event(
                name=params["name"],
                start_datetime=datetime.fromisoformat(params["start_datetime"].replace('Z', '+00:00')),
                end_datetime=datetime.fromisoformat(params["end_datetime"].replace('Z', '+00:00')) if params.get("end_datetime") else None,
                creator_phone=params.get("creator_phone"),
                description=params.get("description"),
                location_name=params.get("location_name"),
                location_address=params.get("location_address"),
                all_day=params.get("all_day", False)
            )
            return {"event": event, "created": True}

        elif operation == "update_event":
            event_id = params.get("event_id")
            # Get existing event
            with neo4j_session() as session:
                set_clauses = []
                query_params = {"event_id": event_id}

                if "name" in params:
                    set_clauses.append("e.name = $name")
                    query_params["name"] = params["name"]
                if "description" in params:
                    set_clauses.append("e.description = $description")
                    query_params["description"] = params["description"]
                if "start_datetime" in params:
                    set_clauses.append("e.start_datetime = datetime($start)")
                    query_params["start"] = params["start_datetime"]
                if "end_datetime" in params:
                    set_clauses.append("e.end_datetime = datetime($end)")
                    query_params["end"] = params["end_datetime"]
                if "status" in params:
                    set_clauses.append("e.status = $status")
                    query_params["status"] = params["status"]

                set_clauses.append("e.updated_at = datetime()")

                result = session.run(f"""
                    MATCH (e:Event {{event_id: $event_id}})
                    SET {', '.join(set_clauses)}
                    RETURN e
                """, **query_params)

                record = result.single()
                return {"event": dict(record["e"]) if record else None}

        elif operation == "cancel_event":
            event_id = params.get("event_id")
            creator_phone = params.get("creator_phone")
            with neo4j_session() as session:
                if creator_phone:
                    result = session.run("""
                        MATCH (e:Event {event_id: $event_id})
                        MATCH (e)-[:CREATED_BY]->(creator:Person {phone_number: $creator_phone})
                        SET e.status = 'cancelled', e.updated_at = datetime()
                        RETURN e
                    """, event_id=event_id, creator_phone=creator_phone)
                else:
                    result = session.run("""
                        MATCH (e:Event {event_id: $event_id})
                        SET e.status = 'cancelled', e.updated_at = datetime()
                        RETURN e
                    """, event_id=event_id)

                record = result.single()
                return {"event": dict(record["e"]) if record else None, "cancelled": record is not None}

        elif operation == "get_people":
            with neo4j_session() as session:
                result = session.run("""
                    MATCH (p:Person)
                    RETURN p {
                        .*,
                        created_at: toString(p.created_at),
                        updated_at: toString(p.updated_at)
                    } as person
                    ORDER BY p.name ASC
                """)
                people = [dict(record["person"]) for record in result]
            return {"people": people, "count": len(people)}

        elif operation == "rsvp_to_event":
            result = rsvp_to_event(
                person_phone=params["person_phone"],
                event_query=params.get("event_id", ""),
                rsvp_status=params["rsvp"]
            )
            return {"rsvp": result}

        elif operation == "get_event_reminders":
            event_id = params.get("event_id")
            with neo4j_session() as session:
                result = session.run("""
                    MATCH (e:Event {event_id: $event_id})
                    MATCH (r:Reminder)-[:REMINDER_FOR]->(e)
                    MATCH (r)-[:REMIND]->(p:Person)
                    RETURN r, p.name AS person_name
                """, event_id=event_id)

                reminders = []
                for record in result:
                    rem = dict(record["r"])
                    rem["person_name"] = record["person_name"]
                    reminders.append(rem)
            return {"reminders": reminders}

        elif operation == "create_reminder":
            result = create_reminder(
                person_phone=params["person_phone"],
                event_query=params["event_id"],
                remind_at=datetime.fromisoformat(params["remind_at"].replace('Z', '+00:00')),
                offset_desc=params.get("offset_desc", "custom"),
                channel=params.get("channel", "signal")
            )
            return {"reminder": result}

        elif operation == "get_todays_events":
            events = get_todays_events()
            return {"events": events, "count": len(events)}

        elif operation == "get_notification_settings":
            phone = params.get("phone")
            with neo4j_session() as session:
                result = session.run("""
                    MATCH (p:Person {phone_number: $phone})
                    RETURN p.calendar_notifications_enabled as enabled,
                           p.calendar_notification_channel as channel,
                           p.calendar_default_reminders as reminders
                """, phone=phone)

                record = result.single()
                if record:
                    return {
                        "enabled": record["enabled"] if record["enabled"] is not None else True,
                        "channel": record["channel"] if record["channel"] is not None else "signal",
                        "default_reminders": record["reminders"] if record["reminders"] is not None else [15, 60]
                    }
                else:
                    return {"error": "Person not found"}, 404

        elif operation == "update_notification_settings":
            phone = params.get("phone")
            enabled = params.get("enabled", True)
            channel = params.get("channel", "signal")
            reminders = params.get("default_reminders", [15, 60])

            with neo4j_session() as session:
                result = session.run("""
                    MATCH (p:Person {phone_number: $phone})
                    SET p.calendar_notifications_enabled = $enabled,
                        p.calendar_notification_channel = $channel,
                        p.calendar_default_reminders = $reminders,
                        p.updated_at = datetime()
                    RETURN p.phone_number as updated
                """, phone=phone, enabled=enabled, channel=channel, reminders=reminders)

                record = result.single()
                if record:
                    return {"success": True, "phone": record["updated"]}
                else:
                    return {"error": "Person not found"}, 404

        else:
            return {"error": f"Unknown operation: {operation}"}

    except Exception as e:
        return {"error": str(e)}


def main():
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Neo4j Calendar API")
    parser.add_argument("--json", action="store_true", help="Output JSON for API mode")
    parser.add_argument("operation", nargs="?", help="API operation")
    args = parser.parse_args()

    if args.json:
        # JSON API mode
        params = json.loads(os.environ.get("CALENDAR_PARAMS", "{}"))
        result = handle_json_api(args.operation, params)
        print(json_dumps(result))
    else:
        # CLI mode - run tests
        print("Initializing calendar schema...")
        init_schema()
        print("Schema initialized")

        print("\nSeeding persons...")
        seed_persons()
        print("Persons seeded")

        print("\nCalendar module ready")


if __name__ == "__main__":
    main()
