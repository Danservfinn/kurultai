#!/bin/bash
# Cron Job Health Monitor
# 
# Monitors the 3 critical Kurultai cron jobs:
# 1. Hourly Reflection (bfa4cc51-0b06-4ac8-8d2b-e9849ace8f22)
# 2. Architecture Verification (76c16bd7-2ef4-4bc1-816b-7fdd91df4ecf)
# 3. Daily Goal Progress (eb631e87-24a0-43f5-bb0b-2b81b6aab304)
#
# Checks every 15 minutes, auto-fixes failed jobs
#
# Run via cron: */15 * * * * /path/to/cron-health-monitor.sh

set -e

LOG_FILE="/Users/kublai/.openclaw/logs/cron-health-monitor.log"
MEMORY_DIR="/Users/kublai/.openclaw/agents/main/memory"
TODAY=$(date +%Y-%m-%d)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Cron Health Check Started ==="

# Track issues
ISSUES_FOUND=0
ISSUES_FIXED=0

# ============================================
# CHECK 1: Hourly Reflection
# ============================================
log ""
log "CHECK 1: Hourly Reflection"
log "---------------------------"

HOURLY_JOB_ID="bfa4cc51-0b06-4ac8-8d2b-e9849ace8f22"
EXPECTED_HOURS=2  # Should have run at least 2 times in last 2 hours

# Check if job exists and is enabled
HOURLY_LINE=$(openclaw cron list 2>/dev/null | grep "$HOURLY_JOB_ID")

if [ -z "$HOURLY_LINE" ]; then
    log "❌ Hourly Reflection job not found"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
else
    # Check last run status
    LAST_STATUS=$(echo "$HOURLY_LINE" | awk '{print $9}')
    log "Hourly Reflection last status: $LAST_STATUS"
    
    if [ "$LAST_STATUS" = "error" ]; then
        log "❌ Hourly Reflection last run: error"
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
        
        # Try to restart the job
        log "🔧 Attempting to restart Hourly Reflection..."
        openclaw cron run --id "$HOURLY_JOB_ID" 2>/dev/null && {
            log "✅ Hourly Reflection restarted successfully"
            ISSUES_FIXED=$((ISSUES_FIXED + 1))
        } || {
            log "❌ Failed to restart Hourly Reflection"
        }
    else
        log "✅ Hourly Reflection last run: $LAST_STATUS"
    fi
fi

# Check if memory files were created in last 2 hours
RECENT_REFLECTIONS=$(find "$MEMORY_DIR" -name "$TODAY.md" -mmin -120 -type f 2>/dev/null | wc -l)

if [ "$RECENT_REFLECTIONS" -lt "$EXPECTED_HOURS" ]; then
    log "⚠️ Only $RECENT_REFLECTIONS reflection files in last 2 hours (expected: $EXPECTED_HOURS+)"
else
    log "✅ $RECENT_REFLECTIONS reflection files found (healthy)"
fi

# ============================================
# CHECK 2: Architecture Verification
# ============================================
log ""
log "CHECK 2: Architecture Verification"
log "-----------------------------------"

ARCH_JOB_ID="76c16bd7-2ef4-4bc1-816b-7fdd91df4ecf"

# Check if job exists
ARCH_LINE=$(openclaw cron list 2>/dev/null | grep "$ARCH_JOB_ID")

if [ -z "$ARCH_LINE" ]; then
    log "❌ Architecture Verification job not found"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
    
    # Recreate the job
    log "🔧 Recreating Architecture Verification job..."
    
    cat > /tmp/arch-cron-job.json << 'EOF'
{
  "name": "Architecture Verification - 12hr Check",
  "schedule": {
    "kind": "cron",
    "expr": "0 */12 * * *"
  },
  "payload": {
    "kind": "agentTurn",
    "message": "ARCHITECTURE VERIFICATION TASK: Review the current codebase and compare against ARCHITECTURE.md to ensure accuracy. Check for: 1) New files/directories not documented, 2) Changes to agent structure, 3) New operational systems, 4) Outdated Change Log entries, 5) New tools/capabilities, 6) Changes to memory architecture. Read ARCHITECTURE.md, then scan the codebase (ls -la ~/.openclaw/agents/main/, check for new scripts, check operational systems status). Report any discrepancies found and propose updates if needed. If ARCHITECTURE.md is accurate, report: \"✅ Architecture documentation verified - no updates needed\"."
  },
  "sessionTarget": "isolated",
  "delivery": {
    "channel": "signal",
    "mode": "announce",
    "to": "last"
  }
}
EOF
    
    openclaw cron add --job-file /tmp/arch-cron-job.json 2>/dev/null && {
        log "✅ Architecture Verification job recreated"
        ISSUES_FIXED=$((ISSUES_FIXED + 1))
    } || {
        log "❌ Failed to recreate Architecture Verification job"
    }
    
    rm -f /tmp/arch-cron-job.json
else
    log "✅ Architecture Verification job exists"
fi

# ============================================
# CHECK 3: Daily Goal Progress
# ============================================
log ""
log "CHECK 3: Daily Goal Progress"
log "-----------------------------"

DAILY_JOB_ID="eb631e87-24a0-43f5-bb0b-2b81b6aab304"
EXPECTED_TIME="07:00"  # Should run at 7 AM

# Check job status
DAILY_LINE=$(openclaw cron list 2>/dev/null | grep "$DAILY_JOB_ID")

if [ -z "$DAILY_LINE" ]; then
    log "❌ Daily Goal Progress job not found"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
else
    DAILY_STATUS=$(echo "$DAILY_LINE" | awk '{print $9}')
    
    if [ "$DAILY_STATUS" = "error" ]; then
        log "❌ Daily Goal Progress last run: error"
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
        
        # Check if it ran today
        DAILY_RAN=$(grep -l "Daily Progress\|Daily Goal" "$MEMORY_DIR/$TODAY.md" 2>/dev/null | wc -l)
        
        if [ "$DAILY_RAN" -eq 0 ]; then
            log "⚠️ Daily progress summary not found in today's memory"
            
            # Try to run the job manually
            log "🔧 Attempting to run Daily Goal Progress manually..."
            openclaw cron run --id "$DAILY_JOB_ID" 2>/dev/null && {
                log "✅ Daily Goal Progress ran successfully"
                ISSUES_FIXED=$((ISSUES_FIXED + 1))
            } || {
                log "❌ Failed to run Daily Goal Progress"
            }
        else
            log "✅ Daily progress summary found in memory (job error may be transient)"
        fi
    else
        log "✅ Daily Goal Progress last run: $DAILY_STATUS"
    fi
fi

# ============================================
# SUMMARY
# ============================================
log ""
log "=== SUMMARY ==="
log "Issues Found: $ISSUES_FOUND"
log "Issues Fixed: $ISSUES_FIXED"

if [ "$ISSUES_FOUND" -gt 0 ]; then
    if [ "$ISSUES_FIXED" -eq "$ISSUES_FOUND" ]; then
        log "✅ All issues resolved"
    else
        log "⚠️ Some issues remain unresolved ($((ISSUES_FOUND - ISSUES_FIXED)))"
    fi
else
    log "✅ All cron jobs healthy"
fi

log ""
log "=== Cron Health Check Complete ==="
log ""

# Exit with error if issues remain
if [ "$ISSUES_FOUND" -gt "$ISSUES_FIXED" ]; then
    exit 1
fi

exit 0
