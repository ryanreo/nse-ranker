"""Push the dashboard's tables to Supabase, where the dashboard reads them live.

Needs SUPABASE_URL and SUPABASE_SECRET_KEY in .env. The secret key bypasses row-level security, so it
stays on this PC only: the tables have no public access rules, and the dashboard reads them through
the owner's Supabase connection, not this key.
"""
from datetime import date

from . import web
from .sources.eodhd import ENV_FILE

BATCH = 500

# Table -> (primary key columns, columns sent). Rows are upserted on the primary key.
TABLES = {
    "stocks": (["ticker"], ["ticker", "name", "sector", "type", "currency", "status", "notes"]),
    "method": (["key"], ["key", "factor", "weight", "measures", "hold"]),
    "prices": (["ticker", "day"], ["ticker", "day", "close"]),
    "rankings": (["run_date", "ticker"], None),   # every column of the ranking rows, plus run_date
    "stats": (["run_date", "ticker"], None),
    "news_tags": (["id"], ["id", "day", "ticker", "sector", "about", "event", "direction", "strength", "title", "url"]),
    "articles": (["key"], ["key", "ticker", "day", "title", "source", "url"]),
    "posts": (["id"], ["id", "ticker", "platform", "posted", "text"]),
    "not_ranked": (["ticker"], ["ticker", "name", "status", "reason"]),
}
# Which export table feeds which Supabase table.
SOURCES = {"stocks": "stocks", "method": "method", "prices": "prices", "rankings": "ranking", "stats": "stats",
           "news_tags": "news", "articles": "articles", "posts": "posts", "not_ranked": "not_ranked"}
REPLACED = {"not_ranked"}   # emptied first, so stocks that are ranked again drop off


def settings(env_file=ENV_FILE):
    values = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            name, _, value = line.partition("=")
            values[name.strip()] = value.strip()
    url, key = values.get("SUPABASE_URL"), values.get("SUPABASE_SECRET_KEY")
    if not (url and key):
        raise RuntimeError("Add SUPABASE_URL and SUPABASE_SECRET_KEY to .env to push to Supabase.")
    return url.rstrip("/"), key


def _headers(key):
    headers = {"apikey": key}
    if key.startswith("eyJ"):   # an older JWT-style key also goes in Authorization
        headers["Authorization"] = f"Bearer {key}"
    return headers


def shape(table, rows, run_date):
    """Keep only the table's columns; add run_date to the per-run tables."""
    _, columns = TABLES[table]
    shaped = []
    for row in rows:
        row = dict(row, run_date=run_date) if table in ("rankings", "stats") else row
        shaped.append({c: row.get(c) for c in columns} if columns else row)
    return shaped


def push(tables, run_date=None, send=web.send, env_file=ENV_FILE, progress=print):
    """Upsert each table (from export.build_all) into Supabase. Returns {table: rows sent}."""
    url, key = settings(env_file)
    run_date = (run_date or date.today()).isoformat()
    headers = _headers(key)
    sent = {}
    for table, source in SOURCES.items():
        rows = shape(table, tables.get(source, []), run_date)
        pk, _ = TABLES[table]
        if table in REPLACED:
            send("DELETE", f"{url}/rest/v1/{table}?{pk[0]}=not.is.null", headers=headers)
        upsert = dict(headers, Prefer="resolution=merge-duplicates,return=minimal")
        for start in range(0, len(rows), BATCH):
            send("POST", f"{url}/rest/v1/{table}?on_conflict={','.join(pk)}", rows[start:start + BATCH], upsert)
        sent[table] = len(rows)
        progress(f"  {table}: {len(rows)} rows")
    return sent
