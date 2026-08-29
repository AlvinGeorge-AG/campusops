import json
from typing import Optional, List
from .models import Event, EventStatus

# Table DDL for both SQLite and Postgres
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

CREATE_RESPONSES_TABLE = """
CREATE TABLE IF NOT EXISTS event_responses (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    data TEXT NOT NULL,
    respondent_email TEXT,
    created_at TEXT NOT NULL
);
"""

# Postgres-specific DDL when DATABASE_URL is set
CREATE_TABLE_PG = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    org TEXT,
    status TEXT,
    date TEXT,
    last_synced_at TIMESTAMPTZ
);
"""
CREATE_RESPONSES_TABLE_PG = """
CREATE TABLE IF NOT EXISTS event_responses (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    data JSONB NOT NULL,
    respondent_email TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

def _is_pg() -> bool:
    try:
        from .config import DATABASE_URL
        return bool(DATABASE_URL and DATABASE_URL.strip())
    except:
        return False

def _ph() -> str:
    return "%s" if _is_pg() else "?"

def get_conn():
    if _is_pg():
        from .db import get_db as _get_db
        # Return a raw connection that caller must close via context? For compat, return connection object with execute/commit/close
        # We use a context manager wrapper: caller does conn.execute then conn.commit then conn.close
        # So we provide a wrapper that mimics sqlite3 connection
        import contextlib
        # Instead we directly use db.get_db context inside each function; but legacy callers use get_conn()
        # Provide a compat object: open a pg connection synchronously
        from .db import _pg_conn, _get_pg_pool
        pool = _get_pg_pool()
        if pool:
            # getconn without context - we need to handle putconn on close
            class PGPooledWrapper:
                def __init__(self, pool):
                    self._pool = pool
                    self._conn = pool.getconn()
                def execute(self, *a, **kw):
                    return self._conn.execute(*a, **kw)
                def cursor(self, *a, **kw):
                    return self._conn.cursor(*a, **kw)
                def commit(self):
                    try:
                        if not getattr(self._conn, "autocommit", False):
                            return self._conn.commit()
                    except Exception:
                        pass
                def rollback(self):
                    try:
                        if not getattr(self._conn, "autocommit", False):
                            return self._conn.rollback()
                    except Exception:
                        pass
                def close(self):
                    try:
                        if self._pool and self._conn:
                            self._pool.putconn(self._conn)
                    except Exception:
                        pass
                def __enter__(self): return self
                def __exit__(self, *e): self.close()
            return PGPooledWrapper(pool)
        else:
            class PGDirectWrapper:
                def __init__(self, conn):
                    self._conn = conn
                def execute(self, *a, **kw):
                    return self._conn.execute(*a, **kw)
                def cursor(self, *a, **kw):
                    return self._conn.cursor(*a, **kw)
                def commit(self):
                    try:
                        if not getattr(self._conn, "autocommit", False):
                            return self._conn.commit()
                    except Exception:
                        pass
                def rollback(self):
                    try:
                        if not getattr(self._conn, "autocommit", False):
                            return self._conn.rollback()
                    except Exception:
                        pass
                def close(self):
                    try:
                        self._conn.close()
                    except Exception:
                        pass
                def __enter__(self): return self
                def __exit__(self, *e): self.close()
            return PGDirectWrapper(_pg_conn())
    # SQLite fallback - original logic
    import sqlite3
    from .config import DB_PATH
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    conn.execute(CREATE_TABLE)
    conn.execute(CREATE_ORG_SETTINGS_TABLE)
    conn.execute(CREATE_USERS_TABLE)
    conn.execute(CREATE_ROOM_BOOKINGS_TABLE)
    conn.execute(CREATE_RESPONSES_TABLE)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_responses_event ON event_responses(event_id)")
    except: pass
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

# Postgres DDLs
CREATE_ORG_SETTINGS_TABLE_PG = """
CREATE TABLE IF NOT EXISTS org_settings (
    org TEXT PRIMARY KEY,
    data JSONB NOT NULL
);
"""

CREATE_USERS_TABLE_PG = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    org TEXT NOT NULL,
    role TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_sandbox INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

CREATE_ROOM_BOOKINGS_TABLE_PG = """
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

_pg_schema_done = False
def _ensure_pg_schema(conn):
    global _pg_schema_done
    if not _is_pg() or _pg_schema_done:
        return
    # autocommit=True so each DDL is atomic, ignore errors individually
    for stmt in [
        CREATE_TABLE_PG,
        CREATE_ORG_SETTINGS_TABLE_PG,
        CREATE_USERS_TABLE_PG,
        CREATE_ROOM_BOOKINGS_TABLE_PG,
        CREATE_RESPONSES_TABLE_PG,
        "CREATE INDEX IF NOT EXISTS idx_events_org ON events(org)",
        "CREATE INDEX IF NOT EXISTS idx_events_date ON events(date)",
        "CREATE INDEX IF NOT EXISTS idx_room_bookings_room_date ON room_bookings(room, date)",
        "CREATE INDEX IF NOT EXISTS idx_responses_event ON event_responses(event_id)",
    ]:
        try:
            conn.execute(stmt)
        except Exception:
            pass
    for stmt in [
        "ALTER TABLE org_settings ALTER COLUMN data TYPE JSONB USING data::jsonb",
        "ALTER TABLE events ALTER COLUMN data TYPE JSONB USING data::jsonb",
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ",
    ]:
        try:
            conn.execute(stmt)
        except Exception:
            pass
    _pg_schema_done = True

def _pg_ensure(conn):
    if _is_pg():
        _ensure_pg_schema(conn)

def save_event(event: Event):
    event.ensure_id()
    org = (event.org or "").strip()
    status = event.status.value if hasattr(event.status, "value") else str(event.status)
    date = event.date or ""
    ph = _ph()
    data_json = event.model_dump_json()
    conn = get_conn()
    _pg_ensure(conn)
    try:
        if _is_pg():
            # Postgres UPSERT
            conn.execute(f"INSERT INTO events (id, data, org, status, date) VALUES ({ph},{ph},{ph},{ph},{ph}) ON CONFLICT (id) DO UPDATE SET data=EXCLUDED.data, org=EXCLUDED.org, status=EXCLUDED.status, date=EXCLUDED.date", (event.id, data_json, org, status, date))
        else:
            conn.execute(f"INSERT OR REPLACE INTO events (id, data, org, status, date) VALUES ({ph},{ph},{ph},{ph},{ph})", (event.id, data_json, org, status, date))
        conn.commit()
    finally:
        conn.close()
    return event

def get_event(event_id: str) -> Optional[Event]:
    ph = _ph()
    conn = get_conn()
    _pg_ensure(conn)
    try:
        cur = conn.execute(f"SELECT data FROM events WHERE id={ph}", (event_id,))
        row = cur.fetchone()
        if not row:
            return None
        raw = row[0] if not isinstance(row, dict) else row["data"]
        if isinstance(raw, dict):
            raw = json.dumps(raw)
        return Event.model_validate_json(raw)
    finally:
        conn.close()

def clean_unsent_drafts():
    conn = get_conn()
    _pg_ensure(conn)
    try:
        if _is_pg():
            conn.execute("DELETE FROM events WHERE status = 'draft' OR (data->>'permission_email_sent' IS NULL OR data->>'permission_email_sent' = 'false') AND status != 'live' AND status != 'closed'")
        else:
            cur = conn.execute("SELECT id, data FROM events WHERE status = 'draft'")
            rows = cur.fetchall()
            for r in rows:
                try:
                    d = json.loads(r[1] if not isinstance(r[1], dict) else json.dumps(r[1]))
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
    _pg_ensure(conn)
    try:
        if org and not scope_all:
            cur = conn.execute(f"SELECT data FROM events WHERE org={ph}", (org.strip(),))
        else:
            cur = conn.execute("SELECT data FROM events")
        rows = cur.fetchall()
        evs = []
        for r in rows:
            raw = r[0] if not isinstance(r, dict) else r["data"]
            if isinstance(raw, dict):
                raw = json.dumps(raw)
            try:
                ev = Event.model_validate_json(raw)
                # Only include events with successful permission request sent (or live/closed)
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
    _pg_ensure(conn)
    try:
        cur = conn.execute(f"SELECT data FROM org_settings WHERE org={ph}", (org,))
        row = cur.fetchone()
        if not row:
            return _default_org_settings(org)
        raw = row[0] if not isinstance(row, dict) else row["data"]
        if isinstance(raw, dict):
            raw = json.dumps(raw)
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
    _pg_ensure(conn)
    try:
        if _is_pg():
            conn.execute(f"INSERT INTO org_settings (org, data) VALUES ({ph},{ph}) ON CONFLICT (org) DO UPDATE SET data=EXCLUDED.data", (settings.org, settings.model_dump_json()))
        else:
            conn.execute(f"INSERT OR REPLACE INTO org_settings (org, data) VALUES ({ph},{ph})", (settings.org, settings.model_dump_json()))
        conn.commit()
        # invalidate cache
        try:
            _is_cfg_cache.pop(settings.org.strip().lower(), None)
        except: pass
        return settings
    finally:
        conn.close()

def list_org_settings() -> List[_OrgSettings]:
    conn = get_conn()
    _pg_ensure(conn)
    try:
        cur = conn.execute("SELECT data FROM org_settings")
        rows = cur.fetchall()
        out = []
        for r in rows:
            raw = r[0] if not isinstance(r, dict) else r["data"]
            if isinstance(raw, dict):
                raw = json.dumps(raw)
            try:
                out.append(_OrgSettings.model_validate_json(raw))
            except:
                pass
        return out
    finally:
        conn.close()

def get_effective_settings(org: str) -> _OrgSettings:
    return get_org_settings(org)

# simple in-memory cache for is_org_configured to avoid Neon latency on every chat
_is_cfg_cache: dict[str, tuple[float, tuple[bool, list[str]]]] = {}
def is_org_configured(org: str) -> tuple[bool, list[str]]:
    # TEST_CLUB no longer bypasses validation — empty faculty/announcement emails must be warned and blocked for send
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
    _pg_ensure(conn)
    try:
        cur = conn.execute(f"SELECT data FROM org_settings WHERE org={ph}", (org.strip(),))
        row = cur.fetchone()
        if not row:
            res = (False, ["institution_name", "institution_place", "faculty_email", "announcement_recipients", "chairperson", "staff_in_charge"])
            _is_cfg_cache[ck] = (now, res)
            return res
        raw = row[0] if not isinstance(row, dict) else row["data"]
        if isinstance(raw, dict):
            raw = json.dumps(raw)
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
    _pg_ensure(conn)
    try:
        conn.execute(f"INSERT INTO users (id, email, org, role, password_hash, is_sandbox, created_at) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})", (uid, email.strip().lower(), org.strip(), role, password_hash, 1 if is_sandbox else 0, _dt.utcnow().isoformat()))
        conn.commit()
        return uid
    finally:
        conn.close()

def get_user_by_email(email: str):
    ph = _ph()
    conn = get_conn()
    _pg_ensure(conn)
    try:
        cur = conn.execute(f"SELECT id, email, org, role, password_hash, is_sandbox, created_at FROM users WHERE email={ph}", (email.strip().lower(),))
        row = cur.fetchone()
        if not row:
            return None
        if isinstance(row, dict):
            return {"id":row["id"],"email":row["email"],"org":row["org"],"role":row["role"],"password_hash":row["password_hash"],"is_sandbox":bool(row["is_sandbox"]),"created_at":row["created_at"]}
        return {"id":row[0],"email":row[1],"org":row[2],"role":row[3],"password_hash":row[4],"is_sandbox":bool(row[5]),"created_at":row[6]}
    finally:
        conn.close()

def get_user_by_id(uid: str):
    ph = _ph()
    conn = get_conn()
    _pg_ensure(conn)
    try:
        cur = conn.execute(f"SELECT id, email, org, role, password_hash, is_sandbox, created_at FROM users WHERE id={ph}", (uid,))
        row = cur.fetchone()
        if not row:
            return None
        if isinstance(row, dict):
            return {"id":row["id"],"email":row["email"],"org":row["org"],"role":row["role"],"password_hash":row["password_hash"],"is_sandbox":bool(row["is_sandbox"]),"created_at":row["created_at"]}
        return {"id":row[0],"email":row[1],"org":row[2],"role":row[3],"password_hash":row[4],"is_sandbox":bool(row[5]),"created_at":row[6]}
    finally:
        conn.close()

def list_users():
    conn = get_conn()
    _pg_ensure(conn)
    try:
        cur = conn.execute("SELECT id, email, org, role, is_sandbox, created_at FROM users")
        rows = cur.fetchall()
        out=[]
        for r in rows:
            if isinstance(r, dict):
                out.append({"id":r["id"],"email":r["email"],"org":r["org"],"role":r["role"],"is_sandbox":bool(r["is_sandbox"]),"created_at":r["created_at"]})
            else:
                out.append({"id":r[0],"email":r[1],"org":r[2],"role":r[3],"is_sandbox":bool(r[4]),"created_at":r[5]})
        return out
    finally:
        conn.close()

# --- Room Bookings ledger ---
def add_room_booking(org: str, room: str, date: str, start_min: int, end_min: int, event_id: str):
    bid = str(uuid.uuid4())
    ph = _ph()
    conn = get_conn()
    _pg_ensure(conn)
    try:
        conn.execute(f"INSERT INTO room_bookings (id, org, room, date, start_min, end_min, event_id, created_at) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})", (bid, org.strip(), room.strip(), date.strip(), start_min, end_min, event_id, _dt.utcnow().isoformat()))
        conn.commit()
        return True
    except Exception as e:
        try: conn.rollback()
        except: pass
        # check duplicate
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return False
        return False
    finally:
        conn.close()

def check_room_conflict(room: str, date: str, start_min: int, end_min: int) -> list:
    ph = _ph()
    conn = get_conn()
    _pg_ensure(conn)
    try:
        cur = conn.execute(f"SELECT org, room, date, start_min, end_min, event_id FROM room_bookings WHERE room={ph} AND date={ph}", (room.strip(), date.strip()))
        rows = cur.fetchall()
        conflicts=[]
        for r in rows:
            if isinstance(r, dict):
                org, rm, d, s, e, eid = r["org"], r["room"], r["date"], int(r["start_min"]), int(r["end_min"]), r["event_id"]
            else:
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
    _pg_ensure(conn)
    try:
        cur = conn.execute(f"DELETE FROM room_bookings WHERE date < {ph}", (today_str,))
        n = cur.rowcount if hasattr(cur, 'rowcount') else 0
        conn.commit()
        return n if n and n!=-1 else 0
    finally:
        conn.close()

# --- Event Responses (native DB, replaces Sheets) ---
def add_response(event_id: str, data: dict, respondent_email: str = "") -> str:
    rid = str(uuid.uuid4())
    ph = _ph()
    conn = get_conn()
    _pg_ensure(conn)
    try:
        j = json.dumps(data)
        if _is_pg():
            conn.execute(f"INSERT INTO event_responses (id, event_id, data, respondent_email, created_at) VALUES ({ph},{ph},{ph},{ph}, now())", (rid, event_id, j, respondent_email))
        else:
            conn.execute(f"INSERT INTO event_responses (id, event_id, data, respondent_email, created_at) VALUES ({ph},{ph},{ph},{ph},{ph})", (rid, event_id, j, respondent_email, _dt.utcnow().isoformat()))
        conn.commit()
        return rid
    finally:
        conn.close()

def list_responses(event_id: str, limit: int = 100, offset: int = 0):
    ph = _ph()
    conn = get_conn()
    _pg_ensure(conn)
    try:
        cur = conn.execute(f"SELECT id, data, respondent_email, created_at FROM event_responses WHERE event_id={ph} ORDER BY created_at DESC LIMIT {ph} OFFSET {ph}", (event_id, limit, offset))
        rows = cur.fetchall()
        out=[]
        for r in rows:
            if isinstance(r, dict):
                d = r["data"]
                if isinstance(d, dict): j = d
                else:
                    try: j=json.loads(d)
                    except: j={"raw":d}
                out.append({"id":r["id"],"data":j,"respondent_email":r["respondent_email"],"created_at":str(r["created_at"])})
            else:
                rid, d, email, cat = r
                try: j=json.loads(d) if isinstance(d,str) else d
                except: j={"raw":d}
                out.append({"id":rid,"data":j,"respondent_email":email,"created_at":cat})
        return out
    finally:
        conn.close()

def count_responses(event_id: str) -> int:
    ph = _ph()
    conn = get_conn()
    _pg_ensure(conn)
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM event_responses WHERE event_id={ph}", (event_id,))
        row = cur.fetchone()
        if not row: return 0
        v = row[0] if not isinstance(row, dict) else list(row.values())[0]
        return int(v)
    finally:
        conn.close()

def get_response_headers(event_id: str):
    rows = list_responses(event_id, limit=1)
    if not rows:
        return []
    return list(rows[0]["data"].keys()) if isinstance(rows[0]["data"], dict) else []
