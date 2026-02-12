#!/usr/bin/env python3
"""
Heartbeat Monitor - Ensures heartbeat_master.py is always running
Runs via cron every hour to check and restart if needed
"""

import os
import sys
import subprocess
import signal
import time
from datetime import datetime

# Configuration
WORKSPACE = os.environ.get('WORKSPACE', '/data/workspace/souls/main')
HEARTBEAT_SCRIPT = os.path.join(WORKSPACE, 'tools/kurultai/heartbeat_master.py')
LOG_FILE = '/tmp/heartbeat_monitor.log'
PID_FILE = '/tmp/heartbeat.pid'

def log(message):
    """Log with timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    with open(LOG_FILE, 'a') as f:
        f.write(log_line + '\n')

def is_heartbeat_running():
    """Check if heartbeat process is running"""
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            
            # Check if process exists
            os.kill(pid, 0)  # Signal 0 just checks if process exists
            return True
    except (FileNotFoundError, ValueError, OSError, ProcessLookupError):
        pass
    
    # Fallback: check if process is running by name
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'heartbeat_master.py'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.stdout.strip():
            return True
    except Exception:
        pass
    
    return False

def restart_heartbeat():
    """Restart the heartbeat daemon"""
    log("Restarting heartbeat daemon...")
    
    # Kill any existing heartbeat processes
    try:
        subprocess.run(
            ['pkill', '-f', 'heartbeat_master.py'],
            capture_output=True,
            timeout=5
        )
        time.sleep(1)
    except Exception as e:
        log(f"Warning: Could not kill existing processes: {e}")
    
    # Start new instance
    try:
        proc = subprocess.Popen(
            [sys.executable, HEARTBEAT_SCRIPT, '--daemon'],
            stdout=open('/tmp/heartbeat.log', 'a'),
            stderr=subprocess.STDOUT,
            cwd=WORKSPACE,
            start_new_session=True  # Detach from parent
        )
        
        # Write PID file
        with open(PID_FILE, 'w') as f:
            f.write(str(proc.pid))
        
        log(f"Heartbeat restarted with PID: {proc.pid}")
        
        # Wait a moment and verify it's running
        time.sleep(2)
        if is_heartbeat_running():
            log("✅ Heartbeat confirmed running")
            return True
        else:
            log("❌ Heartbeat failed to start")
            return False
            
    except Exception as e:
        log(f"❌ Failed to restart heartbeat: {e}")
        return False

def main():
    """Main monitor function"""
    log("=" * 50)
    log("Heartbeat monitor check starting...")
    
    # Check if heartbeat is running
    if is_heartbeat_running():
        log("✅ Heartbeat is running normally")
        
        # Also check if it's making progress (log file updated recently)
        try:
            if os.path.exists('/tmp/heartbeat.log'):
                mtime = os.path.getmtime('/tmp/heartbeat.log')
                age_minutes = (time.time() - mtime) / 60
                
                if age_minutes > 10:
                    log(f"⚠️  Heartbeat log stale ({age_minutes:.1f} min old) - may be stuck")
                    # Restart anyway if log is stale
                    restart_heartbeat()
                else:
                    log(f"✅ Heartbeat log active ({age_minutes:.1f} min old)")
        except Exception as e:
            log(f"Warning: Could not check log age: {e}")
            
    else:
        log("❌ Heartbeat is NOT running")
        restart_heartbeat()
    
    log("Monitor check complete")
    log("=" * 50)

if __name__ == '__main__':
    main()
