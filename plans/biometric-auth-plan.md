# Plan: Add Biometric Authentication to Moltbot Control UI

## Goal
Require Face ID (iPhone/iPad) or Touch ID (Mac) to access the Moltbot Control UI web dashboard, providing an additional layer of security beyond the gateway token.

## Current State
- Moltbot Control UI uses token-based authentication (`CLAWDBOT_GATEWAY_TOKEN`)
- No native support for WebAuthn/FIDO2/biometric authentication
- Railway hosts the Control UI at `https://<domain>/`

## Approach: Reverse Proxy with Biometric Gate

Since Moltbot doesn't natively support WebAuthn, we'll add a **Caddy reverse proxy with Cloudflare Access** (or similar) as an authentication layer in front of the Control UI.

### Architecture

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Device    │───▶│  Cloudflare      │───▶│   Moltbot       │
│ Face ID/    │    │  Access          │    │   Gateway       │
│ Touch ID    │    │  (WebAuthn)      │    │   (Railway)     │
└─────────────┘    └──────────────────┘    └─────────────────┘
                         │
                   Biometric Challenge
                   before proxying
```

### Why Cloudflare Access?
1. **Native WebAuthn support** - Works with Face ID, Touch ID, hardware keys
2. **Zero Trust architecture** - Every request authenticated
3. **Free tier available** - 50 users free
4. **No code changes to Moltbot** - Pure infrastructure layer
5. **Works with Railway** - Just change DNS routing

## Implementation Plan

### Phase 1: Cloudflare Setup (15 min)

1. **Add domain to Cloudflare** (if not already)
   - Your Moltbot domain needs DNS managed by Cloudflare
   - Or use a Cloudflare Tunnel for the Railway service

2. **Enable Cloudflare Access** (Zero Trust dashboard)
   ```
   https://one.dash.cloudflare.com/
   ```

3. **Create Access Application**
   - Application name: "Moltbot Control UI"
   - Application domain: `moltbot.yourdomain.com` (or your Railway domain)
   - Session duration: 24 hours (configurable)

### Phase 2: Configure WebAuthn Policy (10 min)

1. **Create Access Policy**
   - Policy name: "Biometric Required"
   - Action: Allow
   - Include: Email ending in `@youremail.com` (or specific emails)

2. **Set Authentication Method**
   - Require: **Hardware Key or Platform Authenticator**
   - This forces Face ID/Touch ID on supported devices

3. **Configure Identity Providers**
   - Option A: One-time PIN (email code + biometric)
   - Option B: GitHub/Google OAuth + biometric
   - Recommended: One-time PIN for simplicity

### Phase 3: Railway Configuration (10 min)

**Option A: Cloudflare Tunnel (Recommended)**

1. Create Cloudflare Tunnel in Zero Trust dashboard
2. Install `cloudflared` connector on Railway:

```dockerfile
# Add to Railway Dockerfile or create sidecar service
FROM cloudflare/cloudflared:latest
CMD ["tunnel", "--no-autoupdate", "run", "--token", "$CLOUDFLARE_TUNNEL_TOKEN"]
```

3. Route tunnel to `localhost:8080` (Moltbot gateway)

**Option B: DNS Proxy (if domain on Cloudflare)**

1. Point domain A record to Railway
2. Enable Cloudflare Proxy (orange cloud)
3. Access policies apply automatically

### Phase 4: Device Registration (5 min per device)

1. **First access** to Control UI triggers enrollment:
   - Enter email → receive one-time code
   - Prompted to register Face ID/Touch ID
   - Device bound to your identity

2. **Subsequent access**:
   - Cloudflare challenges with WebAuthn
   - Device prompts for Face ID/Touch ID
   - On success, proxies to Moltbot

### Phase 5: Fallback Configuration

Configure backup authentication for:
- Devices without biometrics
- Recovery scenarios

```yaml
# Cloudflare Access Policy
Rules:
  - Require: Platform Authenticator (Face ID/Touch ID)
  - Fallback: Hardware Security Key (YubiKey)
  - Emergency: One-time PIN + Email verification
```

## Alternative Approaches

### Alternative 1: Tailscale with Device Auth
- Pros: Simple, works with any Railway service
- Cons: Requires Tailscale client on all devices

### Alternative 2: Custom Caddy Proxy with WebAuthn
- Pros: Self-hosted, no third-party dependency
- Cons: More complex setup, need to host Caddy somewhere

### Alternative 3: Modify Moltbot Source
- Pros: Native integration
- Cons: Requires forking Moltbot, maintaining patches

**Recommendation**: Cloudflare Access is the best balance of security, simplicity, and cost.

## Critical Files/Services

| Component | Location | Changes |
|-----------|----------|---------|
| Cloudflare Access | one.dash.cloudflare.com | Create application + policy |
| DNS Records | Cloudflare DNS | Point to tunnel or Railway |
| Railway Service | Railway dashboard | Add tunnel sidecar (if using tunnel) |
| Environment Vars | Railway | Add `CLOUDFLARE_TUNNEL_TOKEN` |

## Verification

1. **Access Control UI** from iPhone
   - Should prompt for Face ID before showing dashboard
   - ✓ Pass: Dashboard loads after biometric
   - ✗ Fail: Dashboard loads without biometric

2. **Access Control UI** from Mac
   - Should prompt for Touch ID
   - ✓ Pass: Touch ID required
   - ✗ Fail: Bypassed biometric

3. **Test fallback**
   - Disable biometrics on device
   - Should require hardware key or email verification

4. **Session persistence**
   - After auth, should stay authenticated for session duration
   - New browser/incognito should require re-authentication

## Security Considerations

- **Session duration**: 24 hours recommended (balance security/convenience)
- **Device binding**: Each device registers separately
- **Audit logs**: Cloudflare logs all access attempts
- **Revocation**: Can instantly revoke access from dashboard

## Cost

- **Cloudflare Access Free Tier**: 50 users, unlimited applications
- **Cloudflare Tunnel**: Free
- **Total**: $0/month for personal use

## Timeline

| Phase | Task | Duration |
|-------|------|----------|
| 1 | Cloudflare setup | 15 min |
| 2 | WebAuthn policy | 10 min |
| 3 | Railway config | 10 min |
| 4 | Device registration | 5 min |
| 5 | Testing | 10 min |
| **Total** | | ~50 min |
