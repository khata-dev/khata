# Roadmap

This is directional, not a promise. If something here matters to you, open an issue — user pull is what actually moves items up.

## v0.0.1 — Scaffold ✅ *(shipped 2026-04-20)*

- Canonical schema, Dhan adapter, FIFO round-trip engine, CLI, 5 tests.

## v0.1 — Web UI

- FastAPI + HTMX UI.
- Calendar heatmap (month view, P&L-coloured days, expiry days marked).
- Trade list with filters (date range, symbol, strategy, tag).
- Trade detail page with notes and tags.
- Daily note page (one markdown area + tag bucket per date).

## v0.2 — Attachments

- Image / video / audio / PDF uploads with thumbnails.
- Attach to a trade **or** a daily note.
- Client-side image resize before upload (bandwidth-friendly).
- Optional Whisper transcription for voice memos (local, no cloud).

## v0.3 — Mobile PWA + public launch

- Installable PWA shell (manifest, service worker, offline).
- Quick-capture screen (camera + mic + tag-to-today's-trades).
- Analytics: equity curve, stats strip (WR / PF / expectancy), R-multiple histogram.
- Launch: r/IndianStreetBets, HN Show, X / fintwit.

## v0.4 — Broker expansion

- **Zerodha (Kite)** — largest retail base in India.
- **Fyers** — OAuth, good WebSocket.
- **Upstox** — OAuth, solid REST.

## v0.5 — Strategy auto-tagger

- Detect iron condor / short straddle / strangle / BTST / expiry-day-selling from leg structure + timing.
- User override per trade.

## v0.6 — Playbook rules

- Pre-trade checklist enforced at place-time (mobile widget / Telegram bot).
- Score per trade. Correlate score with P&L.

## v1.0 — Tax engine + ITR export

- F&O P&L as non-speculative business income.
- Intraday equity as speculation.
- SEBI turnover formula.
- ITR-3 schedule output (Sch-BP, Sch-CG, Sch-OS).
- 44AB audit-flag detection.

## Beyond

- **Angel One** adapter (TOTP auth).
- **Groww / ICICI Direct / HDFC Sec** — contract-note PDF/email parsing (no retail API).
- Telegram / WhatsApp daily digest.
- Public profiles with verified P&L badge.
- Self-hosted hosted mode (multi-user) with per-user encryption key.

---

## Non-goals

- **Algo execution**. khata is a journal, not a trading engine. No order placement, ever.
- **Hosted SaaS run by the maintainer**. Self-host only — the trust posture is the product.
- **Advisory / tip / signal features**. Requires SEBI registration; not our domain.
