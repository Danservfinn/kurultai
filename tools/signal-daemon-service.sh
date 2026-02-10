#!/bin/bash
# Signal Daemon Service - Runs continuously and monitors/restarts as needed
# Usage: signal-daemon-service.sh &

PIDFILE=/tmp/signal-daemon.pid
LOGFILE=/tmp/signal-daemon-service.log
HEALTH_CHECK_INTERVAL=60  # seconds
RESTART_COOLDOWN=300      # 5 minutes between restarts

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOGFILE"
}

# Ensure single instance
if [ -f /tmp/signal-service.lock ]; then
    pid=$(cat /tmp/signal-service.lock 2>/dev/null)
    if kill -0 "$pid" 2>/dev/null; then
        log "ERROR: Service already running (PID: $pid)"
        exit 1
    fi
fi
echo $$ > /tmp/signal-service.lock

log "Service started (PID: $$)"

# Cleanup on exit
trap 'rm -f /tmp/signal-service.lock; log "Service stopped"; exit 0' EXIT TERM INT

last_restart=0

while true; do
    # Check if daemon is running and healthy
    healthy=true
    
    # Check process
    if [ -f "$PIDFILE" ]; then
        pid=$(cat "$PIDFILE" 2>/dev/null)
        if ! kill -0 "$pid" 2>/dev/null; then
            log "Daemon process not found"
            healthy=false
        fi
    else
        log "PID file not found"
        healthy=false
    fi
    
    # Check API
    if [ "$healthy" = true ]; then
        if ! curl -s http://127.0.0.1:8080/api/v1/rpc \
            -X POST \
            -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","id":"1","method":"version"}' \
            | grep -q "version"; then
            log "API not responding"
            healthy=false
        fi
    fi
    
    # Check for lock errors
    if [ "$healthy" = true ]; then
        if tail -5 /tmp/signal-daemon.log 2>/dev/null | grep -q "Config file is in use"; then
            log "Config lock detected"
            healthy=false
        fi
    fi
    
    # Restart if unhealthy
    if [ "$healthy" = false ]; then
        now=$(date +%s)
        if [ $((now - last_restart)) -gt $RESTART_COOLDOWN ]; then
            log "RESTARTING: Signal daemon"
            
            # Kill existing
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
            last_restart=$now
            
            # Wait for startup
            sleep 5
            
            # Verify
            if curl -s http://127.0.0.1:8080/api/v1/rpc \
                -X POST \
                -H "Content-Type: application/json" \
                -d '{"jsonrpc":"2.0","id":"1","method":"version"}' \
                | grep -q "version"; then
                log "SUCCESS: Daemon restarted (PID: $new_pid)"
            else
                log "FAILED: Restart unsuccessful"
            fi
        else
            log "SKIPPING: Restart cooldown active ($((RESTART_COOLDOWN - (now - last_restart)))s remaining)"
        fi
    fi
    
    sleep $HEALTH_CHECK_INTERVAL
done
