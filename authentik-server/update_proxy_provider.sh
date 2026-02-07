#!/bin/bash

# Authentik Proxy Provider API Update Script
# ===========================================
# This script updates the Authentik Proxy Provider configuration via API
# without requiring database access.

set -e

# Configuration
AUTHENTIK_URL="${AUTHENTIK_URL:-https://unique-manifestation-production.up.railway.app}"
BOOTSTRAP_TOKEN="${AUTHENTIK_BOOTSTRAP_TOKEN:?AUTHENTIK_BOOTSTRAP_TOKEN must be set}"
PROVIDER_ID="${PROVIDER_ID:-1}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check dependencies
if ! command -v curl &> /dev/null; then
    log_error "curl is required but not installed"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    log_error "python3 is required but not installed"
    exit 1
fi

# Parse arguments
NEW_EXTERNAL_HOST=""
NEW_INTERNAL_HOST=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --external-host)
            NEW_EXTERNAL_HOST="$2"
            shift 2
            ;;
        --internal-host)
            NEW_INTERNAL_HOST="$2"
            shift 2
            ;;
        --provider-id)
            PROVIDER_ID="$2"
            shift 2
            ;;
        --show-current)
            log_info "Current Proxy Provider configuration:"
            curl -s -X GET "${AUTHENTIK_URL}/api/v3/providers/proxy/${PROVIDER_ID}/" \
                -H "Authorization: Bearer ${BOOTSTRAP_TOKEN}" | python3 -m json.tool
            exit 0
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo
            echo "Options:"
            echo "  --external-host URL    Set new external_host"
            echo "  --internal-host URL    Set new internal_host"
            echo "  --provider-id ID       Proxy Provider ID (default: 1)"
            echo "  --show-current         Show current configuration"
            echo
            echo "Environment variables:"
            echo "  AUTHENTIK_URL          Authentik API URL"
            echo "  AUTHENTIK_BOOTSTRAP_TOKEN  Bootstrap token"
            echo
            echo "Examples:"
            echo "  $0 --show-current"
            echo "  $0 --external-host https://example.com"
            echo "  $0 --external-host https://example.com --internal-host http://localhost:4180"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Get current configuration
log_info "Getting current Proxy Provider configuration..."
CURRENT_CONFIG=$(curl -s -X GET "${AUTHENTIK_URL}/api/v3/providers/proxy/${PROVIDER_ID}/" \
    -H "Authorization: Bearer ${BOOTSTRAP_TOKEN}")

if [ -z "$CURRENT_CONFIG" ]; then
    log_error "Failed to get current configuration. Check your AUTHENTIK_URL and BOOTSTRAP_TOKEN."
    exit 1
fi

# Extract current values
CURRENT_EXTERNAL_HOST=$(echo "$CURRENT_CONFIG" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('external_host', ''))")
CURRENT_INTERNAL_HOST=$(echo "$CURRENT_CONFIG" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('internal_host', ''))")

log_info "Current external_host: $CURRENT_EXTERNAL_HOST"
log_info "Current internal_host: $CURRENT_INTERNAL_HOST"

# Build update payload
if [ -z "$NEW_EXTERNAL_HOST" ] && [ -z "$NEW_INTERNAL_HOST" ]; then
    log_warn "No updates specified. Use --external-host or --internal-host"
    exit 0
fi

# Use current values if not specified
EXTERNAL_HOST="${NEW_EXTERNAL_HOST:-$CURRENT_EXTERNAL_HOST}"
INTERNAL_HOST="${NEW_INTERNAL_HOST:-$CURRENT_INTERNAL_HOST}"

# For external_host updates, we MUST include internal_host in the payload
if [ -n "$NEW_EXTERNAL_HOST" ] && [ -z "$NEW_INTERNAL_HOST" ]; then
    log_warn "When updating external_host, internal_host must also be provided"
    INTERNAL_HOST="$CURRENT_INTERNAL_HOST"
fi

# Perform update
log_info "Updating Proxy Provider..."
log_info "  external_host: $EXTERNAL_HOST"
log_info "  internal_host: $INTERNAL_HOST"

UPDATE_RESPONSE=$(curl -s -X PATCH "${AUTHENTIK_URL}/api/v3/providers/proxy/${PROVIDER_ID}/" \
    -H "Authorization: Bearer ${BOOTSTRAP_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
        \"external_host\": \"${EXTERNAL_HOST}\",
        \"internal_host\": \"${INTERNAL_HOST}\"
    }")

# Check for errors
if echo "$UPDATE_RESPONSE" | grep -q '"detail"'; then
    log_error "Update failed:"
    echo "$UPDATE_RESPONSE" | python3 -m json.tool
    exit 1
fi

# Verify update
log_info "Verifying update..."
VERIFY_RESPONSE=$(curl -s -X GET "${AUTHENTIK_URL}/api/v3/providers/proxy/${PROVIDER_ID}/" \
    -H "Authorization: Bearer ${BOOTSTRAP_TOKEN}")

UPDATED_EXTERNAL_HOST=$(echo "$VERIFY_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('external_host', ''))" 2>/dev/null || echo "error")
UPDATED_INTERNAL_HOST=$(echo "$VERIFY_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('internal_host', ''))" 2>/dev/null || echo "error")

if [ "$UPDATED_EXTERNAL_HOST" = "$EXTERNAL_HOST" ] && [ "$UPDATED_INTERNAL_HOST" = "$INTERNAL_HOST" ]; then
    log_info "Update successful!"
    log_info "  external_host: $UPDATED_EXTERNAL_HOST"
    log_info "  internal_host: $UPDATED_INTERNAL_HOST"
else
    log_warn "Update verification inconclusive"
    log_info "  Expected external_host: $EXTERNAL_HOST"
    log_info "  Got external_host: $UPDATED_EXTERNAL_HOST"
fi
