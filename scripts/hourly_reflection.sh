#!/bin/bash
# Concurrent Kurultai Reflection - All 6 Agents Reflect Simultaneously
# Runs every hour with all agents reflecting in parallel
#
# Option B: Protocol-based reflections (~800 tokens/agent vs ~6400 legacy)
# - Role-specific protocols with WHEN/THEN behavioral rules
# - Commitment tracking across sessions
# - Tock data replaces redundant CLI calls
#
# HARD TIMEOUT: 420s (7 min) — Phase 3b moved to separate :30 launchd job
# Budget: reflections ~30s + reviews ~120s + downstream ~300s + margin
# CHECKPOINT: Emits reflection-status.json after core reflections complete
# FALLBACK: Exit 0 even if downstream steps fail (content generation succeeded)

SCRIPT_START=$(date +%s)
TIMEOUT_SECONDS=420

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
    # Kill any straggler background processes from review phase
    for _pid in "${review_pids[@]}"; do
        kill "$_pid" 2>/dev/null || true
    done
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

echo "[$(date)] Starting Concurrent Kurultai Reflection (All 6 Agents) [Protocol Mode]"
echo "[$(date)] Hard timeout: ${TIMEOUT_SECONDS}s | Watchdog PID: $WATCHDOG_PID"
echo "================================================================"

AGENTS=("kublai" "mongke" "chagatai" "temujin" "jochi" "ogedei")
HOURS=1
SCRIPTS="/Users/kublai/.openclaw/agents/main/scripts"
STEP_TIMING_FILE="$LOGS_DIR/reflection-step-timing.json"
REVIEWS_DIR="$LOGS_DIR/reviews"
CLAUDE_AGENT_BIN="/Users/kublai/.local/bin/claude-agent"
REVIEW_TIMEOUT=120

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

# Function to run reflection for a single agent
run_agent_reflection() {
    local AGENT="$1"
    local WORKSPACE="/Users/kublai/.openclaw/agents/$AGENT"
    local MEMORY_DIR="$WORKSPACE/memory"
    local DATE=$(date +%Y-%m-%d)
    local TIME=$(date +%H:%M)

    echo "[$(date)] [$AGENT] Starting protocol reflection..."

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
run_agent_review() {
    local AGENT="$1"
    local DATE=$(date +%Y-%m-%d)
    local MEMORY_FILE="/Users/kublai/.openclaw/agents/$AGENT/memory/$DATE.md"
    local REVIEW_FILE="$REVIEWS_DIR/${AGENT}-latest.md"

    echo "[$(date)] [$AGENT] Starting /horde-review performance analysis..."

    # Gather latest reflection (last 80 lines of today's memory)
    local REFLECTION=""
    if [ -f "$MEMORY_FILE" ]; then
        REFLECTION=$(tail -80 "$MEMORY_FILE" 2>/dev/null || echo "(no reflection)")
    else
        REFLECTION="(no reflection data for today)"
    fi

    # Gather tock metrics
    local TOCK_DATA=""
    local TOCK_FILE="$LOGS_DIR/tock/latest.json"
    if [ -f "$TOCK_FILE" ]; then
        TOCK_DATA=$(TOCK_FILE="$TOCK_FILE" AGENT="$AGENT" python3 -c "
import json, os
tf = os.environ['TOCK_FILE']
agent = os.environ['AGENT']
target = os.path.realpath(tf) if os.path.islink(tf) else tf
with open(target) as f:
    d = json.load(f)
a = d.get('agents',{}).get(agent,{})
t = a.get('tasks',{})
print(f'Completed: {t.get(\"completed\",0)} | Failed: {t.get(\"failed\",0)} | Queue: {t.get(\"queue_depth\",0)} | Retries: {a.get(\"retries\",0)} | Success: {a.get(\"success_rate\",\"N/A\")}%')
" 2>/dev/null || echo "Tock data unavailable")
    fi

    # Build review prompt and invoke /horde-review via claude-agent
    local REVIEW_PROMPT="/horde-review

Critically review ${AGENT} agent performance for the past hour.

## Agent Metrics (from tock)
${TOCK_DATA}

## Latest Reflection Data
${REFLECTION}

## Review Focus
Analyze this agent's performance with structured critical analysis:
1. Task completion effectiveness — what succeeded, what failed, why
2. Behavioral rule compliance — are WHEN/THEN rules being followed
3. Efficiency — time spent vs output produced
4. Cross-agent impact — how does this agent affect system throughput

Output EXACTLY this format:
STRENGTHS: (2-3 bullet points of what worked well)
WEAKNESSES: (2-3 bullet points of what failed or underperformed)
PATTERNS: (recurring issues or successes observed)
PRIORITY_FIX: (single most impactful improvement for next hour)
SCORE: (1-10 performance rating with one-line justification)"

    run_with_timeout "$REVIEW_TIMEOUT" "$CLAUDE_AGENT_BIN" --model sonnet "$REVIEW_PROMPT" > "$REVIEW_FILE" 2>>"$LOGS_DIR/horde-review-error.log"
    local rc=$?

    if [ $rc -eq 0 ] && [ -s "$REVIEW_FILE" ]; then
        echo "[$(date)] [$AGENT] /horde-review complete -> $REVIEW_FILE"
    else
        echo "[$(date)] [$AGENT] /horde-review failed or timed out (rc=$rc)"
        echo "# Review unavailable (rc=$rc, timeout=${REVIEW_TIMEOUT}s)" > "$REVIEW_FILE"
    fi
}

# Run all 6 agents in parallel (reflections are pure Python, no API rate limit concern)
echo "[$(date)] Launching ${#AGENTS[@]} agents in parallel..."

pids=()
for agent in "${AGENTS[@]}"; do
    run_agent_reflection "$agent" &
    pids+=($!)
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

echo "[$(date)] Starting /horde-review analysis for all agents (parallel, timeout=${REVIEW_TIMEOUT}s)..."

review_pids=()
for agent in "${AGENTS[@]}"; do
    run_agent_review "$agent" &
    review_pids+=($!)
done
for pid in "${review_pids[@]}"; do
    wait "$pid" || true
done

echo "[$(date)] All agent /horde-review analyses complete"
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
# BRAINSTORMING: Decoupled to run_brainstorm.sh (separate schedule at :30)
# ============================================================

# ============================================================
# DOWNSTREAM STEPS: Tiered parallel execution
# Tier 1: Independent steps (parallel)
# Tier 2: Depends on score-skills (sequential after Tier 1)
# Tier 3: Depends on all above (sequential after Tier 2)
# ============================================================

# --- Tier 1: Independent (parallel) ---
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

_bg_timed_step "memory-audit-fix" \
    run_with_timeout 30 python3 "$SCRIPTS/memory_audit.py" --fix >> "$LOGS_DIR/memory-audit.log" 2>&1 &
t1_pids+=($!)

_bg_timed_step "cross-agent-rules" \
    run_with_timeout 30 python3 "$SCRIPTS/cross_agent_rules.py" >> "$LOGS_DIR/cross-agent-rules.log" 2>&1 &
t1_pids+=($!)

_bg_timed_step "capability-scores" \
    run_with_timeout 30 python3 "$SCRIPTS/route_quality_tracker.py" >> "$LOGS_DIR/capability-scores.log" 2>&1 &
t1_pids+=($!)

_bg_timed_step "routing-audit" \
    run_with_timeout 30 python3 "$SCRIPTS/routing_audit_action.py" >> "$LOGS_DIR/routing-audit.log" 2>&1 &
t1_pids+=($!)

_bg_timed_step "score-skills" \
    run_with_timeout 30 python3 "$SCRIPTS/score_skills.py" --hours 2 >> "$LOGS_DIR/skill-scorer.log" 2>&1 &
t1_pids+=($!)

_bg_timed_step "action-scorer" \
    run_with_timeout 30 python3 "$SCRIPTS/action_scorer.py" --all --hours 2 >> "$LOGS_DIR/action-scorer.log" 2>&1 &
t1_pids+=($!)

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
    run_with_timeout 120 "$CLAUDE_AGENT_BIN" --model sonnet /kurultai-report >> "$LOGS_DIR/kurultai-report.log" 2>&1

timed_step "hourly-report" \
    run_with_timeout 60 python3 "$SCRIPTS/generate_hourly_report.py" >> "$LOGS_DIR/hourly-report.log" 2>&1

# Write step timing data
write_step_timing
echo "[$(date)] Step timing written to $STEP_TIMING_FILE"
echo "[$(date)] Hourly reflection pipeline complete (all steps)"
