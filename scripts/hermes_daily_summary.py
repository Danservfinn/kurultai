#!/usr/bin/env python3
"""Hermes daily summary generator.

Reads the day's activity from hermes-actions.jsonl + cascade-detections.jsonl
and asks Claude Code (`claude --print`) to write a short plain-English
narrative describing what Hermes did — aimed at a non-engineer reader.

Caches to ~/.openclaw/logs/hermes-summaries/YYYY-MM-DD.json.

Today's cache is regenerated on request (with a 10-minute soft-rate-limit
to avoid LLM spam). Prior days are cached permanently unless --force.

CLI:
    python3 hermes_daily_summary.py --date 2026-04-19
    python3 hermes_daily_summary.py --date today
    python3 hermes_daily_summary.py --date 2026-04-19 --force
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta, date as date_cls
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hermes_token_usage as tu  # noqa: E402

LLM_CMD = os.getenv("HERMES_LLM_CMD", "claude")
LLM_TIMEOUT_SECS = int(os.getenv("HERMES_SUMMARY_TIMEOUT", "120"))

ACTIONS_LOG = Path.home() / ".openclaw" / "agents" / "main" / "logs" / "hermes-actions.jsonl"
CASCADE_LOG = Path.home() / ".openclaw" / "agents" / "main" / "logs" / "cascade-detections.jsonl"
SUMMARY_CACHE_DIR = Path.home() / ".openclaw" / "logs" / "hermes-summaries"
TODAY_REGEN_WINDOW_SECS = 600  # 10 min


def _today_utc() -> date_cls:
    return datetime.now(timezone.utc).date()


def _parse_date(s: str) -> date_cls:
    if s in ("today", "now"):
        return _today_utc()
    if s == "yesterday":
        return _today_utc() - timedelta(days=1)
    return date_cls.fromisoformat(s)


def _events_for_date(target_date: date_cls, max_events: int = 100) -> list[dict]:
    """Collect actions + cascade detections for the given UTC date."""
    events: list[dict] = []
    for path, kind in [(ACTIONS_LOG, "action"), (CASCADE_LOG, "cascade")]:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts_str = d.get("timestamp") or d.get("ts") or ""
                    if not ts_str:
                        continue
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    if ts.astimezone(timezone.utc).date() != target_date:
                        continue
                    events.append({"kind": kind, "payload": d})
        except OSError:
            continue

    # Sort chronologically, cap to max_events (take most recent if over cap)
    events.sort(key=lambda e: e["payload"].get("timestamp") or e["payload"].get("ts") or "")
    if len(events) > max_events:
        events = events[-max_events:]
    return events


def _build_prompt(target_date: date_cls, events: list[dict]) -> str:
    if not events:
        lines = "(no events)"
    else:
        rendered = []
        for e in events:
            p = e["payload"]
            ts = (p.get("timestamp") or p.get("ts") or "")[:19]
            kind = p.get("action_type") or p.get("detection_type") or p.get("type") or e["kind"]
            outcome = p.get("outcome") or p.get("status") or ""
            target = p.get("target") or p.get("path") or p.get("detail") or ""
            tier = p.get("tier") or ""
            ev = p.get("evidence") or {}
            ev_bits = []
            for k in ("sweep", "autonomy_level", "diff_lines", "commit_sha", "push_ok", "reason"):
                if k in ev:
                    ev_bits.append(f"{k}={ev[k]}")
            extras = " · " + " · ".join(ev_bits) if ev_bits else ""
            rendered.append(
                f"- {ts} | {kind} | {outcome} | target={target}"
                + (f" | tier={tier}" if tier else "")
                + extras
            )
        lines = "\n".join(rendered)

    return (
        f"You are writing a concise plain-English summary of what the Hermes autonomous agent "
        f"did on {target_date.isoformat()} (UTC). Your audience is a non-engineer who wants a "
        f"one-glance sense of the day: what happened, what mattered, was anything concerning.\n\n"
        f"Rules:\n"
        f"- Write 2–4 short paragraphs, 200–400 words total.\n"
        f"- Start with a single lede sentence that captures the arc of the day.\n"
        f"- Use past tense, human voice. No bullet lists.\n"
        f"- Avoid technical jargon. Translate terms: 'autonomous_fix' → 'fixed a file'; 'rotate_failing_provider' → 'switched a model provider'; 'reconcile_orphan_tasks' → 'cleaned up abandoned tasks'.\n"
        f"- Group related events rather than listing them one-by-one.\n"
        f"- If it was a quiet day (very few or no events), say so concisely in 1–2 sentences.\n"
        f"- Output the prose narrative only. No heading, no meta-comments, no explanations.\n\n"
        f"--- Events on {target_date.isoformat()} ---\n"
        f"{lines}\n"
        f"--- End of events ---\n"
    )


def _invoke_llm(prompt: str) -> tuple[int, str, str]:
    """Invoke `claude --print` with model override + token logging."""
    env = os.environ.copy()
    model_used = "default"
    override = tu.get_model()
    if override:
        env["ANTHROPIC_MODEL"] = override
        model_used = override
    try:
        result = subprocess.run(
            [LLM_CMD, "--print", prompt],
            capture_output=True, text=True, timeout=LLM_TIMEOUT_SECS,
            env=env,
        )
        try:
            tu.record_usage(
                f"summary-{_today_utc().isoformat()}",
                prompt,
                result.stdout or "",
                model_used,
                kind="summary",
            )
        except Exception as e:
            print(f"[hermes_daily_summary] token record failed: {e}")
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", f"LLM CLI '{LLM_CMD}' not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", f"LLM timeout after {LLM_TIMEOUT_SECS}s"


def _cache_path(target_date: date_cls) -> Path:
    return SUMMARY_CACHE_DIR / f"{target_date.isoformat()}.json"


def _load_cache(target_date: date_cls) -> dict | None:
    p = _cache_path(target_date)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_cache(target_date: date_cls, payload: dict) -> None:
    SUMMARY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(target_date).write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def _regen_allowed_for_today(cache: dict | None) -> bool:
    """Today's summary is regen-eligible after TODAY_REGEN_WINDOW_SECS."""
    if not cache:
        return True
    try:
        generated = datetime.fromisoformat(cache["generated_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return True
    age = (datetime.now(timezone.utc) - generated).total_seconds()
    return age >= TODAY_REGEN_WINDOW_SECS


def generate(target_date: date_cls, force: bool = False) -> dict:
    """Generate or return cached summary for the given date."""
    is_today = target_date == _today_utc()
    cache = _load_cache(target_date)

    if cache and not force:
        if not is_today:
            return cache
        if not _regen_allowed_for_today(cache):
            return cache

    events = _events_for_date(target_date)

    if not events:
        payload = {
            "date": target_date.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": tu.get_model() or "default",
            "narrative": "Quiet day. No events recorded for this date.",
            "event_count": 0,
            "token_est": 0,
            "state": "empty",
        }
        _save_cache(target_date, payload)
        return payload

    prompt = _build_prompt(target_date, events)
    rc, stdout, stderr = _invoke_llm(prompt)

    if rc != 0:
        # Don't cache failures — fall back to a minimal stub that surfaces the error
        return {
            "date": target_date.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": tu.get_model() or "default",
            "narrative": f"(summary unavailable: LLM returned rc={rc})",
            "event_count": len(events),
            "token_est": 0,
            "state": "error",
            "error": stderr[-500:],
        }

    narrative = stdout.strip() or "(empty response from LLM)"
    token_est = tu.estimate_tokens(prompt) + tu.estimate_tokens(narrative)
    payload = {
        "date": target_date.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": tu.get_model() or "default",
        "narrative": narrative,
        "event_count": len(events),
        "token_est": token_est,
        "state": "ok",
    }
    _save_cache(target_date, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes daily summary")
    parser.add_argument("--date", default="today", help="YYYY-MM-DD or 'today' or 'yesterday'")
    parser.add_argument("--force", action="store_true", help="Bypass cache")
    parser.add_argument("--json", action="store_true", help="Output raw JSON (default)")
    args = parser.parse_args()

    try:
        target = _parse_date(args.date)
    except ValueError as e:
        print(f"invalid date: {e}", file=sys.stderr)
        return 2

    result = generate(target, force=args.force)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
