#!/usr/bin/env python3
"""
Completion Gate Audit v2 - Three-Tier LLM Fallback

Analyzes task completion with robust fallback hierarchy:
  Tier 1: LLM with validation + retry (2 retries, exponential backoff)
  Tier 2: Template-based heuristics with same validation
  Tier 3: Permissive pass-through (50% completion, logs warning)

Circuit breaker prevents cascade failures when LLM is degraded.

Usage:
    from completion_gate_audit import completion_gate_audit_v2, AuditResultV2

    result = completion_gate_audit_v2(task_file, agent)
    if not result.can_complete:
        create_followup_tasks_v2(result, task_metadata)
"""
from __future__ import annotations

import os
import re
import json
import time
import uuid
import random
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Tuple

# Add scripts dir to path for imports
sys_path_insert = os.path.dirname(os.path.abspath(__file__))
if sys_path_insert not in os.sys.path:
    os.sys.path.insert(0, sys_path_insert)

from kurultai_paths import AGENTS_DIR, TASK_LEDGER, VALID_AGENTS
from kurultai_ledger import append_ledger

# Gate configuration
GATE_THRESHOLD_PERCENT = 90
MAX_FOLLOWUPS_PER_AUDIT = 5
MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 1.0  # seconds
CIRCUIT_BREAKER_THRESHOLD = 0.10  # 10% failure rate
CIRCUIT_BREAKER_COOLDOWN_MINUTES = 10  # Reduced from 30 - transient API failures don't need long blocks

# Audit log directory
AUDIT_LOG_DIR = Path(AGENTS_DIR) / "main" / "logs" / "gate-audits"
CIRCUIT_STATE_FILE = AUDIT_LOG_DIR / "circuit-breaker-state.json"

# Valid priorities (VALID_AGENTS imported from kurultai_paths)
VALID_PRIORITIES = {"critical", "high", "normal", "low"}

# Output validation schema (JSON Schema Draft 7 compatible)
AUDIT_RESULT_SCHEMA = {
    "type": "object",
    "required": ["completion_percentage", "can_complete", "required_followups", "optional_improvements"],
    "properties": {
        "completion_percentage": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100
        },
        "can_complete": {"type": "boolean"},
        "required_followups": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "required": ["title", "agent", "priority", "reason"],
                "properties": {
                    "title": {
                        "type": "string",
                        "minLength": 5,
                        "maxLength": 200
                    },
                    "agent": {"type": "string"},
                    "priority": {"type": "string"},
                    "reason": {"type": "string", "minLength": 10}
                }
            }
        },
        "optional_improvements": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "required": ["title", "agent", "priority", "reason"],
                "properties": {
                    "title": {"type": "string"},
                    "agent": {"type": "string"},
                    "priority": {"type": "string"},
                    "reason": {"type": "string"}
                }
            }
        },
        "missing_components": {"type": "array"},
        "quality_issues": {"type": "array"},
        "blockers": {"type": "array"}
    }
}


@dataclass
class AuditResultV2:
    """Result of a completion gate audit v2."""
    original_task: str
    audit_timestamp: str
    audit_version: str
    completion_percentage: int
    can_complete: bool
    missing_components: List[str] = field(default_factory=list)
    quality_issues: List[str] = field(default_factory=list)
    required_followups: List[Dict[str, str]] = field(default_factory=list)
    optional_improvements: List[Dict[str, str]] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    gate_cycle: int = 0
    audit_tier: str = "unknown"  # "llm", "template", "permissive"
    validation_errors: List[str] = field(default_factory=list)
    retries_performed: int = 0
    audit_fallback: bool = False  # True if tier 3 (permissive) was used

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================
# CIRCUIT BREAKER
# ============================================================

@dataclass
class CircuitBreakerState:
    """State of the LLM circuit breaker."""
    is_open: bool = False
    half_open: bool = False  # Partial recovery state - allows test requests
    failure_count: int = 0
    success_count: int = 0
    consecutive_successes: int = 0  # Track recovery progress
    last_failure_time: Optional[str] = None
    last_state_change: Optional[str] = None  # Track when state changed for logging
    window_start: str = field(default_factory=lambda: datetime.now().isoformat())
    llm_disabled_until: Optional[str] = None
    backoff_multiplier: float = 1.0  # Exponential backoff for repeated failures

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CircuitBreakerState':
        return cls(**data)


def load_circuit_state() -> CircuitBreakerState:
    """Load circuit breaker state from disk."""
    try:
        if CIRCUIT_STATE_FILE.exists():
            with open(CIRCUIT_STATE_FILE, 'r') as f:
                data = json.load(f)
                state = CircuitBreakerState.from_dict(data)

                # Reset window if it's older than 1 hour
                window_start = datetime.fromisoformat(state.window_start)
                if datetime.now() - window_start > timedelta(hours=1):
                    return CircuitBreakerState()

                return state
    except Exception:
        pass
    return CircuitBreakerState()


def save_circuit_state(state: CircuitBreakerState) -> None:
    """Save circuit breaker state to disk."""
    AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CIRCUIT_STATE_FILE, 'w') as f:
        json.dump(state.to_dict(), f, indent=2)


def check_circuit_breaker() -> Tuple[bool, Optional[str]]:
    """
    Check if circuit breaker is open (LLM should be skipped).

    Supports three states:
    - CLOSED (normal): Allow all requests
    - OPEN (blocked): Reject all requests, wait for cooldown
    - HALF_OPEN (recovery): Allow limited test requests

    Returns:
        (is_open, reason_if_open)
    """
    state = load_circuit_state()

    # Check if we're in cooldown period
    if state.llm_disabled_until:
        disabled_until = datetime.fromisoformat(state.llm_disabled_until)
        if datetime.now() < disabled_until:
            remaining = (disabled_until - datetime.now()).total_seconds() / 60
            # Transition to half-open when cooldown expires
            if remaining <= 1 and not state.half_open:
                state.half_open = True
                state.last_state_change = datetime.now().isoformat()
                save_circuit_state(state)
                append_ledger({
                    "event": "CIRCUIT_BREAKER_HALF_OPEN",
                    "ts": datetime.now().isoformat(),
                    "message": "Entering half-open state - allowing test requests"
                })
                return False, None  # Allow test request in half-open
            return True, f"Circuit breaker open - {remaining:.0f} minutes remaining"
        else:
            # Cooldown expired, transition to half-open for recovery
            if not state.half_open:
                state.half_open = True
                state.is_open = False
                state.llm_disabled_until = None
                state.last_state_change = datetime.now().isoformat()
                save_circuit_state(state)
                append_ledger({
                    "event": "CIRCUIT_BREAKER_HALF_OPEN",
                    "ts": datetime.now().isoformat(),
                    "message": "Cooldown expired, entering half-open recovery state"
                })
                return False, None  # Allow test request

    # In half-open state, allow requests to test recovery
    if state.half_open:
        # Check if we've had enough consecutive successes to close
        if state.consecutive_successes >= 3:
            state.half_open = False
            state.is_open = False
            state.failure_count = 0
            state.success_count = 0
            state.consecutive_successes = 0
            state.backoff_multiplier = max(1.0, state.backoff_multiplier / 2)  # Reduce backoff on recovery
            state.last_state_change = datetime.now().isoformat()
            save_circuit_state(state)
            append_ledger({
                "event": "CIRCUIT_BREAKER_CLOSED",
                "ts": datetime.now().isoformat(),
                "message": "Circuit breaker recovered - resuming normal operation"
            })
            return False, None
        return False, None  # Allow test request in half-open

    # Check failure rate
    total_calls = state.failure_count + state.success_count
    if total_calls > 0 and total_calls >= 10:
        failure_rate = state.failure_count / total_calls
        if failure_rate >= CIRCUIT_BREAKER_THRESHOLD:
            # Open the circuit with exponential backoff
            cooldown_minutes = CIRCUIT_BREAKER_COOLDOWN_MINUTES * state.backoff_multiplier
            if not state.is_open:
                state.is_open = True
                state.half_open = False
                state.llm_disabled_until = (datetime.now() + timedelta(minutes=cooldown_minutes)).isoformat()
                state.last_failure_time = datetime.now().isoformat()
                state.last_state_change = datetime.now().isoformat()
                state.backoff_multiplier = min(4.0, state.backoff_multiplier * 1.5)  # Cap at 4x
                save_circuit_state(state)

                # Send alert
                append_ledger({
                    "event": "CIRCUIT_BREAKER_OPENED",
                    "ts": datetime.now().isoformat(),
                    "failure_rate": f"{failure_rate:.1%}",
                    "failure_count": state.failure_count,
                    "disabled_until": state.llm_disabled_until,
                    "cooldown_minutes": cooldown_minutes,
                    "backoff_multiplier": state.backoff_multiplier
                })

            return True, f"Circuit breaker opened - failure rate {failure_rate:.1%}"

    return False, None


def record_llm_success() -> None:
    """Record a successful LLM call. In half-open state, tracks recovery progress."""
    state = load_circuit_state()
    state.success_count += 1

    # In half-open state, track consecutive successes for recovery
    if state.half_open:
        state.consecutive_successes += 1
        if state.consecutive_successes >= 3:
            # Recovery complete - close circuit
            state.half_open = False
            state.is_open = False
            state.failure_count = 0
            state.success_count = 0
            state.consecutive_successes = 0
            state.backoff_multiplier = max(1.0, state.backoff_multiplier / 2)
            state.last_state_change = datetime.now().isoformat()
            append_ledger({
                "event": "CIRCUIT_BREAKER_CLOSED",
                "ts": datetime.now().isoformat(),
                "message": "Circuit breaker recovered after 3 consecutive successes"
            })
    else:
        state.consecutive_successes = 0  # Reset if not in half-open

    save_circuit_state(state)


def record_llm_failure(reason: str) -> None:
    """Record a failed LLM call. In half-open state, reopens circuit immediately."""
    state = load_circuit_state()
    state.failure_count += 1
    state.last_failure_time = datetime.now().isoformat()
    state.consecutive_successes = 0  # Reset recovery progress

    # If in half-open and failure occurs, reopen circuit with increased backoff
    if state.half_open:
        state.half_open = False
        state.is_open = True
        state.backoff_multiplier = min(4.0, state.backoff_multiplier * 2)
        cooldown_minutes = CIRCUIT_BREAKER_COOLDOWN_MINUTES * state.backoff_multiplier
        state.llm_disabled_until = (datetime.now() + timedelta(minutes=cooldown_minutes)).isoformat()
        state.last_state_change = datetime.now().isoformat()
        save_circuit_state(state)
        append_ledger({
            "event": "CIRCUIT_BREAKER_REOPENED",
            "ts": datetime.now().isoformat(),
            "reason": reason,
            "cooldown_minutes": cooldown_minutes,
            "backoff_multiplier": state.backoff_multiplier,
            "message": "Failure during half-open state - circuit reopened with increased backoff"
        })
    else:
        save_circuit_state(state)


# ============================================================
# VALIDATION
# ============================================================

def validate_audit_result(data: Dict[str, Any], default_agent: str) -> Tuple[bool, List[str]]:
    """
    Validate audit result against schema.

    Returns:
        (is_valid, list_of_validation_errors)
    """
    errors = []

    # Check required fields
    for field in ["completion_percentage", "can_complete", "required_followups", "optional_improvements"]:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Validate completion_percentage
    if "completion_percentage" in data:
        try:
            pct = int(data["completion_percentage"])
            if not (0 <= pct <= 100):
                errors.append(f"completion_percentage must be 0-100, got {pct}")
        except (ValueError, TypeError):
            errors.append(f"completion_percentage must be integer, got {data['completion_percentage']}")

    # Validate can_complete
    if "can_complete" in data and not isinstance(data["can_complete"], bool):
        errors.append(f"can_complete must be boolean, got {type(data['can_complete'])}")

    # Validate required_followups
    if "required_followups" in data:
        followups = data["required_followups"]
        if not isinstance(followups, list):
            errors.append("required_followups must be a list")
        else:
            if len(followups) > MAX_FOLLOWUPS_PER_AUDIT:
                errors.append(f"Too many follow-ups: {len(followups)} > {MAX_FOLLOWUPS_PER_AUDIT}")

            for i, fu in enumerate(followups):
                if not isinstance(fu, dict):
                    errors.append(f"required_followups[{i}] must be an object")
                    continue

                # Validate title
                title = fu.get("title", "")
                if not isinstance(title, str) or len(title.strip()) < 5:
                    errors.append(f"required_followups[{i}].title must be >=5 chars, got '{title}'")
                elif len(title) > 200:
                    errors.append(f"required_followups[{i}].title must be <=200 chars")

                # Validate agent
                agent = fu.get("agent", "")
                if agent not in VALID_AGENTS:
                    errors.append(f"required_followups[{i}].agent '{agent}' is not valid. Valid: {VALID_AGENTS}")

                # Validate priority
                priority = fu.get("priority", "")
                if priority not in VALID_PRIORITIES:
                    errors.append(f"required_followups[{i}].priority '{priority}' is not valid")

                # Validate reason
                reason = fu.get("reason", "")
                if not isinstance(reason, str) or len(reason.strip()) < 10:
                    errors.append(f"required_followups[{i}].reason must be >=10 chars")

    # Validate optional_improvements
    if "optional_improvements" in data:
        improvements = data["optional_improvements"]
        if not isinstance(improvements, list):
            errors.append("optional_improvements must be a list")
        elif len(improvements) > 3:
            errors.append(f"Too many improvements: {len(improvements)} > 3")

        for i, imp in enumerate(improvements):
            if isinstance(imp, dict):
                agent = imp.get("agent", "")
                if agent and agent not in VALID_AGENTS:
                    errors.append(f"optional_improvements[{i}].agent '{agent}' is not valid")

    # Fix invalid agents by defaulting to current agent
    if errors:
        for followup in data.get("required_followups", []) + data.get("optional_improvements", []):
            if isinstance(followup, dict) and followup.get("agent") not in VALID_AGENTS:
                followup["agent"] = default_agent

    return len(errors) == 0, errors


# ============================================================
# TIER 1: LLM with Validation + Retry
# ============================================================

# ============================================================
# PROMPT INJECTION DEFENSE
# ============================================================

def sanitize_for_llm(content: str, max_len: int = 2000) -> str:
    """
    Sanitize content before passing to LLM to prevent prompt injection.

    Removes:
    - Control characters (except whitespace: newline, tab, space)
    - LLM control tokens (SYSTEM:, IGNORE:, etc.)
    - Markdown code fences that could confuse the LLM
    - Special tokens used by various LLM providers

    Args:
        content: The content to sanitize
        max_len: Maximum length (will truncate)

    Returns:
        Sanitized string safe for LLM consumption
    """
    if not content:
        return ""

    # Truncate first to avoid processing huge strings
    content = content[:max_len]

    # Remove control characters (keep printable + whitespace)
    sanitized = ''.join(c for c in content if c.isprintable() or c in '\n\t ')

    # LLM injection tokens to remove (case-insensitive matching)
    injection_patterns = [
        r'\bSYSTEM\s*:',
        r'\bIGNORE\s*:',
        r'\bIGNORE\s+ALL\s+PREVIOUS\s+INSTRUCTIONS\b',
        r'\bASSISTANT\s*:',
        r'\bUSER\s*:',
        r'\bINSTRUCTION\s*:',
        r'<\|',
        r'\|>',
        r'<\[/?',
        r'###\s*SYSTEM',
        r'###\s*INSTRUCTION',
        r'```system',
        r'```instruction',
    ]

    for pattern in injection_patterns:
        sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)

    # Remove null bytes and ANSI escape sequences
    sanitized = sanitized.replace('\x00', '')
    sanitized = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', sanitized)

    # Collapse multiple spaces/newlines
    sanitized = re.sub(r' {3,}', '  ', sanitized)
    sanitized = re.sub(r'\n{4,}', '\n\n\n', sanitized)

    return sanitized.strip()


def extract_yaml_frontmatter(content: str) -> Dict[str, Any]:
    """Extract YAML frontmatter from task content."""
    metadata = {}
    if not content.startswith('---'):
        return metadata

    lines = content.split('\n')
    in_frontmatter = False
    frontmatter_lines = []

    for i, line in enumerate(lines):
        if i == 0 and line.strip() == '---':
            in_frontmatter = True
            continue
        if in_frontmatter and line.strip() == '---':
            break
        if in_frontmatter:
            frontmatter_lines.append(line)

    for line in frontmatter_lines:
        if ':' in line:
            key, _, value = line.partition(':')
            metadata[key.strip()] = value.strip().strip('"\'').strip()

    return metadata


def extract_body_after_frontmatter(content: str) -> str:
    """Extract the body content after YAML frontmatter."""
    if not content.startswith('---'):
        return content

    lines = content.split('\n')
    found_close = False
    body_start = 0

    for i, line in enumerate(lines):
        if i > 0 and line.strip() == '---':
            found_close = True
            body_start = i + 1
            break

    if not found_close:
        return content

    return '\n'.join(lines[body_start:])


def extract_execution_output(content: str) -> str:
    """Extract execution output section from task content."""
    marker = '## Execution Output'
    if marker not in content:
        return ""

    parts = content.rsplit(marker, 1)
    if len(parts) < 2:
        return ""

    return parts[1].strip()


def call_llm_audit_with_validation(
    task_id: str,
    task_title: str,
    task_body: str,
    execution_output: str,
    default_agent: str
) -> Tuple[Optional[Dict[str, Any]], int, List[str]]:
    """
    Call LLM for audit with validation and retry logic.

    Returns:
        (validated_result_or_None, retries_performed, validation_errors)
    """
    # Check circuit breaker first
    is_open, reason = check_circuit_breaker()
    if is_open:
        print(f"[completion_gate_v2] LLM skipped: {reason}")
        return None, 0, [f"Circuit breaker: {reason}"]

    try:
        import openai
    except ImportError:
        return None, 0, ["OpenAI module not available"]

    # Check for API credentials
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None, 0, ["No API credentials found"]

    # SECURITY: Sanitize all user-provided content to prevent prompt injection
    task_id_safe = sanitize_for_llm(task_id, max_len=100)
    task_title_safe = sanitize_for_llm(task_title, max_len=200)
    task_body_safe = sanitize_for_llm(task_body, max_len=2000)
    exec_output_safe = sanitize_for_llm(execution_output, max_len=5000)

    agents_list = ", ".join(sorted(VALID_AGENTS))
    priorities_list = ", ".join(sorted(VALID_PRIORITIES))

    audit_prompt = f"""You are a Completion Auditor. Analyze if this task is truly complete.

TASK ID: {task_id_safe}
TASK TITLE: {task_title_safe}

ORIGINAL REQUIREMENTS:
{task_body_safe}

EXECUTION OUTPUT (what was delivered):
{exec_output_safe}

Audit the task completion:

1. REQUIREMENTS_COVERAGE: What % of requirements were met? (0-100)
2. MISSING_COMPONENTS: List specific missing items
3. QUALITY_ISSUES: List any quality problems (tests missing, docs incomplete, etc.)
4. DEPENDENCIES_NEEDED: List dependencies that should be created
5. IMPROVEMENTS_SUGGESTED: Optional improvements for better quality
6. RESOLUTION_SECTION: REQUIRED for all substantive completions (>=100 chars). Must include "## Resolution" heading.

IMPORTANT CONSTRAINTS:
- Valid agents: {agents_list}
- Valid priorities: {priorities_list}
- Maximum 5 required follow-ups
- Maximum 3 optional improvements
- Follow-up titles must be 5-200 characters
- Reasons must be >=10 characters

CRITICAL: If execution output >= 100 chars but lacks "## Resolution" heading, add "Missing ## Resolution section" to MISSING_COMPONENTS (not quality_issues) and set can_complete=false.

Output ONLY valid JSON (no markdown, no code fence):
{{
  "completion_percentage": 85,
  "can_complete": false,
  "missing_components": ["Credit pack display not fixed", "Missing ## Resolution section"],
  "quality_issues": ["No tests written"],
  "required_followups": [
    {{"title": "Fix credit pack display", "agent": "temujin", "priority": "high", "reason": "UX bug affects checkout flow"}},
    {{"title": "Add resolution section", "agent": "temujin", "priority": "high", "reason": "Missing ## Resolution heading"}}
  ],
  "optional_improvements": [
    {{"title": "Add analytics", "agent": "mongke", "priority": "normal", "reason": "Track feature usage"}}
  ],
  "blockers": []
}}"""

    validation_errors = []

    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            backoff = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
            time.sleep(backoff)

        try:
            client = openai.OpenAI(api_key=api_key)
            # Use different seed for each retry
            seed = random.randint(1, 100000) if attempt > 0 else None

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": audit_prompt}],
                max_tokens=1000,
                temperature=0.3,
                seed=seed
            )

            result_text = response.choices[0].message.content.strip()

            # Remove potential markdown code fences
            if result_text.startswith('```'):
                result_text = re.sub(r'^```(?:json)?\s*', '', result_text)
                result_text = re.sub(r'\s*```$', '', result_text)

            # Parse JSON
            try:
                result_data = json.loads(result_text)
            except json.JSONDecodeError as e:
                validation_errors.append(f"Attempt {attempt + 1}: JSON parse error - {e}")
                record_llm_failure(f"JSON parse error: {e}")
                continue

            # Validate against schema
            is_valid, errors = validate_audit_result(result_data, default_agent)
            if not is_valid:
                validation_errors.extend([f"Attempt {attempt + 1}: {err}" for err in errors])
                record_llm_failure(f"Validation failed: {errors[0] if errors else 'unknown'}")
                continue

            # Success!
            record_llm_success()
            return result_data, attempt, []

        except Exception as e:
            validation_errors.append(f"Attempt {attempt + 1}: API error - {e}")
            record_llm_failure(f"API error: {e}")
            continue

    # All retries exhausted
    return None, MAX_RETRIES, validation_errors


# ============================================================
# TIER 2: Template-Based Heuristics
# ============================================================

def fallback_template_audit_v2(
    task_content: Dict[str, Any],
    execution_output: str,
    default_agent: str
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Fallback audit using heuristic template matching with validation.

    Returns:
        (audit_result_dict, validation_errors)
    """
    missing = []
    improvements = []
    validation_errors = []

    task_title = task_content.get('title', '')
    task_body = task_content.get('body', '')

    # Pattern 1: TODO/FIXME in output
    if re.search(r'\b(TODO|FIXME|XXX|HACK|WIP)\b', execution_output, re.I):
        missing.append("Incomplete items marked TODO/FIXME/WIP in code")

    # Pattern 2: Empty or very short output
    output_lines = [l for l in execution_output.split('\n') if l.strip() and not l.strip().startswith('**')]
    if len(output_lines) < 5:
        missing.append("Insufficient execution output")

    # Pattern 3: Test required but not mentioned
    if 'test' in task_title.lower() or 'test' in task_body.lower():
        if 'test' not in execution_output.lower():
            missing.append("Tests not written")

    # Pattern 4: Error handling not mentioned for endpoints/APIs
    if 'endpoint' in execution_output.lower() or 'api' in execution_output.lower():
        if 'error' not in execution_output.lower() and 'catch' not in execution_output.lower():
            improvements.append("Add error handling")

    # Pattern 5: No documentation mentioned
    if 'implement' in task_title.lower() or 'add' in task_title.lower():
        if 'doc' not in execution_output.lower():
            improvements.append("Add documentation")

    # Pattern 6: Task says "implement" but no code shown
    if 'implement' in task_title.lower():
        has_code = any(keyword in execution_output for keyword in ['```', 'def ', 'class ', 'function ', 'const ', 'let '])
        if not has_code:
            missing.append("No code implementation shown")

    # Pattern 7: Missing resolution section (required for substantive completions)
    # CRITICAL: Resolution section is a BLOCKER matching /horde-review PRIORITY_FIX
    # 9/10 reports were missing resolution sections, degrading completion quality tracking
    if len(execution_output.strip()) >= 100:
        has_resolution = (
            "## Resolution" in execution_output
            or "**Status:**" in execution_output
            or "## Result" in execution_output
            or "## Summary" in execution_output
        )
        if not has_resolution:
            missing.append("Missing ## Resolution section - add ## Resolution heading with What Was Done subsection")

    can_complete = len(missing) == 0 and len(improvements) == 0
    completion_percentage = 100 if can_complete else max(50, 100 - len(missing) * 15 - len(improvements) * 5)

    result = {
        "completion_percentage": completion_percentage,
        "can_complete": can_complete,
        "missing_components": missing,
        "quality_issues": [],
        "required_followups": [
            {"title": m[:200], "agent": default_agent, "priority": "high", "reason": f"Auto-detected: {m}"}
            for m in missing[:MAX_FOLLOWUPS_PER_AUDIT]
        ],
        "optional_improvements": [
            {"title": i[:200], "agent": default_agent, "priority": "normal", "reason": f"Auto-suggested: {i}"}
            for i in improvements[:3]
        ],
        "blockers": []
    }

    # Validate the template result
    is_valid, errors = validate_audit_result(result, default_agent)
    if not is_valid:
        validation_errors.extend([f"Template validation: {err}" for err in errors])
        # Fix critical issues
        for fu in result.get("required_followups", []):
            if fu.get("agent") not in VALID_AGENTS:
                fu["agent"] = default_agent

    return result, validation_errors


# ============================================================
# TIER 3: Permissive Pass-Through
# ============================================================

def permissive_pass_through(
    task_id: str,
    default_agent: str,
    tier_validation_errors: List[str]
) -> Dict[str, Any]:
    """
    Permissive pass-through when both LLM and template fail.
    Returns conservative 75% completion - requires manual review before completion.
    """
    # Log critical warning
    append_ledger({
        "event": "GATE_AUDIT_PERMISSIVE_FALLBACK",
        "ts": datetime.now().isoformat(),
        "task_id": task_id,
        "agent": default_agent,
        "validation_errors": tier_validation_errors[:5],  # First 5 errors
        "warning": "All audit tiers failed - using permissive pass-through at 75% threshold"
    })

    return {
        "completion_percentage": 75,  # Raised from 50 - requires more substantive work
        "can_complete": False,  # Require manual review - audit system failed
        "missing_components": [],
        "quality_issues": ["Audit system unavailable - manual review required"],
        "required_followups": [
            {
                "title": "Manual review required - audit unavailable",
                "agent": default_agent,
                "priority": "high",
                "reason": "Completion gate audit system was unavailable - human must verify work before marking complete"
            }
        ],
        "optional_improvements": [],
        "blockers": []
    }


# ============================================================
# MAIN AUDIT FUNCTION
# ============================================================

def completion_gate_audit_v2(task_file: str, agent: str) -> AuditResultV2:
    """
    Analyze task completion with three-tier fallback.

    Args:
        task_file: Path to the task file (.executing.md)
        agent: Agent who executed the task

    Returns: AuditResultV2 with completion status and follow-up tasks
    """
    task_path = Path(task_file)
    audit_tier = "unknown"
    validation_errors = []
    retries_performed = 0
    audit_fallback = False

    if not task_path.exists():
        return AuditResultV2(
            original_task="unknown",
            audit_timestamp=datetime.now().isoformat(),
            audit_version="2.0",
            completion_percentage=0,
            can_complete=False,
            blockers=["Task file not found"],
            audit_tier="error",
            validation_errors=["File not found"]
        )

    # Read task content
    try:
        with open(task_path, 'r') as f:
            content = f.read()
    except Exception as e:
        return AuditResultV2(
            original_task="unknown",
            audit_timestamp=datetime.now().isoformat(),
            audit_version="2.0",
            completion_percentage=0,
            can_complete=False,
            blockers=[f"Failed to read task file: {e}"],
            audit_tier="error",
            validation_errors=[f"Read error: {e}"]
        )

    # Parse frontmatter and body
    metadata = extract_yaml_frontmatter(content)
    task_id = metadata.get('task_id', task_path.stem)
    task_title = metadata.get('title', task_path.stem)
    task_body = extract_body_after_frontmatter(content)
    execution_output = extract_execution_output(content)

    # Tier 1: LLM with validation + retry
    audit_data = None
    llm_result, retries, errors = call_llm_audit_with_validation(
        task_id, task_title, task_body, execution_output, agent
    )
    validation_errors.extend(errors)
    retries_performed = retries

    if llm_result is not None:
        audit_data = llm_result
        audit_tier = "llm"
    else:
        # Tier 2: Template-based heuristics
        template_result, template_errors = fallback_template_audit_v2(
            {'agent': agent, 'title': task_title, 'body': task_body},
            execution_output,
            agent
        )
        validation_errors.extend(template_errors)

        if template_errors:
            # Tier 3: Permissive pass-through
            audit_data = permissive_pass_through(task_id, agent, validation_errors)
            audit_tier = "permissive"
            audit_fallback = True
        else:
            audit_data = template_result
            audit_tier = "template"

    # Enforce gate rules
    if audit_data["completion_percentage"] < GATE_THRESHOLD_PERCENT and audit_data.get("required_followups"):
        audit_data["can_complete"] = False

    if audit_data.get("blockers"):
        audit_data["can_complete"] = False

    if audit_data["completion_percentage"] >= 100:
        audit_data["can_complete"] = True
        audit_data["required_followups"] = []

    # Limit number of follow-ups (safety check)
    if len(audit_data.get("required_followups", [])) > MAX_FOLLOWUPS_PER_AUDIT:
        audit_data["required_followups"] = audit_data["required_followups"][:MAX_FOLLOWUPS_PER_AUDIT]

    # Build result
    result = AuditResultV2(
        original_task=task_id,
        audit_timestamp=datetime.now().isoformat(),
        audit_version="2.0",
        completion_percentage=audit_data["completion_percentage"],
        can_complete=audit_data["can_complete"],
        missing_components=audit_data.get("missing_components", []),
        quality_issues=audit_data.get("quality_issues", []),
        required_followups=audit_data.get("required_followups", []),
        optional_improvements=audit_data.get("optional_improvements", []),
        blockers=audit_data.get("blockers", []),
        gate_cycle=int(metadata.get('gate_cycle', 0)),
        audit_tier=audit_tier,
        validation_errors=validation_errors,
        retries_performed=retries_performed,
        audit_fallback=audit_fallback
    )

    # Save audit log
    save_audit_log_v2(result, task_path)

    # Log if permissive fallback was used
    if audit_fallback:
        append_ledger({
            "event": "GATE_AUDIT_TIER3_USED",
            "ts": datetime.now().isoformat(),
            "task_id": task_id,
            "tier": audit_tier,
            "completion_percentage": result.completion_percentage,
            "warning": "Permissive pass-through used"
        })

    return result


def save_audit_log_v2(result: AuditResultV2, task_path: Path) -> str:
    """Save audit result v2 to JSON log file."""
    AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = AUDIT_LOG_DIR / f"{result.original_task}-{timestamp}-v2.json"

    with open(log_file, 'w') as f:
        json.dump(result.to_dict(), f, indent=2)

    return str(log_file)


def create_followup_tasks_v2(audit_result: AuditResultV2, original_task: Dict[str, Any], original_file: str) -> List[str]:
    """
    Create follow-up tasks from v2 audit results.

    Args:
        audit_result: The audit result with follow-up specifications
        original_task: Metadata from the original task
        original_file: Path to the original task file

    Returns: List of created task file paths
    """
    created_tasks = []
    original_task_id = audit_result.original_task
    original_agent = original_task.get('agent', 'temujin')
    audit_ref = save_audit_log_v2(audit_result, Path(original_file))

    for i, followup in enumerate(audit_result.required_followups):
        task_id = f"gate-{original_task_id[:8]}-{uuid.uuid4().hex[:8]}"
        priority = followup.get("priority", "high")
        target_agent = followup.get("agent", original_agent)

        # Validate agent and priority
        if target_agent not in VALID_AGENTS:
            target_agent = original_agent
        if priority not in VALID_PRIORITIES:
            priority = "high"

        # Build task frontmatter
        depth = original_task.get('depth', 0) + 1

        frontmatter = f"""---
agent: {target_agent}
priority: {priority}
created: {datetime.now().isoformat()}
source: completion-gate-v2
depth: {depth}
task_id: {task_id}
parent_task: {original_task_id}
completion_gate: true
gate_audit_ref: {audit_ref}
gate_required: true
gate_version: v2
bucket: TODAY
domain: implementation
timeout: 3600
skill_hint: null
---
"""

        # Build task body
        body = f"""# Task: {followup['title']}

This is a **completion gate follow-up task (v2)** for parent: `{original_task_id}`

## Parent Context

The parent task identified that the following item is incomplete or missing:
- **Issue:** {followup['reason']}
- **Original completion:** {audit_result.completion_percentage}%
- **Audit tier:** {audit_result.audit_tier}

This follow-up must be completed before the parent task can be marked as fully complete.

## What to Do

1. Analyze the parent task to understand context
2. Implement the required fix or improvement
3. Test your changes
4. Update any relevant documentation

## Audit Reason

> {followup['reason']}

## Success Criteria

- [ ] Fix/improvement implemented and tested
- [ ] No regressions introduced
- [ ] Documentation updated if applicable

---
_Generated by completion-gate-audit-v2 at {datetime.now().isoformat()}_
"""

        # Write task file
        task_dir = Path(AGENTS_DIR) / target_agent / "tasks"
        task_dir.mkdir(parents=True, exist_ok=True)
        task_path = task_dir / f"{priority}-{task_id}.md"

        with open(task_path, 'w') as f:
            f.write(frontmatter + body)

        created_tasks.append(str(task_path))

        # Track in Neo4j
        try:
            from neo4j_task_tracker import get_tracker
            tracker = get_tracker()
            tracker.create_task_full(
                agent=target_agent,
                title=followup['title'],
                body=body,
                priority=priority,
                source="completion-gate-v2",
                depth=depth,
                parent_id=original_task_id,
                skill_hint=None
            )
            tracker.update_gate_status(task_id, "PENDING", gate_required=True, parent_task=original_task_id)
        except Exception as e:
            print(f"[completion_gate_v2] Neo4j update failed (non-fatal): {e}")

    # Log follow-up creation
    if created_tasks:
        append_ledger({
            "event": "GATE_FOLLOWUPS_CREATED_V2",
            "ts": datetime.now().isoformat(),
            "original_task": original_task_id,
            "followup_count": len(created_tasks),
            "followup_tasks": [os.path.basename(t) for t in created_tasks],
            "completion_percentage": audit_result.completion_percentage,
            "audit_tier": audit_result.audit_tier
        })

    return created_tasks


def should_run_gate(task_file: str) -> bool:
    """
    Determine if completion gate should run for a task.
    """
    try:
        with open(task_file, 'r') as f:
            content = f.read(2000)

        if re.search(r'^completion_gate:\s*false', content, re.MULTILINE):
            return False
        if re.search(r'^completion_gate_optout:\s*true', content, re.MULTILINE):
            return False

        depth_match = re.search(r'^depth:\s*(\d+)', content, re.MULTILINE)
        if depth_match and int(depth_match.group(1)) > 2:
            return False

        return True
    except Exception:
        return True


# ============================================================
# BACKWARD COMPATIBILITY ALIASES
# ============================================================
# Provide v1 function names for backward compatibility with existing code
completion_gate_audit = completion_gate_audit_v2
save_audit_result = save_audit_log_v2
create_followup_tasks = create_followup_tasks_v2

# ============================================================
# CLI INTERFACE
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Completion Gate Audit v2 - Three-Tier Fallback")
    parser.add_argument("task_file", nargs='?', help="Path to task file (.executing.md)")
    parser.add_argument("--agent", default="temujin", help="Agent who executed the task")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--no-gate-check", action="store_true", help="Skip should_run_gate check")
    parser.add_argument("--circuit-status", action="store_true", help="Show circuit breaker status")
    parser.add_argument("--circuit-reset", action="store_true", help="Reset circuit breaker")
    parser.add_argument("--circuit-half-open", action="store_true", help="Manually transition circuit to half-open state for recovery testing")
    parser.add_argument("--test", action="store_true", help="Run test mode")
    parser.add_argument("--validate-only", action="store_true", help="Run validation tests only (no task file needed)")

    args = parser.parse_args()

    # Validation-only test mode (no task file needed)
    if args.validate_only:
        print("=== Completion Gate Audit v2 - Validation Tests ===\n")

        # Test 1: Valid data
        print("Test 1: Valid audit data")
        test_data = {
            "completion_percentage": 85,
            "can_complete": False,
            "required_followups": [
                {"title": "Test follow-up with sufficient length", "agent": "temujin", "priority": "high", "reason": "This is a test reason that meets minimum length"}
            ],
            "optional_improvements": []
        }
        is_valid, errors = validate_audit_result(test_data, "temujin")
        print(f"  Result: {'PASS' if is_valid else 'FAIL'}")
        if errors:
            for err in errors:
                print(f"    - {err}")

        # Test 2: Invalid agent name
        print("\nTest 2: Invalid agent name (should be rejected)")
        test_data2 = {
            "completion_percentage": 85,
            "can_complete": False,
            "required_followups": [
                {"title": "Test follow-up", "agent": "hallucinated_agent", "priority": "high", "reason": "This is a test reason"}
            ],
            "optional_improvements": []
        }
        is_valid2, errors2 = validate_audit_result(test_data2, "temujin")
        print(f"  Result: {'PASS' if not is_valid2 else 'UNEXPECTED PASS'}")
        if errors2:
            for err in errors2:
                print(f"    - {err}")

        # Test 3: Title too short
        print("\nTest 3: Title too short (should be rejected)")
        test_data3 = {
            "completion_percentage": 85,
            "can_complete": False,
            "required_followups": [
                {"title": "Bad", "agent": "temujin", "priority": "high", "reason": "This is a test reason"}
            ],
            "optional_improvements": []
        }
        is_valid3, errors3 = validate_audit_result(test_data3, "temujin")
        print(f"  Result: {'PASS' if not is_valid3 else 'UNEXPECTED PASS'}")
        if errors3:
            for err in errors3[:3]:
                print(f"    - {err}")

        # Test 4: Too many follow-ups
        print("\nTest 4: Too many follow-ups (should be rejected)")
        test_data4 = {
            "completion_percentage": 50,
            "can_complete": False,
            "required_followups": [
                {"title": f"Follow-up {i}", "agent": "temujin", "priority": "high", "reason": f"Reason {i} that is long enough"}
                for i in range(7)  # 7 > MAX_FOLLOWUPS_PER_AUDIT (5)
            ],
            "optional_improvements": []
        }
        is_valid4, errors4 = validate_audit_result(test_data4, "temujin")
        print(f"  Result: {'PASS' if not is_valid4 else 'UNEXPECTED PASS'}")
        if errors4:
            for err in errors4[:2]:
                print(f"    - {err}")

        # Test 5: Circuit breaker status
        print("\nTest 5: Circuit breaker status")
        state = load_circuit_state()
        print(f"  Is Open: {state.is_open}")
        print(f"  Failure Count: {state.failure_count}")
        print(f"  Success Count: {state.success_count}")

        print("\n=== All Tests Complete ===")
        exit(0)

    # Circuit breaker management
    if args.circuit_status:
        state = load_circuit_state()
        print("=== CIRCUIT BREAKER STATUS ===")
        print(f"State: {'OPEN' if state.is_open else 'HALF-OPEN' if state.half_open else 'CLOSED'}")
        print(f"Is Open: {state.is_open}")
        print(f"Half Open: {state.half_open}")
        print(f"Failure Count: {state.failure_count}")
        print(f"Success Count: {state.success_count}")
        print(f"Consecutive Successes: {state.consecutive_successes}")
        print(f"Backoff Multiplier: {state.backoff_multiplier}x")
        total = state.failure_count + state.success_count
        if total > 0:
            print(f"Failure Rate: {state.failure_count / total:.1%}")
        print(f"Window Start: {state.window_start}")
        if state.last_state_change:
            print(f"Last State Change: {state.last_state_change}")
        if state.llm_disabled_until:
            print(f"Disabled Until: {state.llm_disabled_until}")
        exit(0)

    if args.circuit_reset:
        CIRCUIT_STATE_FILE.unlink(missing_ok=True)
        print("Circuit breaker reset")
        exit(0)

    if args.circuit_half_open:
        state = load_circuit_state()
        state.half_open = True
        state.is_open = False
        state.llm_disabled_until = None
        state.consecutive_successes = 0
        state.last_state_change = datetime.now().isoformat()
        save_circuit_state(state)
        append_ledger({
            "event": "CIRCUIT_BREAKER_HALF_OPEN",
            "ts": datetime.now().isoformat(),
            "message": "Manual transition to half-open state"
        })
        print("Circuit breaker transitioned to half-open state - test requests allowed")
        exit(0)

    # Test mode
    if args.test:
        print("Running completion gate audit v2 tests...")
        # Run validation tests
        test_data = {
            "completion_percentage": 85,
            "can_complete": False,
            "required_followups": [
                {"title": "Test follow-up", "agent": "temujin", "priority": "high", "reason": "This is a test reason"}
            ],
            "optional_improvements": []
        }
        is_valid, errors = validate_audit_result(test_data, "temujin")
        print(f"Validation test: {'PASS' if is_valid else 'FAIL'}")
        if errors:
            for err in errors:
                print(f"  - {err}")

        # Test invalid agent
        test_data["required_followups"][0]["agent"] = "invalid_agent"
        is_valid, errors = validate_audit_result(test_data, "temujin")
        print(f"Invalid agent test: {'PASS' if not is_valid else 'FAIL'}")
        exit(0)

    # Normal audit - requires task_file
    if not args.task_file:
        parser.print_help()
        print("\nError: task_file is required for audit mode")
        exit(1)

    if not args.no_gate_check and not should_run_gate(args.task_file):
        result = {"skipped": True, "reason": "Task opted out of completion gate"}
        print(json.dumps(result) if args.json else "Gate skipped: task opted out")
        exit(0)

    result = completion_gate_audit_v2(args.task_file, args.agent)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Completion Gate Audit v2: {result.original_task}")
        print(f"  Completion: {result.completion_percentage}%")
        print(f"  Can Complete: {result.can_complete}")
        print(f"  Audit Tier: {result.audit_tier}")
        if result.retries_performed > 0:
            print(f"  Retries: {result.retries_performed}")
        if result.validation_errors:
            print(f"  Validation Errors: {len(result.validation_errors)}")
        if result.audit_fallback:
            print(f"  WARNING: Permissive fallback used - manual review recommended")
        if result.missing_components:
            print(f"  Missing: {', '.join(result.missing_components)}")
        if result.required_followups:
            print(f"  Follow-ups Required: {len(result.required_followups)}")
            for f in result.required_followups:
                print(f"    - {f['title']} ({f['agent']}, {f['priority']})")
        if result.blockers:
            print(f"  Blockers: {', '.join(result.blockers)}")

    exit(0 if result.can_complete else 1)
