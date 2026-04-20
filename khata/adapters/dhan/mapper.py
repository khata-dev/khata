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
    "NA": None,
    None: None,
}


def _parse_ts(raw: str | None) -> datetime:
    """Parse Dhan timestamps. IST-local, no tz suffix. Two formats observed:
    - '/trades' (today):   'YYYY-MM-DD HH:MM:SS'
    - '/trades/.../{p}' (history): 'YYYY-MM-DDTHH:MM:SS'
    The literal string 'NA' appears on some history rows.
    """
    if not raw or raw.strip() in ("", "NA"):
        return datetime.now(UTC)
    s = raw.strip().replace("T", " ")
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    return dt.astimezone(UTC)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _underlying_from_symbol(trading_symbol: str | None, custom_symbol: str | None) -> str | None:
    """Extract the underlying from a Dhan symbol.

    Three observed formats in the wild:
      - 'NIFTY24APR2624300PE'       (concat, history equity/options)
      - 'NIFTY 21 APR 24300 PUT'    (space-separated, history options customSymbol)
      - 'NIFTY-Apr2026-24300-PE'    (hyphenated, today's /trades tradingSymbol)

    The underlying is always the first token. Stop at first digit, hyphen, or
    whitespace.
    """
    src = custom_symbol or trading_symbol or ""
    for i, ch in enumerate(src):
        if ch.isdigit() or ch in "- \t":
            return src[:i].strip() or None
    return src.strip() or None


def _option_type_from_symbol(
    trading_symbol: str | None, custom_symbol: str | None
) -> OptionType | None:
    """Fallback option-type parser when drvOptionType is 'NA' or missing.

    Checks the symbol tail for '-CE'/'-PE'/'CE'/'PE'/'CALL'/'PUT'.
    """
    src = (custom_symbol or trading_symbol or "").upper().strip()
    if not src:
        return None
    for suffix, ot in (
        ("-CE", OptionType.CE),
        ("-PE", OptionType.PE),
        (" CALL", OptionType.CE),
        (" PUT", OptionType.PE),
        ("CE", OptionType.CE),
        ("PE", OptionType.PE),
    ):
        if src.endswith(suffix):
            return ot
    return None


def _infer_instrument_type(row: dict) -> InstrumentType:
    """Today's /trades omits the `instrument` field. Infer it.

    Priority: explicit `instrument` → option markers → FNO segment fallback → EQ.
    """
    explicit = row.get("instrument") or ""
    if explicit in _INSTRUMENT_TO_CANONICAL:
        return _INSTRUMENT_TO_CANONICAL[explicit]

    segment = (row.get("exchangeSegment") or "").upper()

    has_option_markers = (
        row.get("drvStrikePrice") not in (None, 0)
        or (row.get("drvOptionType") or "").upper() in ("CALL", "PUT", "CE", "PE")
        or _option_type_from_symbol(row.get("tradingSymbol"), row.get("customSymbol")) is not None
    )

    if has_option_markers:
        return InstrumentType.OPT
    if "FNO" in segment or "CURRENCY" in segment or "COMM" in segment:
        # FNO segment without option markers → futures
        return InstrumentType.FUT
    return InstrumentType.EQ


def map_trade(row: dict, broker: str = "dhan") -> CanonicalExecution:
    """Map one Dhan trade-book row to a CanonicalExecution."""
    segment = row.get("exchangeSegment") or ""
    exchange = _SEGMENT_TO_EXCHANGE.get(segment, segment.split("_")[0] or "NSE")

    instrument_type = _infer_instrument_type(row)

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

    # History rows return exchangeTradeId='0' (orders are aggregated per-day, not per-fill).
    # Fall back to orderId in that case so our UNIQUE(broker, broker_trade_id) holds.
    raw_trade_id = str(row.get("exchangeTradeId") or "").strip()
    broker_trade_id = (
        raw_trade_id if raw_trade_id and raw_trade_id != "0" else str(row.get("orderId") or "")
    )

    return CanonicalExecution(
        broker=broker,
        broker_trade_id=broker_trade_id,
        broker_order_id=str(row.get("orderId") or "") or None,
        symbol=row.get("customSymbol") or row.get("tradingSymbol") or "",
        underlying=_underlying_from_symbol(row.get("tradingSymbol"), row.get("customSymbol")),
        exchange=exchange,
        segment=segment or exchange,
        instrument_type=instrument_type,
        option_type=(
            _OPTION_TYPE.get(row.get("drvOptionType"))
            or (
                _option_type_from_symbol(row.get("tradingSymbol"), row.get("customSymbol"))
                if instrument_type == InstrumentType.OPT
                else None
            )
        ),
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
