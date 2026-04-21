"""Smoke tests for image upload + media serving + markdown rendering."""

from __future__ import annotations

import io
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from khata.core.db import init_schema


@pytest.fixture
def app_and_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    media_dir = tmp_path / "media"
    monkeypatch.setenv("KHATA_DB_PATH", str(db_path))
    monkeypatch.setenv("KHATA_MEDIA_DIR", str(media_dir))
    monkeypatch.setenv("KHATA_USER", "default")
    monkeypatch.setenv("KHATA_SECRET", "test-secret")

    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    # Seed one trade so /upload/note/trade/1 works.
    conn.execute(
        """INSERT INTO trades
        (user_id, symbol, underlying, instrument_type, direction, qty,
         avg_entry_paise, entry_ts, status)
        VALUES (1, 'NIFTY 24300 PE', 'NIFTY', 'OPT', 'LONG', 75,
                10000, '2026-04-15T04:00:00+00:00', 'OPEN')""",
    )
    conn.close()

    if "khata.web.main" in os.sys.modules:
        del os.sys.modules["khata.web.main"]
    from khata.web.main import create_app

    return TestClient(create_app()), db_path, media_dir


# Smallest valid PNG (1x1 red pixel).
ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d4944415478da62f8cfc0000000030001004d5f1b6e0000000049454e44ae426082"
)


def test_upload_to_daily_note_stores_file_and_row(app_and_db):
    client, db_path, media_dir = app_and_db
    r = client.post(
        "/upload/note/day/2026-04-15",
        files={"file": ("shot.png", ONE_PIXEL_PNG, "image/png")},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["url"].startswith("/media/")
    assert j["url"].endswith(".png")
    # File actually on disk
    rel = j["url"].removeprefix("/media/")
    assert (media_dir / rel).is_file()
    # Attachment row exists and points at the day's note
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM attachments").fetchone()
    assert row is not None
    assert row["kind"] == "image"
    assert row["note_id"] is not None
    assert row["trade_id"] is None
    conn.close()


def test_upload_to_trade_note_links_to_trade(app_and_db):
    client, db_path, _ = app_and_db
    r = client.post(
        "/upload/note/trade/1",
        files={"file": ("chart.png", ONE_PIXEL_PNG, "image/png")},
    )
    assert r.status_code == 200
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # note got auto-created for trade
    note = conn.execute("SELECT * FROM notes WHERE trade_id=1").fetchone()
    assert note is not None
    att = conn.execute("SELECT * FROM attachments").fetchone()
    assert att["note_id"] == note["id"]
    conn.close()


def test_upload_rejects_non_image(app_and_db):
    client, _, _ = app_and_db
    r = client.post(
        "/upload/note/day/2026-04-15",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400


def test_upload_rejects_oversize(app_and_db, monkeypatch):
    # Force the cap low so we don't have to send 10MB of bytes.
    from khata.web import attachments as A

    monkeypatch.setattr(A, "MAX_UPLOAD_BYTES", 100)
    client, _, _ = app_and_db
    huge = io.BytesIO(b"\x00" * 500)
    r = client.post(
        "/upload/note/day/2026-04-15",
        files={"file": ("big.png", huge.getvalue(), "image/png")},
    )
    assert r.status_code == 413


def test_media_path_traversal_blocked(app_and_db):
    client, _, _ = app_and_db
    r = client.get("/media/../../etc/passwd")
    # 404 because resolved target falls outside media_dir
    assert r.status_code == 404


def test_media_missing_file_404(app_and_db):
    client, _, _ = app_and_db
    r = client.get("/media/does/not/exist.png")
    assert r.status_code == 404


def test_media_serves_uploaded_file(app_and_db):
    client, _, _ = app_and_db
    up = client.post(
        "/upload/note/day/2026-04-15",
        files={"file": ("a.png", ONE_PIXEL_PNG, "image/png")},
    )
    url = up.json()["url"]
    r = client.get(url)
    assert r.status_code == 200
    assert r.content == ONE_PIXEL_PNG


def test_upload_for_missing_trade_404(app_and_db):
    client, _, _ = app_and_db
    r = client.post(
        "/upload/note/trade/9999",
        files={"file": ("a.png", ONE_PIXEL_PNG, "image/png")},
    )
    assert r.status_code == 404


def test_markdown_render_handles_images_and_formatting():
    from khata.web.markdown import render

    html = render("# Title\n\n**bold** and *italic*\n\n![shot](/media/2026/04/15/abc.png)")
    assert "<h1>" in html
    assert "<strong>" in html
    assert '<img src="/media/2026/04/15/abc.png"' in html
    assert 'alt="shot"' in html


def test_markdown_render_escapes_raw_html():
    """We don't allow inline HTML in notes."""
    from khata.web.markdown import render

    html = render("<script>alert(1)</script>\n\nSafe paragraph")
    assert "<script>" not in html
    assert "Safe paragraph" in html


def test_attachments_show_in_day_view(app_and_db):
    client, _, _ = app_and_db
    client.post(
        "/upload/note/day/2026-04-15",
        files={"file": ("x.png", ONE_PIXEL_PNG, "image/png")},
    )
    r = client.get("/day/2026-04-15")
    assert r.status_code == 200
    assert 'class="attachments"' in r.text
    assert 'class="attachment"' in r.text
    assert "/media/" in r.text


def test_editor_assets_served(app_and_db):
    client, _, _ = app_and_db
    for path in [
        "/static/vendor/easymde/easymde.min.css",
        "/static/vendor/easymde/easymde.min.js",
        "/static/editor.js",
    ]:
        r = client.get(path)
        assert r.status_code == 200, path
