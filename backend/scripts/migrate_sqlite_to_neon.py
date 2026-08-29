#!/usr/bin/env python3
"""
Migrate SQLite events.db -> Neon Postgres.
Usage: DATABASE_URL=postgres://... python scripts/migrate_sqlite_to_neon.py
Requires: psycopg[binary]
"""
import os, sqlite3, json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

DB_PATH = Path(__file__).resolve().parent.parent / "events.db"
DATABASE_URL = os.getenv("DATABASE_URL","")
if not DATABASE_URL:
    print("Set DATABASE_URL first: export DATABASE_URL=postgres://...")
    exit(1)

import psycopg

src = sqlite3.connect(str(DB_PATH))
src.row_factory = sqlite3.Row

dst = psycopg.connect(DATABASE_URL, autocommit=True)
cur = dst.cursor()

# Ensure tables (same DDL as state.py pg)
cur.execute("""
CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, data JSONB NOT NULL, org TEXT, status TEXT, date TEXT, last_synced_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS org_settings (org TEXT PRIMARY KEY, data JSONB NOT NULL);
CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, org TEXT NOT NULL, role TEXT CHECK(role IN ('club','admin')), password_hash TEXT NOT NULL, is_sandbox INTEGER DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS room_bookings (id TEXT PRIMARY KEY, org TEXT NOT NULL, room TEXT NOT NULL, date TEXT NOT NULL, start_min INTEGER NOT NULL, end_min INTEGER NOT NULL, event_id TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(room, date, start_min, end_min));
CREATE TABLE IF NOT EXISTS event_responses (id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE, data JSONB NOT NULL, respondent_email TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS idx_events_org ON events(org);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);
CREATE INDEX IF NOT EXISTS idx_responses_event ON event_responses(event_id);
""")

def migrate(table, cols):
    rows = src.execute(f"SELECT * FROM {table}").fetchall()
    if not rows: print(f"{table}: 0 rows"); return
    for r in rows:
        d = dict(r)
        # data JSON -> JSONB
        if "data" in d and d["data"]:
            # psycopg handles json string
            pass
        placeholders = ",".join(["%s"]*len(cols))
        try:
            dst.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) ON CONFLICT DO NOTHING", [d[c] for c in cols])
        except Exception as e:
            print(f"skip {table} {d.get('id','?')}: {e}")
    print(f"{table}: migrated {len(rows)} rows")

migrate("events", ["id","data","org","status","date"])
migrate("org_settings", ["org","data"])
migrate("users", ["id","email","org","role","password_hash","is_sandbox","created_at"])
migrate("room_bookings", ["id","org","room","date","start_min","end_min","event_id","created_at"])
# event_responses likely empty initially
try:
    migrate("event_responses", ["id","event_id","data","respondent_email","created_at"])
except: pass

# Verify
for t in ["events","org_settings","users","room_bookings","event_responses"]:
    c = dst.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"VERIFY {t}: {c} rows in Neon")

src.close(); dst.close()
print("Done. Now deploy with DATABASE_URL set.")
