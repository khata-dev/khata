# Changelog

All notable changes to khata are documented here. This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- GitHub Actions CI (lint + matrix test on Ubuntu + macOS × Python 3.11/3.12/3.13)
- Dependabot weekly updates for pip and GitHub Actions
- Issue templates (bug / feature / broker adapter) and PR template
- `CODE_OF_CONDUCT.md` (Contributor Covenant v2.1)
- `CODEOWNERS`
- `ROADMAP.md`

## [0.0.1] — 2026-04-20

### Added
- Apache 2.0 licence, published at [github.com/khata-dev/khata](https://github.com/khata-dev/khata).
- SQLite canonical schema: `users`, `broker_credentials`, `broker_events`, `executions`, `trades`, `trade_legs`, `strategies`, `notes`, `tags`, `trade_tags`, `attachments`, `playbooks`, `trade_playbook_runs`, `sync_runs`.
- `BrokerAdapter` protocol with canonical types (`CanonicalExecution`, `CanonicalPosition`, `CanonicalOrder`, `CanonicalFees`).
- Dhan v2 REST adapter: client (throttled), mapper (trade-book → canonical), adapter (trades + backfill chunking).
- FIFO round-trip reconstruction engine covering scale-ins, scale-outs, overshoots, multi-contract isolation.
- Typer CLI: `init`, `sync`, `backfill`, `stats`, `reset`, `dump-executions`.
- Docker + docker-compose scaffolding.
- README with logo, comparison table, and design principles.
- `docs/ADAPTERS.md` — contributor guide for adding a broker.
- `docs/SECURITY.md` — responsible-disclosure process and self-hosting guidance.
- 5 round-trip engine tests (all green).
