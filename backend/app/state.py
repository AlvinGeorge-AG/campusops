import sqlite3
import json
from typing import Optional, List
from .models import Event, EventStatus
from .config import DB_PATH

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
"""

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(CREATE_TABLE)
    conn.commit()
    return conn

def save_event(event: Event):
    event.ensure_id()
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO events (id, data) VALUES (?, ?)",
                 (event.id, event.model_dump_json()))
    conn.commit()
    conn.close()
    return event

def get_event(event_id: str) -> Optional[Event]:
    conn = get_conn()
    cur = conn.execute("SELECT data FROM events WHERE id=?", (event_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return Event.model_validate_json(row[0])

def list_events() -> List[Event]:
    conn = get_conn()
    cur = conn.execute("SELECT data FROM events")
    rows = cur.fetchall()
    conn.close()
    return [Event.model_validate_json(r[0]) for r in rows]

def get_latest_event() -> Optional[Event]:
    events = list_events()
    if not events:
        return None
    # sort by created_at desc
    events.sort(key=lambda e: e.created_at, reverse=True)
    return events[0]

def update_event(event_id: str, **kwargs) -> Optional[Event]:
    event = get_event(event_id)
    if not event:
        return None
    for k, v in kwargs.items():
        if hasattr(event, k):
            setattr(event, k, v)
    return save_event(event)
