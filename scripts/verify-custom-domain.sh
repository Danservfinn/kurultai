#!/usr/bin/env bash
# =============================================================================
# kublai.kurult.ai Custom Domain Verification & Rollback Script
# =============================================================================
#
# This script verifies that the custom domain switch from a raw Railway URL
# to kublai.kurult.ai is working correctly across all layers:
#   1. DNS (Cloudflare CNAME)
#   2. SSL/TLS (Let's Encrypt certificate)
#   3. Authentik reverse proxy (login, CSRF, redirects)
#   4. OpenClaw gateway (health, WebSocket, webchat UI)
#
# It also provides rollback commands if something is broken.
#
# Usage:
#   ./scripts/verify-custom-domain.sh              # Run all checks
#   ./scripts/verify-custom-domain.sh --rollback    # Show rollback commands
#   ./scripts/verify-custom-domain.sh --check-only  # Non-interactive checks only
#
# Prerequisites:
#   - curl, openssl, dig (or nslookup), jq
#   - AUTHENTIK_BOOTSTRAP_PASSWORD env var (for rollback API calls)
#
# Architecture:
#   Cloudflare DNS --> Railway (authentik-proxy) --> Caddy --> Authentik + OpenClaw
#   kublai.kurult.ai CNAME --> cryqc2p5.up.railway.app
#
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CUSTOM_DOMAIN="kublai.kurult.ai"
RAILWAY_CNAME="cryqc2p5.up.railway.app"
RAILWAY_URL="https://${RAILWAY_CNAME}"
CUSTOM_URL="https://${CUSTOM_DOMAIN}"

# Authentik API config
AUTHENTIK_BASE="${CUSTOM_URL}"
AUTHENTIK_FLOW_SLUG="default-authentication-flow"
AUTHENTIK_PROVIDER_ID="1"
BRAND_UUID="bed854f1-e54b-4616-adfb-c667a42b2b13"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASS=0
FAIL=0
WARN=0

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
check_pass() {
    echo -e "  ${GREEN}[PASS]${NC} $1"
    ((PASS++))
}

check_fail() {
    echo -e "  ${RED}[FAIL]${NC} $1"
    ((FAIL++))
}

check_warn() {
    echo -e "  ${YELLOW}[WARN]${NC} $1"
    ((WARN++))
}

check_info() {
    echo -e "  ${BLUE}[INFO]${NC} $1"
}

section() {
    echo ""
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

# ---------------------------------------------------------------------------
# Pre-flight: check required tools
# ---------------------------------------------------------------------------
preflight() {
    section "Pre-flight: Checking required tools"

    for tool in curl openssl jq; do
        if command -v "$tool" &>/dev/null; then
            check_pass "$tool is installed"
        else
            check_fail "$tool is NOT installed (required)"
        fi
    done

    # dig or nslookup
    if command -v dig &>/dev/null; then
        check_pass "dig is installed"
        DNS_TOOL="dig"
    elif command -v nslookup &>/dev/null; then
        check_warn "dig not found, using nslookup (less detailed output)"
        DNS_TOOL="nslookup"
    else
        check_fail "Neither dig nor nslookup found"
        DNS_TOOL="none"
    fi
}

# ---------------------------------------------------------------------------
# Phase 1: DNS Verification
# ---------------------------------------------------------------------------
verify_dns() {
    section "Phase 1: DNS Verification"

    echo ""
    echo "  Expected: ${CUSTOM_DOMAIN} CNAME --> ${RAILWAY_CNAME}"
    echo ""

    if [[ "$DNS_TOOL" == "dig" ]]; then
        echo "  Command: dig +short CNAME ${CUSTOM_DOMAIN}"
        CNAME_RESULT=$(dig +short CNAME "${CUSTOM_DOMAIN}" 2>/dev/null || true)
        echo "  Result:  ${CNAME_RESULT:-<empty>}"
        echo ""

        # Remove trailing dot from dig output
        CNAME_CLEAN="${CNAME_RESULT%.}"

        if [[ "$CNAME_CLEAN" == "$RAILWAY_CNAME" ]]; then
            check_pass "CNAME points to correct Railway target: ${RAILWAY_CNAME}"
        elif [[ -z "$CNAME_CLEAN" ]]; then
            check_fail "No CNAME record found for ${CUSTOM_DOMAIN}"
            echo "         Fix: Add CNAME record in Cloudflare DNS:"
            echo "         Type: CNAME, Name: kublai, Target: ${RAILWAY_CNAME}"
        else
            check_fail "CNAME points to WRONG target: ${CNAME_CLEAN}"
            echo "         Expected: ${RAILWAY_CNAME}"
            echo "         Fix: Update CNAME in Cloudflare from ${CNAME_CLEAN} to ${RAILWAY_CNAME}"
        fi

        # Also check A record resolution (end-to-end)
        echo ""
        echo "  Command: dig +short A ${CUSTOM_DOMAIN}"
        A_RESULT=$(dig +short A "${CUSTOM_DOMAIN}" 2>/dev/null || true)
        echo "  Result:  ${A_RESULT:-<empty>}"

        if [[ -n "$A_RESULT" ]]; then
            check_pass "Domain resolves to IP(s): ${A_RESULT}"
        else
            check_fail "Domain does not resolve to any IP address"
        fi

    elif [[ "$DNS_TOOL" == "nslookup" ]]; then
        echo "  Command: nslookup -type=CNAME ${CUSTOM_DOMAIN}"
        nslookup -type=CNAME "${CUSTOM_DOMAIN}" 2>/dev/null || true
        check_info "Verify CNAME target is ${RAILWAY_CNAME} in the output above"
    else
        check_fail "No DNS tool available to verify"
    fi

    # Check Cloudflare proxy status (orange cloud vs gray cloud)
    echo ""
    echo "  Checking if Cloudflare proxy (orange cloud) is active..."
    echo "  Command: dig +short A ${CUSTOM_DOMAIN} | head -1"
    RESOLVED_IP=$(dig +short A "${CUSTOM_DOMAIN}" 2>/dev/null | head -1 || true)

    if [[ -n "$RESOLVED_IP" ]]; then
        # Check if IP belongs to Cloudflare ranges (rough check)
        # Cloudflare IPs typically: 104.x.x.x, 172.64-71.x.x, 162.159.x.x
        if [[ "$RESOLVED_IP" =~ ^104\. ]] || [[ "$RESOLVED_IP" =~ ^172\.(6[4-9]|7[0-1])\. ]] || [[ "$RESOLVED_IP" =~ ^162\.159\. ]]; then
            check_warn "IP ${RESOLVED_IP} appears to be Cloudflare (proxy enabled / orange cloud)"
            echo "         This means Cloudflare is proxying. Railway SSL cert will be between"
            echo "         Cloudflare and Railway. Browser will see Cloudflare's cert."
            echo "         If Railway cert validation is failing, try DNS-only (gray cloud)."
        else
            check_info "IP ${RESOLVED_IP} does not appear to be Cloudflare (gray cloud / DNS-only)"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Phase 2: SSL Certificate Verification
# ---------------------------------------------------------------------------
verify_ssl() {
    section "Phase 2: SSL Certificate Verification"

    echo ""
    echo "  Command: openssl s_client -connect ${CUSTOM_DOMAIN}:443 -servername ${CUSTOM_DOMAIN}"
    echo ""

    # Get certificate details
    CERT_OUTPUT=$(echo | openssl s_client -connect "${CUSTOM_DOMAIN}:443" \
        -servername "${CUSTOM_DOMAIN}" 2>/dev/null || true)

    if [[ -z "$CERT_OUTPUT" ]]; then
        check_fail "Could not establish TLS connection to ${CUSTOM_DOMAIN}:443"
        echo "         This may mean DNS is not resolving, or the port is not open."
        return
    fi

    # Extract subject
    CERT_SUBJECT=$(echo "$CERT_OUTPUT" | openssl x509 -noout -subject 2>/dev/null || true)
    echo "  Subject: ${CERT_SUBJECT:-<could not parse>}"

    if echo "$CERT_SUBJECT" | grep -q "${CUSTOM_DOMAIN}"; then
        check_pass "Certificate subject contains ${CUSTOM_DOMAIN}"
    elif echo "$CERT_SUBJECT" | grep -qi "cloudflare"; then
        check_warn "Certificate subject is Cloudflare (proxy mode). Railway cert is behind CF."
        echo "         This is expected if Cloudflare proxy (orange cloud) is enabled."
    elif echo "$CERT_SUBJECT" | grep -q "railway.app"; then
        check_fail "Certificate subject is still *.up.railway.app wildcard"
        echo "         Railway has not provisioned a cert for ${CUSTOM_DOMAIN}"
        echo "         Check Railway dashboard > Settings > Custom Domains"
    else
        check_warn "Unexpected certificate subject: ${CERT_SUBJECT}"
    fi

    # Extract issuer
    CERT_ISSUER=$(echo "$CERT_OUTPUT" | openssl x509 -noout -issuer 2>/dev/null || true)
    echo "  Issuer:  ${CERT_ISSUER:-<could not parse>}"

    if echo "$CERT_ISSUER" | grep -qi "let's encrypt\|R1[0-9]\|E[0-9]\|ISRG"; then
        check_pass "Certificate issued by Let's Encrypt"
    elif echo "$CERT_ISSUER" | grep -qi "cloudflare"; then
        check_info "Certificate issued by Cloudflare (proxy mode)"
    elif echo "$CERT_ISSUER" | grep -qi "google trust"; then
        check_info "Certificate issued by Google Trust Services"
    else
        check_warn "Unexpected certificate issuer: ${CERT_ISSUER}"
    fi

    # Extract expiry date
    CERT_ENDDATE=$(echo "$CERT_OUTPUT" | openssl x509 -noout -enddate 2>/dev/null || true)
    echo "  Expiry:  ${CERT_ENDDATE:-<could not parse>}"

    if [[ -n "$CERT_ENDDATE" ]]; then
        # Parse the date
        EXPIRY_DATE=$(echo "$CERT_ENDDATE" | sed 's/notAfter=//')
        EXPIRY_EPOCH=$(date -j -f "%b %d %T %Y %Z" "$EXPIRY_DATE" "+%s" 2>/dev/null || \
                       date -d "$EXPIRY_DATE" "+%s" 2>/dev/null || echo "0")
        NOW_EPOCH=$(date "+%s")

        if [[ "$EXPIRY_EPOCH" -gt "$NOW_EPOCH" ]]; then
            DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
            if [[ "$DAYS_LEFT" -gt 14 ]]; then
                check_pass "Certificate expires in ${DAYS_LEFT} days"
            elif [[ "$DAYS_LEFT" -gt 0 ]]; then
                check_warn "Certificate expires in ${DAYS_LEFT} days (renewal soon)"
            fi
        else
            check_fail "Certificate has EXPIRED"
        fi
    fi

    # Check SANs (Subject Alternative Names)
    echo ""
    CERT_SANS=$(echo "$CERT_OUTPUT" | openssl x509 -noout -ext subjectAltName 2>/dev/null || true)
    echo "  SANs:    ${CERT_SANS:-<none found>}"

    if echo "$CERT_SANS" | grep -q "${CUSTOM_DOMAIN}"; then
        check_pass "SAN includes ${CUSTOM_DOMAIN}"
    fi

    # Verify full chain
    echo ""
    echo "  Verifying certificate chain..."
    VERIFY_RESULT=$(echo | openssl s_client -connect "${CUSTOM_DOMAIN}:443" \
        -servername "${CUSTOM_DOMAIN}" -verify_return_error 2>&1 | \
        grep -i "verify return\|verify error" | head -3 || true)
    echo "  ${VERIFY_RESULT:-<no verify output>}"

    if echo "$VERIFY_RESULT" | grep -q "verify return:1"; then
        check_pass "Certificate chain is valid"
    elif echo "$VERIFY_RESULT" | grep -q "verify error"; then
        check_fail "Certificate chain verification failed"
        echo "         ${VERIFY_RESULT}"
    fi
}

# ---------------------------------------------------------------------------
# Phase 3: Authentik Proxy Verification
# ---------------------------------------------------------------------------
verify_authentik() {
    section "Phase 3: Authentik Proxy Verification"

    # 3a. Check if login page loads
    echo ""
    echo "  3a. Checking if Authentik login page loads..."
    echo "  Command: curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' ${CUSTOM_URL}/"
    echo ""

    RESPONSE=$(curl -sS -o /dev/null -w '%{http_code}|%{redirect_url}|%{url_effective}' \
        --max-time 15 "${CUSTOM_URL}/" 2>/dev/null || echo "000||")

    HTTP_CODE=$(echo "$RESPONSE" | cut -d'|' -f1)
    REDIRECT_URL=$(echo "$RESPONSE" | cut -d'|' -f2)
    EFFECTIVE_URL=$(echo "$RESPONSE" | cut -d'|' -f3)

    echo "  HTTP Status: ${HTTP_CODE}"
    echo "  Redirect:    ${REDIRECT_URL:-<none>}"

    if [[ "$HTTP_CODE" == "302" ]] || [[ "$HTTP_CODE" == "303" ]]; then
        if echo "$REDIRECT_URL" | grep -q "/flows/"; then
            check_pass "Root URL redirects to Authentik login flow"
        elif echo "$REDIRECT_URL" | grep -q "0.0.0.0:9000"; then
            check_fail "Redirect contains 0.0.0.0:9000 -- brand domain is misconfigured!"
            echo "         Fix: PATCH the brand domain to ${CUSTOM_DOMAIN}"
            echo "         See rollback section for exact commands."
        else
            check_warn "Root URL redirects to: ${REDIRECT_URL}"
            echo "         Verify this is the expected Authentik login flow URL."
        fi
    elif [[ "$HTTP_CODE" == "200" ]]; then
        check_info "Root URL returned 200 (may already be authenticated or no auth required)"
    elif [[ "$HTTP_CODE" == "000" ]]; then
        check_fail "Connection failed -- service may be down or DNS not resolving"
    else
        check_warn "Unexpected HTTP status: ${HTTP_CODE}"
    fi

    # 3b. Check for redirect loops
    echo ""
    echo "  3b. Checking for redirect loops..."
    echo "  Command: curl -sS -L --max-redirs 5 -o /dev/null -w '%{http_code} %{num_redirects}' ${CUSTOM_URL}/"
    echo ""

    LOOP_CHECK=$(curl -sS -L --max-redirs 5 -o /dev/null \
        -w '%{http_code}|%{num_redirects}' \
        --max-time 20 "${CUSTOM_URL}/" 2>/dev/null || echo "000|0")

    FINAL_CODE=$(echo "$LOOP_CHECK" | cut -d'|' -f1)
    NUM_REDIRECTS=$(echo "$LOOP_CHECK" | cut -d'|' -f2)

    echo "  Final HTTP Status: ${FINAL_CODE}"
    echo "  Number of redirects: ${NUM_REDIRECTS}"

    if [[ "$NUM_REDIRECTS" -le 3 ]] && [[ "$FINAL_CODE" == "200" ]]; then
        check_pass "No redirect loop detected (${NUM_REDIRECTS} redirect(s) to ${FINAL_CODE})"
    elif [[ "$NUM_REDIRECTS" -ge 5 ]]; then
        check_fail "Possible redirect loop! ${NUM_REDIRECTS} redirects detected"
        echo "         Common cause: provider external_host and brand domain mismatch"
    elif [[ "$FINAL_CODE" == "000" ]]; then
        check_fail "Connection failed during redirect following"
    else
        check_info "${NUM_REDIRECTS} redirect(s), final status ${FINAL_CODE}"
    fi

    # 3c. Check for 0.0.0.0:9000 redirect (known Authentik misconfiguration)
    echo ""
    echo "  3c. Checking for 0.0.0.0:9000 redirect (known brand domain issue)..."
    echo "  Command: curl -sS -D - -o /dev/null ${CUSTOM_URL}/ | grep -i location"
    echo ""

    HEADERS=$(curl -sS -D - -o /dev/null --max-time 15 "${CUSTOM_URL}/" 2>/dev/null || true)
    LOCATION_HEADER=$(echo "$HEADERS" | grep -i "^location:" || true)
    echo "  Location header: ${LOCATION_HEADER:-<none>}"

    if echo "$LOCATION_HEADER" | grep -q "0.0.0.0"; then
        check_fail "CRITICAL: Redirect to 0.0.0.0 detected!"
        echo "         The Authentik brand domain is not set correctly."
        echo "         Run: ./scripts/verify-custom-domain.sh --rollback"
    elif [[ -n "$LOCATION_HEADER" ]]; then
        if echo "$LOCATION_HEADER" | grep -q "${CUSTOM_DOMAIN}"; then
            check_pass "Location header correctly references ${CUSTOM_DOMAIN}"
        else
            check_warn "Location header references: ${LOCATION_HEADER}"
        fi
    else
        check_info "No Location header (may be 200 response)"
    fi

    # 3d. Verify CSRF token is generated for custom domain
    echo ""
    echo "  3d. Checking CSRF token generation..."
    echo "  Command: curl -sS -c - ${CUSTOM_URL}/if/flow/default-authentication-flow/ | grep csrf"
    echo ""

    CSRF_CHECK=$(curl -sS -c - -o /dev/null --max-time 15 \
        -L "${CUSTOM_URL}/if/flow/${AUTHENTIK_FLOW_SLUG}/" 2>/dev/null || true)
    CSRF_COOKIE=$(echo "$CSRF_CHECK" | grep -i "authentik_csrf" || true)

    if [[ -n "$CSRF_COOKIE" ]]; then
        check_pass "CSRF cookie (authentik_csrf) is set"
    else
        check_warn "Could not detect authentik_csrf cookie"
        echo "         This may be expected if the flow redirects before setting cookies."
        echo "         Manual check: Open ${CUSTOM_URL} in browser, inspect cookies."
    fi

    # 3e. Verify Authentik API is accessible
    echo ""
    echo "  3e. Checking Authentik API health..."
    echo "  Command: curl -sS ${CUSTOM_URL}/-/health/ready/"
    echo ""

    HEALTH_CODE=$(curl -sS -o /dev/null -w '%{http_code}' \
        --max-time 10 "${CUSTOM_URL}/-/health/ready/" 2>/dev/null || echo "000")

    echo "  Health endpoint status: ${HEALTH_CODE}"

    if [[ "$HEALTH_CODE" == "200" || "$HEALTH_CODE" == "204" ]]; then
        check_pass "Authentik health endpoint is responding"
    elif [[ "$HEALTH_CODE" == "503" ]]; then
        check_fail "Authentik is unhealthy (503)"
    else
        check_warn "Authentik health returned: ${HEALTH_CODE}"
    fi
}

# ---------------------------------------------------------------------------
# Phase 4: OpenClaw Gateway Verification
# ---------------------------------------------------------------------------
verify_openclaw() {
    section "Phase 4: OpenClaw Gateway Verification"

    # 4a. Health check (unauthenticated -- Caddyfile routes /health directly)
    echo ""
    echo "  4a. OpenClaw health check (bypasses auth per Caddyfile)..."
    echo "  Command: curl -sS ${CUSTOM_URL}/health"
    echo ""

    HEALTH_RESPONSE=$(curl -sS --max-time 10 "${CUSTOM_URL}/health" 2>/dev/null || echo "")
    HEALTH_CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 \
        "${CUSTOM_URL}/health" 2>/dev/null || echo "000")

    echo "  HTTP Status: ${HEALTH_CODE}"
    echo "  Response:    ${HEALTH_RESPONSE:-<empty>}"

    if [[ "$HEALTH_CODE" == "200" ]]; then
        check_pass "OpenClaw health endpoint returned 200"
    elif [[ "$HEALTH_CODE" == "302" ]]; then
        check_warn "Health endpoint redirected (may be going through auth)"
        echo "         If this is a redirect to Authentik login, the /health route"
        echo "         may not be excluded from forward_auth in the Caddyfile."
    elif [[ "$HEALTH_CODE" == "502" ]]; then
        check_fail "502 Bad Gateway -- OpenClaw may be down or unreachable from proxy"
    else
        check_warn "Health check returned: ${HEALTH_CODE}"
    fi

    # 4b. WebSocket upgrade support check
    echo ""
    echo "  4b. WebSocket upgrade support check..."
    echo "  Command: curl -sS -I -H 'Upgrade: websocket' -H 'Connection: Upgrade' ${CUSTOM_URL}/ws/"
    echo ""

    WS_RESPONSE=$(curl -sS -I --max-time 10 \
        -H "Upgrade: websocket" \
        -H "Connection: Upgrade" \
        -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
        -H "Sec-WebSocket-Version: 13" \
        "${CUSTOM_URL}/ws/" 2>/dev/null || true)

    WS_STATUS=$(echo "$WS_RESPONSE" | head -1 || true)
    echo "  Response: ${WS_STATUS:-<empty>}"

    if echo "$WS_STATUS" | grep -q "101"; then
        check_pass "WebSocket upgrade successful (101 Switching Protocols)"
    elif echo "$WS_STATUS" | grep -q "200\|302\|403"; then
        check_info "WebSocket endpoint returned $(echo "$WS_STATUS" | grep -o '[0-9][0-9][0-9]')"
        echo "         101 is expected for active WS. Other codes may be normal for"
        echo "         unauthenticated requests or if OpenClaw requires auth first."
    elif [[ -z "$WS_STATUS" ]]; then
        check_warn "No response from WebSocket endpoint"
    else
        check_warn "WebSocket endpoint: ${WS_STATUS}"
    fi

    # 4c. Check that the webchat UI resources load
    echo ""
    echo "  4c. Checking webchat UI resource availability..."
    echo "  (These may redirect to auth if not authenticated)"
    echo ""

    UI_CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 \
        "${CUSTOM_URL}/" 2>/dev/null || echo "000")

    echo "  Root page status: ${UI_CODE}"
    if [[ "$UI_CODE" == "200" ]] || [[ "$UI_CODE" == "302" ]] || [[ "$UI_CODE" == "303" ]]; then
        check_pass "Root page is accessible (${UI_CODE})"
    else
        check_warn "Root page returned: ${UI_CODE}"
    fi
}

# ---------------------------------------------------------------------------
# Phase 5: Cross-domain consistency check
# ---------------------------------------------------------------------------
verify_consistency() {
    section "Phase 5: Configuration Consistency"

    echo ""
    echo "  Checking that Railway URL still works as fallback..."
    echo "  Command: curl -sS -o /dev/null -w '%{http_code}' ${RAILWAY_URL}/"
    echo ""

    RAILWAY_CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 \
        "${RAILWAY_URL}/" 2>/dev/null || echo "000")

    echo "  Railway URL status: ${RAILWAY_CODE}"

    if [[ "$RAILWAY_CODE" == "200" ]] || [[ "$RAILWAY_CODE" == "302" ]] || [[ "$RAILWAY_CODE" == "303" ]]; then
        check_info "Railway URL is still accessible (${RAILWAY_CODE}) -- good for rollback"
    elif [[ "$RAILWAY_CODE" == "000" ]]; then
        check_warn "Railway URL is not responding (may be expected if custom domain is primary)"
    fi
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print_summary() {
    section "Verification Summary"

    echo ""
    echo -e "  ${GREEN}Passed: ${PASS}${NC}"
    echo -e "  ${RED}Failed: ${FAIL}${NC}"
    echo -e "  ${YELLOW}Warnings: ${WARN}${NC}"
    echo ""

    if [[ "$FAIL" -eq 0 ]]; then
        echo -e "  ${GREEN}All critical checks passed. The custom domain switch looks healthy.${NC}"
    else
        echo -e "  ${RED}${FAIL} check(s) failed. Review the failures above.${NC}"
        echo -e "  ${RED}Consider running: ./scripts/verify-custom-domain.sh --rollback${NC}"
    fi
    echo ""
}

# ---------------------------------------------------------------------------
# Rollback Procedure
# ---------------------------------------------------------------------------
print_rollback() {
    section "ROLLBACK PROCEDURE"

    local RAILWAY_FALLBACK_URL="${RAILWAY_URL}"
    local RAILWAY_FALLBACK_DOMAIN="${RAILWAY_CNAME}"

    cat << 'ROLLBACK_HEADER'

  If the custom domain switch is broken, follow these steps to revert
  Authentik's provider and brand configuration back to the Railway URL.

  This uses the Authentik flow-based admin API authentication pattern
  (3-step auth) because AUTHENTIK_SECRET_KEY is the outpost service
  account, NOT an admin account.

ROLLBACK_HEADER

    echo -e "  ${YELLOW}NOTE: Replace <BOOTSTRAP_PASSWORD> with your actual password.${NC}"
    echo -e "  ${YELLOW}      Set it via: export AUTHENTIK_BOOTSTRAP_PASSWORD=yourpassword${NC}"
    echo ""

    cat << ROLLBACK_COMMANDS
  =========================================================================
  Step 1: Authenticate via Authentik Flow API (3-step process)
  =========================================================================

  The Authentik admin API requires authentication via the flow executor,
  not a simple bearer token. The SECRET_KEY is an outpost account (pk=2),
  which is read-only. Admin actions require flow-based auth.

  # Step 1a: GET the authentication flow (establishes session)
  curl -v -c /tmp/ak-cookies.txt \\
    -H "Referer: ${RAILWAY_FALLBACK_URL}/" \\
    "${RAILWAY_FALLBACK_URL}/api/v3/flows/executor/default-authentication-flow/?query="

  # Step 1b: POST the username (identification stage)
  curl -v -b /tmp/ak-cookies.txt -c /tmp/ak-cookies.txt \\
    -H "Content-Type: application/json" \\
    -H "Referer: ${RAILWAY_FALLBACK_URL}/" \\
    -X POST \\
    -d '{"component":"ak-stage-identification","uid_field":"akadmin"}' \\
    "${RAILWAY_FALLBACK_URL}/api/v3/flows/executor/default-authentication-flow/"

  # Step 1c: POST the password (password stage)
  # Replace <BOOTSTRAP_PASSWORD> with your actual AUTHENTIK_BOOTSTRAP_PASSWORD
  curl -v -b /tmp/ak-cookies.txt -c /tmp/ak-cookies.txt \\
    -H "Content-Type: application/json" \\
    -H "Referer: ${RAILWAY_FALLBACK_URL}/" \\
    -X POST \\
    -d '{"component":"ak-stage-password","password":"<BOOTSTRAP_PASSWORD>"}' \\
    "${RAILWAY_FALLBACK_URL}/api/v3/flows/executor/default-authentication-flow/"

  # Verify: extract CSRF token from cookies
  CSRF_TOKEN=\$(grep authentik_csrf /tmp/ak-cookies.txt | awk '{print \$NF}')
  echo "CSRF Token: \$CSRF_TOKEN"

  =========================================================================
  Step 2: PATCH the Proxy Provider external_host back to Railway URL
  =========================================================================

  # Revert provider external_host from custom domain to Railway URL
  curl -v -b /tmp/ak-cookies.txt \\
    -H "Content-Type: application/json" \\
    -H "X-authentik-CSRF: \$CSRF_TOKEN" \\
    -H "Referer: ${RAILWAY_FALLBACK_URL}/" \\
    -X PATCH \\
    -d '{"external_host":"${RAILWAY_FALLBACK_URL}"}' \\
    "${RAILWAY_FALLBACK_URL}/api/v3/providers/proxy/${AUTHENTIK_PROVIDER_ID}/"

  Expected response: HTTP 200 with the updated provider JSON.
  Verify: "external_host" should be "${RAILWAY_FALLBACK_URL}"

  =========================================================================
  Step 3: PATCH the Brand domain back to Railway domain
  =========================================================================

  # Revert brand domain from custom domain to Railway domain
  curl -v -b /tmp/ak-cookies.txt \\
    -H "Content-Type: application/json" \\
    -H "X-authentik-CSRF: \$CSRF_TOKEN" \\
    -H "Referer: ${RAILWAY_FALLBACK_URL}/" \\
    -X PATCH \\
    -d '{"domain":"${RAILWAY_FALLBACK_DOMAIN}"}' \\
    "${RAILWAY_FALLBACK_URL}/api/v3/core/brands/${BRAND_UUID}/"

  Expected response: HTTP 200 with the updated brand JSON.
  Verify: "domain" should be "${RAILWAY_FALLBACK_DOMAIN}"

  =========================================================================
  Step 4: Verify the Rollback
  =========================================================================

  # 4a. Check provider external_host
  curl -s -b /tmp/ak-cookies.txt \\
    -H "X-authentik-CSRF: \$CSRF_TOKEN" \\
    -H "Referer: ${RAILWAY_FALLBACK_URL}/" \\
    "${RAILWAY_FALLBACK_URL}/api/v3/providers/proxy/${AUTHENTIK_PROVIDER_ID}/" \\
    | jq '{external_host, internal_host, mode}'

  Expected:
  {
    "external_host": "${RAILWAY_FALLBACK_URL}",
    "internal_host": "http://moltbot-railway-template.railway.internal:18789",
    "mode": "forward_domain"
  }

  # 4b. Check brand domain
  curl -s -b /tmp/ak-cookies.txt \\
    -H "X-authentik-CSRF: \$CSRF_TOKEN" \\
    -H "Referer: ${RAILWAY_FALLBACK_URL}/" \\
    "${RAILWAY_FALLBACK_URL}/api/v3/core/brands/${BRAND_UUID}/" \\
    | jq '{domain, default}'

  Expected:
  {
    "domain": "${RAILWAY_FALLBACK_DOMAIN}",
    "default": true
  }

  # 4c. Test the Railway URL loads the login page (not 0.0.0.0:9000)
  curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' ${RAILWAY_FALLBACK_URL}/

  Expected: 302 redirecting to ${RAILWAY_FALLBACK_URL}/flows/... (NOT 0.0.0.0:9000)

  # 4d. Full health check
  curl -sS ${RAILWAY_FALLBACK_URL}/health

  Expected: 200 OK with OpenClaw health JSON

  =========================================================================
  Step 5: Cleanup
  =========================================================================

  rm -f /tmp/ak-cookies.txt

  =========================================================================
  Re-applying the Custom Domain (when ready to try again)
  =========================================================================

  When you're ready to switch back to the custom domain:

  1. Ensure DNS CNAME is correct:
     kublai.kurult.ai CNAME --> ${RAILWAY_CNAME}

  2. Ensure Railway has provisioned an SSL cert for kublai.kurult.ai:
     - Railway Dashboard > authentik-proxy > Settings > Custom Domains
     - Status should be "active" or "issued"

  3. Authenticate via flow API (Step 1 above, using Railway URL)

  4. PATCH provider external_host to custom domain:
     curl -v -b /tmp/ak-cookies.txt \\
       -H "Content-Type: application/json" \\
       -H "X-authentik-CSRF: \$CSRF_TOKEN" \\
       -H "Referer: ${RAILWAY_FALLBACK_URL}/" \\
       -X PATCH \\
       -d '{"external_host":"${CUSTOM_URL}"}' \\
       "${RAILWAY_FALLBACK_URL}/api/v3/providers/proxy/${AUTHENTIK_PROVIDER_ID}/"

  5. PATCH brand domain to custom domain:
     curl -v -b /tmp/ak-cookies.txt \\
       -H "Content-Type: application/json" \\
       -H "X-authentik-CSRF: \$CSRF_TOKEN" \\
       -H "Referer: ${RAILWAY_FALLBACK_URL}/" \\
       -X PATCH \\
       -d '{"domain":"${CUSTOM_DOMAIN}"}' \\
       "${RAILWAY_FALLBACK_URL}/api/v3/core/brands/${BRAND_UUID}/"

  6. Run verification:
     ./scripts/verify-custom-domain.sh

  =========================================================================
  Timeline Expectations
  =========================================================================

  - DNS propagation (CNAME change): 30 seconds to 5 minutes (Cloudflare)
  - Railway SSL cert provisioning: 1-10 minutes (Let's Encrypt)
  - Authentik API PATCH: Immediate effect
  - Full rollback: Under 5 minutes once commands are executed
  - Re-application: 5-15 minutes (mostly waiting for SSL cert)

ROLLBACK_COMMANDS
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    echo ""
    echo "=========================================="
    echo "  kublai.kurult.ai Domain Verification"
    echo "  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=========================================="

    case "${1:-}" in
        --rollback)
            print_rollback
            exit 0
            ;;
        --check-only)
            preflight
            verify_dns
            verify_ssl
            print_summary
            exit "$FAIL"
            ;;
        *)
            preflight
            verify_dns
            verify_ssl
            verify_authentik
            verify_openclaw
            verify_consistency
            print_summary

            if [[ "$FAIL" -gt 0 ]]; then
                echo -e "  ${YELLOW}Tip: Run './scripts/verify-custom-domain.sh --rollback' for rollback commands.${NC}"
                echo ""
            fi

            exit "$FAIL"
            ;;
    esac
}

main "$@"
