#!/bin/bash
# Signal Health Monitor - Auto-restarts daemon if unhealthy
# Run via cron every minute: * * * * * /data/workspace/souls/main/tools/signal-health-monitor.sh

PIDFILE=/tmp/signal-daemon.pid
LOGFILE=/tmp/signal-health-monitor.log
ALERT_FILE=/tmp/signal-last-alert

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOGFILE"
}

# Check if daemon is healthy
check_health() {
    # Check process exists
    if [ -f "$PIDFILE" ]; then
        pid=$(cat "$PIDFILE")
        if ! kill -0 "$pid" 2>/dev/null; then
            log "ERROR: Daemon process not found (PID: $pid)"
            return 1
        fi
    else
        log "ERROR: PID file not found"
        return 1
    fi
    
    # Check API responsiveness
    if ! curl -s http://127.0.0.1:8080/api/v1/rpc \
        -X POST \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","id":"1","method":"version"}' \
        | grep -q "version"; then
        log "ERROR: API not responding"
        return 1
    fi
    
    # Check for config lock errors in recent logs
    if tail -10 /tmp/signal-daemon.log 2>/dev/null | grep -q "Config file is in use"; then
        log "ERROR: Config lock detected"
        return 1
    fi
    
    return 0
}

# Restart daemon
restart_daemon() {
    log "RESTARTING: Signal daemon"
    
    # Kill existing processes
    pkill -9 signal-cli 2>/dev/null || true
    sleep 3
    
    # Clean locks
    rm -f ~/.local/share/signal-cli/data/*.lock
    rm -f /data/.signal/data/*.lock
    
    # Start fresh
    SIGNAL_DATA_DIR=/data/.signal \
    signal-cli --trust-new-identities always \
        -a +15165643945 \
        daemon \
        --http 127.0.0.1:8080 \
        --no-receive-stdout \
        --receive-mode on-start \
        --ignore-stories \
        >> /tmp/signal-daemon.log 2>&1 &
    
    new_pid=$!
    echo $new_pid > "$PIDFILE"
    
    # Wait and verify
    sleep 5
    
    if kill -0 $new_pid 2>/dev/null; then
        if curl -s http://127.0.0.1:8080/api/v1/rpc \
           -X POST \
           -H "Content-Type: application/json" \
           -d '{"jsonrpc":"2.0","id":"1","method":"version"}' \
           | grep -q "version"; then
            log "SUCCESS: Daemon restarted (PID: $new_pid)"
            
            # Send alert (max once per hour)
            if [ ! -f "$ALERT_FILE" ] || [ $(($(date +%s) - $(stat -c %Y "$ALERT_FILE" 2>/dev/null || echo 0))) -gt 3600 ]; then
                # Send test message via API
                curl -s http://127.0.0.1:8080/api/v1/rpc \
                    -X POST \
                    -H "Content-Type: application/json" \
                    -d '{"jsonrpc":"2.0","id":"2","method":"send","params":{"recipient":"+19194133445","message":"🔄 Signal daemon auto-restarted due to health check failure. Now stable."}}' \
                    > /dev/null 2>&1
                touch "$ALERT_FILE"
            fi
            return 0
        fi
    fi
    
    log "FAILED: Could not restart daemon"
    return 1
}

# Main check
if ! check_health; then
    restart_daemon
else
    # Log success every 10 minutes (to avoid log spam)
    if [ $(($(date +%s) % 600)) -lt 60 ]; then
        log "OK: Daemon healthy"
    fi
fi
