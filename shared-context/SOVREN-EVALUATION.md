# Sovren / Augmentum OS Evaluation

**Evaluated:** 2026-03-02  
**Sources:** 
- https://github.com/sovren-software/sovren-software.github.io
- https://sovren.software/augmentum

---

## What is Sovren?

**Sovren Software** is building a "sovereign computing platform" with three products:

| Product | Layer | Status |
|---------|-------|--------|
| **Augmentum OS** | Computing (NixOS-based) | Ships Summer 2026 |
| **Visage** | Identity (face auth via PAM + ONNX) | ✅ Live v0.2.0 (MIT) |
| **MrHaven** | Finance (USDC time vault on Base L2) | ✅ Live on mainnet |

---

## Augmentum OS Features

### Core Features
- **Base:** NixOS (declarative, version-controlled, rollback-capable)
- **Interface:** Voice-native command layer with natural language
- **Authentication:** Biometric (Visage) + MFA + session-scoped privileges
- **AI Layer:** Local-first inference by default, optional cloud
- **Orchestration:** Programmable automation with explicit agent boundaries

### Key Claims
- "One operator. Total authority."
- "UX, privacy, and security — none sacrificed"
- "Local inference by default with optional cloud"
- "Your operational data stays yours"
- "No telemetry collected by us"
- "Entire OS state in one reproducible config"

---

## Technical Stack

| Component | Technology |
|-----------|------------|
| **Base OS** | NixOS (declarative, reproducible) |
| **Auth** | Visage (ONNX face inference via PAM) |
| **AI** | Local inference (default) + optional cloud |
| **Config** | Single declarative config file |
| **Finance** | MrHaven (USDC vault on Base L2) |

---

## Evaluation: Should We Move from Mac?

### ✅ PROS

| Benefit | Relevance to Kurultai |
|---------|----------------------|
| **NixOS base** | Reproducible dev environments, version-controlled configs |
| **Local-first AI** | Aligns with our local LLM strategy (LM Studio, nano-banana-pro) |
| **Privacy-focused** | No telemetry, data stays local |
| **Declarative config** | Version-controlled OS state, easy rollback |
| **Sovereign computing** | Full control over system, no vendor lock-in |
| **Biometric auth** | Visage integration for secure access |

### ❌ CONS / RISKS

| Concern | Impact |
|---------|--------|
| **Not released yet** | Ships Summer 2026 (4+ months away) |
| **NixOS learning curve** | Significant time investment to learn Nix/NixOS |
| **Hardware compatibility** | May not support all Mac hardware (ARM/M-series) |
| **App ecosystem** | Limited compared to macOS (no native Xcode, Adobe, etc.) |
| **Unproven** | New project, no track record of stability |
| **Migration cost** | Significant effort to migrate from macOS |

---

## Recommendation: WAIT AND OBSERVE

### Current State (Mac)
- ✅ Stable, proven platform
- ✅ Full hardware support (M-series Mac mini)
- ✅ Full app ecosystem
- ✅ Working with our stack (LM Studio, OpenClaw, Neo4j, Railway)
- ✅ Low friction, high productivity

### Future State (Augmentum OS)
- ⏳ Promising features (local AI, declarative config, privacy)
- ⏳ Aligned with sovereignty values
- ⏳ **BUT:** Not available until Summer 2026
- ⏳ **Risk:** Unproven, potential compatibility issues

---

## Strategic Approach

### Phase 1: Monitor (Now - Summer 2026)
- [ ] Watch Sovren's progress (GitHub, newsletter)
- [ ] Test Visage (already available, MIT licensed)
- [ ] Evaluate MrHaven (live on mainnet)
- [ ] Join community/discord if available

### Phase 2: Test (Summer 2026)
- [ ] Install Augmentum OS on secondary machine
- [ ] Test with Kurultai stack (OpenClaw, Neo4j, etc.)
- [ ] Evaluate performance, compatibility
- [ ] Test local AI inference capabilities

### Phase 3: Migrate (If Viable)
- [ ] Migrate dev environment to Augmentum
- [ ] Keep Mac as fallback
- [ ] Gradual transition, not all-at-once

---

## Immediate Actions

### 1. Subscribe to Launch Briefing
```bash
# Visit https://sovren.software/augmentum
# Sign up for launch briefing newsletter
```

### 2. Test Visage (Available Now)
```bash
# Visage is MIT licensed and available
# GitHub: https://github.com/sovren-software/visage
# Test on Mac first, then on Augmentum when available
```

### 3. Monitor Development
- Watch GitHub org: https://github.com/sovren-software
- Follow release announcements
- Join community if available

---

## Verdict

### ❌ DON'T MIGRATE NOW
- Augmentum OS doesn't exist yet (Summer 2026)
- Mac is stable and working well
- Migration cost is high, benefit is uncertain

### ✅ DO ENGAGE NOW
- Subscribe to launch briefing
- Test Visage on Mac
- Monitor development progress
- Evaluate when beta/release candidate available

### 🎯 RECOMMENDATION

**Stay on macOS for now. Re-evaluate when Augmentum OS beta is available (Q2-Q3 2026).**

The vision aligns with our values (sovereignty, local AI, privacy), but:
- The product doesn't exist yet
- Migration risk is significant
- Mac is working well for Kurultai

**Best approach:** Monitor, test Visage, prepare for potential migration in Summer 2026.

---

## Files to Watch

- **GitHub:** https://github.com/sovren-software
- **Visage:** https://github.com/sovren-software/visage (MIT, available now)
- **Website:** https://sovren.software
- **Augmentum:** https://sovren.software/augmentum (launch briefing signup)

---

**Last Updated:** 2026-03-02  
**Next Review:** When Augmentum OS beta announced (expected Q2 2026)
