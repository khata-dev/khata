# Writing a broker adapter

A broker adapter maps your broker's API into khata's canonical schema. Target is ~200 LOC per adapter.

## Contract

Implement `khata.core.adapter.BrokerAdapter`:

```python
from khata.core.adapter import BrokerAdapter, AuthFlow, CanonicalExecution, CanonicalPosition, CanonicalOrder, CanonicalFees, Session

class MyBrokerAdapter(BrokerAdapter):
    name = "mybroker"
    auth_flow = AuthFlow.TOKEN  # or OAUTH, DAILY_LOGIN, TOTP

    def authenticate(self, creds: dict) -> Session: ...
    def fetch_trades(self, session: Session, since: datetime) -> list[CanonicalExecution]: ...
    def fetch_positions(self, session: Session) -> list[CanonicalPosition]: ...
    def fetch_orders(self, session: Session, date: date) -> list[CanonicalOrder]: ...
    def charges_for(self, execution: CanonicalExecution) -> CanonicalFees | None: ...
```

## Register it

Add your adapter to `pyproject.toml`:

```toml
[project.entry-points."khata.adapters"]
mybroker = "khata.adapters.mybroker:MyBrokerAdapter"
```

## Test it

- Drop recorded API responses into `tests/fixtures/mybroker/`.
- Write a test that loads the fixtures, runs the mapper, and asserts the canonical output.
- No live broker account needed to review your PR.

## What "canonical" means

- Times are UTC.
- Money is paise (int) internally, not rupees. Float in = paise out.
- Instrument types: `EQ`, `FUT`, `OPT`.
- Exchanges: `NSE`, `BSE`, `NFO`, `BFO`, `MCX`, `CDS`.
- Sides: `BUY`, `SELL`.
- Fees breakdown: brokerage, stt, exch_txn, sebi, stamp, gst, ipft, others.

If your broker exposes something the canonical schema doesn't capture, open an issue — we'd rather extend the schema than bloat per-adapter code.
