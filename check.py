#!/usr/bin/env python3
"""Check Apple India in-store PICKUP availability for iPhone 17 256GB
at Apple BKC and Apple Borivali, and send a Telegram alert.

Two modes (controlled by the HEARTBEAT env var):
  - Default (HEARTBEAT unset/0): alert ONLY when a colour is pickup-available.
    Silent otherwise. Use this for the frequent (every-5-min) run.
  - HEARTBEAT=1: always send a status message ("still running" + current
    status + timestamp), whether or not stock is available. Use this hourly.

Uses Apple India's public buyability API. The `apu` block in the response
= Apple Pickup availability at the given store.
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

# India-locale cookie so Apple serves the IN store context
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


def main():
    query = "&".join(
        f"parts.{i}={urllib.parse.quote(p, safe='')}"
        for i, p in enumerate(PARTS)
    )
    available = []
    errors = 0
    for sid, sname in STORES.items():
        url = f"https://www.apple.com/in/shop/buyability-message?{query}&store={sid}"
        try:
            data = fetch(url)
            apu = data["body"]["content"]["buyabilityMessage"].get("apu", {})
        except Exception as e:
            print(f"WARN {sname}: {e}")
            errors += 1
            apu = {}
        for part, v in apu.items():
            if v.get("isBuyable") is True:
                available.append(f"{PARTS.get(part, part)} @ {sname}")

    now = ist_now()

    if available:
        print("AVAILABLE:", "; ".join(available))
        send_telegram(
            "\U0001F389 iPhone 17 256GB pickup AVAILABLE now: "
            + "; ".join(available)
            + f".\nReserve/buy: {BUY_URL} → choose 'Pick up' and pick the store.\n"
            + f"(checked {now})"
        )
        return

    print("AVAILABLE: NONE")

    if HEARTBEAT:
        status = "not available for pickup yet" if errors < len(STORES) else (
            "could not reach Apple this run (will retry)"
        )
        send_telegram(
            "✅ Monitor is running.\n"
            f"iPhone 17 256GB @ Apple BKC / Borivali: {status}.\n"
            f"Last checked: {now}"
        )


if __name__ == "__main__":
    main()
