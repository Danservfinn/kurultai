#!/bin/bash
# Task Scheduler Service
# Runs Kurultai background task scheduler continuously

PIDFILE=/tmp/task-scheduler.pid
LOGFILE=/tmp/task-scheduler.log

case "$1" in
    start)
        if [ -f "$PIDFILE" ] && kill -0 $(cat "$PIDFILE") 2>/dev/null; then
            echo "Task scheduler already running (PID: $(cat $PIDFILE))"
            exit 0
        fi
        
        echo "Starting task scheduler..."
        cd /data/workspace/souls/main
        nohup python3 tools/task_scheduler.py --interval 60 >> "$LOGFILE" 2>&1 &
        echo $! > "$PIDFILE"
        echo "✅ Task scheduler started (PID: $!)"
        ;;
    
    stop)
        if [ -f "$PIDFILE" ]; then
            pid=$(cat "$PIDFILE")
            echo "Stopping task scheduler (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
            sleep 2
            kill -9 "$pid" 2>/dev/null || true
            rm -f "$PIDFILE"
            echo "✅ Task scheduler stopped"
        else
            echo "Task scheduler not running"
        fi
        ;;
    
    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
    
    status)
        if [ -f "$PIDFILE" ] && kill -0 $(cat "$PIDFILE") 2>/dev/null; then
            echo "✅ Task scheduler running (PID: $(cat $PIDFILE))"
            cd /data/workspace/souls/main
            python3 tools/task_scheduler.py --status 2>&1 | head -20
        else
            echo "❌ Task scheduler not running"
        fi
        ;;
    
    logs)
        tail -50 "$LOGFILE" 2>/dev/null || echo "No logs yet"
        ;;
    
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
