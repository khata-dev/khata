# Contributing

## Setup

```bash
uv sync --all-extras
uv run pytest
uv run ruff check khata
```

## What's welcome

- **New broker adapters.** See [`docs/ADAPTERS.md`](docs/ADAPTERS.md).
- **Bug fixes** with a reproducing test.
- **Analytics** — new charts, new metrics. Keep them in `khata/web/analytics/`.
- **Docs** — anything that helps someone self-host faster.

## What's less welcome (ask first)

- Major UI overhauls. The stack is intentionally boring.
- Hosted-service features. khata is self-hosted.
- Telemetry, analytics-on-users, phone-home. Non-starter.

## PR expectations

- One logical change per PR.
- Tests for anything that isn't trivial.
- `ruff check` clean.
