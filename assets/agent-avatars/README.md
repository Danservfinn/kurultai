# Agent Avatars Directory

This directory stores Mongolian khan avatars for the 7 Kurultai agents.

## Expected Files

Each agent should have an avatar file named: `{agent}.png`

- `temujin.png` - Genghis Khan (Developer)
- `mongke.png` - Möngke Khan (Researcher)
- `chagatai.png` - Chagatai Khan (Analyst)
- `jochi.png` - Jochi Khan (Coordinator)
- `ogedei.png` - Ögedei Khan (Operations)
- `tolui.png` - Tolui Khan (Writer)
- `kublai.png` - Kublai Khan (Router)

## Specifications

- **Format:** PNG with transparency
- **Size:** 512x512px (scales to 32px, 48px, 64px, 128px in UI)
- **Style:** Photorealistic Mongolian khan regalia
- **Background:** Transparent

## Fallback System

The frontend UI includes a fallback system:
1. If avatar file exists → display image
2. Else → show colored icon (SVG)
3. Else → show initials with agent color

## Integration

The frontend (`~/.openclaw/apps/the-kurultai/`) serves avatars via:
- API endpoint: `/api/avatars/{agent}.png`
- Helper function: `agentAvatar(agent, size)`
- Inline fallback: `<img src onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`

## Generation

Avatars are generated via nano-banana-pro (Google Gemini 3 Pro Image).
See task: `Create photorealistic Mongolian khan avatars`
