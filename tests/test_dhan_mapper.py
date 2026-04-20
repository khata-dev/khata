"""Regression tests for the Dhan → canonical mapper.

Covers the two response shapes observed in the wild:
  - /trades (today's book): per-fill, real exchangeTradeId, space-separated timestamps
  - /trades/{from}/{to}/{page} (history): aggregated per-order-per-day,
    exchangeTradeId='0', ISO-T timestamps, createTime/updateTime='NA'
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from khata.adapters.dhan.mapper import map_trade
from khata.core.adapter import InstrumentType, OptionType, Side

FIXTURES = Path(__file__).parent / "fixtures" / "dhan"


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())


# ── today's endpoint (per-fill) ────────────────────────────────────────
def test_today_uses_exchange_trade_id_as_canonical_id():
    row = _load("trades_today.json")[0]
    e = map_trade(row)
    assert e.broker_trade_id == "TEST_EXCH_TRADE_0001"
    assert e.broker_order_id == "TEST_ORDER_0001"


def test_today_parses_space_separated_timestamp_as_ist_to_utc():
    row = _load("trades_today.json")[0]  # "2026-04-21 09:35:12" IST
    e = map_trade(row)
    # 09:35:12 IST = 04:05:12 UTC
    assert e.ts == datetime(2026, 4, 21, 4, 5, 12, tzinfo=UTC)


def test_today_maps_fields_into_canonical():
    rows = _load("trades_today.json")
    buy = map_trade(rows[0])
    sell = map_trade(rows[1])

    assert buy.side == Side.BUY
    assert sell.side == Side.SELL
    assert buy.instrument_type == InstrumentType.OPT
    assert buy.option_type == OptionType.PE
    assert buy.strike_paise == 24300 * 100
    assert buy.qty == 75
    assert buy.price_paise == 10025  # ₹100.25
    assert buy.exchange == "NFO"
    assert buy.segment == "NSE_FNO"

    # Fees recorded in paise (rounded from rupees float)
    assert buy.fees.brokerage_paise == 2000  # ₹20.00
    assert sell.fees.stt_paise == 422  # ₹4.22


# ── history endpoint (aggregated, shape differs) ───────────────────────
def test_history_falls_back_to_order_id_when_trade_id_is_zero():
    """Without the fallback the DB's UNIQUE(broker, broker_trade_id) would
    collapse every history row to one — this is the critical fix."""
    row = _load("trades_history_page0.json")[0]
    assert row["exchangeTradeId"] == "0"
    e = map_trade(row)
    assert e.broker_trade_id == "TEST_HIST_ORDER_0001"
    assert e.broker_order_id == "TEST_HIST_ORDER_0001"


def test_history_parses_iso_t_timestamp_as_ist_to_utc():
    row = _load("trades_history_page0.json")[0]  # "2026-04-17T10:48:02" IST
    e = map_trade(row)
    # 10:48:02 IST = 05:18:02 UTC
    assert e.ts == datetime(2026, 4, 17, 5, 18, 2, tzinfo=UTC)


def test_history_handles_na_literal_in_create_time():
    """History rows set createTime='NA'. Mapper must not crash; exchangeTime
    is the authoritative source so we prefer it anyway."""
    row = _load("trades_history_page0.json")[0]
    assert row["createTime"] == "NA"
    e = map_trade(row)
    assert e.ts.tzinfo == UTC  # parsed from exchangeTime, not createTime


def test_history_custom_symbol_extracts_underlying_without_trailing_space():
    """'NIFTY 21 APR 24300 PUT' must yield 'NIFTY', not 'NIFTY ' (trailing
    space would break joins with the positions/quote feed later)."""
    row = _load("trades_history_page0.json")[0]
    e = map_trade(row)
    assert e.underlying == "NIFTY"
    assert e.symbol == "NIFTY 21 APR 24300 PUT"

    row2 = _load("trades_history_page0.json")[1]
    e2 = map_trade(row2)
    assert e2.underlying == "BANKNIFTY"


# ── shared behaviours ──────────────────────────────────────────────────
@pytest.mark.parametrize("fixture_name", ["trades_today.json", "trades_history_page0.json"])
def test_every_fixture_row_produces_a_canonical_execution(fixture_name):
    rows = _load(fixture_name)
    assert rows, f"fixture {fixture_name} is empty"
    for row in rows:
        e = map_trade(row)
        assert e.broker == "dhan"
        assert e.broker_trade_id  # never empty — this is the dedup key
        assert e.qty > 0
        assert e.price_paise > 0
        assert e.ts.tzinfo is UTC


def test_mapper_handles_missing_na_exchange_time():
    """If exchangeTime itself is 'NA', we fall back to now(UTC) not crash."""
    row = _load("trades_today.json")[0].copy()
    row["exchangeTime"] = "NA"
    row["updateTime"] = "NA"
    row["createTime"] = "NA"
    e = map_trade(row)
    assert e.ts.tzinfo is UTC  # defaulted to now, no exception
