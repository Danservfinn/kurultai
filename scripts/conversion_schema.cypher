// Conversion Tracking Schema for Neo4j
// Version: 1.0
// Date: 2026-03-08
//
// This file defines the schema for conversion tracking and funnel analytics.
// Run with: cat conversion_schema.cypher | cypher-shell -u neo4j -p <password>
// Or via Python: python3 neo4j_conversion_tracker.py init

// ============================================================================
// CONSTRAINTS
// ============================================================================

// Unique identifiers
CREATE CONSTRAINT conversion_context_id_unique IF NOT EXISTS
FOR (c:ConversionContext) REQUIRE c.context_id IS UNIQUE;

CREATE CONSTRAINT funnel_event_id_unique IF NOT EXISTS
FOR (f:FunnelEvent) REQUIRE f.event_id IS UNIQUE;

// ============================================================================
// INDEXES
// ============================================================================

// Fast lookups by human_id
CREATE INDEX conversion_context_human_id_idx IF NOT EXISTS
FOR (c:ConversionContext) ON (c.human_id);

CREATE INDEX funnel_event_human_id_idx IF NOT EXISTS
FOR (f:FunnelEvent) ON (f.human_id);

// Filter by event type for analytics
CREATE INDEX funnel_event_type_idx IF NOT EXISTS
FOR (f:FunnelEvent) ON (f.event_type);

// Time-based queries for funnel stats
CREATE INDEX funnel_event_date_idx IF NOT EXISTS
FOR (f:FunnelEvent) ON (f.event_date);

// Subscription status filtering
CREATE INDEX conversion_context_subscription_idx IF NOT EXISTS
FOR (c:ConversionContext) ON (c.subscription_status);

// First touch source analytics
CREATE INDEX conversion_context_source_idx IF NOT EXISTS
FOR (c:ConversionContext) ON (c.first_touch_source);

// ============================================================================
// NODE LABELS & PROPERTIES
// ============================================================================

// (:ConversionContext) - Stores per-human conversion and subscription data
//
// Properties:
//   context_id: UUID, unique identifier
//   human_id: E.164 phone number (e.g., "+19194133445")
//   first_touch_date: datetime of first interaction
//   first_touch_source: string ("twitter", "direct", "github", etc.)
//   pricing_views: int, count of pricing page views
//   pricing_view_dates: list of datetime
//   checkout_attempts: int, count of checkout starts
//   checkout_abort_reasons: list of string
//   subscription_status: string ("none" | "trial" | "pro_monthly" | "pro_annual" | "enterprise" | "churned")
//   subscription_start: datetime
//   subscription_end: datetime
//   mrr_cents: int, monthly recurring revenue in cents
//   total_revenue_cents: int, lifetime revenue in cents
//   plan_preferences: map (feature_priorities, price_sensitivity, decision_factors)
//   conversion_trigger: string, what made them convert
//   last_activity: datetime
//   created_at: datetime
//   updated_at: datetime

// (:FunnelEvent) - Individual events in the conversion funnel
//
// Properties:
//   event_id: UUID, unique identifier (prefix "fe-")
//   human_id: E.164 phone number
//   event_type: string (see FUNNEL_EVENT_TYPES below)
//   event_date: datetime
//   metadata: map, event-specific data
//   session_id: string, browser session identifier
//   user_agent: string, browser user agent
//   ip_hash: string, SHA256(first 16 chars) for privacy
//   created_at: datetime

// ============================================================================
// FUNNEL EVENT TYPES
// ============================================================================
//
// first_touch        - First interaction with Parse
// pricing_view       - Viewed pricing page
// signup_start       - Started signup flow
// signup_complete    - Completed signup
// checkout_start     - Started checkout
// checkout_complete  - Completed purchase
// checkout_abort     - Abandoned checkout
// subscription_cancel - Cancelled subscription
// plan_upgrade       - Upgraded plan
// plan_downgrade     - Downgraded plan
// trial_start        - Started trial
// trial_end          - Trial ended
// feature_view       - Viewed a feature page
// demo_request       - Requested a demo
// support_contact    - Contacted support

// ============================================================================
// RELATIONSHIPS
// ============================================================================
//
// (:HumanProfile)-[:HAS_CONVERSION_CONTEXT]->(:ConversionContext)
//   Links a human profile to their conversion context
//
// (:HumanProfile)-[:GENERATED]->(:FunnelEvent)
//   Links a human profile to events they generated
//
// (:ConversionContext)-[:TRIGGERED_BY]->(:FunnelEvent)
//   Links conversion to the event that triggered it (checkout_complete)

// ============================================================================
// SAMPLE QUERIES
// ============================================================================

// Get conversion context for a human
// MATCH (cc:ConversionContext {human_id: $human_id}) RETURN cc

// Get all funnel events for a human
// MATCH (fe:FunnelEvent {human_id: $human_id})
// RETURN fe ORDER BY fe.event_date DESC LIMIT 50

// Get funnel stats for last 30 days
// MATCH (fe:FunnelEvent)
// WHERE fe.event_date > datetime() - duration('P30D')
// RETURN fe.event_type AS type, count(fe) AS count
// ORDER BY count DESC

// Get conversion rate by source
// MATCH (cc:ConversionContext)
// WHERE cc.first_touch_source IS NOT NULL
// WITH cc.first_touch_source AS source,
//      count(cc) AS total,
//      sum(CASE WHEN cc.subscription_status IN ['pro_monthly', 'pro_annual', 'enterprise']
//               THEN 1 ELSE 0 END) AS converted
// RETURN source, total, converted,
//        CASE WHEN total > 0 THEN toFloat(converted) / toFloat(total) ELSE 0 END AS rate
// ORDER BY converted DESC

// Delete all conversion data for a human (GDPR)
// MATCH (cc:ConversionContext {human_id: $human_id})
// OPTIONAL MATCH (cc)-[r1]-()
// DELETE r1, cc
// WITH 1 AS _
// MATCH (fe:FunnelEvent {human_id: $human_id})
// OPTIONAL MATCH (fe)-[r2]-()
// DELETE r2, fe

// ============================================================================
// SCHEMA VERIFICATION
// ============================================================================

// After running this schema, verify with:
// SHOW CONSTRAINTS
// SHOW INDEXES
