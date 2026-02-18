#!/bin/sh
# Moltbot entrypoint - runs migrations, extracts Signal data, then starts OpenClaw gateway
# Runs as root initially to handle volume permissions, then drops to moltbot user
# Version: 2026-02-18-v52-CLEAN

echo "=== Entrypoint starting (version 2026-02-18-v52-CLEAN) ==="

OPENCLAW_STATE_DIR="${OPENCLAW_STATE_DIR:-/data/.openclaw}"

# Ensure data directories exist with proper permissions
mkdir -p "$OPENCLAW_STATE_DIR" 2>/dev/null || true
mkdir -p /data/logs 2>/dev/null || true
mkdir -p /data/workspace 2>/dev/null || true

# =============================================================================
# DEPLOY AGENT SOUL FILES
# =============================================================================
if [ -d /app/souls ]; then
    echo "=== Deploying Agent Soul Files ==="

    for stale in SOUL.md AGENTS.md BOOTSTRAP.md IDENTITY.md USER.md MEMORY.md; do
        if [ -f "/data/workspace/$stale" ]; then
            echo "  Removing stale /data/workspace/$stale"
            rm -f "/data/workspace/$stale"
        fi
    done

    for agent_dir in /app/souls/*/; do
        agent_id=$(basename "$agent_dir")
        target="/data/workspace/souls/$agent_id"
        mkdir -p "$target"
        rm -f "$target"/*.md 2>/dev/null || true
        cp -f "$agent_dir"*.md "$target/" 2>/dev/null || true
        file_count=$(ls "$target"/*.md 2>/dev/null | wc -l | tr -d ' ')
        echo "  $agent_id: $file_count files deployed"
        if [ -f "$target/SOUL.md" ]; then
            first_line=$(head -1 "$target/SOUL.md")
            echo "    SOUL.md: $first_line"
        fi
    done
    chown -R 1001:1001 /data/workspace/souls 2>/dev/null || true
    echo "=== Soul Files Deployed ==="
fi

# =============================================================================
# CLEAR STALE SESSION LOCKS
# =============================================================================
echo "=== Clearing Stale Session Locks ==="
if [ -d "$OPENCLAW_STATE_DIR/agents" ]; then
    lock_count=$(find "$OPENCLAW_STATE_DIR/agents" -name "*.lock" -type f 2>/dev/null | wc -l | tr -d ' ')
    if [ "$lock_count" -gt 0 ]; then
        echo "  Found $lock_count stale lock files, removing..."
        find "$OPENCLAW_STATE_DIR/agents" -name "*.lock" -type f -delete 2>/dev/null || true
        echo "  Stale locks cleared"
    else
        echo "  No stale locks found"
    fi
fi

# Skills directory
SKILLS_DIR="${SKILLS_DIR:-/data/skills}"
mkdir -p "$SKILLS_DIR" 2>/dev/null || true
chown -R 1001:1001 /data 2>/dev/null || true
echo "Skills directory: $SKILLS_DIR"

# =============================================================================
# RUN NEO4J MIGRATIONS
# =============================================================================
if [ -n "$NEO4J_PASSWORD" ]; then
    echo "=== Running Neo4j Migrations ==="

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

    if [ -f /app/scripts/run_migrations.py ]; then
        echo "Running migration script..."
        python /app/scripts/run_migrations.py --target-version 4 || echo "Migration completed with status: $?"
    fi
    echo "=== Migrations Complete ==="
else
    echo "NEO4J_PASSWORD not set, skipping migrations..."
fi

# =============================================================================
# EXTRACT SIGNAL DATA
# =============================================================================
SIGNAL_CLI_DATA_DIR="/data/.local/share/signal-cli"

SIGNAL_RELINKED=0
if [ "$SIGNAL_FORCE_RELINK" = "1" ]; then
    echo "=== SIGNAL_FORCE_RELINK: Wiping stale Signal data ==="
    rm -rf "$SIGNAL_CLI_DATA_DIR/data" 2>/dev/null || true
    SIGNAL_RELINKED=1
    echo "  Wiped. Signal will not start until device is re-linked."
fi

if [ "$SIGNAL_RELINKED" = "1" ]; then
    echo "=== Signal: Skipping data extraction (FORCE_RELINK active) ==="
    mkdir -p "$SIGNAL_CLI_DATA_DIR/data"
elif [ -f "$SIGNAL_CLI_DATA_DIR/data/accounts.json" ]; then
    echo "=== Signal Data Already on Volume ==="
    echo "  Preserving existing signal-cli data"
    ls -la "$SIGNAL_CLI_DATA_DIR/data/"
    echo "  accounts.json size: $(wc -c < "$SIGNAL_CLI_DATA_DIR/data/accounts.json") bytes"
elif [ -f /opt/signal-data.tar.gz ]; then
    echo "=== Extracting Signal Data (first deploy) ==="
    mkdir -p "$SIGNAL_CLI_DATA_DIR"
    tar -xzf /opt/signal-data.tar.gz -C "$SIGNAL_CLI_DATA_DIR"
    find "$SIGNAL_CLI_DATA_DIR" -name '._*' -delete 2>/dev/null
    echo "  Extracted to: $SIGNAL_CLI_DATA_DIR"
    ls -la "$SIGNAL_CLI_DATA_DIR/data/"
else
    echo "  WARNING: No signal data found"
fi

chown -R 1001:1001 /data/.local 2>/dev/null || true
chmod -R 700 "$SIGNAL_CLI_DATA_DIR" 2>/dev/null || true
chmod 755 /data/.local /data/.local/share 2>/dev/null || true

echo "Signal data status:"
if [ -f "$SIGNAL_CLI_DATA_DIR/data/accounts.json" ]; then
    echo "  accounts.json: OK ($(wc -c < "$SIGNAL_CLI_DATA_DIR/data/accounts.json") bytes)"
else
    echo "  WARNING: accounts.json missing"
fi

# =============================================================================
# TRUST SIGNAL IDENTITY KEYS
# =============================================================================
if [ "$SIGNAL_RELINKED" != "1" ] && [ -f "$SIGNAL_CLI_DATA_DIR/data/accounts.json" ] && [ -n "$SIGNAL_ACCOUNT" ]; then
    echo "=== Trusting Signal Identity Keys ==="
    if [ -n "$SIGNAL_ALLOW_FROM" ]; then
        echo "$SIGNAL_ALLOW_FROM" | tr ',' '\n' | while read -r NUM; do
            NUM=$(echo "$NUM" | tr -d ' ')
            [ -z "$NUM" ] && continue
            echo "  Trusting $NUM..."
            su -s /bin/sh moltbot -c "HOME=/data /usr/local/bin/signal-cli -a $SIGNAL_ACCOUNT trust --trust-all-known-keys $NUM" 2>&1 || true
        done
    fi
    echo "  Trusting $SIGNAL_ACCOUNT (self)..."
    su -s /bin/sh moltbot -c "HOME=/data /usr/local/bin/signal-cli -a $SIGNAL_ACCOUNT trust --trust-all-known-keys $SIGNAL_ACCOUNT" 2>&1 || true
    echo "=== Identity Keys Trusted ==="
fi

# =============================================================================
# CLEAN STALE OPENCLAW STATE FILES
# =============================================================================
for stale in SOUL.md AGENTS.md BOOTSTRAP.md IDENTITY.md USER.md; do
    if [ -f "$OPENCLAW_STATE_DIR/$stale" ]; then
        rm -f "$OPENCLAW_STATE_DIR/$stale"
    fi
done
for agent_state in "$OPENCLAW_STATE_DIR"/agents/*/; do
    [ -d "$agent_state" ] || continue
    if ls "$agent_state"*.md 1>/dev/null 2>&1; then
        rm -f "$agent_state"*.md
    fi
done

# =============================================================================
# INSTALL OPENCLAW CONFIGURATION
# =============================================================================
echo "Installing OpenClaw configuration..."
cp /app/openclaw.json "$OPENCLAW_STATE_DIR/openclaw.json"
chown root:root "$OPENCLAW_STATE_DIR/openclaw.json"
chmod 444 "$OPENCLAW_STATE_DIR/openclaw.json"
echo "OpenClaw config installed at $OPENCLAW_STATE_DIR/openclaw.json ($(wc -c < $OPENCLAW_STATE_DIR/openclaw.json) bytes) [read-only, root-owned]"

# =============================================================================
# START HEARTBEAT SIDECAR
# =============================================================================
if [ -n "$NEO4J_PASSWORD" ] && [ -f /app/scripts/heartbeat_writer.py ]; then
    echo "Starting heartbeat writer sidecar..."
    su -s /bin/sh moltbot -c "NEO4J_URI=$NEO4J_URI NEO4J_USER=${NEO4J_USER:-neo4j} NEO4J_PASSWORD=$NEO4J_PASSWORD python /app/scripts/heartbeat_writer.py &"
fi

# =============================================================================
# PATCH WEBCHAT WEBSOCKET URL (RUNTIME)
# =============================================================================
# The OpenClaw Control UI has a hardcoded placeholder ws://100.x.y.z:18789
# Replace it with the actual public Railway URL so webchat works
JS_FILE=$(ls /usr/local/lib/node_modules/openclaw/dist/control-ui/assets/index-*.js 2>/dev/null | head -1)
if [ -n "$JS_FILE" ] && [ -f "$JS_FILE" ]; then
    echo "Patching WebSocket URL in: $(basename $JS_FILE)"
    sed -i 's|ws://100\.x\.y\.z:18789|wss://moltbot-railway-template-production-c0a3.up.railway.app/ws|g' "$JS_FILE"
    sed -i 's|ws://localhost:18789|wss://moltbot-railway-template-production-c0a3.up.railway.app/ws|g' "$JS_FILE"
    echo "WebSocket URL patched"
fi

# =============================================================================
# PATCH OPENCLAW GATEWAY TO ALLOW WEBCHAT DEVICE AUTH BYPASS
# =============================================================================
# The dangerouslyDisableDeviceAuth setting only applies to Control UI (client.id = "openclaw-control-ui")
# but webchat uses client.id = "webchat". This patch allows webchat to also bypass device auth.
GATEWAY_CLI_FILE="/usr/local/lib/node_modules/openclaw/dist/gateway-cli-BYMlAFfC.js"
if [ -f "$GATEWAY_CLI_FILE" ]; then
    echo "Patching OpenClaw gateway for webchat device auth bypass..."
    node -e "
const fs = require('fs');
const file = '$GATEWAY_CLI_FILE';
let content = fs.readFileSync(file, 'utf8');
let modified = false;

// Patch disableControlUiDeviceAuth to include webchat
const oldDisable = 'const disableControlUiDeviceAuth = isControlUi && configSnapshot.gateway?.controlUi?.dangerouslyDisableDeviceAuth === true;';
const newDisable = 'const disableControlUiDeviceAuth = (isControlUi || isWebchat) && configSnapshot.gateway?.controlUi?.dangerouslyDisableDeviceAuth === true;';
if (content.includes(oldDisable)) {
    content = content.replace(oldDisable, newDisable);
    modified = true;
    console.log('  - Patched disableControlUiDeviceAuth');
}

// Patch allowInsecureControlUi to include webchat
const oldAllow = 'const allowInsecureControlUi = isControlUi && configSnapshot.gateway?.controlUi?.allowInsecureAuth === true;';
const newAllow = 'const allowInsecureControlUi = (isControlUi || isWebchat) && configSnapshot.gateway?.controlUi?.allowInsecureAuth === true;';
if (content.includes(oldAllow)) {
    content = content.replace(oldAllow, newAllow);
    modified = true;
    console.log('  - Patched allowInsecureControlUi');
}

if (modified) {
    fs.writeFileSync(file, content);
    console.log('Gateway patched successfully');
} else {
    console.log('Gateway already patched or patterns not found');
}
"
fi

# =============================================================================
# START OPENCLAW GATEWAY
# =============================================================================
OPENCLAW_INTERNAL_PORT=18790
echo "Starting OpenClaw Gateway on internal port ${OPENCLAW_INTERNAL_PORT}..."

OPENCLAW_BIN=$(which openclaw 2>/dev/null || echo "/usr/local/bin/openclaw")

if [ -x "$OPENCLAW_BIN" ]; then
    echo "Using OpenClaw binary: $OPENCLAW_BIN"
    su -s /bin/sh moltbot -c "HOME=/data OPENCLAW_STATE_DIR=$OPENCLAW_STATE_DIR NEO4J_URI=$NEO4J_URI NEO4J_USER=${NEO4J_USER:-neo4j} NEO4J_PASSWORD=$NEO4J_PASSWORD $OPENCLAW_BIN gateway --port ${OPENCLAW_INTERNAL_PORT} --allow-unconfigured" &
    OPENCLAW_PID=$!
    echo "OpenClaw gateway started with PID $OPENCLAW_PID"
else
    echo "ERROR: OpenClaw not found. Falling back to health check server."
    su -s /bin/sh moltbot -c "python /app/start_server.py" &
    OPENCLAW_PID=$!
fi

echo "Waiting for OpenClaw to start..."
sleep 5

# =============================================================================
# START EXPRESS API SERVER
# =============================================================================
echo "DEBUG: PORT env var = '${PORT}'"
EXPRESS_SERVER_PORT=${PORT:-8082}
echo "DEBUG: EXPRESS_SERVER_PORT = '${EXPRESS_SERVER_PORT}'"
echo "DEBUG: OPENCLAW_INTERNAL_PORT = '${OPENCLAW_INTERNAL_PORT}'"

if [ -f /app/src/index.js ]; then
    echo "=== Starting Express API server on port ${EXPRESS_SERVER_PORT} ==="
    su -s /bin/sh moltbot -c "cd /app && NODE_ENV=production EXPRESS_PORT=${EXPRESS_SERVER_PORT} PORT=${EXPRESS_SERVER_PORT} NEO4J_URI=$NEO4J_URI NEO4J_USER=${NEO4J_USER:-neo4j} NEO4J_PASSWORD=$NEO4J_PASSWORD SIGNAL_ACCOUNT=$SIGNAL_ACCOUNT node /app/src/index.js" &
    EXPRESS_PID=$!
    echo "  Express server started with PID $EXPRESS_PID"

    sleep 5

    echo "  Verifying Express health check..."
    if curl -sf http://localhost:${EXPRESS_SERVER_PORT}/health >/dev/null 2>&1; then
        echo "  Express API server started successfully"
    else
        echo "  WARNING: Express health check failed (may still be starting)"
    fi
else
    echo "WARNING: Express server not found at /app/src/index.js"
fi

# =============================================================================
# KEEP CONTAINER RUNNING
# =============================================================================
echo "=== All services started, monitoring... ==="
wait
