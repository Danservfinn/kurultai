# Neo4j IPv6 Fix for Railway

## Problem Summary

Neo4j connection fails on Railway because:
1. Railway's internal DNS (`neo4j.railway.internal`) returns **IPv6 addresses**
2. Neo4j by default only listens on **IPv4** (`0.0.0.0`)
3. This causes connection timeouts when services try to connect

## Solution Overview

### Primary Fix (Recommended)

Update the Neo4j service configuration in `railway.yml` to listen on both IPv4 and IPv6:

```yaml
neo4j:
  environment:
    # OLD (IPv4 only - BROKEN on Railway):
    - name: NEO4J_dbms_default__listen__address
      value: "0.0.0.0"
    
    # NEW (IPv4 + IPv6 - WORKS on Railway):
    - name: NEO4J_dbms_default__listen__address
      value: "::"
```

The `::` address tells Neo4j to listen on **all interfaces** (both IPv4 and IPv6).

## Quick Implementation

### Option 1: Apply Fix via Railway Dashboard (Immediate)

1. Go to Railway Dashboard → Your Project → Neo4j Service
2. Click "Variables" tab
3. Add/Update variable:
   - **Name**: `NEO4J_dbms_default__listen__address`
   - **Value**: `::`
4. Redeploy the Neo4j service

### Option 2: Update railway.yml (Recommended for IaC)

Apply the fix in `railway.yml` (already done if you're reading this):

```yaml
# In railway.yml, neo4j service section:
- name: NEO4J_dbms_default__listen__address
  value: "::"  # Changed from "0.0.0.0"
```

Then deploy:
```bash
railway up
```

## Verification

Run the diagnostic script to verify the fix:

```bash
# From any service container that connects to Neo4j
python3 scripts/neo4j-connection-helper.py --diagnose
```

Expected output after fix:
```
✅ DNS Resolution: WORKS (IPv6 addresses found)
✅ Port Connectivity: WORKS (port 7687 is open)
✅ Bolt Handshake: WORKS (Neo4j responding)
```

## Fallback Options

If the primary fix cannot be applied immediately, use these workarounds:

### Fallback 1: Connection Retry with Auto-Detection

Use the connection helper in your application code:

```python
from scripts.neo4j_connection_helper import create_neo4j_driver_with_fallback

driver = create_neo4j_driver_with_fallback(
    uri="bolt://neo4j.railway.internal:7687",
    user="neo4j",
    password=os.environ.get("NEO4J_PASSWORD")
)
```

### Fallback 2: Force IPv4 Resolution (If Available)

If Railway provides IPv4 fallback:

```python
import socket

def get_ipv4_for_host(hostname):
    """Try to get IPv4 address for hostname."""
    try:
        addrs = socket.getaddrinfo(hostname, None, socket.AF_INET)
        return addrs[0][4][0] if addrs else None
    except:
        return None

# Use IPv4 if available
ipv4 = get_ipv4_for_host("neo4j.railway.internal")
uri = f"bolt://{ipv4}:7687" if ipv4 else "bolt://neo4j.railway.internal:7687"
```

### Fallback 3: Railway Public URL (Emergency Only)

⚠️ **Security Warning**: This exposes Neo4j to the public internet. Use only temporarily!

1. Enable public networking for Neo4j in Railway Dashboard
2. Use the public URL with auth:
   ```
   NEO4J_URI=neo4j+s://neo4j-xxx.up.railway.app:443
   ```

## Files Included

| File | Purpose |
|------|---------|
| `railway.yml` | Updated with `NEO4J_dbms_default__listen__address=::` |
| `scripts/neo4j-connection-helper.py` | Python helper with fallback connection logic |
| `scripts/neo4j-ipv6-wrapper.sh` | Shell wrapper for container startup |
| `RAILWAY_NEO4J_NETWORKING.md` | Full troubleshooting guide |
| `railway-neo4j-diagnose.py` | Diagnostic script |
| `railway-network-debug.sh` | Network debugging script |

## Technical Details

### Why `::` Works

- `0.0.0.0` = IPv4 "all interfaces"
- `::` = IPv6 "all interfaces" (also enables IPv4 via dual-stack)

On modern Linux systems, binding to `::` enables **dual-stack** mode where the service accepts both IPv4 and IPv6 connections.

### Neo4j Configuration Hierarchy

Neo4j applies settings in this order (later overrides earlier):
1. Default values in `neo4j.conf`
2. Environment variables (highest priority)

The environment variable `NEO4J_dbms_default__listen__address` overrides any config file setting.

## Troubleshooting

### Still getting timeouts after fix?

1. **Check Neo4j is actually listening on IPv6:**
   ```bash
   # Inside Neo4j container
   netstat -tlnp | grep 7687
   # Should show :::7687 (IPv6) not 0.0.0.0:7687 (IPv4 only)
   ```

2. **Verify the environment variable is set:**
   ```bash
   env | grep NEO4J_dbms_default__listen__address
   # Should output: NEO4J_dbms_default__listen__address=::
   ```

3. **Check if Neo4j finished starting:**
   ```bash
   # View Neo4j logs in Railway Dashboard
   # Look for "Started Neo4j" message
   ```

4. **Try restarting both services:**
   - Restart Neo4j service first
   - Wait 30-60 seconds for startup
   - Then restart the connecting service

### Connection refused (not timeout)?

This usually means Neo4j is running but authentication failed:
- Check `NEO4J_PASSWORD` is set correctly
- Default user is `neo4j`

### DNS resolution fails?

Check Railway internal networking:
```bash
getent hosts neo4j.railway.internal
# Should return IPv6 address like: fd12:3456:7890::1
```

If DNS fails, verify:
- Both services are in the same Railway project
- Both services are in the same environment
- Service name is correct (check `RAILWAY_SERVICE_NAME`)

## References

- [Neo4j Docker Configuration](https://neo4j.com/docs/operations-manual/current/docker/configuration/)
- [Railway Internal Networking](https://docs.railway.app/reference/private-networking)
- [Neo4j Listen Address Configuration](https://neo4j.com/docs/operations-manual/current/configuration/ports/)

## Support

If issues persist after applying this fix:
1. Run `python3 railway-neo4j-diagnose.py` and save output
2. Check Railway service logs for both Neo4j and your application
3. Contact Railway support with diagnostic output
