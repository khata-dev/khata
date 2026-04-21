"""FastAPI app for khata's local web UI.

Single-user, localhost-first. No auth (run behind Tailscale/VPN for remote
access). HTMX-powered inline editing — no client-side JS framework.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from khata.config import Config
from khata.core.db import connect, init_schema, user_id_for
from khata.core.money import fmt_rupees, paise_to_rupees
from khata.web import helpers as H
from khata.web import queries as Q

HERE = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=HERE / "templates")
TEMPLATES.env.globals.update(
    fmt_rupees=fmt_rupees,
    paise_to_rupees=paise_to_rupees,
    month_name=H.month_name,
    fmt_time_ist=H.fmt_time_ist,
    today_iso=lambda: H.today_ist().isoformat(),
)


def create_app() -> FastAPI:
    app = FastAPI(title="khata", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    cfg = Config.load()

    def _conn():
        c = connect(cfg)
        init_schema(c)
        try:
            yield c
        finally:
            c.close()

    def _user_id(conn=Depends(_conn)) -> int:
        return user_id_for(conn, cfg.user)

    # ── routes ─────────────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    def home():
        today = H.today_ist()
        return RedirectResponse(f"/calendar/{today.year}/{today.month}")

    @app.get("/calendar/{year}/{month}", response_class=HTMLResponse)
    def calendar_view(
        request: Request,
        year: int,
        month: int,
        conn=Depends(_conn),
        user_id: int = Depends(_user_id),
    ):
        if not (1 <= month <= 12):
            raise HTTPException(400, "invalid month")
        summary = Q.month_summary_by_day(conn, user_id, year, month)
        grid = H.month_grid(year, month)
        prev_y, prev_m = H.prev_month(year, month)
        next_y, next_m = H.next_month(year, month)
        expiry_days = Q.expiry_days_in_range(
            conn, user_id, date(year, month, 1), date(next_y, next_m, 1)
        )

        # Month totals
        total_net = sum((d.get("net_paise") or 0) for d in summary.values())
        total_trades = sum((d.get("n") or 0) for d in summary.values())
        active_days = len(summary)

        return TEMPLATES.TemplateResponse(
            request,
            "calendar.html",
            {
                "year": year,
                "month": month,
                "grid": grid,
                "summary": summary,
                "expiry_days": expiry_days,
                "prev_y": prev_y,
                "prev_m": prev_m,
                "next_y": next_y,
                "next_m": next_m,
                "today": H.today_ist(),
                "total_net": total_net,
                "total_trades": total_trades,
                "active_days": active_days,
            },
        )

    @app.get("/day/{day}", response_class=HTMLResponse)
    def day_view(
        request: Request,
        day: str,
        conn=Depends(_conn),
        user_id: int = Depends(_user_id),
    ):
        try:
            d = date.fromisoformat(day)
        except ValueError as e:
            raise HTTPException(400, "invalid date") from e
        trades = Q.trades_on_day(conn, user_id, d)
        totals = Q.day_totals(trades)
        note = Q.get_daily_note(conn, user_id, d)
        # `d` counts as an expiry day if any trade in the user's book expires on it.
        expiry_days = Q.expiry_days_in_range(conn, user_id, d, H.shift_day(d, 1))
        return TEMPLATES.TemplateResponse(
            request,
            "day.html",
            {
                "d": d,
                "prev_day": H.shift_day(d, -1),
                "next_day": H.shift_day(d, 1),
                "trades": trades,
                "totals": totals,
                "note": note,
                "endpoint": f"/notes/day/{d.isoformat()}",
                "is_expiry": d in expiry_days,
            },
        )

    @app.get("/trade/{trade_id}", response_class=HTMLResponse)
    def trade_view(
        request: Request,
        trade_id: int,
        conn=Depends(_conn),
        user_id: int = Depends(_user_id),
    ):
        trade = Q.trade_by_id(conn, user_id, trade_id)
        if trade is None:
            raise HTTPException(404, "trade not found")
        execs = Q.executions_for_trade(conn, trade_id)
        note = Q.get_trade_note(conn, user_id, trade_id)
        tags = Q.tags_for_trade(conn, user_id, trade_id)
        return TEMPLATES.TemplateResponse(
            request,
            "trade.html",
            {
                "trade": trade,
                "executions": execs,
                "note": note,
                "tags": tags,
                "trade_id": trade_id,
                "endpoint": f"/notes/trade/{trade_id}",
            },
        )

    # ── HTMX partial endpoints ─────────────────────────────────────────
    @app.post("/notes/trade/{trade_id}", response_class=HTMLResponse)
    def save_trade_note(
        request: Request,
        trade_id: int,
        body: Annotated[str, Form()] = "",
        conn=Depends(_conn),
        user_id: int = Depends(_user_id),
    ):
        if Q.trade_by_id(conn, user_id, trade_id) is None:
            raise HTTPException(404)
        note = Q.set_trade_note(conn, user_id, trade_id, body)
        return TEMPLATES.TemplateResponse(
            request,
            "partials/note_block.html",
            {"note": note, "endpoint": f"/notes/trade/{trade_id}"},
        )

    @app.post("/notes/day/{day}", response_class=HTMLResponse)
    def save_daily_note(
        request: Request,
        day: str,
        body: Annotated[str, Form()] = "",
        conn=Depends(_conn),
        user_id: int = Depends(_user_id),
    ):
        try:
            d = date.fromisoformat(day)
        except ValueError as e:
            raise HTTPException(400) from e
        note = Q.set_daily_note(conn, user_id, d, body)
        return TEMPLATES.TemplateResponse(
            request,
            "partials/note_block.html",
            {"note": note, "endpoint": f"/notes/day/{day}"},
        )

    @app.post("/tags/trade/{trade_id}", response_class=HTMLResponse)
    def add_trade_tag(
        request: Request,
        trade_id: int,
        name: Annotated[str, Form()] = "",
        kind: Annotated[str, Form()] = "custom",
        conn=Depends(_conn),
        user_id: int = Depends(_user_id),
    ):
        if Q.trade_by_id(conn, user_id, trade_id) is None:
            raise HTTPException(404)
        kind = kind if kind in ("psych", "setup", "mistake", "custom") else "custom"
        Q.add_tag_to_trade(conn, user_id, trade_id, name, kind)
        tags = Q.tags_for_trade(conn, user_id, trade_id)
        return TEMPLATES.TemplateResponse(
            request,
            "partials/tag_list.html",
            {"tags": tags, "trade_id": trade_id},
        )

    @app.delete("/tags/trade/{trade_id}/{tag_id}", response_class=HTMLResponse)
    def delete_trade_tag(
        request: Request,
        trade_id: int,
        tag_id: int,
        conn=Depends(_conn),
        user_id: int = Depends(_user_id),
    ):
        Q.remove_tag_from_trade(conn, trade_id, tag_id)
        tags = Q.tags_for_trade(conn, user_id, trade_id)
        return TEMPLATES.TemplateResponse(
            request,
            "partials/tag_list.html",
            {"tags": tags, "trade_id": trade_id},
        )

    return app


# Convenience: `uvicorn khata.web.main:app`
app = create_app()
