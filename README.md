<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
  <img src="assets/logo.svg" alt="khata" width="420">
</picture>

### The open-source trading journal for Indian markets.

<p>Self-hosted. Broker-synced. Your tokens never leave your machine.</p>

[![CI](https://github.com/khata-dev/khata/actions/workflows/ci.yml/badge.svg)](https://github.com/khata-dev/khata/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-0f172a.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-0f172a.svg)](pyproject.toml)
[![Status: alpha](https://img.shields.io/badge/status-alpha-fbbf24.svg)](docs/ROADMAP.md)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-22c55e.svg)](CONTRIBUTING.md)
[![Zero telemetry](https://img.shields.io/badge/telemetry-zero-0f172a.svg)](docs/SECURITY.md)

[**Quick start**](#quick-start) · [**Features**](#features) · [**Supported brokers**](#supported-brokers) · [**Architecture**](#architecture) · [**Roadmap**](docs/ROADMAP.md) · [**Contributing**](CONTRIBUTING.md)

</div>

---

**khata** (खाता — Hindi for *ledger*) is a self-hosted trading journal built for Indian retail traders. It pulls executions directly from your broker, reconstructs round-trip trades with correct fees, and gives you a fast, keyboard-friendly UI to review your edge — without surrendering your broker tokens or P&L data to a foreign SaaS.

## Why khata exists

Indian retail traders have had to pick one of three bad options:

- **Your broker's built-in console** — scoped to that broker, shallow journaling, no cross-broker view.
- **International SaaS** (Tradezella, Tradervue, TradesViz, TWI Journal) — closed source, no Indian broker APIs, no Indian tax logic, and you upload your P&L to foreign infrastructure.
- **Spreadsheets** — work until trade 200, then the FIFO math quietly breaks.

khata is the fourth option: the data and the code live on your machine, the broker integration is open for inspection, and the journal takes the behavioural loop — notes, tags, reflections — seriously enough to matter.

| | Auto-sync<br/>Indian brokers | Self-hosted | Open source | Journal +<br/>attachments | Indian tax |
|---|:---:|:---:|:---:|:---:|:---:|
| Zerodha Console | Zerodha only | — | — | Shallow | ✓ |
| Tradezella · Tradervue | CSV only | — | — | ✓ | — |
| TradesViz · TWI Journal | CSV only | — | — | ✓ | — |
| Spreadsheets | — | ✓ | — | Manual | Manual |
| **khata** | **✓** | **✓** | **✓** | **✓** | **Planned (v1)** |

---

## What's in the box today

### Command-line sync

```bash
$ uv run khata sync --broker dhan --since-days 30
→ authenticating with dhan…
→ fetching executions since 2026-03-21 …
  got 103 executions
  inserted 103 new rows
→ rebuilding round-trip trades…
  ✓ trades=18 (open=0) across 16 contracts
```

Historical backfill paginates through your broker's statement API. Intraday re-sync just re-runs the command. Everything is idempotent.

### Local web UI

```bash
$ uv run khata web
→ starting khata web at http://127.0.0.1:8000
```

- **Calendar** — month grid, P&L-coloured days, weekly-expiry markers, prev/next nav.
- **Day view** — every trade with IST times, direction badges, fees, inline daily reflection.
- **Trade view** — entry/exit, fills breakdown, tag chips (`setup` / `psych` / `mistake` / `custom`), freeform note editor.

HTMX for interactivity. No build step, no SPA. Loads in under a second on a laptop.

### Stats at a glance

```bash
$ uv run khata stats
           khata
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ metric   ┃         value ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ trades   │            18 │
│ wins     │             4 │
│ losses   │            14 │
│ open     │             0 │
│ win rate │         22.2% │
│ net P&L  │ -₹2,53,270.53 │
└──────────┴───────────────┘
```

---

## Features

- **Auto-sync from your broker.** Historical backfill + intraday re-sync, paginated where the API requires it.
- **Canonical trade schema.** One shape across every broker — portable, queryable, analytics-friendly.
- **FIFO round-trip reconstruction.** Partial fills, scale-ins, scale-outs, direction overshoots, expiry settlements. All covered by unit tests.
- **Accurate Indian fees.** STT, stamp duty, exchange transaction charges, SEBI turnover fee, IPFT, GST — recomputed from first principles when the broker hasn't settled yet.
- **Web UI with inline journaling.** Calendar heatmap → day → trade → tags and notes, each saved on blur. No floating dialogs.
- **Zero telemetry.** No outbound calls to any khata-owned server. There are none.
- **Attachments** *(v0.2)* — images, voice memos, screen recordings, contract-note PDFs.
- **Mobile PWA** *(v0.3)* — installable on your phone for sub-ten-second capture of photo, voice, and tags.
- **Analytics** *(v0.3)* — equity curve, R-multiple histogram, strategy/psych breakdowns.
- **Tax engine** *(v1.0)* — F&O P&L, SEBI turnover, ITR-3 schedule output.

---

## Quick start

### With `uv` (recommended)

```bash
git clone https://github.com/khata-dev/khata
cd khata
cp .env.example .env
# edit .env: DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN

uv sync
uv run khata init
uv run khata sync --broker dhan --since-days 30
uv run khata web
```

Open http://127.0.0.1:8000.

### With Docker

```bash
docker compose up -d
docker compose exec khata khata sync --broker dhan
```

### Getting Dhan API credentials

1. Log in at [dhan.co](https://dhan.co) → **Trading APIs** → **Access DhanHQ APIs**.
2. Generate an access token — it's a ~24-hour JWT, so regenerate each market morning around 08:50 IST.
3. Paste your `dhanClientId` and the token into `.env`.

---

## Supported brokers

| Broker | Status | Auth | Notes |
|---|---|---|---|
| **Dhan** | ✅ shipped | 24h JWT | REST + postback webhooks, paginated statement API |
| Zerodha (Kite) | 🔜 v0.4 | Daily login | Largest retail user base in India |
| Fyers | 🔜 v0.4 | OAuth | REST + WebSocket |
| Upstox | 🔜 v0.4 | OAuth | REST |
| Angel One | 🔜 v0.5 | TOTP | |
| Groww · ICICI Direct · HDFC Sec | Planned | No retail API | Contract-note import |

Want your broker sooner? Each adapter is ~200 lines of code plus recorded fixtures — see [`docs/ADAPTERS.md`](docs/ADAPTERS.md). Open a PR or a [broker adapter request](../../issues/new?template=broker_adapter.yml).

---

## Architecture

```
┌─────────────────────────┐
│   Broker APIs           │   Dhan today — others next
│   (auth, trades,        │
│    positions, orders)   │
└───────────┬─────────────┘
            │
   ┌────────▼────────┐
   │  Adapter layer  │   khata/adapters/<broker>/
   │  canonical out  │   One file per broker, one protocol
   └────────┬────────┘
            │
   ┌────────▼────────┐      ┌──────────────────┐
   │  Round-trip     │──────▶  SQLite DB        │   Canonical schema.
   │  FIFO engine    │      │  (executions,     │   Multi-user by design.
   └─────────────────┘      │   trades, notes,  │   Single-user default.
                            │   tags, …)        │
                            └────┬─────────────-┘
                                 │
                     ┌───────────▼───────────┐
                     │  CLI    ·   Web UI    │   Typer · FastAPI + HTMX
                     │  (both local-only)    │   No telemetry. No cloud.
                     └───────────────────────┘
```

Stack choices are intentionally boring — Python 3.11+, FastAPI, SQLite, Jinja2, HTMX. You can understand the whole codebase in an afternoon and patch it in an hour.

---

## Design principles

1. **Self-hosted, always.** Data stays on your machine. No exceptions.
2. **Zero telemetry.** khata has no servers. We couldn't phone home if we wanted to.
3. **Adapters are pluggable.** The canonical schema is the contract — drop in a new broker without touching analytics.
4. **Journaling is a behaviour, not a form.** Mobile capture under ten seconds is the goal.
5. **Boring stack.** A contributor should be able to modify any subsystem in one afternoon.
6. **Apache 2.0, forever.** No open-core rug-pull. No relicensing.

---

## FAQ

**Is khata a trading platform?**
No. It's strictly read-only — it never places an order, modifies a position, or holds funds. It's a journal.

**Do I need a VPS?**
No. Runs on your laptop with zero dependencies beyond Python. If you want mobile access, Tailscale your laptop and use the PWA — no public tunnel required.

**Is my broker token safe?**
Read the code. The token lives in your `.env` file (gitignored), is sent only to your broker's API, and never leaves your machine. khata has no servers and makes no outbound calls to any third party.

**What about tax reports?**
On the roadmap for v1.0 — F&O P&L, SEBI turnover, ITR-3 schedule output. Not in the current release.

**How does this compare to Zerodha Console?**
Console sets the bar for broker-integrated analytics, but it's Zerodha-only and the journaling is shallow. khata is Console-across-every-broker, plus a real journal, plus (eventually) Indian tax.

**Why not just a spreadsheet?**
Works until trade 200. Then FIFO breaks, fees get rounded wrong, and P&L stops matching your broker statement. khata handles all of that for you, deterministically.

**Can I use this for equity / futures / currency / commodities?**
The schema supports all of them today. The fee recomputation logic is options-only for now; futures and equity land as needed — open an issue if you need them sooner.

---

## Contributing

Three of the most welcome kinds of contribution:

- **A new broker adapter** — canonical schema is the contract, each adapter is ~200 lines plus recorded fixtures. Read [`docs/ADAPTERS.md`](docs/ADAPTERS.md).
- **A regression test from real data** — even one fixture covering an edge case we hadn't seen helps.
- **Docs** — anything that makes the first ten minutes of setup faster.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development setup, local test commands, and PR conventions.

## Security

Broker tokens are the most sensitive thing khata touches. We keep them in `.env` (gitignored) or encrypted in the DB via `KHATA_SECRET`. Never commit your token. Never paste it in an issue. Report security issues privately as described in [`docs/SECURITY.md`](docs/SECURITY.md).

## Licence

Apache 2.0 — see [`LICENSE`](LICENSE).

## Acknowledgments

- **[Zerodha Console](https://console.zerodha.com/)** set the bar for what broker-integrated analytics can feel like for Indian traders.
- **[Tradezella](https://www.tradezella.com/), [Tradervue](https://www.tradervue.com/), [TradesViz](https://www.tradesviz.com/), [TWI Journal](https://journal.tradewithinsight.com/)** — the journals Indian traders reach for when spreadsheets stop scaling. Each is a reason khata exists.
- **[Dhan](https://dhanhq.co/docs/v2/)** — for shipping a clean REST API with a generous developer tier.
- **[HTMX](https://htmx.org/)** — for making server-rendered UI legible again.

---

<div align="center">
  <sub>Built for the Indian retail trader. One broker at a time.</sub>
  <br/>
  <sub><a href="https://github.com/khata-dev/khata">github.com/khata-dev/khata</a></sub>
</div>
