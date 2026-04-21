"""khata CLI. Entry point via `khata` (see pyproject.toml scripts)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib.metadata import entry_points

import typer
from rich.console import Console
from rich.table import Table

from khata.config import Config, DhanCreds
from khata.core.adapter import BrokerAdapter
from khata.core.db import connect, init_schema, user_id_for
from khata.core.money import fmt_rupees
from khata.core.roundtrip import rebuild_trades
from khata.core.store import upsert_executions

app = typer.Typer(add_completion=False, help="khata — self-hosted trading journal")
console = Console()


# ── helpers ────────────────────────────────────────────────────────────
def _load_adapter(name: str) -> BrokerAdapter:
    for ep in entry_points(group="khata.adapters"):
        if ep.name == name:
            return ep.load()()
    raise typer.BadParameter(f"No adapter registered for broker '{name}'")


def _load_creds(broker: str, user_id: int) -> dict:
    if broker == "dhan":
        c = DhanCreds.from_env()
        if not c:
            raise typer.BadParameter("DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN must be set in .env")
        return {"client_id": c.client_id, "access_token": c.access_token, "user_id": user_id}
    raise typer.BadParameter(f"Unknown broker: {broker}")


# ── commands ───────────────────────────────────────────────────────────
@app.command()
def init() -> None:
    """Create the SQLite database and schema."""
    cfg = Config.load()
    conn = connect(cfg)
    init_schema(conn)
    user_id_for(conn, cfg.user)
    console.print(f"[green]✓[/] schema initialised at [cyan]{cfg.db_path}[/]")


def _do_sync(broker: str, since: datetime) -> None:
    cfg = Config.load()
    conn = connect(cfg)
    init_schema(conn)
    user_id = user_id_for(conn, cfg.user)

    adapter = _load_adapter(broker)
    creds = _load_creds(broker, user_id)

    console.print(f"→ authenticating with [cyan]{broker}[/]…")
    session = adapter.authenticate(creds)

    console.print(f"→ fetching executions since [cyan]{since.date()}[/] …")
    executions = adapter.fetch_trades(session, since)
    console.print(f"  got [bold]{len(executions)}[/] executions")

    inserted = upsert_executions(conn, user_id, executions)
    console.print(f"  inserted [bold]{inserted}[/] new rows")

    console.print("→ rebuilding round-trip trades…")
    stats = rebuild_trades(conn, user_id)
    console.print(
        f"  [green]✓[/] trades=[bold]{stats['trades']}[/] "
        f"(open=[yellow]{stats['open']}[/]) across {stats['contracts']} contracts"
    )


@app.command()
def sync(
    broker: str = typer.Option("dhan", help="Broker name"),
    since_days: int = typer.Option(7, help="Pull trades from N days back (default 7)"),
) -> None:
    """Pull new executions from the broker and rebuild round-trip trades."""
    since = datetime.now(UTC) - timedelta(days=since_days)
    _do_sync(broker, since)


@app.command()
def backfill(
    since: str = typer.Argument(..., help="Backfill start date, YYYY-MM-DD"),
    broker: str = typer.Option("dhan"),
) -> None:
    """Pull a long historical window. Dhan caps ~90d per call; the adapter chunks."""
    since_dt = datetime.fromisoformat(since).replace(tzinfo=UTC)
    _do_sync(broker, since_dt)


@app.command()
def stats() -> None:
    """Print a quick summary."""
    cfg = Config.load()
    conn = connect(cfg)
    user_id = user_id_for(conn, cfg.user)
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS n,
            COALESCE(SUM(CASE WHEN status='CLOSED' THEN net_pnl_paise ELSE 0 END), 0) AS net,
            SUM(CASE WHEN status='CLOSED' AND net_pnl_paise > 0 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN status='CLOSED' AND net_pnl_paise <= 0 THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) AS open
        FROM trades WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    if not row or not row["n"]:
        console.print("[yellow]No trades yet. Run `khata sync` first.[/]")
        return

    t = Table(title="khata", show_header=True, header_style="bold cyan")
    t.add_column("metric")
    t.add_column("value", justify="right")
    t.add_row("trades", str(row["n"]))
    t.add_row("wins", str(row["wins"] or 0))
    t.add_row("losses", str(row["losses"] or 0))
    t.add_row("open", str(row["open"] or 0))
    wr = (
        (row["wins"] / (row["wins"] + row["losses"]) * 100)
        if (row["wins"] or 0) + (row["losses"] or 0)
        else 0
    )
    t.add_row("win rate", f"{wr:.1f}%")
    t.add_row("net P&L", fmt_rupees(row["net"]))
    console.print(t)


@app.command()
def reset(yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation")) -> None:
    """DANGER: delete all local khata data (DB + media). Does NOT touch your broker."""
    cfg = Config.load()
    if not yes:
        confirm = typer.confirm(f"Delete {cfg.db_path} and wipe {cfg.media_dir}?")
        if not confirm:
            raise typer.Abort()
    if cfg.db_path.exists():
        cfg.db_path.unlink()
    for wal in cfg.db_path.parent.glob(f"{cfg.db_path.name}-*"):
        wal.unlink()
    for p in cfg.media_dir.rglob("*"):
        if p.is_file() and p.name != ".gitkeep":
            p.unlink()
    console.print("[green]✓[/] reset complete")


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", help="Bind address (localhost-only by default)"),
    port: int = typer.Option(8000, help="Port"),
    reload: bool = typer.Option(
        True, "--reload/--no-reload", help="Auto-reload on code change (disable for deploy)"
    ),
) -> None:
    """Start the khata web UI (FastAPI + HTMX)."""
    import uvicorn

    console.print(f"→ starting khata web at [cyan]http://{host}:{port}[/] (reload={reload})")
    uvicorn.run(
        "khata.web.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@app.command("dump-executions")
def dump_executions(limit: int = 20) -> None:
    """Print the last N executions (debug)."""
    cfg = Config.load()
    conn = connect(cfg)
    user_id = user_id_for(conn, cfg.user)
    rows = conn.execute(
        "SELECT broker, symbol, side, qty, price_paise, ts FROM executions "
        "WHERE user_id = ? ORDER BY ts DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    t = Table(show_header=True, header_style="bold cyan")
    for c in ("broker", "symbol", "side", "qty", "price", "ts"):
        t.add_column(c)
    for r in rows:
        t.add_row(
            r["broker"],
            r["symbol"],
            r["side"],
            str(r["qty"]),
            fmt_rupees(r["price_paise"]),
            r["ts"],
        )
    console.print(t)


if __name__ == "__main__":
    app()
