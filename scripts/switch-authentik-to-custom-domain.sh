#!/bin/bash
# =============================================================================
# switch-authentik-to-custom-domain.sh
# =============================================================================
# Switches Authentik reverse proxy configuration from Railway URL to
# the custom domain kublai.kurult.ai after SSL certificate is issued.
#
# ARCHITECTURE:
#   Client -> Railway (TLS) -> Caddy (authentik-proxy) -> forward_auth -> Authentik
#                                                      -> reverse_proxy -> OpenClaw (moltbot:18789)
#
# WHAT THIS SCRIPT DOES:
#   1. Verifies SSL certificate is valid on kublai.kurult.ai
#   2. Authenticates to Authentik admin API via 3-step flow auth
#   3. PATCHes proxy provider external_host to https://kublai.kurult.ai
#   4. PATCHes brand domain to kublai.kurult.ai
#   5. Validates the full auth redirect chain on the custom domain
#
# PREREQUISITES:
#   - AUTHENTIK_BOOTSTRAP_PASSWORD env var set (or pass as argument)
#   - curl and jq installed
#   - SSL cert already provisioned by Railway for kublai.kurult.ai
#
# USAGE:
#   export AUTHENTIK_BOOTSTRAP_PASSWORD="your-password-here"
#   ./scripts/switch-authentik-to-custom-domain.sh
#
#   Or pass password as argument:
#   ./scripts/switch-authentik-to-custom-domain.sh --password "your-password-here"
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CUSTOM_DOMAIN="kublai.kurult.ai"
TARGET_URL="https://${CUSTOM_DOMAIN}"

# The current Railway URL where Authentik API is reachable.
# This is the authentik-proxy service's Railway-assigned domain.
RAILWAY_URL="${AUTHENTIK_RAILWAY_URL:-https://authentik-proxy-production-06a7.up.railway.app}"

# Authentik API base -- we authenticate through the proxy, which routes
# /api/v3/* to authentik-server internally.
AUTHENTIK_API_BASE="${RAILWAY_URL}"

# Provider and Brand IDs (known from previous configuration)
PROVIDER_ID="1"
BRAND_UUID="bed854f1-e54b-4616-adfb-c667a42b2b13"

# Bootstrap password (from env or argument)
BOOTSTRAP_PASSWORD="${AUTHENTIK_BOOTSTRAP_PASSWORD:-}"

# Timeouts
CURL_TIMEOUT=30
SSL_CHECK_RETRIES=5
SSL_CHECK_INTERVAL=10

# ---------------------------------------------------------------------------
# Colors and logging
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log_step()    { echo -e "\n${BLUE}${BOLD}[STEP $1]${NC} $2"; }
log_info()    { echo -e "  ${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "  ${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "  ${RED}[FAIL]${NC} $1"; }
log_detail()  { echo -e "         $1"; }

# Cookie jar for session persistence across flow auth steps
COOKIE_JAR=$(mktemp /tmp/authentik-cookies.XXXXXX)
trap 'rm -f "$COOKIE_JAR"' EXIT

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case $1 in
        --password)
            BOOTSTRAP_PASSWORD="$2"
            shift 2
            ;;
        --railway-url)
            RAILWAY_URL="$2"
            AUTHENTIK_API_BASE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-ssl-check)
            SKIP_SSL_CHECK=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --password PASSWORD    Authentik bootstrap password (or set AUTHENTIK_BOOTSTRAP_PASSWORD)"
            echo "  --railway-url URL      Override Railway URL for Authentik API access"
            echo "  --dry-run              Show what would be done without making changes"
            echo "  --skip-ssl-check       Skip SSL certificate verification (use with caution)"
            echo "  --help                 Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

DRY_RUN="${DRY_RUN:-false}"
SKIP_SSL_CHECK="${SKIP_SSL_CHECK:-false}"

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
log_step "0" "Preflight checks"

# Check dependencies
for cmd in curl jq; do
    if ! command -v "$cmd" &>/dev/null; then
        log_error "$cmd is required but not installed."
        exit 1
    fi
done
log_success "curl and jq are installed"

# Check password
if [[ -z "$BOOTSTRAP_PASSWORD" ]]; then
    log_error "AUTHENTIK_BOOTSTRAP_PASSWORD is not set."
    log_detail "Set it via: export AUTHENTIK_BOOTSTRAP_PASSWORD='your-password'"
    log_detail "Or pass it: $0 --password 'your-password'"
    exit 1
fi
log_success "Bootstrap password is set"

# Verify Railway URL is reachable
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    --max-time "$CURL_TIMEOUT" \
    "${RAILWAY_URL}/-/health/ready/" 2>/dev/null || echo "000")

if [[ "$HTTP_CODE" == "200" ]]; then
    log_success "Authentik is reachable at ${RAILWAY_URL} (HTTP $HTTP_CODE)"
elif [[ "$HTTP_CODE" == "204" ]]; then
    log_success "Authentik is reachable at ${RAILWAY_URL} (HTTP $HTTP_CODE - no content, OK)"
else
    log_warn "Authentik health check returned HTTP $HTTP_CODE at ${RAILWAY_URL}"
    log_detail "This may be fine if the health endpoint is behind auth."
    log_detail "Attempting to continue..."
fi

echo ""
echo -e "${BOLD}Configuration Summary:${NC}"
echo "  Custom domain:    ${CUSTOM_DOMAIN}"
echo "  Target URL:       ${TARGET_URL}"
echo "  Railway URL:      ${RAILWAY_URL}"
echo "  Provider ID:      ${PROVIDER_ID}"
echo "  Brand UUID:       ${BRAND_UUID}"
echo "  Dry run:          ${DRY_RUN}"


# =============================================================================
# STEP 1: Verify SSL Certificate
# =============================================================================
log_step "1" "Verify SSL certificate for ${CUSTOM_DOMAIN}"

if [[ "$SKIP_SSL_CHECK" == "true" ]]; then
    log_warn "SSL check skipped (--skip-ssl-check flag)"
else
    SSL_VALID=false
    for attempt in $(seq 1 "$SSL_CHECK_RETRIES"); do
        log_info "Checking SSL certificate (attempt ${attempt}/${SSL_CHECK_RETRIES})..."

        # Use curl to verify SSL. We connect to the domain and check if TLS succeeds.
        # The page itself may redirect or return any status -- we only care about TLS.
        SSL_OUTPUT=$(curl -sS -o /dev/null -w "%{ssl_verify_result}|%{http_code}" \
            --max-time "$CURL_TIMEOUT" \
            "https://${CUSTOM_DOMAIN}/" 2>&1 || true)

        SSL_VERIFY=$(echo "$SSL_OUTPUT" | cut -d'|' -f1)
        HTTP_STATUS=$(echo "$SSL_OUTPUT" | cut -d'|' -f2)

        if [[ "$SSL_VERIFY" == "0" ]]; then
            SSL_VALID=true
            log_success "SSL certificate is valid (verify_result=0, HTTP ${HTTP_STATUS})"

            # Extract certificate details
            CERT_INFO=$(echo | openssl s_client -servername "$CUSTOM_DOMAIN" \
                -connect "${CUSTOM_DOMAIN}:443" 2>/dev/null | \
                openssl x509 -noout -subject -dates 2>/dev/null || echo "Could not extract cert details")

            if [[ -n "$CERT_INFO" ]]; then
                log_detail "Certificate details:"
                echo "$CERT_INFO" | while IFS= read -r line; do
                    log_detail "  $line"
                done
            fi
            break
        else
            log_warn "SSL verify failed (result=${SSL_VERIFY}). Retrying in ${SSL_CHECK_INTERVAL}s..."
            sleep "$SSL_CHECK_INTERVAL"
        fi
    done

    if [[ "$SSL_VALID" != "true" ]]; then
        log_error "SSL certificate is NOT valid for ${CUSTOM_DOMAIN} after ${SSL_CHECK_RETRIES} attempts."
        log_detail ""
        log_detail "Possible causes:"
        log_detail "  1. CNAME record not pointing to correct Railway target"
        log_detail "     Run: dig ${CUSTOM_DOMAIN} CNAME"
        log_detail "  2. Railway cert provisioning still in progress"
        log_detail "     Check Railway dashboard -> authentik-proxy -> Settings -> Domains"
        log_detail "  3. DNS propagation not complete"
        log_detail "     Run: dig +trace ${CUSTOM_DOMAIN}"
        log_detail ""
        log_detail "To proceed anyway (not recommended): $0 --skip-ssl-check"
        exit 1
    fi
fi


# =============================================================================
# STEP 2: Authenticate to Authentik Admin via Flow API (3-step)
# =============================================================================
log_step "2" "Authenticate to Authentik admin API"

# --- Step 2a: Start the authentication flow ---
log_info "Step 2a: Starting authentication flow..."

FLOW_RESPONSE=$(curl -s --max-time "$CURL_TIMEOUT" \
    -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
    -H "Accept: application/json" \
    -H "Referer: ${AUTHENTIK_API_BASE}/" \
    "${AUTHENTIK_API_BASE}/api/v3/flows/executor/default-authentication-flow/?query=")

FLOW_TYPE=$(echo "$FLOW_RESPONSE" | jq -r '.type // empty' 2>/dev/null)
FLOW_COMPONENT=$(echo "$FLOW_RESPONSE" | jq -r '.component // empty' 2>/dev/null)

if [[ "$FLOW_TYPE" != "native" ]] || [[ "$FLOW_COMPONENT" != "ak-stage-identification" ]]; then
    log_error "Unexpected flow challenge response."
    log_detail "Expected: type=native, component=ak-stage-identification"
    log_detail "Got: type=${FLOW_TYPE}, component=${FLOW_COMPONENT}"
    log_detail "Full response:"
    echo "$FLOW_RESPONSE" | jq . 2>/dev/null || echo "$FLOW_RESPONSE"
    exit 1
fi

log_success "Got identification challenge (component: ${FLOW_COMPONENT})"

# --- Step 2b: Submit username ---
log_info "Step 2b: Submitting username (akadmin)..."

# Extract CSRF token from cookies
CSRF_TOKEN=$(grep -i "authentik_csrf" "$COOKIE_JAR" | awk '{print $NF}' || echo "")

USERNAME_RESPONSE=$(curl -s --max-time "$CURL_TIMEOUT" \
    -X POST \
    -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -H "Referer: ${AUTHENTIK_API_BASE}/" \
    ${CSRF_TOKEN:+-H "X-authentik-CSRF: ${CSRF_TOKEN}"} \
    -d '{"component": "ak-stage-identification", "uid_field": "akadmin"}' \
    "${AUTHENTIK_API_BASE}/api/v3/flows/executor/default-authentication-flow/")

USERNAME_COMPONENT=$(echo "$USERNAME_RESPONSE" | jq -r '.component // empty' 2>/dev/null)

if [[ "$USERNAME_COMPONENT" != "ak-stage-password" ]]; then
    log_error "Unexpected response after username submission."
    log_detail "Expected: component=ak-stage-password"
    log_detail "Got: component=${USERNAME_COMPONENT}"
    log_detail "Full response:"
    echo "$USERNAME_RESPONSE" | jq . 2>/dev/null || echo "$USERNAME_RESPONSE"
    exit 1
fi

log_success "Username accepted, got password challenge"

# --- Step 2c: Submit password ---
log_info "Step 2c: Submitting password..."

# Re-read CSRF token (may have been updated)
CSRF_TOKEN=$(grep -i "authentik_csrf" "$COOKIE_JAR" | awk '{print $NF}' || echo "")

PASSWORD_RESPONSE=$(curl -s --max-time "$CURL_TIMEOUT" \
    -X POST \
    -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -H "Referer: ${AUTHENTIK_API_BASE}/" \
    ${CSRF_TOKEN:+-H "X-authentik-CSRF: ${CSRF_TOKEN}"} \
    -d "{\"component\": \"ak-stage-password\", \"password\": $(echo "$BOOTSTRAP_PASSWORD" | jq -Rs .)}" \
    "${AUTHENTIK_API_BASE}/api/v3/flows/executor/default-authentication-flow/")

# Check if authentication succeeded.
# A successful auth returns a redirect or a response with type "redirect".
PASSWORD_TYPE=$(echo "$PASSWORD_RESPONSE" | jq -r '.type // empty' 2>/dev/null)
PASSWORD_STATUS=$(echo "$PASSWORD_RESPONSE" | jq -r '.status // empty' 2>/dev/null)

# Authentik returns type=redirect on success, or we get a session cookie
if [[ "$PASSWORD_TYPE" == "redirect" ]] || [[ "$PASSWORD_STATUS" == "200" ]]; then
    log_success "Authentication successful (type: ${PASSWORD_TYPE:-direct})"
else
    # Check if we got an error
    ERROR_MSG=$(echo "$PASSWORD_RESPONSE" | jq -r '.response_errors // empty' 2>/dev/null)
    if [[ -n "$ERROR_MSG" ]] && [[ "$ERROR_MSG" != "null" ]] && [[ "$ERROR_MSG" != "" ]]; then
        log_error "Authentication failed."
        log_detail "Error: ${ERROR_MSG}"
        exit 1
    fi
    # Some Authentik versions return different success indicators
    log_warn "Unexpected auth response type '${PASSWORD_TYPE}', attempting to continue..."
    log_detail "Response: $(echo "$PASSWORD_RESPONSE" | jq -c . 2>/dev/null || echo "$PASSWORD_RESPONSE")"
fi

# Re-read CSRF token after auth (this is the admin session CSRF)
CSRF_TOKEN=$(grep -i "authentik_csrf" "$COOKIE_JAR" | awk '{print $NF}' || echo "")

if [[ -z "$CSRF_TOKEN" ]]; then
    log_warn "No CSRF token found in cookies. API calls may fail."
    log_detail "Cookie jar contents:"
    cat "$COOKIE_JAR" | grep -v "^#" || true
fi

# --- Verify admin access ---
log_info "Verifying admin API access..."

ME_RESPONSE=$(curl -s --max-time "$CURL_TIMEOUT" \
    -b "$COOKIE_JAR" \
    -H "Accept: application/json" \
    -H "Referer: ${AUTHENTIK_API_BASE}/" \
    "${AUTHENTIK_API_BASE}/api/v3/core/users/me/")

MY_USERNAME=$(echo "$ME_RESPONSE" | jq -r '.user.username // empty' 2>/dev/null)
MY_IS_SUPERUSER=$(echo "$ME_RESPONSE" | jq -r '.user.is_superuser // false' 2>/dev/null)

if [[ "$MY_USERNAME" == "akadmin" ]]; then
    log_success "Authenticated as: ${MY_USERNAME} (superuser: ${MY_IS_SUPERUSER})"
else
    log_error "Failed to verify admin access."
    log_detail "Expected username: akadmin"
    log_detail "Got: ${MY_USERNAME:-<empty>}"
    log_detail "Response: $(echo "$ME_RESPONSE" | jq -c . 2>/dev/null || echo "$ME_RESPONSE")"
    exit 1
fi


# =============================================================================
# STEP 3: Read current provider configuration
# =============================================================================
log_step "3" "Read current proxy provider configuration"

PROVIDER_RESPONSE=$(curl -s --max-time "$CURL_TIMEOUT" \
    -b "$COOKIE_JAR" \
    -H "Accept: application/json" \
    -H "Referer: ${AUTHENTIK_API_BASE}/" \
    "${AUTHENTIK_API_BASE}/api/v3/providers/proxy/${PROVIDER_ID}/")

CURRENT_EXTERNAL=$(echo "$PROVIDER_RESPONSE" | jq -r '.external_host // empty' 2>/dev/null)
CURRENT_INTERNAL=$(echo "$PROVIDER_RESPONSE" | jq -r '.internal_host // empty' 2>/dev/null)
PROVIDER_NAME=$(echo "$PROVIDER_RESPONSE" | jq -r '.name // empty' 2>/dev/null)

if [[ -z "$PROVIDER_NAME" ]]; then
    log_error "Could not read proxy provider (ID: ${PROVIDER_ID})"
    log_detail "Response: $(echo "$PROVIDER_RESPONSE" | jq -c . 2>/dev/null || echo "$PROVIDER_RESPONSE")"
    exit 1
fi

log_success "Current provider: ${PROVIDER_NAME}"
log_detail "  external_host: ${CURRENT_EXTERNAL}"
log_detail "  internal_host: ${CURRENT_INTERNAL}"

if [[ "$CURRENT_EXTERNAL" == "$TARGET_URL" ]]; then
    log_warn "Provider external_host is already set to ${TARGET_URL}"
    log_detail "No update needed for provider."
    PROVIDER_ALREADY_SET=true
else
    PROVIDER_ALREADY_SET=false
fi


# =============================================================================
# STEP 4: Update proxy provider external_host
# =============================================================================
log_step "4" "Update proxy provider external_host"

if [[ "$PROVIDER_ALREADY_SET" == "true" ]]; then
    log_info "Skipping provider update (already set to target)"
elif [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY RUN] Would PATCH /api/v3/providers/proxy/${PROVIDER_ID}/"
    log_detail "  external_host: ${CURRENT_EXTERNAL} -> ${TARGET_URL}"
else
    log_info "Updating provider external_host to ${TARGET_URL}..."

    # Re-read CSRF token
    CSRF_TOKEN=$(grep -i "authentik_csrf" "$COOKIE_JAR" | awk '{print $NF}' || echo "")

    PATCH_PROVIDER_RESPONSE=$(curl -s --max-time "$CURL_TIMEOUT" \
        -X PATCH \
        -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        -H "Referer: ${AUTHENTIK_API_BASE}/" \
        ${CSRF_TOKEN:+-H "X-authentik-CSRF: ${CSRF_TOKEN}"} \
        -d "{\"external_host\": \"${TARGET_URL}\", \"internal_host\": \"${CURRENT_INTERNAL}\"}" \
        "${AUTHENTIK_API_BASE}/api/v3/providers/proxy/${PROVIDER_ID}/")

    UPDATED_EXTERNAL=$(echo "$PATCH_PROVIDER_RESPONSE" | jq -r '.external_host // empty' 2>/dev/null)

    if [[ "$UPDATED_EXTERNAL" == "$TARGET_URL" ]]; then
        log_success "Provider external_host updated to ${TARGET_URL}"
    else
        # Check for error
        ERROR_DETAIL=$(echo "$PATCH_PROVIDER_RESPONSE" | jq -r '.detail // empty' 2>/dev/null)
        if [[ -n "$ERROR_DETAIL" ]] && [[ "$ERROR_DETAIL" != "null" ]]; then
            log_error "Provider update failed: ${ERROR_DETAIL}"
            log_detail "Full response:"
            echo "$PATCH_PROVIDER_RESPONSE" | jq . 2>/dev/null || echo "$PATCH_PROVIDER_RESPONSE"
            exit 1
        fi
        log_warn "Provider update response did not confirm new value."
        log_detail "Expected: ${TARGET_URL}"
        log_detail "Got: ${UPDATED_EXTERNAL:-<empty>}"
        log_detail "Full response:"
        echo "$PATCH_PROVIDER_RESPONSE" | jq . 2>/dev/null || echo "$PATCH_PROVIDER_RESPONSE"
    fi
fi


# =============================================================================
# STEP 5: Read current brand configuration
# =============================================================================
log_step "5" "Read current brand configuration"

BRAND_RESPONSE=$(curl -s --max-time "$CURL_TIMEOUT" \
    -b "$COOKIE_JAR" \
    -H "Accept: application/json" \
    -H "Referer: ${AUTHENTIK_API_BASE}/" \
    "${AUTHENTIK_API_BASE}/api/v3/core/brands/${BRAND_UUID}/")

CURRENT_BRAND_DOMAIN=$(echo "$BRAND_RESPONSE" | jq -r '.domain // empty' 2>/dev/null)
BRAND_NAME=$(echo "$BRAND_RESPONSE" | jq -r '.branding_title // empty' 2>/dev/null)

if [[ -z "$CURRENT_BRAND_DOMAIN" ]] || [[ "$CURRENT_BRAND_DOMAIN" == "null" ]]; then
    log_error "Could not read brand (UUID: ${BRAND_UUID})"
    log_detail "Response: $(echo "$BRAND_RESPONSE" | jq -c . 2>/dev/null || echo "$BRAND_RESPONSE")"

    # Try listing all brands to find the right one
    log_info "Listing all brands to find the correct UUID..."
    ALL_BRANDS=$(curl -s --max-time "$CURL_TIMEOUT" \
        -b "$COOKIE_JAR" \
        -H "Accept: application/json" \
        -H "Referer: ${AUTHENTIK_API_BASE}/" \
        "${AUTHENTIK_API_BASE}/api/v3/core/brands/")

    echo "$ALL_BRANDS" | jq '.results[] | {brand_uuid: .brand_uuid, domain: .domain, branding_title: .branding_title}' 2>/dev/null || echo "$ALL_BRANDS"
    exit 1
fi

log_success "Current brand: ${BRAND_NAME:-<unnamed>}"
log_detail "  domain: ${CURRENT_BRAND_DOMAIN}"

if [[ "$CURRENT_BRAND_DOMAIN" == "$CUSTOM_DOMAIN" ]]; then
    log_warn "Brand domain is already set to ${CUSTOM_DOMAIN}"
    log_detail "No update needed for brand."
    BRAND_ALREADY_SET=true
else
    BRAND_ALREADY_SET=false
fi


# =============================================================================
# STEP 6: Update brand domain
# =============================================================================
log_step "6" "Update brand domain"

if [[ "$BRAND_ALREADY_SET" == "true" ]]; then
    log_info "Skipping brand update (already set to target)"
elif [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY RUN] Would PATCH /api/v3/core/brands/${BRAND_UUID}/"
    log_detail "  domain: ${CURRENT_BRAND_DOMAIN} -> ${CUSTOM_DOMAIN}"
else
    log_info "Updating brand domain to ${CUSTOM_DOMAIN}..."

    # Re-read CSRF token
    CSRF_TOKEN=$(grep -i "authentik_csrf" "$COOKIE_JAR" | awk '{print $NF}' || echo "")

    PATCH_BRAND_RESPONSE=$(curl -s --max-time "$CURL_TIMEOUT" \
        -X PATCH \
        -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        -H "Referer: ${AUTHENTIK_API_BASE}/" \
        ${CSRF_TOKEN:+-H "X-authentik-CSRF: ${CSRF_TOKEN}"} \
        -d "{\"domain\": \"${CUSTOM_DOMAIN}\"}" \
        "${AUTHENTIK_API_BASE}/api/v3/core/brands/${BRAND_UUID}/")

    UPDATED_BRAND_DOMAIN=$(echo "$PATCH_BRAND_RESPONSE" | jq -r '.domain // empty' 2>/dev/null)

    if [[ "$UPDATED_BRAND_DOMAIN" == "$CUSTOM_DOMAIN" ]]; then
        log_success "Brand domain updated to ${CUSTOM_DOMAIN}"
    else
        ERROR_DETAIL=$(echo "$PATCH_BRAND_RESPONSE" | jq -r '.detail // empty' 2>/dev/null)
        if [[ -n "$ERROR_DETAIL" ]] && [[ "$ERROR_DETAIL" != "null" ]]; then
            log_error "Brand update failed: ${ERROR_DETAIL}"
            log_detail "Full response:"
            echo "$PATCH_BRAND_RESPONSE" | jq . 2>/dev/null || echo "$PATCH_BRAND_RESPONSE"
            exit 1
        fi
        log_warn "Brand update response did not confirm new value."
        log_detail "Expected: ${CUSTOM_DOMAIN}"
        log_detail "Got: ${UPDATED_BRAND_DOMAIN:-<empty>}"
        log_detail "Full response:"
        echo "$PATCH_BRAND_RESPONSE" | jq . 2>/dev/null || echo "$PATCH_BRAND_RESPONSE"
    fi
fi


# =============================================================================
# STEP 7: Verify updated configuration
# =============================================================================
log_step "7" "Verify updated configuration"

# Re-read provider
VERIFY_PROVIDER=$(curl -s --max-time "$CURL_TIMEOUT" \
    -b "$COOKIE_JAR" \
    -H "Accept: application/json" \
    -H "Referer: ${AUTHENTIK_API_BASE}/" \
    "${AUTHENTIK_API_BASE}/api/v3/providers/proxy/${PROVIDER_ID}/")

VERIFY_EXTERNAL=$(echo "$VERIFY_PROVIDER" | jq -r '.external_host // empty' 2>/dev/null)
VERIFY_INTERNAL=$(echo "$VERIFY_PROVIDER" | jq -r '.internal_host // empty' 2>/dev/null)

# Re-read brand
VERIFY_BRAND=$(curl -s --max-time "$CURL_TIMEOUT" \
    -b "$COOKIE_JAR" \
    -H "Accept: application/json" \
    -H "Referer: ${AUTHENTIK_API_BASE}/" \
    "${AUTHENTIK_API_BASE}/api/v3/core/brands/${BRAND_UUID}/")

VERIFY_DOMAIN=$(echo "$VERIFY_BRAND" | jq -r '.domain // empty' 2>/dev/null)

echo ""
echo -e "${BOLD}Final Configuration State:${NC}"
echo "  Provider external_host: ${VERIFY_EXTERNAL}"
echo "  Provider internal_host: ${VERIFY_INTERNAL}"
echo "  Brand domain:           ${VERIFY_DOMAIN}"
echo ""

ERRORS=0

if [[ "$VERIFY_EXTERNAL" != "$TARGET_URL" ]]; then
    log_error "Provider external_host mismatch: expected ${TARGET_URL}, got ${VERIFY_EXTERNAL}"
    ERRORS=$((ERRORS + 1))
else
    log_success "Provider external_host: ${VERIFY_EXTERNAL}"
fi

if [[ "$VERIFY_DOMAIN" != "$CUSTOM_DOMAIN" ]]; then
    log_error "Brand domain mismatch: expected ${CUSTOM_DOMAIN}, got ${VERIFY_DOMAIN}"
    ERRORS=$((ERRORS + 1))
else
    log_success "Brand domain: ${VERIFY_DOMAIN}"
fi

if [[ "$VERIFY_INTERNAL" != "http://moltbot-railway-template.railway.internal:18789" ]]; then
    log_warn "Provider internal_host is ${VERIFY_INTERNAL}"
    log_detail "Expected: http://moltbot-railway-template.railway.internal:18789"
    log_detail "This may be fine if you are using a different internal routing."
fi


# =============================================================================
# STEP 8: Test the full auth flow on the custom domain
# =============================================================================
log_step "8" "Test auth flow on custom domain"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY RUN] Would test ${TARGET_URL}"
else
    # Test 1: Health endpoint (bypasses auth in Caddyfile)
    log_info "Test 1: Health endpoint..."
    HEALTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        --max-time "$CURL_TIMEOUT" \
        "${TARGET_URL}/health" 2>/dev/null || echo "000")

    if [[ "$HEALTH_CODE" == "200" ]]; then
        log_success "Health endpoint: HTTP ${HEALTH_CODE}"
    else
        log_warn "Health endpoint: HTTP ${HEALTH_CODE} (may be behind auth)"
    fi

    # Test 2: Root URL should redirect to Authentik login
    log_info "Test 2: Auth redirect on root URL..."
    ROOT_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}|%{redirect_url}" \
        --max-time "$CURL_TIMEOUT" \
        -L --max-redirs 0 \
        "${TARGET_URL}/" 2>/dev/null || echo "000|")

    ROOT_CODE=$(echo "$ROOT_RESPONSE" | cut -d'|' -f1)
    ROOT_REDIRECT=$(echo "$ROOT_RESPONSE" | cut -d'|' -f2)

    if [[ "$ROOT_CODE" == "302" ]] || [[ "$ROOT_CODE" == "303" ]] || [[ "$ROOT_CODE" == "307" ]]; then
        log_success "Root URL redirects (HTTP ${ROOT_CODE})"
        if echo "$ROOT_REDIRECT" | grep -q "outpost.goauthentik.io\|/flows/"; then
            log_success "Redirect points to Authentik flow: ${ROOT_REDIRECT}"
        else
            log_detail "Redirect URL: ${ROOT_REDIRECT}"
        fi
    elif [[ "$ROOT_CODE" == "200" ]]; then
        log_warn "Root URL returned 200 (auth may not be enforcing)"
    elif [[ "$ROOT_CODE" == "401" ]] || [[ "$ROOT_CODE" == "403" ]]; then
        log_success "Root URL returns ${ROOT_CODE} (auth is enforcing)"
    else
        log_warn "Root URL returned HTTP ${ROOT_CODE}"
    fi

    # Test 3: Authentik admin UI should be accessible
    log_info "Test 3: Authentik admin interface..."
    ADMIN_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        --max-time "$CURL_TIMEOUT" \
        "${TARGET_URL}/if/admin/" 2>/dev/null || echo "000")

    if [[ "$ADMIN_CODE" == "200" ]] || [[ "$ADMIN_CODE" == "302" ]] || [[ "$ADMIN_CODE" == "303" ]]; then
        log_success "Admin UI accessible: HTTP ${ADMIN_CODE}"
    else
        log_warn "Admin UI returned HTTP ${ADMIN_CODE}"
    fi

    # Test 4: API endpoint should be accessible
    log_info "Test 4: Authentik API via custom domain..."
    API_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        --max-time "$CURL_TIMEOUT" \
        "${TARGET_URL}/api/v3/root/config/" 2>/dev/null || echo "000")

    if [[ "$API_CODE" == "200" ]]; then
        log_success "API accessible: HTTP ${API_CODE}"
    else
        log_warn "API returned HTTP ${API_CODE}"
    fi

    # Test 5: WebSocket endpoint should be accessible (OpenClaw)
    log_info "Test 5: WebSocket endpoint availability..."
    WS_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        --max-time "$CURL_TIMEOUT" \
        -H "Upgrade: websocket" \
        -H "Connection: Upgrade" \
        "${TARGET_URL}/ws/" 2>/dev/null || echo "000")

    if [[ "$WS_CODE" == "101" ]] || [[ "$WS_CODE" == "400" ]] || [[ "$WS_CODE" == "426" ]]; then
        log_success "WebSocket endpoint responded: HTTP ${WS_CODE}"
    else
        log_warn "WebSocket endpoint: HTTP ${WS_CODE}"
    fi
fi


# =============================================================================
# SUMMARY
# =============================================================================
echo ""
echo -e "${BOLD}============================================${NC}"
if [[ "$DRY_RUN" == "true" ]]; then
    echo -e "${BOLD}  DRY RUN COMPLETE${NC}"
else
    if [[ "$ERRORS" -eq 0 ]]; then
        echo -e "${GREEN}${BOLD}  DOMAIN SWITCH COMPLETE${NC}"
    else
        echo -e "${YELLOW}${BOLD}  DOMAIN SWITCH COMPLETED WITH WARNINGS${NC}"
    fi
fi
echo -e "${BOLD}============================================${NC}"
echo ""
echo "  Provider:  ${VERIFY_EXTERNAL:-${TARGET_URL} (dry run)}"
echo "  Brand:     ${VERIFY_DOMAIN:-${CUSTOM_DOMAIN} (dry run)}"
echo "  Internal:  ${VERIFY_INTERNAL:-unchanged (dry run)}"
echo ""

if [[ "$DRY_RUN" != "true" ]] && [[ "$ERRORS" -eq 0 ]]; then
    echo -e "${BOLD}Next steps:${NC}"
    echo "  1. Open ${TARGET_URL} in a browser"
    echo "  2. You should be redirected to the Authentik login page"
    echo "  3. Log in with akadmin and verify access to the OpenClaw gateway"
    echo "  4. Test WebSocket connectivity for chat functionality"
    echo ""
    echo -e "${BOLD}Rollback:${NC}"
    echo "  If something is wrong, revert to Railway URL:"
    echo "  $0 --railway-url '${RAILWAY_URL}' \\"
    echo "    --password '\$AUTHENTIK_BOOTSTRAP_PASSWORD'"
    echo "  Then manually PATCH provider back to Railway URL."
    echo ""
fi

if [[ "$DRY_RUN" == "true" ]]; then
    echo "  Run without --dry-run to apply changes."
fi

exit "$ERRORS"
