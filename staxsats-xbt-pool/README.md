# Terminus Pool

Umbrel dashboard and public website for Terminus Pool, an XBT BLAKE2b pool built around RATUM Prime and native DATUM.

## Privacy and deployment boundaries

- `/api/stats` is aggregate telemetry. Account data appears only after an explicit payout-address lookup.
- `/api/stats?view=leaderboard` exposes opaque aliases; it never returns payout addresses.
- `/admin` and `/api/admin/miners` are enabled only by the private owner marker or deployment environment.
- Community Store installs use the authoritative public Terminus relay by default. Only the owner marker or an explicit `TERMINUS_TELEMETRY_MODE=local` override enables local RATUM telemetry.
- The Pi collects durable SQLite history. The VPS relays Pi telemetry with its collector disabled.
- Public `23334` is a hidden RouteHash return relay. It is not advertised in the UI or DNS.

## Checks

```bash
python3 -m py_compile staxsats-xbt-pool/data/server.py
python3 -m unittest discover -s staxsats-xbt-pool/tests -v
```

## Release gate

1. Update `server.py` and `umbrel-app.yml` together.
2. Run syntax, unit, privacy, secret, desktop, and mobile checks.
3. Verify published GitHub blobs match the tested local hashes.
4. Back up live source, manifest, compose, and SQLite state before deployment.
5. Preserve Pi/VPS environment differences and verify DATUM plus the hidden RouteHash return relay.
