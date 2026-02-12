#!/usr/bin/env python3
"""
Heartbeat Monitor Daemon - Runs heartbeat_monitor.py every hour
Alternative to cron for environments without crontab
"""

import os
import sys
import time
import signal
from datetime import datetime

# Configuration
WORKSPACE = os.environ.get('WORKSPACE', '/data/workspace/souls/main')
MONITOR_SCRIPT = os.path.join(WORKSPACE, 'tools/kurultai/heartbeat_monitor.py')
PID_FILE = '/tmp/heartbeat_monitor_daemon.pid'
RUN_INTERVAL_HOURS = 1

def log(message):
    """Log with timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

def run_monitor():
    """Run the heartbeat monitor script"""
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, MONITOR_SCRIPT],
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.returncode == 0
    except Exception as e:
        log(f"Error running monitor: {e}")
        return False

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    log("Received shutdown signal, stopping monitor daemon...")
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    sys.exit(0)

def main():
    """Main daemon loop"""
    # Write PID file
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    log("=" * 60)
    log("Heartbeat Monitor Daemon started")
    log(f"Will check heartbeat every {RUN_INTERVAL_HOURS} hour(s)")
    log("=" * 60)
    
    # Run immediately on start
    log("Running initial check...")
    run_monitor()
    
    # Schedule next runs
    last_run = time.time()
    interval_seconds = RUN_INTERVAL_HOURS * 3600
    
    try:
        while True:
            time.sleep(60)  # Check every minute
            
            elapsed = time.time() - last_run
            if elapsed >= interval_seconds:
                log(f"Running scheduled check (every {RUN_INTERVAL_HOURS} hour(s))...")
                run_monitor()
                last_run = time.time()
                
    except KeyboardInterrupt:
        log("Shutdown requested")
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        log("Monitor daemon stopped")

if __name__ == '__main__':
    main()
