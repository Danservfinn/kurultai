#!/usr/bin/env python3
"""
Completion Audit — Continuous verification of recently completed tasks.

Integrates into watchdog-gather.sh heartbeat cycle (runs every 5 minutes).
Verifies tasks that completed since the last audit by checking:
  1. Workspace result file exists with substantive content
  2. No fake completion markers (delegated without execution, wrong model)
  3. Cross-references watcher state for execution records

Unlike queue-audit.py (30-min full audit), this is a lightweight,
continuous check that catches fake completions within minutes.

Usage:
    python3 completion-audit.py [--json]

Output:
    - completion-audit.jsonl (append, machine-readable history)
    - stdout (summary for watchdog integration)
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_state import locked_json_read, locked_json_update
from kurultai_paths import AGENTS_DIR, LOGS_DIR

# Task completion standard validator
try:
    from task_completion_standard import validate_completion_report, score_report_quality
    HAS_COMPLETION_STANDARD = True
except ImportError:
    HAS_COMPLETION_STANDARD = False

STATE_FILE = LOGS_DIR / "completion-audit-state.json"
AUDIT_LOG = LOGS_DIR / "completion-audit.jsonl"
WATCHER_STATE = LOGS_DIR / "watcher-state.json"

AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]

# Known test/trivial patterns to skip
SKIP_PATTERNS = [
    "test", "hello world", "fibonacci",
    "build a login", "verify claude code", "write a short"
]

# LLM configuration for intelligent review
LLM_ENDPOINT = "http://localhost:11434/api/chat"
LLM_MODEL = "hf.co/lukey03/Qwen3.5-9B-abliterated-GGUF"
LLM_TIMEOUT = 30  # Max seconds for LLM review (don't block tick cycle)


def load_state():
    """Load last audit timestamp."""
    return locked_json_read(str(STATE_FILE), default={"last_audit": 0, "audits_run": 0})


def save_state(state):
    """Persist audit state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with locked_json_update(str(STATE_FILE)) as data:
        data.clear()
        data.update(state)


def get_recent_audit_trends(n=5):
    """Get trends from recent audit history."""
    if not AUDIT_LOG.exists():
        return []

    trends = []
    try:
        with open(AUDIT_LOG, "r") as f:
            lines = f.readlines()[-n:]
            for line in lines:
                line = line.strip()
                if line:
                    trends.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        pass
    return trends


def llm_review(totals, details):
    """Pass audit findings to local LLM for intelligent escalation decision.

    Returns dict with:
        - decision: IGNORE | WARN | ESCALATE
        - confidence: 0-100
        - reasoning: str
        - recommended_action: str or None
    """
    # Build context for LLM
    trends = get_recent_audit_trends(5)

    # Summarize recent trends
    trend_summary = ""
    if trends:
        fake_counts = [t.get("totals", {}).get("fake_found", 0) for t in trends]
        requeue_counts = [t.get("totals", {}).get("requeued", 0) for t in trends]
        avg_fake = sum(fake_counts) / len(fake_counts) if fake_counts else 0
        avg_requeue = sum(requeue_counts) / len(requeue_counts) if requeue_counts else 0
        trend_summary = f"\nRECENT TRENDS (last {len(trends)} audits): avg_fake={avg_fake:.1f} avg_requeued={avg_requeue:.1f}"

    # Summarize current findings
    findings = []
    for d in details[:10]:  # Limit to first 10
        findings.append(f"  - {d['agent']}/{d['task']}: {d['action']}" +
                       (f" ({d.get('reason', '')})" if d.get('reason') else ''))

    # Get system state
    system_state = ""
    try:
        import subprocess
        result = subprocess.run(
            ["python3", str(Path(__file__).parent / "queue_status.py"), "--json"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            qs = json.loads(result.stdout)
            system_state = f"\nSYSTEM STATE: pending={qs.get('total_pending', '?')} queues={qs.get('by_agent', {})}"
    except Exception:
        pass

    prompt = f"""You are an audit reviewer for a 6-agent AI system (Kurultai). Analyze the completion audit findings and recommend an action.

CURRENT AUDIT:
  Audited: {totals['audited']}
  Verified: {totals['verified']}
  Fake completions found: {totals['fake_found']}
  Re-queued: {totals['requeued']}
  Skipped (test tasks): {totals['skipped']}

FINDINGS:
{chr(10).join(findings) if findings else '  (no significant findings)'}
{trend_summary}
{system_state}

DECISION GUIDELINES:
- IGNORE: Normal operation, fake_found=0 or all requeued successfully
- WARN: Minor concern (1-2 fakes, low priority tasks, first occurrence)
- ESCALATE: Requires Kublai attention (3+ fakes, high priority tasks, recurring pattern, or system issues)

Respond in EXACTLY this format (no extra text):
DECISION: IGNORE|WARN|ESCALATE
CONFIDENCE: <0-100>
REASONING: <1-2 sentences>
RECOMMENDED_ACTION: <what Kublai should do, or "none">"""

    try:
        import requests
        from ollama_lock import OllamaLock, Priority, LockBusy

        with OllamaLock(Priority.NORMAL, label="completion-audit-review"):
            resp = requests.post(
                LLM_ENDPOINT,
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are a concise operations auditor. Provide structured decisions only."},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False,
                    "think": False,
                    "options": {"num_predict": 200}
                },
                timeout=LLM_TIMEOUT
            )

            if resp.status_code != 200:
                return fallback_decision(totals, details, "llm_error")

            text = resp.json().get("message", {}).get("content", "").strip()
            # Remove thinking blocks if present
            text = re.sub(r'<think.*?>.*?</think.*?>', '', text, flags=re.DOTALL).strip()

            if not text:
                return fallback_decision(totals, details, "empty_response")

            # Parse response
            decision = "IGNORE"
            confidence = 50
            reasoning = "Unable to parse LLM response"
            recommended_action = None

            for line in text.split('\n'):
                line = line.strip()
                if line.startswith("DECISION:"):
                    val = line.split(":", 1)[1].strip().upper()
                    if val in ("IGNORE", "WARN", "ESCALATE"):
                        decision = val
                elif line.startswith("CONFIDENCE:"):
                    try:
                        confidence = int(re.sub(r'[^0-9]', '', line.split(":", 1)[1]))
                        confidence = max(0, min(100, confidence))
                    except ValueError:
                        pass
                elif line.startswith("REASONING:"):
                    reasoning = line.split(":", 1)[1].strip()
                elif line.startswith("RECOMMENDED_ACTION:"):
                    recommended_action = line.split(":", 1)[1].strip()
                    if recommended_action.lower() in ("none", "n/a", "-"):
                        recommended_action = None

            return {
                "decision": decision,
                "confidence": confidence,
                "reasoning": reasoning,
                "recommended_action": recommended_action
            }

    except LockBusy:
        return fallback_decision(totals, details, "gpu_busy")
    except ImportError:
        return fallback_decision(totals, details, "no_ollama_lock")
    except Exception as e:
        return fallback_decision(totals, details, f"error: {str(e)[:50]}")


def fallback_decision(totals, details, reason="fallback"):
    """Rule-based fallback when LLM is unavailable."""
    fake = totals.get("fake_found", 0)

    if fake >= 3:
        return {
            "decision": "ESCALATE",
            "confidence": 80,
            "reasoning": f"Rule-based: {fake} fake completions detected (threshold: 3)",
            "recommended_action": "Review agent execution logs and check for systematic issues"
        }
    elif fake >= 1:
        return {
            "decision": "WARN",
            "confidence": 60,
            "reasoning": f"Rule-based: {fake} fake completion(s) detected",
            "recommended_action": None
        }
    else:
        return {
            "decision": "IGNORE",
            "confidence": 90,
            "reasoning": f"Rule-based: No fake completions ({reason})",
            "recommended_action": None
        }


def create_escalation_task(llm_result, totals, details):
    """Create a task for Kublai when LLM recommends escalation."""
    try:
        from task_intake import create_task

        # Build task body
        fake_details = [d for d in details if d.get("action") == "requeued"]
        detail_lines = []
        for d in fake_details[:5]:
            detail_lines.append(f"- {d['agent']}/{d['task']}")

        body = f"""## LLM Escalation from Completion Audit

**LLM Decision:** {llm_result['decision']}
**Confidence:** {llm_result['confidence']}%
**Reasoning:** {llm_result['reasoning']}

### Audit Summary
- Audited: {totals['audited']}
- Verified: {totals['verified']}
- Fake found: {totals['fake_found']}
- Re-queued: {totals['requeued']}

### Affected Tasks
{chr(10).join(detail_lines) if detail_lines else '(none)'}

### Recommended Action
{llm_result.get('recommended_action') or 'Investigate and take appropriate action'}

---
*Auto-generated by completion-audit.py LLM review*"""

        task_id = create_task(
            title=f"Completion Audit Escalation: {totals['fake_found']} fake completions",
            body=body,
            priority="high" if llm_result['confidence'] >= 70 else "normal",
            source="completion-audit-llm",
            depth=1,
            agent="kublai",
        )
        return task_id
    except Exception as e:
        # Log error but don't fail the audit
        return None


def is_test_task(content):
    """Check if task is a test or trivial task."""
    content_lower = content.lower()
    for pattern in SKIP_PATTERNS:
        if pattern in content_lower:
            return True
    # Very short content is likely a test
    text = content.split("---", 3)[-1].strip() if "---" in content else content
    if len(text) < 80:
        return True
    return False


def find_result_file(agent, task_mtime):
    """Find workspace result file created near task completion time."""
    workspace = AGENTS_DIR / agent / "workspace"
    if not workspace.exists():
        return None

    best = None
    best_delta = 1800  # 30 min window
    for f in workspace.glob("task-*.md"):
        try:
            delta = abs(f.stat().st_mtime - task_mtime)
            if delta < best_delta:
                best_delta = delta
                best = str(f)
        except OSError:
            continue
    return best


def check_execution_in_watcher_state(agent, task_name):
    """Check if task has execution record in watcher state."""
    if not WATCHER_STATE.exists():
        return False
    try:
        state = json.loads(WATCHER_STATE.read_text())
        key = f"{agent}/{task_name}"
        return key in state
    except (OSError, json.JSONDecodeError):
        return False


def is_fake_completion(result_path, done_content, agent, task_name):
    """Determine if a task completion is fake (no real execution)."""
    # Check for agent-written closures with real content
    if "## Resolution" in done_content or "**Status:** RESOLVED" in done_content:
        return False

    # Intentionally marked obsolete
    if ".obsolete.done" in task_name:
        return False

    # Failed tasks are legitimate (agent ran but failed)
    if ".failed.done" in task_name or ".orphan-failed.done" in task_name:
        return False

    # Verified/unverified passed through task-verifier.py
    if ".verified.done" in task_name or ".unverified.done" in task_name:
        return False

    # CRITICAL: Handle .no_output.done.md (sub-threshold but legitimate execution)
    # The _verify_task_completion() function marks these when output < 500 chars or < 8 lines
    # We need to distinguish between "brief but real output" vs "actual no output"
    if ".no_output.done" in task_name:
        # Check if there's actual execution output section with substance
        # SECURITY: Use rsplit() to find the LAST occurrence of the marker,
        # which is always the system-controlled marker added by _append_output_to_executing()
        # This prevents injection attacks where task descriptions contain the marker.
        execution_marker = "## Execution Output"
        if execution_marker in done_content:
            parts = done_content.rsplit(execution_marker, 1)
            if len(parts) == 2:
                exec_output = parts[1].strip()
                # At least 200 chars of content means real execution, just brief
                if len(exec_output) > 200:
                    return False  # Brief but legitimate output
        # No meaningful execution output found
        return True

    # No result file — check watcher state
    if result_path is None:
        # Strip suffixes to get original name
        orig_name = task_name.replace(".completed.done.md", ".md")
        orig_name = orig_name.replace(".done.md", ".md")
        if check_execution_in_watcher_state(agent, orig_name):
            return False
        return True

    # Check result file content
    try:
        result_content = Path(result_path).read_text()
    except OSError:
        return True

    # Real Claude Code execution markers
    if "**Model:** claude-code" in result_content:
        return False

    # Fake completion markers
    if "delegated to" in result_content.lower() and "spawn queue" in result_content.lower():
        return True

    # Note: qwen3.5-plus check removed - legitimate proxy model, not fake
    # Legacy fake markers (from old model routing) kept for other models
    if "**Latency:** 0ms" in result_content and "**Model:**" in result_content:
        return True

    return False


def audit():
    """Run completion audit. Returns (totals, details)."""
    state = load_state()
    last_audit = state.get("last_audit", 0)
    now = time.time()

    totals = {
        "audited": 0,
        "fake_found": 0,
        "requeued": 0,
        "skipped": 0,
        "verified": 0,
        "poor_reports": 0,
        "missing_report_standard": 0,
    }
    details = []

    for agent in AGENTS:
        tasks_dir = AGENTS_DIR / agent / "tasks"
        if not tasks_dir.exists():
            continue

        for f in tasks_dir.glob("*.done.md"):
            # Skip files audited in previous cycle
            try:
                mtime = f.stat().st_mtime
                if mtime <= last_audit:
                    continue
            except OSError:
                continue

            # Skip old tasks (only check recent completions)
            age_hours = (now - mtime) / 3600
            if age_hours > 2:
                continue

            task_name = f.name
            content = f.read_text(encoding="utf-8", errors="replace")

            # Skip test tasks
            if is_test_task(content):
                totals["skipped"] += 1
                continue

            totals["audited"] += 1

            # Find result file
            result_path = find_result_file(agent, mtime)

            # Check if fake
            if is_fake_completion(result_path, content, agent, task_name):
                totals["fake_found"] += 1

                # Re-queue by renaming back to pending
                orig_name = task_name.replace(".completed.done.md", ".md")
                orig_name = orig_name.replace(".done.md", ".md")

                # Handle various suffix patterns
                for suffix in [".verified.done.md", ".unverified.done.md",
                               ".failed.done.md", ".stale.done.md"]:
                    if task_name.endswith(suffix):
                        orig_name = task_name[:-len(suffix)] + ".md"
                        break

                dest = tasks_dir / orig_name
                if not dest.exists():
                    try:
                        f.rename(dest)
                        # Touch to update mtime
                        dest.touch()
                        totals["requeued"] += 1

                        # Clear from watcher state
                        try:
                            ws = json.loads(WATCHER_STATE.read_text())
                            key = f"{agent}/{orig_name}"
                            if key in ws:
                                del ws[key]
                                WATCHER_STATE.write_text(json.dumps(ws, indent=2))
                        except (OSError, json.JSONDecodeError):
                            pass

                        details.append({
                            "agent": agent,
                            "task": task_name,
                            "action": "requeued",
                            "reason": "fake_completion"
                        })
                    except OSError:
                        details.append({
                            "agent": agent,
                            "task": task_name,
                            "action": "requeue_failed"
                        })
                else:
                    details.append({
                        "agent": agent,
                        "task": task_name,
                        "action": "skipped",
                        "reason": "original_exists"
                    })
            else:
                totals["verified"] += 1

                # Check completion report quality (Kurultai standard)
                quality_score = None
                report_is_valid = True
                quality_issues = []

                if HAS_COMPLETION_STANDARD and result_path:
                    try:
                        result_content = Path(result_path).read_text(encoding="utf-8", errors="replace")
                        scores = score_report_quality(result_content, {"agent": agent})
                        quality_score = scores.get("overall_score", 100)
                        report_is_valid = scores.get("overall_score", 100) >= 50

                        if quality_score < 70:
                            totals["poor_reports"] += 1
                            quality_issues = scores.get("recommendations", [])[:3]

                        # Extract task metadata for type detection
                        is_valid, missing, report_type = validate_completion_report(
                            result_content, {"agent": agent}
                        )
                        if not is_valid and report_type == "implementation":
                            totals["missing_report_standard"] += 1
                    except Exception:
                        pass

                details.append({
                    "agent": agent,
                    "task": task_name,
                    "action": "verified",
                    "has_result": result_path is not None,
                    "quality_score": quality_score,
                    "report_is_valid": report_is_valid,
                    "quality_issues": quality_issues,
                })

    # Update state
    state["last_audit"] = now
    state["audits_run"] = state.get("audits_run", 0) + 1
    state["last_totals"] = totals
    state["last_ts"] = datetime.now().isoformat()
    save_state(state)

    # LLM Review for intelligent escalation
    llm_result = llm_review(totals, details)
    escalation_task_id = None

    # Create escalation task if LLM recommends it
    if llm_result["decision"] == "ESCALATE":
        escalation_task_id = create_escalation_task(llm_result, totals, details)

    # Append to audit log (include LLM decision)
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG, "a") as logf:
        logf.write(json.dumps({
            "ts": datetime.now().isoformat(),
            "totals": totals,
            "details": details[:10],  # Limit details in log
            "llm_decision": llm_result["decision"],
            "llm_confidence": llm_result["confidence"],
            "llm_reasoning": llm_result["reasoning"],
            "escalation_task_id": escalation_task_id
        }) + "\n")

    return totals, details, llm_result


def main():
    totals, details, llm_result = audit()

    if "--json" in sys.argv:
        output = {
            **totals,
            "llm_decision": llm_result["decision"],
            "llm_confidence": llm_result["confidence"],
            "llm_reasoning": llm_result["reasoning"]
        }
        print(json.dumps(output))
    else:
        ts = datetime.now().isoformat(timespec="seconds")
        print(f"[{ts}] Completion Audit")
        print(f"  Audited: {totals['audited']}")
        print(f"  Verified: {totals['verified']}")
        print(f"  Fake: {totals['fake_found']}")
        print(f"  Re-queued: {totals['requeued']}")
        print(f"  Skipped: {totals['skipped']}")
        if HAS_COMPLETION_STANDARD:
            print(f"  Poor Reports (<70%): {totals['poor_reports']}")
            print(f"  Missing Standard: {totals['missing_report_standard']}")
        print(f"  LLM: {llm_result['decision']} ({llm_result['confidence']}%) - {llm_result['reasoning']}")

        for d in details:
            if d["action"] == "requeued":
                print(f"  [REQUEUED] {d['agent']}/{d['task']} ({d['reason']})")
            elif d["action"] == "verified":
                icon = "+" if d.get("has_result") else "?"
                score_str = f" [{d.get('quality_score', 0)}%]" if d.get('quality_score') is not None else ""
                print(f"  [{icon}] {d['agent']}/{d['task']}{score_str}")
                if d.get("quality_issues") and d.get("quality_score", 100) < 70:
                    for issue in d.get("quality_issues", [])[:2]:
                        print(f"      ⚠ {issue}")


if __name__ == "__main__":
    main()
