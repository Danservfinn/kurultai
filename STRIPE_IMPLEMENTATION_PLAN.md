# Stripe Integration Implementation Plan

## Task Requirements
1. Stripe Checkout integration (Next.js) ✅ Already exists
2. 4 pricing tiers: Free ($0), Pro ($19/mo), Team ($99/mo), Enterprise ($499/mo) ⚠️ Needs update
3. Webhook handlers for subscription events ✅ Already exists
4. Database schema for subscriptions + usage tracking ✅ Already exists
5. Usage limit enforcement (5/month free, 100/month Pro, etc.) ⚠️ Needs update

## Current State Analysis

### What's Already Implemented
- ✅ Stripe client initialization (`src/lib/stripe.ts`)
- ✅ Checkout session creation (`src/app/api/stripe/checkout/subscription/route.ts`)
- ✅ Webhook handlers (`src/app/api/stripe/webhook/route.ts`)
- ✅ Subscription model in Prisma schema
- ✅ Credits service with reserve-confirm-cancel pattern
- ✅ Pricing page UI (`src/app/pricing/page.tsx`)
- ✅ One-time credit pack purchases

### What Needs to be Updated

#### 1. Pricing Configuration (`src/lib/pricing.ts`)
Update `SUBSCRIPTION_TIERS` to match requirements:
- **Free**: $0/mo, 5 analyses/month
- **Pro**: $19/mo, 100 analyses/month
- **Team**: $99/mo, 500 analyses/month
- **Enterprise**: $499/mo, custom/unlimited

#### 2. Tier Configuration (`src/lib/stripe.ts`)
Update `TIER_CONFIG` to match new pricing structure.

#### 3. Environment Variables (`.env.example`)
Update Stripe price ID variables to match new tiers.

#### 4. Usage Limit Enforcement
Verify `FREE_TIER_LIMITS` and credit costs align with requirements.

## Implementation Steps

### Step 1: Update Pricing Configuration
- Modify `SUBSCRIPTION_TIERS` in `src/lib/pricing.ts`
- Update `FEATURE_COMPARISON` table
- Update `TIER_CONFIG` in `src/lib/stripe.ts`

### Step 2: Update Environment Variables
- Update `.env.example` with new price ID variables
- Document required Stripe products/prices to create

### Step 3: Verify Usage Enforcement
- Check `FREE_TIER_LIMITS` matches 5/month requirement
- Verify credit costs align with analysis limits
- Test reserve-confirm-cancel flow

### Step 4: Update Pricing Page
- Ensure UI displays correct tiers and pricing
- Update feature comparison table
- Verify checkout flow works for all tiers

### Step 5: Test Integration
- Create test products in Stripe dashboard
- Configure webhook endpoints
- Test subscription flow end-to-end
- Verify webhook event handling

## Required Stripe Products/Prices

Create in Stripe Dashboard:

### Subscription Products

#### Pro Plan ($19/mo)
- Product: "Parse Pro"
- Price: $19.00/month (recurring)
- Price ID: `STRIPE_PRICE_TIER_PRO`

#### Team Plan ($99/mo)
- Product: "Parse Team"
- Price: $99.00/month (recurring)
- Price ID: `STRIPE_PRICE_TIER_TEAM`

#### Enterprise Plan ($499/mo)
- Product: "Parse Enterprise"
- Price: $499.00/month (recurring)
- Price ID: `STRIPE_PRICE_TIER_ENTERPRISE`

### Webhook Configuration
- Endpoint: `https://your-domain.com/api/stripe/webhook`
- Events to subscribe:
  - `checkout.session.completed`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.paid`
  - `invoice.payment_failed`

## Success Criteria
- [ ] All 4 tiers configured correctly
- [ ] Test subscription payments successful
- [ ] Webhooks processed correctly
- [ ] Usage limits enforced (5 free, 100 Pro, etc.)
- [ ] Production ready configuration documented
