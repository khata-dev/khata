"""Persist canonical objects into SQLite. Idempotent: re-running a sync skips rows already seen."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable

from khata.core.adapter import CanonicalExecution


def upsert_broker_event(
    conn: sqlite3.Connection,
    user_id: int,
    broker: str,
    event_type: str,
    external_id: str | None,
    payload: dict,
) -> int | None:
    """Record a raw broker response. Returns the row id, or None if already present."""
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO broker_events (user_id, broker, event_type, external_id, payload_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, broker, event_type, external_id, json.dumps(payload, default=str)),
    )
    return cur.lastrowid if cur.rowcount else None


def upsert_executions(
    conn: sqlite3.Connection,
    user_id: int,
    executions: Iterable[CanonicalExecution],
) -> int:
    """Insert executions. Skips duplicates by (broker, broker_trade_id). Returns rows inserted."""
    inserted = 0
    for e in executions:
        raw_event_id = upsert_broker_event(
            conn,
            user_id=user_id,
            broker=e.broker,
            event_type="trade",
            external_id=e.broker_trade_id,
            payload=e.raw,
        )
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO executions (
                user_id, broker, broker_order_id, broker_trade_id,
                symbol, underlying, exchange, segment, instrument_type,
                option_type, strike_paise, expiry, side, qty, price_paise, ts,
                product_type,
                brokerage_paise, stt_paise, exch_txn_paise, sebi_paise,
                stamp_paise, gst_paise, ipft_paise, other_paise,
                raw_event_id
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?
            )
            """,
            (
                user_id,
                e.broker,
                e.broker_order_id,
                e.broker_trade_id,
                e.symbol,
                e.underlying,
                e.exchange,
                e.segment,
                e.instrument_type.value,
                e.option_type.value if e.option_type else None,
                e.strike_paise,
                e.expiry.isoformat() if e.expiry else None,
                e.side.value,
                e.qty,
                e.price_paise,
                e.ts.isoformat(),
                e.product_type,
                e.fees.brokerage_paise,
                e.fees.stt_paise,
                e.fees.exch_txn_paise,
                e.fees.sebi_paise,
                e.fees.stamp_paise,
                e.fees.gst_paise,
                e.fees.ipft_paise,
                e.fees.other_paise,
                raw_event_id,
            ),
        )
        if cur.rowcount:
            inserted += 1
    return inserted
