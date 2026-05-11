"""Phase 2.5 Step 6 — calendar helper for brain-service.

Wraps ``gcalcli`` subprocess as the source of truth for CalendarEvent reads
and writes, with a short-TTL cache in ``calendar_event_cache``. Replaces the
Neo4j ``CalendarEvent`` access pattern that used to live in ``server.js``.

Public surface used by ``brain_service.handle_rpc``:

* ``CalendarService.list_events(time_min, time_max, person=None, calendar=None)``
* ``CalendarService.create_event(...)``
* ``CalendarService.update_event(...)``
* ``CalendarService.cancel_event(...)``
* ``CalendarService.list_due_reminders(now_ms=None, limit=50)``
* ``CalendarService.health()``

The ``server.js`` calendar route migration in Step 8/9 calls these via the
brain-service Unix socket.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


DEFAULT_GCALCLI = "/Users/kublai/.brain-migration-venv/bin/gcalcli"
DEFAULT_CACHE_TTL_SECONDS = 300


class CalendarError(Exception):
    """Generic calendar failure."""


class CalendarUnavailableError(CalendarError):
    """Raised when gcalcli is missing or auth has expired."""


class CalendarValidationError(CalendarError):
    """Raised on invalid caller input."""


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    external_id: str | None
    provider: str
    calendar_id: str | None
    title: str
    start_at: int
    end_at: int | None
    status: str
    payload: dict[str, Any]
    fetched_at: int
    expires_at: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "external_id": self.external_id,
            "provider": self.provider,
            "calendar_id": self.calendar_id,
            "title": self.title,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "status": self.status,
            "payload": self.payload,
            "fetched_at": self.fetched_at,
            "expires_at": self.expires_at,
        }


def _parse_iso_or_ms(value: str | int | float) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise CalendarValidationError(f"invalid datetime: {value!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _ms_to_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _ms_to_gcalcli_date(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M")


class CalendarStore:
    """SQLite-backed cache for CalendarEvent reads."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def upsert(self, event: CalendarEvent) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO calendar_event_cache
                  (id, external_id, provider, calendar_id, title,
                   start_at, end_at, status, payload_json, fetched_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  external_id = excluded.external_id,
                  provider = excluded.provider,
                  calendar_id = excluded.calendar_id,
                  title = excluded.title,
                  start_at = excluded.start_at,
                  end_at = excluded.end_at,
                  status = excluded.status,
                  payload_json = excluded.payload_json,
                  fetched_at = excluded.fetched_at,
                  expires_at = excluded.expires_at
                """,
                (
                    event.id, event.external_id, event.provider, event.calendar_id,
                    event.title, event.start_at, event.end_at, event.status,
                    json.dumps(event.payload, ensure_ascii=False, sort_keys=True),
                    event.fetched_at, event.expires_at,
                ),
            )

    def query_window(self, *, time_min_ms: int, time_max_ms: int,
                     now_ms: int | None = None) -> list[CalendarEvent]:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM calendar_event_cache
                 WHERE start_at >= ? AND start_at < ? AND expires_at >= ?
                 ORDER BY start_at
                """,
                (time_min_ms, time_max_ms, now_ms),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def is_window_fresh(self, *, time_min_ms: int, time_max_ms: int,
                        now_ms: int | None = None) -> bool:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT min(expires_at) AS exp, count(*) AS n FROM calendar_event_cache "
                "WHERE start_at >= ? AND start_at < ?",
                (time_min_ms, time_max_ms),
            ).fetchone()
        if not row or row["n"] == 0:
            return False
        return row["exp"] is not None and row["exp"] >= now_ms

    def purge_expired(self, *, now_ms: int | None = None) -> int:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM calendar_event_cache WHERE expires_at < ?", (now_ms,))
            return cur.rowcount

    def delete(self, event_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM calendar_event_cache WHERE id = ?", (event_id,))

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> CalendarEvent:
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        return CalendarEvent(
            id=row["id"], external_id=row["external_id"],
            provider=row["provider"], calendar_id=row["calendar_id"],
            title=row["title"], start_at=row["start_at"], end_at=row["end_at"],
            status=row["status"], payload=payload,
            fetched_at=row["fetched_at"], expires_at=row["expires_at"],
        )


class GcalcliClient:
    """Subprocess wrapper for gcalcli on the Mac mini."""

    def __init__(self, *, gcalcli_path: str | Path = DEFAULT_GCALCLI,
                 default_calendar: str | None = None,
                 timeout_seconds: float = 30.0):
        self.gcalcli_path = str(gcalcli_path)
        self.default_calendar = default_calendar
        self.timeout_seconds = timeout_seconds

    def _run(self, args: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess:
        cmd = [self.gcalcli_path, *args]
        try:
            return subprocess.run(
                cmd, input=stdin, capture_output=True, text=True,
                timeout=self.timeout_seconds, check=False,
            )
        except FileNotFoundError as exc:
            raise CalendarUnavailableError(f"gcalcli not found at {self.gcalcli_path}") from exc

    def list_calendars(self) -> list[dict[str, str]]:
        result = self._run(["--nocolor", "list"])
        if result.returncode != 0:
            raise CalendarUnavailableError(f"gcalcli list failed: {result.stderr.strip()}")
        out: list[dict[str, str]] = []
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("Access") or stripped.startswith("------"):
                continue
            access, _, title = stripped.partition(" ")
            if title:
                out.append({"access": access, "title": title.strip()})
        return out

    def agenda_tsv(self, *, time_min: str, time_max: str,
                   calendar: str | None = None) -> list[dict[str, str]]:
        args = ["--nocolor"]
        cal = calendar or self.default_calendar
        if cal:
            args.extend(["--calendar", cal])
        args.extend(["agenda", "--tsv", time_min, time_max])
        result = self._run(args)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "credentials" in stderr.lower() or "auth" in stderr.lower():
                raise CalendarUnavailableError(stderr)
            raise CalendarError(f"gcalcli agenda failed: {stderr}")
        events: list[dict[str, str]] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            cols = line.split("\t")
            # gcalcli >= 4.x emits a header row plus 5-column rows:
            # start_date, start_time, end_date, end_time, title
            # Older versions emit a 6-column form with a leading link column;
            # detect by header-row "start_date" first cell, then route columns.
            if cols[0] == "start_date":
                continue
            if len(cols) >= 6 and cols[4].startswith("http"):
                events.append({
                    "start_date": cols[0], "start_time": cols[1],
                    "end_date": cols[2], "end_time": cols[3],
                    "link": cols[4], "title": cols[5],
                })
            elif len(cols) >= 5:
                events.append({
                    "start_date": cols[0], "start_time": cols[1],
                    "end_date": cols[2], "end_time": cols[3],
                    "link": "", "title": cols[4],
                })
        return events

    def add_event(self, *, title: str, when: str, length_minutes: int | None = None,
                  where: str | None = None, description: str | None = None,
                  reminders: list[int] | None = None,
                  calendar: str | None = None) -> dict[str, Any]:
        args = ["--nocolor"]
        cal = calendar or self.default_calendar
        if cal:
            args.extend(["--calendar", cal])
        args.extend(["add", "--title", title, "--when", when])
        if length_minutes is not None:
            args.extend(["--duration", str(length_minutes)])
        if where:
            args.extend(["--where", where])
        if description:
            args.extend(["--description", description])
        for offset in reminders or []:
            args.extend(["--reminder", str(int(offset))])
        args.append("--default-reminders")
        result = self._run(args)
        if result.returncode != 0:
            raise CalendarError(
                f"gcalcli add failed: {result.stderr.strip() or result.stdout.strip()}"
            )
        return {"stdout": result.stdout, "stderr": result.stderr}

    def edit_events(self, *, search_text: str, action: str = "title",
                    value: str | None = None,
                    calendar: str | None = None) -> dict[str, Any]:
        args = ["--nocolor"]
        cal = calendar or self.default_calendar
        if cal:
            args.extend(["--calendar", cal])
        args.extend(["edit", search_text])
        result = self._run(args, stdin=f"{action}\n{value or ''}\nq\n")
        if result.returncode != 0:
            raise CalendarError(
                f"gcalcli edit failed: {result.stderr.strip() or result.stdout.strip()}"
            )
        return {"stdout": result.stdout, "stderr": result.stderr}

    def delete_events(self, *, search_text: str,
                      calendar: str | None = None) -> dict[str, Any]:
        args = ["--nocolor"]
        cal = calendar or self.default_calendar
        if cal:
            args.extend(["--calendar", cal])
        args.extend(["delete", search_text])
        result = self._run(args, stdin="y\n" * 50)
        if result.returncode != 0:
            raise CalendarError(
                f"gcalcli delete failed: {result.stderr.strip() or result.stdout.strip()}"
            )
        return {"stdout": result.stdout, "stderr": result.stderr}


_EID_RE = re.compile(r"[?&]eid=([^&\s]+)")


def _row_to_event(row: dict[str, str], *, fetched_at: int, ttl_seconds: int,
                  default_calendar: str | None) -> CalendarEvent:
    is_all_day = row["start_time"].strip().lower() in ("", "all-day")
    start_date = row["start_date"]
    end_date = row["end_date"] or start_date
    if is_all_day:
        start_at = _parse_iso_or_ms(start_date + "T00:00:00+00:00")
        end_at = _parse_iso_or_ms(end_date + "T00:00:00+00:00")
    else:
        start_at = _parse_iso_or_ms(f"{start_date}T{row['start_time']}")
        if row["end_time"] and row["end_time"].lower() not in ("", "all-day"):
            end_at = _parse_iso_or_ms(f"{end_date}T{row['end_time']}")
        else:
            end_at = None
    link = row.get("link") or ""
    eid_match = _EID_RE.search(link)
    external_id = eid_match.group(1) if eid_match else None
    cache_id = external_id or f"{start_date}|{row['start_time']}|{row['title']}"
    payload = {
        "link": link,
        "is_all_day": is_all_day,
        "raw_row": row,
        "calendar_hint": default_calendar,
    }
    return CalendarEvent(
        id=cache_id,
        external_id=external_id,
        provider="google-calendar",
        calendar_id=default_calendar,
        title=row["title"],
        start_at=start_at,
        end_at=end_at,
        status="active",
        payload=payload,
        fetched_at=fetched_at,
        expires_at=fetched_at + ttl_seconds * 1000,
    )


class CalendarService:
    """High-level calendar API for brain-service."""

    def __init__(self, store: CalendarStore, client: GcalcliClient,
                 telemetry: Any | None = None, *,
                 default_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
                 default_calendar: str | None = None):
        self.store = store
        self.client = client
        self.telemetry = telemetry
        self.default_ttl_seconds = default_ttl_seconds
        self.default_calendar = default_calendar

    def health(self) -> dict[str, Any]:
        try:
            calendars = self.client.list_calendars()
            return {
                "ok": True,
                "calendars": calendars,
                "gcalcli": self.client.gcalcli_path,
                "default_calendar": self.default_calendar,
            }
        except CalendarUnavailableError as exc:
            return {"ok": False, "error": str(exc), "gcalcli": self.client.gcalcli_path}

    def list_events(self, *, time_min: str | int, time_max: str | int,
                    person: str | None = None, calendar: str | None = None,
                    use_cache: bool = True) -> list[dict[str, Any]]:
        time_min_ms = _parse_iso_or_ms(time_min)
        time_max_ms = _parse_iso_or_ms(time_max)
        if time_max_ms < time_min_ms:
            raise CalendarValidationError("time_max must be >= time_min")

        now_ms = int(time.time() * 1000)
        cal = calendar or self.default_calendar

        if use_cache and self.store.is_window_fresh(
            time_min_ms=time_min_ms, time_max_ms=time_max_ms, now_ms=now_ms,
        ):
            cached = self.store.query_window(
                time_min_ms=time_min_ms, time_max_ms=time_max_ms, now_ms=now_ms,
            )
            return [
                ev.to_dict() for ev in cached if self._matches_person(ev, person)
            ]

        rows = self.client.agenda_tsv(
            time_min=_ms_to_gcalcli_date(time_min_ms),
            time_max=_ms_to_gcalcli_date(time_max_ms),
            calendar=cal,
        )
        events = [
            _row_to_event(
                r, fetched_at=now_ms,
                ttl_seconds=self.default_ttl_seconds,
                default_calendar=cal,
            )
            for r in rows
        ]
        for ev in events:
            self.store.upsert(ev)
        return [ev.to_dict() for ev in events if self._matches_person(ev, person)]

    @staticmethod
    def _matches_person(event: CalendarEvent, person: str | None) -> bool:
        if not person:
            return True
        haystack = (event.title or "").lower()
        return person.lower() in haystack

    def create_event(self, *, title: str, when: str, length_minutes: int | None = None,
                     where: str | None = None, description: str | None = None,
                     reminders: list[int] | None = None,
                     calendar: str | None = None) -> dict[str, Any]:
        cal = calendar or self.default_calendar
        result = self.client.add_event(
            title=title, when=when, length_minutes=length_minutes,
            where=where, description=description, reminders=reminders, calendar=cal,
        )
        self.store.purge_expired()
        return result

    def update_event(self, *, search_text: str, action: str = "title",
                     value: str | None = None,
                     calendar: str | None = None) -> dict[str, Any]:
        cal = calendar or self.default_calendar
        result = self.client.edit_events(
            search_text=search_text, action=action, value=value, calendar=cal,
        )
        self.store.purge_expired()
        return result

    def cancel_event(self, *, search_text: str,
                     calendar: str | None = None) -> dict[str, Any]:
        cal = calendar or self.default_calendar
        result = self.client.delete_events(search_text=search_text, calendar=cal)
        self.store.purge_expired()
        return result

    def list_due_reminders(self, *, now_ms: int | None = None,
                           limit: int = 50) -> list[dict[str, Any]]:
        if self.telemetry is None:
            raise CalendarError("telemetry not wired on calendar service")
        return self.telemetry.list_due_reminders(now_ms=now_ms, limit=limit)
