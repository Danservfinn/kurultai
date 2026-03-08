# Conversion Tracking Schema Documentation

**Version:** 1.0
**Date:** 2026-03-08
**Status:** Production Ready

## Overview

The Conversion Tracking System provides comprehensive funnel analytics and monetization context for Parse users. It combines Neo4j graph storage with file-based narrative memory to track user journeys from first touch through subscription.

## Architecture

```
┌─────────────────┐
│  Parse Website  │
│  /pricing, etc  │
└────────┬────────┘
         │ POST /api/conversion/track
         ▼
┌─────────────────┐     ┌──────────────────┐
│  Next.js API    │────▶│  Neo4j Graph     │
│  Endpoints      │     │  ConversionData  │
└─────────────────┘     └──────────────────┘
         │                       │
         │ sync                  │ enrich
         ▼                       ▼
┌─────────────────┐     ┌──────────────────┐
│  File-Based     │◀────│  Narrative       │
│  Memory (.md)   │     │  Context         │
└─────────────────┘     └──────────────────┘
```

## Neo4j Schema

### Node: ConversionContext

Stores per-human conversion and subscription data.

```cypher
(:ConversionContext {
  context_id: string,              // UUID, unique
  human_id: string,                // E.164 phone number
  first_touch_date: datetime,
  first_touch_source: string,      // "twitter", "direct", "github", etc.

  // Engagement metrics
  pricing_views: int,
  pricing_view_dates: [datetime],
  checkout_attempts: int,
  checkout_abort_reasons: [string],

  // Subscription data
  subscription_status: string,     // "none" | "trial" | "pro_monthly" | "pro_annual" | "enterprise" | "churned"
  subscription_start: datetime,
  subscription_end: datetime,
  mrr_cents: int,
  total_revenue_cents: int,

  // Preferences and triggers
  plan_preferences: map,           // {feature_priorities, price_sensitivity, etc.}
  conversion_trigger: string,      // What made them convert

  // Timestamps
  last_activity: datetime,
  created_at: datetime,
  updated_at: datetime
})
```

### Node: FunnelEvent

Individual events in the conversion funnel.

```cypher
(:FunnelEvent {
  event_id: string,                // UUID, unique
  human_id: string,
  event_type: string,              // See FUNNEL_EVENT_TYPES below
  event_date: datetime,
  metadata: map,                   // Event-specific data
  session_id: string,
  user_agent: string,
  ip_hash: string,                 // SHA256(first 16 chars) for privacy
  created_at: datetime
})
```

### Funnel Event Types

```python
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
```

### Relationships

```cypher
(:HumanProfile)-[:HAS_CONVERSION_CONTEXT]->(:ConversionContext)
(:HumanProfile)-[:GENERATED]->(:FunnelEvent)
(:ConversionContext)-[:TRIGGERED_BY]->(:FunnelEvent)
```

## File-Based Memory Format

Conversion context is appended to human profile markdown files:

```markdown
## Conversion Context
- **First Touch:** 2026-03-01 via Twitter
- **Pricing Views:** 5 (last: 2026-03-07)
- **Checkout Attempts:** 2 (aborted: "Need to think about it")
- **Subscription:** Pro Monthly ($79/mo) since 2026-03-08
- **Conversion Trigger:** "Team needed automated task review"
- **Plan Preferences:** Values time-saving features over cost

### Engagement Notes
- [2026-03-07] Asked about team pricing
- [2026-03-08] Converted to Pro Monthly
```

## API Endpoints

### POST /api/conversion/track

Track a funnel event.

**Request:**
```json
{
  "human_id": "+19194133445",
  "event_type": "pricing_view",
  "metadata": {
    "plan": "pro",
    "referral": "twitter"
  },
  "session_id": "sess_abc123",
  "user_agent": "Mozilla/5.0...",
  "ip_address": "192.168.1.1"
}
```

**Response:**
```json
{
  "event_id": "fe-64a1703c907c",
  "tracked": true,
  "context_updated": true
}
```

### GET /api/conversion/:human_id

Get conversion context for a human.

**Response:**
```json
{
  "context": {
    "context_id": "cc-5ab9efb2-e3e9-4088-ab95-2f855f59e5f2",
    "human_id": "+19194133445",
    "first_touch_date": "2026-03-01T10:30:00Z",
    "first_touch_source": "twitter",
    "pricing_views": 5,
    "checkout_attempts": 2,
    "subscription_status": "pro_monthly",
    "mrr_cents": 7900,
    "conversion_trigger": "Team needed automated task review",
    "last_activity": "2026-03-08T15:20:00Z",
    "_narrative": {
      "subscription_status": "Pro Monthly",
      "mrr_display": "$79/mo"
    }
  }
}
```

### GET /api/conversion/funnel/stats?days=30

Get aggregate funnel statistics.

**Query Parameters:**
- `days` (default: 30, range: 1-365) - Number of days to look back

**Response:**
```json
{
  "stats": {
    "total_leads": 1250,
    "converted": 87,
    "conversion_rate": 0.0696,
    "total_mrr_cents": 687300,
    "avg_pricing_views": 2.4,
    "events": [
      {"type": "first_touch", "count": 1250},
      {"type": "pricing_view", "count": 450},
      {"type": "checkout_start", "count": 120},
      {"type": "checkout_complete", "count": 87}
    ],
    "top_sources": [
      {
        "source": "twitter",
        "total": 450,
        "converted": 42,
        "conversion_rate": 0.0933
      },
      {
        "source": "github",
        "total": 320,
        "converted": 28,
        "conversion_rate": 0.0875
      }
    ]
  }
}
```

### PUT /api/conversion/:human_id/subscription

Update subscription status.

**Request:**
```json
{
  "status": "pro_monthly",
  "mrr_cents": 7900,
  "subscription_start": "2026-03-08T00:00:00Z",
  "conversion_trigger": "Team needed automated task review"
}
```

**Response:**
```json
{
  "updated": true,
  "context_id": "cc-5ab9efb2-e3e9-4088-ab95-2f855f59e5f2"
}
```

## Privacy & Security

### IP Hashing

IP addresses are hashed before storage using SHA256 (first 16 characters):

```python
ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:16]
```

### Data Deletion

Users can request deletion of all conversion data:

```python
tracker.delete_conversion_data(human_id)  # Neo4j
memory.remove_conversion_context(human_id)  # File-based
```

### Consent Gating

The "marketing" consent category gates promotional tracking:

```python
from neo4j_human_profile import HumanProfileStore

store = HumanProfileStore()
if store.check_consent(human_id, "marketing"):
    # Track marketing events
    pass
```

## Usage Examples

### Python Script Integration

```python
from neo4j_conversion_tracker import ConversionTracker
from conversion_context_memory import ConversionContextMemory

tracker = ConversionTracker()
memory = ConversionContextMemory()

# Track events
tracker.track_event(
    human_id="+19194133445",
    event_type="pricing_view",
    metadata={"plan": "pro"}
)

# Update subscription
tracker.update_subscription(
    human_id="+19194133445",
    status="pro_monthly",
    mrr_cents=7900,
    conversion_trigger="Team scaling"
)

# Sync to file-based memory
from conversion_context_memory import ConversionSync
sync = ConversionSync()
sync.sync_to_file("+19194133445")
sync.close()

# Get funnel stats
stats = tracker.get_funnel_stats(days=30)
print(f"Conversion rate: {stats['conversion_rate']:.1%}")

tracker.close()
```

### Next.js API Route Integration

```typescript
import { trackConversionEvent } from '@/lib/conversion';

// In your pricing page component
useEffect(() => {
  trackConversionEvent({
    human_id: user.phone,
    event_type: 'pricing_view',
    metadata: { plan: 'pro' }
  });
}, []);
```

## Testing

Run the integration test suite:

```bash
cd ~/.openclaw/agents/main/scripts
python3 test_conversion_tracking.py
```

Expected output: 8/8 tests passed

## Migration Guide

### From Existing Systems

1. **Export existing conversion data** to CSV/JSON
2. **Transform to ConversionContext format**
3. **Import using ConversionTracker**:
   ```python
   for user in existing_users:
       tracker.update_subscription(
           human_id=user.phone,
           status=user.subscription_tier,
           mrr_cents=user.mrr * 100
       )
   ```

### Backfilling Historical Data

```python
# For users who already have subscriptions
from datetime import datetime

tracker.update_subscription(
    human_id="+19194133445",
    status="pro_monthly",
    mrr_cents=7900,
    subscription_start=datetime(2026, 2, 1),  # Backfilled date
    conversion_trigger="Existing customer migration"
)
```

## Performance Considerations

- **Indexes:** All frequently queried fields are indexed
- **Funnel stats:** Aggregation query optimized with date filtering
- **File sync:** Lazy sync (only on explicit calls)
- **IP hashing:** Computed once per event

## Troubleshooting

### Common Issues

**Issue:** "Property key does not exist" warnings
- **Cause:** Optional fields not yet set on node
- **Solution:** Ignore warnings (expected behavior)

**Issue:** File sync fails
- **Cause:** Profile doesn't exist in Neo4j
- **Solution:** Create conversion context first with `track_event()`

**Issue:** Conversion rate > 100%
- **Cause:** Multiple conversion events per human
- **Solution:** Use `conversion_trigger` to identify primary conversion

## Support

For issues or questions:
- Check `test_conversion_tracking.py` for examples
- Review Neo4j logs: `tail -f /var/log/neo4j/neo4j.log`
- Contact: Kublai (temujin agent)

## Changelog

### v1.0 (2026-03-08)
- Initial release
- Neo4j schema with ConversionContext and FunnelEvent
- File-based narrative memory
- Next.js API endpoints
- Privacy features (IP hashing, deletion)
- Integration test suite
