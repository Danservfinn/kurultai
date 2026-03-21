# Lightpanda - Headless Browser for AI Agents

**Date Learned:** 2026-03-20
**Source:** Danny (+19194133445)
**GitHub:** https://github.com/lightpanda-io/browser

## Overview

A completely new headless browser written from scratch in Zig, designed specifically for AI agents and web automation. Not a Chromium fork, not a WebKit patch - built from zero.

## Problem It Solves

Every AI agent doing web automation currently runs Chrome under the hood:
- Full desktop browser with CSS rendering, GPU compositing, image decoding, font rasterization
- Running on servers for agents that never see pixels
- Paying for 100% of Chrome, using 20%

## What Lightpanda Keeps

- **Full JavaScript execution via V8:** Ajax, Fetch, SPAs, infinite scroll, dynamic content
- **HTML parsing via html5ever:** Mozilla's battle-tested parser
- **Custom DOM engine:** Built in Zig
- **Built-in MCP server:** Direct AI agent integration

## What Lightpanda Removes

- No CSS layout
- No image decoder
- No GPU compositor
- No font rasterizer

## Benchmarks

| Metric | Chrome | Lightpanda |
|--------|--------|------------|
| 100-page scrape | 25.2 seconds | 2.3 seconds |
| Peak memory | 207MB | 24MB |
| Concurrent sessions (same RAM) | 9 | 140 |
| 100 tabs processing | >1 hour | <5 seconds |

## Status

- Still in Beta
- Web API coverage is growing
- 100% Open Source (AGPL-3.0)

## Background

Founder built this after running 20 million Chrome crawls per day at previous company and watching infrastructure costs pile up.

## Potential Use Cases for Kurultai

1. **Mongke research tasks** - faster web scraping for market research
2. **Tolui verification** - efficient fact-checking across multiple sources
3. **Agent web automation** - reduced memory footprint for browser-based tasks
4. **Infrastructure cost reduction** - significant savings at scale

## Action Items

- [ ] Monitor project maturity and Web API coverage
- [ ] Evaluate for Kurultai integration once stable
- [ ] Consider for research agent (mongke) optimization
