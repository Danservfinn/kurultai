# stereOS Evaluation

**Evaluated:** 2026-03-02  
**Sources:** 
- https://github.com/papercomputeco/stereos
- https://github.com/papercomputeco/stereosd
- https://stereos.ai

---

## What is stereOS?

**stereOS** is "a Linux based operating system hardened and purpose-built for AI agents."

### Core Concept

stereOS runs AI coding agents inside **sandboxed Linux VMs** (not containers). Instead of giving agents access to your host machine, stereOS:
1. Boots a disposable VM
2. Injects credentials
3. Launches the agent in isolation

### Key Components

| Component | Purpose |
|-----------|---------|
| **masterblaster (mb)** | CLI that manages everything |
| **stereosd** | System daemon (control plane) |
| **agentd** | Agent management daemon |
| **Mixtapes** | Pre-built VM images with agents included |

---

## Technical Architecture

### VM-Based Isolation (Not Containers)

| Feature | stereOS | Containers | MicroVMs |
|---------|---------|------------|----------|
| **Full Isolation** | ✅ Own kernel, RAM, disk | ❌ Shared kernel | ⚠️ Limited |
| **Hardware Access** | ✅ GPU passthrough, secure boot | ❌ Limited | ❌ No |
| **FIPS Compliance** | ✅ Yes | ⚠️ Depends | ❌ No |
| **Bare Metal** | ✅ Yes | ✅ Yes | ❌ No |
| **Nested Virt** | ✅ Yes | ⚠️ Limited | ❌ Broken |

### Mixtape System

**Mixtapes** are pre-built VM images bundling:
- Hardened minimal Linux system
- Specific AI agent harnesses
- API key injection

**Available Mixtapes:**
| Mixtape | Agent Binary | API Key Required |
|---------|--------------|------------------|
| `opencode-mixtape` | opencode | ANTHROPIC_API_KEY or OPENAI_API_KEY |

### Build Artifacts

stereOS produces multiple formats:

| Format | Output | Use Case |
|--------|--------|----------|
| **Raw EFI** | stereos.img | Apple Virt Framework bootable |
| **QCOW2** | stereos.qcow2 | QEMU/KVM |
| **Kernel artifacts** | bzImage, initrd, cmdline | Direct-kernel boot |

---

## Evaluation: Should We Move from Mac?

### ✅ PROS

| Benefit | Relevance to Kurultai |
|---------|----------------------|
| **Agent isolation** | Each agent runs in isolated VM (security) |
| **Purpose-built for AI** | Designed specifically for AI agent workloads |
| **GPU passthrough** | Could run local LLMs with GPU access |
| **Disposable VMs** | Clean state for each agent session |
| **Hardened security** | Security-first design |
| **Bare metal support** | Could run on dedicated hardware |
| **NixOS-based** | Reproducible, declarative configs |

### ❌ CONS / RISKS

| Concern | Impact |
|---------|--------|
| **Early stage** | Very new project, unproven stability |
| **VM overhead** | Running VMs adds latency vs. native processes |
| **Complexity** | VM management adds operational complexity |
| **Mac compatibility** | Unclear Apple Silicon (M-series) support |
| **Migration effort** | Significant work to migrate Kurultai stack |
| **Limited ecosystem** | New project, small community |
| **Resource intensive** | Each agent needs full VM (RAM, CPU, disk) |

---

## Comparison: Current Setup vs. stereOS

| Aspect | Current (macOS) | stereOS |
|--------|-----------------|---------|
| **Agent Model** | Native processes | Sandboxed VMs |
| **Isolation** | Process-level | Full VM isolation |
| **Resource Usage** | Low (shared OS) | High (per-VM overhead) |
| **Latency** | Low (native) | Higher (VM boot time) |
| **Security** | Standard macOS | Hardened Linux |
| **Maturity** | ✅ Proven | ⚠️ Early stage |
| **Mac Support** | ✅ Native | ⚠️ Unclear |
| **Local LLM** | ✅ LM Studio works | ⚠️ Would need GPU passthrough |
| **Migration Effort** | N/A | ⚠️ Significant |

---

## Recommendation: OBSERVE BUT DON'T MIGRATE

### Current State (macOS + Native Processes)
- ✅ **Stable** - macOS is proven, stable platform
- ✅ **Low overhead** - Agents run as native processes
- ✅ **Low latency** - No VM boot time
- ✅ **Full hardware support** - M-series Mac works perfectly
- ✅ **Working stack** - LM Studio, OpenClaw, Neo4j all working
- ✅ **Low friction** - Easy to develop and maintain

### Future State (stereOS)
- ⚠️ **Promising concept** - Agent isolation is valuable
- ⚠️ **Purpose-built for AI** - Aligned with our use case
- ❌ **Early stage** - Unproven, potential stability issues
- ❌ **VM overhead** - Each agent needs full VM resources
- ❌ **Unclear Mac support** - May not support Apple Silicon
- ❌ **High migration cost** - Significant re-architecture needed

---

## Strategic Approach

### Phase 1: Monitor (Now - 6-12 months)
- [ ] Watch stereOS development (GitHub stars, releases)
- [ ] Test locally with `mb` CLI on Mac (if supported)
- [ ] Evaluate stability and performance
- [ ] Join Discord community: https://discord.gg/T6Y4XkmmV5

### Phase 2: Experiment (When Mature)
- [ ] Test Kurultai agents in stereOS VMs
- [ ] Benchmark performance vs. native processes
- [ ] Evaluate isolation benefits vs. overhead costs
- [ ] Test on dedicated hardware (not primary Mac)

### Phase 3: Hybrid Approach (If Viable)
- [ ] Run sensitive agents in stereOS VMs (isolation)
- [ ] Keep primary Kurultai on macOS (stability)
- [ ] Use stereOS for specific use cases (not full migration)

---

## Immediate Actions

### 1. Install masterblaster CLI (Test on Mac)
```bash
curl -fsSL https://mb.stereos.ai/install | bash
```

### 2. Test Local VM
```bash
# Start daemon
mb serve

# Pull mixtape
mb pull opencode-mixtape

# Create jcard.toml
cat > jcard.toml << EOF
mixtape = "opencode-mixtape:latest"

[agent]
harness = "opencode"
prompt = "Test stereOS with Kurultai stack"
EOF

# Boot VM
mb up

# Test inside VM
mb ssh
```

### 3. Monitor Development
- Watch GitHub: https://github.com/papercomputeco/stereos
- Join Discord: https://discord.gg/T6Y4XkmmV5
- Check releases and stability reports

---

## Verdict

### ❌ DON'T MIGRATE NOW

| Reason | Impact |
|--------|--------|
| **Early stage project** | Unproven stability for production use |
| **VM overhead** | Significant resource overhead for our use case |
| **Mac compatibility** | Unclear Apple Silicon support |
| **Migration complexity** | Would require re-architecting Kurultai |
| **Current setup works** | macOS + native processes working well |

### ✅ DO EXPERIMENT

| Action | Benefit |
|--------|---------|
| **Test locally** | Evaluate without commitment |
| **Monitor development** | Stay informed on progress |
| **Hybrid approach** | Use stereOS for specific isolated tasks |
| **Future migration** | Re-evaluate when mature (6-12 months) |

---

## Key Insight

**stereOS solves a different problem than we have:**

- **stereOS:** Isolates untrusted AI agents from host (security focus)
- **Our need:** Run trusted Kurultai agents efficiently (performance focus)

**Our agents are trusted** (they're part of our system), so VM isolation adds overhead without significant benefit.

**Better use case for stereOS:**
- Running untrusted third-party AI agents
- Multi-tenant AI agent hosting
- Enterprise AI agent deployments with strict security requirements

---

## Recommendation

### 🎯 STAY ON macOS FOR NOW

**Why:**
- ✅ Stable, proven platform
- ✅ Full M-series Mac support
- ✅ Low overhead, low latency
- ✅ All tools working (LM Studio, OpenClaw, Neo4j)
- ✅ Easy to develop and maintain

### 🔬 EXPERIMENT WITH stereOS

**Why:**
- ✅ Learn about the platform
- ✅ Evaluate for specific use cases
- ✅ Prepare for future hybrid approach
- ❌ Don't migrate production Kurultai yet

### 📅 RE-EVALUATE TIMELINE

| Timeframe | Action |
|-----------|--------|
| **Now** | Test stereOS locally, monitor development |
| **3-6 months** | Evaluate stability, community growth |
| **6-12 months** | Consider hybrid approach (specific use cases) |
| **12+ months** | Re-evaluate full migration if mature |

---

## Files to Watch

- **GitHub:** https://github.com/papercomputeco/stereos
- **CLI:** https://github.com/papercomputeco/masterblaster
- **Daemon:** https://github.com/papercomputeco/stereosd
- **Docs:** https://stereos.ai
- **Community:** https://discord.gg/T6Y4XkmmV5

---

## Final Verdict

**stereOS is an interesting project with a compelling vision, but:**

1. **Too early** for production migration
2. **Wrong fit** for our trusted-agent use case
3. **High overhead** vs. our current native process model
4. **Unclear Mac support** for Apple Silicon

**Best approach:** Monitor, experiment locally, consider hybrid approach in 6-12 months when the project matures.

**Don't migrate Kurultai from macOS yet.** The current setup is stable, efficient, and working well.

---

**Last Updated:** 2026-03-02  
**Next Review:** When stereOS reaches v1.0 or has significant adoption (6-12 months)
