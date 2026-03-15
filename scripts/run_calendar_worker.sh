#!/bin/bash
# Source Neo4j credentials from restricted env file
set -a
source ~/.openclaw/credentials/neo4j.env
set +a

export SIGNAL_API_URL="http://127.0.0.1:8080"
export SIGNAL_ACCOUNT="+15165643945"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONIOENCODING="UTF-8"

# Log rotation: truncate if > 10MB
for logfile in ~/.openclaw/logs/calendar-reminders.log ~/.openclaw/logs/calendar-reminders-error.log; do
    if [ -f "$logfile" ]; then
        size=$(stat -f%z "$logfile" 2>/dev/null || echo 0)
        if [ "$size" -gt 10485760 ]; then
            mv "$logfile" "${logfile}.1"
            : > "$logfile"
        fi
    fi
done

cd ~/.openclaw/agents/main/scripts
exec .venv/bin/python3 calendar_reminder_worker.py
