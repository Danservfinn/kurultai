---
name: curiosity-scheduler-fix
description: Fixed 0% Curiosity Engine answer rate by adding missing launchd scheduling
type: feedback
---

# Rule: Curiosity Engine Must Be Scheduled

**Why:** The Curiosity Scheduler script (`curiosity_scheduler.py`) existed and was configured in `curiosity.json` to run every 4 hours, but there was NO launchd plist to actually execute it. This resulted in 19 expired questions at 0% answer rate — questions were being generated but never sent.

**How to apply:** When adding new scheduled scripts to the Kurultai system:
1. Create the Python script in `/Users/kublai/.openclaw/agents/main/scripts/`
2. Create a launchd plist in `~/Library/LaunchAgents/ai.kurultai.*.plist`
3. Load it with `launchctl load ~/Library/LaunchAgents/ai.kurultai.*.plist`
4. Verify with `launchctl list | grep <name>`
5. Test with `--dry-run` flag if available

**Fix implemented 2026-03-23:**
- Created `/Users/kublai/Library/LaunchAgents/ai.kurultai.curiosity-scheduler.plist`
- Scheduled to run at 9am, 1pm, 5pm, 9pm ET (every 4 hours during waking hours)
- Logs to `/Users/kublai/.openclaw/logs/curiosity-scheduler.{log,err}`
- Loaded successfully and verified with dry-run test

**Related files:**
- `/Users/kublai/.openclaw/agents/main/scripts/curiosity_scheduler.py`
- `/Users/kublai/.openclaw/config/curiosity.json`
- `/Users/kublai/Library/LaunchAgents/ai.kurultai.curiosity-scheduler.plist`
