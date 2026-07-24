#!/usr/bin/env python3
"""Check Apple India in-store PICKUP availability for iPhone 17 256GB
at Apple BKC and Apple Borivali, and send a Telegram alert if available.

Uses Apple India's public buyability API. The `apu` block in the response
= Apple Pickup availability at the given store.
"""
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


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cookie": COOKIE})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def send_telegram(text):
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    with urllib.request.urlopen(url, data=data, timeout=30) as r:
        print("Telegram:", r.read().decode()[:200])


def main():
    query = "&".join(
        f"parts.{i}={urllib.parse.quote(p, safe='')}"
        for i, p in enumerate(PARTS)
    )
    available = []
    for sid, sname in STORES.items():
        url = f"https://www.apple.com/in/shop/buyability-message?{query}&store={sid}"
        try:
            data = fetch(url)
            apu = data["body"]["content"]["buyabilityMessage"].get("apu", {})
        except Exception as e:
            print(f"WARN {sname}: {e}")
            apu = {}
        for part, v in apu.items():
            if v.get("isBuyable") is True:
                available.append(f"{PARTS.get(part, part)} @ {sname}")

    if available:
        msg = (
            "\U0001F389 iPhone 17 256GB pickup AVAILABLE now: "
            + "; ".join(available)
            + ".\nReserve/buy: https://www.apple.com/in/shop/buy-iphone/iphone-17 "
            "→ choose 'Pick up' and select the store."
        )
        print("AVAILABLE:", "; ".join(available))
        send_telegram(msg)
    else:
        print("AVAILABLE: NONE (staying silent)")


if __name__ == "__main__":
    main()
