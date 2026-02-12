# Infrastructure Status - Kurultai

## Current State (2026-02-12)

### Signal: ✅ OPERATIONAL
**Status:** SSE Bridge running at http://127.0.0.1:8080
**Health:** {"status": "healthy", "signal_cli_running": true}
**Capabilities:**
- ✅ Text messages (send/receive)
- ✅ Media attachments (base64 encoded)
- ✅ Instant delivery (~500ms latency)
- ✅ OpenClaw integration ready

**Note:** Bridge provides SSE endpoint that OpenClaw expects. signal-cli 0.13.24 only provides JSON-RPC, so the bridge translates between protocols.

### Neo4j: ⚠️ RAILWAY-INTERNAL ONLY
**URI:** bolt://neo4j.railway.internal:7687
**Issue:** Hostname only resolves within Railway's private network
**Impact:** Cannot connect from external environments
**Workaround:** None - requires Railway deployment or public Neo4j endpoint

### OpenClaw Gateway: ⏸️ NOT RUNNING
**Status:** Stopped (not started in current session)
**Action needed:** `openclaw gateway` to start

## Autonomous Debugging Checklist

When I detect issues, I should:
1. Check actual service status (curl, process check)
2. Verify environment variables are set
3. Test connectivity with timeout
4. Report root cause, not symptom
5. Update status files immediately

## Known Limitations

1. **Neo4j:** Railway-internal networking - cannot access from outside Railway
2. **Signal:** Requires bridge running (now automated via start script)
3. **OpenClaw:** Manual start required (no auto-start in current setup)
