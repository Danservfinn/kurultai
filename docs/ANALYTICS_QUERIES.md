# Parse Conversion Analytics Queries

## Event Schema

Events are tracked in the `AnalyticsEvent` Prisma model with the following structure:

```typescript
interface AnalyticsEvent {
  id: string
  eventType: EventType  // USER_CREATED | PRICING_PAGE_VIEW | CHECKOUT_STARTED | CHECKOUT_COMPLETED | SUBSCRIPTION_CREATED
  userId: string | null
  sessionId: string | null
  timestamp: DateTime
  metadata: Json  // { source?, tier?, amount?, currency?, plan?, billing? }
}
```

## Funnel Stages

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   USER_CREATED  │───▶│ PRICING_PAGE_VIEW│───▶│CHECKOUT_STARTED │───▶│CHECKOUT_COMPLETE│───▶│SUBSCRIPTION_CRD │
│   (signup)      │    │  (view pricing) │    │ (click checkout)│    │  (payment done) │    │  (active sub)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Core Analytics Queries

### 1. Daily Conversion Rate (Sign-up to Paid)

```cypher
// Neo4j equivalent - use Prisma query below
MATCH (signup:UserCreated)-[:CONVERTED_TO]->(sub:SubscriptionCreated)
WHERE signup.timestamp >= datetime().date() - duration({days: 7})
RETURN 
  date(signup.timestamp) as day,
  count(distinct signup) as signups,
  count(distinct sub) as conversions,
  round(100.0 * count(distinct sub) / count(distinct signup), 2) as conversion_rate
ORDER BY day DESC
```

**Prisma/SQL Query:**
```typescript
// Get daily conversion rates for last 30 days
const dailyConversion = await prisma.$queryRaw`
  SELECT 
    DATE("createdAt") as day,
    COUNT(DISTINCT CASE WHEN "eventType" = 'USER_CREATED' THEN "userId" END) as signups,
    COUNT(DISTINCT CASE WHEN "eventType" = 'SUBSCRIPTION_CREATED' THEN "userId" END) as conversions,
    ROUND(
      100.0 * COUNT(DISTINCT CASE WHEN "eventType" = 'SUBSCRIPTION_CREATED' THEN "userId" END) / 
      NULLIF(COUNT(DISTINCT CASE WHEN "eventType" = 'USER_CREATED' THEN "userId" END), 0),
      2
    ) as conversion_rate
  FROM "AnalyticsEvent"
  WHERE "createdAt" >= NOW() - INTERVAL '30 days'
  GROUP BY DATE("createdAt")
  ORDER BY day DESC
`
```

### 2. Funnel Drop-off Analysis

```typescript
// Get conversion rates between each funnel stage for last 7 days
const funnelMetrics = await prisma.$queryRaw`
  WITH funnel AS (
    SELECT 
      "userId",
      MAX(CASE WHEN "eventType" = 'USER_CREATED' THEN 1 ELSE 0 END) as reached_signup,
      MAX(CASE WHEN "eventType" = 'PRICING_PAGE_VIEW' THEN 1 ELSE 0 END) as reached_pricing,
      MAX(CASE WHEN "eventType" = 'CHECKOUT_STARTED' THEN 1 ELSE 0 END) as reached_checkout,
      MAX(CASE WHEN "eventType" = 'CHECKOUT_COMPLETED' THEN 1 ELSE 0 END) as reached_payment,
      MAX(CASE WHEN "eventType" = 'SUBSCRIPTION_CREATED' THEN 1 ELSE 0 END) as reached_subscription
    FROM "AnalyticsEvent"
    WHERE "createdAt" >= NOW() - INTERVAL '7 days'
    GROUP BY "userId"
  )
  SELECT
    SUM(reached_signup) as total_signups,
    SUM(reached_pricing) as pricing_views,
    SUM(reached_checkout) as checkouts_started,
    SUM(reached_payment) as payments_completed,
    SUM(reached_subscription) as subscriptions_created,
    ROUND(100.0 * SUM(reached_pricing) / NULLIF(SUM(reached_signup), 0), 2) as signup_to_pricing_rate,
    ROUND(100.0 * SUM(reached_checkout) / NULLIF(SUM(reached_pricing), 0), 2) as pricing_to_checkout_rate,
    ROUND(100.0 * SUM(reached_payment) / NULLIF(SUM(reached_checkout), 0), 2) as checkout_to_payment_rate,
    ROUND(100.0 * SUM(reached_subscription) / NULLIF(SUM(reached_payment), 0), 2) as payment_to_sub_rate,
    ROUND(100.0 * SUM(reached_subscription) / NULLIF(SUM(reached_signup), 0), 2) as overall_conversion_rate
  FROM funnel
`
```

### 3. Revenue by Tier

```typescript
// Get subscription counts and revenue by tier for last 30 days
const revenueByTier = await prisma.$queryRaw`
  SELECT 
    CAST(e."metadata"->>'tierId' AS TEXT) as tier,
    COUNT(DISTINCT e."userId") as subscribers,
    CAST(e."metadata"->>'amount' AS DECIMAL) as amount,
    SUM(CAST(e."metadata"->>'amount' AS DECIMAL)) as total_revenue
  FROM "AnalyticsEvent" e
  WHERE e."eventType" = 'SUBSCRIPTION_CREATED'
    AND e."createdAt" >= NOW() - INTERVAL '30 days'
  GROUP BY tier, amount
  ORDER BY total_revenue DESC
`
```

### 4. Day-over-Day Conversion Change (for Alerts)

```typescript
// Calculate day-over-day conversion rate change
const dodConversion = await prisma.$queryRaw`
  WITH daily_rates AS (
    SELECT 
      DATE("createdAt") as day,
      COUNT(DISTINCT CASE WHEN "eventType" = 'USER_CREATED' THEN "userId" END) as signups,
      COUNT(DISTINCT CASE WHEN "eventType" = 'SUBSCRIPTION_CREATED' THEN "userId" END) as conversions,
      ROUND(
        100.0 * COUNT(DISTINCT CASE WHEN "eventType" = 'SUBSCRIPTION_CREATED' THEN "userId" END) / 
        NULLIF(COUNT(DISTINCT CASE WHEN "eventType" = 'USER_CREATED' THEN "userId" END), 0),
        2
      ) as conversion_rate
    FROM "AnalyticsEvent"
    WHERE "createdAt" >= NOW() - INTERVAL '14 days'
    GROUP BY DATE("createdAt")
  ),
  with_previous AS (
    SELECT 
      day,
      conversion_rate,
      LAG(conversion_rate) OVER (ORDER BY day) as previous_rate
    FROM daily_rates
  )
  SELECT 
    day,
    conversion_rate,
    previous_rate,
    ROUND(conversion_rate - previous_rate, 2) as rate_change,
    ROUND(
      100.0 * (conversion_rate - previous_rate) / NULLIF(previous_rate, 0),
      2
    ) as percent_change
  FROM with_previous
  WHERE previous_rate IS NOT NULL
  ORDER BY day DESC
  LIMIT 1
`
```

### 5. Pricing Page Views by Source/UTM

```typescript
// Track which sources drive the most pricing page engagement
const pricingBySource = await prisma.$queryRaw`
  SELECT 
    CAST("metadata"->>'source' AS TEXT) as source,
    COUNT(*) as views,
    COUNT(DISTINCT "userId") as unique_users
  FROM "AnalyticsEvent"
  WHERE "eventType" = 'PRICING_PAGE_VIEW'
    AND "createdAt" >= NOW() - INTERVAL '30 days'
  GROUP BY source
  ORDER BY views DESC
`
```

### 6. Checkout Abandonment Rate

```typescript
// Users who started checkout but didn't complete
const abandonmentQuery = await prisma.$queryRaw`
  WITH checkout_users AS (
    SELECT DISTINCT "userId"
    FROM "AnalyticsEvent"
    WHERE "eventType" = 'CHECKOUT_STARTED'
      AND "createdAt" >= NOW() - INTERVAL '7 days'
  ),
  completed_users AS (
    SELECT DISTINCT "userId"
    FROM "AnalyticsEvent"
    WHERE "eventType" = 'CHECKOUT_COMPLETED'
      AND "createdAt" >= NOW() - INTERVAL '7 days'
  )
  SELECT
    (SELECT COUNT(*) FROM checkout_users) as checkouts_started,
    (SELECT COUNT(*) FROM completed_users) as checkouts_completed,
    (SELECT COUNT(*) FROM checkout_users) - (SELECT COUNT(*) FROM completed_users) as abandoned,
    ROUND(
      100.0 * (
        (SELECT COUNT(*) FROM checkout_users) - (SELECT COUNT(*) FROM completed_users)
      ) / NULLIF((SELECT COUNT(*) FROM checkout_users), 0),
      2
    ) as abandonment_rate
`
```

## Alert Queries

### Conversion Drop Alert (>20% day-over-day decrease)

```typescript
async function checkConversionDropAlert(): Promise<Alert | null> {
  const result = await prisma.$queryRaw`
    WITH daily_rates AS (
      SELECT 
        DATE("createdAt") as day,
        COUNT(DISTINCT CASE WHEN "eventType" = 'USER_CREATED' THEN "userId" END) as signups,
        COUNT(DISTINCT CASE WHEN "eventType" = 'SUBSCRIPTION_CREATED' THEN "userId" END) as conversions,
        ROUND(
          100.0 * COUNT(DISTINCT CASE WHEN "eventType" = 'SUBSCRIPTION_CREATED' THEN "userId" END) / 
          NULLIF(COUNT(DISTINCT CASE WHEN "eventType" = 'USER_CREATED' THEN "userId" END), 0),
          4
        ) as conversion_rate
      FROM "AnalyticsEvent"
      WHERE "createdAt" >= NOW() - INTERVAL '3 days'
      GROUP BY DATE("createdAt")
      ORDER BY day DESC
      LIMIT 2
    )
    SELECT 
      MAX(day) as current_day,
      MAX(conversion_rate) FILTER (WHERE day = (SELECT MAX(day) FROM daily_rates)) as current_rate,
      MAX(conversion_rate) FILTER (WHERE day = (SELECT MIN(day) FROM daily_rates)) as previous_rate,
      ROUND(
        100.0 * (
          MAX(conversion_rate) FILTER (WHERE day = (SELECT MIN(day) FROM daily_rates)) - 
          MAX(conversion_rate) FILTER (WHERE day = (SELECT MAX(day) FROM daily_rates))
        ) / NULLIF(MAX(conversion_rate) FILTER (WHERE day = (SELECT MIN(day) FROM daily_rates)), 0),
        2
      ) as drop_percentage
    FROM daily_rates
  `

  const alert = result[0] as any
  if (alert.drop_percentage && alert.drop_percentage > 20) {
    return {
      type: 'CONVERSION_DROP',
      severity: 'HIGH',
      message: `Conversion rate dropped ${alert.drop_percentage}% day-over-day`,
      currentRate: alert.current_rate,
      previousRate: alert.previous_rate,
      timestamp: new Date()
    }
  }
  return null
}
```

## Dashboard Queries

### Summary Metrics (Last 7 Days)

```typescript
const summaryMetrics = await prisma.$queryRaw`
  SELECT
    COUNT(DISTINCT CASE WHEN "eventType" = 'USER_CREATED' THEN "userId" END) as total_signups,
    COUNT(DISTINCT CASE WHEN "eventType" = 'PRICING_PAGE_VIEW' THEN "userId" END) as pricing_views,
    COUNT(DISTINCT CASE WHEN "eventType" = 'CHECKOUT_STARTED' THEN "userId" END) as checkouts_started,
    COUNT(DISTINCT CASE WHEN "eventType" = 'SUBSCRIPTION_CREATED' THEN "userId" END) as new_subscribers,
    ROUND(
      100.0 * COUNT(DISTINCT CASE WHEN "eventType" = 'SUBSCRIPTION_CREATED' THEN "userId" END) / 
      NULLIF(COUNT(DISTINCT CASE WHEN "eventType" = 'USER_CREATED' THEN "userId" END), 0),
      2
    ) as overall_conversion_rate,
    SUM(CAST("metadata"->>'amount' AS DECIMAL)) FILTER (WHERE "eventType" = 'SUBSCRIPTION_CREATED') as total_revenue
  FROM "AnalyticsEvent"
  WHERE "createdAt" >= NOW() - INTERVAL '7 days'
`
```

### Conversion Trend (Last 30 Days)

```typescript
const conversionTrend = await prisma.$queryRaw`
  SELECT 
    DATE("createdAt") as date,
    COUNT(DISTINCT CASE WHEN "eventType" = 'USER_CREATED' THEN "userId" END) as signups,
    COUNT(DISTINCT CASE WHEN "eventType" = 'SUBSCRIPTION_CREATED' THEN "userId" END) as conversions,
    ROUND(
      100.0 * COUNT(DISTINCT CASE WHEN "eventType" = 'SUBSCRIPTION_CREATED' THEN "userId" END) / 
      NULLIF(COUNT(DISTINCT CASE WHEN "eventType" = 'USER_CREATED' THEN "userId" END), 0),
      2
    ) as conversion_rate
  FROM "AnalyticsEvent"
  WHERE "createdAt" >= NOW() - INTERVAL '30 days'
  GROUP BY DATE("createdAt")
  ORDER BY date ASC
`
```

## Implementation Notes

1. **Event Consistency**: Always use the same `userId` for events from the same user
2. **Session Tracking**: Use `sessionId` for anonymous events (pricing page views before signup)
3. **Metadata Standardization**: Use consistent keys in metadata:
   - `source`: Traffic source (organic, paid, referral, etc.)
   - `tier`: Subscription tier ID
   - `amount`: Revenue amount in cents
   - `currency`: Currency code (USD, EUR, etc.)
   - `billing`: monthly or annual
4. **Timezone**: All timestamps are in UTC
5. **Idempotency**: Event logging should be idempotent where possible
