"""Round-trip engine tests.

Insert synthetic executions directly into SQLite (no broker), then assert the
resulting trades. This is the unit test that guards FIFO correctness forever.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from khata.core.db import init_schema
from khata.core.roundtrip import rebuild_trades

SCHEMA_PATH = Path(__file__).parent.parent / "khata" / "core" / "schema.sql"


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "t.db"
    c = sqlite3.connect(db, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    init_schema(c)
    yield c
    c.close()


def _ins(conn, *, ts, side, qty, price_paise, symbol="NIFTY-TEST", broker_trade_id=None, fees=0):
    broker_trade_id = broker_trade_id or f"t-{ts.isoformat()}-{side}-{qty}"
    conn.execute(
        """INSERT INTO executions (
            user_id, broker, broker_trade_id, symbol, underlying, exchange, segment,
            instrument_type, side, qty, price_paise, ts, brokerage_paise
        ) VALUES (1, 'test', ?, ?, 'NIFTY', 'NFO', 'NSE_FNO', 'EQ', ?, ?, ?, ?, ?)""",
        (broker_trade_id, symbol, side, qty, price_paise, ts.isoformat(), fees),
    )


def _ts(offset_min=0):
    return datetime(2026, 4, 15, 9, 30, tzinfo=UTC) + timedelta(minutes=offset_min)


def test_simple_round_trip(conn):
    _ins(conn, ts=_ts(0), side="BUY", qty=100, price_paise=10000)  # ₹100
    _ins(conn, ts=_ts(5), side="SELL", qty=100, price_paise=10500)  # ₹105

    rebuild_trades(conn, user_id=1)
    rows = conn.execute("SELECT * FROM trades").fetchall()

    assert len(rows) == 1
    t = rows[0]
    assert t["status"] == "CLOSED"
    assert t["direction"] == "LONG"
    assert t["qty"] == 100
    assert t["avg_entry_paise"] == 10000
    assert t["avg_exit_paise"] == 10500
    assert t["gross_pnl_paise"] == 50000  # 100 * (10500-10000)
    assert t["duration_s"] == 300


def test_scale_in_then_full_exit(conn):
    _ins(conn, ts=_ts(0), side="BUY", qty=50, price_paise=10000)
    _ins(conn, ts=_ts(3), side="BUY", qty=50, price_paise=10200)
    _ins(conn, ts=_ts(10), side="SELL", qty=100, price_paise=10500)

    rebuild_trades(conn, user_id=1)
    rows = conn.execute("SELECT * FROM trades").fetchall()

    assert len(rows) == 1
    t = rows[0]
    assert t["qty"] == 100
    assert t["avg_entry_paise"] == 10100  # (50*100 + 50*102)/100
    assert t["gross_pnl_paise"] == (10500 - 10100) * 100


def test_partial_exit_leaves_trade_open(conn):
    _ins(conn, ts=_ts(0), side="BUY", qty=100, price_paise=10000)
    _ins(conn, ts=_ts(5), side="SELL", qty=40, price_paise=10500)

    rebuild_trades(conn, user_id=1)
    rows = conn.execute("SELECT * FROM trades").fetchall()

    assert len(rows) == 1
    assert rows[0]["status"] == "OPEN"
    assert rows[0]["qty"] == 100  # opened qty
    assert rows[0]["gross_pnl_paise"] is None  # still open


def test_overshoot_opens_opposite_trade(conn):
    _ins(conn, ts=_ts(0), side="BUY", qty=100, price_paise=10000)
    _ins(conn, ts=_ts(5), side="SELL", qty=150, price_paise=10500)

    rebuild_trades(conn, user_id=1)
    rows = conn.execute("SELECT * FROM trades ORDER BY entry_ts").fetchall()

    assert len(rows) == 2
    long_trade, short_trade = rows[0], rows[1]

    assert long_trade["direction"] == "LONG"
    assert long_trade["status"] == "CLOSED"
    assert long_trade["qty"] == 100
    assert long_trade["gross_pnl_paise"] == 50000

    assert short_trade["direction"] == "SHORT"
    assert short_trade["status"] == "OPEN"
    assert short_trade["qty"] == 50
    assert short_trade["avg_entry_paise"] == 10500


def test_separate_contracts_are_independent(conn):
    _ins(conn, ts=_ts(0), side="BUY", qty=100, price_paise=10000, symbol="A", broker_trade_id="a1")
    _ins(conn, ts=_ts(2), side="BUY", qty=50, price_paise=20000, symbol="B", broker_trade_id="b1")
    # Note: current schema groups by underlying+instrument+option+strike+expiry.
    # Here both rows have underlying=NIFTY, so they merge. Use per-test schema tweak:
    conn.execute("UPDATE executions SET underlying='A' WHERE broker_trade_id='a1'")
    conn.execute("UPDATE executions SET underlying='B' WHERE broker_trade_id='b1'")

    rebuild_trades(conn, user_id=1)
    rows = conn.execute("SELECT underlying, status FROM trades ORDER BY underlying").fetchall()
    assert [(r["underlying"], r["status"]) for r in rows] == [("A", "OPEN"), ("B", "OPEN")]
