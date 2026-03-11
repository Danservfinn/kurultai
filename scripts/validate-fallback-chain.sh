#!/bin/bash
# validate-fallback-chain.sh — Validate claude-agent fallback chain configuration
# Updated 2026-03-09 to support vault-based configuration
#
# Validates the 3-tier fallback system: Anthropic -> Z.AI -> Alibaba
# The wrapper loads credentials from ~/.openclaw/credentials/provider.env

set -o pipefail

TS=$(date '+%Y-%m-%d %H:%M:%S')
TS_ISO=$(date '+%Y-%m-%dT%H:%M:%S%z')
CLAUDE_AGENT_SCRIPT="${HOME}/.local/bin/claude-agent"
VAULT_FILE="${HOME}/.openclaw/credentials/provider.env"
VALIDATION_LOG="${HOME}/.openclaw/logs/fallback-chain-validation.log"
mkdir -p "$(dirname "$VALIDATION_LOG")"

# Result tracking
VALIDATION_RESULT="valid"
VALIDATION_REASON=""
DETAILS=()

# Expected configuration
EXPECTED_TIER_0_MODEL="claude-sonnet-4-6"
EXPECTED_TIER_1_MODEL="glm-5"
EXPECTED_TIER_1_URL="https://api.z.ai/api/anthropic"
EXPECTED_TIER_2_MODEL="qwen3.5-plus"
EXPECTED_TIER_2_URL="https://coding-intl.dashscope.aliyuncs.com/apps/anthropic"

# ============================================================================
# CHECK 1: Script exists and is executable
# ============================================================================
if [ ! -f "$CLAUDE_AGENT_SCRIPT" ]; then
    VALIDATION_RESULT="INVALID"
    VALIDATION_REASON="script_missing"
    DETAILS+=("FAIL: ~/.local/bin/claude-agent does not exist")
else
    if [ ! -x "$CLAUDE_AGENT_SCRIPT" ]; then
        VALIDATION_RESULT="INVALID"
        VALIDATION_REASON="script_not_executable"
        DETAILS+=("FAIL: ~/.local/bin/claude-agent is not executable")
    else
        DETAILS+=("PASS: Script exists and is executable")
    fi
fi

# ============================================================================
# CHECK 2: Script has shebang pointing to bash/sh
# ============================================================================
if [ -f "$CLAUDE_AGENT_SCRIPT" ]; then
    FIRST_LINE=$(head -1 "$CLAUDE_AGENT_SCRIPT")
    if [[ "$FIRST_LINE" == "#!"* ]]; then
        DETAILS+=("PASS: Script has shebang: ${FIRST_LINE:0:40}...")
    else
        VALIDATION_RESULT="INVALID"
        VALIDATION_REASON="no_shebang"
        DETAILS+=("FAIL: Script missing shebang")
    fi
fi

# ============================================================================
# CHECK 3: Vault file exists and is readable
# ============================================================================
if [ ! -r "$VAULT_FILE" ]; then
    VALIDATION_RESULT="INVALID"
    VALIDATION_REASON="vault_missing"
    DETAILS+=("FAIL: Vault file not found: $VAULT_FILE")
else
    DETAILS+=("PASS: Vault file exists and is readable")
fi

# ============================================================================
# CHECK 4: Tier 0 configuration (Anthropic default)
# ============================================================================
if [ -r "$VAULT_FILE" ]; then
    if grep -q "^DEFAULT_MODEL=" "$VAULT_FILE"; then
        FOUND_DEFAULT=$(grep "^DEFAULT_MODEL=" "$VAULT_FILE" | cut -d'=' -f2)
        if [[ "$FOUND_DEFAULT" == "$EXPECTED_TIER_0_MODEL" ]]; then
            DETAILS+=("PASS: Tier 0 (default) model: $FOUND_DEFAULT")
        else
            DETAILS+=("WARN: Tier 0 model is '$FOUND_DEFAULT', expected '$EXPECTED_TIER_0_MODEL'")
        fi
    else
        DETAILS+=("INFO: DEFAULT_MODEL not in vault (uses hard-coded default)")
    fi
fi

# ============================================================================
# CHECK 5: Tier 1 configuration (Z.AI)
# ============================================================================
if [ -r "$VAULT_FILE" ]; then
    if grep -q "^ZAI_BASE_URL=" "$VAULT_FILE"; then
        FOUND_URL=$(grep "^ZAI_BASE_URL=" "$VAULT_FILE" | cut -d'=' -f2)
        if [[ "$FOUND_URL" == "$EXPECTED_TIER_1_URL" ]]; then
            DETAILS+=("PASS: Tier 1 (Z.AI) URL configured: $FOUND_URL")
        else
            DETAILS+=("WARN: Tier 1 URL is '$FOUND_URL', expected '$EXPECTED_TIER_1_URL'")
        fi
    else
        VALIDATION_RESULT="INVALID"
        VALIDATION_REASON="tier1_url_missing"
        DETAILS+=("FAIL: Tier 1 (Z.AI) URL not found in vault")
    fi

    if grep -q "^ZAI_MODEL=" "$VAULT_FILE"; then
        FOUND_MODEL=$(grep "^ZAI_MODEL=" "$VAULT_FILE" | cut -d'=' -f2)
        if [[ "$FOUND_MODEL" == "$EXPECTED_TIER_1_MODEL" ]]; then
            DETAILS+=("PASS: Tier 1 (Z.AI) model: $FOUND_MODEL")
        else
            DETAILS+=("INFO: Tier 1 model is '$FOUND_MODEL', expected '$EXPECTED_TIER_1_MODEL'")
        fi
    else
        DETAILS+=("INFO: Tier 1 model not in vault (will use default)")
    fi

    if grep -q "^ZAI_AUTH_TOKEN=" "$VAULT_FILE"; then
        DETAILS+=("PASS: Tier 1 (Z.AI) auth token configured")
    else
        VALIDATION_RESULT="INVALID"
        VALIDATION_REASON="tier1_token_missing"
        DETAILS+=("FAIL: Tier 1 (Z.AI) auth token not found")
    fi
fi

# ============================================================================
# CHECK 6: Tier 2 configuration (Alibaba)
# ============================================================================
if [ -r "$VAULT_FILE" ]; then
    if grep -q "^ALIBABA_BASE_URL=" "$VAULT_FILE"; then
        FOUND_URL=$(grep "^ALIBABA_BASE_URL=" "$VAULT_FILE" | cut -d'=' -f2)
        DETAILS+=("PASS: Tier 2 (Alibaba) URL configured")
    else
        VALIDATION_RESULT="INVALID"
        VALIDATION_REASON="tier2_url_missing"
        DETAILS+=("FAIL: Tier 2 (Alibaba) URL not found in vault")
    fi

    if grep -q "^ALIBABA_MODEL=" "$VAULT_FILE"; then
        FOUND_MODEL=$(grep "^ALIBABA_MODEL=" "$VAULT_FILE" | cut -d'=' -f2)
        if [[ "$FOUND_MODEL" == "$EXPECTED_TIER_2_MODEL" ]]; then
            DETAILS+=("PASS: Tier 2 (Alibaba) model: $FOUND_MODEL")
        else
            DETAILS+=("INFO: Tier 2 model is '$FOUND_MODEL', expected '$EXPECTED_TIER_2_MODEL'")
        fi
    else
        DETAILS+=("INFO: Tier 2 model not in vault (will use default)")
    fi

    if grep -q "^ALIBABA_AUTH_TOKEN=" "$VAULT_FILE"; then
        DETAILS+=("PASS: Tier 2 (Alibaba) auth token configured")
    else
        VALIDATION_RESULT="INVALID"
        VALIDATION_REASON="tier2_token_missing"
        DETAILS+=("FAIL: Tier 2 (Alibaba) auth token not found")
    fi
fi

# ============================================================================
# CHECK 7: Fallback chain order in wrapper script
# ============================================================================
if [ -f "$CLAUDE_AGENT_SCRIPT" ]; then
    # Check for the fallback loop
    if grep -q "for fallback in zai alibaba" "$CLAUDE_AGENT_SCRIPT"; then
        DETAILS+=("PASS: Fallback chain: 3-tier (default -> zai -> alibaba)")
    elif grep -q "for fallback in" "$CLAUDE_AGENT_SCRIPT"; then
        FALLBACK_LINE=$(grep "for fallback in" "$CLAUDE_AGENT_SCRIPT")
        DETAILS+=("WARN: Fallback loop found but may be non-standard: $FALLBACK_LINE")
    else
        VALIDATION_RESULT="INVALID"
        VALIDATION_REASON="fallback_chain_missing"
        DETAILS+=("FAIL: Fallback loop not found in wrapper script")
    fi

    # Check for apply_provider function with correct providers
    if grep -A 10 "apply_provider()" "$CLAUDE_AGENT_SCRIPT" | grep -q 'zai)'; then
        DETAILS+=("PASS: apply_provider supports 'zai' tier")
    else
        DETAILS+=("WARN: apply_provider may not support 'zai' tier")
    fi

    if grep -A 15 "apply_provider()" "$CLAUDE_AGENT_SCRIPT" | grep -q 'alibaba)'; then
        DETAILS+=("PASS: apply_provider supports 'alibaba' tier")
    else
        DETAILS+=("WARN: apply_provider may not support 'alibaba' tier")
    fi
fi

# ============================================================================
# CHECK 8: Proxy endpoint health
# ============================================================================
if command -v curl >/dev/null 2>&1; then
    ZAI_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 --connect-timeout 3 "$EXPECTED_TIER_1_URL" 2>/dev/null || echo "000")
    if [[ "$ZAI_HEALTH" == "000" ]]; then
        VALIDATION_RESULT="INVALID"
        VALIDATION_REASON="zai_endpoint_unreachable"
        DETAILS+=("FAIL: Z.AI endpoint unreachable (HTTP $ZAI_HEALTH)")
    elif [[ "$ZAI_HEALTH" == "40"* ]] || [[ "$ZAI_HEALTH" == "50"* ]]; then
        DETAILS+=("PASS: Z.AI endpoint reachable (HTTP $ZAI_HEALTH)")
    else
        DETAILS+=("PASS: Z.AI endpoint reachable (HTTP $ZAI_HEALTH)")
    fi

    ALIBABA_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 --connect-timeout 3 "$EXPECTED_TIER_2_URL" 2>/dev/null || echo "000")
    if [[ "$ALIBABA_HEALTH" == "000" ]]; then
        DETAILS+=("WARN: Alibaba endpoint unreachable (HTTP $ALIBABA_HEALTH) - Tier 2 fallback may fail")
    elif [[ "$ALIBABA_HEALTH" == "404" ]]; then
        DETAILS+=("WARN: Alibaba endpoint returns 404 - API URL may be incorrect or service changed")
    elif [[ "$ALIBABA_HEALTH" == "40"* ]] || [[ "$ALIBABA_HEALTH" == "50"* ]]; then
        DETAILS+=("INFO: Alibaba endpoint reachable (HTTP $ALIBABA_HEALTH)")
    else
        DETAILS+=("PASS: Alibaba endpoint reachable (HTTP $ALIBABA_HEALTH)")
    fi
else
    DETAILS+=("SKIP: Endpoint health checks (curl not available)")
fi

# ============================================================================
# OUTPUT RESULTS
# =============================================================================

# Log detailed results to validation log
{
    echo "=== Fallback Chain Validation: $TS_ISO ==="
    echo "Result: $VALIDATION_RESULT"
    if [ -n "$VALIDATION_REASON" ]; then
        echo "Reason: $VALIDATION_REASON"
    fi
    echo ""
    for detail in "${DETAILS[@]}"; do
        echo "  $detail"
    done
    echo ""
} >> "$VALIDATION_LOG"

# Output one-line result for tock.log consumption
echo "$VALIDATION_RESULT|$VALIDATION_REASON"
