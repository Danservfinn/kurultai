# Implementation Plan: Conversion Context & Preference Tracking Schema

**Date:** 2026-03-08
**Priority:** HIGH - Critical for Parse monetization optimization
**Status:** Ready for execution

## Objective

Build comprehensive conversion context and preference tracking for Parse users, extending the existing human profile system with monetization funnel data, subscription tracking, and conversion analytics.

## Current State Assessment

**✅ Already Exists:**
- `neo4j_conversion_tracker.py` - Complete Neo4j CRUD operations for ConversionContext and FunnelEvent
- Schema constraints and indexes for conversion tracking
- Privacy features (IP hashing, deletion, anonymization)
- Human profile system (Neo4j + file-based memory)
- Parse GitHub API structure at `/Users/kublai/projects/parse-github/src/app/api/`

**❌ Missing Components:**
1. File-based memory extension for conversion context narrative
2. Conversion context section in human profile markdown files
3. Funnel event tracker API endpoints (Next.js routes)
4. Comprehensive documentation
5. Integration between conversion tracker and human profile memory

---

## Phase 0: Prerequisites Verification

**Duration:** 5 minutes
**Dependencies:** None
**Gate Depth:** NONE

### Task 0.1: Verify Existing Schema
- Run `python3 ~/.openclaw/agents/main/scripts/neo4j_conversion_tracker.py init`
- Confirm Neo4j schema initialization succeeds
- Verify constraints and indexes exist

### Task 0.2: Test Existing CRUD Operations
- Run existing test in `neo4j_conversion_tracker.py`
- Verify event tracking works
- Verify conversion context creation works

### Exit Criteria Phase 0
- [ ] Schema initialization returns "Schema initialized successfully"
- [ ] Test event creation succeeds without errors
- [ ] Conversion context retrieval returns valid data

---

## Phase 1: File-Based Memory Extension

**Duration:** 30 minutes
**Dependencies:** Phase 0
**Gate Depth:** LIGHT

### Task 1.1: Extend `human_profile_memory.py` for Conversion Context

**File:** `~/.openclaw/agents/main/scripts/human_profile_memory.py`

**Changes Required:**
1. Add `_format_conversion_context()` method to format conversion data for markdown
2. Add `_parse_conversion_context()` method to parse conversion section from markdown
3. Modify `write_profile()` to include conversion context section
4. Modify `_parse_profile()` to extract conversion context
5. Add `update_conversion_context()` method

**Conversion Context Section Format:**
```markdown
## Conversion Context
- **First Touch:** 2026-03-01 via Twitter
- **Pricing Views:** 5 (last: 2026-03-07)
- **Checkout Attempts:** 2
- **Subscription:** Pro Monthly ($79/mo) since 2026-03-08
- **Conversion Trigger:** "Needed automated task review for team"
- **Plan Preferences:** Values time-saving features over cost
```

### Task 1.2: Create `conversion_context_memory.py`

**File:** `~/.openclaw/agents/main/scripts/conversion_context_memory.py`

**Purpose:** Dedicated module for conversion context narrative storage

**Key Methods:**
- `write_conversion_context(human_id, context_data)` - Write conversion narrative
- `read_conversion_context(human_id)` - Read conversion narrative
- `sync_from_neo4j(human_id)` - Sync from Neo4j to file
- `enrich_with_narrative(human_id, context)` - Add narrative to Neo4j data

**Data Format:**
```python
{
    "first_touch": {"date": "2026-03-01", "source": "twitter"},
    "pricing_views": {"count": 5, "last_viewed": "2026-03-07"},
    "checkout_attempts": 2,
    "abort_reasons": ["Need to think about it", "Too expensive"],
    "subscription": {
        "status": "pro_monthly",
        "start_date": "2026-03-08",
        "mrr_cents": 7900
    },
    "conversion_trigger": "Team needed automated task review",
    "plan_preferences": {
        "feature_priorities": ["automation", "review"],
        "price_sensitivity": "low",
        "decision_factors": ["time_saving", "team_coordination"]
    }
}
```

### Task 1.3: Update Profile Sync to Include Conversion Context

**File:** `~/.openclaw/agents/main/scripts/human_profile_memory.py`

**Modify `ProfileSync` class:**
- Add conversion context to `get_enriched_profile()`
- Add `sync_conversion_context()` method
- Update `sync_to_file()` to include conversion data

### Exit Criteria Phase 1
- [ ] `human_profile_memory.py` compiles without errors
- [ ] `conversion_context_memory.py` creates successfully
- [ ] Writing a profile includes conversion context section
- [ ] Reading a profile parses conversion context correctly

---

## Phase 2: API Endpoints (Parse GitHub)

**Duration:** 45 minutes
**Dependencies:** Phase 1
**Gate Depth:** STANDARD

### Task 2.1: Create Conversion Tracking API Route

**File:** `/Users/kublai/projects/parse-github/src/app/api/conversion/track/route.ts`

**Endpoint:** `POST /api/conversion/track`

**Request Body:**
```typescript
{
  human_id: string;          // E.164 phone number
  event_type: string;        // pricing_view, checkout_start, etc.
  metadata?: Record<string, any>;
  session_id?: string;
  user_agent?: string;
  ip_address?: string;
}
```

**Response:**
```typescript
{
  event_id: string;
  tracked: boolean;
  context_updated: boolean;
}
```

**Implementation:**
- Import `ConversionTracker` from Neo4j scripts
- Validate event type against `FUNNEL_EVENT_TYPES`
- Hash IP address before storage
- Call `tracker.track_event()`
- Sync conversion context to file-based memory
- Return event ID

### Task 2.2: Create Get Conversion Context API

**File:** `/Users/kublai/projects/parse-github/src/app/api/conversion/[human_id]/route.ts`

**Endpoint:** `GET /api/conversion/{human_id}`

**Response:**
```typescript
{
  context_id: string;
  human_id: string;
  first_touch_date: string;
  first_touch_source: string;
  pricing_views: number;
  checkout_attempts: number;
  subscription_status: string;
  mrr_cents: number;
  conversion_trigger?: string;
  plan_preferences: Record<string, any>;
  last_activity: string;
}
```

**Implementation:**
- Call `tracker.get_conversion_context()`
- Enrich with file-based narrative
- Return combined data

### Task 2.3: Create Funnel Stats API

**File:** `/Users/kublai/projects/parse-github/src/app/api/conversion/funnel/stats/route.ts`

**Endpoint:** `GET /api/conversion/funnel/stats?days=30`

**Query Params:**
- `days` (default: 30) - Number of days to look back

**Response:**
```typescript
{
  total_leads: number;
  converted: number;
  conversion_rate: number;
  total_mrr_cents: number;
  avg_pricing_views: number;
  events: Array<{
    type: string;
    count: number;
  }>;
  top_sources: Array<{
    source: string;
    total: number;
    converted: number;
    conversion_rate: number;
  }>;
}
```

**Implementation:**
- Call `tracker.get_funnel_stats()`
- Call `tracker.get_top_conversion_sources()`
- Combine and return

### Task 2.4: Create Update Subscription API

**File:** `/Users/kublai/projects/parse-github/src/app/api/conversion/[human_id]/subscription/route.ts`

**Endpoint:** `PUT /api/conversion/{human_id}/subscription`

**Request Body:**
```typescript
{
  status: string;            // trial, pro_monthly, pro_annual, etc.
  mrr_cents?: number;
  subscription_start?: string;
  subscription_end?: string;
  conversion_trigger?: string;
}
```

**Response:**
```typescript
{
  updated: boolean;
  context_id: string;
}
```

**Implementation:**
- Validate subscription status
- Call `tracker.update_subscription()`
- Sync to file-based memory
- Return result

### Task 2.5: Add Privacy/Delete API

**File:** `/Users/kublai/projects/parse-github/src/app/api/conversion/[human_id]/delete/route.ts`

**Endpoint:** `DELETE /api/conversion/{human_id}`

**Response:**
```typescript
{
  deleted: boolean;
  contexts_deleted: number;
  events_deleted: number;
}
```

**Implementation:**
- Call `tracker.delete_conversion_data()`
- Remove conversion context section from file-based memory
- Return deletion counts

### Exit Criteria Phase 2
- [ ] All API routes compile without TypeScript errors
- [ ] `POST /api/conversion/track` returns event_id
- [ ] `GET /api/conversion/{human_id}` returns context data
- [ ] `GET /api/conversion/funnel/stats` returns aggregate metrics
- [ ] `PUT /api/conversion/{human_id}/subscription` updates subscription
- [ ] `DELETE /api/conversion/{human_id}` removes all conversion data

---

## Phase 3: Integration & Testing

**Duration:** 30 minutes
**Dependencies:** Phase 2
**Gate Depth:** STANDARD

### Task 3.1: Create Integration Test Script

**File:** `~/.openclaw/agents/main/scripts/test_conversion_tracking.py`

**Test Cases:**
1. Track first touch event
2. Track pricing view
3. Track checkout start
4. Update subscription to pro_monthly
5. Verify conversion context creation
6. Verify file-based memory sync
7. Test funnel stats aggregation
8. Test data deletion

### Task 3.2: Test API Endpoints Locally

**Actions:**
- Start Parse dev server: `cd /Users/kublai/projects/parse-github && npm run dev`
- Run curl tests against each endpoint
- Verify responses match expected format
- Check file-based memory for conversion context

### Task 3.3: Verify Privacy Features

**Tests:**
- Confirm IP addresses are hashed (first 16 chars of SHA256)
- Test data deletion removes all traces
- Test anonymization removes PII
- Verify consent category gating for "marketing"

### Exit Criteria Phase 3
- [ ] Integration test script passes all 8 test cases
- [ ] API endpoints return valid responses
- [ ] File-based memory contains conversion context section
- [ ] Privacy features verified (IP hash, deletion, anonymization)

---

## Phase 4: Documentation

**Duration:** 20 minutes
**Dependencies:** Phase 3
**Gate Depth:** LIGHT

### Task 4.1: Create Schema Documentation

**File:** `~/.openclaw/agents/main/docs/conversion-tracking-schema.md`

**Sections:**
1. Overview
2. Neo4j Schema Definition
3. File-Based Memory Format
4. API Endpoint Reference
5. Privacy & Security Considerations
6. Usage Examples
7. Migration Guide

### Task 4.2: Create API Usage Guide

**File:** `/Users/kublai/projects/parse-github/docs/conversion-api.md`

**Sections:**
1. Quick Start
2. Authentication & Authorization
3. Event Tracking Examples
4. Retrieving Conversion Context
5. Funnel Analytics Queries
6. Subscription Management
7. Data Deletion Requests

### Task 4.3: Update Main ARCHITECTURE.md

**File:** `/Users/kublai/projects/parse-github/ARCHITECTURE.md`

**Add Section:** "Conversion Tracking System"
- Schema overview
- API routes
- Integration points
- Data flow diagram

### Exit Criteria Phase 4
- [ ] Schema documentation created with all sections
- [ ] API usage guide includes code examples
- [ ] ARCHITECTURE.md updated with conversion tracking section

---

## Phase 5: Deployment & Verification

**Duration:** 15 minutes
**Dependencies:** Phase 4
**Gate Depth:** DEEP

### Task 5.1: Deploy to Railway Production

**Actions:**
- Commit changes to Parse GitHub repo
- Push to main branch
- Verify Railway auto-deployment
- Check production logs for errors

### Task 5.2: Smoke Test Production API

**Tests:**
- Track a test event via production API
- Verify conversion context creation
- Check funnel stats endpoint
- Test subscription update
- Verify data deletion

### Task 5.3: Create Rollback Plan

**Document:**
- How to revert API changes
- Neo4j schema rollback if needed
- File-based memory recovery
- Emergency contacts

### Exit Criteria Phase 5
- [ ] Railway deployment succeeds
- [ ] Production API smoke tests pass
- [ ] Rollback plan documented
- [ ] No errors in production logs

---

## Success Criteria

**Overall Requirements Met:**
- ✅ Neo4j ConversionContext and FunnelEvent nodes operational
- ✅ File-based memory extended with conversion context narrative
- ✅ API endpoints functional (track, get context, stats, update subscription, delete)
- ✅ Privacy features implemented (IP hashing, deletion, anonymization)
- ✅ Comprehensive documentation created
- ✅ Integration tests passing
- ✅ Deployed to production

**Monetization Optimization Enabled:**
- Track first touch sources to identify high-value channels
- Monitor pricing page views for purchase intent
- Analyze checkout abandonment for friction points
- Measure conversion triggers for messaging optimization
- Aggregate funnel metrics for business intelligence

---

## Estimated Total Duration

**Phase 0:** 5 minutes (prerequisites)
**Phase 1:** 30 minutes (file-based memory)
**Phase 2:** 45 minutes (API endpoints)
**Phase 3:** 30 minutes (integration & testing)
**Phase 4:** 20 minutes (documentation)
**Phase 5:** 15 minutes (deployment & verification)

**Total:** ~2 hours 25 minutes

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Neo4j schema conflicts | Low | High | Phase 0 verification checks constraints |
| API TypeScript errors | Medium | Medium | Phase 3 includes compilation check |
| File-based memory sync issues | Low | Medium | Phase 3 integration tests |
| Production deployment failure | Low | High | Phase 5 includes rollback plan |
| Privacy consent violations | Low | High | Phase 3 includes privacy verification |

---

## Notes

- The Neo4j schema (`neo4j_conversion_tracker.py`) is already complete and production-ready
- File-based memory extends existing `human_profile_memory.py` patterns
- API endpoints follow Parse's existing Next.js route conventions
- Privacy features are implemented at the Neo4j level (IP hashing) and API level (consent checks)
- This system enables data-driven monetization optimization without compromising user privacy
