# Signal Config Lock Prevention Plan

## Problem
Signal-cli config file locks when multiple instances try to access it simultaneously:
```
INFO SignalAccount - Config file is in use by another instance, waiting…
```

## Root Cause
- Multiple signal-cli processes running
- No process management to ensure single daemon
- No automatic cleanup of stale locks

## Solution

### Phase 1: Immediate Fix (5 min)
1. Kill all existing signal-cli processes
2. Remove stale lock files
3. Start single daemon with proper configuration

### Phase 2: Process Management (15 min)
1. Create systemd service or supervisor config
2. Ensure only one daemon instance runs
3. Auto-restart on failure

### Phase 3: Lock Monitoring (10 min)
1. Add health check for config lock
2. Alert if lock persists >30 seconds
3. Auto-cleanup stale locks

### Phase 4: Documentation (5 min)
1. Document signal-cli daemon management
2. Add troubleshooting guide

## Implementation

```bash
# Phase 1: Immediate cleanup
pkill -9 signal-cli
rm -f ~/.local/share/signal-cli/data/*.lock
signal-cli daemon --http 127.0.0.1:8080 &

# Phase 2: Create supervisor script
cat > /usr/local/bin/signal-daemon-manager.sh << 'EOF'
#!/bin/bash
# Ensure only one signal-cli daemon runs

PIDFILE=/var/run/signal-cli.pid

# Kill existing
if [ -f $PIDFILE ]; then
    kill $(cat $PIDFILE) 2>/dev/null
fi

# Clean locks
rm -f ~/.local/share/signal-cli/data/*.lock

# Start daemon
signal-cli daemon --http 127.0.0.1:8080 &
echo $! > $PIDFILE
EOF

chmod +x /usr/local/bin/signal-daemon-manager.sh

# Phase 3: Health check
# Add to Jochi's health checks
```

## Verification
- Single daemon process running
- No config lock errors in logs
- Messages send/receive without delays

## Timeline: 35 minutes total