# kublai.kurult.ai Domain Switch Execution Plan

**Created:** 2026-02-07
**Status:** Waiting for Railway SSL cert issuance
**DNS:** `kublai.kurult.ai` CNAME → `cryqc2p5.up.railway.app` (propagated)
**Cert:** `CERTIFICATE_STATUS_TYPE_VALIDATING_OWNERSHIP` (pending)

---

## Phase 0: Pre-Migration Security Fixes (CRITICAL)

Address these **before** switching the domain.

| # | Finding | Severity | Action | Verify |
|---|---------|----------|--------|--------|
| 0.1 | `authentik-credentials.txt` in working dir with plaintext admin password | **CRITICAL** | Delete file, add to `.gitignore` | `ls authentik-credentials.txt` should fail |
| 0.2 | Hardcoded fallback token in `update_proxy_provider.sh` line 12 (`bootstraptoken123456`) | **CRITICAL** | Remove default value | `grep "bootstraptoken123456" authentik-server/update_proxy_provider.sh` — no match |
| 0.3 | `/ws/*` route bypasses Authentik auth entirely | **CRITICAL** | Add `forward_auth` or Origin validation to Caddyfile `/ws/*` route | `wscat -c "wss://kublai.kurult.ai/ws/"` without auth cookie should be rejected |
| 0.4 | `shellEnv.enabled: true` exposes all secrets to agent sandboxes | **HIGH** | Restrict env vars in `openclaw.json5` | Review `shellEnv` config |
| 0.5 | No security headers in Caddyfile (HSTS, CSP, X-Frame-Options) | **MEDIUM** | Add after domain switch confirmed working | `curl -sI https://kublai.kurult.ai/ \| grep -i strict-transport` |

---

## Phase 1: Verify SSL Certificate Issuance

### 1.1 Check Railway cert status

```bash
RAILWAY_TOKEN=$(cat ~/.railway/config.json | python3 -c "import sys,json; print(json.load(sys.stdin)['user']['token'])")
curl -s -X POST https://backboard.railway.app/graphql/v2 \
  -H "Authorization: Bearer $RAILWAY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"query { project(id: \"26201f75-3375-46ce-98c7-9d1dde5f9569\") { services { edges { node { name serviceInstances { edges { node { domains { customDomains { domain status { dnsRecords { requiredValue currentValue status } certificateStatus } } } } } } } } } } }"}' \
  | python3 -m json.tool
```

**Expected:** `certificateStatus: "CERTIFICATE_STATUS_TYPE_ISSUED"`

### 1.2 Verify cert subject

```bash
openssl s_client -connect kublai.kurult.ai:443 -servername kublai.kurult.ai \
  < /dev/null 2>/dev/null | openssl x509 -noout -subject -dates -issuer
```

**Expected:**
- Subject: `CN=kublai.kurult.ai` (NOT `*.up.railway.app`)
- Issuer: Let's Encrypt (R13 or E6)
- Expiry: ~90 days from issuance

### 1.3 Quick HTTPS check

```bash
curl -sI https://kublai.kurult.ai/ 2>&1 | head -10
```

**Expected:** HTTP response (302 redirect to Authentik login, or 502 if Authentik isn't configured yet). No SSL errors.

---

## Phase 2: Switch Authentik Configuration

### Option A: Use existing script (recommended)

A complete script exists at `scripts/switch-authentik-to-custom-domain.sh` (709 lines, executable). It handles all steps with error handling and rollback.

```bash
# Set the bootstrap password
export AUTHENTIK_BOOTSTRAP_PASSWORD="<password>"

# Dry run first (read-only, no changes)
./scripts/switch-authentik-to-custom-domain.sh --dry-run

# If dry run passes, execute live
./scripts/switch-authentik-to-custom-domain.sh
```

**What the script does internally:**

| Step | Action | API Call |
|------|--------|---------|
| 0 | Preflight: health check on Railway URL | `GET /-/health/ready/` |
| 1 | SSL cert verification (retries 5x @ 10s) | TLS handshake to `kublai.kurult.ai:443` |
| 2a | Start auth flow | `GET /api/v3/flows/executor/default-authentication-flow/?query=` |
| 2b | Submit username | `POST` with `{component: "ak-stage-identification", uid_field: "akadmin"}` |
| 2c | Submit password | `POST` with `{component: "ak-stage-password", password: "..."}` |
| 3 | Read current provider config | `GET /api/v3/providers/proxy/1/` |
| 4 | Update provider `external_host` | `PATCH /api/v3/providers/proxy/1/` → `https://kublai.kurult.ai` |
| 5 | Read current brand config | `GET /api/v3/core/brands/bed854f1-e54b-4616-adfb-c667a42b2b13/` |
| 6 | Update brand `domain` | `PATCH /api/v3/core/brands/bed854f1-.../` → `kublai.kurult.ai` |
| 7 | Verify both configs updated | Re-read provider + brand |
| 8 | End-to-end tests (5 checks) | Health, auth redirect, admin UI, API, WebSocket |

### Option B: Manual curl commands

If the script doesn't work, use these manual commands.

#### 2.1 Authenticate to Authentik admin (3-step flow API)

```bash
AUTHENTIK_URL="https://authentik-proxy-production-06a7.up.railway.app"
COOKIE_JAR=$(mktemp)

# Step 1: Start auth flow
curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
  -H "Referer: ${AUTHENTIK_URL}/" \
  "${AUTHENTIK_URL}/api/v3/flows/executor/default-authentication-flow/?query=" \
  | python3 -m json.tool

# Step 2: Submit username
CSRF=$(grep authentik_csrf "$COOKIE_JAR" | awk '{print $NF}')
curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-authentik-CSRF: $CSRF" \
  -H "Referer: ${AUTHENTIK_URL}/" \
  -d '{"component":"ak-stage-identification","uid_field":"akadmin"}' \
  "${AUTHENTIK_URL}/api/v3/flows/executor/default-authentication-flow/" \
  | python3 -m json.tool

# Step 3: Submit password
CSRF=$(grep authentik_csrf "$COOKIE_JAR" | awk '{print $NF}')
curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-authentik-CSRF: $CSRF" \
  -H "Referer: ${AUTHENTIK_URL}/" \
  -d "{\"component\":\"ak-stage-password\",\"password\":\"${AUTHENTIK_BOOTSTRAP_PASSWORD}\"}" \
  "${AUTHENTIK_URL}/api/v3/flows/executor/default-authentication-flow/" \
  | python3 -m json.tool

# Verify: check we're admin
curl -s -b "$COOKIE_JAR" \
  -H "Referer: ${AUTHENTIK_URL}/" \
  "${AUTHENTIK_URL}/api/v3/core/users/me/" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"User: {d['user']['username']}, Superuser: {d['user']['is_superuser']}\")"
```

#### 2.2 Update provider external_host

```bash
CSRF=$(grep authentik_csrf "$COOKIE_JAR" | awk '{print $NF}')
curl -s -b "$COOKIE_JAR" \
  -X PATCH \
  -H "Content-Type: application/json" \
  -H "X-authentik-CSRF: $CSRF" \
  -H "Referer: ${AUTHENTIK_URL}/" \
  -d '{"external_host":"https://kublai.kurult.ai","internal_host":"http://moltbot-railway-template.railway.internal:18789"}' \
  "${AUTHENTIK_URL}/api/v3/providers/proxy/1/" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"external_host: {d['external_host']}\")"
```

#### 2.3 Update brand domain

```bash
CSRF=$(grep authentik_csrf "$COOKIE_JAR" | awk '{print $NF}')
curl -s -b "$COOKIE_JAR" \
  -X PATCH \
  -H "Content-Type: application/json" \
  -H "X-authentik-CSRF: $CSRF" \
  -H "Referer: ${AUTHENTIK_URL}/" \
  -d '{"domain":"kublai.kurult.ai"}' \
  "${AUTHENTIK_URL}/api/v3/core/brands/bed854f1-e54b-4616-adfb-c667a42b2b13/" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"domain: {d['domain']}\")"

# Cleanup
rm -f "$COOKIE_JAR"
```

---

## Phase 3: Post-Switch Verification

### 3.1 SSL/TLS

```bash
# Cert subject check
openssl s_client -connect kublai.kurult.ai:443 -servername kublai.kurult.ai \
  < /dev/null 2>/dev/null | openssl x509 -noout -subject -dates -issuer

# TLS 1.1 should be rejected
openssl s_client -connect kublai.kurult.ai:443 -tls1_1 < /dev/null 2>&1 | grep -i "protocol"

# HSTS header (may not exist yet)
curl -sI https://kublai.kurult.ai/ 2>/dev/null | grep -i strict-transport
```

### 3.2 Authentik Proxy

```bash
# Should redirect to login (302), NOT to 0.0.0.0:9000
curl -sI https://kublai.kurult.ai/ | grep -i location

# Health endpoint
curl -s https://kublai.kurult.ai/-/health/ready/

# No redirect loops (max 5 redirects)
curl -sL --max-redirs 5 -o /dev/null -w "%{http_code} %{num_redirects} redirects\n" https://kublai.kurult.ai/

# Check for 0.0.0.0:9000 bug
curl -sL https://kublai.kurult.ai/if/admin/ 2>&1 | grep "0.0.0.0"
# Expected: no output
```

### 3.3 Cookie Security

```bash
# Check cookie attributes
curl -sI -c - https://kublai.kurult.ai/outpost.goauthentik.io/start 2>/dev/null | grep -i "set-cookie"
# Look for: Secure; HttpOnly; SameSite=Lax

# Ensure no cookies leak to parent domain (.kurult.ai)
curl -v https://kublai.kurult.ai/ 2>&1 | grep -i "set-cookie" | grep -i "domain"
```

### 3.4 CSRF Protection

```bash
# CSRF cookie should be set
curl -c /tmp/csrf_test.txt -s https://kublai.kurult.ai/if/flow/default-authentication-flow/ > /dev/null
grep csrf /tmp/csrf_test.txt

# Wrong Referer should get 403
curl -X POST https://kublai.kurult.ai/api/v3/flows/executor/default-authentication-flow/ \
  -H "Referer: https://evil.example.com/" \
  -s | head -c 200
```

### 3.5 Open Redirect Protection

```bash
# Should NOT redirect to evil.com
curl -sI "https://kublai.kurult.ai/outpost.goauthentik.io/start?rd=//evil.com" | grep -i location
```

### 3.6 WebSocket

```bash
# WebSocket upgrade test
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  "https://kublai.kurult.ai/ws/" 2>&1 | head -5

# Origin validation (should be rejected)
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Origin: https://evil.example.com" \
  "https://kublai.kurult.ai/ws/" 2>&1 | head -5
```

### 3.7 Browser Test

```bash
open "https://kublai.kurult.ai"
# Should show Authentik login page
# After login, OpenClaw webchat UI should load
# Check DevTools > Network > WS tab for wss:// connections
```

---

## Phase 4: Post-Migration Hardening

After confirming everything works:

### 4.1 Add security headers to Caddyfile

```caddy
header X-Content-Type-Options "nosniff"
header X-Frame-Options "DENY"
header Referrer-Policy "strict-origin-when-cross-origin"
header Permissions-Policy "camera=(), microphone=(), geolocation=()"
```

### 4.2 Add HSTS (only after HTTPS confirmed reliable)

```caddy
header Strict-Transport-Security "max-age=31536000; includeSubDomains"
```

### 4.3 Add CAA DNS record in Cloudflare

```
kurult.ai  CAA  0 issue "letsencrypt.org"
```

### 4.4 Add Origin validation for `/ws/*` route

```caddy
@badOrigin {
    not header Origin https://kublai.kurult.ai
    path /ws/*
}
respond @badOrigin "Forbidden" 403
```

### 4.5 Reduce refresh token validity

In `authentik-proxy/config/proxy-provider.yaml`:
```yaml
refresh_token_validity: days=7  # was days=30
```

### 4.6 Restrict shell environment in OpenClaw

In `moltbot-railway-template/openclaw.json5`, change `shellEnv` to allowlist specific safe vars instead of passing all.

---

## Rollback Procedure

If anything breaks after the switch, revert Authentik to the Railway URL.

### Quick Rollback

```bash
export AUTHENTIK_BOOTSTRAP_PASSWORD="<password>"
AUTHENTIK_URL="https://authentik-proxy-production-06a7.up.railway.app"
COOKIE_JAR=$(mktemp)

# Auth (same 3-step flow)
curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
  -H "Referer: ${AUTHENTIK_URL}/" \
  "${AUTHENTIK_URL}/api/v3/flows/executor/default-authentication-flow/?query=" > /dev/null

CSRF=$(grep authentik_csrf "$COOKIE_JAR" | awk '{print $NF}')
curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" -X POST \
  -H "Content-Type: application/json" \
  -H "X-authentik-CSRF: $CSRF" \
  -H "Referer: ${AUTHENTIK_URL}/" \
  -d '{"component":"ak-stage-identification","uid_field":"akadmin"}' \
  "${AUTHENTIK_URL}/api/v3/flows/executor/default-authentication-flow/" > /dev/null

CSRF=$(grep authentik_csrf "$COOKIE_JAR" | awk '{print $NF}')
curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" -X POST \
  -H "Content-Type: application/json" \
  -H "X-authentik-CSRF: $CSRF" \
  -H "Referer: ${AUTHENTIK_URL}/" \
  -d "{\"component\":\"ak-stage-password\",\"password\":\"${AUTHENTIK_BOOTSTRAP_PASSWORD}\"}" \
  "${AUTHENTIK_URL}/api/v3/flows/executor/default-authentication-flow/" > /dev/null

# Revert provider
CSRF=$(grep authentik_csrf "$COOKIE_JAR" | awk '{print $NF}')
curl -s -b "$COOKIE_JAR" -X PATCH \
  -H "Content-Type: application/json" \
  -H "X-authentik-CSRF: $CSRF" \
  -H "Referer: ${AUTHENTIK_URL}/" \
  -d "{\"external_host\":\"${AUTHENTIK_URL}\"}" \
  "${AUTHENTIK_URL}/api/v3/providers/proxy/1/" \
  | python3 -c "import sys,json; print(f\"Reverted to: {json.load(sys.stdin)['external_host']}\")"

# Revert brand
CSRF=$(grep authentik_csrf "$COOKIE_JAR" | awk '{print $NF}')
curl -s -b "$COOKIE_JAR" -X PATCH \
  -H "Content-Type: application/json" \
  -H "X-authentik-CSRF: $CSRF" \
  -H "Referer: ${AUTHENTIK_URL}/" \
  -d '{"domain":"authentik-proxy-production-06a7.up.railway.app"}' \
  "${AUTHENTIK_URL}/api/v3/core/brands/bed854f1-e54b-4616-adfb-c667a42b2b13/" \
  | python3 -c "import sys,json; print(f\"Reverted to: {json.load(sys.stdin)['domain']}\")"

rm -f "$COOKIE_JAR"
```

### Verify Rollback

```bash
curl -sI https://authentik-proxy-production-06a7.up.railway.app/ | head -5
# Should show 302 to Authentik login, no errors
```

### Timeline Expectations

| Operation | Duration |
|-----------|----------|
| DNS propagation (Cloudflare) | 30s - 5 min |
| Railway SSL cert provisioning | 1 - 30 min (currently stuck) |
| Authentik API PATCH | Immediate |
| Full rollback execution | Under 5 min |
| Re-application (DNS + cert + API) | 5 - 15 min |

---

## Key Configuration Reference

| Item | Value |
|------|-------|
| Custom domain | `kublai.kurult.ai` |
| Railway CNAME target | `cryqc2p5.up.railway.app` |
| Railway domain ID | `9b25dacc-adeb-4077-bfb6-a03c79ab05d5` |
| Provider ID | `1` |
| Brand UUID | `bed854f1-e54b-4616-adfb-c667a42b2b13` |
| Auth flow slug | `default-authentication-flow` |
| Internal host | `http://moltbot-railway-template.railway.internal:18789` |
| CSRF header | `X-authentik-CSRF` (from `authentik_csrf` cookie) |
| Railway project ID | `26201f75-3375-46ce-98c7-9d1dde5f9569` |
| Authentik Railway URL | `https://authentik-proxy-production-06a7.up.railway.app` |
| Script path | `scripts/switch-authentik-to-custom-domain.sh` |
| Verification script | `scripts/verify-custom-domain.sh` |

---

## Sources

- **Backend architect agent**: Discovered existing `switch-authentik-to-custom-domain.sh` script (709 lines), documented its 8-step flow and failure scenarios
- **DevOps agent**: Created `verify-custom-domain.sh` with 5-phase verification and rollback mode
- **Security auditor**: Found CRITICAL credential exposure (`authentik-credentials.txt`), WebSocket auth bypass (`/ws/*`), and 7 additional findings across the infrastructure
