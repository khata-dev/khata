<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
  <img src="assets/logo.svg" alt="khata" width="420">
</picture>

### Your trading journal. On your machine. Synced from your broker.

[![CI](https://github.com/khata-dev/khata/actions/workflows/ci.yml/badge.svg)](https://github.com/khata-dev/khata/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-0f172a.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-0f172a.svg)](pyproject.toml)
[![Status: pre-alpha](https://img.shields.io/badge/status-pre--alpha-fbbf24.svg)](docs/ROADMAP.md)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-22c55e.svg)](CONTRIBUTING.md)

[Quick start](#quick-start) · [What you'll see](#what-youll-see) · [Why khata](#why-khata) · [Supported brokers](#supported-brokers) · [Roadmap](docs/ROADMAP.md) · [Contributing](CONTRIBUTING.md)

</div>

---

**khata** (खाता — Hindi for *ledger*) is an open-source trading journal built for Indian markets. It syncs automatically from your broker, reconstructs round-trip trades from fills, and lets you attach screenshots, voice memos, and screen recordings to any trade.

Self-hosted. Your broker tokens never leave your machine. Zero telemetry.

```bash
uv run khata sync --broker dhan --since-days 30
→ authenticating with dhan…
→ fetching executions since 2026-03-21…
  got 247 executions
  inserted 247 new rows
→ rebuilding round-trip trades…
  ✓ trades=89 (open=3) across 14 contracts
```

## Why khata

Every other tool forces a tradeoff you shouldn't have to make:

| Tool | Auto-sync from Indian brokers | Open source | Self-hosted | Journal + attachments | Indian tax |
|---|:-:|:-:|:-:|:-:|:-:|
| Zerodha Console | Zerodha only | ✗ | ✗ | Shallow | ✓ |
| Tradezella / Tradervue | ✗ (CSV only) | ✗ | ✗ | ✓ | ✗ |
| TradesViz / TWI Journal | ✗ (CSV only) | ✗ | ✗ | ✓ | ✗ |
| Spreadsheets | ✗ | — | ✓ | Manual | Manual |
| **khata** | **✓** | **✓** | **✓** | **✓** | **Planned (v1)** |

The sensitive bit — your broker tokens and your P&L — stays on your machine. Read the code, self-host, and nobody can change their mind about your data.

## Features

- **Auto-sync** from your broker. Historical backfill and intraday polls.
- **Canonical trade schema.** One shape for every broker — portable, queryable, analytics-friendly.
- **FIFO round-trip reconstruction** across executions: partial fills, scale-ins, scale-outs, overshoots, expiry settlements. [5/5 tests green.](tests/test_roundtrip.py)
- **Attachments** — photos, voice memos, screen recordings, and PDFs on any trade or daily note.
- **Analytics** *(v0.3)* — calendar heatmap, equity curve, win rate / profit factor / expectancy, R-multiple distribution, strategy and psychology breakdowns.
- **Mobile PWA** *(v0.3)* — quick capture on your phone in under ten seconds.
- **Tax engine** *(v1.0)* — F&O P&L, SEBI turnover, ITR-3 ready output.
- **Boring stack.** FastAPI + SQLite + HTMX + Python. One Docker command to run.

## What you'll see

Get the last month of trades and a quick summary:

```bash
$ uv run khata stats
                   khata
  ┏━━━━━━━━━━┳━━━━━━━━━━━━━━┓
  ┃ metric   ┃        value ┃
  ┡━━━━━━━━━━╇━━━━━━━━━━━━━━┩
  │ trades   │           89 │
  │ wins     │           52 │
  │ losses   │           34 │
  │ open     │            3 │
  │ win rate │        60.5% │
  │ net P&L  │   ₹1,24,350.80 │
  └──────────┴──────────────┘
```

Or drop to raw executions for debugging:

```bash
$ uv run khata dump-executions --limit 5
  broker  symbol                 side  qty  price       ts
  dhan    NIFTY 24350 CE         BUY   75   ₹75.30      2026-04-15T04:15:22Z
  dhan    NIFTY 24350 CE         SELL  75   ₹85.60      2026-04-15T04:32:08Z
  dhan    BANKNIFTY 51000 PE     BUY   30   ₹142.50     2026-04-15T05:03:11Z
  ...
```

## Supported brokers

| Broker | Status | Auth | Notes |
|---|---|---|---|
| **Dhan** | ✅ v0.0.1 | 24h JWT | REST + postback webhooks |
| Zerodha (Kite) | 🔜 v0.4 | Daily login | Largest retail user base |
| Fyers | 🔜 v0.4 | OAuth | REST + WebSocket |
| Upstox | 🔜 v0.4 | OAuth | REST |
| Angel One | 🔜 v0.5 | TOTP | |
| Groww / ICICI Direct / HDFC Sec | Planned | No API | Contract-note import |

Want your broker added sooner? Read [`docs/ADAPTERS.md`](docs/ADAPTERS.md) — each adapter is ~200 lines of code + recorded fixtures. Open a PR or a [broker adapter request](../../issues/new?template=broker_adapter.yml).

## Quick start

### With uv (recommended)

```bash
git clone https://github.com/khata-dev/khata
cd khata
cp .env.example .env
# edit .env: DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN

uv sync
uv run khata init
uv run khata sync --broker dhan --since-days 30
uv run khata stats
```

### With Docker

```bash
docker compose up -d
docker compose exec khata khata sync --broker dhan
```

### Getting Dhan API credentials

1. Log in at [dhan.co](https://dhan.co) → **Trading APIs** → **Access DhanHQ APIs**.
2. Generate an access token. It's a ~24-hour JWT — regenerate around 08:50 IST each market morning.
3. Copy your `dhanClientId` and the token into `.env`.

## Design principles

1. **Self-hosted, always.** Your data stays on your machine. No telemetry.
2. **Broker adapters are pluggable.** Canonical schema is the only contract.
3. **Journaling is a behaviour, not a form.** Mobile capture takes under ten seconds.
4. **Boring stack.** Modify it in one afternoon.
5. **Apache 2.0, forever.** No open-core rug-pull.

## FAQ

**Is khata a trading platform?** No. khata is read-only — it never places orders. It's a journal.

**Do I need a VPS to run it?** No. Runs fine on your laptop (SQLite, zero dependencies beyond Python). If you want mobile access, Tailscale + your laptop works.

**Can I trust it with my broker token?** Read the code. The token sits in your `.env` file, is sent only to your broker's API, and never leaves your machine. khata has no servers and makes no outbound calls to any third party.

**What about tax reports?** On the roadmap for v1.0 — F&O P&L, SEBI turnover, ITR-3 schedule output. Not in the current release.

**How does this compare to Zerodha Console?** Console is great, but it's Zerodha-only and the journaling is shallow. khata aims to be Console-across-every-broker, plus a real journal, plus Indian tax.

**Why not just a spreadsheet?** A spreadsheet works until it doesn't — by trade 200 you're copying data by hand, rebuilding round-trips manually, and P&L stops matching your broker statement. khata handles all of that.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development setup. The fastest path to a useful contribution is writing an adapter for your broker — [`docs/ADAPTERS.md`](docs/ADAPTERS.md).

## Security

Broker tokens are sensitive. Keep them in `.env` (gitignored) or encrypted in the DB via `KHATA_SECRET`. See [`docs/SECURITY.md`](docs/SECURITY.md) for responsible-disclosure guidance.

## Licence

Apache 2.0. See [`LICENSE`](LICENSE).

## Acknowledgments

- **[Zerodha Console](https://console.zerodha.com/)** set the bar for what broker-integrated analytics can feel like.
- **[Tradezella](https://www.tradezella.com/), [Tradervue](https://www.tradervue.com/), [TradesViz](https://www.tradesviz.com/), [TWI Journal](https://journal.tradewithinsight.com/)** are the journals Indian traders reach for when they need more than a spreadsheet — and each one is the reason this exists.
- **[Dhan](https://dhanhq.co/docs/v2/)** for shipping a clean, documented REST API with a generous developer tier.

---

<div align="center">
  <sub>Built for the Indian retail trader. One broker at a time.</sub>
</div>
