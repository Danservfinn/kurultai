#!/bin/sh
# Moltbot entrypoint - runs migrations, extracts Signal data, then starts OpenClaw gateway
# Runs as root initially to handle volume permissions, then drops to moltbot user
# Version: 2026-02-07-v9 (Express port 8082 to avoid signal-cli conflict)

echo "=== Entrypoint starting (version 2026-02-08-v11) ==="

OPENCLAW_STATE_DIR="${OPENCLAW_STATE_DIR:-/data/.openclaw}"

# Ensure data directories exist with proper permissions
mkdir -p "$OPENCLAW_STATE_DIR" 2>/dev/null || true
mkdir -p /data/logs 2>/dev/null || true
mkdir -p /data/workspace 2>/dev/null || true

# =============================================================================
# DEPLOY AGENT SOUL FILES
# =============================================================================
# Copy SOUL.md + CLAUDE.md for each agent to their workspace on the volume.
# OpenClaw loads these at session start from each agent's workspace path.
# CLEAN deploy: wipe stale files first to prevent OpenClaw defaults from persisting.
if [ -d /app/souls ]; then
    echo "=== Deploying Agent Soul Files ==="

    # Remove stale root-level OpenClaw template files that override per-agent souls
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
        # Wipe ALL .md files in target to remove stale OpenClaw-generated content
        rm -f "$target"/*.md 2>/dev/null || true
        # Deploy fresh copies from Docker image
        cp -f "$agent_dir"*.md "$target/" 2>/dev/null || true
        file_count=$(ls "$target"/*.md 2>/dev/null | wc -l | tr -d ' ')
        echo "  $agent_id: $file_count files deployed"
        # Verify correct SOUL.md deployed (not the generic OpenClaw template)
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
# Session locks can persist across redeployments on persistent volumes.
# Clear stale locks to prevent "session file locked" errors.
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
        python /app/scripts/run_migrations.py --target-version 4 || echo "Migration completed with status: $?"
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
    echo "  accounts.json: OK ($(wc -c < "$SIGNAL_CLI_DATA_DIR/data/accounts.json") bytes)"
    echo "  signal-cli: $(/usr/local/bin/signal-cli --version 2>&1 || echo unknown)"
else
    echo "  WARNING: accounts.json missing — Signal will not work"
fi

# =============================================================================
# TRUST SIGNAL IDENTITY KEYS
# =============================================================================
# After being offline, the linked device may have stale identity keys.
# Trust all known keys to prevent "untrusted identities" errors on send
# and "decryption failed" errors on receive.
if [ -f "$SIGNAL_CLI_DATA_DIR/data/accounts.json" ] && [ -n "$SIGNAL_ACCOUNT" ]; then
    echo "=== Trusting Signal Identity Keys ==="
    # Trust each number in SIGNAL_ALLOW_FROM (comma-separated)
    if [ -n "$SIGNAL_ALLOW_FROM" ]; then
        echo "$SIGNAL_ALLOW_FROM" | tr ',' '\n' | while read -r NUM; do
            NUM=$(echo "$NUM" | tr -d ' ')
            [ -z "$NUM" ] && continue
            echo "  Trusting $NUM..."
            su -s /bin/sh moltbot -c "HOME=/data /usr/local/bin/signal-cli -a $SIGNAL_ACCOUNT trust --trust-all-known-keys $NUM" 2>&1 || echo "  trust $NUM returned: $?"
        done
    fi
    # Trust the account's own number (self-messaging)
    echo "  Trusting $SIGNAL_ACCOUNT (self)..."
    su -s /bin/sh moltbot -c "HOME=/data /usr/local/bin/signal-cli -a $SIGNAL_ACCOUNT trust --trust-all-known-keys $SIGNAL_ACCOUNT" 2>&1 || echo "  trust command returned: $?"
    echo "=== Identity Keys Trusted ==="

    # Session reset: uncomment if decryption errors return after extended offline periods.
    # Runs BEFORE the daemon starts to avoid lock file conflicts.
    # echo "=== Resetting Signal Sessions ==="
    # su -s /bin/sh moltbot -c "HOME=/data /usr/local/bin/signal-cli -a $SIGNAL_ACCOUNT send --end-session +19194133445" 2>&1 || echo "  end-session returned: $?"
    # echo "=== Session Reset Complete ==="
fi

# =============================================================================
# CLEAN STALE OPENCLAW STATE FILES
# =============================================================================
# Remove any SOUL.md or identity files from the OpenClaw state directory
# that may have been auto-generated by previous OpenClaw bootstrap runs.
for stale in SOUL.md AGENTS.md BOOTSTRAP.md IDENTITY.md USER.md; do
    if [ -f "$OPENCLAW_STATE_DIR/$stale" ]; then
        echo "Removing stale $OPENCLAW_STATE_DIR/$stale"
        rm -f "$OPENCLAW_STATE_DIR/$stale"
    fi
done
# Also clean any .md files in per-agent state subdirs
for agent_state in "$OPENCLAW_STATE_DIR"/agents/*/; do
    [ -d "$agent_state" ] || continue
    if ls "$agent_state"*.md 1>/dev/null 2>&1; then
        echo "Cleaning stale state files in $agent_state"
        rm -f "$agent_state"*.md
    fi
done

# =============================================================================
# INSTALL OPENCLAW CONFIGURATION
# =============================================================================
# Always copy config to the state directory to pick up config changes
# OpenClaw reads from ~/.openclaw/openclaw.json
echo "Installing OpenClaw configuration..."
cp /app/openclaw.json "$OPENCLAW_STATE_DIR/openclaw.json"
cp /app/openclaw.json5 "$OPENCLAW_STATE_DIR/openclaw.json5"
chown 1001:1001 "$OPENCLAW_STATE_DIR/openclaw.json" "$OPENCLAW_STATE_DIR/openclaw.json5"
echo "OpenClaw config installed at $OPENCLAW_STATE_DIR/openclaw.json ($(wc -c < $OPENCLAW_STATE_DIR/openclaw.json) bytes)"

# =============================================================================
# START HEARTBEAT SIDECAR
# =============================================================================
if [ -n "$NEO4J_PASSWORD" ] && [ -f /app/scripts/heartbeat_writer.py ]; then
    echo "Starting heartbeat writer sidecar..."
    su -s /bin/sh moltbot -c "NEO4J_URI=$NEO4J_URI NEO4J_USER=${NEO4J_USER:-neo4j} NEO4J_PASSWORD=$NEO4J_PASSWORD python /app/scripts/heartbeat_writer.py &"
fi

# =============================================================================
# VERIFY EXPRESS API SERVER FILES
# =============================================================================
# The Express server provides the proposal API endpoints on port 8082

echo "Checking for Express server at /app/src/index.js..."
if [ -f /app/src/index.js ]; then
    echo "  Express server found: $(wc -c < /app/src/index.js) bytes"
else
    echo "  ERROR: Express server not found at /app/src/index.js"
    echo "  Directory contents of /app/:"
    ls -la /app/ 2>/dev/null || echo "    (cannot list /app/)"
fi

# =============================================================================
# START OPENCLAW GATEWAY (in background)
# =============================================================================
# Start OpenClaw first in background so Express can start afterward
# The gateway includes the built-in webchat UI at :18789
echo "Starting OpenClaw Gateway on port ${OPENCLAW_GATEWAY_PORT:-18789}..."

# Find the OpenClaw entry point - installed globally via npm
OPENCLAW_BIN=$(which openclaw 2>/dev/null || echo "/usr/local/bin/openclaw")
OPENCLAW_DIST=$(node -e "console.log(require.resolve('openclaw/dist/index.js'))" 2>/dev/null || echo "")

if [ -n "$OPENCLAW_DIST" ]; then
    echo "Using OpenClaw dist: $OPENCLAW_DIST"
    su -s /bin/sh moltbot -c "HOME=/data OPENCLAW_STATE_DIR=$OPENCLAW_STATE_DIR node $OPENCLAW_DIST gateway --bind lan --port ${OPENCLAW_GATEWAY_PORT:-18789} --allow-unconfigured" &
    OPENCLAW_PID=$!
    echo "OpenClaw gateway started with PID $OPENCLAW_PID"
elif [ -x "$OPENCLAW_BIN" ]; then
    echo "Using OpenClaw binary: $OPENCLAW_BIN"
    su -s /bin/sh moltbot -c "HOME=/data OPENCLAW_STATE_DIR=$OPENCLAW_STATE_DIR $OPENCLAW_BIN gateway --bind lan --port ${OPENCLAW_GATEWAY_PORT:-18789} --allow-unconfigured" &
    OPENCLAW_PID=$!
    echo "OpenClaw gateway started with PID $OPENCLAW_PID"
else
    echo "ERROR: OpenClaw not found. Falling back to health check server."
    su -s /bin/sh moltbot -c "python /app/start_server.py" &
    OPENCLAW_PID=$!
fi

# Wait for OpenClaw to be ready
echo "Waiting for OpenClaw to start..."
sleep 5

# =============================================================================
# START EXPRESS API SERVER (in background)
# =============================================================================
# The Express server provides the proposal API endpoints on port 8082
# Note: Port 8080 is used by signal-cli daemon, 8081 is signal-cli HTTP interface

# Verify Express files exist before starting
if [ -f /app/src/index.js ]; then
    echo "=== Starting Express API server on port ${EXPRESS_PORT:-8082} ==="
    echo "  File check: /app/src/index.js exists ($(wc -c < /app/src/index.js) bytes)"
    su -s /bin/sh moltbot -c "cd /app && NODE_ENV=production PORT=${EXPRESS_PORT:-8082} NEO4J_URI=$NEO4J_URI NEO4J_USER=${NEO4J_USER:-neo4j} NEO4J_PASSWORD=$NEO4J_PASSWORD SIGNAL_ACCOUNT=$SIGNAL_ACCOUNT node /app/src/index.js" &
    EXPRESS_PID=$!
    echo "  Express server started with PID $EXPRESS_PID"

    # Wait for Express to start
    sleep 5

    # Verify Express started with health check
    echo "  Verifying Express health check..."
    if curl -sf http://localhost:${EXPRESS_PORT:-8082}/health >/dev/null 2>&1; then
        echo "  Express API server started successfully and responding to health checks"
    else
        echo "  WARNING: Express server health check failed (may still be starting)"
        # Try one more time after a longer wait
        sleep 5
        if curl -sf http://localhost:${EXPRESS_PORT:-8082}/health >/dev/null 2>&1; then
            echo "  Express API server now responding to health checks"
        else
            echo "  WARNING: Express server still not responding after 10 seconds"
        fi
    fi

    # Trigger architecture sync to Neo4j
    echo "  Triggering architecture sync to Neo4j..."
    sleep 3
    SYNC_RESULT=$(curl -sf -X POST http://localhost:${EXPRESS_PORT:-8082}/api/architecture/sync \
        -H "Content-Type: application/json" \
        -d "{\"commitHash\":\"startup-$(date +%s)\"}" 2>&1) || {
        echo "  WARNING: Architecture sync failed: $SYNC_RESULT"
    }
    if [ -n "$SYNC_RESULT" ]; then
        echo "  Architecture sync result: $SYNC_RESULT"
    fi
else
    echo "WARNING: Express server not found at /app/src/index.js after installation attempt"
    echo "  Directory contents of /app/:"
    ls -la /app/ 2>/dev/null || echo "    (cannot list /app/)"
    echo "  Directory contents of /app/src/:"
    ls -la /app/src/ 2>/dev/null || echo "    (cannot list /app/src/)"
fi

# =============================================================================
# KEEP CONTAINER RUNNING
# =============================================================================
# Wait for all background processes
echo "=== All services started, monitoring... ==="
wait
# Test timestamp: Sat Feb  8 14:52:00 EST 2026
# Cache bust: 1770506520
