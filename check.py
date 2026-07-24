#!/usr/bin/env python3
"""Check Apple India in-store PICKUP availability for iPhone 17 256GB
at Apple BKC and Apple Borivali, and send a Telegram alert.

Modes (HEARTBEAT env var):
  - Default: alert ONLY when a colour is pickup-available. Also alert if the
    check could NOT be verified (so a silent breakage never looks like "no stock").
  - HEARTBEAT=1: always send a status message with the exact per-store result
    and a timestamp, so you know it is genuinely running.

Each store is resolved to one of three states, never guessed:
  - AVAILABLE  : Apple returned apu.<part>.isBuyable == True
  - NO STOCK   : Apple returned a valid apu block for our parts, all isBuyable False
  - UNVERIFIED : fetch failed, or the response didn't contain our parts (format
                 change / block). This is NOT reported as "no stock".
"""
import datetime
import json
import os
import urllib.parse
import urllib.request

# iPhone 17 256GB India part numbers (all colours)
PARTS = {
    "MG6J4HN/A": "Black",
    "MG6K4HN/A": "White",
    "MG6M4HN/A": "Lavender",
    "MG6N4HN/A": "Sage",
    "MG6Q4HN/A": "Mist Blue",
}
STORES = {"R744": "Apple BKC", "R757": "Apple Borivali"}

COOKIE = "as_sfa=Mnxpbnxpbnx8ZW5fSU58Y29uc3VtZXJ8aW50ZXJuZXR8MHwwfDE"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
HEARTBEAT = os.environ.get("HEARTBEAT", "0") == "1"

BUY_URL = "https://www.apple.com/in/shop/buy-iphone/iphone-17"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cookie": COOKIE})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def send_telegram(text):
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    with urllib.request.urlopen(url, data=data, timeout=30) as r:
        print("Telegram:", r.read().decode()[:200])


def ist_now():
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.now(ist).strftime("%d %b %Y, %I:%M %p IST")


def check_store(sid, query):
    """Return (state, detail). state in {'available','nostock','unverified'}."""
    url = f"https://www.apple.com/in/shop/buyability-message?{query}&store={sid}"
    try:
        data = fetch(url)
    except Exception as e:
        return "unverified", f"fetch failed: {e}"

    try:
        apu = data["body"]["content"]["buyabilityMessage"]["apu"]
    except (KeyError, TypeError):
        # No apu block at all -> we did NOT actually verify pickup status.
        return "unverified", "no 'apu' block in Apple response (format change/block)"

    # Confirm the response actually covered OUR parts. If none of our part
    # numbers are present, we cannot claim "no stock".
    seen = [p for p in PARTS if p in apu]
    if not seen:
        return "unverified", "Apple response did not include our part numbers"

    ready = [PARTS[p] for p in seen if apu[p].get("isBuyable") is True]
    if ready:
        return "available", ready
    return "nostock", f"{len(seen)}/{len(PARTS)} colours confirmed, none buyable"


def main():
    query = "&".join(
        f"parts.{i}={urllib.parse.quote(p, safe='')}" for i, p in enumerate(PARTS)
    )

    results = {sid: check_store(sid, query) for sid in STORES}
    now = ist_now()
    for sid, (state, detail) in results.items():
        print(f"{STORES[sid]}: {state} — {detail}")

    available = [
        f"{c} @ {STORES[sid]}"
        for sid, (state, detail) in results.items()
        if state == "available"
        for c in detail
    ]
    unverified = [STORES[sid] for sid, (state, _) in results.items() if state == "unverified"]

    # 1) Real stock -> always alert (any mode)
    if available:
        send_telegram(
            "\U0001F389 iPhone 17 256GB pickup AVAILABLE now: "
            + "; ".join(available)
            + f".\nReserve/buy: {BUY_URL} → choose 'Pick up' and pick the store.\n"
            + f"(checked {now})"
        )
        return

    # 2) Couldn't verify (both stores) even on a normal run -> alert, so silence
    #    is never mistaken for "no stock". One-off blips on a single store are
    #    left for the hourly heartbeat to surface.
    if len(unverified) == len(STORES) and not HEARTBEAT:
        send_telegram(
            "⚠️ Monitor could NOT verify pickup status this run "
            f"({', '.join(unverified)}). Apple API may have changed or is blocking. "
            f"Will keep trying. ({now})"
        )
        return

    # 3) Heartbeat -> report exactly what was found per store
    if HEARTBEAT:
        lines = []
        for sid, (state, detail) in results.items():
            if state == "nostock":
                lines.append(f"• {STORES[sid]}: no pickup stock (verified live ✓)")
            elif state == "unverified":
                lines.append(f"• {STORES[sid]}: ⚠️ could not verify — {detail}")
        send_telegram(
            "✅ Monitor is running. Live check just now:\n"
            + "\n".join(lines)
            + f"\nLast checked: {now}"
        )


if __name__ == "__main__":
    main()
