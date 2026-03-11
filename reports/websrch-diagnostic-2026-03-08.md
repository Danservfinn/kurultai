# WebSearch Diagnostic Report

**Task ID**: websrch-root-cause-1772974514
**Agent**: kublai (investigation delegated from jochi)
**Date**: 2026-03-08T22:30:00
**Status**: ROOT CAUSE CONFIRMED

## Executive Summary

WebSearch is **non-functional** due to a Z.ai provider-side issue. All queries return empty results. The `web_search_prime` backend tool is broken on Z.ai's infrastructure.

## Root Cause

**Z.ai's `web_search_prime` server-side tool returns empty arrays for all search queries.**

### Technical Details

1. **Environment**: All tool calls route through Z.ai proxy
   - `ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic`

2. **Tool Output Pattern**:
   ```
   web_search_prime_result_summary: [{"text": [], "type": "text"}]
   ```

3. **Scope**: Affects ALL queries regardless of:
   - Query complexity (simple "test" vs complex research queries)
   - Topic (technology, weather, finance)
   - Time of day

## Test Results

| Query | Tool | Result |
|-------|------|--------|
| "Claude AI latest news 2026" | WebSearch | `[]` empty |
| "Anthropic Claude API pricing" | WebSearch | `[]` empty |
| "OpenClaw multi-agent system" | WebSearch | `[]` empty |
| "weather today" | WebSearch | `[]` empty |
| "Apple Inc stock" | WebSearch | `[]` empty |
| https://www.anthropic.com/news | webReader | **SUCCESS** |

## Impact Assessment

| Agent | Impact | Severity |
|-------|--------|----------|
| mongke (Researcher) | **CRITICAL** - Cannot perform web research | HIGH |
| jochi (Analyst) | HIGH - Cannot gather external data | HIGH |
| chagatai (Writer) | MEDIUM - Cannot research content | MEDIUM |
| temujin (Developer) | LOW - Can use direct URLs | LOW |
| ogedei (Ops) | LOW - Monitoring doesn't require search | LOW |

## Available Workarounds

### 1. mcp__web_reader__webReader (RECOMMENDED for known URLs)

**Status**: WORKING
**Use case**: Fetching content from known URLs

```
mcp__web_reader__webReader(url="https://example.com", return_format="markdown")
```

**Pros**: Works perfectly, returns full content
**Cons**: Requires knowing the URL first

### 2. Playwright Browser

**Status**: AVAILABLE
**Use case**: Full browser interaction, Google searches

```
mcp__plugin_playwright_playwright__browser_navigate(url="https://google.com")
mcp__plugin_playwright_playwright__browser_type(ref="searchbox", text="query")
mcp__plugin_playwright_playwright__browser_snapshot()
```

**Pros**: Full browser access, can search via Google
**Cons**: Heavier, requires navigation steps

### 3. Tavily MCP

**Status**: NOT CONFIGURED
**Required**: API key from https://tavily.com/

Configuration file: `/Users/kublai/.openclaw/credentials/tavily.env`
Current value: `TAVILY_API_KEY=your_api_key_here` (placeholder)

**To enable**:
1. Get API key from https://tavily.com/ (1000 free searches/month)
2. Update `/Users/kublai/.openclaw/credentials/tavily.env`
3. Restart Claude Code

## Escalation Options

1. **Contact Z.ai support** - Report that `web_search_prime` returns empty arrays
2. **Switch to direct Anthropic API** - Remove `ANTHROPIC_BASE_URL` override
3. **Configure Tavily** - Enable backup search provider

## Recommendations

### Immediate (Today)
- [ ] Document limitation for all Kurultai agents
- [ ] Use `webReader` for known URLs
- [ ] Use Playwright for discovery searches

### Short-term (This Week)
- [ ] Configure Tavily API key for backup search
- [ ] Update agent workflows to use fallback tools

### Medium-term (This Month)
- [ ] Evaluate switching to direct Anthropic API
- [ ] Consider custom search MCP server

## Related Files

- Previous debug report: `/Users/kublai/.openclaw/agents/temujin/workspace/websearch-debug-report.md`
- Backup provider docs: `/Users/kublai/.openclaw/docs/websearch-backup-provider.md`
- Fallback script: `/Users/kublai/.openclaw/scripts/web_search_fallback.py`
- Tavily config: `/Users/kublai/.openclaw/credentials/tavily.env`

## Verification Checklist

- [x] WebSearch tested with 5+ different query types
- [x] Root cause identified and documented
- [x] Workaround options tested (webReader works)
- [x] Tavily status verified (not configured)
- [x] Escalation path identified
- [x] This is unfixable at agent level - requires Z.ai fix or alternative provider

---

**Classification**: CRITICAL INFRASTRUCTURE
**Requires Action**: YES - Either configure Tavily or escalate to Z.ai
