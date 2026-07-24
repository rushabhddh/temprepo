# iPhone 17 256GB — Apple pickup monitor (GitHub Action)

Checks Apple India's live in-store **pickup** availability for the iPhone 17
256GB (all colours) at **Apple BKC** and **Apple Borivali**, and sends a
**Telegram** message the moment a colour becomes pickup-available at either store.
Stays silent otherwise.

## How it works
- Calls Apple India's public `buyability-message` API for both stores. The `apu`
  block in the response = Apple Pickup availability at that store.
- Runs on GitHub's servers on a cron schedule — nothing needs to stay open on your
  computer. The API is globally routed, so it works fine from GitHub's runners.

## Setup (one time, ~3 minutes)

1. **Create a GitHub repo** (private is fine), e.g. `iphone-pickup-monitor`.
2. Add these two files, keeping the exact paths:
   - `check.py`  →  repo root
   - `.github/workflows/iphone-monitor.yml`  ← rename/move `iphone-monitor.yml` into this path
3. **Add secrets:** repo → *Settings → Secrets and variables → Actions → New repository secret*. Add:
   - `TELEGRAM_TOKEN` = your bot token (`1446577636:AAG...hgCk`)
   - `TELEGRAM_CHAT_ID` = `549489041`
   (Keeping these as secrets means the token isn't committed in the code.)
4. Push. Go to the **Actions** tab, and if prompted, enable workflows.
5. Click the workflow → **Run workflow** to test it once manually. You'll see
   `AVAILABLE: NONE` in the logs (correct — not in stock yet).

That's it. From then on it checks every 5 minutes and pings your Telegram when
pickup opens up.

## Notes
- **Frequency:** GitHub scheduled workflows don't reliably run more often than
  every ~5 min and can be delayed under load, so this uses `*/5`. (Every 3 min
  isn't dependable on GitHub Actions.)
- **Cron is UTC** on GitHub — doesn't matter here since it's a fixed interval.
- **It alerts on every run while a colour is in stock**, so you'll keep getting
  pings until you buy it or disable the workflow. To stop: disable the workflow
  in the Actions tab.
- **Reference data:**
  - Part numbers: Black `MG6J4HN/A`, White `MG6K4HN/A`, Lavender `MG6M4HN/A`,
    Sage `MG6N4HN/A`, Mist Blue `MG6Q4HN/A`
  - Stores: `R744` = Apple BKC, `R757` = Apple Borivali
- If Apple ever changes part numbers (new model year), update the `PARTS` dict in
  `check.py`.
