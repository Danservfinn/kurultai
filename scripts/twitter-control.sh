#!/bin/bash
# Kurultai Twitter Maintenance Control Script
# Usage: ./twitter-control.sh [start|stop|status|restart|logs|once|queue]

PLIST_NAME="ai.kurultai.twitter-maintenance"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
SCRIPT_PATH="$HOME/.openclaw/agents/main/scripts/twitter_maintenance.py"
LOG_PATH="$HOME/.openclaw/logs/twitter-maintenance.log"

usage() {
    echo "Kurultai Twitter Maintenance Control"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  start      - Load and start the LaunchAgent"
    echo "  stop       - Stop and unload the LaunchAgent"
    echo "  restart    - Restart the LaunchAgent"
    echo "  status     - Check if LaunchAgent is loaded"
    echo "  logs       - Tail the log file"
    echo "  once       - Run once manually (tweet mode)"
    echo "  queue      - Show content queue status"
    echo "  engage     - Run community engagement once"
    echo "  init       - Initialize/reinitialize content queue"
    echo ""
}

case "${1:-}" in
    start)
        echo "Starting Kurultai Twitter maintenance..."
        if [ -f "$PLIST_PATH" ]; then
            launchctl load "$PLIST_PATH" 2>/dev/null
            echo "✅ LaunchAgent loaded"
        else
            echo "❌ LaunchAgent plist not found at $PLIST_PATH"
            exit 1
        fi
        ;;

    stop)
        echo "Stopping Kurultai Twitter maintenance..."
        launchctl unload "$PLIST_PATH" 2>/dev/null
        echo "✅ LaunchAgent unloaded"
        ;;

    restart)
        echo "Restarting Kurultai Twitter maintenance..."
        launchctl unload "$PLIST_PATH" 2>/dev/null
        sleep 1
        launchctl load "$PLIST_PATH" 2>/dev/null
        echo "✅ LaunchAgent restarted"
        ;;

    status)
        echo "Kurultai Twitter Maintenance Status"
        echo "==================================="

        # Check if loaded
        if launchctl list | grep -q "$PLIST_NAME"; then
            echo "✅ LaunchAgent: LOADED"
        else
            echo "❌ LaunchAgent: NOT LOADED"
        fi

        # Show queue status
        echo ""
        python3 "$SCRIPT_PATH" status
        ;;

    logs)
        echo "Tailing logs (Ctrl+C to exit)..."
        tail -f "$LOG_PATH"
        ;;

    once)
        echo "Running single tweet post..."
        python3 "$SCRIPT_PATH" tweet
        ;;

    engage)
        echo "Running community engagement..."
        python3 "$SCRIPT_PATH" engage
        ;;

    queue)
        python3 "$SCRIPT_PATH" status
        ;;

    init)
        echo "Initializing content queue..."
        python3 "$SCRIPT_PATH" init
        ;;

    *)
        usage
        ;;
esac
