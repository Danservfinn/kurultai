# Technology Watchlist

**Purpose:** Track emerging technologies and research projects relevant to Kurultai operations.

**Review Cadence:** Every 12 hours (via OpenClaw Discovery cron)

---

## Active Watchlist

### 1. ANE - Apple Neural Engine Training 🔬

| Attribute | Value |
|-----------|-------|
| **Repository** | https://github.com/maderix/ANE |
| **Category** | Research / Experimental |
| **Priority** | LOW |
| **Added** | 2026-03-04 |
| **Status** | Monitoring |
| **Last Verified** | 2026-03-10 |

**What It Is:**
Training neural networks directly on Apple's Neural Engine (ANE) using reverse-engineered private APIs (`_ANEClient`, `_ANECompiler`).

**Key Metrics:**
| Metric | Value |
|--------|-------|
| Peak Performance | 15.8 TFLOPS (M4) |
| Actual Training | ~1-2 TFLOPS (5-9% utilization) |
| Model Size Limit | ~200M params |
| Training Speed | 91-110 ms/step (Stories110M) |
| License | MIT |

**Recent Updates (March 2026):**
- ✅ **INT8 W8A8 Support**: New quantization with **1.88x throughput improvement** (Mar 10)
- ✅ **Multi-Model Dashboard**: Added with GQA (Grouped Query Attention) support (Mar 7)
- ✅ **Qwen3-0.6B Support**: New model support added (Mar 6)
- ✅ **Active Development**: Latest commit Mar 10, 2026

**Current Limitations:**
- Research project, NOT production-ready
- Many operations fall back to CPU
- Low utilization (~5-9%)
- ~119 compile limit per process
- Private APIs (could break with macOS updates)

**Potential Use Cases:**
- [ ] Fine-tuning tiny models (<100M params) for specific tasks
- [ ] Power-efficient edge training experiments
- [ ] Research into NPU optimization
- [ ] Learning ANE architecture for future projects

**Integration Decision:**
**DEFERRED** — Not production-ready. Monitor for:
- Utilization improvements (>50%)
- Larger model support (>500M params)
- Stable API or official Apple support
- Active maintenance/community

**Alert Triggers:**
- [ ] Major performance breakthrough (>50% utilization)
- [ ] Official Apple endorsement/API release
- [ ] Production-ready framework fork emerges
- [ ] Model size limit increases significantly

---

### 2. Scrapling ✅ (INTEGRATED)

| Attribute | Value |
|-----------|-------|
| **Repository** | https://github.com/D4Vinci/Scrapling |
| **Category** | Web Scraping |
| **Priority** | HIGH |
| **Added** | 2026-03-04 |
| **Status** | **INTEGRATED** |
| **Current Version** | v0.4.2 (Mar 8, 2026) |

**What It Is:**
Adaptive web scraping framework with anti-bot bypass and MCP server support.

**Integration Status:**
- ✅ Phase 1: Installation + skill library
- ✅ Phase 2: Agent tasks + cron jobs
- ✅ Phase 3: MCP server for Claude Code

**v0.4.2 Updates (March 8, 2026):**
- ✅ **Spider Framework Integration**: New scraping capabilities
- ✅ **Proxy Rotation**: Built-in proxy rotation support
- ✅ **Cloudflare Solver**: 2x faster bypass
- ✅ **MCP Schema Improvements**: Enhanced Model Context Protocol integration
- ✅ **Documentation Updates**: March 10 docs refresh

**Cron Jobs:**
- Competitor Monitoring (every 6 hours)
- OpenClaw Discovery (every 12 hours)

---

## Watchlist Criteria

**Add to watchlist when:**
- Novel technology with Kurultai relevance
- Research breakthrough in AI/ML/automation
- Potential competitive advantage
- Early-stage but promising

**Remove from watchlist when:**
- Integrated into production (→ move to "Integrated")
- Project abandoned (>6 months no activity)
- Proven not useful for our use cases
- Superseded by better alternative

---

## Review Process

1. **Discovery cron** runs every 12 hours
2. **Mongke** reviews new findings
3. **Kublai** decides: watchlist, integrate, or ignore
4. **Weekly summary** of watchlist changes

---

*Last updated: 2026-03-10* — ⚠️ **Needs re-verification** (13 days since last check as of 2026-03-23). ANE entry last verified 2026-03-10. Discovery cron status unknown — verify cron jobs are still running.
