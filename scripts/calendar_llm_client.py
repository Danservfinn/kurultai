#!/usr/bin/env python3
"""
Calendar LLM Client - Claude Code session-based LLM integration

Replaces direct OpenRouter API calls with Claude Code sessions.
Uses subprocess to spawn claude-agent for intent classification.
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# Configuration
CLAUDE_AGENT = os.path.expanduser("~/.local/bin/claude")
CLAUDE_TIMEOUT = 90  # 90s timeout to allow for Claude Code startup
SCRIPT_DIR = Path(__file__).parent.resolve()

# System prompt for calendar parsing (same as before)
SYSTEM_PROMPT = """You are a calendar assistant parsing messages from a group chat.

Given a message and recent chat context, respond with JSON only. No explanation.

Schema:
{
  "intent": "event_create" | "event_query" | "event_rsvp_yes" | "event_rsvp_no" |
            "event_rsvp_maybe" | "event_modify" | "event_cancel" | "event_remind" |
            "not_calendar",
  "confidence": 0.0-1.0,
  "event": {
    "name": "string or null",
    "date_text": "string or null",
    "location": "string or null",
    "duration_minutes": int or null,
    "participants": ["string"] or [],
    "reference_event": "string or null"
  },
  "query": {
    "time_range": "string or null",
    "filter": "string or null"
  },
  "ambiguities": ["string"]
}

Rules:
- "I'm in" / "count me in" ALONE with no event mentioned = not_calendar (need reference event)
- "I'm in for [event]" with explicit event name = event_rsvp_yes with reference_event set
- "I'm in" following an event creation = event_rsvp_yes referencing that event
- "Can't make it", "not going", "decline", "skip", "no", "nope", "nah" = event_rsvp_no
- "Maybe", "not sure", "might" = event_rsvp_maybe
- If the message contains multiple events, return the primary one and note others in ambiguities
- confidence < 0.6 = flag for confirmation
- Default duration is null (caller will apply 2-hour default)
- Participants are first names only as mentioned in the message
- For RSVP/modify/cancel, reference_event should match the most recent relevant event name
- "my place" = sender's location
- Bare hours (1-6) default to PM for social events
- Morning keywords (breakfast, brunch, hike, run) keep AM times"""


def _build_classification_prompt(message: str, sender: str, recent_context: list = None) -> str:
    """Build the prompt for classification."""
    context_block = ""
    if recent_context:
        lines = [f"[{m['sender']}]: {m['text']}" for m in recent_context[-5:]]
        context_block = "\nRecent messages for context:\n" + "\n".join(lines)

    return f"""{SYSTEM_PROMPT}

Parse this message and respond with JSON only:

Sender: {sender}
Message: {message}{context_block}"""


def parse_with_claude_code(
    message: str,
    sender: str,
    recent_context: list = None,
    timeout: int = CLAUDE_TIMEOUT,
) -> dict:
    """
    Use Claude Code to classify intent and extract entities.

    Args:
        message: The message text to parse
        sender: Name or phone of sender
        recent_context: List of recent messages for context
        timeout: Timeout in seconds (default 90s to allow for Claude Code startup)

    Returns:
        Dict with intent, confidence, event, query, ambiguities
    """
    prompt = _build_classification_prompt(message, sender, recent_context)

    # Use main agent directory as workdir for CLAUDE.md context
    agent_root = str(SCRIPT_DIR)

    env = os.environ.copy()
    env.pop('CLAUDECODE', None)  # Allow nested Claude Code sessions
    env['PATH'] = (
        "/Users/kublai/.local/bin:/opt/homebrew/bin:"
        "/usr/local/bin:/usr/bin:/bin:" + env.get('PATH', '')
    )

    # Build claude command with print mode for non-interactive output
    # Use low effort for fast response, no tools needed for simple parsing
    cmd = [
        CLAUDE_AGENT,
        "--print",
        "--effort", "low",
        "--permission-mode", "bypassPermissions",
        "--no-session-persistence",
        prompt
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=agent_root,  # Run from agent directory for CLAUDE.md context
        )

        stdout_chunks = []
        start = time.time()

        # Read with timeout
        while True:
            elapsed = time.time() - start
            if elapsed >= timeout:
                proc.kill()
                proc.wait()
                raise TimeoutError(f"Claude Code timed out after {timeout}s")

            # Check if process has exited
            retcode = proc.poll()
            if retcode is not None:
                break

            time.sleep(0.1)

        # Collect remaining output
        stdout, stderr = proc.communicate(timeout=5)
        if stdout:
            stdout_chunks.append(stdout)

        full_output = "".join(stdout_chunks)

        if retcode != 0:
            raise RuntimeError(f"Claude Code failed with code {retcode}: {stderr}")

        # Parse JSON from output
        # Claude Code may wrap output in markdown code blocks
        json_str = _extract_json_from_output(full_output)

        result = json.loads(json_str)

        # Validate required fields
        if "intent" not in result:
            raise ValueError("Missing 'intent' field in response")

        return {
            "intent": result.get("intent", "not_calendar"),
            "confidence": result.get("confidence", 0.5),
            "event": result.get("event"),
            "query": result.get("query"),
            "ambiguities": result.get("ambiguities", []),
        }

    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse JSON from Claude Code output: {e}\nOutput: {full_output[:500]}")
    except Exception as e:
        raise RuntimeError(f"Claude Code execution failed: {e}")


def _extract_json_from_output(output: str) -> str:
    """Extract JSON from Claude Code output, handling markdown code blocks."""
    output = output.strip()

    # Check for markdown code block
    if "```json" in output:
        start = output.find("```json") + 7
        end = output.find("```", start)
        if end > start:
            return output[start:end].strip()
    elif "```" in output:
        start = output.find("```") + 3
        end = output.find("```", start)
        if end > start:
            return output[start:end].strip()

    # Try to find JSON object directly
    start = output.find("{")
    end = output.rfind("}")
    if start >= 0 and end > start:
        return output[start:end+1]

    # Return as-is and let JSON parser handle it
    return output


def is_claude_code_available() -> bool:
    """Check if Claude Code is available."""
    return os.path.exists(CLAUDE_AGENT) and os.access(CLAUDE_AGENT, os.X_OK)


if __name__ == "__main__":
    # Test the client
    test_cases = [
        ("Dinner at Mario's Friday at 7pm", "Danny"),
        ("What's happening this weekend?", "Liz"),
        ("I'm in for dinner", "Danny"),
        ("lol nice photo", "Liz"),
    ]

    print("Testing Calendar LLM Client (Claude Code)...")
    print(f"Claude Agent: {CLAUDE_AGENT}")
    print(f"Available: {is_claude_code_available()}")
    print()

    if not is_claude_code_available():
        print("ERROR: Claude Code not available at", CLAUDE_AGENT)
        sys.exit(1)

    for message, sender in test_cases:
        print(f"\nTest: '{message}' from {sender}")
        try:
            result = parse_with_claude_code(message, sender)
            print(f"  Intent: {result['intent']}")
            print(f"  Confidence: {result['confidence']}")
            if result.get('event'):
                print(f"  Event: {result['event']}")
        except Exception as e:
            print(f"  ERROR: {e}")
