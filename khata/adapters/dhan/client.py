"""Thin HTTP client around the Dhan v2 REST API.

Auth:
  headers: {"access-token": <JWT>, "client-id": <id>, "Content-Type": "application/json"}
  Token is a ~24h JWT obtained from dhan.co → Trading APIs → Access DhanHQ APIs.

Docs: https://dhanhq.co/docs/v2/
Rate limits (from docs):
  Order APIs        — 10/s, 250/min, 1000/h, 7000/day
  Non-trading APIs  — 20/s, unlimited/min
  Data APIs         —  5/s, 100000/day
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any

import httpx

API_BASE = "https://api.dhan.co/v2"


class DhanAPIError(RuntimeError):
    def __init__(self, status: int | None, body: Any, message: str = ""):
        self.status = status
        self.body = body
        super().__init__(message or f"Dhan API error {status}: {body!r}")


class DhanClient:
    def __init__(self, client_id: str, access_token: str, timeout: float = 15.0):
        self._headers = {
            "access-token": access_token,
            "client-id": client_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._client = httpx.Client(base_url=API_BASE, headers=self._headers, timeout=timeout)
        self._last_call: dict[str, float] = {}

    # ── read endpoints ────────────────────────────────────────────────
    def get_orders(self) -> list[dict]:
        """Today's order book."""
        return self._get("/orders")

    def get_trades(self) -> list[dict]:
        """Today's executions (trade book)."""
        return self._get("/trades")

    def get_trades_range(self, from_date: date, to_date: date, page: int = 0) -> list[dict]:
        """Historical trades via Statement API.

        Path: GET /trades/{YYYY-MM-DD}/{YYYY-MM-DD}/{pageNumber}
        Page size is ~20, newest-first. Caller paginates until an empty list.
        """
        path = f"/trades/{from_date.isoformat()}/{to_date.isoformat()}/{page}"
        return self._get(path)

    def get_positions(self) -> list[dict]:
        """Current day net positions."""
        return self._get("/positions")

    def get_holdings(self) -> list[dict]:
        """Long-term delivery holdings."""
        return self._get("/holdings")

    # ── lifecycle ─────────────────────────────────────────────────────
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DhanClient:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── internals ─────────────────────────────────────────────────────
    def _get(self, path: str) -> Any:
        self._throttle(path)
        try:
            r = self._client.get(path)
        except httpx.HTTPError as e:
            raise DhanAPIError(None, None, f"network error: {e}") from e
        if r.status_code == 401:
            raise DhanAPIError(401, r.text, "Dhan auth failed — token may be expired")
        if r.status_code >= 400:
            raise DhanAPIError(r.status_code, self._safe_json(r), "Dhan API error")
        body = self._safe_json(r)
        # Dhan wraps some responses in a list, others in {data: [...]}, others in {status, data}.
        if isinstance(body, dict) and "data" in body and isinstance(body["data"], list):
            return body["data"]
        return body

    @staticmethod
    def _safe_json(r: httpx.Response) -> Any:
        try:
            return r.json()
        except Exception:
            return r.text

    def _throttle(self, path: str) -> None:
        # Crude 200ms-between-calls guard. Dhan allows 20/s on non-trading calls;
        # we stay well under that with the buffer below.
        now = time.monotonic()
        last = self._last_call.get("_any", 0.0)
        gap = 0.1
        sleep_for = last + gap - now
        if sleep_for > 0:
            time.sleep(sleep_for)
        self._last_call["_any"] = time.monotonic()
