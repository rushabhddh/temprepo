#!/usr/bin/env python3
"""Export the current SQLite state to docs/data.json for the static GitHub Pages
dashboard. Run this after the checks, before committing.

The Pages site (docs/index.html) fetches this file client-side and renders it,
so no server is needed — GitHub Pages serves it as a plain static file.
"""
import datetime
import json
import os

import db

DB_PATH = os.environ.get("DB_PATH", "pickup_history.db")
OUT = os.environ.get("STATUS_JSON", "docs/data.json")

db.init_db(DB_PATH)

payload = {
    "generated_at_utc": datetime.datetime.now(datetime.timezone.utc)
    .strftime("%Y-%m-%d %H:%M:%SZ"),
    "current": db.current_status(DB_PATH),
    "changes": db.changes(days=7, db_path=DB_PATH),
    "stats": db.stats(days=7, db_path=DB_PATH),
}

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
with open(OUT, "w") as f:
    json.dump(payload, f, indent=2, default=str)

print(f"Wrote {OUT}: {len(payload['current'].get('stores', []))} stores, "
      f"{len(payload['changes'])} changes, {len(payload['stats'])} stat rows")
