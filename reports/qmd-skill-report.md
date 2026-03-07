# QMD-Skill: Comprehensive Research Report

**Author:** Mongke (Researcher, Kurultai)
**Date:** 2026-03-06
**Status:** Complete
**Sources:** 6 (GitHub repos, FastMCP registry, community reports, X posts)

---

## 1. What is QMD-Skill and What Does It Do

### QMD (Quick Markdown Search)

[QMD](https://github.com/tobi/qmd) is a **local, on-device hybrid search engine for Markdown files** created by Tobi Lutke (CEO of Shopify). It combines three search technologies into a single tool:

- **BM25 keyword search** via SQLite FTS5 — instant results
- **Vector semantic search** via local embeddings (Gemma 300M) — finds conceptually related content
- **LLM re-ranking** via Qwen3-Reranker 0.6B — optimizes result quality

Everything runs locally with no API calls and no token costs. Three GGUF models totaling ~2.1GB handle all AI operations on-device.

### QMD-Skill

[QMD-Skill](https://github.com/montyanderson/qmd-skill) is a **Claude Code skill wrapper** that packages QMD for use in Claude Code, Codex, GitHub Copilot, and Google Antigravity environments. It follows a "skill-as-wrapper" pattern — a minimal SKILL.md file that teaches the LLM *when* and *how* to use QMD, without reimplementing any functionality.

There is also a related project, **qmd-sessions** ([William Belk](https://www.williambelk.com/blog/qmd-sessions-claude-code-memory-with-qmd-20260303/)), which converts Claude Code session transcripts (JSONL) into clean, searchable markdown and indexes them with QMD — effectively giving Claude Code persistent, searchable memory across sessions.

**Current version:** 2.0.0 | **License:** MIT | **Install:** `npm install -g @tobilu/qmd`

---

## 2. Key Patterns, Architecture, and Capabilities

### 2.1 Three-Tier Search Architecture

| Mode | Engine | Speed | Quality | Use Case |
|------|--------|-------|---------|----------|
| `search` (BM25) | SQLite FTS5 | Instant | Keyword-match only | Known terms, exact phrases |
| `vsearch` (Vector) | Gemma 300M embeddings | ~30-60s | Semantic similarity | Conceptual queries |
| `query` (Hybrid) | BM25 + Vector + LLM rerank | Slowest | Best quality | Complex research questions |

### 2.2 Hybrid Query Pipeline (Deep Search)

The `query` mode implements a sophisticated 5-stage pipeline:

1. **Query expansion** — Fine-tuned 1.7B model generates 3 query variations
2. **Parallel retrieval** — Each variation searches both FTS and vector indexes
3. **RRF fusion** — Reciprocal Rank Fusion combines results (k=60, original query weighted 2x)
4. **LLM re-ranking** — Qwen3-Reranker 0.6B scores top 30 candidates
5. **Position-aware blending** — Varies reranker trust by rank position

### 2.3 Smart Chunking Algorithm

QMD's document chunking preserves semantic boundaries:

- **900-token chunks** with 15% overlap
- Break-point scoring: H1=100, H2=90, code blocks=80, horizontal rules=60, blank lines=20
- Window search: at 900-token target, scan 200-token window before cutoff
- Score formula: `finalScore = baseScore x (1 - (distance/window)^2 x 0.7)`
- **Code block protection:** blocks stay together even if they exceed chunk size

This is significantly better than naive fixed-size chunking for markdown content.

### 2.4 MCP Server Integration

QMD exposes 6 tools via its MCP server (`qmd mcp`):

| Tool | Function |
|------|----------|
| `qmd_search` | Fast BM25 keyword search (supports collection filter) |
| `qmd_vector_search` | Semantic vector search (supports collection filter) |
| `qmd_deep_search` | Hybrid search with query expansion + reranking |
| `qmd_get` | Retrieve document by path or docid (fuzzy matching) |
| `qmd_multi_get` | Retrieve multiple docs by glob pattern |
| `qmd_status` | Index health and collection info |

Configuration for Claude Code:
```json
{
  "mcpServers": {
    "qmd": {
      "command": "qmd",
      "args": ["mcp"]
    }
  }
}
```

Also supports **HTTP transport** (`qmd mcp --http`) with daemon mode at `localhost:8181`.

### 2.5 Collection + Context Model

QMD organizes knowledge into named collections with metadata:

- **Collections** — Named directory mappings (e.g., `~/notes` -> "notes")
- **Contexts** — Descriptive metadata per collection/path
- **Virtual paths** — `qmd://collection/path` addressing scheme

### 2.6 Skill-as-Wrapper Pattern

The qmd-skill repo is just 2 files:
- `SKILL.md` — Full skill definition with frontmatter, trigger conditions, usage docs
- `references/cli_reference.md` — Complete CLI documentation

The SKILL.md encodes:
- Trigger conditions (when to activate)
- Default behavior preferences (BM25 first, semantic on fallback)
- Prerequisites and installation
- Performance guidance per search mode

**Key insight:** The skill doesn't reimplement the tool — it wraps it with LLM-friendly context.

---

## 3. How QMD Could Be Useful for the Kurultai

### 3.1 Cross-Agent Knowledge Search (HIGH VALUE)

Currently, Kurultai agents use `Grep` and `Glob` for file search. These are purely syntactic — they can't answer "what research have we done about pricing?" or "find previous work related to authentication architecture."

QMD would add:
- **Semantic search** across all 6 agents' workspaces, memory files, and shared context
- **Zero token cost** — all search runs locally, no LLM API calls consumed
- **Collection-based isolation** — each agent's workspace as a named collection

Natural collection mapping:
```
qmd://agents              -> "All Kurultai agent workspaces"
qmd://shared-context      -> "Cross-agent coordination docs"
qmd://mongke-research     -> "Research deliverables and findings"
qmd://parse-docs          -> "Parse platform documentation"
qmd://jochi-data          -> "Competitor intelligence data"
```

### 3.2 Persistent Agent Memory (HIGH VALUE)

With qmd-sessions pattern, each agent's conversation transcripts could be indexed and searchable. This means:
- Agents can search their own history for prior decisions and reasoning
- Cross-agent history search ("what did Temujin decide about the auth refactor?")
- Eliminates redundant research — find what was already investigated

### 3.3 Research Deliverable Retrieval (MEDIUM VALUE)

Mongke has produced 15+ research deliverables in `workspace/`. Currently, finding relevant prior research requires knowing exact filenames. With QMD:
- Search by concept: "competitive pricing analysis" finds the right report
- Cross-reference: "x402 protocol" finds mentions across all reports
- Context windows stay clean — retrieve only relevant sections, not full files

### 3.4 Token Economics (HIGH VALUE)

From our agent-first interfaces research:
- Structured API call: ~500 tokens/operation
- Browser automation: ~50,000 tokens/operation
- **Local QMD search: ~0 tokens/operation**

For a system running 6 agents with cron jobs, the token savings compound rapidly.

### 3.5 Community Validation

Community reports confirm significant real-world impact:
- [Kevin Lee](https://x.com/kevinleeme/status/2018421153795367135): "Reduced token usage and processing time across the board by more than 60%" using QMD semantic chunking
- [Derek](https://x.com/cyberdrk/status/2016552044614840790): "Massive speedup — skill search from 5+ seconds down to ~0.4s"
- [Kavir](https://x.com/kavirkaycee/status/2017118236387791143): Significant token difference for vault search vs alternatives

---

## 4. Specific Skills and Patterns to Adopt

### 4.1 Skill-as-Wrapper Pattern
**Adopt for:** Any external tool we want to make agent-accessible. Instead of building complex integrations, write a thin SKILL.md that teaches the LLM when/how to use the tool. Our existing skills could be simplified using this pattern.

### 4.2 Progressive Search Escalation
**Adopt for:** All agent search behavior. Pattern: BM25 first (instant) -> Vector only if BM25 fails -> Hybrid only for complex conceptual queries. This prevents slow searches when fast ones suffice.

### 4.3 MCP-First Tool Integration
**Adopt for:** Future tool additions. QMD confirms MCP is the right integration layer. One config line adds 6 tools. With our existing MCP lazy loading (verified active), these tools cost ~0 context until invoked.

### 4.4 Collection-Based Knowledge Organization
**Adopt for:** Kurultai workspace structure. Named collections with context metadata map perfectly to our multi-agent workspace hierarchy.

### 4.5 Smart Chunking for RAG
**Adopt for:** Any future RAG pipeline. QMD's break-point scoring system (heading-aware, code-block-protecting) is superior to naive fixed-size chunking.

---

## 5. Recommendations for Integration

### Phase 1: Install and Index (Effort: Low, Impact: High)

1. Install QMD globally: `npm install -g @tobilu/qmd`
2. Create collections for agent workspaces:
   ```bash
   qmd collection add ~/.openclaw/agents/ --name agents
   qmd collection add ~/.openclaw/agents/shared-context --name shared-context
   qmd collection add ~/.openclaw/agents/mongke/workspace --name mongke-research
   qmd collection add ~/.openclaw/agents/jochi/data --name jochi-intel
   ```
3. Add context descriptions for each collection
4. Run initial embedding: `qmd embed`
5. Add cron job: `qmd update && qmd embed` every 30 minutes

### Phase 2: MCP Integration (Effort: Medium, Impact: High)

1. Add QMD as MCP server in Claude Code config (see config above)
2. Or run as HTTP daemon: `qmd mcp --http --daemon`
3. Test with each agent type — verify search quality for:
   - Research queries (Mongke)
   - Code lookups (Temujin)
   - Documentation search (Chagatai)
   - Competitive intel (Jochi)
4. With lazy loading active, adds 6 deferred tools at ~0 context cost

### Phase 3: Kurultai-Specific Skill (Effort: Low, Impact: Medium)

1. Create `~/.openclaw/skills/qmd-kurultai/SKILL.md`
2. Define Kurultai-specific trigger conditions and behavior preferences
3. Include collection names, contexts, and search escalation guidance
4. Deploy to all 6 agents

### Phase 4: Session Memory (Effort: Medium, Impact: High)

1. Evaluate qmd-sessions for indexing agent conversation transcripts
2. Set up automatic transcript -> markdown conversion pipeline
3. Enable cross-session, cross-agent memory search

### Phase 5: Parse Codebase Indexing (Effort: Medium, Impact: Medium)

1. Index Parse documentation and API specs
2. Useful for Chagatai (docs) and Temujin (code reference)
3. Enables conceptual code search ("how does the payment flow work?")

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| 2.1GB model download size | Low | One-time cost; Mac Mini has storage |
| Embedding compute on initial index | Low | Run overnight; incremental updates after |
| QMD not maintained | Very Low | Author is Tobi Lutke (Shopify CEO); active development |
| Search quality worse than Grep for keywords | Medium | Keep Grep for exact-match; QMD for semantic |
| MCP server stability | Low | HTTP daemon mode provides fallback |

---

## Conclusion

QMD is a high-quality, well-architected local search engine that directly addresses Kurultai's knowledge retrieval gaps. The combination of instant BM25 search, optional semantic search, and native MCP integration makes it a natural fit for our multi-agent system. Installation effort is minimal, token savings are significant, and the tool is backed by a high-credibility author.

**Top recommendation:** Install QMD, index agent workspaces, and add as MCP server. This gives all 6 agents instant search over accumulated knowledge at zero token cost.

---

## Sources

- [QMD GitHub (tobi/qmd)](https://github.com/tobi/qmd) — Core search engine
- [QMD-Skill GitHub (montyanderson/qmd-skill)](https://github.com/montyanderson/qmd-skill) — Claude Code skill wrapper
- [QMD-Skill GitHub (levineam/qmd-skill)](https://github.com/levineam/qmd-skill) — Alternative skill wrapper (543 stars)
- [QMD on FastMCP Skills Registry](https://fastmcp.me/skills/details/1046/qmd) — v2.0.0 listing
- [QMD-Sessions Blog (William Belk)](https://www.williambelk.com/blog/qmd-sessions-claude-code-memory-with-qmd-20260303/) — Session transcript indexing
- [Claude Code Skills Documentation](https://code.claude.com/docs/en/skills) — Official skill architecture
- [Kevin Lee on X](https://x.com/kevinleeme/status/2018421153795367135) — 60% token reduction report
- [Derek on X](https://x.com/cyberdrk/status/2016552044614840790) — Search speedup from 5s to 0.4s
- [Kavir on X](https://x.com/kavirkaycee/status/2017118236387791143) — Token difference validation
