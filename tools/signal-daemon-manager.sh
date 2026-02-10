#!/bin/bash
# Signal Daemon Manager - Prevents config lock issues
# Usage: signal-daemon-manager.sh {start|stop|restart|status}

PIDFILE=/tmp/signal-daemon.pid
LOCKFILE=/tmp/signal-daemon.lock
LOGFILE=/tmp/signal-daemon.log

# Function to check if daemon is running
is_running() {
    if [ -f "$PIDFILE" ]; then
        pid=$(cat "$PIDFILE")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

# Function to get lock
acquire_lock() {
    exec 200>"$LOCKFILE"
    if ! flock -n 200; then
        echo "Another instance is already running"
        exit 1
    fi
}

# Start daemon
start_daemon() {
    acquire_lock
    
    if is_running; then
        echo "Signal daemon already running (PID: $(cat $PIDFILE))"
        exit 0
    fi
    
    echo "Starting Signal daemon..."
    
    # Clean up any stale locks
    rm -f ~/.local/share/signal-cli/data/*.lock
    rm -f /data/.signal/data/*.lock
    
    # Kill any existing signal-cli processes
    pkill -9 signal-cli 2>/dev/null || true
    sleep 2
    
    # Start daemon with HTTP API
    SIGNAL_DATA_DIR=/data/.signal \
    signal-cli --trust-new-identities always \
        -a +15165643945 \
        daemon \
        --http 127.0.0.1:8080 \
        --no-receive-stdout \
        --receive-mode on-start \
        --ignore-stories \
        >> "$LOGFILE" 2>&1 &
    
    daemon_pid=$!
    echo $daemon_pid > "$PIDFILE"
    
    # Wait for daemon to be ready
    sleep 5
    
    # Verify it's working
    if kill -0 $daemon_pid 2>/dev/null; then
        if curl -s http://127.0.0.1:8080/api/v1/rpc \
           -X POST \
           -H "Content-Type: application/json" \
           -d '{"jsonrpc":"2.0","id":"1","method":"version"}' \
           | grep -q "version"; then
            echo "✅ Signal daemon started (PID: $daemon_pid)"
            return 0
        fi
    fi
    
    echo "❌ Failed to start Signal daemon"
    rm -f "$PIDFILE"
    return 1
}

# Stop daemon
stop_daemon() {
    if [ -f "$PIDFILE" ]; then
        pid=$(cat "$PIDFILE")
        echo "Stopping Signal daemon (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 2
        kill -9 "$pid" 2>/dev/null || true
        rm -f "$PIDFILE"
        echo "✅ Signal daemon stopped"
    else
        echo "Signal daemon not running"
    fi
    
    # Clean up any remaining locks
    rm -f ~/.local/share/signal-cli/data/*.lock
    rm -f /data/.signal/data/*.lock
}

# Check status
status_daemon() {
    if is_running; then
        pid=$(cat "$PIDFILE")
        echo "✅ Signal daemon running (PID: $pid)"
        
        # Check API responsiveness
        if curl -s http://127.0.0.1:8080/api/v1/rpc \
           -X POST \
           -H "Content-Type: application/json" \
           -d '{"jsonrpc":"2.0","id":"1","method":"version"}' \
           | grep -q "version"; then
            echo "✅ API responsive"
        else
            echo "⚠️  API not responding"
        fi
    else
        echo "❌ Signal daemon not running"
    fi
}

# Restart daemon
restart_daemon() {
    stop_daemon
    sleep 2
    start_daemon
}

# Main
 case "$1" in
    start)
        start_daemon
        ;;
    stop)
        stop_daemon
        ;;
    restart)
        restart_daemon
        ;;
    status)
        status_daemon
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
