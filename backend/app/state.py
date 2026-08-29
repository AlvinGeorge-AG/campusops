import sqlite3
import json
from typing import Optional, List
from .models import Event, EventStatus
from .config import DB_PATH

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    org TEXT,
    status TEXT,
    date TEXT
);
"""

CREATE_ORG_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS org_settings (
    org TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
"""

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    org TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('club','admin')),
    password_hash TEXT NOT NULL,
    is_sandbox INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

CREATE_ROOM_BOOKINGS_TABLE = """
CREATE TABLE IF NOT EXISTS room_bookings (
    id TEXT PRIMARY KEY,
    org TEXT NOT NULL,
    room TEXT NOT NULL,
    date TEXT NOT NULL,
    start_min INTEGER NOT NULL,
    end_min INTEGER NOT NULL,
    event_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(room, date, start_min, end_min)
);
"""

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(CREATE_TABLE)
    conn.execute(CREATE_ORG_SETTINGS_TABLE)
    conn.execute(CREATE_USERS_TABLE)
    conn.execute(CREATE_ROOM_BOOKINGS_TABLE)
    # Ensure columns exist for old DBs
    for col in [("org","TEXT"),("status","TEXT"),("date","TEXT")]:
        try:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col[0]} {col[1]}")
        except: pass
    # Backfill org/status/date columns & indexes (idempotent)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_org ON events(org)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_date ON events(date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_org_date ON events(org, date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_room_bookings_room_date ON room_bookings(room, date)")
    except: pass
    # Backfill from JSON blob where org is null or empty
    try:
        cur = conn.execute("SELECT id, data FROM events WHERE org IS NULL OR org=''")
        for eid, data in cur.fetchall():
            try:
                obj = json.loads(data)
                org = (obj.get("org") or "").strip()
                status = obj.get("status") or ""
                date = obj.get("date") or ""
                conn.execute("UPDATE events SET org=?, status=?, date=? WHERE id=?", (org, status, date, eid))
            except: pass
        conn.commit()
    except: pass
    return conn

def save_event(event: Event):
    event.ensure_id()
    # keep indexed columns in sync
    org = (event.org or "").strip()
    status = event.status.value if hasattr(event.status, "value") else str(event.status)
    date = event.date or ""
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO events (id, data, org, status, date) VALUES (?, ?, ?, ?, ?)",
                 (event.id, event.model_dump_json(), org, status, date))
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

def list_events(org: Optional[str] = None, scope_all: bool = True) -> List[Event]:
    conn = get_conn()
    if org and not scope_all:
        cur = conn.execute("SELECT data FROM events WHERE org=?", (org.strip(),))
    else:
        cur = conn.execute("SELECT data FROM events")
    rows = cur.fetchall()
    conn.close()
    evs = [Event.model_validate_json(r[0]) for r in rows]
    # Sort by date+created_at in python (JSON fields)
    try:
        evs.sort(key=lambda e: (e.date or "", e.created_at or ""), reverse=True)
    except: pass
    return evs

def get_latest_event(org: Optional[str] = None) -> Optional[Event]:
    if org:
        # org-scoped latest
        evs = list_events(org=org, scope_all=False)
        if evs:
            evs.sort(key=lambda e: e.created_at, reverse=True)
            return evs[0]
        return None
    events = list_events(scope_all=True)
    if not events:
        return None
    events.sort(key=lambda e: e.created_at, reverse=True)
    return events[0]

def get_event_for_org(event_id: str, org: str) -> Optional[Event]:
    ev = get_event(event_id)
    if not ev: return None
    if ev.org.strip().lower() != org.strip().lower():
        return None
    return ev

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

def is_org_configured(org: str) -> tuple[bool, list[str]]:
    """Check if org has completed required settings. Returns (is_ready, missing_fields). TEST_CLUB sandbox is always ready."""
    if not org or org.strip().lower() == "test_club":
        return True, []
    # Check if row exists
    conn = get_conn()
    cur = conn.execute("SELECT data FROM org_settings WHERE org=?", (org.strip(),))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False, ["institution_name", "institution_place", "faculty_email", "announcement_recipients", "chairperson", "staff_in_charge"]
    try:
        s = _OrgSettings.model_validate_json(row[0])
    except:
        return False, ["institution_name", "institution_place", "faculty_email", "announcement_recipients", "chairperson", "staff_in_charge"]
    missing = []
    # Check placeholders
    if not s.institution_name or not s.institution_name.strip() or s.institution_name.strip() == "Govt. Model Engineering College":
        # Actually allow this default but require explicit? For now require non-empty and not placeholder example? Let's be lenient: institution can be default, but we still require faculty etc.
        pass
    if not s.institution_name or not s.institution_name.strip():
        missing.append("institution_name")
    if not s.institution_place or not s.institution_place.strip():
        missing.append("institution_place")
    if not s.faculty_email or not s.faculty_email.strip() or s.faculty_email.strip() == "principal@example.com" or "example.com" in s.faculty_email or "@" not in s.faculty_email:
        missing.append("faculty_email")
    if not s.announcement_recipients or not s.announcement_recipients.strip() or "example.com" in s.announcement_recipients:
        missing.append("announcement_recipients")
    if not s.chairperson or not s.chairperson.strip():
        missing.append("chairperson")
    if not s.staff_in_charge or not s.staff_in_charge.strip():
        missing.append("staff_in_charge")
    return (len(missing) == 0), missing

def is_google_connected(org: str) -> bool:
    """Check if Drive is connected. CENTRAL_DRIVE=true -> admin token is enough for all clubs."""
    if not org or org.strip().lower() == "test_club":
        return True  # sandbox doesn't need Drive
    try:
        from .config import CENTRAL_DRIVE, GOOGLE_TOKEN_PATH, google_token_path_for_org
        import os
        if CENTRAL_DRIVE:
            # Central mode: admin token is source for all clubs
            if os.path.exists(GOOGLE_TOKEN_PATH) or os.path.exists("backend/token.json") or os.path.exists("./token.json"):
                return True
        path = google_token_path_for_org(org)
        if os.path.exists(path):
            return True
        # Fallback to admin token for migration
        if os.path.exists(GOOGLE_TOKEN_PATH):
            return True
        return False
    except:
        return False

# --- Users ---
import uuid
from datetime import datetime as _dt

def create_user(email: str, org: str, role: str, password_hash: str, is_sandbox: bool = False):
    uid = str(uuid.uuid4())
    conn = get_conn()
    conn.execute("INSERT INTO users (id, email, org, role, password_hash, is_sandbox, created_at) VALUES (?,?,?,?,?,?,?)",
                 (uid, email.strip().lower(), org.strip(), role, password_hash, 1 if is_sandbox else 0, _dt.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return uid

def get_user_by_email(email: str):
    conn = get_conn()
    cur = conn.execute("SELECT id, email, org, role, password_hash, is_sandbox, created_at FROM users WHERE email=?", (email.strip().lower(),))
    row = cur.fetchone()
    conn.close()
    if not row: return None
    return {"id":row[0],"email":row[1],"org":row[2],"role":row[3],"password_hash":row[4],"is_sandbox":bool(row[5]),"created_at":row[6]}

def get_user_by_id(uid: str):
    conn = get_conn()
    cur = conn.execute("SELECT id, email, org, role, password_hash, is_sandbox, created_at FROM users WHERE id=?", (uid,))
    row = cur.fetchone()
    conn.close()
    if not row: return None
    return {"id":row[0],"email":row[1],"org":row[2],"role":row[3],"password_hash":row[4],"is_sandbox":bool(row[5]),"created_at":row[6]}

def list_users():
    conn = get_conn()
    cur = conn.execute("SELECT id, email, org, role, is_sandbox, created_at FROM users")
    rows = cur.fetchall()
    conn.close()
    return [{"id":r[0],"email":r[1],"org":r[2],"role":r[3],"is_sandbox":bool(r[4]),"created_at":r[5]} for r in rows]

# --- Room Bookings ledger ---
def add_room_booking(org: str, room: str, date: str, start_min: int, end_min: int, event_id: str):
    bid = str(uuid.uuid4())
    conn = get_conn()
    try:
        conn.execute("INSERT INTO room_bookings (id, org, room, date, start_min, end_min, event_id, created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (bid, org.strip(), room.strip(), date.strip(), start_min, end_min, event_id, _dt.utcnow().isoformat()))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False
    except:
        conn.close()
        return False

def check_room_conflict(room: str, date: str, start_min: int, end_min: int) -> list:
    conn = get_conn()
    cur = conn.execute("SELECT org, room, date, start_min, end_min, event_id FROM room_bookings WHERE room=? AND date=?", (room.strip(), date.strip()))
    rows = cur.fetchall()
    conn.close()
    conflicts=[]
    for org, r, d, s, e, eid in rows:
        if max(s, start_min) < min(e, end_min):
            conflicts.append({"org":org,"room":r,"date":d,"start_min":s,"end_min":e,"event_id":eid})
    return conflicts

def reset_past_bookings(today_str: str) -> int:
    conn = get_conn()
    cur = conn.execute("DELETE FROM room_bookings WHERE date < ?", (today_str,))
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n
