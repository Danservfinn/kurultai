#!/bin/sh
# Moltbot entrypoint - runs migrations, extracts Signal data, then starts OpenClaw gateway
# Runs as root initially to handle volume permissions, then drops to moltbot user

SIGNAL_DATA_DIR="${SIGNAL_DATA_DIR:-/data/.signal}"
OPENCLAW_STATE_DIR="${OPENCLAW_STATE_DIR:-/data/.openclaw}"

# Ensure data directories exist with proper permissions
mkdir -p "$SIGNAL_DATA_DIR" 2>/dev/null || true
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
# EXTRACT AND START SIGNAL
# =============================================================================
# signal-cli --config <dir> expects: <dir>/data/accounts.json
# We use /data/.signal as the config dir, with data/ subdirectory inside.
# Archive structure: data/accounts.json, data/182126, data/182126.d/

# Always force-extract from archive to ensure clean state
# Previous migrations may have created truncated or corrupted files
if [ -f /opt/signal-data.tar.gz ]; then
    echo "Extracting Signal data from archive to $SIGNAL_DATA_DIR..."
    # Remove old data/ subdir to ensure clean extraction
    rm -rf "$SIGNAL_DATA_DIR/data" 2>/dev/null || true
    tar -xzf /opt/signal-data.tar.gz -C "$SIGNAL_DATA_DIR"
    find "$SIGNAL_DATA_DIR" -name '._*' -delete 2>/dev/null
    echo "  Extracted contents:"
    ls -la "$SIGNAL_DATA_DIR/data/"
    echo "  accounts.json size: $(wc -c < "$SIGNAL_DATA_DIR/data/accounts.json") bytes"
fi

chown -R 1001:1001 "$SIGNAL_DATA_DIR" 2>/dev/null || true
chmod -R 700 "$SIGNAL_DATA_DIR" 2>/dev/null || true

echo "Signal data status:"
if [ -f "$SIGNAL_DATA_DIR/data/accounts.json" ]; then
    echo "  accounts.json found"
    ls -la "$SIGNAL_DATA_DIR/data/"
else
    echo "  WARNING: accounts.json missing at $SIGNAL_DATA_DIR/data/"
fi

# Start signal-cli daemon BEFORE OpenClaw (with explicit --config path)
# OpenClaw will connect to it via httpUrl instead of autoStart
SIGNAL_CLI_PORT=8080
if [ -f "$SIGNAL_DATA_DIR/data/accounts.json" ] && [ -x /usr/local/bin/signal-cli ]; then
    echo "Starting signal-cli daemon on port $SIGNAL_CLI_PORT..."
    su -s /bin/sh moltbot -c "/usr/local/bin/signal-cli --config $SIGNAL_DATA_DIR daemon --http 127.0.0.1:$SIGNAL_CLI_PORT --receive-mode on-connection --ignore-stories" &
    SIGNAL_PID=$!
    echo "  signal-cli PID: $SIGNAL_PID"

    # Wait for daemon to become ready
    SIGNAL_READY=false
    for i in $(seq 1 30); do
        sleep 2
        if curl -sf http://127.0.0.1:$SIGNAL_CLI_PORT/api/v1/check > /dev/null 2>&1; then
            SIGNAL_READY=true
            echo "  signal-cli daemon ready after $((i*2))s"
            break
        fi
        echo "  Waiting for signal-cli... (${i}/30)"
    done

    if [ "$SIGNAL_READY" = "false" ]; then
        echo "  WARNING: signal-cli daemon not ready after 60s"
        # Check if process is still running
        kill -0 $SIGNAL_PID 2>/dev/null && echo "  Process still running" || echo "  Process exited"
    fi
else
    echo "Skipping signal-cli daemon (missing accounts or binary)"
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
