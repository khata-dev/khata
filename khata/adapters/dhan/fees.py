"""Recompute Indian F&O charges from first principles.

Used when the broker's response omits fee fields (Dhan's today /trades endpoint
doesn't populate fees until EOD settlement; history rows do). Keeping the
formulas in one place so they're easy to update when regulation shifts.

Rates as of 2026-04. Sources: Zerodha/Dhan brokerage calculators, NSE
transaction charge circulars, SEBI turnover-fee notification.

Known limitations:
- Brokerage assumes Dhan's intraday flat ₹20 / executed order. Not correct
  for delivery (CNC) trades or for brokers with per-leg pricing.
- NSE transaction charges updated 2024-10 to 0.03503%. Older trades may have
  used 0.053%; we apply the current rate uniformly — acceptable drift.
- IPFT rate is nominal (₹0.05 per lakh turnover); we approximate.
"""

from __future__ import annotations

from khata.core.adapter import CanonicalExecution, CanonicalFees, InstrumentType, Side


def _round_paise(rupees: float) -> int:
    return round(rupees * 100)


def compute_fno_options_fees(e: CanonicalExecution) -> CanonicalFees:
    """Compute standard Indian F&O option charges for one execution."""
    turnover_rs = (e.qty * e.price_paise) / 100  # premium in rupees

    brokerage_rs = min(20.0, turnover_rs * 0.0003)  # Dhan intraday F&O flat ₹20
    stt_rs = turnover_rs * 0.000625 if e.side == Side.SELL else 0.0  # SELL side only
    exch_txn_rs = turnover_rs * 0.0003503  # NSE options, post-Oct-2024
    sebi_rs = turnover_rs * 10 / 1_00_00_000  # ₹10 per crore
    stamp_rs = turnover_rs * 0.00003 if e.side == Side.BUY else 0.0  # 0.003% BUY only
    ipft_rs = turnover_rs * 0.000005  # NSE IPFT

    gst_rs = (brokerage_rs + exch_txn_rs + sebi_rs + ipft_rs) * 0.18

    return CanonicalFees(
        brokerage_paise=_round_paise(brokerage_rs),
        stt_paise=_round_paise(stt_rs),
        exch_txn_paise=_round_paise(exch_txn_rs),
        sebi_paise=_round_paise(sebi_rs),
        stamp_paise=_round_paise(stamp_rs),
        gst_paise=_round_paise(gst_rs),
        ipft_paise=_round_paise(ipft_rs),
    )


def compute_fees(e: CanonicalExecution) -> CanonicalFees | None:
    """Dispatch by instrument type. Returns None for types we can't price yet."""
    if e.instrument_type == InstrumentType.OPT:
        return compute_fno_options_fees(e)
    # FUT and EQ formulas differ; leave as a follow-up. We won't pollute the
    # trade with wrong numbers in the meantime.
    return None
