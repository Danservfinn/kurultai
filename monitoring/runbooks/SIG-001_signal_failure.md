# SIG-001: Signal Service Failure

**Severity**: Medium
**Affected Component**: Signal CLI / Message Delivery
**Recovery Time**: 3-5 minutes

## Symptoms
- Messages not being sent or received via Signal
- Signal CLI daemon not responding
- "Failed to send Signal message" errors
- Signal container in unhealthy state
- Message queue backing up

## Diagnosis
```bash
# 1. Check Signal daemon status
docker ps | grep signal
systemctl status signal-cli  # if running natively

# 2. Check Signal logs
docker logs signal-cli --tail 100
journalctl -u signal-cli -n 100  # if running natively

# 3. Check Signal registration status
docker exec signal-cli signal-cli -a +PHONE_NUMBER getUserStatus +PHONE_NUMBER

# 4. Check for rate limiting
docker logs signal-cli | grep -i "rate\|limit\|429"

# 5. Verify Signal data directory
ls -la /data/signal/
docker exec signal-cli ls -la /home/signal/.local/share/signal-cli/

# 6. Check network connectivity to Signal servers
curl -I https://chat.signal.org

# 7. Check message queue depth
redis-cli LLEN signal:outgoing  # if using Redis queue
```

## Recovery Steps
### Step 1: Diagnose Signal Channel
```bash
SIGNAL_CONTAINER="signal-cli"
SIGNAL_ACCOUNT="+1234567890"  # Replace with actual number

# Check if container is running
if docker ps | grep -q "$SIGNAL_CONTAINER"; then
    echo "Signal container is running"
else
    echo "Signal container NOT running"
fi
```

### Step 2: Check/Restore Registration
```bash
# Verify registration
docker exec "$SIGNAL_CONTAINER" signal-cli -a "$SIGNAL_ACCOUNT" listAccounts

# If not registered, check for backup registration data
if [ -f "/data/signal/data/accounts.json" ]; then
    echo "Found existing registration data, reloading..."
    docker restart "$SIGNAL_CONTAINER"
    sleep 10
else
    echo "CRITICAL: No registration data found"
    echo "Manual re-registration required:"
    echo "1. Run: docker exec -it $SIGNAL_CONTAINER signal-cli link"
    echo "2. Scan QR code with Signal app"
fi
```

### Step 3: Restart Signal Service
```bash
# Start container if not running
docker start "$SIGNAL_CONTAINER" || {
    # Recreate if start fails
    docker rm -f "$SIGNAL_CONTAINER" 2>/dev/null || true

    docker run -d \
        --name "$SIGNAL_CONTAINER" \
        --restart unless-stopped \
        -v /data/signal:/home/signal/.local/share/signal-cli \
        -p 8080:8080 \
        -e SIGNAL_ACCOUNT="$SIGNAL_ACCOUNT" \
        bbernhard/signal-cli-rest-api:latest
}

# Wait for service to be ready
sleep 10
```

### Step 4: Test Message Sending
```bash
# Send test message
TEST_RESULT=$(docker exec "$SIGNAL_CONTAINER" \
    signal-cli -a "$SIGNAL_ACCOUNT" \
    send -m "Recovery test $(date)" "$SIGNAL_ACCOUNT" 2>&1)

if echo "$TEST_RESULT" | grep -q "Failed\|Error"; then
    echo "Test message failed: $TEST_RESULT"
else
    echo "Test message sent successfully"
fi
```

### Step 5: Clear Message Queue (if backed up)
```bash
# Check queue depth
QUEUE_DEPTH=$(redis-cli LLEN signal:outgoing)
echo "Queue depth: $QUEUE_DEPTH"

# Process queue or flush if stale (implementation-specific)
# redis-cli LTRIM signal:outgoing 0 -100  # Keep only 100 most recent
```

## Rollback Options
1. **Container Rollback**: Restart Signal container
2. **Registration Rollback**: Restore registration data from backup
3. **Full Rollback**: Re-link Signal device (requires QR scan)

## Prevention Measures

```yaml
# docker-compose.yml - Signal resilience
services:
  signal-cli:
    image: bbernhard/signal-cli-rest-api:latest
    restart: unless-stopped
    environment:
      - MODE=normal
      - SIGNAL_ACCOUNT_NUMBER=${SIGNAL_ACCOUNT_NUMBER}
    volumes:
      - signal_data:/home/signal/.local/share/signal-cli
      - ./signal-backup:/backup:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 512M
    labels:
      - "backup.enabled=true"
      - "backup.schedule=0 */6 * * *"
```
