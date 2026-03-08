#!/usr/bin/env python3
"""
Funnel Event Tracker - Event ingestion API for conversion funnel tracking

Provides a simple interface for tracking funnel events from various sources:
- Web frontend (pricing page views, checkout flow)
- Signal bot (subscription commands)
- API clients (Stripe webhooks, etc.)

Usage:
    from funnel_event_tracker import FunnelEventTracker
    tracker = FunnelEventTracker()

    # Track from web frontend
    tracker.track_web_event(
        human_id="+19194133445",
        event_type="pricing_view",
        metadata={"plan": "pro_annual", "referrer": "twitter"},
        session_id="sess_abc123",
        user_agent="Mozilla/5.0...",
        ip_address="192.168.1.1"
    )

    # Track from Signal
    tracker.track_signal_event(
        human_id="+19194133445",
        event_type="subscription_cancel",
        metadata={"reason": "too expensive"}
    )

    # Track from Stripe webhook
    tracker.track_stripe_event(
        human_id="+19194133445",
        event_type="checkout_complete",
        metadata={"plan": "pro_monthly", "amount_cents": 7900}
    )
"""

import os
import sys
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_conversion_tracker import ConversionTracker


class EventSource(Enum):
    """Source of the funnel event."""
    WEB = "web"
    SIGNAL = "signal"
    API = "api"
    STRIPE = "stripe"
    INTERNAL = "internal"


@dataclass
class FunnelEvent:
    """Represents a funnel event for tracking."""
    human_id: str
    event_type: str
    source: EventSource = EventSource.API
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for tracking."""
        return {
            "human_id": self.human_id,
            "event_type": self.event_type,
            "source": self.source.value,
            "metadata": self.metadata,
            "session_id": self.session_id,
            "user_agent": self.user_agent,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp or datetime.now()
        }


class FunnelEventTracker:
    """
    High-level event tracking API.

    Wraps Neo4j ConversionTracker with source-specific convenience methods.
    """

    def __init__(self):
        self.tracker = ConversionTracker()

    def close(self):
        """Close the tracker."""
        self.tracker.close()

    # ==========================================================================
    # Core Tracking
    # ==========================================================================

    def track(self, event: FunnelEvent) -> Dict[str, Any]:
        """
        Track a funnel event.

        Args:
            event: FunnelEvent to track

        Returns:
            The created event record
        """
        # Add source to metadata
        metadata = {**event.metadata, "source": event.source.value}

        return self.tracker.track_event(
            human_id=event.human_id,
            event_type=event.event_type,
            metadata=metadata,
            session_id=event.session_id,
            user_agent=event.user_agent,
            ip_address=event.ip_address
        )

    def track_batch(self, events: List[FunnelEvent]) -> List[Dict[str, Any]]:
        """
        Track multiple events in batch.

        Args:
            events: List of FunnelEvents

        Returns:
            List of created event records
        """
        results = []
        for event in events:
            try:
                result = self.track(event)
                results.append(result)
            except Exception as e:
                results.append({"error": str(e), "human_id": event.human_id})
        return results

    # ==========================================================================
    # Source-Specific Methods
    # ==========================================================================

    def track_web_event(self, human_id: str, event_type: str,
                        metadata: Optional[Dict[str, Any]] = None,
                        session_id: Optional[str] = None,
                        user_agent: Optional[str] = None,
                        ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Track an event from web frontend.

        Args:
            human_id: Phone number
            event_type: Event type
            metadata: Event metadata
            session_id: Browser session ID
            user_agent: Browser user agent
            ip_address: Client IP (will be hashed)

        Returns:
            Created event record
        """
        event = FunnelEvent(
            human_id=human_id,
            event_type=event_type,
            source=EventSource.WEB,
            metadata=metadata or {},
            session_id=session_id,
            user_agent=user_agent,
            ip_address=ip_address
        )
        return self.track(event)

    def track_signal_event(self, human_id: str, event_type: str,
                           metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Track an event from Signal bot.

        Args:
            human_id: Phone number (from Signal)
            event_type: Event type
            metadata: Event metadata

        Returns:
            Created event record
        """
        event = FunnelEvent(
            human_id=human_id,
            event_type=event_type,
            source=EventSource.SIGNAL,
            metadata=metadata or {}
        )
        return self.track(event)

    def track_stripe_event(self, human_id: str, event_type: str,
                           metadata: Optional[Dict[str, Any]] = None,
                           stripe_event_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Track an event from Stripe webhook.

        Args:
            human_id: Phone number
            event_type: Event type
            metadata: Event metadata
            stripe_event_id: Stripe event ID for dedup

        Returns:
            Created event record
        """
        metadata = {**(metadata or {}), "stripe_event_id": stripe_event_id}

        event = FunnelEvent(
            human_id=human_id,
            event_type=event_type,
            source=EventSource.STRIPE,
            metadata=metadata
        )
        return self.track(event)

    def track_api_event(self, human_id: str, event_type: str,
                        metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Track an event from API call.

        Args:
            human_id: Phone number
            event_type: Event type
            metadata: Event metadata

        Returns:
            Created event record
        """
        event = FunnelEvent(
            human_id=human_id,
            event_type=event_type,
            source=EventSource.API,
            metadata=metadata or {}
        )
        return self.track(event)

    # ==========================================================================
    # Convenience Methods for Common Events
    # ==========================================================================

    def track_first_touch(self, human_id: str, source: str,
                          referrer: Optional[str] = None,
                          ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Track first touch event.

        Args:
            human_id: Phone number
            source: Traffic source (twitter, direct, github, etc.)
            referrer: Referrer URL
            ip_address: Client IP

        Returns:
            Created event record
        """
        return self.track_web_event(
            human_id=human_id,
            event_type="first_touch",
            metadata={"source": source, "referrer": referrer},
            ip_address=ip_address
        )

    def track_pricing_view(self, human_id: str, plan: str,
                           session_id: Optional[str] = None,
                           ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Track pricing page view.

        Args:
            human_id: Phone number
            plan: Plan viewed (pro_monthly, pro_annual, etc.)
            session_id: Session ID
            ip_address: Client IP

        Returns:
            Created event record
        """
        return self.track_web_event(
            human_id=human_id,
            event_type="pricing_view",
            metadata={"plan": plan},
            session_id=session_id,
            ip_address=ip_address
        )

    def track_checkout_start(self, human_id: str, plan: str,
                             session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Track checkout start.

        Args:
            human_id: Phone number
            plan: Plan being purchased
            session_id: Session ID

        Returns:
            Created event record
        """
        return self.track_web_event(
            human_id=human_id,
            event_type="checkout_start",
            metadata={"plan": plan},
            session_id=session_id
        )

    def track_checkout_complete(self, human_id: str, plan: str,
                                amount_cents: int,
                                stripe_event_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Track successful checkout.

        Args:
            human_id: Phone number
            plan: Plan purchased
            amount_cents: Amount paid in cents
            stripe_event_id: Stripe event ID

        Returns:
            Created event record
        """
        return self.track_stripe_event(
            human_id=human_id,
            event_type="checkout_complete",
            metadata={"plan": plan, "amount_cents": amount_cents},
            stripe_event_id=stripe_event_id
        )

    def track_checkout_abort(self, human_id: str, plan: str,
                             reason: Optional[str] = None,
                             step: Optional[str] = None) -> Dict[str, Any]:
        """
        Track checkout abandonment.

        Args:
            human_id: Phone number
            plan: Plan attempted
            reason: Abort reason if known
            step: Step where abandoned

        Returns:
            Created event record
        """
        metadata = {"plan": plan}
        if reason:
            metadata["reason"] = reason
        if step:
            metadata["step"] = step

        return self.track_web_event(
            human_id=human_id,
            event_type="checkout_abort",
            metadata=metadata
        )

    def track_subscription_cancel(self, human_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Track subscription cancellation.

        Args:
            human_id: Phone number
            reason: Cancellation reason if known

        Returns:
            Created event record
        """
        return self.track_signal_event(
            human_id=human_id,
            event_type="subscription_cancel",
            metadata={"reason": reason} if reason else {}
        )

    def track_plan_upgrade(self, human_id: str, from_plan: str, to_plan: str) -> Dict[str, Any]:
        """
        Track plan upgrade.

        Args:
            human_id: Phone number
            from_plan: Previous plan
            to_plan: New plan

        Returns:
            Created event record
        """
        return self.track_stripe_event(
            human_id=human_id,
            event_type="plan_upgrade",
            metadata={"from_plan": from_plan, "to_plan": to_plan}
        )

    def track_trial_start(self, human_id: str, plan: str) -> Dict[str, Any]:
        """
        Track trial start.

        Args:
            human_id: Phone number
            plan: Plan on trial

        Returns:
            Created event record
        """
        return self.track_web_event(
            human_id=human_id,
            event_type="trial_start",
            metadata={"plan": plan}
        )

    # ==========================================================================
    # Query Methods
    # ==========================================================================

    def get_recent_events(self, human_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent events for a human."""
        return self.tracker.get_events(human_id, limit=limit)

    def get_conversion_context(self, human_id: str) -> Optional[Dict[str, Any]]:
        """Get conversion context for a human."""
        return self.tracker.get_conversion_context(human_id)

    def get_funnel_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get aggregate funnel statistics."""
        return self.tracker.get_funnel_stats(days)


# ==========================================================================
# API Handler Helper
# ==========================================================================

def create_api_handler() -> Dict[str, Any]:
    """
    Create a handler dict for use in API endpoints.

    Returns:
        Dict with handler functions for common operations
    """
    tracker = FunnelEventTracker()

    def handle_track_event(data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle POST /api/conversion/track"""
        event = FunnelEvent(
            human_id=data["human_id"],
            event_type=data["event_type"],
            source=EventSource(data.get("source", "api")),
            metadata=data.get("metadata", {}),
            session_id=data.get("session_id"),
            user_agent=data.get("user_agent"),
            ip_address=data.get("ip_address")
        )
        return tracker.track(event)

    def handle_get_context(human_id: str) -> Optional[Dict[str, Any]]:
        """Handle GET /api/conversion/{human_id}"""
        return tracker.get_conversion_context(human_id)

    def handle_get_stats(days: int = 30) -> Dict[str, Any]:
        """Handle GET /api/conversion/funnel/stats"""
        return tracker.get_funnel_stats(days)

    def handle_update_subscription(human_id: str, data: Dict[str, Any]) -> bool:
        """Handle PUT /api/conversion/{human_id}/subscription"""
        return tracker.tracker.update_subscription(
            human_id=human_id,
            status=data["status"],
            mrr_cents=data.get("mrr_cents", 0),
            subscription_start=data.get("subscription_start"),
            subscription_end=data.get("subscription_end"),
            conversion_trigger=data.get("conversion_trigger")
        )

    return {
        "track_event": handle_track_event,
        "get_context": handle_get_context,
        "get_stats": handle_get_stats,
        "update_subscription": handle_update_subscription,
        "close": tracker.close
    }


if __name__ == "__main__":
    # Test the module
    tracker = FunnelEventTracker()

    test_id = "+19999999999"

    # Test first touch
    result = tracker.track_first_touch(test_id, "twitter", referrer="https://twitter.com/kurult_ai")
    print(f"First touch: {result['event_id']}")

    # Test pricing view
    result = tracker.track_pricing_view(test_id, "pro_annual", session_id="sess_test")
    print(f"Pricing view: {result['event_id']}")

    # Test checkout start
    result = tracker.track_checkout_start(test_id, "pro_annual", session_id="sess_test")
    print(f"Checkout start: {result['event_id']}")

    # Test checkout complete
    result = tracker.track_checkout_complete(
        test_id, "pro_annual", 9500,
        stripe_event_id="evt_test123"
    )
    print(f"Checkout complete: {result['event_id']}")

    # Test update subscription
    tracker.tracker.update_subscription(
        human_id=test_id,
        status="pro_annual",
        mrr_cents=7900,
        conversion_trigger="Needed automated task review for team"
    )
    print("Updated subscription")

    # Get context
    context = tracker.get_conversion_context(test_id)
    print(f"Context: {context['subscription_status']}, MRR: {context['mrr_cents']}")

    # Get events
    events = tracker.get_recent_events(test_id)
    print(f"Events: {len(events)}")

    # Get stats
    stats = tracker.get_funnel_stats(30)
    print(f"Stats: {stats}")

    # Cleanup
    tracker.tracker.delete_conversion_data(test_id)
    print("Test data deleted")

    tracker.close()
