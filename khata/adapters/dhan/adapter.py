"""Dhan broker adapter. Implements BrokerAdapter."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from khata.adapters.dhan.client import DhanClient
from khata.adapters.dhan.mapper import map_trade
from khata.core.adapter import (
    AuthFlow,
    BrokerAdapter,
    CanonicalExecution,
    CanonicalOrder,
    CanonicalPosition,
    Session,
)


class DhanAdapter(BrokerAdapter):
    name = "dhan"
    auth_flow = AuthFlow.TOKEN

    def authenticate(self, creds: dict) -> Session:
        client_id = creds["client_id"]
        access_token = creds["access_token"]
        client = DhanClient(client_id=client_id, access_token=access_token)
        # Cheap probe to surface bad tokens early.
        client.get_positions()
        return Session(
            broker=self.name,
            user_id=creds.get("user_id", 1),
            data={"client": client, "client_id": client_id},
        )

    def fetch_trades(self, session: Session, since: datetime) -> list[CanonicalExecution]:
        client: DhanClient = session.data["client"]
        today = datetime.now(UTC).date()
        since_date = since.astimezone(UTC).date()

        rows: list[dict] = []
        if since_date >= today:
            rows.extend(client.get_trades())
        else:
            # Statement API: paginate until empty. Dhan caps history queries at
            # ~90 days per call, so chunk date ranges too.
            cur = since_date
            while cur < today:
                chunk_end = min(cur + timedelta(days=89), today - timedelta(days=1))
                page = 0
                while page < 100:  # safety bound
                    chunk = client.get_trades_range(cur, chunk_end, page=page)
                    if not chunk:
                        break
                    rows.extend(chunk)
                    page += 1
                cur = chunk_end + timedelta(days=1)
            rows.extend(client.get_trades())

        executions = [map_trade(r, broker=self.name) for r in rows]
        # Filter to `since` precisely (Statement API is date-granular).
        return [e for e in executions if e.ts >= since.astimezone(UTC)]

    def fetch_positions(self, session: Session) -> list[CanonicalPosition]:
        # Left as a stub for Weekend 1 — positions mapper lands with the web UI work.
        return []

    def fetch_orders(self, session: Session, on_date: date) -> list[CanonicalOrder]:
        # Stub: order-book mapper lands with the UI work.
        return []
