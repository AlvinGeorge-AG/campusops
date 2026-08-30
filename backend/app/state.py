import json
from typing import Optional, List
from .models import Event, EventStatus

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

def _ph() -> str:
    return "?"

def get_conn():
    import sqlite3
    from .config import DB_PATH
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    conn.execute(CREATE_TABLE)
    conn.execute(CREATE_ORG_SETTINGS_TABLE)
    conn.execute(CREATE_USERS_TABLE)
    conn.execute(CREATE_ROOM_BOOKINGS_TABLE)
    for col in [("org","TEXT"),("status","TEXT"),("date","TEXT")]:
        try:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col[0]} {col[1]}")
        except: pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_org ON events(org)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_date ON events(date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_org_date ON events(org, date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_room_bookings_room_date ON room_bookings(room, date)")
    except: pass
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
    org = (event.org or "").strip()
    status = event.status.value if hasattr(event.status, "value") else str(event.status)
    date = event.date or ""
    ph = _ph()
    data_json = event.model_dump_json()
    conn = get_conn()
    try:
        conn.execute(f"INSERT OR REPLACE INTO events (id, data, org, status, date) VALUES ({ph},{ph},{ph},{ph},{ph})", (event.id, data_json, org, status, date))
        conn.commit()
    finally:
        conn.close()
    return event

def get_event(event_id: str) -> Optional[Event]:
    ph = _ph()
    conn = get_conn()
    try:
        cur = conn.execute(f"SELECT data FROM events WHERE id={ph}", (event_id,))
        row = cur.fetchone()
        if not row:
            return None
        raw = row[0]
        return Event.model_validate_json(raw)
    finally:
        conn.close()

def clean_unsent_drafts():
    conn = get_conn()
    try:
        cur = conn.execute("SELECT id, data FROM events WHERE status = 'draft'")
        rows = cur.fetchall()
        for r in rows:
            try:
                d = json.loads(r[1])
                if not d.get("permission_email_sent"):
                    conn.execute("DELETE FROM events WHERE id = ?", (r[0],))
            except:
                conn.execute("DELETE FROM events WHERE id = ?", (r[0],))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

def list_events(org: Optional[str] = None, scope_all: bool = True, include_drafts: bool = False) -> List[Event]:
    ph = _ph()
    conn = get_conn()
    try:
        if org and not scope_all:
            cur = conn.execute(f"SELECT data FROM events WHERE org={ph}", (org.strip(),))
        else:
            cur = conn.execute("SELECT data FROM events")
        rows = cur.fetchall()
        evs = []
        for r in rows:
            raw = r[0]
            try:
                ev = Event.model_validate_json(raw)
                if not include_drafts:
                    if ev.status == EventStatus.DRAFT:
                        continue
                    if not ev.permission_email_sent and ev.status not in (EventStatus.LIVE, EventStatus.CLOSED):
                        continue
                evs.append(ev)
            except: pass
        try:
            evs.sort(key=lambda e: (e.date or "", e.created_at or ""), reverse=True)
        except: pass
        return evs
    finally:
        conn.close()

def get_latest_event(org: Optional[str] = None) -> Optional[Event]:
    if org:
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
    ph = _ph()
    conn = get_conn()
    try:
        cur = conn.execute(f"SELECT data FROM org_settings WHERE org={ph}", (org,))
        row = cur.fetchone()
        if not row:
            return _default_org_settings(org)
        raw = row[0]
        try:
            return _OrgSettings.model_validate_json(raw)
        except:
            return _default_org_settings(org)
    finally:
        conn.close()

def save_org_settings(settings: _OrgSettings) -> _OrgSettings:
    settings.ensure_updated()
    ph = _ph()
    conn = get_conn()
    try:
        conn.execute(f"INSERT OR REPLACE INTO org_settings (org, data) VALUES ({ph},{ph})", (settings.org, settings.model_dump_json()))
        conn.commit()
        try:
            _is_cfg_cache.pop(settings.org.strip().lower(), None)
        except: pass
        return settings
    finally:
        conn.close()

def list_org_settings() -> List[_OrgSettings]:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT data FROM org_settings")
        rows = cur.fetchall()
        out = []
        for r in rows:
            raw = r[0]
            try:
                out.append(_OrgSettings.model_validate_json(raw))
            except:
                pass
        return out
    finally:
        conn.close()

def get_effective_settings(org: str) -> _OrgSettings:
    return get_org_settings(org)

_is_cfg_cache: dict[str, tuple[float, tuple[bool, list[str]]]] = {}
def is_org_configured(org: str) -> tuple[bool, list[str]]:
    import time
    ck = (org or "").strip().lower()
    now = time.time()
    if ck in _is_cfg_cache and now - _is_cfg_cache[ck][0] < 60:
        return _is_cfg_cache[ck][1]
    if not org or not org.strip():
        res = (False, ["institution_name", "institution_place", "faculty_email", "announcement_recipients", "chairperson", "staff_in_charge"])
        _is_cfg_cache[ck] = (now, res)
        return res
    ph = _ph()
    conn = get_conn()
    try:
        cur = conn.execute(f"SELECT data FROM org_settings WHERE org={ph}", (org.strip(),))
        row = cur.fetchone()
        if not row:
            res = (False, ["institution_name", "institution_place", "faculty_email", "announcement_recipients", "chairperson", "staff_in_charge"])
            _is_cfg_cache[ck] = (now, res)
            return res
        raw = row[0]
        try:
            s = _OrgSettings.model_validate_json(raw)
        except:
            return False, ["institution_name", "institution_place", "faculty_email", "announcement_recipients", "chairperson", "staff_in_charge"]
        missing = []
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
        res = (len(missing) == 0), missing
        _is_cfg_cache[ck] = (now, res)
        return res
    finally:
        conn.close()

def is_google_connected(org: str) -> bool:
    if not org or org.strip().lower() == "test_club":
        return True
    try:
        from .config import CENTRAL_DRIVE, GOOGLE_TOKEN_PATH, google_token_path_for_org
        import os
        if CENTRAL_DRIVE:
            if os.path.exists(GOOGLE_TOKEN_PATH) or os.path.exists("backend/token.json") or os.path.exists("./token.json"):
                return True
        path = google_token_path_for_org(org)
        if os.path.exists(path):
            return True
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
    ph = _ph()
    conn = get_conn()
    try:
        conn.execute(f"INSERT INTO users (id, email, org, role, password_hash, is_sandbox, created_at) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})", (uid, email.strip().lower(), org.strip(), role, password_hash, 1 if is_sandbox else 0, _dt.utcnow().isoformat()))
        conn.commit()
        return uid
    finally:
        conn.close()

def get_user_by_email(email: str):
    ph = _ph()
    conn = get_conn()
    try:
        cur = conn.execute(f"SELECT id, email, org, role, password_hash, is_sandbox, created_at FROM users WHERE email={ph}", (email.strip().lower(),))
        row = cur.fetchone()
        if not row:
            return None
        return {"id":row[0],"email":row[1],"org":row[2],"role":row[3],"password_hash":row[4],"is_sandbox":bool(row[5]),"created_at":row[6]}
    finally:
        conn.close()

def get_user_by_id(uid: str):
    ph = _ph()
    conn = get_conn()
    try:
        cur = conn.execute(f"SELECT id, email, org, role, password_hash, is_sandbox, created_at FROM users WHERE id={ph}", (uid,))
        row = cur.fetchone()
        if not row:
            return None
        return {"id":row[0],"email":row[1],"org":row[2],"role":row[3],"password_hash":row[4],"is_sandbox":bool(row[5]),"created_at":row[6]}
    finally:
        conn.close()

def list_users():
    conn = get_conn()
    try:
        cur = conn.execute("SELECT id, email, org, role, is_sandbox, created_at FROM users")
        rows = cur.fetchall()
        out=[]
        for r in rows:
            out.append({"id":r[0],"email":r[1],"org":r[2],"role":r[3],"is_sandbox":bool(r[4]),"created_at":r[5]})
        return out
    finally:
        conn.close()

# --- Room Bookings ledger ---
def add_room_booking(org: str, room: str, date: str, start_min: int, end_min: int, event_id: str):
    bid = str(uuid.uuid4())
    ph = _ph()
    conn = get_conn()
    try:
        conn.execute(f"INSERT INTO room_bookings (id, org, room, date, start_min, end_min, event_id, created_at) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})", (bid, org.strip(), room.strip(), date.strip(), start_min, end_min, event_id, _dt.utcnow().isoformat()))
        conn.commit()
        return True
    except Exception as e:
        try: conn.rollback()
        except: pass
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return False
        return False
    finally:
        conn.close()

def check_room_conflict(room: str, date: str, start_min: int, end_min: int) -> list:
    ph = _ph()
    conn = get_conn()
    try:
        cur = conn.execute(f"SELECT org, room, date, start_min, end_min, event_id FROM room_bookings WHERE room={ph} AND date={ph}", (room.strip(), date.strip()))
        rows = cur.fetchall()
        conflicts=[]
        for r in rows:
            org, rm, d, s, e, eid = r
            s, e = int(s), int(e)
            if max(s, start_min) < min(e, end_min):
                conflicts.append({"org":org,"room":rm,"date":d,"start_min":s,"end_min":e,"event_id":eid})
        return conflicts
    finally:
        conn.close()

def reset_past_bookings(today_str: str) -> int:
    ph = _ph()
    conn = get_conn()
    try:
        cur = conn.execute(f"DELETE FROM room_bookings WHERE date < {ph}", (today_str,))
        n = cur.rowcount if hasattr(cur, 'rowcount') else 0
        conn.commit()
        return n if n and n!=-1 else 0
    finally:
        conn.close()
