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


# ── unsettled today rows: hyphenated tradingSymbol + 'NA' drvOptionType + no fees ──
def test_underlying_handles_hyphenated_tradingSymbol():
    """Today's /trades returns 'NIFTY-Apr2026-24300-PE' with null customSymbol.
    Extractor must stop at first hyphen, not at 'Apr'."""
    row = _load("trades_today_unsettled.json")[0]
    assert row["tradingSymbol"] == "NIFTY-Apr2026-24300-PE"
    assert row["customSymbol"] is None
    e = map_trade(row)
    assert e.underlying == "NIFTY"


def test_option_type_falls_back_to_symbol_when_drv_is_na():
    """drvOptionType='NA' is common on today's rows. Parser must read the
    '-PE' suffix off tradingSymbol instead."""
    row = _load("trades_today_unsettled.json")[0]
    assert row["drvOptionType"] == "NA"
    e = map_trade(row)
    assert e.option_type == OptionType.PE


def test_option_type_still_preferred_from_drv_when_valid():
    """Don't regress the primary path: if drvOptionType is populated, use it."""
    row = _load("trades_today.json")[0]
    assert row["drvOptionType"] == "PUT"
    e = map_trade(row)
    assert e.option_type == OptionType.PE


def test_unsettled_row_maps_with_zero_fees():
    """The mapper doesn't invent fees. Recompute happens at adapter layer."""
    row = _load("trades_today_unsettled.json")[0]
    e = map_trade(row)
    assert e.fees.total_paise == 0


# ── charges_for: Indian F&O fee recomputation ─────────────────────────
def test_charges_for_computes_standard_fno_fees():
    from khata.adapters.dhan.fees import compute_fno_options_fees

    row = _load("trades_today_unsettled.json")[0]  # BUY 195 @ ₹100.20
    e = map_trade(row)
    fees = compute_fno_options_fees(e)

    # Turnover = 195 * 100.20 = ₹19,539
    # Brokerage = min(₹20, 19539 * 0.0003) = min(20, 5.86) = ₹5.86
    assert 500 <= fees.brokerage_paise <= 600  # ~₹5.86 = 586 paise
    # STT BUY side only for options = 0
    assert fees.stt_paise == 0
    # Stamp duty on BUY = 0.003% of 19539 = ~₹0.59
    assert 50 <= fees.stamp_paise <= 70
    # Exchange txn = 0.03503% of 19539 = ~₹6.84
    assert 650 <= fees.exch_txn_paise <= 750
    # Total > 0
    assert fees.total_paise > 0


def test_charges_for_sell_adds_stt():
    from khata.adapters.dhan.fees import compute_fno_options_fees

    row = _load("trades_today_unsettled.json")[1]  # SELL 195 @ ₹88
    e = map_trade(row)
    fees = compute_fno_options_fees(e)

    # Turnover = 195 * 88 = ₹17,160
    # STT SELL side = 0.0625% of 17160 = ~₹10.73
    assert 1050 <= fees.stt_paise <= 1100
    # Stamp duty SELL side = 0
    assert fees.stamp_paise == 0


def test_charges_for_returns_none_for_non_options():
    """Futures and equity formulas differ — return None rather than pollute."""
    from khata.adapters.dhan.fees import compute_fees
    from khata.core.adapter import (
        CanonicalExecution,
        CanonicalFees,
    )
    from khata.core.adapter import (
        InstrumentType as IT,
    )
    from khata.core.adapter import (
        Side as S,
    )

    eq_exec = CanonicalExecution(
        broker="dhan",
        broker_trade_id="x",
        broker_order_id="x",
        symbol="RELIANCE",
        underlying="RELIANCE",
        exchange="NSE",
        segment="NSE_EQ",
        instrument_type=IT.EQ,
        option_type=None,
        strike_paise=None,
        expiry=None,
        side=S.BUY,
        qty=10,
        price_paise=300000,
        ts=datetime(2026, 4, 20, tzinfo=UTC),
        product_type="CNC",
        fees=CanonicalFees(),
        raw={},
    )
    assert compute_fees(eq_exec) is None
