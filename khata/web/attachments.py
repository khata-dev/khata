"""Attachment handling for notes and trades.

Files live under KHATA_MEDIA_DIR in a date-sharded layout:
  <media_dir>/YYYY/MM/DD/<uuid><ext>

The `attachments` table carries the relative path and the owning note_id or
trade_id (XOR). Served back via GET /media/{path:path}.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException

from khata.config import Config

# Conservative allowlist for this PR — notes support images only.
# Video/audio/PDFs land in a later PR.
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_IMAGE_MIME = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _ext_from_filename(name: str | None) -> str:
    if not name:
        return ""
    return Path(name).suffix.lower()


def save_upload(
    cfg: Config,
    stream: BinaryIO,
    *,
    original_filename: str | None,
    content_type: str | None,
) -> tuple[Path, str, int, str, str]:
    """Write an upload to media_dir. Returns (abs_path, rel_path, size, mime, kind)."""
    ext = _ext_from_filename(original_filename)
    if ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(400, f"Unsupported file type: {ext or '(none)'}")
    if content_type and content_type not in ALLOWED_IMAGE_MIME:
        raise HTTPException(400, f"Unsupported content type: {content_type}")

    now = datetime.now()
    rel_dir = Path(f"{now.year:04d}/{now.month:02d}/{now.day:02d}")
    abs_dir = cfg.media_dir / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    fname = f"{uuid.uuid4().hex}{ext}"
    rel_path = rel_dir / fname
    abs_path = abs_dir / fname

    # Stream-copy with size cap.
    total = 0
    with open(abs_path, "wb") as out:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                out.close()
                abs_path.unlink(missing_ok=True)
                raise HTTPException(413, f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
            out.write(chunk)

    return (
        abs_path,
        str(rel_path).replace("\\", "/"),
        total,
        content_type or "image/octet-stream",
        "image",
    )


def record_attachment(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    trade_id: int | None,
    note_id: int | None,
    rel_path: str,
    mime: str,
    size: int,
    kind: str,
    caption: str | None = None,
) -> int:
    """Insert an attachments row. Exactly one of trade_id/note_id must be set."""
    if (trade_id is None) == (note_id is None):
        raise HTTPException(400, "attachment needs exactly one of trade_id or note_id")
    cur = conn.execute(
        """
        INSERT INTO attachments
          (user_id, trade_id, note_id, kind, path, mime, size_bytes, caption)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, trade_id, note_id, kind, rel_path, mime, size, caption),
    )
    return int(cur.lastrowid)


def attachments_for_note(conn: sqlite3.Connection, user_id: int, note_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, kind, path, mime, size_bytes, caption, created_at
        FROM attachments
        WHERE user_id = ? AND note_id = ?
        ORDER BY created_at
        """,
        (user_id, note_id),
    ).fetchall()


def attachments_for_trade(
    conn: sqlite3.Connection, user_id: int, trade_id: int
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, kind, path, mime, size_bytes, caption, created_at
        FROM attachments
        WHERE user_id = ? AND trade_id = ?
        ORDER BY created_at
        """,
        (user_id, trade_id),
    ).fetchall()


def ensure_note_for_date(conn: sqlite3.Connection, user_id: int, iso_date: str) -> int:
    row = conn.execute(
        "SELECT id FROM notes WHERE user_id = ? AND for_date = ?",
        (user_id, iso_date),
    ).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO notes (user_id, for_date, body_md) VALUES (?, ?, '')",
        (user_id, iso_date),
    )
    return int(cur.lastrowid)


def ensure_note_for_trade(conn: sqlite3.Connection, user_id: int, trade_id: int) -> int:
    row = conn.execute(
        "SELECT id FROM notes WHERE user_id = ? AND trade_id = ?",
        (user_id, trade_id),
    ).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO notes (user_id, trade_id, body_md) VALUES (?, ?, '')",
        (user_id, trade_id),
    )
    return int(cur.lastrowid)
