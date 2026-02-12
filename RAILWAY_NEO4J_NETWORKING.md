# Railway Neo4j Networking Troubleshooting Guide

## Problem Summary

**Issue:** Container can resolve `neo4j.railway.internal` → IPv6 address, but cannot connect to port 7687 (timeout)

**Root Cause Patterns:**
1. Neo4j not configured to listen on IPv6 interfaces
2. Neo4j only listening on localhost (127.0.0.1)
3. Railway internal networking DNS returns IPv6, but Neo4j binds to IPv4
4. Neo4j service still starting up (cold start latency)

---

## Quick Diagnostic Commands

Run these in your Railway container:

```bash
# 1. Check Railway environment variables
env | grep -E "^RAILWAY_"

# 2. Test DNS resolution
getent hosts neo4j.railway.internal
nslookup neo4j.railway.internal

# 3. Test port connectivity (replace <IP> with resolved address)
timeout 5 bash -c 'echo > /dev/tcp/<IP>/7687' && echo "OPEN" || echo "TIMEOUT"

# 4. Check if Neo4j is running
ps aux | grep neo4j
netstat -tlnp | grep 7687

# 5. Run full diagnostic script
chmod +x railway-network-debug.sh && ./railway-network-debug.sh
python3 railway-neo4j-diagnose.py
```

---

## Railway Environment Variables

### Core Railway Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `RAILWAY_SERVICE_NAME` | Current service name | `api`, `neo4j` |
| `RAILWAY_PROJECT_NAME` | Project name | `my-project` |
| `RAILWAY_ENVIRONMENT_NAME` | Environment (production/staging) | `production` |
| `RAILWAY_SERVICE_ID` | Unique service ID | `uuid-string` |
| `RAILWAY_PROJECT_ID` | Unique project ID | `uuid-string` |
| `RAILWAY_ENVIRONMENT_ID` | Environment ID | `uuid-string` |
| `RAILWAY_PRIVATE_DOMAIN` | Internal domain suffix | `railway.internal` |

### Service-Specific Variables (if using Railway's Neo4j template)

| Variable | Purpose |
|----------|---------|
| `NEO4J_URI` | Connection URI |
| `NEO4J_AUTH` | username/password |
| `NEO4J_PASSWORD` | Password only |
| `NEO4J_BOLT_URL` | Direct Bolt URL |

### Internal Networking Pattern

Railway uses the pattern: `{service-name}.railway.internal`

For a service named `neo4j`:
- Internal hostname: `neo4j.railway.internal`
- Resolves to: IPv6 address (commonly)
- Ports: 7687 (Bolt), 7474 (HTTP), 7473 (HTTPS)

---

## IPv6-Specific Issues

### The Core Problem

Railway's internal DNS often returns **IPv6 addresses** for service discovery. However, Neo4j by default may:
1. Only listen on `127.0.0.1` (localhost)
2. Only listen on `0.0.0.0` (all IPv4)
3. Not bind to IPv6 unless explicitly configured

### Neo4j Configuration Fix

In your Neo4j service, set these environment variables:

```bash
# Option 1: Listen on all interfaces (IPv4 + IPv6)
NEO4J_dbms_default__listen__address=::

# Option 2: Listen on specific addresses
NEO4J_dbms_connector_bolt_listen__address=::
NEO4J_dbms_connector_http_listen__address=::

# Option 3: Keep IPv4 but force Railway DNS to return IPv4
# (Not always possible - see workaround below)
```

Or in `neo4j.conf`:
```properties
# Listen on all interfaces including IPv6
dbms.default_listen_address=::
```

---

## Alternative Connection Approaches

### Approach 1: Direct IP Connection

If DNS resolution returns an IP that works:

```python
import os
import socket

# Get IP from environment or resolve manually
neo4j_host = os.environ.get('NEO4J_HOST', 'neo4j.railway.internal')

# Try to get IPv4 if available
try:
    addr_info = socket.getaddrinfo(neo4j_host, 7687, socket.AF_INET)
    ipv4 = addr_info[0][4][0]
    uri = f"bolt://{ipv4}:7687"
except:
    # Fall back to hostname
    uri = f"bolt://{neo4j_host}:7687"
```

### Approach 2: Railway Public URL (Temporary)

If internal networking fails, use Railway's public URL:

```bash
# In Neo4j service, check for:
RAILWAY_PUBLIC_DOMAIN=neo4j-xxx.up.railway.app

# Then connect via:
NEO4J_URI=neo4j+s://neo4j-xxx.up.railway.app:443
```

⚠️ **Warning:** This exposes Neo4j to the public internet. Use auth and only as temporary workaround.

### Approach 3: Service-to-Service via Railway Variables

Reference the Neo4j service directly:

```bash
# In your application service, reference Neo4j:
NEO4J_URI=bolt://${NEO4J_SERVICE_NAME:-neo4j}:7687
```

### Approach 4: Docker Compose Networking (if using)

If both services are in the same Railway project:

```yaml
# railway.yaml or compose equivalent
services:
  neo4j:
    image: neo4j:latest
    environment:
      - NEO4J_dbms_default__listen__address=0.0.0.0
  
  api:
    build: .
    environment:
      - NEO4J_URI=bolt://neo4j:7687
```

---

## Immediate Workarounds

### Workaround 1: Force IPv4 Resolution

```bash
# Add to /etc/hosts (requires root, may not work on Railway)
echo "127.0.0.1 neo4j neo4j.railway.internal" >> /etc/hosts
```

### Workaround 2: Connection Retry with Fallback

```python
from neo4j import GraphDatabase
import socket

def get_working_uri():
    """Try multiple connection strategies"""
    
    # Strategy 1: Try IPv4 resolution
    try:
        addrs = socket.getaddrinfo('neo4j.railway.internal', 7687, socket.AF_INET)
        ip = addrs[0][4][0]
        return f"bolt://{ip}:7687"
    except:
        pass
    
    # Strategy 2: Try direct hostname
    return "bolt://neo4j:7687"

# Use with retry
driver = GraphDatabase.driver(
    get_working_uri(),
    auth=("neo4j", "password"),
    connection_timeout=10,
    max_connection_lifetime=3600
)
```

### Workaround 3: TCP Proxy Sidecar

Deploy a lightweight TCP proxy in your app container:

```bash
# Using socat
socat TCP4-LISTEN:17687,fork TCP6:[::1]:7687 &

# Then connect to localhost:17687 (IPv4) → forwards to IPv6
```

### Workaround 4: Use HTTP API Instead of Bolt

If Bolt protocol fails, try HTTP:

```python
import requests

# Neo4j HTTP API
url = "http://neo4j.railway.internal:7474/db/data/transaction/commit"
response = requests.post(url, json={"statements": [{"statement": "RETURN 1"}]})
```

---

## Diagnostic Checklist

- [ ] Neo4j service is running (check Railway logs)
- [ ] Neo4j has finished startup (not still initializing)
- [ ] Neo4j is listening on the expected port: `netstat -tlnp | grep 7687`
- [ ] Neo4j is listening on all interfaces, not just localhost
- [ ] DNS resolution works: `getent hosts neo4j.railway.internal`
- [ ] Port is accessible: `timeout 5 bash -c 'echo > /dev/tcp/<IP>/7687'`
- [ ] Bolt handshake works (use Python script)
- [ ] Firewall/security groups allow internal traffic
- [ ] Both services are in the same Railway project/environment

---

## Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `Connection timeout` | Neo4j not listening on IPv6 | Set `NEO4J_dbms_default__listen__address=::` |
| `Connection refused` | Neo4j not running or wrong port | Check Neo4j logs and port config |
| `DNS resolution failed` | Wrong service name | Verify `RAILWAY_SERVICE_NAME` |
| `Authentication failed` | Wrong credentials | Check `NEO4J_AUTH` or default password |
| `ServiceUnavailable` | Neo4j still starting | Add retry logic with backoff |

---

## Railway-Specific Notes

1. **Cold Start Latency**: Neo4j can take 30-60 seconds to start. Implement connection retries.

2. **Internal DNS**: Railway uses IPv6 for internal service discovery by default.

3. **Service Dependencies**: Define service startup order if needed in Railway config.

4. **Environment Variables**: Railway automatically injects connection info as env vars between linked services.

5. **Networking Isolation**: Services in different Railway projects cannot communicate via internal networking.

---

## Files Included

- `railway-network-debug.sh` - Bash diagnostic script
- `railway-neo4j-diagnose.py` - Python diagnostic script with Bolt handshake test
- `RAILWAY_NEO4J_NETWORKING.md` - This documentation

---

## Next Steps

1. Run the diagnostic scripts in your container
2. Check Neo4j configuration and logs
3. Apply the Neo4j IPv6 listen address fix
4. Implement connection retry logic in your application
5. If issues persist, contact Railway support with diagnostic output
