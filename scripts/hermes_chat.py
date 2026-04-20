#!/usr/bin/env python3
"""Hermes chat wrapper.

Spawns `claude --print --verbose --output-format=stream-json
--include-partial-messages` with the conversation history replayed into
the prompt and a Hermes-specific system prompt appended. Streams stdout
line-by-line to our own stdout, then persists the completed turn to
~/.openclaw/logs/hermes-chats/{convo_id}.jsonl.

Phase 1: read-only chat. Claude Code can use Read/Grep/Glob on the
Kurultai workspace; no writes, no bash, no commits. Tool-calling phase
(queue_fix / trigger_sweep) comes later via an MCP server.

Usage:
    python3 hermes_chat.py --convo abc --message "..." [--history path]

The --history flag loads prior turns from JSONL and replays them into
the prompt.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hermes_token_usage as tu  # noqa: E402

LLM_CMD = os.getenv("HERMES_LLM_CMD", "claude")
LLM_TIMEOUT_SECS = int(os.getenv("HERMES_CHAT_TIMEOUT", "300"))

CONVO_DIR = Path.home() / ".openclaw" / "logs" / "hermes-chats"
WORKSPACE_ADDS = [
    str(Path.home() / ".openclaw" / "agents" / "main"),
    str(Path.home() / ".openclaw" / "agents" / "hermes"),
    str(Path.home() / ".openclaw" / "logs"),
    str(Path.home() / ".openclaw" / "flags"),
    str(Path.home() / "brain"),
]

SYSTEM_PROMPT = """You are Hermes — the eighth member of the Kurultai
multi-agent system. You are speaking directly to the operator through
the dashboard chat at the.kurult.ai/hermes.

Your purpose: help the operator observe and reason about your own
autonomous behavior. You can read files in the Kurultai workspace,
grep through logs, inspect configuration, and answer questions about
what you have done or are doing.

## Constraints
- You have read-only execution. You cannot write files, run git, run
  bash, or take any action with side effects directly.
- You must not reveal secrets, tokens, or credential file contents.
  If asked to read ~/.openclaw/credentials/ or similar, politely
  refuse.
- Be brief and concrete. Terse > verbose. Non-engineer readable
  when possible.

## How to propose actions

When the operator asks you to TAKE AN ACTION (queue a fix, trigger a
sweep, etc.), you do NOT execute it. Instead you propose it by emitting
a fenced code block. The dashboard will render your proposal as a card
with Apply and Dismiss buttons, and the operator must confirm before
anything happens. Proposals flow through the same safety gates
(rate limit, denylist, circuit breaker) as your autonomous fixes.

Two proposal types are supported:

1. `queue_fix` — propose a content-docs or code fix on a specific file:
```hermes-proposal
{"tool": "queue_fix", "target": "/absolute/path/to/file.py", "reason": "short description of what to fix"}
```

2. `trigger_sweep` — propose running a sweep in dry-run:
```hermes-proposal
{"tool": "trigger_sweep", "name": "knowledge_stale"}
```
   Valid sweep names: knowledge_stale, dedup_gap, bare_except.

Rules for proposals:
- Output the fenced `hermes-proposal` block ON ITS OWN, with at most
  a single sentence of lead-in prose. Do NOT explain the JSON.
- Target paths must be absolute and within the Kurultai workspace
  (under ~/.openclaw or ~/brain).
- Reason is short: ≤80 characters, describing the fix intent.
- If unclear what the operator wants, ASK a clarifying question first
  instead of proposing.
- NEVER emit hermes-proposal for hypothetical discussion — only when
  the operator has genuinely asked you to take action.

## Useful locations (you may Read/Grep these)
- ~/.openclaw/agents/main/logs/hermes-actions.jsonl — action ledger
- ~/.openclaw/agents/main/logs/cascade-detections.jsonl — cascade events
- ~/.openclaw/logs/hermes-summaries/*.json — cached daily summaries
- ~/.openclaw/logs/hermes-token-usage.jsonl — token ledger
- ~/.openclaw/flags/hermes-*.flag — kill switches (presence = engaged)
- ~/.openclaw/agents/main/scripts/hermes-*.py — the scripts that
  power you
- ~/.openclaw/logs/hermes-chats/*.jsonl — your own past conversations
"""


def _convo_path(convo_id: str) -> Path:
    return CONVO_DIR / f"{convo_id}.jsonl"


def _load_history(convo_id: str) -> list[dict]:
    path = _convo_path(convo_id)
    if not path.exists():
        return []
    turns: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    turns.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return turns


def _append_turn(convo_id: str, turn: dict) -> None:
    CONVO_DIR.mkdir(parents=True, exist_ok=True)
    # Use `with` so the handle closes on every write — prevents FD leak
    # under long sessions or high turn counts.
    with _convo_path(convo_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps(turn) + "\n")


_FENCE_RE = re.compile(r"```hermes-proposal[\s\S]*?```", re.MULTILINE)


def _sanitize_replay(content: str) -> str:
    """Strip hermes-proposal fences + suspicious ##-headers from replayed
    assistant content so cross-turn prompt injection cannot amplify.

    An attacker who got a fence planted in a prior assistant turn (via
    an indirect-injection file read) would have the LLM re-see its own
    "correct" proposal and repeat. Stripping the fence breaks that loop.
    """
    if not content:
        return ""
    cleaned = _FENCE_RE.sub("[proposal fence removed from replay]", content)
    # Also neutralize any attempted ## markers that could confuse the
    # User / Assistant boundary injection we build below.
    cleaned = cleaned.replace("\n## User", "\n(## User)")
    cleaned = cleaned.replace("\n## Assistant", "\n(## Assistant)")
    return cleaned


def _build_prompt(history: list[dict], new_message: str) -> str:
    """Render history + new user message as a single prompt.

    We use a human-readable transcript format; Claude Code will read
    this as the user's turn and respond.
    """
    if not history:
        return new_message

    lines = ["# Previous conversation\n"]
    for turn in history:
        role = turn.get("role", "?")
        content = _sanitize_replay(turn.get("content", ""))
        if role == "user":
            lines.append(f"\n## User\n{content}")
        elif role == "assistant":
            lines.append(f"\n## Assistant (you)\n{content}")
    lines.append(f"\n# Current user message\n{new_message}")
    return "\n".join(lines)


def _invoke(convo_id: str, prompt: str) -> int:
    """Spawn claude, stream stdout line-by-line to our stdout, capture
    the final assistant text for persistence + token accounting."""

    env = os.environ.copy()
    model_used = tu.get_model() or "default"
    if model_used != "default":
        env["ANTHROPIC_MODEL"] = model_used

    args = [
        LLM_CMD,
        "--print",
        "--verbose",
        "--output-format=stream-json",
        "--include-partial-messages",
        "--allowedTools", "Read", "Grep", "Glob",
        "--disallowedTools", "Bash", "Edit", "Write", "NotebookEdit",
        "--append-system-prompt", SYSTEM_PROMPT,
    ]
    for extra in WORKSPACE_ADDS:
        args.extend(["--add-dir", extra])

    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1,  # line-buffered
    )

    # Send prompt and close stdin so claude begins
    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
    except BrokenPipeError:
        pass

    collected_text = ""
    collected_tool_uses: list[dict] = []
    result_payload: dict | None = None

    start = time.time()
    for line in proc.stdout:
        # Forward raw line to caller
        sys.stdout.write(line)
        sys.stdout.flush()

        # Parse to collect final text + usage
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue

        if evt.get("type") == "assistant":
            msg = evt.get("message", {})
            for block in msg.get("content", []):
                if block.get("type") == "text":
                    collected_text = block.get("text", collected_text)
                elif block.get("type") == "tool_use":
                    collected_tool_uses.append({
                        "name": block.get("name"),
                        "input": block.get("input"),
                        "id": block.get("id"),
                    })
        elif evt.get("type") == "result":
            result_payload = evt
            break

        if time.time() - start > LLM_TIMEOUT_SECS:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass  # zombie; OS will reap eventually
            sys.stderr.write(f"[hermes_chat] timeout after {LLM_TIMEOUT_SECS}s\n")
            _append_turn(
                convo_id,
                {
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "role": "assistant",
                    "content": "(timed out — partial or no response)",
                    "tool_uses": [],
                    "model": model_used,
                    "interrupted": True,
                },
            )
            return 124

    try:
        rc = proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            rc = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            rc = 124

    # Append turn to convo JSONL
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _append_turn(
        convo_id,
        {
            "ts": now_iso,
            "role": "assistant",
            "content": collected_text,
            "tool_uses": collected_tool_uses,
            "model": model_used,
            "result": {
                "duration_ms": (result_payload or {}).get("duration_ms"),
                "num_turns": (result_payload or {}).get("num_turns"),
                "stop_reason": (result_payload or {}).get("stop_reason"),
            },
        },
    )

    # Token accounting
    try:
        tu.record_usage(
            f"chat-{convo_id}",
            prompt,
            collected_text,
            model_used,
            kind="chat",
        )
    except Exception as e:
        sys.stderr.write(f"[hermes_chat] token record failed: {e}\n")

    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes chat wrapper")
    parser.add_argument("--convo", required=True, help="Conversation id")
    parser.add_argument("--message", required=True, help="User message")
    args = parser.parse_args()

    # Validate convo_id format — no path traversal
    if not re.fullmatch(r"[a-z0-9-]{4,64}", args.convo):
        sys.stderr.write("convo id must match [a-z0-9-]{4,64}\n")
        return 2

    # Load history, persist user turn, build prompt
    history = _load_history(args.convo)
    _append_turn(
        args.convo,
        {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "role": "user",
            "content": args.message,
        },
    )
    prompt = _build_prompt(history, args.message)

    return _invoke(args.convo, prompt)


if __name__ == "__main__":
    sys.exit(main())
