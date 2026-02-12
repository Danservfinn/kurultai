# X-Research Setup - Final Steps

## ✅ What's Already Done

1. **Composio API Key** - Added to `.env` files
2. **Composio CLI** - Installed and working (v0.7.21)
3. **x-research skill** - Configured with API key
4. **Watchlist** - Created from example

## ⏳ What You Need To Do (Requires Browser)

The Twitter OAuth connection requires browser-based authentication. Here's how:

### Option 1: Run the setup locally

```bash
# SSH into the machine or run locally
export COMPOSIO_API_KEY=ak_H2v4OXQDpl0ZyvXkgU_a
composio add twitter
```

This will open a browser window for Twitter OAuth.

### Option 2: Use Composio web dashboard

1. Go to https://app.composio.dev
2. Sign in with your Composio account
3. Navigate to "Integrations" or "Connections"
4. Click "Add Connection" → Select "Twitter"
5. Authorize the connection

### Option 3: Use Composio's hosted auth

```bash
export COMPOSIO_API_KEY=ak_H2v4OXQDpl0ZyvXkgU_a

# Get auth URL
composio add twitter --no-browser

# This will output a URL like:
# https://platform.composio.dev/auth/twitter?connection_id=...

# Open that URL in your browser and authorize
# The connection will be established automatically
```

## 🧪 Verify Setup

After connecting Twitter, verify everything works:

```bash
export COMPOSIO_API_KEY=ak_H2v4OXQDpl0ZyvXkgU_a
python3 tools/verify_composio.py
```

Or check connections directly:
```bash
composio connections
```

You should see a Twitter/X connection listed.

## 🚀 Test X-Research

Once connected, test the skill:

```bash
cd /data/workspace/kurultai-skills/x-research
export COMPOSIO_API_KEY=ak_H2v4OXQDpl0ZyvXkgU_a
bun run index.ts search "AI agents" --limit 5
```

Or ask Möngke to research: "Search Twitter for latest AI agent developments"

## 📁 Files Created

- `.env` - Contains COMPOSIO_API_KEY
- `/data/workspace/kurultai-skills/x-research/.env` - X-research skill config
- `/data/workspace/kurultai-skills/x-research/data/watchlist.json` - Watchlist
- `tools/verify_composio.py` - Verification script
- `X_RESEARCH_SETUP_INSTRUCTIONS.md` - This file

---

**Status:** Infrastructure ready, waiting for OAuth authorization
