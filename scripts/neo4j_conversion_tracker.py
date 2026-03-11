#!/usr/bin/env python3
"""
Neo4j Conversion Tracker - Graph CRUD operations for conversion context and funnel tracking

Schema:
- (:ConversionContext {context_id, human_id, first_touch_date, first_touch_source, ...})
- (:FunnelEvent {event_id, human_id, event_type, event_date, metadata, ...})

Relationships:
- (:HumanProfile)-[:HAS_CONVERSION_CONTEXT]->(:ConversionContext)
- (:HumanProfile)-[:GENERATED]->(:FunnelEvent)
- (:ConversionContext)-[:TRIGGERED_BY]->(:FunnelEvent)

Usage:
    from neo4j_conversion_tracker import ConversionTracker
    tracker = ConversionTracker()
    tracker.track_event("+19194133445", "pricing_view", {"plan": "pro"})
    context = tracker.get_conversion_context("+19194133445")
"""

import os
import sys
import json
import uuid
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver
from neo4j_utils import parse_json_field, parse_json_fields


# Subscription status enum
SUBSCRIPTION_STATUS = ["none", "trial", "pro_monthly", "pro_annual", "enterprise", "churned"]

# Funnel event types
FUNNEL_EVENT_TYPES = [
    "first_touch",           # First interaction with Parse
    "pricing_view",          # Viewed pricing page
    "signup_start",          # Started signup flow
    "signup_complete",       # Completed signup
    "checkout_start",        # Started checkout
    "checkout_complete",     # Completed purchase
    "checkout_abort",        # Abandoned checkout
    "subscription_cancel",   # Cancelled subscription
    "plan_upgrade",          # Upgraded plan
    "plan_downgrade",        # Downgraded plan
    "trial_start",           # Started trial
    "trial_end",             # Trial ended
    "feature_view",          # Viewed a feature page
    "demo_request",          # Requested a demo
    "support_contact",       # Contacted support
]

# Default conversion context template
DEFAULT_CONVERSION_CONTEXT = {
    "pricing_views": 0,
    "pricing_view_dates": [],
    "checkout_attempts": 0,
    "checkout_abort_reasons": [],
    "subscription_status": "none",
    "mrr_cents": 0,
    "total_revenue_cents": 0,
    "plan_preferences": {},
    "conversion_trigger": None,
}


class ConversionTracker:
    """CRUD operations for ConversionContext and FunnelEvent nodes in Neo4j."""

    def __init__(self):
        self.driver = get_driver()

    def close(self):
        """Close the Neo4j driver."""
        self.driver.close()

    # ==========================================================================
    # Schema Initialization
    # ==========================================================================

    def init_schema(self) -> bool:
        """Create all constraints and indexes for the conversion tracking schema."""
        constraints = [
            "CREATE CONSTRAINT conversion_context_id_unique IF NOT EXISTS FOR (c:ConversionContext) REQUIRE c.context_id IS UNIQUE",
            "CREATE CONSTRAINT funnel_event_id_unique IF NOT EXISTS FOR (f:FunnelEvent) REQUIRE f.event_id IS UNIQUE",
        ]

        indexes = [
            "CREATE INDEX conversion_context_human_id_idx IF NOT EXISTS FOR (c:ConversionContext) ON (c.human_id)",
            "CREATE INDEX funnel_event_human_id_idx IF NOT EXISTS FOR (f:FunnelEvent) ON (f.human_id)",
            "CREATE INDEX funnel_event_type_idx IF NOT EXISTS FOR (f:FunnelEvent) ON (f.event_type)",
            "CREATE INDEX funnel_event_date_idx IF NOT EXISTS FOR (f:FunnelEvent) ON (f.event_date)",
            "CREATE INDEX conversion_context_subscription_idx IF NOT EXISTS FOR (c:ConversionContext) ON (c.subscription_status)",
        ]

        with self.driver.session() as session:
            for constraint in constraints:
                session.run(constraint)
            for index in indexes:
                session.run(index)

        return True

    # ==========================================================================
    # ConversionContext CRUD
    # ==========================================================================

    def get_or_create_context(self, human_id: str, first_touch_source: Optional[str] = None) -> Dict[str, Any]:
        """
        Get existing conversion context or create a new one.

        Args:
            human_id: Phone number (E.164 format)
            first_touch_source: Source of first touch (twitter, direct, github, etc.)

        Returns:
            The conversion context dict
        """
        with self.driver.session() as session:
            result = session.run("""
                MERGE (cc:ConversionContext {human_id: $human_id})
                ON CREATE SET
                    cc.context_id = "cc-" + randomUUID(),
                    cc.first_touch_date = datetime(),
                    cc.first_touch_source = $first_touch_source,
                    cc.pricing_views = 0,
                    cc.pricing_view_dates = [],
                    cc.checkout_attempts = 0,
                    cc.checkout_abort_reasons = [],
                    cc.subscription_status = "none",
                    cc.subscription_start = null,
                    cc.subscription_end = null,
                    cc.mrr_cents = 0,
                    cc.total_revenue_cents = 0,
                    cc.plan_preferences = {},
                    cc.conversion_trigger = null,
                    cc.last_activity = datetime(),
                    cc.created_at = datetime(),
                    cc.updated_at = datetime()

                // Link to HumanProfile if exists
                WITH cc
                OPTIONAL MATCH (hp:HumanProfile {human_id: $human_id})
                FOREACH (_ IN CASE WHEN hp IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (hp)-[:HAS_CONVERSION_CONTEXT]->(cc)
                )

                RETURN cc.context_id AS context_id,
                       cc.human_id AS human_id,
                       cc.first_touch_date AS first_touch_date,
                       cc.first_touch_source AS first_touch_source,
                       cc.pricing_views AS pricing_views,
                       cc.pricing_view_dates AS pricing_view_dates,
                       cc.checkout_attempts AS checkout_attempts,
                       cc.checkout_abort_reasons AS checkout_abort_reasons,
                       cc.subscription_status AS subscription_status,
                       cc.subscription_start AS subscription_start,
                       cc.subscription_end AS subscription_end,
                       cc.mrr_cents AS mrr_cents,
                       cc.total_revenue_cents AS total_revenue_cents,
                       cc.plan_preferences AS plan_preferences,
                       cc.conversion_trigger AS conversion_trigger,
                       cc.last_activity AS last_activity
            """, human_id=human_id, first_touch_source=first_touch_source)

            record = result.single()
            if not record:
                return None

            context = dict(record)

            # Parse JSON fields
            parse_json_fields(context, ["pricing_view_dates", "checkout_abort_reasons", "plan_preferences"])

            return context

    def get_conversion_context(self, human_id: str) -> Optional[Dict[str, Any]]:
        """
        Get conversion context for a human.

        Args:
            human_id: Phone number (E.164 format)

        Returns:
            Conversion context dict or None
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (cc:ConversionContext {human_id: $human_id})
                OPTIONAL MATCH (cc)-[:TRIGGERED_BY]->(fe:FunnelEvent)
                WHERE fe.event_type = "checkout_complete"
                RETURN cc.context_id AS context_id,
                       cc.human_id AS human_id,
                       cc.first_touch_date AS first_touch_date,
                       cc.first_touch_source AS first_touch_source,
                       cc.pricing_views AS pricing_views,
                       cc.pricing_view_dates AS pricing_view_dates,
                       cc.checkout_attempts AS checkout_attempts,
                       cc.checkout_abort_reasons AS checkout_abort_reasons,
                       cc.subscription_status AS subscription_status,
                       cc.subscription_start AS subscription_start,
                       cc.subscription_end AS subscription_end,
                       cc.mrr_cents AS mrr_cents,
                       cc.total_revenue_cents AS total_revenue_cents,
                       cc.plan_preferences AS plan_preferences,
                       cc.conversion_trigger AS conversion_trigger,
                       cc.last_activity AS last_activity,
                       fe.event_id AS conversion_event_id
            """, human_id=human_id)

            record = result.single()
            if not record:
                return None

            context = dict(record)

            # Parse JSON fields
            parse_json_fields(context, ["pricing_view_dates", "checkout_abort_reasons", "plan_preferences"])

            return context

    def update_subscription(self, human_id: str, status: str,
                           mrr_cents: int = 0,
                           subscription_start: Optional[datetime] = None,
                           subscription_end: Optional[datetime] = None,
                           conversion_trigger: Optional[str] = None) -> bool:
        """
        Update subscription status for a human.

        Args:
            human_id: Phone number
            status: New subscription status
            mrr_cents: Monthly recurring revenue in cents
            subscription_start: When subscription started
            subscription_end: When subscription ends/renews
            conversion_trigger: What made them convert

        Returns:
            True if updated
        """
        if status not in SUBSCRIPTION_STATUS:
            raise ValueError(f"Invalid subscription status: {status}")

        with self.driver.session() as session:
            result = session.run("""
                MATCH (cc:ConversionContext {human_id: $human_id})
                SET cc.subscription_status = $status,
                    cc.mrr_cents = $mrr_cents,
                    cc.subscription_start = CASE WHEN $subscription_start IS NOT NULL THEN $subscription_start ELSE cc.subscription_start END,
                    cc.subscription_end = CASE WHEN $subscription_end IS NOT NULL THEN $subscription_end ELSE cc.subscription_end END,
                    cc.conversion_trigger = CASE WHEN $conversion_trigger IS NOT NULL THEN $conversion_trigger ELSE cc.conversion_trigger END,
                    cc.last_activity = datetime(),
                    cc.updated_at = datetime()

                // Update total revenue if this is a new subscription
                WITH cc
                WHERE $mrr_cents > 0 AND cc.subscription_status <> "none"
                SET cc.total_revenue_cents = cc.total_revenue_cents + $mrr_cents

                RETURN cc.context_id AS context_id
            """, human_id=human_id, status=status, mrr_cents=mrr_cents,
                subscription_start=subscription_start, subscription_end=subscription_end,
                conversion_trigger=conversion_trigger)

            return result.single() is not None

    def update_plan_preferences(self, human_id: str, preferences: Dict[str, Any]) -> bool:
        """
        Update plan preferences for a human.

        Args:
            human_id: Phone number
            preferences: Dict with feature_priorities, price_sensitivity, etc.

        Returns:
            True if updated
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (cc:ConversionContext {human_id: $human_id})
                SET cc.plan_preferences = $preferences,
                    cc.last_activity = datetime(),
                    cc.updated_at = datetime()
                RETURN cc.context_id AS context_id
            """, human_id=human_id, preferences=json.dumps(preferences))

            return result.single() is not None

    # ==========================================================================
    # FunnelEvent Tracking
    # ==========================================================================

    def track_event(self, human_id: str, event_type: str,
                    metadata: Optional[Dict[str, Any]] = None,
                    session_id: Optional[str] = None,
                    user_agent: Optional[str] = None,
                    ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Track a funnel event for a human.

        Args:
            human_id: Phone number (E.164 format)
            event_type: Type of event (pricing_view, checkout_start, etc.)
            metadata: Event-specific data
            session_id: Session identifier
            user_agent: Browser user agent
            ip_address: Client IP (will be hashed)

        Returns:
            The created event dict
        """
        if event_type not in FUNNEL_EVENT_TYPES:
            # Allow custom event types but log warning
            pass

        # Hash IP for privacy
        ip_hash = None
        if ip_address:
            ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:16]

        event_id = f"fe-{uuid.uuid4().hex[:12]}"
        metadata = metadata or {}

        # Extract metadata values for Cypher (can't access nested props on JSON string)
        metadata_source = metadata.get("source")
        metadata_reason = metadata.get("reason")

        with self.driver.session() as session:
            result = session.run("""
                // Create the funnel event
                CREATE (fe:FunnelEvent {
                    event_id: $event_id,
                    human_id: $human_id,
                    event_type: $event_type,
                    event_date: datetime(),
                    metadata: $metadata,
                    session_id: $session_id,
                    user_agent: $user_agent,
                    ip_hash: $ip_hash,
                    created_at: datetime()
                })

                // Link to HumanProfile if exists
                WITH fe
                OPTIONAL MATCH (hp:HumanProfile {human_id: $human_id})
                FOREACH (_ IN CASE WHEN hp IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (hp)-[:GENERATED]->(fe)
                )

                // Ensure conversion context exists
                WITH fe
                MERGE (cc:ConversionContext {human_id: $human_id})
                ON CREATE SET
                    cc.context_id = "cc-" + randomUUID(),
                    cc.first_touch_date = datetime(),
                    cc.first_touch_source = CASE WHEN $event_type = "first_touch" AND $metadata_source IS NOT NULL THEN $metadata_source ELSE "unknown" END,
                    cc.pricing_views = 0,
                    cc.pricing_view_dates = "[]",
                    cc.checkout_attempts = 0,
                    cc.checkout_abort_reasons = "[]",
                    cc.subscription_status = "none",
                    cc.mrr_cents = 0,
                    cc.total_revenue_cents = 0,
                    cc.plan_preferences = "{}",
                    cc.conversion_trigger = null,
                    cc.last_activity = datetime(),
                    cc.created_at = datetime(),
                    cc.updated_at = datetime()

                // Update conversion context based on event type
                WITH fe, cc
                SET cc.last_activity = datetime(),
                    cc.updated_at = datetime(),

                    // Increment pricing views
                    cc.pricing_views = CASE WHEN $event_type = "pricing_view" THEN cc.pricing_views + 1 ELSE cc.pricing_views END,
                    cc.pricing_view_dates = CASE
                        WHEN $event_type = "pricing_view"
                        THEN [date IN COALESCE(cc.pricing_view_dates, []) WHERE date > datetime() - duration('P30D')] + [datetime()]
                        ELSE cc.pricing_view_dates
                    END,

                    // Increment checkout attempts
                    cc.checkout_attempts = CASE WHEN $event_type IN ["checkout_start", "checkout_abort"] THEN cc.checkout_attempts + 1 ELSE cc.checkout_attempts END,
                    cc.checkout_abort_reasons = CASE
                        WHEN $event_type = "checkout_abort" AND $metadata_reason IS NOT NULL
                        THEN COALESCE(cc.checkout_abort_reasons, []) + [$metadata_reason]
                        ELSE cc.checkout_abort_reasons
                    END

                // Link HumanProfile to ConversionContext if both exist
                WITH fe, cc
                OPTIONAL MATCH (hp:HumanProfile {human_id: $human_id})
                FOREACH (_ IN CASE WHEN hp IS NOT NULL AND cc IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (hp)-[:HAS_CONVERSION_CONTEXT]->(cc)
                )

                // Link event as conversion trigger if checkout complete
                WITH fe, cc
                FOREACH (_ IN CASE WHEN $event_type = "checkout_complete" THEN [1] ELSE [] END |
                    MERGE (cc)-[:TRIGGERED_BY]->(fe)
                )

                RETURN fe.event_id AS event_id,
                       fe.human_id AS human_id,
                       fe.event_type AS event_type,
                       fe.event_date AS event_date,
                       fe.metadata AS metadata,
                       fe.session_id AS session_id
            """,
            event_id=event_id,
            human_id=human_id,
            event_type=event_type,
            metadata=json.dumps(metadata),
            metadata_source=metadata_source,
            metadata_reason=metadata_reason,
            session_id=session_id,
            user_agent=user_agent,
            ip_hash=ip_hash)

            record = result.single()
            if not record:
                return None

            event = dict(record)
            event["metadata"] = parse_json_field(event.get("metadata"), default={})

            return event

    def get_events(self, human_id: str, event_type: Optional[str] = None,
                   limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get funnel events for a human.

        Args:
            human_id: Phone number
            event_type: Optional filter by event type
            limit: Max results

        Returns:
            List of events
        """
        with self.driver.session() as session:
            if event_type:
                result = session.run("""
                    MATCH (fe:FunnelEvent {human_id: $human_id})
                    WHERE fe.event_type = $event_type
                    RETURN fe.event_id AS event_id,
                           fe.human_id AS human_id,
                           fe.event_type AS event_type,
                           fe.event_date AS event_date,
                           fe.metadata AS metadata,
                           fe.session_id AS session_id,
                           fe.ip_hash AS ip_hash
                    ORDER BY fe.event_date DESC
                    LIMIT $limit
                """, human_id=human_id, event_type=event_type, limit=limit)
            else:
                result = session.run("""
                    MATCH (fe:FunnelEvent {human_id: $human_id})
                    RETURN fe.event_id AS event_id,
                           fe.human_id AS human_id,
                           fe.event_type AS event_type,
                           fe.event_date AS event_date,
                           fe.metadata AS metadata,
                           fe.session_id AS session_id,
                           fe.ip_hash AS ip_hash
                    ORDER BY fe.event_date DESC
                    LIMIT $limit
                """, human_id=human_id, limit=limit)

            events = []
            for record in result:
                event = dict(record)
                if event.get("metadata") and isinstance(event["metadata"], str):
                    try:
                        event["metadata"] = json.loads(event["metadata"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                events.append(event)

            return events

    # ==========================================================================
    # Funnel Analytics
    # ==========================================================================

    def get_funnel_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Get aggregate funnel statistics.

        Args:
            days: Number of days to look back

        Returns:
            Dict with funnel metrics
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (fe:FunnelEvent)
                WHERE fe.event_date > datetime() - duration('P' + $days + 'D')

                WITH fe.event_type AS event_type, count(fe) AS count
                ORDER BY event_type

                WITH collect({type: event_type, count: count}) AS events

                // Get conversion metrics
                MATCH (cc:ConversionContext)
                WHERE cc.created_at > datetime() - duration('P' + $days + 'D')

                WITH events,
                     count(cc) AS total_leads,
                     sum(CASE WHEN cc.subscription_status IN ['pro_monthly', 'pro_annual', 'enterprise'] THEN 1 ELSE 0 END) AS converted,
                     sum(cc.mrr_cents) AS total_mrr,
                     avg(cc.pricing_views) AS avg_pricing_views

                RETURN {
                    events: events,
                    total_leads: total_leads,
                    converted: converted,
                    conversion_rate: CASE WHEN total_leads > 0 THEN toFloat(converted) / toFloat(total_leads) ELSE 0 END,
                    total_mrr_cents: total_mrr,
                    avg_pricing_views: avg_pricing_views
                } AS stats
            """, days=str(days))

            record = result.single()
            return dict(record["stats"]) if record else {}

    def get_conversion_cohort(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """
        Get conversion data for a cohort (users who first touched in date range).

        Args:
            start_date: Cohort start date
            end_date: Cohort end date

        Returns:
            List of conversion contexts
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (cc:ConversionContext)
                WHERE cc.first_touch_date >= $start_date
                  AND cc.first_touch_date <= $end_date
                RETURN cc.human_id AS human_id,
                       cc.first_touch_date AS first_touch_date,
                       cc.first_touch_source AS first_touch_source,
                       cc.subscription_status AS subscription_status,
                       cc.mrr_cents AS mrr_cents,
                       cc.total_revenue_cents AS total_revenue_cents,
                       cc.pricing_views AS pricing_views,
                       cc.checkout_attempts AS checkout_attempts,
                       cc.conversion_trigger AS conversion_trigger
                ORDER BY cc.first_touch_date
            """, start_date=start_date, end_date=end_date)

            return [dict(record) for record in result]

    def get_top_conversion_sources(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get conversion rates by first touch source.

        Args:
            limit: Max results

        Returns:
            List of sources with conversion metrics
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (cc:ConversionContext)
                WHERE cc.first_touch_source IS NOT NULL
                WITH cc.first_touch_source AS source,
                     count(cc) AS total,
                     sum(CASE WHEN cc.subscription_status IN ['pro_monthly', 'pro_annual', 'enterprise'] THEN 1 ELSE 0 END) AS converted,
                     sum(cc.mrr_cents) AS mrr
                RETURN source,
                       total,
                       converted,
                       CASE WHEN total > 0 THEN toFloat(converted) / toFloat(total) ELSE 0 END AS conversion_rate,
                       mrr
                ORDER BY converted DESC
                LIMIT $limit
            """, limit=limit)

            return [dict(record) for record in result]

    # ==========================================================================
    # Privacy and Data Management
    # ==========================================================================

    def delete_conversion_data(self, human_id: str) -> bool:
        """
        Delete all conversion data for a human (GDPR/right to delete).

        Args:
            human_id: Phone number

        Returns:
            True if deleted
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (cc:ConversionContext {human_id: $human_id})
                OPTIONAL MATCH (cc)-[r1]-()
                DELETE r1, cc

                WITH count(cc) AS deleted_contexts

                MATCH (fe:FunnelEvent {human_id: $human_id})
                OPTIONAL MATCH (fe)-[r2]-()
                DELETE r2, fe

                RETURN deleted_contexts, count(fe) AS deleted_events
            """, human_id=human_id)

            return result.single() is not None

    def anonymize_conversion_data(self, human_id: str) -> bool:
        """
        Anonymize conversion data (soft delete).

        Args:
            human_id: Phone number

        Returns:
            True if anonymized
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (cc:ConversionContext {human_id: $human_id})
                SET cc.human_id = "anon-" + randomUUID(),
                    cc.first_touch_source = "anonymized",
                    cc.plan_preferences = {},
                    cc.updated_at = datetime()

                MATCH (fe:FunnelEvent {human_id: $human_id})
                SET fe.human_id = "anon-" + randomUUID(),
                    fe.metadata = {},
                    fe.ip_hash = null,
                    fe.session_id = null,
                    fe.user_agent = null

                RETURN count(cc) AS anonymized
            """, human_id=human_id)

            return result.single() is not None


# ==========================================================================
# Helper Functions
# ==========================================================================

def get_tracker() -> ConversionTracker:
    """Factory function to get a tracker instance."""
    return ConversionTracker()


def init_conversion_tracking_system() -> bool:
    """Initialize the conversion tracking system."""
    tracker = ConversionTracker()
    try:
        return tracker.init_schema()
    finally:
        tracker.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "init":
        print("Initializing conversion tracking system...")
        if init_conversion_tracking_system():
            print("Schema initialized successfully")
        else:
            print("Failed to initialize schema")
        sys.exit(0)

    # Simple test
    tracker = ConversionTracker()

    # Test track event
    test_id = "+19999999999"
    event = tracker.track_event(
        human_id=test_id,
        event_type="first_touch",
        metadata={"source": "twitter"},
        ip_address="192.168.1.1"
    )
    print(f"Created event: {event['event_id']}")

    # Test get context
    context = tracker.get_conversion_context(test_id)
    print(f"Conversion context: {context['context_id']}")

    # Test pricing view
    tracker.track_event(test_id, "pricing_view", {"plan": "pro"})
    tracker.track_event(test_id, "checkout_start", {"plan": "pro_annual"})

    # Test subscription update
    tracker.update_subscription(
        human_id=test_id,
        status="pro_annual",
        mrr_cents=7900,
        conversion_trigger="Team needed automated task review"
    )

    # Get updated context
    context = tracker.get_conversion_context(test_id)
    print(f"Updated context - Status: {context['subscription_status']}, MRR: {context['mrr_cents']}")

    # Get events
    events = tracker.get_events(test_id)
    print(f"Events: {len(events)}")

    # Clean up
    tracker.delete_conversion_data(test_id)
    print("Test data deleted")

    tracker.close()
