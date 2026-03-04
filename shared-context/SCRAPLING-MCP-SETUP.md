# Scrapling MCP Server Setup ✅

**Date:** 2026-03-04  
**Status:** COMPLETE  
**Server:** ScraplingServer

---

## What is Scrapling MCP?

The Scrapling MCP (Model Context Protocol) Server enables Claude Code to use Scrapling's web scraping capabilities directly through natural language commands.

**Key Benefits:**
- 🎯 **Targeted extraction** — Use CSS selectors to extract only what you need (saves tokens)
- 🔒 **Anti-bot bypass** — Cloudflare Turnstile, Interstitial protection built-in
- ⚡ **Parallel scraping** — Bulk fetch multiple URLs concurrently
- 🤖 **AI-assisted** — Claude can iteratively refine selectors until it finds the right data

---

## Installation Status

| Component | Status | Details |
|-----------|--------|---------|
| **Scrapling** | ✅ Installed | v0.4.1 |
| **MCP Dependencies** | ✅ Installed | mcp>=1.26.0 |
| **Browser Dependencies** | ✅ Installed | Playwright + Chromium |
| **Claude Code MCP** | ✅ Connected | ScraplingServer |
| **Executable Path** | ✅ `/opt/homebrew/bin/scrapling` |

---

## Configuration

### Claude Code (Local Project)

**Config File:** `~/.claude.json`

```json
{
  "mcpServers": {
    "ScraplingServer": {
      "command": "/opt/homebrew/bin/scrapling",
      "args": ["mcp"]
    }
  }
}
```

### Claude Desktop (MacOS)

**Config File:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ScraplingServer": {
      "command": "/opt/homebrew/bin/scrapling",
      "args": ["mcp"]
    }
  }
}
```

---

## Available Tools

| Tool | Description | Use Case |
|------|-------------|----------|
| **`get`** | Fast HTTP requests with browser fingerprint | Simple static sites |
| **`bulk_get`** | Async HTTP for multiple URLs | Batch scraping |
| **`fetch`** | Full browser automation (Chromium) | Dynamic/JS sites |
| **`bulk_fetch`** | Async browser for multiple URLs | Parallel dynamic scraping |
| **`stealthy_fetch`** | Stealth browser with anti-bot bypass | Cloudflare, protected sites |
| **`bulk_stealthy_fetch`** | Async stealth for multiple URLs | Parallel protected scraping |

---

## Usage Examples

### 1. Basic Scraping

```
Scrape the main content from https://example.com and convert it to markdown.
```

### 2. Targeted Extraction

```
Get all product titles from https://shop.example.com using CSS selector '.product-title'.
```

### 3. Bulk Scraping

```
Use bulk browser fetches to extract product info from:
- https://shop1.com/product-a
- https://shop2.com/product-b
- https://shop3.com/product-c

Get names, prices, and descriptions.
```

### 4. Cloudflare Bypass

```
What's the price of this product? Be cautious, it uses Cloudflare Turnstile.
https://ao.com/product/oo101uk-ninja-woodfire-outdoor-pizza-oven-brown-99357-685.aspx
```

### 5. Multi-Step Workflow

```
Go to https://www.arnotts.ie/furniture/bedroom/bed-frames/ and extract all product URLs using CSS selector "a". Then fetch the first 3 product pages in parallel and extract price and details.

Keep output in markdown to reduce irrelevant content.
```

---

## Integration with Kurultai

### For Jochi (Intelligence)

```
Use stealthy_fetch to monitor competitor pricing:
- https://www.back4app.com/pricing
- https://supabase.com/pricing

Extract pricing tiers and features using CSS selectors.
```

### For Mongke (Research)

```
Use bulk_get to gather news from:
- https://techcrunch.com/
- https://venturebeat.com/
- https://www.theverge.com/

Extract article titles, URLs, and publication dates.
```

### For Kublai (Strategic)

```
Create a competitive analysis report:
1. Scrape pricing from 5 Parse competitors
2. Compare features and pricing tiers
3. Identify gaps in our positioning
4. Summarize in markdown table format
```

---

## Best Practices

### 1. Choose the Right Tool

| Tool | When to Use |
|------|-------------|
| `get` | Fast, simple static websites |
| `fetch` | Sites with JavaScript/dynamic content |
| `stealthy_fetch` | Protected sites, Cloudflare, anti-bot |

### 2. Optimize Performance

- Use **bulk tools** for multiple URLs
- Use **CSS selectors** for targeted extraction (saves tokens!)
- Set appropriate **timeouts** for slow sites
- Use `main_content_only=true` to skip navigation/ads

### 3. Handle Dynamic Content

- Use `network_idle` for SPAs (Single Page Apps)
- Set `wait_selector` for specific elements
- Increase timeout for slow-loading sites

### 4. Token Efficiency

**Bad (wasteful):**
```
Scrape https://example.com and find the product prices.
```

**Good (efficient):**
```
Use get to scrape https://example.com with CSS selector '.price::text' to extract only prices.
```

---

## Testing

### Verify MCP Connection

```bash
claude mcp list | grep Scrapling
# Expected: ScraplingServer: /opt/homebrew/bin/scrapling mcp - ✓ Connected
```

### Test with Claude Code

```bash
cd /tmp
claude -p "Use the Scrapling MCP server to scrape the main content from https://example.com as markdown."
```

---

## Troubleshooting

### Server Not Connecting

```bash
# Check scrapling installation
which scrapling
scrapling --version

# Restart Claude Code
# The MCP server connects on Claude Code startup
```

### Browser Issues

```bash
# Reinstall browser dependencies
scrapling install
```

### Permission Errors

```bash
# Ensure scrapling is executable
chmod +x /opt/homebrew/bin/scrapling
```

---

## Resources

- **Scrapling Docs:** https://scrapling.readthedocs.io/
- **MCP Server Guide:** https://scrapling.readthedocs.io/en/latest/ai/mcp-server/
- **Demo Video:** https://www.youtube.com/watch?v=qyFk3ZNwOxE
- **GitHub:** https://github.com/D4Vinci/Scrapling
- **Discord:** https://discord.gg/EMgGbDceNQ

---

*Setup complete. Scrapling MCP server ready for AI-assisted web scraping.*
