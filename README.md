# iPhone 17 Pickup Monitor (Apple India)

Checks in-store **pickup** availability for iPhone 17 256GB (all colours) at Apple BKC
and Apple Borivali via Apple's `buyability-message` JSON API, and alerts on Telegram.

Built to run **stateless** (cron / GitHub Actions): each run exits on its own. A small
SQLite file is the shared state that gives you history, a dashboard, and anti-spam
across those independent runs.

## Files

| File | Purpose | Needs |
|------|---------|-------|
| `monitor.py` | The checker. Run this on a schedule. | stdlib (cloudscraper optional) |
| `db.py` | SQLite history + notification cooldown state. | stdlib |
| `dashboard.py` | On-demand web dashboard + REST API (read-only). | Flask |
| `requirements.txt` | Optional deps only. | — |

## What was added vs. the original script

The original 3-state logic (`available` / `nostock` / `unverified`, never guessed) is
**unchanged**. On top of it:

- **Error recovery / retries** — each store fetch retries with exponential backoff
  (`FETCH_RETRIES`, `FETCH_BACKOFF`) before it's declared UNVERIFIED, so a transient
  blip doesn't trigger a false "couldn't verify" alert.
- **Anti-block fallback** — rotates the User-Agent across retries, then falls back to
  `cloudscraper` (if installed) when plain `urllib` is blocked. If cloudscraper isn't
  installed, it's simply skipped.
- **Rate limiting / anti-spam** — an identical alert (same colours@stores, or same set
  of unverified stores) is suppressed within a cooldown window (`ALERT_COOLDOWN_SECONDS`,
  default 6h). The last-sent timestamp lives in SQLite, so suppression works even though
  each cron run is a fresh process. Real stock transitions after the window still alert.
- **History + dashboard + API** — every run logs per-store state and per-colour
  buyability, and records a change event when a colour flips. `dashboard.py` serves a
  live page plus JSON endpoints over that history.

## Quick start (local)

```bash
export TELEGRAM_TOKEN=123456:abc
export TELEGRAM_CHAT_ID=987654

# one live check (alerts only on stock or total unverified)
python monitor.py

# always-report heartbeat
HEARTBEAT=1 python monitor.py

# view history (separate terminal; reads the same DB)
pip install flask
python dashboard.py        # http://127.0.0.1:5001
```

`monitor.py` runs with **zero** third-party packages. Install `cloudscraper` only if you
want the anti-block fallback; install `Flask` only for the dashboard.

## Environment variables

| Var | Default | Meaning |
|-----|---------|---------|
| `TELEGRAM_TOKEN` | — (required) | Bot token |
| `TELEGRAM_CHAT_ID` | — (required) | Chat/channel ID |
| `HEARTBEAT` | `0` | `1` = always send a status message |
| `DB_PATH` | `pickup_history.db` | Where state/history is stored |
| `ALERT_COOLDOWN_SECONDS` | `21600` | Anti-spam window (6h) |
| `FETCH_RETRIES` | `3` | Attempts per store fetch |
| `FETCH_BACKOFF` | `2.0` | Base backoff seconds (doubles each retry) |
| `DISABLE_DB` | `0` | `1` = pure-stdlib, no history/anti-spam (original behaviour) |

## Persisting the DB on GitHub Actions

The catch with a stateless runner: unless you persist `pickup_history.db`, every run
starts blank — you lose history **and** anti-spam (so a long-lived stock could ping every
run). Pick one:

**Option A — commit the DB back (simplest, keeps full history):**

```yaml
name: pickup-monitor
on:
  schedule: [{ cron: "*/10 * * * *" }]   # every 10 min
  workflow_dispatch:
permissions:
  contents: write
jobs:
  check:
    runs-on: ubuntu-latest
    concurrency: pickup-monitor          # avoid overlapping runs racing the DB
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install cloudscraper      # optional, enables anti-block fallback
      - env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          DB_PATH: pickup_history.db
        run: python monitor.py
      - run: |
          git config user.name  "monitor-bot"
          git config user.email "monitor-bot@users.noreply.github.com"
          git add pickup_history.db
          git commit -m "history $(date -u +%FT%TZ)" || echo "no change"
          git pull --rebase --autostash && git push || echo "push skipped"
```

Add an hourly heartbeat by duplicating the job with `HEARTBEAT: "1"` on a `0 * * * *`
cron.

**Option B — no history, just correct alerts:** set `DISABLE_DB=1` and drop the commit
step. You keep the monitor and Telegram alerts but lose history, the dashboard data, and
cross-run anti-spam.

> The dashboard is a **local viewer**, not a hosted service. Pull the repo (which now
> contains `pickup_history.db`) and run `python dashboard.py` whenever you want to look.
> To host it live, run `monitor.py` and `dashboard.py` on the same box (a small VM) with a
> shared `DB_PATH` instead of GitHub Actions.

## REST API

| Endpoint | Description |
|----------|-------------|
| `GET /api/current` | Latest state per store + latest per-colour buyability |
| `GET /api/history?store=R744&hours=24` | Raw per-store checks |
| `GET /api/changes?days=7&became=1` | Colour buyability change events (`became=1` = only "became buyable") |
| `GET /api/stats?days=7` | Per-store totals, verified rate, times became available |

## Notes

- Store codes: `R744` = Apple BKC, `R757` = Apple Borivali. Part numbers are the five
  iPhone 17 256GB India colours. Edit `PARTS` / `STORES` in `monitor.py` to change them.
- The cookie and endpoint are Apple's public buyability path; if Apple changes the
  response shape, the monitor reports **UNVERIFIED** (and alerts) rather than a false
  "no stock".
