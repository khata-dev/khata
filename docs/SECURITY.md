# Security

## Your broker tokens

- Tokens live in `.env` (gitignored) or encrypted in the DB with `KHATA_SECRET`.
- khata never sends tokens anywhere except to the broker's API.
- There is zero telemetry. No network calls to khata's own servers (there are no khata servers).

## Reporting vulnerabilities

Email the maintainer privately rather than opening a public issue. Responsible disclosure gets a fast response.

## Self-hosting

- Run behind Tailscale or a VPN; don't expose port 8000 to the public internet.
- Back up `data/khata.db` regularly (it's SQLite — `cp` works).
- If you rotate `KHATA_SECRET`, re-encrypt the DB (`khata rotate-secret`).
