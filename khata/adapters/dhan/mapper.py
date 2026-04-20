"""Map Dhan API response shapes into khata's canonical types.

Dhan v2 trade-book row (key fields used here):
  dhanClientId, orderId, exchangeOrderId, exchangeTradeId,
  transactionType ("BUY"|"SELL"),
  exchangeSegment ("NSE_EQ"|"NSE_FNO"|"BSE_EQ"|"BSE_FNO"|"MCX_COMM"|"NSE_CURRENCY"),
  productType ("INTRADAY"|"CNC"|"MARGIN"|"MIS"|"NRML"|"BO"|"CO"),
  orderType, tradingSymbol, customSymbol, securityId,
  tradedQuantity (int), tradedPrice (float, rupees),
  isin, instrument ("EQUITY"|"FUTIDX"|"OPTIDX"|"FUTSTK"|"OPTSTK"|"FUTCUR"|"OPTCUR"),
  sebiTax, stt, brokerageCharges, serviceTax,
  exchangeTransactionCharges, stampDuty, ipft,
  createTime / updateTime / exchangeTime ("YYYY-MM-DD HH:MM:SS" IST),
  drvExpiryDate ("YYYY-MM-DD"), drvOptionType ("CALL"|"PUT"|""), drvStrikePrice (float).

Not every row has every field. Equity cash rows have no drv* fields.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from khata.core.adapter import (
    CanonicalExecution,
    CanonicalFees,
    InstrumentType,
    OptionType,
    Side,
)
from khata.core.money import rupees_to_paise

IST = ZoneInfo("Asia/Kolkata")


_SEGMENT_TO_EXCHANGE = {
    "NSE_EQ": "NSE",
    "NSE_FNO": "NFO",
    "NSE_CURRENCY": "CDS",
    "BSE_EQ": "BSE",
    "BSE_FNO": "BFO",
    "MCX_COMM": "MCX",
}

_INSTRUMENT_TO_CANONICAL = {
    "EQUITY": InstrumentType.EQ,
    "FUTIDX": InstrumentType.FUT,
    "FUTSTK": InstrumentType.FUT,
    "FUTCUR": InstrumentType.FUT,
    "FUTCOM": InstrumentType.FUT,
    "OPTIDX": InstrumentType.OPT,
    "OPTSTK": InstrumentType.OPT,
    "OPTCUR": InstrumentType.OPT,
    "OPTFUT": InstrumentType.OPT,
}

_OPTION_TYPE = {
    "CALL": OptionType.CE,
    "CE": OptionType.CE,
    "PUT": OptionType.PE,
    "PE": OptionType.PE,
    "": None,
    None: None,
}


def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)
    # Dhan timestamps are IST, "YYYY-MM-DD HH:MM:SS"
    dt = datetime.strptime(raw.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    return dt.astimezone(UTC)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _underlying_from_symbol(trading_symbol: str | None, custom_symbol: str | None) -> str | None:
    """Best-effort underlying extraction. e.g. 'NIFTY25APR25350CE' → 'NIFTY'."""
    src = custom_symbol or trading_symbol or ""
    # Strip digits-and-suffix tail
    for i, ch in enumerate(src):
        if ch.isdigit():
            return src[:i] or None
    return src or None


def map_trade(row: dict, broker: str = "dhan") -> CanonicalExecution:
    """Map one Dhan trade-book row to a CanonicalExecution."""
    segment = row.get("exchangeSegment") or ""
    exchange = _SEGMENT_TO_EXCHANGE.get(segment, segment.split("_")[0] or "NSE")

    instrument_raw = row.get("instrument") or ""
    instrument_type = _INSTRUMENT_TO_CANONICAL.get(instrument_raw, InstrumentType.EQ)

    side = Side.BUY if (row.get("transactionType") or "").upper() == "BUY" else Side.SELL

    strike_rupees = row.get("drvStrikePrice")
    strike_paise = rupees_to_paise(strike_rupees) if strike_rupees else None

    fees = CanonicalFees(
        brokerage_paise=rupees_to_paise(row.get("brokerageCharges")),
        stt_paise=rupees_to_paise(row.get("stt")),
        exch_txn_paise=rupees_to_paise(row.get("exchangeTransactionCharges")),
        sebi_paise=rupees_to_paise(row.get("sebiTax")),
        stamp_paise=rupees_to_paise(row.get("stampDuty")),
        gst_paise=rupees_to_paise(row.get("serviceTax")),
        ipft_paise=rupees_to_paise(row.get("ipft")),
    )

    return CanonicalExecution(
        broker=broker,
        broker_trade_id=str(row.get("exchangeTradeId") or row.get("orderId") or ""),
        broker_order_id=str(row.get("orderId") or "") or None,
        symbol=row.get("customSymbol") or row.get("tradingSymbol") or "",
        underlying=_underlying_from_symbol(row.get("tradingSymbol"), row.get("customSymbol")),
        exchange=exchange,
        segment=segment or exchange,
        instrument_type=instrument_type,
        option_type=_OPTION_TYPE.get(row.get("drvOptionType")),
        strike_paise=strike_paise,
        expiry=_parse_date(row.get("drvExpiryDate")),
        side=side,
        qty=int(row.get("tradedQuantity") or 0),
        price_paise=rupees_to_paise(row.get("tradedPrice")),
        ts=_parse_ts(row.get("exchangeTime") or row.get("updateTime") or row.get("createTime")),
        product_type=row.get("productType"),
        fees=fees,
        raw=row,
    )
