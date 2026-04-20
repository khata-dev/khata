"""FIFO round-trip reconstruction.

Given the stream of `executions` for a user, groups them into `trades`:

- An open trade is a non-zero net position in one contract.
- Same-direction fills extend the current trade (SCALE_IN).
- Opposite-direction fills reduce it (SCALE_OUT / EXIT).
- When qty hits zero the trade closes; any overshoot opens a new opposite trade.

This rebuilds from scratch on each run — O(n) in executions, fine for personal
volumes. We can switch to incremental processing later if someone has millions
of fills.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class _Lot:
    qty: int
    price_paise: int
    fees_alloc_paise: int
    execution_id: int


@dataclass
class _TradeState:
    direction: str  # 'LONG' | 'SHORT'
    symbol: str
    underlying: str | None
    instrument_type: str
    option_type: str | None
    strike_paise: int | None
    expiry: str | None
    entry_ts: str
    opened_qty: int = 0  # total qty opened (for avg_entry)
    entry_cost_paise: int = 0  # Σ qty * price for openings
    closed_qty: int = 0
    exit_proceeds_paise: int = 0  # Σ qty * price for closings
    fees_paise: int = 0
    exit_ts: str | None = None
    legs: list[tuple[int, str, int]] = field(default_factory=list)  # (exec_id, role, qty)
    lots: deque = field(default_factory=deque)


def _contract_key(row: sqlite3.Row) -> tuple:
    return (
        row["underlying"],
        row["instrument_type"],
        row["option_type"],
        row["strike_paise"],
        row["expiry"],
    )


def _fees_total(row: sqlite3.Row) -> int:
    return (
        (row["brokerage_paise"] or 0)
        + (row["stt_paise"] or 0)
        + (row["exch_txn_paise"] or 0)
        + (row["sebi_paise"] or 0)
        + (row["stamp_paise"] or 0)
        + (row["gst_paise"] or 0)
        + (row["ipft_paise"] or 0)
        + (row["other_paise"] or 0)
    )


def rebuild_trades(conn: sqlite3.Connection, user_id: int) -> dict:
    """Wipe trades/trade_legs for this user and rebuild from executions. Returns stats."""
    conn.execute("BEGIN")
    try:
        conn.execute(
            "DELETE FROM trade_legs WHERE trade_id IN (SELECT id FROM trades WHERE user_id = ?)",
            (user_id,),
        )
        conn.execute("DELETE FROM trades WHERE user_id = ?", (user_id,))

        execs = conn.execute(
            "SELECT * FROM executions WHERE user_id = ? ORDER BY ts, id",
            (user_id,),
        ).fetchall()

        grouped: dict[tuple, list[sqlite3.Row]] = defaultdict(list)
        for e in execs:
            grouped[_contract_key(e)].append(e)

        stats = {"contracts": len(grouped), "executions": len(execs), "trades": 0, "open": 0}

        for group in grouped.values():
            stats["trades"] += _process_contract(conn, user_id, group, stats)

        conn.execute("COMMIT")
        return stats
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _process_contract(
    conn: sqlite3.Connection,
    user_id: int,
    execs: list[sqlite3.Row],
    stats: dict,
) -> int:
    """Process all executions for one contract key. Returns trades written."""
    current: _TradeState | None = None
    trades_written = 0

    for e in execs:
        remaining = int(e["qty"])
        fee_per_unit = _fees_total(e) / e["qty"] if e["qty"] else 0
        while remaining > 0:
            if current is None:
                current = _TradeState(
                    direction="LONG" if e["side"] == "BUY" else "SHORT",
                    symbol=e["symbol"],
                    underlying=e["underlying"],
                    instrument_type=e["instrument_type"],
                    option_type=e["option_type"],
                    strike_paise=e["strike_paise"],
                    expiry=e["expiry"],
                    entry_ts=e["ts"],
                )
                fee_alloc = round(fee_per_unit * remaining)
                current.opened_qty += remaining
                current.entry_cost_paise += remaining * e["price_paise"]
                current.fees_paise += fee_alloc
                current.legs.append((e["id"], "ENTRY", remaining))
                current.lots.append(_Lot(remaining, e["price_paise"], fee_alloc, e["id"]))
                remaining = 0
                continue

            is_extending = (current.direction == "LONG" and e["side"] == "BUY") or (
                current.direction == "SHORT" and e["side"] == "SELL"
            )

            if is_extending:
                fee_alloc = round(fee_per_unit * remaining)
                current.opened_qty += remaining
                current.entry_cost_paise += remaining * e["price_paise"]
                current.fees_paise += fee_alloc
                current.legs.append((e["id"], "SCALE_IN", remaining))
                current.lots.append(_Lot(remaining, e["price_paise"], fee_alloc, e["id"]))
                remaining = 0
                continue

            # Reducing. Match FIFO.
            open_qty = sum(lot.qty for lot in current.lots)
            match_qty = min(remaining, open_qty)
            fee_alloc = round(fee_per_unit * match_qty)
            current.closed_qty += match_qty
            current.exit_proceeds_paise += match_qty * e["price_paise"]
            current.fees_paise += fee_alloc

            to_match = match_qty
            while to_match > 0 and current.lots:
                lot = current.lots[0]
                take = min(lot.qty, to_match)
                if take == lot.qty:
                    current.lots.popleft()
                else:
                    lot.qty -= take
                to_match -= take

            if not current.lots:
                current.legs.append((e["id"], "EXIT", match_qty))
                current.exit_ts = e["ts"]
                _persist_trade(conn, user_id, current, status="CLOSED")
                trades_written += 1
                current = None
            else:
                current.legs.append((e["id"], "SCALE_OUT", match_qty))

            remaining -= match_qty

            # If remaining > 0 after closing, loop reopens a new trade in opposite direction.

    if current is not None:
        _persist_trade(conn, user_id, current, status="OPEN")
        trades_written += 1
        stats["open"] += 1

    return trades_written


def _persist_trade(
    conn: sqlite3.Connection,
    user_id: int,
    t: _TradeState,
    *,
    status: str,
) -> int:
    avg_entry = t.entry_cost_paise // t.opened_qty if t.opened_qty else 0
    if status == "CLOSED" and t.closed_qty:
        avg_exit = t.exit_proceeds_paise // t.closed_qty
        if t.direction == "LONG":
            gross = t.exit_proceeds_paise - (avg_entry * t.closed_qty)
        else:
            gross = (avg_entry * t.closed_qty) - t.exit_proceeds_paise
        net = gross - t.fees_paise
        duration_s = _duration_s(t.entry_ts, t.exit_ts)
    else:
        avg_exit = None
        gross = None
        net = None
        duration_s = None

    cur = conn.execute(
        """
        INSERT INTO trades (
            user_id, symbol, underlying, instrument_type, option_type,
            strike_paise, expiry, direction, qty, avg_entry_paise, avg_exit_paise,
            entry_ts, exit_ts, gross_pnl_paise, fees_paise, net_pnl_paise,
            duration_s, status
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            t.symbol,
            t.underlying,
            t.instrument_type,
            t.option_type,
            t.strike_paise,
            t.expiry,
            t.direction,
            t.opened_qty,
            avg_entry,
            avg_exit,
            t.entry_ts,
            t.exit_ts,
            gross,
            t.fees_paise,
            net,
            duration_s,
            status,
        ),
    )
    trade_id = cur.lastrowid

    conn.executemany(
        "INSERT INTO trade_legs (trade_id, execution_id, leg_role, qty_contributed) "
        "VALUES (?, ?, ?, ?)",
        [(trade_id, leg[0], leg[1], leg[2]) for leg in t.legs],
    )
    return trade_id


def _duration_s(entry_iso: str | None, exit_iso: str | None) -> int | None:
    if not entry_iso or not exit_iso:
        return None
    a = datetime.fromisoformat(entry_iso.replace("Z", "+00:00"))
    b = datetime.fromisoformat(exit_iso.replace("Z", "+00:00"))
    return int((b - a).total_seconds())
