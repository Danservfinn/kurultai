// Calendar Notification Rules Schema Extension
// Supports: Single, Multiple, Recurring notifications with fixed/escalating/custom schedules

// =============================================================================
// CONSTRAINTS
// =============================================================================

// NotificationRule constraint
CREATE CONSTRAINT notification_rule_id_unique IF NOT EXISTS
FOR (r:NotificationRule) REQUIRE r.rule_id IS UNIQUE;

// =============================================================================
// INDEXES
// =============================================================================

// Index for finding rules by event
CREATE INDEX notification_rule_event_idx IF NOT EXISTS
FOR ()-[r:HAS_NOTIFICATION_RULE]->() ON r.event_id;

// Index for finding due notifications
CREATE INDEX notification_due_idx IF NOT EXISTS
FOR (n:Notification) ON (n.scheduled_at);

// Index for notification status
CREATE INDEX notification_status_idx IF NOT EXISTS
FOR (n:Notification) ON (n.status);

// =============================================================================
// UPDATED NODE TYPES
// =============================================================================

// Event node gains: has_notification_rules (boolean flag for quick filtering)
// NotificationRule node (NEW):
//   - rule_id: unique identifier
//   - name: display name (e.g., "15 min before", "Escalating reminder")
//   - offset_minutes: minutes relative to event start (negative = before, positive = after)
//   - offset_type: 'before' | 'at' | 'after' | 'absolute' | 'escalating' | 'custom_schedule'
//   - repeat_type: 'single' | 'multiple' | 'recurring_until_event'
//   - repeat_count: number of times to repeat (1 for single)
//   - interval_minutes: interval between repeats (for fixed intervals: 5, 15, 30, 60, 1440)
//   - custom_schedule: JSON array of ISO datetimes for custom schedule
//   - escalating_intervals: JSON array for escalating intervals [1440, 720, 120, 30]
//   - channel: 'signal' | 'email' | 'push' | 'sms'
//   - template: 'meeting' | 'deadline' | 'travel' | 'custom'
//   - message_template: custom message template
//   - is_active: boolean
//   - created_at: datetime
//   - updated_at: datetime

// Notification instance node (NEW) - created from rules when scheduled:
//   - notification_id: unique identifier
//   - rule_id: reference to parent rule
//   - scheduled_at: when to send
//   - status: 'pending' | 'sent' | 'failed' | 'cancelled'
//   - sent_at: when actually sent
//   - channel: notification channel
//   - message: rendered message

// =============================================================================
// UPDATED RELATIONSHIPS
// =============================================================================

// (Event)-[:HAS_NOTIFICATION_RULE {offset_minutes, offset_type, repeat_type,
//                                    repeat_count, interval_minutes, channel, template,
//                                    custom_schedule, escalating_intervals, is_active}]->(Person)

// (Person)-[:RECEIVES_NOTIFICATION]->(Notification)
// (Notification)-[:NOTIFICATION_FOR]->(Event)
// (Notification)-[:TRIGGERED_BY_RULE]->(NotificationRule)

// =============================================================================
// SCHEMA INIT QUERY (run once)
// =============================================================================

// Create constraint
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Notification) REQUIRE n.notification_id IS UNIQUE;

// Create indexes
CREATE INDEX IF NOT EXISTS FOR (n:Notification) ON (n.scheduled_at);
CREATE INDEX IF NOT EXISTS FOR (n:Notification) ON (n.status);
CREATE INDEX IF NOT EXISTS FOR ()-[r:HAS_NOTIFICATION_RULE]->() ON r.event_id;

// =============================================================================
// SAMPLE QUERIES
// =============================================================================

-- Add a single notification rule (15 minutes before)
MATCH (e:Event {event_id: $event_id})
MATCH (p:Person {phone_number: $phone})
MERGE (e)-[r:HAS_NOTIFICATION_RULE {
    rule_id: $rule_id,
    name: "15 minutes before",
    offset_minutes: -15,
    offset_type: "before",
    repeat_type: "single",
    repeat_count: 1,
    interval_minutes: null,
    channel: "signal",
    template: "meeting",
    is_active: true,
    created_at: datetime()
}]->(p);

-- Add escalating notification rule (1 day, 12 hours, 2 hours, 30 min before)
MATCH (e:Event {event_id: $event_id})
MATCH (p:Person {phone_number: $phone})
MERGE (e)-[r:HAS_NOTIFICATION_RULE {
    rule_id: $escalating_rule_id,
    name: "Escalating reminders",
    offset_minutes: -1440,  -- Start from 24 hours before
    offset_type: "escalating",
    repeat_type: "multiple",
    repeat_count: 4,
    escalating_intervals: [1440, 720, 120, 30],  -- in minutes before event
    channel: "signal",
    template: "deadline",
    is_active: true,
    created_at: datetime()
}]->(p);

-- Add custom schedule notification
MATCH (e:Event {event_id: $event_id})
MATCH (p:Person {phone_number: $phone})
MERGE (e)-[r:HAS_NOTIFICATION_RULE {
    rule_id: $custom_rule_id,
    name: "Custom schedule",
    offset_minutes: null,
    offset_type: "custom_schedule",
    repeat_type: "multiple",
    custom_schedule: [
        "2026-03-15T08:00:00Z",
        "2026-03-15T12:00:00Z",
        "2026-03-15T16:00:00Z"
    ],
    channel: "signal",
    template: "travel",
    is_active: true,
    created_at: datetime()
}]->(p);

-- Get all notification rules for an event
MATCH (e:Event {event_id: $event_id})-[r:HAS_NOTIFICATION_RULE]->(p:Person)
WHERE r.is_active = true
RETURN r.rule_id, r.name, r.offset_minutes, r.offset_type,
       r.repeat_type, r.repeat_count, r.channel, r.template,
       p.name as person_name, p.phone_number as person_phone
ORDER BY r.offset_minutes ASC;

-- Create notification instances from a rule
MATCH (e:Event {event_id: $event_id})-[r:HAS_NOTIFICATION_RULE]->(p:Person)
WHERE r.rule_id = $rule_id AND r.is_active = true
WITH e, r, p,
     CASE
       WHEN r.offset_type = 'escalating' THEN r.escalating_intervals
       WHEN r.repeat_type = 'multiple' AND r.interval_minutes IS NOT NULL
         THEN [i IN range(0, r.repeat_count - 1) | r.offset_minutes + (i * r.interval_minutes)]
       ELSE [r.offset_minutes]
     END as offsets
UNWIND offsets as offset_minutes
CREATE (n:Notification {
    notification_id: 'notif-' + randomUUID(),
    rule_id: r.rule_id,
    scheduled_at: e.start_datetime + duration({minutes: offset_minutes}),
    status: 'pending',
    channel: r.channel,
    template: r.template,
    created_at: datetime()
})
CREATE (n)-[:NOTIFICATION_FOR]->(e)
CREATE (p)-[:RECEIVES_NOTIFICATION]->(n)
CREATE (n)-[:TRIGGERED_BY_RULE {offset_minutes: offset_minutes}]->(r);

-- Get due notifications
MATCH (n:Notification)-[:NOTIFICATION_FOR]->(e:Event)
MATCH (p:Person)-[:RECEIVES_NOTIFICATION]->(n)
WHERE n.status = 'pending'
  AND n.scheduled_at <= datetime()
  AND e.status = 'active'
RETURN n.notification_id, n.channel, n.template, e.name as event_name,
       e.start_datetime as event_start, p.name as person_name,
       p.phone_number as person_phone
ORDER BY n.scheduled_at ASC;

-- Mark notification as sent
MATCH (n:Notification {notification_id: $notification_id})
SET n.status = 'sent', n.sent_at = datetime();

-- Delete all notification rules for an event
MATCH (e:Event {event_id: $event_id})-[r:HAS_NOTIFICATION_RULE]-()
DELETE r;

-- Update notification rule
MATCH (e:Event {event_id: $event_id})-[r:HAS_NOTIFICATION_RULE]->(p:Person)
WHERE r.rule_id = $rule_id
SET r.offset_minutes = $offset_minutes,
    r.interval_minutes = $interval_minutes,
    r.is_active = $is_active,
    r.updated_at = datetime();
