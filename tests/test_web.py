"""Smoke tests for the web UI.

Uses a FastAPI TestClient pointed at a throwaway SQLite DB seeded with a few
trades. Tests don't assert CSS — just that routes return 2xx, render expected
HTML snippets, and HTMX partial endpoints round-trip.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from khata.core.db import init_schema


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("KHATA_DB_PATH", str(db_path))
    monkeypatch.setenv("KHATA_MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("KHATA_USER", "default")
    monkeypatch.setenv("KHATA_SECRET", "test-secret")

    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)

    # Seed: 2 trades on 2026-04-15, 1 on 2026-04-16
    base = datetime(2026, 4, 15, 4, 0, tzinfo=UTC)
    for i, (day_off, sym, entry, exit_, net) in enumerate(
        [
            (0, "NIFTY 24300 PE", 10000, 10500, 37500),
            (0, "BANKNIFTY 51000 CE", 15000, 13000, -60000),
            (1, "NIFTY 24400 PE", 8000, 9200, 90000),
        ]
    ):
        ts = (base + timedelta(days=day_off, minutes=i * 30)).isoformat()
        exit_ts = (base + timedelta(days=day_off, minutes=i * 30 + 10)).isoformat()
        # First insert two executions
        for leg_i, side, qty, px in [(0, "BUY", 75, entry), (1, "SELL", 75, exit_)]:
            conn.execute(
                """INSERT INTO executions
                (user_id, broker, broker_trade_id, symbol, underlying, exchange, segment,
                 instrument_type, side, qty, price_paise, ts, brokerage_paise)
                VALUES (1, 'test', ?, ?, ?, 'NFO', 'NSE_FNO', 'OPT', ?, ?, ?, ?, 2000)""",
                (
                    f"t{i}-{leg_i}",
                    sym,
                    sym.split()[0],
                    side,
                    qty,
                    px,
                    ts if leg_i == 0 else exit_ts,
                ),
            )
        # Then insert the reconstructed trade directly (bypass round-trip engine for speed)
        conn.execute(
            """INSERT INTO trades
            (user_id, symbol, underlying, instrument_type, direction, qty,
             avg_entry_paise, avg_exit_paise, entry_ts, exit_ts,
             gross_pnl_paise, fees_paise, net_pnl_paise, status)
            VALUES (1, ?, ?, 'OPT', 'LONG', 75, ?, ?, ?, ?, ?, 500, ?, 'CLOSED')""",
            (sym, sym.split()[0], entry, exit_, ts, exit_ts, net + 500, net),
        )
    conn.close()
    return db_path


@pytest.fixture
def client(seeded_db):
    # Import after env is set so Config.load() picks up the tmp paths.
    if "khata.web.main" in os.sys.modules:
        del os.sys.modules["khata.web.main"]
    from khata.web.main import create_app

    return TestClient(create_app())


def test_root_redirects_to_current_month(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (301, 302, 307)
    assert r.headers["location"].startswith("/calendar/")


def test_calendar_page_renders(client):
    r = client.get("/calendar/2026/4")
    assert r.status_code == 200
    assert "April 2026" in r.text
    assert "month P&amp;L" in r.text
    # Days with trades are linked; 2026-04-15 should be there
    assert "/day/2026-04-15" in r.text


def test_calendar_invalid_month(client):
    r = client.get("/calendar/2026/13")
    assert r.status_code == 400


def test_day_page_renders_with_trades(client):
    r = client.get("/day/2026-04-15")
    assert r.status_code == 200
    assert "NIFTY 24300 PE" in r.text
    assert "BANKNIFTY 51000 CE" in r.text
    assert "Daily reflection" in r.text


def test_day_page_empty(client):
    r = client.get("/day/2026-01-01")
    assert r.status_code == 200
    assert "No trades on this day" in r.text


def test_day_invalid_date(client):
    r = client.get("/day/not-a-date")
    assert r.status_code == 400


def test_trade_page_renders(client):
    # trade id 1 should exist from fixture (fixture skips trade_legs for speed,
    # so 'Fills' section won't render — just check trade metadata + sections).
    r = client.get("/trade/1")
    assert r.status_code == 200
    assert "NIFTY 24300 PE" in r.text
    assert "Tags" in r.text
    assert "Notes" in r.text
    assert "avg entry" in r.text


def test_trade_404(client):
    r = client.get("/trade/9999")
    assert r.status_code == 404


def test_note_save_and_reload(client):
    r = client.post("/notes/trade/1", data={"body": "First thoughts on this trade"})
    assert r.status_code == 200
    assert "First thoughts" in r.text
    # Reload the page and confirm note persisted
    r2 = client.get("/trade/1")
    assert "First thoughts" in r2.text


def test_tag_add_and_remove(client):
    r = client.post("/tags/trade/1", data={"name": "fomo", "kind": "psych"})
    assert r.status_code == 200
    assert "fomo" in r.text

    # Find the tag id in the DB to build the delete URL
    import os as _os
    conn = sqlite3.connect(_os.environ["KHATA_DB_PATH"])
    conn.row_factory = sqlite3.Row
    tag_id = conn.execute("SELECT id FROM tags WHERE name='fomo'").fetchone()["id"]
    conn.close()

    r = client.delete(f"/tags/trade/1/{tag_id}")
    assert r.status_code == 200
    assert "fomo" not in r.text
    assert "no tags yet" in r.text


def test_daily_note_save(client):
    r = client.post("/notes/day/2026-04-15", data={"body": "Revenge traded after the morning loss"})
    assert r.status_code == 200
    assert "Revenge traded" in r.text

    r2 = client.get("/day/2026-04-15")
    assert "Revenge traded" in r2.text


def test_static_css_served(client):
    r = client.get("/static/style.css")
    assert r.status_code == 200
    assert "khata" in r.text.lower()  # our stylesheet header comment
