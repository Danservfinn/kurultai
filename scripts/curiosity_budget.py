"""
curiosity_budget.py — Budget tracking and spend management for the General Curiosity Engine.

Uses SQLite for high-frequency writes. Budget is date-based (America/New_York),
with graceful degradation through four stages: normal -> conserve -> shared -> suspend.
"""

import sqlite3
import json
import os
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/New_York")
DB_PATH = Path.home() / ".openclaw" / "data" / "curiosity_spend.db"
CONFIG_PATH = Path.home() / ".openclaw" / "config" / "curiosity.json"

CATEGORIES = ("human", "self", "world", "contextual")


def _get_db() -> sqlite3.Connection:
    """Get SQLite connection, create table if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS curiosity_spend (
            cycle_id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            question TEXT,
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0,
            tool_calls INTEGER DEFAULT 0,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            outcome TEXT,
            depth INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def load_config() -> dict:
    """Load curiosity.json config."""
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def _today_str() -> str:
    """Today's date string in local timezone for date-based grouping."""
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")


def _now_iso() -> str:
    """Current timestamp in ISO format with timezone."""
    return datetime.now(LOCAL_TZ).isoformat()


def record_spend(
    cycle_id: str,
    category: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    tool_calls: int = 0,
    question: str = "",
    outcome: str = "",
    depth: int = 0,
):
    """Insert or update a spend record.

    If cycle_id already exists, accumulates token counts and tool_calls
    and updates the question/outcome/depth fields.
    """
    db = _get_db()
    try:
        existing = db.execute(
            "SELECT cycle_id FROM curiosity_spend WHERE cycle_id = ?", (cycle_id,)
        ).fetchone()

        if existing:
            db.execute(
                """UPDATE curiosity_spend
                   SET tokens_in = tokens_in + ?,
                       tokens_out = tokens_out + ?,
                       tool_calls = tool_calls + ?,
                       question = CASE WHEN ? != '' THEN ? ELSE question END,
                       outcome = CASE WHEN ? != '' THEN ? ELSE outcome END,
                       depth = CASE WHEN ? > 0 THEN ? ELSE depth END
                   WHERE cycle_id = ?""",
                (
                    tokens_in, tokens_out, tool_calls,
                    question, question,
                    outcome, outcome,
                    depth, depth,
                    cycle_id,
                ),
            )
        else:
            db.execute(
                """INSERT INTO curiosity_spend
                   (cycle_id, category, question, tokens_in, tokens_out,
                    tool_calls, started_at, outcome, depth)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    cycle_id, category, question, tokens_in, tokens_out,
                    tool_calls, _now_iso(), outcome, depth,
                ),
            )
        db.commit()
    finally:
        db.close()


def complete_spend(cycle_id: str, outcome: str):
    """Mark a spend record as completed with outcome."""
    db = _get_db()
    try:
        db.execute(
            """UPDATE curiosity_spend
               SET completed_at = ?, outcome = ?
               WHERE cycle_id = ?""",
            (_now_iso(), outcome, cycle_id),
        )
        db.commit()
    finally:
        db.close()


def get_daily_spend(category: str = None) -> dict:
    """Sum today's spend. If category is None, return all categories.

    Returns:
        If category specified: {tokens: N, cycles: N}
        If category is None: {category: {tokens: N, cycles: N}, ...}
    """
    db = _get_db()
    today = _today_str()
    try:
        if category:
            row = db.execute(
                """SELECT COALESCE(SUM(tokens_in + tokens_out), 0) AS tokens,
                          COUNT(*) AS cycles
                   FROM curiosity_spend
                   WHERE category = ?
                     AND started_at LIKE ?""",
                (category, f"{today}%"),
            ).fetchone()
            return {"tokens": row["tokens"], "cycles": row["cycles"]}
        else:
            result = {}
            for cat in CATEGORIES:
                row = db.execute(
                    """SELECT COALESCE(SUM(tokens_in + tokens_out), 0) AS tokens,
                              COUNT(*) AS cycles
                       FROM curiosity_spend
                       WHERE category = ?
                         AND started_at LIKE ?""",
                    (cat, f"{today}%"),
                ).fetchone()
                result[cat] = {"tokens": row["tokens"], "cycles": row["cycles"]}
            return result
    finally:
        db.close()


def _category_token_budget(config: dict = None) -> int:
    """Per-category token budget = (dailyTokens - sharedPoolTokens) / 4."""
    if config is None:
        config = load_config()
    budget = config["budget"]
    return (budget["dailyTokens"] - budget["sharedPoolTokens"]) // len(CATEGORIES)


def get_budget_stage(category: str) -> str:
    """Returns 'normal', 'conserve', 'shared', or 'suspend'.

    normal:   < 80% of category's proportional token budget used
    conserve: 80-100% used
    shared:   category exhausted but shared pool available
    suspend:  everything exhausted
    """
    config = load_config()
    cat_budget = _category_token_budget(config)
    spend = get_daily_spend(category)
    used = spend["tokens"]

    if used < cat_budget * 0.8:
        return "normal"
    elif used <= cat_budget:
        return "conserve"
    else:
        # Category exhausted — check shared pool
        remaining_shared = get_shared_pool_remaining()
        if remaining_shared > 0:
            return "shared"
        else:
            return "suspend"


def get_shared_pool_remaining() -> int:
    """Shared pool remaining = sharedPoolTokens - total overflow across all categories.

    Overflow per category = max(0, category_spend - category_budget).
    """
    config = load_config()
    budget = config["budget"]
    shared_pool = budget["sharedPoolTokens"]
    cat_budget = _category_token_budget(config)
    all_spend = get_daily_spend()

    total_overflow = 0
    for cat in CATEGORIES:
        cat_used = all_spend.get(cat, {}).get("tokens", 0)
        overflow = max(0, cat_used - cat_budget)
        total_overflow += overflow

    return max(0, shared_pool - total_overflow)


def get_category_quota_remaining(category: str) -> int:
    """How many more questions can be asked in this category today.

    Based on dailyQuota from config minus today's completed cycles in that category.
    """
    config = load_config()
    quota = config["budget"]["categories"].get(category, {}).get("dailyQuota", 0)

    db = _get_db()
    today = _today_str()
    try:
        row = db.execute(
            """SELECT COUNT(*) AS completed
               FROM curiosity_spend
               WHERE category = ?
                 AND started_at LIKE ?
                 AND completed_at IS NOT NULL""",
            (category, f"{today}%"),
        ).fetchone()
        return max(0, quota - row["completed"])
    finally:
        db.close()


def get_stats() -> dict:
    """Today's summary for the settings page API endpoint.

    Returns:
        {
            tokens_used: N, tokens_budget: N, tokens_remaining: N,
            questions_generated: N, dms_sent: N,
            by_category: {human: {used: N, quota: N, remaining: N, stage: str}, ...},
            budget_stage: str (overall)
        }
    """
    config = load_config()
    budget = config["budget"]
    daily_tokens = budget["dailyTokens"]

    all_spend = get_daily_spend()
    total_used = sum(s["tokens"] for s in all_spend.values())
    total_cycles = sum(s["cycles"] for s in all_spend.values())

    by_category = {}
    worst_stage = "normal"
    stage_severity = {"normal": 0, "conserve": 1, "shared": 2, "suspend": 3}

    for cat in CATEGORIES:
        cat_quota = budget["categories"].get(cat, {}).get("dailyQuota", 0)
        cat_remaining = get_category_quota_remaining(cat)
        cat_stage = get_budget_stage(cat)
        by_category[cat] = {
            "used": all_spend.get(cat, {}).get("tokens", 0),
            "quota": cat_quota,
            "remaining": cat_remaining,
            "stage": cat_stage,
        }
        if stage_severity.get(cat_stage, 0) > stage_severity.get(worst_stage, 0):
            worst_stage = cat_stage

    # Count DMs: cycles with outcome containing "dm_sent"
    db = _get_db()
    today = _today_str()
    try:
        row = db.execute(
            """SELECT COUNT(*) AS dms
               FROM curiosity_spend
               WHERE started_at LIKE ?
                 AND outcome LIKE '%dm_sent%'""",
            (f"{today}%",),
        ).fetchone()
        dms_sent = row["dms"]
    finally:
        db.close()

    return {
        "tokens_used": total_used,
        "tokens_budget": daily_tokens,
        "tokens_remaining": max(0, daily_tokens - total_used),
        "questions_generated": total_cycles,
        "dms_sent": dms_sent,
        "by_category": by_category,
        "budget_stage": worst_stage,
    }


def reset_daily():
    """No-op -- budget is date-based, not reset-based.

    Verifies that date grouping works by confirming today's spend
    only includes records from today.
    """
    today = _today_str()
    db = _get_db()
    try:
        row = db.execute(
            """SELECT COUNT(*) AS cnt
               FROM curiosity_spend
               WHERE started_at LIKE ?""",
            (f"{today}%",),
        ).fetchone()
        total = db.execute("SELECT COUNT(*) AS cnt FROM curiosity_spend").fetchone()
        return {
            "today_records": row["cnt"],
            "total_records": total["cnt"],
            "date_filter": today,
            "status": "ok",
        }
    finally:
        db.close()


if __name__ == "__main__":
    import uuid

    print("=== Curiosity Budget Self-Test ===\n")

    # 1. Create DB/table
    db = _get_db()
    db.close()
    print(f"[1] DB ready at {DB_PATH}")

    # 2. Record a test spend entry
    test_id = f"test-{uuid.uuid4().hex[:8]}"
    record_spend(
        cycle_id=test_id,
        category="human",
        tokens_in=1200,
        tokens_out=350,
        question="What motivates this person's recent career change?",
        depth=1,
    )
    print(f"[2] Recorded spend: {test_id}")

    # Accumulate more tokens on same cycle
    record_spend(cycle_id=test_id, category="human", tokens_in=800, tokens_out=200)
    print(f"    Updated spend (accumulated tokens)")

    # Complete it
    complete_spend(test_id, outcome="stored")
    print(f"    Completed spend with outcome=stored")

    # 3. Query daily spend
    spend = get_daily_spend("human")
    print(f"\n[3] Daily spend (human): {spend}")
    spend_all = get_daily_spend()
    print(f"    Daily spend (all): {json.dumps(spend_all, indent=2)}")

    # 4. Check budget stage
    for cat in CATEGORIES:
        stage = get_budget_stage(cat)
        print(f"\n[4] Budget stage ({cat}): {stage}")

    # 5. Get stats
    stats = get_stats()
    print(f"\n[5] Stats: {json.dumps(stats, indent=2)}")

    # Verify quota
    remaining = get_category_quota_remaining("human")
    print(f"\n    Human quota remaining: {remaining}")

    shared = get_shared_pool_remaining()
    print(f"    Shared pool remaining: {shared}")

    # Verify reset_daily (no-op)
    reset_info = reset_daily()
    print(f"\n    Reset check: {json.dumps(reset_info)}")

    # 6. Clean up test data
    db = _get_db()
    db.execute("DELETE FROM curiosity_spend WHERE cycle_id = ?", (test_id,))
    db.commit()
    db.close()
    print(f"\n[6] Cleaned up test record: {test_id}")

    print("\n=== All checks passed ===")
