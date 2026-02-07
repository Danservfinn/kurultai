#!/bin/sh
# Moltbot entrypoint - runs migrations, extracts Signal data, then starts OpenClaw gateway
# Runs as root initially to handle volume permissions, then drops to moltbot user

OPENCLAW_STATE_DIR="${OPENCLAW_STATE_DIR:-/data/.openclaw}"

# Ensure data directories exist with proper permissions
mkdir -p "$OPENCLAW_STATE_DIR" 2>/dev/null || true
mkdir -p /data/logs 2>/dev/null || true
mkdir -p /data/workspace 2>/dev/null || true

# Skills directory for hot-reload (shared with skill-sync-service)
SKILLS_DIR="${SKILLS_DIR:-/data/skills}"
mkdir -p "$SKILLS_DIR" 2>/dev/null || true
chown -R 1001:1001 /data 2>/dev/null || true
echo "Skills directory: $SKILLS_DIR"

# =============================================================================
# RUN NEO4J MIGRATIONS
# =============================================================================
if [ -n "$NEO4J_PASSWORD" ]; then
    echo "=== Running Neo4j Migrations ==="

    # Wait for Neo4j to be ready
    # Uses environment variables directly in Python (avoids shell injection)
    MAX_RETRIES=30
    RETRY_COUNT=0
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if python -c "
import os
from neo4j import GraphDatabase
uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
user = os.environ.get('NEO4J_USER', 'neo4j')
password = os.environ.get('NEO4J_PASSWORD', '')
driver = GraphDatabase.driver(uri, auth=(user, password))
driver.verify_connectivity()
driver.close()
print('OK')
" 2>/dev/null; then
            echo "Neo4j is ready!"
            break
        fi
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo "Waiting for Neo4j... (attempt $RETRY_COUNT/$MAX_RETRIES)"
        sleep 2
    done

    # Run migrations
    if [ -f /app/scripts/run_migrations.py ]; then
        echo "Running migration script..."
        python /app/scripts/run_migrations.py --target-version 3 || echo "Migration completed with status: $?"
    else
        echo "Migration script not found, skipping..."
    fi
    echo "=== Migrations Complete ==="
else
    echo "NEO4J_PASSWORD not set, skipping migrations..."
fi

# =============================================================================
# EXTRACT SIGNAL DATA
# =============================================================================
# OpenClaw autoStarts signal-cli WITHOUT --config flag.
# signal-cli uses default: $HOME/.local/share/signal-cli/
# With HOME=/data (set at gateway exec), data must be at:
#   /data/.local/share/signal-cli/data/accounts.json
# Archive structure: data/accounts.json, data/182126, data/182126.d/

SIGNAL_CLI_DATA_DIR="/data/.local/share/signal-cli"

if [ -f /opt/signal-data.tar.gz ]; then
    echo "=== Extracting Signal Data ==="
    mkdir -p "$SIGNAL_CLI_DATA_DIR"
    # Force clean extraction every deploy to prevent corruption
    rm -rf "$SIGNAL_CLI_DATA_DIR/data" 2>/dev/null || true
    tar -xzf /opt/signal-data.tar.gz -C "$SIGNAL_CLI_DATA_DIR"
    find "$SIGNAL_CLI_DATA_DIR" -name '._*' -delete 2>/dev/null
    echo "  Extracted to: $SIGNAL_CLI_DATA_DIR"
    echo "  Contents:"
    ls -la "$SIGNAL_CLI_DATA_DIR/data/"
    echo "  accounts.json size: $(wc -c < "$SIGNAL_CLI_DATA_DIR/data/accounts.json") bytes"
fi

# Set permissions for moltbot user (OpenClaw runs as moltbot)
# Must chown the entire .local tree since mkdir -p creates parents as root
chown -R 1001:1001 /data/.local 2>/dev/null || true
chmod -R 700 "$SIGNAL_CLI_DATA_DIR" 2>/dev/null || true
# Parent dirs need traverse permission (execute bit)
chmod 755 /data/.local /data/.local/share 2>/dev/null || true

echo "Signal data status:"
if [ -f "$SIGNAL_CLI_DATA_DIR/data/accounts.json" ]; then
    echo "  accounts.json found at $SIGNAL_CLI_DATA_DIR/data/accounts.json"
    echo "  accounts.json content: $(cat "$SIGNAL_CLI_DATA_DIR/data/accounts.json")"
    echo "  signal-cli version: $(/usr/local/bin/signal-cli --version 2>&1 || echo unknown)"
    echo "  Directory tree:"
    find "$SIGNAL_CLI_DATA_DIR" -type f 2>/dev/null | while read -r f; do
        echo "    $f ($(stat -c '%U:%G %a' "$f" 2>/dev/null || stat -f '%Su:%Sg %Lp' "$f" 2>/dev/null))"
    done
    # Quick smoke test: list accounts as moltbot user
    echo "  Testing signal-cli env and listAccounts as moltbot..."
    su -s /bin/sh moltbot -c "HOME=/data; export HOME; echo HOME=\$HOME; echo XDG_DATA_HOME=\${XDG_DATA_HOME:-unset}; echo 'Expected data dir: /data/.local/share/signal-cli'; ls -la /data/.local/share/signal-cli/data/ 2>&1; echo '--- verbose listAccounts ---'; /usr/local/bin/signal-cli -v listAccounts 2>&1" || true
else
    echo "  WARNING: accounts.json missing — Signal will not work"
fi

# =============================================================================
# INSTALL OPENCLAW CONFIGURATION
# =============================================================================
# Always copy config to the state directory to pick up config changes
# OpenClaw reads from ~/.openclaw/openclaw.json
echo "Installing OpenClaw configuration..."
cp /app/openclaw.json "$OPENCLAW_STATE_DIR/openclaw.json"
cp /app/openclaw.json5 "$OPENCLAW_STATE_DIR/openclaw.json5"
chown 1001:1001 "$OPENCLAW_STATE_DIR/openclaw.json" "$OPENCLAW_STATE_DIR/openclaw.json5"
echo "OpenClaw config installed at $OPENCLAW_STATE_DIR/openclaw.json"
echo "Config contents (agents section):"
python3 -c "import json; c=json.load(open('$OPENCLAW_STATE_DIR/openclaw.json')); print(json.dumps(c.get('agents',{}).get('defaults',{}), indent=2))" 2>&1 || echo "  (could not parse config)"
echo "Config file size: $(wc -c < $OPENCLAW_STATE_DIR/openclaw.json) bytes"

# Run OpenClaw doctor to check config validity
echo "Running OpenClaw config validation..."
OPENCLAW_BIN_CHECK=$(which openclaw 2>/dev/null || echo "/usr/local/bin/openclaw")
if [ -x "$OPENCLAW_BIN_CHECK" ]; then
    HOME=/data su -s /bin/sh moltbot -c "HOME=/data OPENCLAW_STATE_DIR=$OPENCLAW_STATE_DIR $OPENCLAW_BIN_CHECK doctor" 2>&1 || echo "  (doctor exited with code $?)"
fi

# =============================================================================
# START HEARTBEAT SIDECAR
# =============================================================================
if [ -n "$NEO4J_PASSWORD" ] && [ -f /app/scripts/heartbeat_writer.py ]; then
    echo "Starting heartbeat writer sidecar..."
    su -s /bin/sh moltbot -c "NEO4J_URI=$NEO4J_URI NEO4J_USER=${NEO4J_USER:-neo4j} NEO4J_PASSWORD=$NEO4J_PASSWORD python /app/scripts/heartbeat_writer.py &"
fi

# =============================================================================
# START OPENCLAW GATEWAY
# =============================================================================
# Drop to moltbot user and start the OpenClaw gateway
# The gateway includes the built-in webchat UI at :18789
echo "Starting OpenClaw Gateway on port ${OPENCLAW_GATEWAY_PORT:-18789}..."

# Find the OpenClaw entry point - installed globally via npm
OPENCLAW_BIN=$(which openclaw 2>/dev/null || echo "/usr/local/bin/openclaw")
OPENCLAW_DIST=$(node -e "console.log(require.resolve('openclaw/dist/index.js'))" 2>/dev/null || echo "")

if [ -n "$OPENCLAW_DIST" ]; then
    echo "Using OpenClaw dist: $OPENCLAW_DIST"
    exec su -s /bin/sh moltbot -c "HOME=/data OPENCLAW_STATE_DIR=$OPENCLAW_STATE_DIR node $OPENCLAW_DIST gateway --bind lan --port ${OPENCLAW_GATEWAY_PORT:-18789} --allow-unconfigured"
elif [ -x "$OPENCLAW_BIN" ]; then
    echo "Using OpenClaw binary: $OPENCLAW_BIN"
    exec su -s /bin/sh moltbot -c "HOME=/data OPENCLAW_STATE_DIR=$OPENCLAW_STATE_DIR $OPENCLAW_BIN gateway --bind lan --port ${OPENCLAW_GATEWAY_PORT:-18789} --allow-unconfigured"
else
    echo "ERROR: OpenClaw not found. Falling back to health check server."
    exec su -s /bin/sh moltbot -c "python /app/start_server.py"
fi
