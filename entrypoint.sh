#!/bin/sh
# Workspace entrypoint for Kurultai multi-agent system
# Runs heartbeat writer sidecar alongside the main application
# Includes Neo4j IPv6 connectivity fixes for Railway deployment

# =============================================================================
# CONFIGURATION
# =============================================================================
NEO4J_URI="${NEO4J_URI:-bolt://neo4j.railway.internal:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
HEARTBEAT_INTERVAL="${HEARTBEAT_INTERVAL:-30}"
CIRCUIT_BREAKER_THRESHOLD="${CIRCUIT_BREAKER_THRESHOLD:-3}"
CIRCUIT_BREAKER_PAUSE="${CIRCUIT_BREAKER_PAUSE:-60}"
LOG_LEVEL="${HEARTBEAT_LOG_LEVEL:-INFO}"
NEO4J_MAX_RETRIES="${NEO4J_MAX_RETRIES:-30}"
NEO4J_RETRY_DELAY="${NEO4J_RETRY_DELAY:-2}"

WORKSPACE_DIR="/data/workspace/souls/main"
LOGS_DIR="${WORKSPACE_DIR}/logs"
SCRIPTS_DIR="${WORKSPACE_DIR}/scripts"

# =============================================================================
# FUNCTIONS
# =============================================================================

# Test Neo4j connectivity
test_neo4j_connection() {
    python3 "${SCRIPTS_DIR}/neo4j_connection_helper.py" --test 2>/dev/null
    return $?
}

# Wait for Neo4j to be ready with retry logic
wait_for_neo4j() {
    echo ""
    echo "=== Waiting for Neo4j Connection ==="
    echo "  URI: $NEO4J_URI"
    echo "  Max retries: $NEO4J_MAX_RETRIES"
    echo "  Retry delay: ${NEO4J_RETRY_DELAY}s"
    echo ""
    
    local attempt=0
    while [ $attempt -lt $NEO4J_MAX_RETRIES ]; do
        attempt=$((attempt + 1))
        
        if python3 "${SCRIPTS_DIR}/neo4j_connection_helper.py" --test 2>/dev/null; then
            echo ""
            echo "✅ Neo4j is ready! (connected on attempt $attempt)"
            echo "===================================="
            return 0
        fi
        
        if [ $attempt -eq 1 ]; then
            echo "  Attempt $attempt/$NEO4J_MAX_RETRIES: Neo4j not ready yet..."
        elif [ $attempt -lt $NEO4J_MAX_RETRIES ]; then
            echo "  Attempt $attempt/$NEO4J_MAX_RETRIES: Retrying..."
        fi
        
        # On 5th retry, show diagnostic info
        if [ $attempt -eq 5 ]; then
            echo ""
            echo "  ⚠️  Multiple connection failures. Running diagnostics..."
            echo "  (This is normal if Neo4j is still starting up)"
            echo ""
            
            # Try to resolve the hostname
            if command -v getent >/dev/null 2>&1; then
                echo "  DNS Resolution:"
                getent hosts neo4j.railway.internal 2>/dev/null | head -1 | sed 's/^/    /' || echo "    neo4j.railway.internal: Could not resolve"
                getent hosts neo4j 2>/dev/null | head -1 | sed 's/^/    /' || echo "    neo4j: Could not resolve"
            fi
        fi
        
        sleep $NEO4J_RETRY_DELAY
    done
    
    echo ""
    echo "❌ Neo4j connection failed after $NEO4J_MAX_RETRIES attempts"
    echo ""
    echo "Possible solutions:"
    echo "  1. Ensure Neo4j service is running in Railway Dashboard"
    echo "  2. Apply the IPv6 fix (see docs/NEO4J_IPV6_FIX.md)"
    echo "  3. Run diagnostics: python3 scripts/neo4j_connection_helper.py --diagnose"
    echo ""
    
    return 1
}

# =============================================================================
# STARTUP
# =============================================================================
echo "=== Kurultai Workspace Entrypoint ==="
echo "Workspace: $WORKSPACE_DIR"
echo "Neo4j: $NEO4J_URI"

# Create logs directory
mkdir -p "$LOGS_DIR"

# =============================================================================
# NEO4J CONNECTIVITY CHECK
# =============================================================================
if [ -n "$NEO4J_PASSWORD" ]; then
    if wait_for_neo4j; then
        echo ""
        echo "Neo4j connectivity: ✅ OK"
    else
        echo ""
        echo "Neo4j connectivity: ⚠️  FAILED (will retry during operation)"
        echo "Continuing startup..."
    fi
    echo ""
else
    echo ""
    echo "NEO4J_PASSWORD not set, skipping connectivity check"
    echo ""
fi

# =============================================================================
# START HEARTBEAT WRITER SIDECAR
# =============================================================================
HEARTBEAT_WRITER_PID=""

HEARTBEAT_WRITER_PATH="${WORKSPACE_DIR}/tools/kurultai/heartbeat_writer.py"
PID_FILE="/tmp/heartbeat_writer.pid"

# Check if heartbeat_writer is already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "=== Heartbeat Writer Already Running ==="
        echo "  PID: $OLD_PID"
        echo "=========================================="
    else
        # Stale PID file, remove it
        rm -f "$PID_FILE"
    fi
fi

if [ -n "$NEO4J_PASSWORD" ] && [ -f "$HEARTBEAT_WRITER_PATH" ] && [ ! -f "$PID_FILE" ]; then
    echo "=== Starting Heartbeat Writer Sidecar ==="
    echo "  Script: $HEARTBEAT_WRITER_PATH"
    echo "  Configuration:"
    echo "    - Interval: ${HEARTBEAT_INTERVAL}s"
    echo "    - Circuit breaker threshold: ${CIRCUIT_BREAKER_THRESHOLD} failures"
    echo "    - Circuit breaker pause: ${CIRCUIT_BREAKER_PAUSE}s"
    echo "    - Log level: ${LOG_LEVEL}"
    echo "  Logs: $LOGS_DIR/heartbeat_writer.log"

    # Start sidecar
    NEO4J_URI=$NEO4J_URI \
    NEO4J_USER=$NEO4J_USER \
    NEO4J_PASSWORD=$NEO4J_PASSWORD \
    HEARTBEAT_INTERVAL=$HEARTBEAT_INTERVAL \
    CIRCUIT_BREAKER_THRESHOLD=$CIRCUIT_BREAKER_THRESHOLD \
    CIRCUIT_BREAKER_PAUSE=$CIRCUIT_BREAKER_PAUSE \
    LOG_LEVEL=$LOG_LEVEL \
    python "$HEARTBEAT_WRITER_PATH" >> "$LOGS_DIR/heartbeat_writer.log" 2>&1 &

    HEARTBEAT_WRITER_PID=$!
    echo $HEARTBEAT_WRITER_PID > "$PID_FILE"
    echo "  Heartbeat writer started with PID $HEARTBEAT_WRITER_PID"

    # Verify it started
    sleep 2
    if kill -0 $HEARTBEAT_WRITER_PID 2>/dev/null; then
        echo "  ✅ Heartbeat writer is running"
    else
        echo "  ⚠️  Heartbeat writer may have failed to start (check logs)"
        rm -f "$PID_FILE"
    fi
    echo "=========================================="

    # Export PID for other processes
    export HEARTBEAT_WRITER_PID
elif [ -z "$NEO4J_PASSWORD" ]; then
    echo "=== Heartbeat Writer Skipped ==="
    echo "  Reason: NEO4J_PASSWORD not set"
    echo "=========================================="
else
    echo "=== Heartbeat Writer Skipped ==="
    echo "  Reason: heartbeat_writer.py not found at $HEARTBEAT_WRITER_PATH"
    echo "=========================================="
fi

# =============================================================================
# MAIN APPLICATION
# =============================================================================
echo ""
echo "Entrypoint complete. Services running:"
[ -n "$HEARTBEAT_WRITER_PID" ] && echo "  - Heartbeat Writer (PID: $HEARTBEAT_WRITER_PID)"

# Keep script running if in foreground mode
if [ "$1" = "--wait" ]; then
    echo "Waiting for services... (Ctrl+C to stop)"
    wait
fi

exit 0
