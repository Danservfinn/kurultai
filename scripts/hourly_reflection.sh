#!/bin/bash
# Kurultai Reflection - All 6 Agents Reflect Simultaneously (4-Hour Cycle)
# Runs every 4 hours: 12 AM, 4 AM, 8 AM, 12 PM, 4 PM, 8 PM
#
# BENEFITS OF 4-HOUR CYCLE:
# - 6 reflections/day vs 24 (75% reduction in context switches)
# - Cleaner voting windows: 6 overlapping vs 24
# - Each Khan gets 4 hours to review before voting closes
# - 24h voting window works cleanly with fewer cycles
# - 4-hour response time still fast for system operations
#
# Option B: Protocol-based reflections (~800 tokens/agent vs ~6400 legacy)
# - Role-specific protocols with WHEN/THEN behavioral rules
# - Commitment tracking across sessions
# - Tock data replaces redundant CLI calls
#
# HARD TIMEOUT: 600s (10 min) — Increased from 420s to accommodate all 6 agent reviews
# Budget: reflections ~30s + reviews ~180s (30s/agent × 6 in 3 batches) + downstream ~300s + margin
# FIX 2026-03-08: Jochi and Ogedei (Batch 3) were timing out at 420s — now have full 10 min window
# CHECKPOINT: Emits reflection-status.json after core reflections complete
# FALLBACK: Exit 0 even if downstream steps fail (content generation succeeded)

SCRIPT_START=$(date +%s)
TIMEOUT_SECONDS=7200  # 2 hours

# ============================================================
# MODEL DETECTION: Get default model for reflection pipeline
# ============================================================
MODEL=$(python3 "$SCRIPTS/get_model.py" --agent main 2>/dev/null || echo "unknown")

# ============================================================
# CONCURRENCY CONTROL: Semaphore limiting for Claude processes
# ============================================================
MAX_CONCURRENT=3  # Reflections: 3 concurrent (fast, ~30s each)
MAX_CONCURRENT_REVIEW=3  # Reviews: 3 concurrent (FIX 2026-03-08: increased from 2 to reduce batch latency for jochi/ogedei)
MAX_LOAD=4.0  # Max system load (1-min avg) before blocking new spawns

# Job control for process group management
set -m

LOGS_DIR="/Users/kublai/.openclaw/agents/main/logs"
mkdir -p "$LOGS_DIR"
rm -f "$LOGS_DIR/reflection-status.json"

# Rotate logs > 1MB (runs once per hour at start of reflection)
for logfile in "$LOGS_DIR"/*.log; do
    [ -f "$logfile" ] || continue
    size=$(stat -f%z "$logfile" 2>/dev/null || echo 0)
    if [ "$size" -gt 1048576 ]; then
        mv "$logfile" "${logfile}.$(date +%Y%m%d%H%M)"
    fi
done

cleanup_and_exit() {
    local elapsed=$(($(date +%s) - SCRIPT_START))
    echo "[$(date)] Reflection finished in ${elapsed}s"
    # Write whatever step timing data we have so far
    write_step_timing
    # Kill entire process group (cleans up all orphaned child processes)
    kill -- -$$ 2>/dev/null || true
    # Always exit 0 if core reflections completed
    if [ -f "$LOGS_DIR/reflection-status.json" ]; then
        exit 0
    else
        exit 1
    fi
}

# Timeout watchdog - kill if running too long
timeout_watchdog() {
    sleep $TIMEOUT_SECONDS
    echo "[$(date)] TIMEOUT: Reflection exceeded ${TIMEOUT_SECONDS}s, forcing exit"
    kill -TERM $$ 2>/dev/null || true
}
timeout_watchdog &
WATCHDOG_PID=$!
trap "kill $WATCHDOG_PID 2>/dev/null; cleanup_and_exit" EXIT TERM INT

# ============================================================
# LOAD-BASED BACKOFF: Check system load before spawning processes
# ============================================================
check_system_load() {
    # Get 1-minute load average (macOS compatible)
    local load=$(sysctl -n vm.loadavg 2>/dev/null | awk '{print $2}' || echo "0")
    if (( $(echo "$load > $MAX_LOAD" | bc -l 2>/dev/null || echo 0) )); then
        return 1  # Load too high
    fi
    return 0  # Load OK
}

wait_for_semaphore() {
    # Wait for a slot in the semaphore (max concurrent processes)
    local wait_count=0
    while true; do
        running=$(jobs -p 2>/dev/null | wc -l)
        if [ "$running" -lt "$MAX_CONCURRENT" ]; then
            # Also check system load before spawning
            if check_system_load; then
                return 0  # Slot available and load OK
            fi
        fi
        # Wait a bit before checking again
        sleep 0.5
        wait_count=$((wait_count + 1))
        if [ $wait_count -gt 60 ]; then  # Timeout after 30s
            echo "[$(date)] WARNING: Semaphore wait timeout (load=$load, running=$running)"
            return 0  # Proceed anyway to avoid deadlock
        fi
    done
}

echo "[$(date)] Starting Concurrent Kurultai Reflection (All 6 Agents) [Protocol Mode]"
echo "[$(date)] Hard timeout: ${TIMEOUT_SECONDS}s | Watchdog PID: $WATCHDOG_PID"
echo "================================================================"

# ============================================================
# SHORT-CIRCUIT: Skip reflection if tock shows zero activity
# ============================================================
TOCK_FILE="$LOGS_DIR/tock/latest.json"
if [ -f "$TOCK_FILE" ]; then
    ZERO_ACTIVITY=$(python3 -c "
import json
try:
    with open('$TOCK_FILE') as f:
        data = json.load(f)
    total_completed = sum(a.get('tasks', {}).get('completed', 0) for a in data.get('agents', {}).values())
    total_failed = sum(a.get('tasks', {}).get('failed', 0) for a in data.get('agents', {}).values())
    total_pending = data.get('queues', {}).get('total_pending', 0)
    cron_errors = data.get('cron', {}).get('erroring', 0)
    if total_completed == 0 and total_failed == 0 and total_pending == 0 and cron_errors == 0:
        print('ZERO')
    else:
        print('ACTIVITY')
except:
    print('ACTIVITY')
")
    if [ "$ZERO_ACTIVITY" = "ZERO" ]; then
        # Task 6.5: Check agent heartbeat before short-circuiting
        HEARTBEAT_FILE="$LOGS_DIR/last-heartbeat.json"
        HEARTBEAT_STALE=$(python3 -c "
import json, os, time
from datetime import datetime
hb_file = '$HEARTBEAT_FILE'
now = time.time()
stale_agents = []
try:
    with open(hb_file) as f:
        hb = json.load(f)
    for agent, ts in hb.items():
        try:
            # Parse ISO format timestamp
            dt = datetime.fromisoformat(ts)
            age = now - dt.timestamp()
            if age > 90:  # Stale if > 90 seconds
                stale_agents.append(f'{agent}({int(age)}s)')
        except:
            stale_agents.append(f'{agent}(parse_error)')
    if stale_agents:
        print(','.join(stale_agents))
    else:
        print('OK')
except Exception as e:
    print(f'CHECK_FAILED:{e}')
")
        if [ "$HEARTBEAT_STALE" != "OK" ]; then
            echo "[$(date)] AGENT OFFLINE - skipping reflection (stale heartbeats: $HEARTBEAT_STALE)"
            # Write minimal step timing JSON even on heartbeat failure
            STEP_TIMING_FILE="$LOGS_DIR/reflection-step-timing.json"
            cat > "$STEP_TIMING_FILE" << 'TIMING_HB_EOF'
{"timestamp":"TIMESTAMP_HB_PLACEHOLDER","total_elapsed_s":0,"steps":[],"short_circuited":true,"reason":"agent_offline","stale_agents":"STALE_AGENTS_PLACEHOLDER"}
TIMING_HB_EOF
            sed -i.tmp "s/TIMESTAMP_HB_PLACEHOLDER/$(date -Iseconds)/" "$STEP_TIMING_FILE"
            sed -i.tmp2 "s/STALE_AGENTS_PLACEHOLDER/$HEARTBEAT_STALE/" "$STEP_TIMING_FILE"
            exit 0
        fi
        echo "[$(date)] SKIP: Zero activity detected - writing minimal report"
        MINIMAL_REPORT="$LOGS_DIR/hourly-reports/$(date +%Y-%m-%d-%H%M)-reflection-report.md"
        mkdir -p "$LOGS_DIR/hourly-reports"
        echo "# Kurultai Reflection Report - Minimal Cycle" > "$MINIMAL_REPORT"
        echo "" >> "$MINIMAL_REPORT"
        echo "**Period:** $(date +"%Y-%m-%d %H:00")" >> "$MINIMAL_REPORT"
        echo "**Status:** No activity detected - skipping full pipeline" >> "$MINIMAL_REPORT"
        echo "" >> "$MINIMAL_REPORT"
        echo "No agent tasks completed, failed, or pending. No cron errors." >> "$MINIMAL_REPORT"
        # Task 6.3: Write minimal step timing JSON even when short-circuiting
        STEP_TIMING_FILE="$LOGS_DIR/reflection-step-timing.json"
        cat > "$STEP_TIMING_FILE" << 'TIMING_EOF'
{"timestamp":"TIMESTAMP_PLACEHOLDER","total_elapsed_s":0,"steps":[],"short_circuited":true,"reason":"zero_activity"}
TIMING_EOF
        # Replace timestamp placeholder with actual timestamp
        sed -i.tmp "s/TIMESTAMP_PLACEHOLDER/$(date -Iseconds)/" "$STEP_TIMING_FILE"
        echo "[$(date)] Step timing written (short-circuit mode)"
        exit 0
    fi
fi

AGENTS=("kublai" "mongke" "chagatai" "temujin" "jochi" "ogedei")
HOURS=1
SCRIPTS="/Users/kublai/.openclaw/agents/main/scripts"
STEP_TIMING_FILE="$LOGS_DIR/reflection-step-timing.json"
REVIEWS_DIR="$LOGS_DIR/reviews"
CLAUDE_AGENT_BIN="/Users/kublai/.local/bin/claude-agent"
REVIEW_TIMEOUT=3600  # 1 hour - horde-review dispatches multiple parallel agents, needs more time

mkdir -p "$REVIEWS_DIR"

# Portable timeout function (macOS lacks GNU timeout)
run_with_timeout() {
    local secs="$1"; shift
    "$@" &
    local cmd_pid=$!
    ( sleep "$secs" && kill "$cmd_pid" 2>/dev/null ) &
    local wdog_pid=$!
    wait "$cmd_pid" 2>/dev/null
    local rc=$?
    kill "$wdog_pid" 2>/dev/null
    wait "$wdog_pid" 2>/dev/null
    return $rc
}

# Per-step timing: write individual JSON files (works in backgrounded subshells)
_STEP_TIMING_DIR=$(mktemp -d)
_step_counter=0
timed_step() {
    local step_name="$1"
    shift
    local step_start=$(date +%s)
    echo "[$(date)] Running: $step_name..."
    "$@"
    local step_rc=$?
    local step_end=$(date +%s)
    local step_dur=$((step_end - step_start))
    local status="ok"
    [ $step_rc -ne 0 ] && status="failed"
    [ $step_rc -ne 0 ] && echo "[$(date)] WARNING: $step_name FAILED (rc=$step_rc)" >&2
    local safe_name="${step_name//\"/}"
    # Write to temp file — survives backgrounding (subshell-safe)
    printf '{"name":"%s","duration_s":%d,"status":"%s"}' "$safe_name" "$step_dur" "$status" \
        > "$_STEP_TIMING_DIR/${step_start}-${safe_name}.json"
    echo "[$(date)] Completed: $step_name (${step_dur}s, rc=$step_rc)"
    return 0  # Don't fail the pipeline on downstream step errors
}

write_step_timing() {
    # Guard: only write once (EXIT trap may fire after explicit call)
    if [ "${_STEP_TIMING_WRITTEN:-0}" -eq 1 ]; then
        return 0
    fi
    _STEP_TIMING_WRITTEN=1
    local total_elapsed=$(($(date +%s) - SCRIPT_START))
    # Collect all step timing files, sorted by filename (timestamp prefix)
    local entries=""
    for tf in $(ls "$_STEP_TIMING_DIR"/*.json 2>/dev/null | sort); do
        [ -f "$tf" ] || continue
        local content=$(cat "$tf")
        if [ -n "$entries" ]; then entries="$entries,"; fi
        entries="$entries$content"
    done
    cat > "$STEP_TIMING_FILE" << EOTIMING
{"timestamp":"$(date -Iseconds)","total_elapsed_s":$total_elapsed,"steps":[$entries]}
EOTIMING
    rm -rf "$_STEP_TIMING_DIR"
}

# ============================================================
# AUTH HEALTH PREFLIGHT: Check if claude-agent can authenticate
# Prevents 15-hour reflection blackouts from auth failures
# ============================================================
AUTH_FAILURES_LOG="$LOGS_DIR/auth-failures.jsonl"

log_auth_failure() {
    local agent="$1"
    local reason="${2:-unknown}"
    local timestamp="$(date -Iseconds)"

    {
        echo "{\"timestamp\": \"$timestamp\", \"agent\": \"$agent\", \"script\": \"hourly_reflection.sh\", \"reason\": \"$reason\"}"
    } >> "$AUTH_FAILURES_LOG"

    # Also log to ticks for visibility
    echo "[$timestamp] AUTH_FAILURE: $agent failed preflight (reason: $reason)" >> "$LOGS_DIR/ticks.jsonl"
}

# Per-agent provider mapping (must match credential vault)
# All agents -> Z.AI (Tier 1) - Alibaba (sk-sp-*) timing out with Exit 124
get_agent_provider() {
    local agent="$1"
    case "$agent" in
        *) echo "zai" ;;  # All agents on zai (jochi, ogedei fixed 2026-03-12: was alibaba, timeout Exit 124)
    esac
}

auth_health_preflight() {
    local agent="${1:-kublai}"
    local timeout="${2:-30}"  # Increased from 15s to reduce Exit 124 false positives
    local max_retries=3  # Exponential backoff: 0s, 2s, 4s delays
    local attempt=0
    local provider=$(get_agent_provider "$agent")

    # Quick test: Can claude-agent complete a minimal request?
    # NOTE: claude-agent wrapper doesn't support --agent flag
    # We run from the agent's directory to ensure correct context
    local agent_dir="/Users/kublai/.openclaw/agents/$agent"
    if [ ! -d "$agent_dir" ]; then
        return 1  # Agent directory doesn't exist
    fi

    while [ $attempt -lt $max_retries ]; do
        (
            cd "$agent_dir" || exit 1
            # CRITICAL: Set CLAUDE_PROVIDER to use fallback credentials
            # Without this, claude-agent defaults to "default" provider with NO credentials
            export CLAUDE_PROVIDER="$provider"
            timeout ${timeout}s "$CLAUDE_AGENT_BIN" \
                "Respond with exactly: OK" \
                >/dev/null 2>&1
        )
        local rc=$?

        if [ $rc -eq 0 ]; then
            return 0  # Success - no need to retry
        fi

        attempt=$((attempt + 1))

        # Exponential backoff: 2^attempt seconds (2s, 4s, 8s)
        if [ $attempt -lt $max_retries ]; then
            local backoff=$((2 ** attempt))
            echo "[$(date)] [$agent] Auth preflight attempt $attempt failed, retrying in ${backoff}s..." >&2
            sleep $backoff
        fi
    done

    # All retries exhausted
    echo "[$(date)] [$agent] Auth preflight failed after $max_retries attempts" >&2
    return 1
}

# Function to run reflection for a single agent
run_agent_reflection() {
    local AGENT="$1"
    local WORKSPACE="/Users/kublai/.openclaw/agents/$AGENT"
    local MEMORY_DIR="$WORKSPACE/memory"
    local DATE=$(date +%Y-%m-%d)
    local TIME=$(date +%H:%M)

    # ============================================================
    # AUTH PREFLIGHT: Check before attempting reflection
    # Skip gracefully if auth fails (don't fail the entire cron job)
    # ============================================================
    if ! auth_health_preflight "$AGENT" 30; then
        echo "[$(date)] [$AGENT] SKIP: Auth preflight failed - skipping reflection"
        log_auth_failure "$AGENT" "preflight_timeout_or_auth_error"
        return 0  # Exit gracefully, not as error
    fi

    echo "[$(date)] [$AGENT] Auth confirmed - Starting protocol reflection..."

    # Run Neo4j/filesystem reconciliation to catch drift early
    # (Prevents phantom queue entries that block task dispatch)
    if [ -f "$SCRIPTS/reconcile_neo4j_tasks.py" ]; then
        echo "[$(date)] [$AGENT] Running Neo4j reconciliation..."
        python3 "$SCRIPTS/reconcile_neo4j_tasks.py" --fix >> "$LOGS_DIR/reconciliation.log" 2>&1 || true
    fi

    # Clear stale task claims (>10 min old) that block dispatch
    # (Fixes PENDING+session_key state inconsistency)
    if [ -f "$SCRIPTS/clear_stale_claims.py" ]; then
        echo "[$(date)] [$AGENT] Clearing stale task claims..."
        python3 "$SCRIPTS/clear_stale_claims.py" >> "$LOGS_DIR/reconciliation.log" 2>&1 || true
    fi

    # Run state consistency check to detect stale locks and orphaned tasks
    # (Added 2026-03-11: Prevents phantom dispatch failures)
    if [ -f "$SCRIPTS/state_consistency_check.py" ]; then
        echo "[$(date)] [$AGENT] Running state consistency check..."
        python3 "$SCRIPTS/state_consistency_check.py" --fix >> "$LOGS_DIR/state-consistency.log" 2>&1 || true
    fi

    # Ensure memory directory exists
    mkdir -p "$MEMORY_DIR"

    # Generate protocol-based reflection (Option B: ~800 tokens)
    local reflection=$(run_with_timeout 60 python3 "$SCRIPTS/meta_reflection.py" \
        --agent "$AGENT" \
        --hours "$HOURS" \
        --protocol \
        --heartbeat-review 2>/dev/null || echo "# Reflection unavailable")

    # Write reflection to memory with ACTIVE RULES section preserved
    # Check if ACTIVE RULES section already exists in today's file
    if [ -f "$MEMORY_DIR/$DATE.md" ] && grep -q "^## ACTIVE RULES" "$MEMORY_DIR/$DATE.md"; then
        # Append session log only (rules already at top)
        printf '\n---\n\n## SESSION LOG - %s (Protocol Reflection)\n\n%s\n\n---\n' "$TIME" "$reflection" >> "$MEMORY_DIR/$DATE.md"
    else
        # First reflection of the day — include header
        printf '\n---\n\n## %s - Hourly Reflection (Protocol Mode)\n\n**Agent:** %s\n**Period:** Last %s hour(s)\n\n%s\n\n---\n' "$TIME" "$AGENT" "$HOURS" "$reflection" >> "$MEMORY_DIR/$DATE.md"
    fi

    echo "[$(date)] [$AGENT] Protocol reflection complete -> $MEMORY_DIR/$DATE.md"
}

# Function to run /horde-review critical analysis for a single agent
# P0 Self-Healing: Now uses review-with-fallback.py for graceful degradation
run_agent_review() {
    local AGENT="$1"
    local REVIEW_FILE="$REVIEWS_DIR/${AGENT}-latest.md"

    echo "[$(date)] [$AGENT] Starting review with fallback mode..."

    # Use review-with-fallback.py which implements:
    # 1. Full horde-review
    # 2. Degraded single-agent review
    # 3. Static checklist (last resort)
    python3 "$SCRIPTS/review-with-fallback.py" \
        --agent "$AGENT" \
        --timeout "$REVIEW_TIMEOUT" \
        --output "$REVIEW_FILE"

    local rc=$?

    if [ $rc -eq 0 ] && [ -s "$REVIEW_FILE" ]; then
        # Extract mode used from the review content
        local mode=$(grep -E "^\(.*Mode\)" "$REVIEW_FILE" 2>/dev/null | head -1 | sed 's/.*(\(.*\) Mode).*/\1/' || echo "unknown")
        echo "[$(date)] [$AGENT] Review complete (mode: ${mode}) -> $REVIEW_FILE"
    else
        echo "[$(date)] [$AGENT] Review failed even with fallback (rc=$rc)"
        echo "# Review unavailable - all modes failed (rc=$rc)" > "$REVIEW_FILE"
    fi
}

# Run all 6 agents in parallel with concurrency limiting
echo "[$(date)] Launching ${#AGENTS[@]} agents with semaphore (max $MAX_CONCURRENT concurrent)..."

pids=()
for agent in "${AGENTS[@]}"; do
    # Wait for semaphore slot before spawning
    wait_for_semaphore
    run_agent_reflection "$agent" &
    pids+=($!)
    echo "[$(date)] Spawned $agent (running: $(jobs -p | wc -l))"
done
for pid in "${pids[@]}"; do
    wait "$pid" || true
done

echo "[$(date)] All 6 agents completed their reflections (parallel)"
echo "================================================================"

# ============================================================
# CHECKPOINT: Emit success status - core reflections complete
# This decouples content generation success from downstream step failures
# ============================================================
cat > "$LOGS_DIR/reflection-status.json" << EOF
{
  "status": "content_complete",
  "timestamp": "$(date -Iseconds)",
  "elapsed_seconds": $(($(date +%s) - SCRIPT_START)),
  "agents": ["kublai", "mongke", "chagatai", "temujin", "jochi", "ogedei"]
}
EOF
echo "[$(date)] Checkpoint written to $LOGS_DIR/reflection-status.json"

echo "[$(date)] Concurrent Kurultai Reflection Complete"
echo "================================================================"

# ============================================================
# PERFORMANCE REVIEW: /horde-review for each agent (parallel)
# New flow: Reflect -> Review -> Brainstorm -> Proposal
# Review output consumed by kurultai_brainstorm.py at :30
# ============================================================

echo "[$(date)] Starting /horde-review analysis for all agents (batched, timeout=${REVIEW_TIMEOUT}s, max concurrent=$MAX_CONCURRENT_REVIEW)..."

# Run reviews in batches of 2 to reduce resource contention
# horde-review dispatches multiple parallel agents, so we limit concurrency
review_batch() {
    local agents=("$@")
    local pids=()
    for agent in "${agents[@]}"; do
        wait_for_semaphore
        run_agent_review "$agent" &
        pids+=($!)
        echo "[$(date)] Spawned $agent review (running: $(jobs -p | wc -l))"
    done
    for pid in "${pids[@]}"; do
        wait "$pid" || true
    done
}

# Batch 1: kublai, mongke
echo "[$(date)] Starting Batch 1: kublai, mongke"
BATCH1_START=$(date +%s)
review_batch "kublai" "mongke"
BATCH1_END=$(date +%s)
echo "[$(date)] Batch 1 complete in $((BATCH1_END - BATCH1_START))s"

# Batch 2: chagatai, temujin
echo "[$(date)] Starting Batch 2: chagatai, temujin"
BATCH2_START=$(date +%s)
review_batch "chagatai" "temujin"
BATCH2_END=$(date +%s)
echo "[$(date)] Batch 2 complete in $((BATCH2_END - BATCH2_START))s"

# Batch 3: jochi, ogedei (FIX 2026-03-08: now have full 600s window)
echo "[$(date)] Starting Batch 3: jochi, ogedei"
BATCH3_START=$(date +%s)
review_batch "jochi" "ogedei"
BATCH3_END=$(date +%s)
echo "[$(date)] Batch 3 complete in $((BATCH3_END - BATCH3_START))s"

TOTAL_REVIEW_TIME=$((BATCH3_END - BATCH1_START))
echo "[$(date)] All agent /horde-review analyses complete (total: ${TOTAL_REVIEW_TIME}s)"
echo "================================================================"

# ============================================================
# ANOMALY SCANNER: Auto-escalate issues found in reviews + ledger
# Creates tasks for low-scoring agents and unanalyzed failures
# ============================================================
timed_step "anomaly-scanner" \
    run_with_timeout 30 python3 "$SCRIPTS/reflection_anomaly_scanner.py" --hours "$HOURS" >> "$LOGS_DIR/anomaly-scanner.log" 2>&1

# ============================================================
# RULE COMPLIANCE: Parse reflection outputs -> update rule registry
# Closes the feedback loop: follow/violate counts enable auto-deprecation
# ============================================================
timed_step "rule-compliance" \
    run_with_timeout 15 python3 "$SCRIPTS/parse_rule_compliance.py" --auto-deprecate >> "$LOGS_DIR/rule-compliance.log" 2>&1

# ============================================================
# TASK METRICS: Aggregate hourly metrics into TaskMetric nodes
# Creates pre-aggregated metrics for faster reflection queries
# Gracefully degrades when TaskOutcome nodes don't exist (Phase 1 incomplete)
# ============================================================
timed_step "task-metrics" \
    run_with_timeout 30 python3 "$SCRIPTS/aggregate_task_metrics.py" --period hourly --hours 1 >> "$LOGS_DIR/metrics-aggregation.log" 2>&1

# ============================================================
# CONSENSUS VOTING: Authentic Mongolian Kurultai Model
# Phase 1: Generate Proposals (each Khan writes their own)
# Phase 2: Start Voting (60-min window)
# Phase 3: Check Consensus (unanimous = 6/6 APPROVE)
# Phase 4: Create Tasks for Approved (only after consensus)
# ============================================================

echo "[$(date)] Starting Consensus Voting (Kurultai Model)..."

# Phase 1: Generate proposals from each agent's reflection
# Each agent generates 1 sample proposal based on their domain expertise
# In production, this would extract proposals from reflection output
echo "[$(date)] Starting Consensus Voting - Phase 1: Generate proposals..."
for agent in kublai temujin mongke chagatai jochi ogedei; do
    echo "[$(date)] Generating proposal for $agent..."
    if run_with_timeout 30 python3 "$SCRIPTS/proposal_generator.py" --agent "$agent" --sample >> "$LOGS_DIR/voting-phase1.log" 2>&1; then
        echo "[$(date)] Proposal generated for $agent"
    else
        echo "[$(date)] WARNING: Proposal generation failed for $agent (rc=$?)"
    fi
done
echo "[$(date)] Phase 1 complete"

# Phase 2: Start voting for pending proposals
timed_step "voting-phase2-start" \
    run_with_timeout 30 python3 "$SCRIPTS/kurultai_voting.py" --phase 3 >> "$LOGS_DIR/voting-phase2.log" 2>&1

# Phase 2b: Cast votes - Each agent votes on proposals from last 24h
# This is the authentic Kurultai model - all Khans evaluate proposals
timed_step "voting-phase2b-cast-votes" \
    run_with_timeout 120 python3 "$SCRIPTS/kurultai_voting.py" --cast-votes >> "$LOGS_DIR/voting-phase2b.log" 2>&1

# Phase 3: Check consensus (will finalize proposals)
timed_step "voting-phase3-consensus" \
    run_with_timeout 30 python3 "$SCRIPTS/kurultai_voting.py" --phase 4 >> "$LOGS_DIR/voting-phase3.log" 2>&1

# Phase 4: Create tasks for approved proposals
timed_step "voting-phase4-tasks" \
    run_with_timeout 60 python3 "$SCRIPTS/kurultai_voting.py" --phase 5 >> "$LOGS_DIR/voting-phase4.log" 2>&1

echo "[$(date)] Consensus Voting complete"

# ============================================================
# BRAINSTORMING: Decoupled to run_brainstorm.sh (separate schedule at :30)
# ============================================================

# ============================================================
# DOWNSTREAM STEPS: Tiered parallel execution
# Tier 1: Independent steps (parallel)
# Tier 2: Depends on score-skills (sequential after Tier 1)
# Tier 3: Depends on all above (sequential after Tier 2)
# ============================================================

# --- Tier 1: Independent (parallel with semaphore) ---
# _bg_timed_step writes timing to $_STEP_TIMING_DIR (same as timed_step)
# so all step durations are captured by write_step_timing().
t1_pids=()

_bg_timed_step() {
    local step_name="$1"; shift
    local step_start=$(date +%s)
    echo "[$(date)] Running: $step_name..."
    "$@"
    local step_rc=$?
    local step_dur=$(( $(date +%s) - step_start ))
    local status="ok"
    [ $step_rc -ne 0 ] && status="failed"
    [ $step_rc -ne 0 ] && echo "[$(date)] WARNING: $step_name FAILED (rc=$step_rc)" >&2
    local safe_name="${step_name//\"/}"
    printf '{"name":"%s","duration_s":%d,"status":"%s"}' "$safe_name" "$step_dur" "$status" \
        > "$_STEP_TIMING_DIR/${step_start}-${safe_name}.json"
    echo "[$(date)] Completed: $step_name (${step_dur}s, rc=$step_rc)"
}

echo "[$(date)] Starting Tier 1 (independent steps) with semaphore..."

for step_name in "reflection-research-persist" "session-drift-detect" "memory-audit-fix" "cross-agent-rules" "agent-rules-evaluator" "capability-scores" "routing-audit" "score-skills" "action-scorer" "report-analysis"; do
    wait_for_semaphore
    case "$step_name" in
        reflection-research-persist)
            _bg_timed_step "$step_name" run_with_timeout 15 python3 "$SCRIPTS/persist_research.py" --persist-reflection --agent mongke >> "$LOGS_DIR/reflection-research-persist.log" 2>&1 &
            ;;
        session-drift-detect)
            _bg_timed_step "$step_name" run_with_timeout 15 python3 "$SCRIPTS/session_model_drift_detector.py" >> "$LOGS_DIR/session-drift.log" 2>&1 &
            ;;
        memory-audit-fix)
            _bg_timed_step "$step_name" run_with_timeout 30 python3 "$SCRIPTS/memory_audit.py" --fix >> "$LOGS_DIR/memory-audit.log" 2>&1 &
            ;;
        cross-agent-rules)
            _bg_timed_step "$step_name" run_with_timeout 30 python3 "$SCRIPTS/cross_agent_rules.py" >> "$LOGS_DIR/cross-agent-rules.log" 2>&1 &
            ;;
        agent-rules-evaluator)
            _bg_timed_step "$step_name" run_with_timeout 30 python3 "$SCRIPTS/evaluate_agent_rules.py" --exec >> "$LOGS_DIR/agent-rules-evaluator.log" 2>&1 &
            ;;
        capability-scores)
            _bg_timed_step "$step_name" run_with_timeout 30 python3 "$SCRIPTS/route_quality_tracker.py" >> "$LOGS_DIR/capability-scores.log" 2>&1 &
            ;;
        routing-audit)
            _bg_timed_step "$step_name" run_with_timeout 30 python3 "$SCRIPTS/routing_audit_action.py" >> "$LOGS_DIR/routing-audit.log" 2>&1 &
            ;;
        score-skills)
            _bg_timed_step "$step_name" run_with_timeout 30 python3 "$SCRIPTS/score_skills.py" --hours 2 >> "$LOGS_DIR/skill-scorer.log" 2>&1 &
            ;;
        action-scorer)
            _bg_timed_step "$step_name" run_with_timeout 30 python3 "$SCRIPTS/action_scorer.py" --all --hours 2 >> "$LOGS_DIR/action-scorer.log" 2>&1 &
            ;;
        report-analysis)
            _bg_timed_step "$step_name" run_with_timeout 30 python3 "$SCRIPTS/report_analyzer.py" --all-agents --hours 1 --reflection-block > "$LOGS_DIR/task-completion-report.md" 2>&1 &
            ;;
    esac
    t1_pids+=($!)
    echo "[$(date)] Spawned $step_name (running: $(jobs -p | wc -l))"
done

for pid in "${t1_pids[@]}"; do wait "$pid" || true; done

echo "[$(date)] Tier 1 (independent steps) complete"

# --- Tier 2: Depends on score-skills ---
timed_step "update-skill-stats" \
    run_with_timeout 30 python3 "$SCRIPTS/update_skill_stats.py" >> "$LOGS_DIR/skill-scorer.log" 2>&1

# --- Tier 3: Depends on all above ---
timed_step "kublai-actions" \
    run_with_timeout 60 python3 "$SCRIPTS/kublai-actions.py" --trigger kurultai >> "$LOGS_DIR/kublai-actions.log" 2>&1

timed_step "kublai-initiative" \
    run_with_timeout 60 python3 "$SCRIPTS/kublai-initiative.py" >> "$LOGS_DIR/kublai-initiative.log" 2>&1

timed_step "kurultai-report" \
    run_with_timeout 30 "$CLAUDE_AGENT_BIN" /kurultai-report >> "$LOGS_DIR/kurultai-report.log" 2>&1

timed_step "hourly-report" \
    run_with_timeout 60 python3 "$SCRIPTS/generate_hourly_report.py" >> "$LOGS_DIR/hourly-report.log" 2>&1

# Write step timing data
write_step_timing
echo "[$(date)] Step timing written to $STEP_TIMING_FILE"
echo "[$(date)] Hourly reflection pipeline complete (all steps)"
