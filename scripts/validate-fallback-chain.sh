#!/bin/bash
# validate-fallback-chain.sh — Validate claude-agent fallback chain configuration
# Updated 2026-03-13 for new primary/backup settings architecture
#
# Validates the 2-tier fallback system: primary settings -> backup settings
# The wrapper reads configuration from ~/.openclaw/kurultai.json

set -o pipefail

TS=$(date '+%Y-%m-%d %H:%M:%S')
TS_ISO=$(date '+%Y-%m-%dT%H:%M:%S%z')
CLAUDE_AGENT_SCRIPT="${HOME}/.local/bin/claude-agent"
KURULTAI_JSON="${HOME}/.openclaw/kurultai.json"
MODE_FILE="${HOME}/.openclaw/claude/mode.json"
VALIDATION_LOG="${HOME}/.openclaw/logs/fallback-chain-validation.log"
mkdir -p "$(dirname "$VALIDATION_LOG")"

# Result tracking
VALIDATION_RESULT="valid"
VALIDATION_REASON=""
DETAILS=()

# ============================================================================
# CHECK 1: Wrapper script exists and is executable
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
        DETAILS+=("PASS: Wrapper script exists and is executable")
    fi
fi

# ============================================================================
# CHECK 2: Script has shebang
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
# CHECK 3: kurultai.json configuration exists
# ============================================================================
if [ ! -r "$KURULTAI_JSON" ]; then
    VALIDATION_RESULT="INVALID"
    VALIDATION_REASON="kurultai_json_missing"
    DETAILS+=("FAIL: kurultai.json not found: $KURULTAI_JSON")
else
    DETAILS+=("PASS: kurultai.json exists and is readable")

    # Extract primary and backup settings paths
    PRIMARY_SETTINGS=$(python3 -c "import json; print(json.load(open('$KURULTAI_JSON'))['execution']['primary_settings'])" 2>/dev/null)
    BACKUP_SETTINGS=$(python3 -c "import json; print(json.load(open('$KURULTAI_JSON'))['execution']['backup_settings'])" 2>/dev/null)

    if [ -z "$PRIMARY_SETTINGS" ]; then
        VALIDATION_RESULT="INVALID"
        VALIDATION_REASON="primary_settings_missing"
        DETAILS+=("FAIL: primary_settings not defined in kurultai.json")
    else
        DETAILS+=("PASS: Primary settings path: $PRIMARY_SETTINGS")
    fi

    if [ -z "$BACKUP_SETTINGS" ]; then
        VALIDATION_RESULT="INVALID"
        VALIDATION_REASON="backup_settings_missing"
        DETAILS+=("FAIL: backup_settings not defined in kurultai.json")
    else
        DETAILS+=("PASS: Backup settings path: $BACKUP_SETTINGS")
    fi
fi

# ============================================================================
# CHECK 4: Primary settings file exists and has auth
# ============================================================================
if [ -n "$PRIMARY_SETTINGS" ]; then
    if [ ! -r "$PRIMARY_SETTINGS" ]; then
        VALIDATION_RESULT="INVALID"
        VALIDATION_REASON="primary_file_missing"
        DETAILS+=("FAIL: Primary settings file not found: $PRIMARY_SETTINGS")
    else
        DETAILS+=("PASS: Primary settings file exists")

        # Check for auth token OR default Anthropic
        if grep -q "ANTHROPIC_AUTH_TOKEN" "$PRIMARY_SETTINGS"; then
            DETAILS+=("PASS: Primary settings has explicit ANTHROPIC_AUTH_TOKEN")
        elif grep -q "ANTHROPIC_BASE_URL" "$PRIMARY_SETTINGS"; then
            # Custom base URL requires explicit auth
            VALIDATION_RESULT="INVALID"
            VALIDATION_REASON="primary_auth_missing"
            DETAILS+=("FAIL: Primary uses custom base URL but missing ANTHROPIC_AUTH_TOKEN")
        else
            # Using default Anthropic - auth handled by Claude Code
            DETAILS+=("PASS: Primary uses default Anthropic auth")
        fi

        # Check for base URL (non-Anthropic provider)
        if grep -q "ANTHROPIC_BASE_URL" "$PRIMARY_SETTINGS"; then
            BASE_URL=$(grep "ANTHROPIC_BASE_URL" "$PRIMARY_SETTINGS" | head -1)
            DETAILS+=("INFO: Primary uses custom base URL")
        else
            DETAILS+=("INFO: Primary uses Anthropic default endpoint")
        fi
    fi
fi

# ============================================================================
# CHECK 5: Backup settings file exists and has auth
# ============================================================================
if [ -n "$BACKUP_SETTINGS" ]; then
    if [ ! -r "$BACKUP_SETTINGS" ]; then
        VALIDATION_RESULT="INVALID"
        VALIDATION_REASON="backup_file_missing"
        DETAILS+=("FAIL: Backup settings file not found: $BACKUP_SETTINGS")
    else
        DETAILS+=("PASS: Backup settings file exists")

        # Check for auth token OR default Anthropic
        if grep -q "ANTHROPIC_AUTH_TOKEN" "$BACKUP_SETTINGS"; then
            DETAILS+=("PASS: Backup settings has explicit ANTHROPIC_AUTH_TOKEN")
        elif grep -q "ANTHROPIC_BASE_URL" "$BACKUP_SETTINGS"; then
            # Custom base URL requires explicit auth
            VALIDATION_RESULT="INVALID"
            VALIDATION_REASON="backup_auth_missing"
            DETAILS+=("FAIL: Backup uses custom base URL but missing ANTHROPIC_AUTH_TOKEN")
        else
            # Using default Anthropic - auth handled by Claude Code
            DETAILS+=("PASS: Backup uses default Anthropic auth")
        fi
    fi
fi

# ============================================================================
# CHECK 6: Wrapper has fallback logic (primary -> backup)
# ============================================================================
if [ -f "$CLAUDE_AGENT_SCRIPT" ]; then
    # Check for run_claude function (new architecture)
    if grep -q "run_claude()" "$CLAUDE_AGENT_SCRIPT"; then
        DETAILS+=("PASS: Wrapper has run_claude() function")
    else
        DETAILS+=("WARN: Wrapper may not have run_claude() function")
    fi

    # Check for is_retryable_error function
    if grep -q "is_retryable_error()" "$CLAUDE_AGENT_SCRIPT"; then
        DETAILS+=("PASS: Wrapper has is_retryable_error() function")
    else
        DETAILS+=("WARN: Wrapper may not have is_retryable_error() function")
    fi

    # Check for primary -> backup fallback pattern
    if grep -q "run_claude.*PRIMARY" "$CLAUDE_AGENT_SCRIPT" && grep -q "run_claude.*BACKUP" "$CLAUDE_AGENT_SCRIPT"; then
        DETAILS+=("PASS: Wrapper has primary -> backup fallback pattern")
    else
        VALIDATION_RESULT="INVALID"
        VALIDATION_REASON="fallback_logic_missing"
        DETAILS+=("FAIL: Wrapper missing primary -> backup fallback logic")
    fi

    # Check for kurultai.json reading
    if grep -q "kurultai.json" "$CLAUDE_AGENT_SCRIPT"; then
        DETAILS+=("PASS: Wrapper reads kurultai.json for configuration")
    else
        DETAILS+=("WARN: Wrapper may not read kurultai.json")
    fi
fi

# ============================================================================
# CHECK 7: Mode file (optional)
# ============================================================================
if [ -r "$MODE_FILE" ]; then
    MODE=$(python3 -c "import json; print(json.load(open('$MODE_FILE')).get('mode','auto'))" 2>/dev/null || echo "auto")
    DETAILS+=("INFO: Current mode: $MODE")
else
    DETAILS+=("INFO: No mode.json (defaults to auto)")
fi

# ============================================================================
# CHECK 8: Endpoint health (check primary settings endpoint)
# ============================================================================
if [ -n "$PRIMARY_SETTINGS" ] && [ -r "$PRIMARY_SETTINGS" ]; then
    # Extract base URL from settings
    SETTINGS_URL=$(grep "ANTHROPIC_BASE_URL" "$PRIMARY_SETTINGS" | sed 's/.*: *"\([^"]*\)".*/\1/' | head -1)

    if [ -n "$SETTINGS_URL" ] && command -v curl >/dev/null 2>&1; then
        HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 --connect-timeout 3 "$SETTINGS_URL" 2>/dev/null || echo "0")
        if [[ "$HEALTH" == "0" ]]; then
            VALIDATION_RESULT="INVALID"
            VALIDATION_REASON="primary_endpoint_unreachable"
            DETAILS+=("FAIL: Primary endpoint unreachable (HTTP $HEALTH)")
        else
            DETAILS+=("PASS: Primary endpoint reachable (HTTP $HEALTH)")
        fi
    elif [ -z "$SETTINGS_URL" ]; then
        # Using Anthropic default - assume OK
        DETAILS+=("INFO: Primary uses Anthropic default endpoint (assumed OK)")
    fi
fi

# ============================================================================
# OUTPUT RESULTS
# ============================================================================

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
