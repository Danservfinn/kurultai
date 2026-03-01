# TOOLS.md - Local Notes

Skills define *how* tools work. This file is for *your* specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:
- Camera names and locations
- SSH hosts and aliases  
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras
- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH
- home-server → 192.168.1.100, user: admin

### TTS
- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

### MarkItDown
Python tool for converting files to Markdown (PDF, Word, Excel, PPT, Images, Audio, HTML, etc.)
- Install: `pip3 install markitdown`
- Usage: `python3 -m markitdown input.pdf > output.md`
- Supports: PDF, PowerPoint, Word, Excel, Images (OCR), Audio (transcription), HTML, ZIP, YouTube URLs, EPubs
- Also has MCP server for Claude Desktop integration
- Docs: https://github.com/microsoft/markitdown

---

### OpenClaw Official Documentation
**ALWAYS check before system modifications**
- **Index:** https://docs.openclaw.ai/llms.txt (list of all docs)
- **Cron:** https://docs.openclaw.ai/automation/cron-jobs.md
- **Hooks:** https://docs.openclaw.ai/automation/hooks.md
- **Heartbeat:** https://docs.openclaw.ai/gateway/heartbeat
- **Channels:** https://docs.openclaw.ai/channels/index.md

**Quick fetch:** `web_fetch https://docs.openclaw.ai/automation/cron-jobs.md`

**When to check:**
- Before modifying cron jobs
- Before changing channel configurations
- Before system automation changes
- When troubleshooting OpenClaw issues
- When upgrading or migrating

---

### Pinchtab (Future Consideration)
Headless browser fleet orchestrator for managing multiple Chrome/Chromium instances
- **Use case:** Large-scale parallel scraping, testing, automation
- **Why deferred:** OpenClaw has built-in browser tool; we don't need fleet operations currently
- **When to reconsider:** If Möngke needs parallel research across hundreds of sources, or for load testing
- **Repo:** https://github.com/pinchtab/pinchtab
- **Install:** `npm install pinchtab`

---

Add whatever helps you do your job. This is your cheat sheet.
