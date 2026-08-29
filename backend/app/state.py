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

CREATE_ORG_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS org_settings (
    org TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
"""

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(CREATE_TABLE)
    conn.execute(CREATE_ORG_SETTINGS_TABLE)
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


# --- Org Settings ---
from .models import OrgSettings as _OrgSettings
from .config import INSTITUTION_NAME as _INST_NAME, INSTITUTION_PLACE as _INST_PLACE, FACULTY_EMAIL as _FAC_EMAIL, ANNOUNCEMENT_RECIPIENTS as _ANN_RECIP, DEFAULT_CHAIRPERSON as _DEF_CHAIR, DEFAULT_STAFF as _DEF_STAFF

def _default_org_settings(org: str) -> _OrgSettings:
    return _OrgSettings(
        org=org,
        institution_name=_INST_NAME,
        institution_place=_INST_PLACE,
        faculty_email=_FAC_EMAIL,
        announcement_recipients=_ANN_RECIP,
        chairperson=_DEF_CHAIR,
        staff_in_charge=_DEF_STAFF,
    )

def get_org_settings(org: str) -> _OrgSettings:
    if not org or not org.strip():
        org = "default"
    org = org.strip()
    conn = get_conn()
    cur = conn.execute("SELECT data FROM org_settings WHERE org=?", (org,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return _default_org_settings(org)
    try:
        return _OrgSettings.model_validate_json(row[0])
    except:
        return _default_org_settings(org)

def save_org_settings(settings: _OrgSettings) -> _OrgSettings:
    settings.ensure_updated()
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO org_settings (org, data) VALUES (?, ?)", (settings.org, settings.model_dump_json()))
    conn.commit()
    conn.close()
    return settings

def list_org_settings() -> List[_OrgSettings]:
    conn = get_conn()
    cur = conn.execute("SELECT data FROM org_settings")
    rows = cur.fetchall()
    conn.close()
    out = []
    for r in rows:
        try:
            out.append(_OrgSettings.model_validate_json(r[0]))
        except:
            pass
    return out

def get_effective_settings(org: str) -> _OrgSettings:
    """Helper used by email/letters to resolve dynamic settings with fallback."""
    return get_org_settings(org)
