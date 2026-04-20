"""BrokerAdapter protocol + canonical types.

Every broker adapter maps its API into these shapes. Money is paise (int).
Times are timezone-aware UTC datetimes. If your broker gives IST or seconds-since-epoch,
the mapper must convert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Protocol


class AuthFlow(StrEnum):
    TOKEN = "token"              # long-lived or daily JWT (Dhan)
    OAUTH = "oauth"              # OAuth refresh dance (Upstox, Fyers)
    DAILY_LOGIN = "daily_login"  # interactive daily login (Zerodha Kite)
    TOTP = "totp"                # TOTP-based session (Angel One)


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class InstrumentType(StrEnum):
    EQ = "EQ"
    FUT = "FUT"
    OPT = "OPT"


class OptionType(StrEnum):
    CE = "CE"
    PE = "PE"


@dataclass
class Session:
    """Opaque broker session. Adapters stash whatever they need inside `data`."""
    broker: str
    user_id: int
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class CanonicalFees:
    brokerage_paise: int = 0
    stt_paise: int = 0
    exch_txn_paise: int = 0
    sebi_paise: int = 0
    stamp_paise: int = 0
    gst_paise: int = 0
    ipft_paise: int = 0
    other_paise: int = 0

    @property
    def total_paise(self) -> int:
        return (
            self.brokerage_paise
            + self.stt_paise
            + self.exch_txn_paise
            + self.sebi_paise
            + self.stamp_paise
            + self.gst_paise
            + self.ipft_paise
            + self.other_paise
        )


@dataclass
class CanonicalExecution:
    broker: str
    broker_trade_id: str
    broker_order_id: str | None
    symbol: str
    underlying: str | None
    exchange: str                    # NSE | BSE | NFO | BFO | MCX | CDS
    segment: str                     # NSE_EQ | NSE_FNO | BSE_EQ | ...
    instrument_type: InstrumentType
    option_type: OptionType | None
    strike_paise: int | None
    expiry: date | None
    side: Side
    qty: int
    price_paise: int
    ts: datetime                     # timezone-aware, stored as UTC
    product_type: str | None
    fees: CanonicalFees
    raw: dict[str, Any]              # original broker payload for debugging


@dataclass
class CanonicalPosition:
    broker: str
    symbol: str
    underlying: str | None
    exchange: str
    segment: str
    instrument_type: InstrumentType
    option_type: OptionType | None
    strike_paise: int | None
    expiry: date | None
    net_qty: int                     # +long, -short
    avg_price_paise: int
    buy_qty: int
    sell_qty: int
    realized_pnl_paise: int
    unrealized_pnl_paise: int
    product_type: str | None


@dataclass
class CanonicalOrder:
    broker: str
    broker_order_id: str
    symbol: str
    exchange: str
    segment: str
    status: str                      # NEW | OPEN | PARTIAL | FILLED | CANCELLED | REJECTED
    side: Side
    qty: int
    filled_qty: int
    price_paise: int | None
    trigger_price_paise: int | None
    order_type: str                  # MARKET | LIMIT | SL | SL-M
    product_type: str | None
    created_at: datetime
    updated_at: datetime


class BrokerAdapter(Protocol):
    """Protocol every broker adapter implements. See docs/ADAPTERS.md."""

    name: str
    auth_flow: AuthFlow

    def authenticate(self, creds: dict) -> Session:
        """Turn raw creds (usually from env) into a Session. Raise on failure."""
        ...

    def fetch_trades(
        self, session: Session, since: datetime
    ) -> list[CanonicalExecution]:
        """Return every execution (fill) at or after `since`, mapped to canonical."""
        ...

    def fetch_positions(self, session: Session) -> list[CanonicalPosition]:
        """Return current open positions."""
        ...

    def fetch_orders(self, session: Session, on_date: date) -> list[CanonicalOrder]:
        """Return orders placed on a given date."""
        ...

    def charges_for(
        self, execution: CanonicalExecution
    ) -> CanonicalFees | None:
        """Optional: recompute exact fees for one execution. Return None to trust broker."""
        return None
