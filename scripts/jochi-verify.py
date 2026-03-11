#!/usr/bin/env python3
"""
Jochi's Verification Helper

ENFORCEMENT RULE (jochi behavioral rule):
WHEN claiming a fix is complete THEN verify by checking file size/content or running test command

Common verifications:
- Session reset: python jochi-verify.py --session <agent>
- Model fix: python jochi-verify.py --model <agent>  (READS settings.json, not file size!)
- File size: python jochi-verify.py --file /path/to/file --expected-size 2
- JSON value: python jochi-verify.py --json-file config.json --key model --contains "claude"
- Command output: python jochi-verify.py --command "pytest" --expect "0 failed"

Enforces the verification protocol:
WHEN claiming a fix is complete THEN verify by checking file size/content or running test command

IMPORTANT: Model verification MUST use --model, NOT file size checking.
File size cannot detect model drift - use --model to read actual settings.json.

Usage:
    python jochi-verify.py --model temujin
    python jochi-verify.py --file /path/to/file --expected-size 2
    python jochi-verify.py --command "pytest" --expect "0 failed"
    python jochi-verify.py --json-file /path/to/config.json --key "model" --contains "claude"
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def verify_file_size(path: str, expected_size: int) -> tuple[bool, str]:
    """Verify file has exact expected size in bytes."""
    if not os.path.exists(path):
        return False, f"FAIL: File does not exist: {path}"
    actual = os.path.getsize(path)
    if actual == expected_size:
        return True, f"OK: {path} is {actual} bytes (expected {expected_size})"
    return False, f"FAIL: {path} is {actual} bytes, expected {expected_size}"


def verify_file_contains(path: str, content: str) -> tuple[bool, str]:
    """Verify file contains expected content."""
    if not os.path.exists(path):
        return False, f"FAIL: File does not exist: {path}"
    try:
        text = Path(path).read_text()
        if content in text:
            return True, f"OK: {path} contains '{content}'"
        return False, f"FAIL: {path} does not contain '{content}'"
    except Exception as e:
        return False, f"FAIL: Could not read {path}: {e}"


def verify_json_key(path: str, key: str, contains: str = None, equals: str = None) -> tuple[bool, str]:
    """Verify JSON file has key with expected value."""
    if not os.path.exists(path):
        return False, f"FAIL: File does not exist: {path}"
    try:
        data = json.loads(Path(path).read_text())
        if key not in data:
            return False, f"FAIL: Key '{key}' not found in {path}"
        value = str(data[key])
        if contains and contains in value:
            return True, f"OK: {key} contains '{contains}' (value: {value})"
        if equals and value == equals:
            return True, f"OK: {key} equals '{equals}'"
        if contains:
            return False, f"FAIL: {key}='{value}' does not contain '{contains}'"
        if equals:
            return False, f"FAIL: {key}='{value}' does not equal '{equals}'"
        return True, f"OK: Key '{key}' exists with value: {value}"
    except json.JSONDecodeError as e:
        return False, f"FAIL: Invalid JSON in {path}: {e}"
    except Exception as e:
        return False, f"FAIL: Error reading {path}: {e}"


def verify_command(cmd: str, expect: str) -> tuple[bool, str]:
    """Run command and check output contains expected string."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        if expect in output:
            return True, f"OK: Command output contains '{expect}'"
        return False, f"FAIL: Command output does not contain '{expect}'\nOutput: {output[:500]}"
    except subprocess.TimeoutExpired:
        return False, f"FAIL: Command timed out after 30s"
    except Exception as e:
        return False, f"FAIL: Command error: {e}"


def verify_session_reset(agent: str) -> tuple[bool, str]:
    """Verify agent session is reset (empty JSON object)."""
    path = f"/Users/kublai/.openclaw/agents/{agent}/sessions/sessions.json"
    return verify_file_size(path, 2)


def verify_model(agent: str, expected_model: str = None) -> tuple[bool, str]:
    """
    Verify agent's actual configured model in settings.json.

    This is the CORRECT way to verify model fixes - NOT file size.
    Reads the model field directly from settings.json and optionally
    checks sessions.json modelProvider for consistency.

    Args:
        agent: Agent name (temujin, mongke, etc.)
        expected_model: Optional expected model (default: claude-opus-4-6)

    Returns:
        (success, message) tuple
    """
    agents_base = Path("/Users/kublai/.openclaw/agents")
    settings_file = agents_base / agent / ".claude" / "settings.json"
    session_file = agents_base / agent / "sessions" / "sessions.json"

    # Valid Claude models (sk-ant- API keys required)
    valid_models = {"claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"}

    if not settings_file.exists():
        return False, f"FAIL: settings.json not found for {agent}"

    # Read configured model from settings.json
    try:
        settings_data = json.loads(Path(settings_file).read_text())
    except json.JSONDecodeError as e:
        return False, f"FAIL: Invalid JSON in settings.json: {e}"

    # Check multiple possible locations for the model setting
    configured_model = (
        settings_data.get("model") or
        settings_data.get("env", {}).get("ANTHROPIC_MODEL") or
        settings_data.get("apiSettings", {}).get("model") or
        settings_data.get("mcp", {}).get("defaultModel")
    )

    if not configured_model:
        return False, f"FAIL: No model field found in settings.json"

    # Check for proxy models (always invalid - indicate credential drift)
    proxy_indicators = ["kimi", "qwen", "glm", "dashscope", "alibaba"]
    is_proxy = any(proxy in configured_model.lower() for proxy in proxy_indicators)

    if is_proxy:
        return False, f"FAIL: Proxy model detected: {configured_model} ( Anthropic API key required)"

    # Validate it's a real Claude model
    if configured_model not in valid_models:
        return False, f"FAIL: Invalid model '{configured_model}' (not in {valid_models})"

    # Check API token format if available
    token = settings_data.get("env", {}).get("ANTHROPIC_AUTH_TOKEN", "")
    if token and not token.startswith("sk-ant-"):
        return False, f"FAIL: Invalid API token prefix (got {token[:10]}..., need sk-ant-)"

    # Optional: Check session consistency
    session_model = None
    if session_file.exists():
        try:
            session_data = json.loads(Path(session_file).read_text())
            if session_data and isinstance(session_data, dict):
                for sess_id, sess in session_data.items():
                    if isinstance(sess, dict):
                        session_model = (
                            sess.get("systemPromptReport", {}).get("model") or
                            sess.get("model") or
                            sess.get("modelProvider")
                        )
                        if session_model:
                            break
        except Exception:
            pass

    # Build success message
    msg_parts = [f"OK: {agent} configured_model={configured_model}"]
    if session_model:
        msg_parts.append(f"session_model={session_model}")
        if session_model != configured_model:
            return False, f"FAIL: Session model '{session_model}' != configured '{configured_model}' (session not reset)"
    else:
        msg_parts.append("session=empty")

    return True, " | ".join(msg_parts)


def main():
    parser = argparse.ArgumentParser(description="Jochi's verification helper")
    parser.add_argument("--file", help="File path to verify size")
    parser.add_argument("--expected-size", type=int, help="Expected file size in bytes")
    parser.add_argument("--contains", help="Expected content in file")
    parser.add_argument("--json-file", help="JSON file path")
    parser.add_argument("--key", help="JSON key to check")
    parser.add_argument("--equals", help="JSON value must equal")
    parser.add_argument("--command", help="Command to run")
    parser.add_argument("--expect", help="Expected string in command output")
    parser.add_argument("--session", help="Verify agent session is reset")
    parser.add_argument("--model", help="Verify agent's configured model in settings.json (agent name)")
    parser.add_argument("--expected-model", help="Expected model name (for --model check)")
    parser.add_argument("--quiet", action="store_true", help="Only output result (no OK/FAIL prefix)")

    args = parser.parse_args()

    checks = []

    if args.file and args.expected_size is not None:
        checks.append(verify_file_size(args.file, args.expected_size))
    elif args.file and args.contains:
        checks.append(verify_file_contains(args.file, args.contains))

    if args.json_file and args.key:
        checks.append(verify_json_key(args.json_file, args.key, args.equals, args.equals))

    if args.command and args.expect:
        checks.append(verify_command(args.command, args.expect))

    if args.session:
        checks.append(verify_session_reset(args.session))

    if args.model:
        checks.append(verify_model(args.model, args.expected_model))

    if not checks:
        parser.print_help()
        sys.exit(1)

    all_passed = True
    for passed, msg in checks:
        if not passed:
            all_passed = False
        if args.quiet:
            print("PASS" if passed else "FAIL")
        else:
            print(msg)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
