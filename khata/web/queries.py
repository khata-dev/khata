"""SQL query layer for the web UI. Returns plain dicts/rows ready for templates."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from typing import Any


# ── calendar ───────────────────────────────────────────────────────────
def expiry_days_in_range(
    conn: sqlite3.Connection, user_id: int, start: date, end_excl: date
) -> frozenset[date]:
    """Distinct `trades.expiry` values falling inside [start, end_excl).

    Used to mark calendar days the user actually had an expiring contract on,
    rather than hardcoding Tue/Thu. Empty set if the user has no derivative
    trades or no data yet.
    """
    rows = conn.execute(
        """
        SELECT DISTINCT expiry
        FROM trades
        WHERE user_id = ?
          AND expiry IS NOT NULL
          AND expiry >= ?
          AND expiry < ?
        """,
        (user_id, start.isoformat(), end_excl.isoformat()),
    ).fetchall()
    out: set[date] = set()
    for r in rows:
        try:
            out.add(date.fromisoformat(r["expiry"]))
        except (TypeError, ValueError):
            continue
    return frozenset(out)


def month_summary_by_day(
    conn: sqlite3.Connection, user_id: int, year: int, month: int
) -> dict[str, dict[str, Any]]:
    """Per-day summary for one month, keyed by ISO date string.

    Uses entry_ts date in the database's UTC representation. For a first cut
    that's acceptable — intraday IST trades all fall on their IST date anyway
    since IST is UTC+5:30 and Indian markets close ~10:00 UTC.
    """
    # strftime on the ISO string picks the YYYY-MM-DD prefix.
    first = f"{year:04d}-{month:02d}-01"
    # Next month's first day as exclusive upper bound.
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    last_excl = f"{ny:04d}-{nm:02d}-01"

    rows = conn.execute(
        """
        SELECT
            substr(entry_ts, 1, 10) AS day,
            COUNT(*) AS n,
            SUM(CASE WHEN net_pnl_paise > 0 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN net_pnl_paise <= 0 AND status='CLOSED' THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) AS opens,
            COALESCE(SUM(net_pnl_paise), 0) AS net_paise
        FROM trades
        WHERE user_id = ?
          AND entry_ts >= ?
          AND entry_ts < ?
        GROUP BY day
        """,
        (user_id, first, last_excl),
    ).fetchall()
    return {r["day"]: dict(r) for r in rows}


# ── day ────────────────────────────────────────────────────────────────
def trades_on_day(conn: sqlite3.Connection, user_id: int, d: date) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, symbol, underlying, instrument_type, option_type, strike_paise,
               expiry, direction, qty, avg_entry_paise, avg_exit_paise,
               gross_pnl_paise, net_pnl_paise, fees_paise, entry_ts, exit_ts,
               duration_s, status, strategy_id
        FROM trades
        WHERE user_id = ? AND substr(entry_ts, 1, 10) = ?
        ORDER BY entry_ts
        """,
        (user_id, d.isoformat()),
    ).fetchall()


def day_totals(trades: list[sqlite3.Row]) -> dict[str, Any]:
    wins = sum(1 for t in trades if (t["net_pnl_paise"] or 0) > 0)
    losses = sum(1 for t in trades if t["status"] == "CLOSED" and (t["net_pnl_paise"] or 0) <= 0)
    net = sum((t["net_pnl_paise"] or 0) for t in trades)
    fees = sum((t["fees_paise"] or 0) for t in trades)
    return {
        "count": len(trades),
        "wins": wins,
        "losses": losses,
        "net_paise": net,
        "fees_paise": fees,
    }


# ── trade ──────────────────────────────────────────────────────────────
def trade_by_id(conn: sqlite3.Connection, user_id: int, trade_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM trades WHERE user_id = ? AND id = ?",
        (user_id, trade_id),
    ).fetchone()


def executions_for_trade(conn: sqlite3.Connection, trade_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT e.side, e.qty, e.price_paise, e.ts, l.leg_role, l.qty_contributed
        FROM trade_legs l
        JOIN executions e ON e.id = l.execution_id
        WHERE l.trade_id = ?
        ORDER BY e.ts, e.id
        """,
        (trade_id,),
    ).fetchall()


# ── notes ──────────────────────────────────────────────────────────────
def get_trade_note(conn: sqlite3.Connection, user_id: int, trade_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM notes WHERE user_id = ? AND trade_id = ?",
        (user_id, trade_id),
    ).fetchone()


def set_trade_note(
    conn: sqlite3.Connection, user_id: int, trade_id: int, body_md: str
) -> sqlite3.Row:
    existing = get_trade_note(conn, user_id, trade_id)
    now = datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"
    if existing:
        conn.execute(
            "UPDATE notes SET body_md = ?, updated_at = ? WHERE id = ?",
            (body_md, now, existing["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO notes (user_id, trade_id, body_md, updated_at, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, trade_id, body_md, now, now),
        )
    return get_trade_note(conn, user_id, trade_id)  # type: ignore[return-value]


def get_daily_note(conn: sqlite3.Connection, user_id: int, d: date) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM notes WHERE user_id = ? AND for_date = ?",
        (user_id, d.isoformat()),
    ).fetchone()


def set_daily_note(conn: sqlite3.Connection, user_id: int, d: date, body_md: str) -> sqlite3.Row:
    existing = get_daily_note(conn, user_id, d)
    now = datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"
    if existing:
        conn.execute(
            "UPDATE notes SET body_md = ?, updated_at = ? WHERE id = ?",
            (body_md, now, existing["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO notes (user_id, for_date, body_md, updated_at, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, d.isoformat(), body_md, now, now),
        )
    return get_daily_note(conn, user_id, d)  # type: ignore[return-value]


# ── tags ───────────────────────────────────────────────────────────────
def tags_for_trade(conn: sqlite3.Connection, user_id: int, trade_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT t.id, t.name, t.kind
        FROM tags t
        JOIN trade_tags tt ON tt.tag_id = t.id
        WHERE t.user_id = ? AND tt.trade_id = ?
        ORDER BY t.kind, t.name
        """,
        (user_id, trade_id),
    ).fetchall()


def add_tag_to_trade(
    conn: sqlite3.Connection, user_id: int, trade_id: int, name: str, kind: str = "custom"
) -> None:
    name = name.strip()
    if not name:
        return
    # Upsert tag.
    conn.execute(
        "INSERT OR IGNORE INTO tags (user_id, name, kind) VALUES (?, ?, ?)",
        (user_id, name, kind),
    )
    row = conn.execute(
        "SELECT id FROM tags WHERE user_id = ? AND name = ?",
        (user_id, name),
    ).fetchone()
    if row:
        conn.execute(
            "INSERT OR IGNORE INTO trade_tags (trade_id, tag_id) VALUES (?, ?)",
            (trade_id, row["id"]),
        )


def remove_tag_from_trade(conn: sqlite3.Connection, trade_id: int, tag_id: int) -> None:
    conn.execute(
        "DELETE FROM trade_tags WHERE trade_id = ? AND tag_id = ?",
        (trade_id, tag_id),
    )
