#!/bin/sh
# Workspace entrypoint for Kurultai multi-agent system
# Runs heartbeat writer sidecar alongside the main application
# This is a simplified entrypoint for development/testing

# =============================================================================
# CONFIGURATION
# =============================================================================
NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
HEARTBEAT_INTERVAL="${HEARTBEAT_INTERVAL:-30}"
CIRCUIT_BREAKER_THRESHOLD="${CIRCUIT_BREAKER_THRESHOLD:-3}"
CIRCUIT_BREAKER_PAUSE="${CIRCUIT_BREAKER_PAUSE:-60}"
LOG_LEVEL="${HEARTBEAT_LOG_LEVEL:-INFO}"

WORKSPACE_DIR="/data/workspace/souls/main"
LOGS_DIR="${WORKSPACE_DIR}/logs"

# =============================================================================
# STARTUP
# =============================================================================
echo "=== Kurultai Workspace Entrypoint ==="
echo "Workspace: $WORKSPACE_DIR"
echo "Neo4j: $NEO4J_URI"

# Create logs directory
mkdir -p "$LOGS_DIR"

# =============================================================================
# START HEARTBEAT WRITER SIDECAR
# =============================================================================
HEARTBEAT_WRITER_PID=""

HEARTBEAT_WRITER_PATH="${WORKSPACE_DIR}/tools/kurultai/heartbeat_writer.py"

if [ -n "$NEO4J_PASSWORD" ] && [ -f "$HEARTBEAT_WRITER_PATH" ]; then
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
    echo "  Heartbeat writer started with PID $HEARTBEAT_WRITER_PID"

    # Verify it started
    sleep 2
    if kill -0 $HEARTBEAT_WRITER_PID 2>/dev/null; then
        echo "  ✅ Heartbeat writer is running"
    else
        echo "  ⚠️  Heartbeat writer may have failed to start (check logs)"
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
