#!/usr/bin/env python3
"""Read-only web dashboard + REST API over the pickup monitor's SQLite history.

This does NOT run the monitor. The monitor (monitor.py) writes to the DB each
cron run; this viewer just reads whatever is there. Launch it on demand:

    pip install flask
    DB_PATH=pickup_history.db python dashboard.py
    # open http://127.0.0.1:5001

REST API (all JSON):
    GET /api/current                       latest state per store + per colour
    GET /api/history?store=R744&hours=24   raw per-store checks
    GET /api/changes?days=7&became=1       colour buyability change events
    GET /api/stats?days=7                  per-store totals / verified rate
"""
import os
from flask import Flask, jsonify, request, render_template_string

import db

DB_PATH = os.environ.get("DB_PATH", "pickup_history.db")
app = Flask(__name__)


def _no_cache(resp):
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/api/current")
def api_current():
    return _no_cache(jsonify(db.current_status(DB_PATH)))


@app.route("/api/history")
def api_history():
    store = request.args.get("store")
    hours = request.args.get("hours", 24, type=int)
    return _no_cache(jsonify(db.history(store, hours, db_path=DB_PATH)))


@app.route("/api/changes")
def api_changes():
    days = request.args.get("days", 7, type=int)
    became = request.args.get("became", 0, type=int) == 1
    return _no_cache(jsonify(db.changes(days, became, db_path=DB_PATH)))


@app.route("/api/stats")
def api_stats():
    days = request.args.get("days", 7, type=int)
    return _no_cache(jsonify(db.stats(days, DB_PATH)))


PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>iPhone 17 Pickup Monitor</title>
<style>
  :root { --bg:#f5f5f7; --card:#fff; --ink:#1d1d1f; --muted:#86868b;
          --ok:#1a7f37; --bad:#b42318; --warn:#9a6700; --line:#d2d2d7; --brand:#0071e3; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
         background:var(--bg); color:var(--ink); }
  header { padding:24px 20px 8px; }
  h1 { font-size:22px; margin:0 0 2px; }
  .sub { color:var(--muted); font-size:13px; }
  main { max-width:960px; margin:0 auto; padding:12px 16px 48px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:14px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px; }
  .card h2 { font-size:15px; margin:0 0 10px; }
  .pill { display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px; font-weight:600; }
  .pill.ok { background:#e6f4ea; color:var(--ok); }
  .pill.bad { background:#fde8e8; color:var(--bad); }
  .pill.warn { background:#fff4e5; color:var(--warn); }
  .colours { margin-top:10px; display:flex; flex-wrap:wrap; gap:6px; }
  .swatch { font-size:12px; padding:3px 8px; border-radius:8px; border:1px solid var(--line); }
  .swatch.ok { border-color:var(--ok); color:var(--ok); }
  .swatch.bad { color:var(--muted); }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); }
  th { color:var(--muted); font-weight:600; }
  .muted { color:var(--muted); }
  .section { margin-top:26px; }
  .row { display:flex; justify-content:space-between; align-items:baseline; }
  .foot { color:var(--muted); font-size:12px; margin-top:8px; }
  .empty { color:var(--muted); font-size:13px; padding:8px 0; }
</style>
</head>
<body>
<header>
  <div class="row">
    <div>
      <h1>iPhone 17 256GB · Pickup Monitor</h1>
      <div class="sub">Apple BKC &amp; Apple Borivali · auto-refreshes every 60s</div>
    </div>
  </div>
</header>
<main>
  <div class="grid" id="stores"></div>

  <div class="section">
    <div class="row"><h2 style="font-size:15px;margin:0">Recent changes (7d)</h2></div>
    <div class="card"><div id="changes"></div></div>
  </div>

  <div class="section">
    <div class="row"><h2 style="font-size:15px;margin:0">Reliability (7d)</h2></div>
    <div class="card"><div id="stats"></div></div>
  </div>

  <div class="foot" id="updated"></div>
</main>

<script>
const esc = s => String(s ?? "").replace(/[&<>]/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]));

function statePill(s){
  if(s==='available') return '<span class="pill ok">AVAILABLE</span>';
  if(s==='nostock')   return '<span class="pill bad">NO STOCK</span>';
  return '<span class="pill warn">UNVERIFIED</span>';
}

async function j(u){ const r = await fetch(u); return r.json(); }

async function load(){
  try {
    const cur = await j('api/current');
    const byStore = {};
    (cur.colours||[]).forEach(c => { (byStore[c.store_id] ??= []).push(c); });

    document.getElementById('stores').innerHTML = (cur.stores||[]).map(s => {
      const cols = (byStore[s.store_id]||[]).map(c =>
        `<span class="swatch ${c.is_buyable? 'ok':'bad'}">${esc(c.colour)}${c.is_buyable?' ✓':''}</span>`
      ).join('') || '<span class="empty">no verified colour data yet</span>';
      return `<div class="card">
        <div class="row"><h2>${esc(s.store_name)}</h2>${statePill(s.state)}</div>
        <div class="muted" style="font-size:12px">${esc(s.detail||'')}</div>
        <div class="colours">${cols}</div>
        <div class="foot">checked: ${esc(s.checked_at)} UTC</div>
      </div>`;
    }).join('') || '<div class="empty">No checks recorded yet. Run monitor.py first.</div>';

    const ch = await j('api/changes?days=7');
    document.getElementById('changes').innerHTML = ch.length ? `<table>
      <tr><th>When (UTC)</th><th>Store</th><th>Colour</th><th>Change</th></tr>
      ${ch.map(x => `<tr>
        <td>${esc(x.changed_at)}</td><td>${esc(x.store_name)}</td><td>${esc(x.colour)}</td>
        <td>${x.new_buyable? '<span class="pill ok">became buyable</span>':'<span class="pill bad">went unbuyable</span>'}</td>
      </tr>`).join('')}</table>` : '<div class="empty">No changes in the last 7 days.</div>';

    const st = await j('api/stats?days=7');
    document.getElementById('stats').innerHTML = st.length ? `<table>
      <tr><th>Store</th><th>Checks</th><th>Verified</th><th>Available</th><th>Became avail.</th></tr>
      ${st.map(x => `<tr>
        <td>${esc(x.store_name)}</td><td>${x.total_checks}</td>
        <td>${x.verified_rate}%</td><td>${x.available_checks}</td><td>${x.times_became_available}</td>
      </tr>`).join('')}</table>` : '<div class="empty">No stats yet.</div>';

    document.getElementById('updated').textContent = 'Dashboard refreshed: ' + new Date().toLocaleString();
  } catch (e) {
    document.getElementById('updated').textContent = 'Error loading data: ' + e;
  }
}
load();
setInterval(load, 60000);
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE)


if __name__ == "__main__":
    db.init_db(DB_PATH)  # ensure tables exist so the API doesn't 500 on a fresh DB
    import sys
    debug = "--production" not in sys.argv
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5001")), debug=debug)
