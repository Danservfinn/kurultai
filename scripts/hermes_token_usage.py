#!/usr/bin/env python3
"""Hermes token-usage ledger.

There is no native token accounting in `claude --print` subprocess output,
so we estimate via a 4-chars/token heuristic on prompt + response. This is
good enough for a dashboard metric but should be labelled "est." on the UI.

Ledger: ~/.openclaw/logs/hermes-token-usage.jsonl (append-only, one line
per LLM invocation).

Also houses the model-override helper (get_model / set_model) that reads/
writes ~/.openclaw/agents/hermes/.claude/settings.json with
{"env": {"ANTHROPIC_MODEL": "..."}}.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta, date as date_cls
from pathlib import Path
from typing import Iterable

LEDGER_PATH = Path.home() / ".openclaw" / "logs" / "hermes-token-usage.jsonl"
MODEL_SETTINGS_PATH = Path.home() / ".openclaw" / "agents" / "hermes" / ".claude" / "settings.json"

# Rate-limit ceiling × typical-fix-prompt-size ≈ 10 × 3500
DAILY_CEILING = 35_000

MODEL_ALLOWLIST = [
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "default",
]

# --------------------------------------------------------------------- usage


def estimate_tokens(text: str) -> int:
    """4 characters ≈ 1 token heuristic (Anthropic average for English)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def record_usage(
    fix_id: str,
    prompt: str,
    response: str,
    model: str,
    kind: str = "fix",
) -> dict:
    """Append a usage line to the ledger. Non-fatal on I/O error."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fix_id": fix_id,
        "kind": kind,  # "fix", "summary", "other"
        "model": model or "default",
        "prompt_chars": len(prompt or ""),
        "response_chars": len(response or ""),
        "prompt_tokens_est": estimate_tokens(prompt or ""),
        "response_tokens_est": estimate_tokens(response or ""),
    }
    entry["total_tokens_est"] = entry["prompt_tokens_est"] + entry["response_tokens_est"]
    try:
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        print(f"[hermes_token_usage] ledger write failed: {e}")
    return entry


def _iter_entries() -> Iterable[dict]:
    if not LEDGER_PATH.exists():
        return
    try:
        with LEDGER_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def summarize(window_days: int = 7) -> dict:
    """Return today / yesterday / N-day totals + per-day breakdown."""
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    cutoff = today - timedelta(days=window_days)

    by_day: dict[str, int] = {}
    total_today = 0
    total_yesterday = 0

    for e in _iter_entries():
        try:
            ts = datetime.fromisoformat(e["ts"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        day = ts.date()
        if day < cutoff:
            continue
        tokens = int(e.get("total_tokens_est", 0))
        by_day[day.isoformat()] = by_day.get(day.isoformat(), 0) + tokens
        if day == today:
            total_today += tokens
        elif day == yesterday:
            total_yesterday += tokens

    seven_day = sum(by_day.values())
    per_day = sorted(
        ({"date": k, "tokens": v} for k, v in by_day.items()),
        key=lambda r: r["date"],
        reverse=True,
    )

    return {
        "today": total_today,
        "yesterday": total_yesterday,
        "seven_day": seven_day,
        "ceiling": DAILY_CEILING,
        "per_day": per_day,
    }


def daily_ceiling() -> int:
    return DAILY_CEILING


# --------------------------------------------------------------------- model


def get_model() -> str | None:
    """Return the current Hermes model override, or None if inherit-default."""
    if not MODEL_SETTINGS_PATH.exists():
        return None
    try:
        data = json.loads(MODEL_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    model = (data.get("env") or {}).get("ANTHROPIC_MODEL")
    return model or None


def set_model(name: str) -> None:
    """Persist a model choice. 'default' clears the override."""
    if name not in MODEL_ALLOWLIST:
        raise ValueError(
            f"model '{name}' not in allowlist: {', '.join(MODEL_ALLOWLIST)}"
        )
    MODEL_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if MODEL_SETTINGS_PATH.exists():
        try:
            existing = json.loads(MODEL_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    env = dict(existing.get("env") or {})

    if name == "default":
        env.pop("ANTHROPIC_MODEL", None)
    else:
        env["ANTHROPIC_MODEL"] = name

    existing["env"] = env

    # Atomic write with 0o600
    fd, tmp = tempfile.mkstemp(
        dir=str(MODEL_SETTINGS_PATH.parent),
        prefix=".settings.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, MODEL_SETTINGS_PATH)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------- CLI


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Hermes token-usage + model helper")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("summarize", help="Print 7-day token-usage summary")
    sub.add_parser("get-model", help="Print current model override")
    set_p = sub.add_parser("set-model", help="Set model override")
    set_p.add_argument("model", choices=MODEL_ALLOWLIST)

    args = parser.parse_args()
    if args.cmd == "summarize":
        print(json.dumps(summarize(7), indent=2))
    elif args.cmd == "get-model":
        print(get_model() or "default")
    elif args.cmd == "set-model":
        set_model(args.model)
        print(f"set to {args.model}")
    sys.exit(0)
