#!/usr/bin/env python3
"""SQLite state + history for the Apple India pickup monitor.

This is the shared state that makes a *stateless* cron/GitHub Actions run
behave like a stateful monitor. Every run writes:
  - one `checks` row per store (the resolved state: available/nostock/unverified)
  - one `colour_status` row per verified colour (isBuyable true/false)
  - `changes` rows whenever a colour's buyability flips vs. the previous run
  - `notifications` rows recording when we last alerted (for anti-spam cooldown)

The dashboard reads this same DB read-only.

DB location is DB_PATH env var, default ./pickup_history.db. On GitHub Actions,
point DB_PATH at a path you persist between runs (committed artifact, cache, or
a mounted volume) so history and cooldown state survive.
"""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "pickup_history.db")


@contextmanager
def _conn(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path=None):
    """Create tables/indices if they don't exist. Safe to call every run."""
    with _conn(db_path) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS checks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id   TEXT NOT NULL,
                store_name TEXT NOT NULL,
                state      TEXT NOT NULL,          -- available | nostock | unverified
                detail     TEXT,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS colour_status (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id    TEXT NOT NULL,
                store_name  TEXT NOT NULL,
                part        TEXT NOT NULL,
                colour      TEXT NOT NULL,
                is_buyable  INTEGER NOT NULL,       -- 0/1
                checked_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS changes (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id     TEXT NOT NULL,
                store_name   TEXT NOT NULL,
                part         TEXT NOT NULL,
                colour       TEXT NOT NULL,
                prev_buyable INTEGER,               -- NULL on first sighting
                new_buyable  INTEGER NOT NULL,
                changed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                kind      TEXT NOT NULL,            -- available | unverified
                signature TEXT NOT NULL,            -- what we alerted about
                sent_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for stmt in (
            "CREATE INDEX IF NOT EXISTS idx_checks_time ON checks(checked_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_checks_store ON checks(store_id, checked_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_colour_time ON colour_status(store_id, part, checked_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_changes_time ON changes(changed_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_notif ON notifications(kind, signature, sent_at DESC)",
        ):
            c.execute(stmt)


def record_check(store_id, store_name, state, detail, db_path=None):
    """Log the resolved per-store state for this run."""
    with _conn(db_path) as conn:
        conn.execute(
            "INSERT INTO checks (store_id, store_name, state, detail) VALUES (?,?,?,?)",
            (store_id, store_name, state, str(detail)),
        )


def record_colour(store_id, store_name, part, colour, is_buyable, db_path=None):
    """Log a single colour's verified buyability, and a change row if it flipped."""
    is_buyable = 1 if is_buyable else 0
    with _conn(db_path) as conn:
        c = conn.cursor()
        # Previous verified value for this store+part (if any).
        c.execute(
            "SELECT is_buyable FROM colour_status "
            "WHERE store_id=? AND part=? ORDER BY checked_at DESC, id DESC LIMIT 1",
            (store_id, part),
        )
        row = c.fetchone()
        prev = row["is_buyable"] if row else None

        c.execute(
            "INSERT INTO colour_status (store_id, store_name, part, colour, is_buyable) "
            "VALUES (?,?,?,?,?)",
            (store_id, store_name, part, colour, is_buyable),
        )
        if prev is None or prev != is_buyable:
            c.execute(
                "INSERT INTO changes (store_id, store_name, part, colour, prev_buyable, new_buyable) "
                "VALUES (?,?,?,?,?,?)",
                (store_id, store_name, part, colour, prev, is_buyable),
            )


def recently_notified(kind, signature, cooldown_seconds, db_path=None):
    """True if we already sent this exact alert within the cooldown window."""
    with _conn(db_path) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT sent_at FROM notifications "
            "WHERE kind=? AND signature=? "
            "AND sent_at > datetime('now', ?) "
            "ORDER BY sent_at DESC LIMIT 1",
            (kind, signature, f"-{int(cooldown_seconds)} seconds"),
        )
        return c.fetchone() is not None


def record_notification(kind, signature, db_path=None):
    with _conn(db_path) as conn:
        conn.execute(
            "INSERT INTO notifications (kind, signature) VALUES (?,?)",
            (kind, signature),
        )


# ---- read helpers used by the dashboard/API ----

def current_status(db_path=None):
    """Latest check per store + latest verified colour statuses."""
    with _conn(db_path) as conn:
        c = conn.cursor()
        stores = c.execute("""
            SELECT ch.* FROM checks ch
            JOIN (SELECT store_id, MAX(id) AS mid FROM checks GROUP BY store_id) last
              ON ch.id = last.mid
            ORDER BY ch.store_name
        """).fetchall()
        colours = c.execute("""
            SELECT cs.* FROM colour_status cs
            JOIN (SELECT store_id, part, MAX(id) AS mid FROM colour_status GROUP BY store_id, part) last
              ON cs.id = last.mid
            ORDER BY cs.store_name, cs.colour
        """).fetchall()
        return {
            "stores": [dict(r) for r in stores],
            "colours": [dict(r) for r in colours],
        }


def history(store_id=None, hours=24, limit=500, db_path=None):
    with _conn(db_path) as conn:
        q = "SELECT * FROM checks WHERE checked_at > datetime('now', ?)"
        params = [f"-{int(hours)} hours"]
        if store_id:
            q += " AND store_id = ?"
            params.append(store_id)
        q += " ORDER BY checked_at DESC LIMIT ?"
        params.append(int(limit))
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def changes(days=7, only_became_available=False, limit=200, db_path=None):
    with _conn(db_path) as conn:
        q = "SELECT * FROM changes WHERE changed_at > datetime('now', ?)"
        params = [f"-{int(days)} days"]
        if only_became_available:
            q += " AND new_buyable = 1"
        q += " ORDER BY changed_at DESC LIMIT ?"
        params.append(int(limit))
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def stats(days=7, db_path=None):
    with _conn(db_path) as conn:
        c = conn.cursor()
        out = []
        rows = c.execute("SELECT DISTINCT store_id, store_name FROM checks ORDER BY store_name").fetchall()
        for r in rows:
            sid = r["store_id"]
            base = "SELECT COUNT(*) FROM checks WHERE store_id=? AND checked_at > datetime('now', ?)"
            win = f"-{int(days)} days"
            total = c.execute(base, (sid, win)).fetchone()[0]
            avail = c.execute(base + " AND state='available'", (sid, win)).fetchone()[0]
            unver = c.execute(base + " AND state='unverified'", (sid, win)).fetchone()[0]
            became = c.execute(
                "SELECT COUNT(*) FROM changes WHERE store_id=? AND new_buyable=1 "
                "AND changed_at > datetime('now', ?)", (sid, win)).fetchone()[0]
            out.append({
                "store_id": sid,
                "store_name": r["store_name"],
                "total_checks": total,
                "available_checks": avail,
                "unverified_checks": unver,
                "verified_rate": round((total - unver) / total * 100, 1) if total else 0.0,
                "times_became_available": became,
            })
        return out
