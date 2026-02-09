/**
 * Subscription System Migration
 *
 * Creates the SUBSCRIBES_TO relationship schema for cross-agent event subscriptions.
 * This enables agents to subscribe to events from other agents with filtering criteria.
 *
 * Relationship Pattern:
 * (:Agent)-[s:SUBSCRIBES_TO {topic, filter, created_at}]->(:Agent)
 *
 * Workflow:
 * 1. Subscriber agent creates subscription to target agent for specific topic
 * 2. When target agent publishes event matching topic
 * 3. NotificationDispatcher filters by subscription criteria
 * 4. Subscriber receives notification via signed message
 */

// Agent node constraint (if not exists)
CREATE CONSTRAINT agent_id IF NOT EXISTS FOR (a:Agent) REQUIRE a.id IS UNIQUE;

// Subscription relationship constraints
CREATE CONSTRAINT subscription_id IF NOT EXISTS FOR ()-[s:SUBSCRIBES_TO]-() REQUIRE s.id IS UNIQUE;

// Indexes for efficient subscription queries
CREATE INDEX subscription_topic IF NOT EXISTS FOR ()-[s:SUBSCRIBES_TO]-() ON (s.topic);
CREATE INDEX subscription_filter IF NOT EXISTS FOR ()-[s:SUBSCRIBES_TO]-() ON (s.filter);
CREATE INDEX subscription_created_at IF NOT EXISTS FOR ()-[s:SUBSCRIBES_TO]-() ON (s.created_at);
CREATE INDEX subscription_subscriber IF NOT EXISTS FOR ()-[s:SUBSCRIBES_TO]-() ON (s.subscriber_id);
CREATE INDEX subscription_target IF NOT EXISTS FOR ()-[s:SUBSCRIBES_TO]-() ON (s.target_id);

// Composite index for topic + subscriber lookups
CREATE INDEX subscription_topic_subscriber IF NOT EXISTS FOR ()-[s:SUBSCRIBES_TO]-() ON (s.topic, s.subscriber_id);

// NotificationLog node for audit trail
CREATE CONSTRAINT notification_log_id IF NOT EXISTS FOR (n:NotificationLog) REQUIRE n.id IS UNIQUE;
CREATE INDEX notification_log_topic IF NOT EXISTS FOR (n:NotificationLog) ON (n.topic);
CREATE INDEX notification_log_created_at IF NOT EXISTS FOR (n:NotificationLog) ON (n.created_at);
CREATE INDEX notification_log_status IF NOT EXISTS FOR (n:NotificationLog) ON (n.status);

// Relationship patterns (documented for reference):
// (:Agent)-[:SUBSCRIBES_TO {id, topic, filter, created_at}]->(:Agent)
// (:Agent)-[:PUBLISHED {topic, payload, timestamp}]->(:NotificationLog)
// (:NotificationLog)-[:DELIVERED_TO]->(:Agent)
// (:NotificationLog)-[:FAILED_DELIVERY {reason}]->(:Agent)
