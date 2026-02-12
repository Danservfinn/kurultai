# Neo4j IPv6 Connection Issue - Workaround Research Report

**Problem Summary:**
- Cannot connect to Neo4j at `bolt://neo4j.railway.internal:7687` from container
- Hostname resolves to IPv6: `fd12:793a:be06:1:a000:86:bd12:7f5d`
- IPv6 connection fails (error 11 - connection refused)
- Railway environment with legacy IPv6-only networking
- Neo4j listens on IPv4 (0.0.0.0) by default, not IPv6
- Setting `NEO4J_dbms_default__listen__address=::` would fix but requires Railway dashboard access

---

## 1. CONNECTION STRING VARIATIONS (Quick Wins - No Dashboard Required)

### Attempt These Immediately:

| Connection String | Format | Likelihood | Notes |
|-------------------|--------|------------|-------|
| `bolt://[fd12:793a:be06:1:a000:86:bd12:7f5d]:7687` | Bracketed IPv6 literal | **LOW** | Only works if Neo4j listens on IPv6 |
| `bolt://neo4j.railway.internal:7687` | Current (fails) | **FAILING** | Resolves to IPv6, but Neo4j not listening on IPv6 |
| `neo4j://neo4j.railway.internal:7687` | Routing protocol | **LOW** | Same underlying issue |
| `bolt://[::1]:7687` | IPv6 localhost | **LOW** | Only for local Neo4j instance |

### IPv6 Literal Formats to Try:
```
bolt://[fd12:793a:be06:1:a000:86:bd12:7f5d]:7687
bolt://fd12:793a:be06:1:a000:86:bd12:7f5d:7687  (without brackets - MAY NOT WORK)
neo4j+s://[fd12:793a:be06:1:a000:86:bd12:7f5d]:7687
```

**Assessment:** Connection string variations are unlikely to work because the core issue is Neo4j not binding to IPv6. The connection string format won't change what interfaces Neo4j listens on.

---

## 2. RAILWAY-SPECIFIC NETWORKING TRICKS

### 2.1 Railway Private Networking Deep Dive

**From Railway Docs:**
- Private networking uses Wireguard tunnels with encrypted mesh
- Legacy environments (pre-Oct 16, 2025): DNS resolves to **IPv6 only**
- New environments: DNS resolves to both IPv4 and IPv6
- Internal DNS pattern: `<service-name>.railway.internal`

**Key Insight:** This is a legacy environment issue. If possible, migrating to a new Railway environment would provide dual-stack (IPv4+IPv6) networking.

### 2.2 TCP Proxy Workaround

Railway supports TCP Proxy for exposing non-HTTP services:
- **Docs:** `/networking/tcp-proxy`
- Could expose Neo4j via public TCP proxy, then connect via public address
- **Trade-off:** Loses private networking benefits, exposes database publicly
- **Security mitigation:** Strong authentication, IP allowlisting if possible

### 2.3 Static Outbound IPs
- Docs: `/networking/static-outbound-ips`
- Not directly helpful for inbound Neo4j connections
- Could help if Neo4j is external and needs IP allowlisting

### 2.4 Railway Variable Reference
- Could reference Neo4j's `PORT` or other service variables
- But variables can't change how Neo4j binds to interfaces

---

## 3. NEO4J HTTP/HTTPS API ALTERNATIVE

### HTTP API Overview
- **Port 7474** (HTTP) and **7473** (HTTPS)
- **Note:** HTTP API is **NOT available on Aura** (but IS available on self-hosted)
- Docs: `neo4j.com/docs/http-api/current/`

### Can HTTP Work Where Bolt Fails?
**Possibly YES** - Worth Testing:
- HTTP/HTTPS connectors may bind differently than Bolt
- Could try: `http://neo4j.railway.internal:7474` or `https://neo4j.railway.internal:7473`
- The HTTP connector might have different default binding behavior

### HTTP API Capabilities:
- Execute Cypher statements via POST requests
- Supports both implicit and explicit transactions
- JSON request/response format
- Full Cypher support

### Implementation Pattern:
```javascript
// Using HTTP API instead of Bolt driver
const response = await fetch('http://neo4j.railway.internal:7474/db/neo4j/tx/commit', {
  method: 'POST',
  headers: {
    'Authorization': 'Basic ' + btoa('neo4j:password'),
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    statements: [{ statement: 'MATCH (n) RETURN n LIMIT 10' }]
  })
});
```

### Testing Checklist:
- [ ] Check if Neo4j HTTP is enabled (port 7474)
- [ ] Try `http://neo4j.railway.internal:7474`
- [ ] Try `http://[fd12:793a:be06:1:a000:86:bd12:7f5d]:7474`
- [ ] Verify Neo4j version (HTTP API has evolved)

---

## 4. RAILWAY API/CLI OPTIONS

### Railway Public API
- **Endpoint:** `https://backboard.railway.app/graphql/v2`
- **Docs:** `docs.railway.com/integrations/api`
- **Token Types:** Account, Workspace, Project tokens

### Variable Management via API
The Railway API supports setting environment variables:

```graphql
mutation variableUpsert {
  variableUpsert(
    input: {
      projectId: "YOUR_PROJECT_ID"
      environmentId: "YOUR_ENV_ID"
      serviceId: "YOUR_SERVICE_ID"
      name: "NEO4J_dbms_default__listen__address"
      value: "::"
    }
  ) {
    id
    name
    value
  }
}
```

**Key Finding:** You CAN modify service environment variables via the Railway API without dashboard access, IF you have:
- A Railway API token (Account, Workspace, or Project token)
- The project/environment/service IDs

### Steps to Set Variable via API:
1. Generate token at `railway.com/account/tokens`
2. Query for project/service IDs
3. Use `variableUpsert` mutation to set `NEO4J_dbms_default__listen__address=::`
4. Trigger redeploy

### Railway CLI Variable Commands:
```bash
# Set variable via CLI
railway variable NEO4J_dbms_default__listen__address="::"

# Redeploy
railway redeploy
```

**Note:** CLI requires authentication (`railway login`) but can be done from any machine, not just Railway dashboard.

---

## 5. NEO4J CONFIGURATION WORKAROUNDS

### 5.1 Docker Environment Variable Mapping

Neo4j Docker image accepts configuration via environment variables:
- **Pattern:** `NEO4J_<setting_name>` with `.` → `_` and `_` → `__`
- **Docs:** `neo4j.com/docs/operations-manual/current/docker/configuration/`

**The Fix:**
```bash
NEO4J_dbms_default__listen__address=::
```
This sets `dbms.default_listen_address=::` in neo4j.conf, making Neo4j listen on all IPv6 interfaces.

### 5.2 Alternative Config Variables to Try

| Variable | Purpose | Effect |
|----------|---------|--------|
| `NEO4J_server_bolt_listen__address` | Bolt specific | `::7687` for IPv6-only Bolt |
| `NEO4J_server_default__listen__address` | All connectors | `::` for all protocols |
| `NEO4J_dbms_connector_bolt_listen__address` | Legacy config | May work on older versions |

### 5.3 Custom Configuration Volume
- Mount `/conf` volume with custom `neo4j.conf`
- Set `server.default_listen_address=::`
- **Issue:** Requires modifying Railway service deployment config

### 5.4 EXTENSION_SCRIPT Environment Variable
- Neo4j Docker supports `EXTENSION_SCRIPT` env var
- Points to a script that can modify configuration at startup
- Could potentially patch neo4j.conf before startup
- **Example:**
```bash
EXTENSION_SCRIPT=/data/extend.sh
```
Where `extend.sh`:
```bash
#!/bin/bash
echo "server.default_listen_address=::" >> /var/lib/neo4j/conf/neo4j.conf
```

---

## 6. PUBLIC NEO4J ALTERNATIVES (Free Tiers)

### 6.1 Neo4j AuraDB Free Tier

**Status: RECOMMENDED FALLBACK**

**Details:**
- Free tier available at `neo4j.com/cloud/platform/aura-graph-database/`
- 200,000 nodes and 400,000 relationships
- 1GB RAM instance
- Always-on, zero admin
- Connect via `neo4j+s://` URI (Bolt over TLS)
- **No IPv6 issues** - managed cloud service

**Pros:**
- No infrastructure management
- Automatic backups
- Works immediately
- Free tier sufficient for development/testing

**Cons:**
- Data limits (200K nodes)
- Not self-hosted
- Potential egress costs from Railway

### 6.2 Neo4j Sandbox
- `sandbox.neo4j.com`
- Free temporary instances
- Pre-built datasets
- Good for experimentation
- **Not suitable** for production use

### 6.3 Self-Hosted Alternatives

If Railway continues to be problematic:

| Provider | Free Tier | Notes |
|----------|-----------|-------|
| **Fly.io** | Yes | Better IPv6 support |
| **Render** | Yes | Native IPv6 |
| **DigitalOcean** | $200 credit | Full control |
| **Hetzner Cloud** | No | Cheap, IPv6 native |
| **AWS EC2** | 12 months free | Full control |

---

## 7. ATTEMPT SEQUENCE (Ranked by Feasibility)

### Immediate Actions (No Dashboard Needed):

1. **TRY HTTP API** (5 min)
   - Test `http://neo4j.railway.internal:7474`
   - May work even if Bolt doesn't
   - Quick win if successful

2. **SET ENV VAR VIA RAILWAY API/CLI** (15 min)
   - Use Railway CLI: `railway variable NEO4J_dbms_default__listen__address="::"`
   - Or use GraphQL API with token
   - Redeploy service
   - **This is the ACTUAL FIX if it works**

3. **TRY EXTENSION_SCRIPT** (10 min)
   - Set `EXTENSION_SCRIPT` env var
   - Script modifies neo4j.conf at startup
   - Requires container restart

### Medium Effort:

4. **CREATE NEW RAILWAY ENVIRONMENT** (30 min)
   - New environments have dual-stack networking
   - Migrate services to new environment
   - IPv4 fallback available

5. **SET UP TCP PROXY** (20 min)
   - Expose Neo4j via public TCP proxy
   - Connect via public address
   - Security implications

### Fallback Options:

6. **MIGRATE TO NEO4J AURA FREE TIER** (1 hour)
   - Sign up at console.neo4j.io
   - Update connection string in app
   - Migrate data if needed

7. **DEPLOY NEO4J ON ALTERNATIVE PLATFORM** (2+ hours)
   - Fly.io, Render, or other
   - Better IPv6 support

---

## 8. DOCUMENTATION OF TRIED APPROACHES

| Approach | Tried | Result | Notes |
|----------|-------|--------|-------|
| `bolt://neo4j.railway.internal:7687` | YES | ❌ IPv6 connection refused | Resolves to IPv6, Neo4j not listening |
| Bracketed IPv6 literal | ? | ? | Try: `bolt://[fd12:...]:7687` |
| HTTP API | ? | ? | Try: `http://neo4j.railway.internal:7474` |
| NEO4J_dbms_default__listen__address=:: | NO | N/A | **PRIMARY FIX TO TRY** |
| Railway CLI variable set | NO | N/A | May work without dashboard |
| TCP Proxy | NO | N/A | Public exposure trade-off |

---

## 9. KEY FINDINGS SUMMARY

### The Core Issue
Neo4j defaults to listening on IPv4 (`0.0.0.0`) only. Railway legacy environments use IPv6-only private networking. The solution is making Neo4j listen on IPv6 (`::`).

### The Solution
Set `NEO4J_dbms_default__listen__address=::` as an environment variable on the Neo4j service.

### How to Apply the Solution
**Option A: Railway CLI (Recommended First Try)**
```bash
railway login
railway link  # select project
railway variable NEO4J_dbms_default__listen__address="::"
railway redeploy
```

**Option B: Railway API**
- Get token from `railway.com/account/tokens`
- Use GraphQL `variableUpsert` mutation
- Trigger redeploy

**Option C: Railway Dashboard (if you regain access)**
- Go to Neo4j service → Variables
- Add `NEO4J_dbms_default__listen__address=::`
- Redeploy

### HTTP API May Work Without Changes
Before trying the above, test if Neo4j HTTP connector (port 7474) responds on IPv6. HTTP and Bolt connectors may bind differently.

---

## 10. NEXT STEPS RECOMMENDATION

1. **IMMEDIATE (5 min):** Test HTTP API endpoint
2. **QUICK FIX (15 min):** Try Railway CLI to set the listen address variable
3. **IF CLI FAILS:** Try Railway API with token
4. **IF ALL FAIL:** Set up Neo4j Aura free tier as fallback
5. **LONG-TERM:** Consider migrating to a Railway environment with dual-stack networking

---

*Report compiled by: Möngke (Researcher)*
*Date: 2026-02-12*
*Sources: Neo4j Operations Manual, Railway Documentation, Docker Hub*
