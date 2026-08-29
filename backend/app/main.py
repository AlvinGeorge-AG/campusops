from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from pydantic import BaseModel, field_validator
from typing import Optional, List
import os
from dotenv import load_dotenv
load_dotenv()

from .agent import get_agent
from .state import save_event, get_event, list_events, get_latest_event
from .models import Event, EventStatus
from .config import (
    MOCK_MODE, POLLER_ENABLED, FACULTY_EMAIL, 
    DEFAULT_CHAIRPERSON, DEFAULT_STAFF, INSTITUTION_NAME, INSTITUTION_PLACE,
    FRONTEND_ORIGIN, SANDBOX_ORG
)
from .state import get_org_settings, save_org_settings, list_org_settings
from .models import OrgSettings, FieldModel
from .auth import get_current_user, require_role, create_token, verify_password, hash_password
from .state import get_user_by_email, create_user, list_users
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import asyncio
import logging
import re
import json as _json_global
import threading

_agent_invocation_lock = threading.Lock()

class AgentBusyError(RuntimeError):
    pass

def _invoke_agent(agent, prompt):
    if not _agent_invocation_lock.acquire(timeout=60):
        raise AgentBusyError("Another agent request is still processing. Please try again in a moment.")
    try:
        return agent(prompt)
    finally:
        _agent_invocation_lock.release()

def _fields_to_json(fields):
    if not fields: return None
    try:
        lst = [f.model_dump() if hasattr(f, "model_dump") else f for f in fields]
        return _json_global.dumps(lst)
    except:
        return _json_global.dumps(fields)

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Suppress noisy googleapiclient discovery cache warnings
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.WARNING)

def _extract_title_from_message(msg: str) -> str:
    """Heuristic: 'FOSS MEC wants to conduct a Java workshop for 50...' -> 'Java Workshop'"""
    if not msg:
        return ""
    # Look for patterns like "a X workshop", "a X seminar", "a X talk"
    m = re.search(r"(?:a|an)\s+([A-Za-z0-9 ]+?)\s+(workshop|seminar|talk|session|event|competition|hackathon)", msg, re.IGNORECASE)
    if m:
        title = f"{m.group(1).strip().title()} {m.group(2).title()}"
        return title
    # Fallback: take first 3-4 words after 'conduct'
    m2 = re.search(r"conduct\s+(?:a\s+)?(.+?)\s+for\s+\d+", msg, re.IGNORECASE)
    if m2:
        cand = m2.group(1).strip()
        # trim to 4 words max
        cand = " ".join(cand.split()[:4])
        return cand.title()
    return ""

def _extract_expected_headcount(msg: str) -> int:
    if not msg:
        return 30
    patterns = [
        r"for\s+(\d+)\s+students",
        r"for\s+(\d+)\s+people",
        r"(\d+)\s+students",
        r"(\d+)\s+attendees",
        r"headcount\s*(?:is|:)?\s*(\d+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, msg, re.IGNORECASE)
        if m:
            try:
                return max(1, int(m.group(1)))
            except Exception:
                pass
    return 30

def _build_announcement_preview(ev: Event) -> str:
    time_line = f"Time: {ev.start_time} - {ev.end_time}" if ev.start_time and ev.end_time else "Time: TBD"
    speaker_line = f"Speaker: {ev.speaker}" if ev.speaker else ""
    return f"""ANNOUNCEMENT PREVIEW (to be sent to students after approval):
---
Hello,

We are excited to announce: {ev.title} by {ev.org}

Date: {ev.date}
Venue: {ev.room}
{time_line}
Expected: {ev.expected_headcount} students
{speaker_line}
Registration will open after approval - form link to be attached.

Seats are limited. Please register soon.
- CampusOps
---"""

def _chat_response_for_event(ev: Event, response_text: str) -> "ChatResponse":
    email_preview = ev.email_draft or ev.permission_letter or ""
    if not email_preview and ev.title:
        _s_prev = get_org_settings(ev.org or "")
        _inst_n = _s_prev.institution_name or INSTITUTION_NAME
        _inst_p = _s_prev.institution_place or INSTITUTION_PLACE
        _chair = ev.chairperson or _s_prev.chairperson or DEFAULT_CHAIRPERSON
        email_preview = f"To,\nThe Principal,\n{_inst_n},\n{_inst_p}.\n\nSubject: Request for permission to host \"{ev.title}\"\n\nRespected Sir/Madam,\n\nI am writing to request permission to conduct \"{ev.title}\", organized by {ev.org}, on {ev.date} from {ev.start_time or '3:30 PM'} to {ev.end_time or '4:30 PM'} at {ev.room}.\n\n{ev.purpose or ''}\n\nThank you.\n\nWith regards,\nChairperson {ev.org}\n{_chair}"
    return ChatResponse(
        response=response_text,
        event_id=ev.id,
        status=ev.status,
        permission_letter=ev.permission_letter or email_preview,
        onfoot_letter=ev.onfoot_letter,
        announcement_draft=ev.announcement_draft,
        email_draft=email_preview,
    )

def _create_event_deterministically(req: "ChatRequest", user: dict, event_id: str) -> "ChatResponse":
    from app.tools.room import check_room_availability, book_room_slot
    from app.tools.letters import generate_permission_letter, generate_onfoot_letter
    import json as _js

    ev = get_event(event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event placeholder not found")

    headcount = _extract_expected_headcount(req.message)
    # Wrap room check with timeout to prevent hanging on Sheets/Neon (Render 30s proxy)
    try:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(check_room_availability, req.date or "", headcount, req.start_time or "", req.end_time or "")
            raw_av = fut.result(timeout=5)
        availability = _js.loads(raw_av)
    except Exception as e:
        logger.warning(f"Room check timeout/fail for {event_id}: {e}, using mock fallback")
        availability = {"available": True, "room": "SDPK", "capacity": 60, "source": "mock_fallback_timeout"}
    if availability.get("available") is False or not availability.get("room"):
        try:
            from app.state import get_conn as _gc2
            from app.config import DATABASE_URL as _DBURL2
            if _DBURL2 and _DBURL2.strip():
                conn = _gc2()
                try:
                    conn.execute("DELETE FROM events WHERE id=%s", (event_id,))
                    conn.commit()
                finally:
                    conn.close()
            else:
                import sqlite3
                from app.config import DB_PATH
                conn = sqlite3.connect(DB_PATH)
                conn.execute("DELETE FROM events WHERE id=?", (event_id,))
                conn.commit()
                conn.close()
        except Exception:
            pass
        raise HTTPException(status_code=409, detail=availability)

    # Booking with timeout to prevent hanging on Sheets
    try:
        import concurrent.futures as _cf2
        with _cf2.ThreadPoolExecutor(max_workers=1) as ex2:
            fut2 = ex2.submit(book_room_slot, availability["room"], req.date or "", req.start_time or "", req.end_time or "", event_id)
            raw_book = fut2.result(timeout=5)
        booking = _js.loads(raw_book)
    except Exception as e:
        logger.warning(f"Room booking timeout/fail for {event_id}: {e}, proceeding with mock ledger")
        booking = {"booked": True, "room": availability["room"], "source": "mock_ledger_timeout"}
    if booking.get("booked") is False and booking.get("reason") == "conflict":
        raise HTTPException(status_code=409, detail=booking)
    if booking.get("booked") is False:
        logger.warning("Room sheet booking warning for event %s: %s", event_id, booking)

    settings = get_org_settings(user["org"])
    ev.org = user["org"]
    ev.title = _extract_title_from_message(req.message) or ev.title or "Campus Event"
    ev.date = req.date or ev.date
    ev.start_time = req.start_time or ev.start_time
    ev.end_time = req.end_time or ev.end_time
    ev.expected_headcount = headcount
    ev.room = availability.get("room")
    ev.room_capacity = availability.get("capacity")
    ev.speaker = req.speaker or ev.speaker
    ev.purpose = req.purpose or req.description or ev.purpose
    ev.chairperson = req.chairperson or ev.chairperson or settings.chairperson
    ev.staff_in_charge = req.staff_in_charge or ev.staff_in_charge or settings.staff_in_charge
    ev.need_onfoot = bool(req.need_onfoot)
    if req.fields:
        ev.form_fields_json = _fields_to_json(req.fields)
    ev.status = EventStatus.PENDING_APPROVAL
    save_event(ev)

    permission_letter = generate_permission_letter(
        ev.org,
        ev.title,
        ev.date,
        ev.start_time or "3:30 PM",
        ev.end_time or "4:30 PM",
        ev.room or "",
        ev.speaker or "",
        ev.purpose or "",
        ev.chairperson or "",
        ev.staff_in_charge or "",
    )
    onfoot_letter = None
    if ev.need_onfoot:
        onfoot_letter = generate_onfoot_letter(
            ev.org,
            ev.title,
            ev.date,
            ev.start_time or "3:30 PM",
            ev.end_time or "4:30 PM",
            ev.room or "",
            ev.speaker or "",
            ev.purpose or "",
            ev.chairperson or "",
            ev.staff_in_charge or "",
        )

    ev = get_event(event_id) or ev
    ev.permission_letter = permission_letter
    if onfoot_letter:
        ev.onfoot_letter = onfoot_letter
    ev.announcement_draft = _build_announcement_preview(ev)
    save_event(ev)

    response_text = (
        f"Room reserved: {ev.room} ({ev.room_capacity or 'capacity available'}) for "
        f"{ev.date} {ev.start_time}-{ev.end_time}.\n\n"
        "Here is the draft email for principal - edit manually or send it from the next step."
    )
    return _chat_response_for_event(ev, response_text)

app = FastAPI(title="CampusOps Backend", version="0.1.0")

# Global exception handler
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )

# --- Daily reset: keep future, remove past bookings from DB + Sheet ---
_reset_task = None
async def _reset_loop():
    await asyncio.sleep(30)
    while True:
        try:
            from datetime import date as _d
            today = _d.today().isoformat()
            from .state import reset_past_bookings
            n = reset_past_bookings(today)
            if n: logger.info(f"Daily reset: removed {n} past room_bookings before {today}")
            # Also clean Sheet via script logic (reuse) — new 2-sheet format: Bookings ledger
            try:
                import os, subprocess, pathlib
                sheet_id = os.getenv("ROOM_SHEET_ID") or os.getenv("MOCK_ROOM_SHEET_ID")
                if sheet_id and not MOCK_MODE:
                    from app.google.auth import get_credentials
                    from googleapiclient.discovery import build
                    creds = get_credentials()
                    if creds:
                        svc = build("sheets","v4", credentials=creds)
                        # Try new Bookings sheet first
                        rows = None
                        sheet_range_used = None
                        clear_range = None
                        update_range = None
                        date_idx = 1  # Bookings: Room(0), Date(1), Start(2), End(3)
                        try:
                            rows = svc.spreadsheets().values().get(spreadsheetId=sheet_id, range="Bookings!A2:F").execute().get("values",[])
                            sheet_range_used = "Bookings"
                            clear_range = "Bookings!A2:F"
                            update_range = "Bookings!A2"
                        except:
                            rows = None
                        if rows is None:
                            # fallback old single-sheet
                            try:
                                rows = svc.spreadsheets().values().get(spreadsheetId=sheet_id, range="Rooms!A2:H").execute().get("values",[])
                                sheet_range_used = "Rooms"
                                clear_range = "Rooms!A2:H"
                                update_range = "Rooms!A2"
                                date_idx = 2
                            except:
                                rows = []
                        kept=[]; removed=0
                        for r in rows or []:
                            if len(r) <= date_idx or not r[date_idx].strip():
                                kept.append(r); continue
                            if r[date_idx].strip() >= today:
                                kept.append(r)
                            else: removed+=1
                        if removed and clear_range:
                            svc.spreadsheets().values().clear(spreadsheetId=sheet_id, range=clear_range).execute()
                            if kept: svc.spreadsheets().values().update(spreadsheetId=sheet_id, range=update_range, valueInputOption="RAW", body={"values": kept}).execute()
                            logger.info(f"Sheet reset ({sheet_range_used}): removed {removed} past rows, kept {len(kept)}")
            except Exception as se: logger.warning(f"Sheet reset warn: {se}")
        except Exception as e: logger.warning(f"Reset loop error: {e}")
        await asyncio.sleep(24*3600)  # 24h

# --- Deprecated poller removed: on-demand + cache (60s TTL) now handles registrations ---
_poller_task = None

@app.on_event("startup")
async def start_poller():
    global _reset_task
    # Poller disabled: use on-demand GET /events/{id}/registrations with 60s cache
    _reset_task = asyncio.create_task(_reset_loop())
    logger.info("Daily reset task enabled (24h, keeps future) - poller disabled (on-demand)")

@app.on_event("shutdown")
async def stop_poller():
    global _reset_task
    if _reset_task:
        _reset_task.cancel()

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"error": "Rate limited", "detail": str(exc.detail)})

# Ensure all standard origins + any custom env origins are permitted
_default_origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "https://campusops-ft.vercel.app",
    "https://campusops.onrender.com",
]
_env_origins = [o.strip() for o in (os.getenv("FRONTEND_ORIGIN") or os.getenv("FRONTEND_URL") or FRONTEND_ORIGIN or "").split(",") if o.strip()]
_allowed_origins = list(dict.fromkeys(_default_origins + _env_origins)) if FRONTEND_ORIGIN != "*" else ["*"]
_vercel_regex = r"https://.*\.vercel\.app" if _allowed_origins != ["*"] else None
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins if _allowed_origins != ["*"] else ["*"],
    allow_origin_regex=_vercel_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    event_id: Optional[str] = None
    fields: Optional[List[FieldModel]] = None
    description: Optional[str] = None
    # Heart of 1-chat: collect all for high-quality letters upfront
    date: Optional[str] = None  # YYYY-MM-DD explicit picker (takes precedence over NLP)
    start_time: Optional[str] = None  # e.g. 3:30 PM or 15:30
    end_time: Optional[str] = None  # e.g. 4:30 PM or 16:30
    speaker: Optional[str] = None
    purpose: Optional[str] = None
    chairperson: Optional[str] = None
    staff_in_charge: Optional[str] = None
    need_onfoot: Optional[bool] = None

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        import re as _re, datetime as _dt
        v = v.strip()
        # Accept YYYY-MM-DD
        if _re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            try:
                _dt.datetime.strptime(v, "%Y-%m-%d")
                return v
            except:
                raise ValueError("invalid date YYYY-MM-DD")
        # Accept DD/MM/YYYY
        if _re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", v):
            try:
                d = _dt.datetime.strptime(v, "%d/%m/%Y")
                return d.strftime("%Y-%m-%d")
            except:
                pass
        # Accept DD-MM-YYYY
        if _re.match(r"^\d{1,2}-\d{1,2}-\d{4}$", v):
            try:
                d = _dt.datetime.strptime(v, "%d-%m-%Y")
                return d.strftime("%Y-%m-%d")
            except:
                pass
        # Accept YYYY/MM/DD
        if _re.match(r"^\d{4}/\d{1,2}/\d{1,2}$", v):
            try:
                d = _dt.datetime.strptime(v, "%Y/%m/%d")
                return d.strftime("%Y-%m-%d")
            except:
                pass
        raise ValueError("date must be YYYY-MM-DD (e.g. 2026-09-01 or 01/09/2026)")

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        v = v.strip()
        # Accept 3:30 PM, 3:30PM, 15:30, 15:30:00
        import re as _re
        if _re.match(r"^\d{1,2}:\d{2}\s*(AM|PM|am|pm)$", v): return v
        if _re.match(r"^\d{1,2}:\d{2}$", v): return v
        if _re.match(r"^\d{1,2}:\d{2}:\d{2}$", v): return v
        raise ValueError("start_time/end_time must be like '3:30 PM' or '15:30'")

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("message must not be empty")
        return v.strip()

class ChatResponse(BaseModel):
    response: str
    event_id: Optional[str] = None
    status: Optional[str] = None
    permission_letter: Optional[str] = None
    onfoot_letter: Optional[str] = None
    announcement_draft: Optional[str] = None
    email_draft: Optional[str] = None

class SendEmailRequest(BaseModel):
    edited_email: Optional[str] = None  # if club manually edited the email text
    regenerate_instruction: Optional[str] = None  # natural language to LLM to regenerate, e.g. "make more formal"

class ApproveRequest(BaseModel):
    approved: bool

class LoginRequest(BaseModel):
    email: str
    password: str
class LoginResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

@app.post("/auth/login")
@limiter.limit("10/minute")
def login(req: LoginRequest, request: Request, response: Response):
    user = get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    token = create_token(user)
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax", max_age=3600, path="/")
    return {"access_token": token, "token_type": "bearer", "user": {"id": user["id"], "email": user["email"], "org": user["org"], "role": user["role"], "is_sandbox": user["is_sandbox"]}}

@app.post("/auth/sandbox-login")
@limiter.limit("30/minute")
def sandbox_login(request: Request, response: Response):
    # Open sandbox - no password, issues TEST_CLUB token
    from .state import get_user_by_email as _g
    u = _g("testclub@mec.ac.in")
    if not u:
        raise HTTPException(500, "Sandbox user not seeded")
    token = create_token(u)
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax", max_age=3600, path="/")
    return {"access_token": token, "token_type": "bearer", "user": u}

@app.get("/auth/me")
def me(user=Depends(get_current_user)):
    # hide hash
    return {"id": user["id"], "email": user["email"], "org": user["org"], "role": user["role"], "is_sandbox": user.get("is_sandbox", False)}

@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}

# --- Per-club Google Drive OAuth (browser flow) ---
_oauth_states: dict[str, str] = {}  # state -> org

@app.get("/auth/google/status")
def google_status(org: str, request: Request, user=Depends(get_current_user)):
    from .auth import require_org_match
    require_org_match(org, user)
    from .state import is_google_connected, is_org_configured
    connected = is_google_connected(org)
    configured, missing = is_org_configured(org)
    return {"org": org, "connected": connected, "configured": configured, "missing_fields": missing, "token_file": f"token_{org.lower().replace(' ','_')}.json"}

@app.post("/auth/google/disconnect")
def google_disconnect(org: str, request: Request, user=Depends(get_current_user)):
    from .auth import require_org_match
    require_org_match(org, user)
    if org.strip().lower() == "test_club":
        raise HTTPException(400, "TEST_CLUB doesn't need Drive")
    import os
    from .config import google_token_path_for_org
    path = google_token_path_for_org(org)
    try:
        if os.path.exists(path):
            os.remove(path)
            return {"ok": True, "removed": path}
        return {"ok": False, "error": "Not connected"}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/auth/google/init")
def google_init(org: str, user=Depends(get_current_user)):
    # Legacy: still returns manual instruction, but new flow is /auth/google/url
    from .auth import require_org_match
    require_org_match(org, user)
    return {"message": f"Run: python scripts/auth_google.py --org \"{org}\" on server with GOOGLE_CREDENTIALS_PATH set. This will create token_{org.lower().replace(' ','_')}.json in backend/ with drive.file/forms.body scopes. Or use browser flow: GET /auth/google/url?org={org}", "org": org, "token_file": f"token_{org.lower().replace(' ','_')}.json"}

@app.get("/auth/google/url")
def google_auth_url(org: str, request: Request, user=Depends(get_current_user)):
    from .auth import require_org_match
    require_org_match(org, user)
    if org.strip().lower() == "test_club":
        return {"url": None, "message": "TEST_CLUB sandbox doesn't need Google Drive"}
    import os, secrets
    from .config import GOOGLE_CREDENTIALS_PATH, SCOPES, google_token_path_for_org
    # Check already connected
    if os.path.exists(google_token_path_for_org(org)):
        return {"url": None, "connected": True, "message": "Already connected"}
    # Try to build Flow with web redirect
    try:
        from google_auth_oauthlib.flow import Flow
        # Determine redirect_uri: must be whitelisted in Google Console
        # Use request base + callback
        redirect_uri = str(request.base_url).rstrip("/") + "/auth/google/callback"
        # Allow override via env
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", redirect_uri)
        flow = Flow.from_client_secrets_file(GOOGLE_CREDENTIALS_PATH, scopes=SCOPES, redirect_uri=redirect_uri)
        state = secrets.token_urlsafe(16)
        _oauth_states[state] = org
        auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent", state=state)
        return {"url": auth_url, "state": state, "redirect_uri": redirect_uri}
    except Exception as e:
        # Fallback: return manual instruction with firebase alternative note
        return {"url": None, "error": str(e), "fallback": f"Ask admin to run: python scripts/auth_google.py --org \"{org}\"", "note": "Or configure GOOGLE_REDIRECT_URI and whitelist it in Google Cloud Console → OAuth client → Authorized redirect URIs"}

@app.get("/auth/google/callback")
def google_callback(request: Request, state: str = "", code: str = "", error: str = ""):
    # No auth required — Google redirects here
    if error:
        raise HTTPException(400, f"Google auth error: {error}")
    org = _oauth_states.get(state)
    if not org:
        # Try to parse state anyway
        raise HTTPException(400, "Invalid or expired state. Please retry from Settings → Connect Drive.")
    try:
        import os
        from google_auth_oauthlib.flow import Flow
        from .config import GOOGLE_CREDENTIALS_PATH, SCOPES, google_token_path_for_org
        redirect_uri = str(request.base_url).rstrip("/") + "/auth/google/callback"
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", redirect_uri)
        flow = Flow.from_client_secrets_file(GOOGLE_CREDENTIALS_PATH, scopes=SCOPES, redirect_uri=redirect_uri)
        flow.fetch_token(code=code)
        creds = flow.credentials
        token_path = google_token_path_for_org(org)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        # Cleanup state
        _oauth_states.pop(state, None)
        # Redirect to frontend settings with success
        from fastapi.responses import RedirectResponse
        frontend = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
        return RedirectResponse(url=f"{frontend}/settings?drive=connected&org={org}", status_code=302)
    except Exception as e:
        raise HTTPException(500, f"Failed to save token: {e}")

@app.get("/")
def health():
    return {"status": "ok", "service": "CampusOps Backend", "mock_mode": MOCK_MODE, "sandbox_org": SANDBOX_ORG}

@app.get("/rooms/availability")
def rooms_availability(date: str, capacity: int = 0, start_time: str = "", end_time: str = "", request: Request = None, user=Depends(get_current_user)):
    from app.tools.room import check_room_availability
    import json as _j
    raw = check_room_availability(date, capacity, start_time, end_time)
    data = _j.loads(raw)
    if data.get("available") is False:
        raise HTTPException(status_code=409, detail=data)
    return data

@app.post("/rooms/reset")
def rooms_reset(request: Request, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Only admin can reset rooms")
    from datetime import date as _d
    from app.state import reset_past_bookings
    today = _d.today().isoformat()
    n = reset_past_bookings(today)
    # also try sheet — new 2-sheet format: Bookings ledger, RoomInventory is static
    try:
        import os
        sheet_id = os.getenv("ROOM_SHEET_ID") or os.getenv("MOCK_ROOM_SHEET_ID")
        if sheet_id and not MOCK_MODE:
            from app.google.auth import get_credentials
            from googleapiclient.discovery import build
            creds = get_credentials()
            if creds:
                svc = build("sheets","v4", credentials=creds)
                rows = None
                clear_range = None
                update_range = None
                date_idx = 1
                sheet_used = "Bookings"
                try:
                    rows = svc.spreadsheets().values().get(spreadsheetId=sheet_id, range="Bookings!A2:F").execute().get("values",[])
                    clear_range = "Bookings!A2:F"
                    update_range = "Bookings!A2"
                except:
                    rows = None
                if rows is None:
                    try:
                        rows = svc.spreadsheets().values().get(spreadsheetId=sheet_id, range="Rooms!A2:H").execute().get("values",[])
                        clear_range = "Rooms!A2:H"
                        update_range = "Rooms!A2"
                        date_idx = 2
                        sheet_used = "Rooms"
                    except:
                        rows = []
                kept=[]; removed=0
                for r in rows or []:
                    if len(r) <= date_idx or not r[date_idx].strip():
                        kept.append(r); continue
                    if r[date_idx].strip() >= today:
                        kept.append(r)
                    else: removed+=1
                if removed and clear_range:
                    svc.spreadsheets().values().clear(spreadsheetId=sheet_id, range=clear_range).execute()
                    if kept: svc.spreadsheets().values().update(spreadsheetId=sheet_id, range=update_range, valueInputOption="RAW", body={"values": kept}).execute()
                return {"db_removed": n, "sheet_removed": removed, "kept": len(kept), "sheet": sheet_used, "today": today}
    except Exception as e:
        return {"db_removed": n, "sheet_error": str(e), "today": today}
    return {"db_removed": n, "today": today}

@app.get("/events")
def get_events(request: Request, scope: Optional[str] = None, user=Depends(get_current_user)):
    # scope=all -> all events (MEC single college), scope=mine -> only caller's org
    # Default: all (per requirement #2)
    if scope == "mine":
        return list_events(org=user["org"], scope_all=False)
    # admin or any club gets all when scope=all or None
    return list_events(scope_all=True)

@app.get("/events/new")
def new_event_page():
    """Serve the React route before the parameterized event endpoint handles it."""
    from pathlib import Path
    from fastapi.responses import FileResponse
    index_file = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist" / "index.html"
    if not index_file.exists():
        raise HTTPException(404, "Frontend not built")
    return FileResponse(index_file)

@app.get("/events/{event_id}")
def get_one_event(event_id: str, request: Request, user=Depends(get_current_user)):
    # Validate UUID format to avoid catching frontend routes like /events/new
    import re
    if not re.match(r'^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{8})$', event_id):
        raise HTTPException(404, "Not found")
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    return ev

@app.post("/events/{event_id}/approve")
def approve_event(event_id: str, body: ApproveRequest, request: Request, user=Depends(get_current_user)):
    # Validate UUID format
    import re
    if not re.match(r'^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{8})$', event_id):
        raise HTTPException(404, "Not found")
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    # RBAC: only admin can approve
    if user["role"] != "admin":
        raise HTTPException(403, "Only admin can approve")
    if ev.status != EventStatus.PENDING_APPROVAL:
        raise HTTPException(400, f"Event not in pending_approval, current: {ev.status}")
    if body.approved:
        # --- AUTO-RESUME: native DB form (Neon) or Google Form fallback ---
        try:
            from .config import USE_NATIVE_FORMS, DATABASE_URL
            use_native = USE_NATIVE_FORMS
            # If Neon is configured and native forms enabled, use DB form (no Google API)
            if use_native:
                from .config import FRONTEND_ORIGIN
                base = FRONTEND_ORIGIN.rstrip("/") if FRONTEND_ORIGIN and FRONTEND_ORIGIN != "*" else str(request.base_url).rstrip("/")
                # If FRONTEND_ORIGIN is localhost in prod, prefer request origin for absolute link
                if "localhost" in base and request.headers.get("origin"):
                    base = request.headers.get("origin").rstrip("/")
                abs_form = f"{base}/r/{ev.id}"
                abs_resp = f"{base}/events/{ev.id}/responses"
                ev.form_id = f"native_{ev.id}"
                ev.form_link = abs_form
                ev.sheet_link = abs_resp
                ev.sheet_id = f"native_sheet_{ev.id}"
                ev.status = EventStatus.LIVE
                save_event(ev)
                announcement_result = ""
                try:
                    from app.tools.announcement import send_announcement as _sa
                    announcement_result = _sa(ev.title or "Event", ev.date or "", ev.room or "", abs_form)
                    if not announcement_result.startswith("[MOCK"):
                        ev.announcement_sent = True
                        save_event(ev)
                except Exception as ae:
                    announcement_result = f"Announcement failed: {ae}"
                    logger.warning("Announcement failed after approval for event %s: %s", ev.id, ae)
                msg = f"Approved. Native form: {ev.form_link} | Responses: {ev.sheet_link}"
                if announcement_result:
                    msg += f" | {announcement_result}"
                return {"message": msg, "event": ev, "agent_response": announcement_result}
            # Google Forms fallback
            from app.tools.forms import create_registration_form as _cf
            import json as _js2
            raw = _cf(ev.title or "Event", ev.date or "", ev.purpose or f"Registration for {ev.title}", ev.form_fields_json or "")
            data = _js2.loads(raw)
            if not data.get("form_link"):
                raise RuntimeError(data.get("error") or "Form creation returned no form_link")
            ev.form_id = data.get("form_id")
            ev.form_link = data.get("form_link")
            ev.sheet_id = data.get("sheet_id") or ev.sheet_id
            ev.sheet_link = data.get("sheet_link") or data.get("responses_link") or ev.sheet_link
            ev.status = EventStatus.LIVE
            save_event(ev)
            announcement_result = ""
            try:
                from app.tools.announcement import send_announcement as _sa
                announcement_result = _sa(ev.title or "Event", ev.date or "", ev.room or "", ev.form_link or "")
                if not announcement_result.startswith("[MOCK"):
                    ev.announcement_sent = True
                    save_event(ev)
            except Exception as ae:
                announcement_result = f"Announcement failed: {ae}"
                logger.warning("Announcement failed after approval for event %s: %s", ev.id, ae)
            msg = f"Approved. Form created: {ev.form_link}"
            if ev.sheet_link:
                msg += f" | Responses sheet: {ev.sheet_link}"
            elif data.get("sheet_error"):
                msg += f" | Response sheet creation failed: {data['sheet_error']}"
            if announcement_result:
                msg += f" | {announcement_result}"
            return {"message": msg, "event": ev, "agent_response": announcement_result}
        except Exception as e:
            logger.exception("Approve resume failed for event %s", ev.id)
            ev.status = EventStatus.PENDING_APPROVAL
            save_event(ev)
            return {"message": f"Approval recorded, but form creation failed: {e}. Event left in pending_approval so it can be retried.", "event": ev}
    else:
        ev.status = EventStatus.DRAFT
        save_event(ev)
        return {"message": "Rejected. Event returned to draft.", "event": ev}

@app.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
def chat(req: ChatRequest, request: Request, user=Depends(get_current_user)):
    # Inject current date for every call so relative dates resolve correctly
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d (%A)")
    date_context = f"[System: Today is {today_str}. Resolve 'next Saturday' etc. to YYYY-MM-DD from this date.]\n"

    # --- Settings completeness gate (block chat if Settings empty) ---
    from .state import is_org_configured, is_google_connected
    ready, missing = is_org_configured(user["org"])
    if not ready:
        raise HTTPException(status_code=400, detail={"error": f"Please complete Settings for {user['org']} before creating events", "missing_fields": missing, "action": "Go to Settings → fill institution, principal email, chairperson, staff, announcement recipients", "org": user["org"]})
    # Drive check: if CENTRAL_DRIVE or USE_NATIVE_FORMS or MOCK_MODE, allow event creation
    from .config import CENTRAL_DRIVE, USE_NATIVE_FORMS, MOCK_MODE
    if not is_google_connected(user["org"]) and not (CENTRAL_DRIVE or USE_NATIVE_FORMS or MOCK_MODE):
        raise HTTPException(status_code=400, detail={"error": f"Google Drive not connected for {user['org']}", "reason": "drive_not_connected", "action": "Go to Settings → Connect Google Drive and approve drive.file/forms.body/spreadsheets permissions", "org": user["org"], "connect_url": f"/auth/google/url?org={user['org']}"})

    # 1-chat heart: persist all extra metadata upfront (time/speaker/purpose/onfoot etc)
    import json as _json
    # If this is a new event (no event_id), create a fresh Event row BEFORE agent so upsert doesn't overwrite old event
    new_event_id = None
    if not req.event_id:
        from app.models import Event as _Event
        _new = _Event()
        _new.ensure_id()
        _new.status = EventStatus.DRAFT
        # Seed a useful title before the agent runs so deterministic fallback
        # responses never leave the event as "Untitled event".
        _new.title = _extract_title_from_message(req.message) or "Campus Event"
        _new.org = user["org"]  # enforce caller's org (sandbox/admin preserved)
        # Enforce date from picker if provided
        if req.date:
            _new.date = req.date
        # pre-seed 1-chat heart so even if agent fails, data isn't lost
        if req.start_time:
            _new.start_time = req.start_time
        if req.end_time:
            _new.end_time = req.end_time
        if req.speaker:
            _new.speaker = req.speaker
        if req.purpose or req.description:
            _new.purpose = req.purpose or req.description
        if req.chairperson:
            _new.chairperson = req.chairperson
        if req.staff_in_charge:
            _new.staff_in_charge = req.staff_in_charge
        if req.need_onfoot is not None:
            _new.need_onfoot = bool(req.need_onfoot)
        if req.fields:
            _new.form_fields_json = _fields_to_json(req.fields)
        save_event(_new)
        new_event_id = _new.id
        # Inject heart into prompt
        extra_heart = []
        if req.start_time or req.end_time:
            extra_heart.append(f"Time: {req.start_time or '?'} to {req.end_time or '?'}")
        if req.speaker:
            extra_heart.append(f"Speaker: {req.speaker}")
        if req.purpose:
            extra_heart.append(f"Purpose: {req.purpose}")
        if req.chairperson:
            extra_heart.append(f"Chairperson: {req.chairperson}")
        if req.staff_in_charge:
            extra_heart.append(f"Staff In Charge: {req.staff_in_charge}")
        if req.need_onfoot is not None:
            extra_heart.append(f"Need on-foot publicity letter: {req.need_onfoot}")
        if extra_heart:
            date_context += f"\n[Event metadata for letter generation (1-chat heart): {'; '.join(extra_heart)} - use these for permission/onfoot letters.]\n"
        if req.fields:
            date_context += f"\n[Form fields upfront: {_fields_to_json(req.fields)} - save via upsert_event form_fields_json and use for create_registration_form.]\n"
        if req.description:
            date_context += f"\n[User event description: {req.description}]\n"
        # Also tell agent the new event_id to use
        date_context += f"\n[New event placeholder created with id={new_event_id} - upsert will update this id.]\n"
    else:
        # Existing event: persist fields/metadata to event for later send
        _ev = get_event(req.event_id)
        if _ev:
            if req.fields:
                _ev.form_fields_json = _fields_to_json(req.fields)
            if req.start_time:
                _ev.start_time = req.start_time
            if req.end_time:
                _ev.end_time = req.end_time
            if req.speaker:
                _ev.speaker = req.speaker
            if req.purpose:
                _ev.purpose = req.purpose
            if req.chairperson:
                _ev.chairperson = req.chairperson
            if req.staff_in_charge:
                _ev.staff_in_charge = req.staff_in_charge
            if req.need_onfoot is not None:
                _ev.need_onfoot = bool(req.need_onfoot)
            if req.description:
                _ev.purpose = req.description  # also store
            save_event(_ev)

    # Load context if event_id provided
    context = ""
    if req.event_id:
        ev = get_event(req.event_id)
        if ev:
            extra = ""
            if ev.form_fields_json and not req.fields:
                extra += f"\n[Stored form fields: {ev.form_fields_json}]\n"
            if ev.need_onfoot:
                extra += f"\n[On-foot publicity required for this event]\n"
            context = f"\n[Current Event Context: {ev.model_dump_json()}]{extra}\n"

    # --- Deterministic conflict pre-check (date picker hybrid) ---
    if req.date and req.start_time and req.end_time:
        # Extract capacity from message (e.g. "for 50 students")
        cap = 30  # fallback
        import re as _re_cap
        mcap = _re_cap.search(r"for\s+(\d+)\s+students", req.message, _re_cap.IGNORECASE)
        if mcap:
            try: cap = int(mcap.group(1))
            except: pass
        from app.tools.room import check_room_availability as _check
        import json as _js
        # Wrap room check with timeout to avoid hanging on Sheets/Neon
        try:
            import signal
            def _timeout_handler(signum, frame): raise TimeoutError("room check timeout")
            # Use thread timeout as fallback - if Sheets hangs, fallback to mock quickly
            raw = _check(req.date, cap, req.start_time, req.end_time)
        except Exception as e:
            logger.warning(f"Room pre-check failed, using mock fallback: {e}")
            raw = _js.dumps({"available": True, "room": "SDPK", "capacity": 60, "source": "mock_fallback_timeout"})
            data = _js.loads(raw)
        else:
            data = _js.loads(raw)
        if data.get("available") is False:
            # Cleanup the placeholder we created (since we block) - handle both SQLite and Neon
            if new_event_id:
                try:
                    from app.state import get_conn as _gc
                    from app.config import DATABASE_URL
                    if DATABASE_URL and DATABASE_URL.strip():
                        # Neon - use state connection
                        conn = _gc()
                        try:
                            conn.execute("DELETE FROM events WHERE id=%s", (new_event_id,))
                            conn.commit()
                        finally:
                            conn.close()
                    else:
                        import sqlite3
                        from app.config import DB_PATH
                        conn = sqlite3.connect(DB_PATH); conn.execute("DELETE FROM events WHERE id=?", (new_event_id,)); conn.commit(); conn.close()
                except Exception as ce:
                    logger.warning(f"Cleanup failed for {new_event_id}: {ce}")
            raise HTTPException(status_code=409, detail=data)

    if not req.event_id and new_event_id and req.date and req.start_time and req.end_time:
        return _create_event_deterministically(req, user, new_event_id)

    full_prompt = date_context + context + req.message

    try:
        try:
            agent = get_agent()
        except ValueError as e:
            raise HTTPException(500, str(e))
        result = _invoke_agent(agent, full_prompt)
        # strands may return: AgentResult, string, or list of blocks like [{'text': ...}, {'reasoningContent': ...}]
        if isinstance(result, list):
            # join all text blocks
            parts = []
            for blk in result:
                if isinstance(blk, dict) and "text" in blk:
                    parts.append(blk["text"])
            text = "\n".join(parts) if parts else str(result)
        elif isinstance(result, dict) and "text" in result:
            text = result["text"]
        elif hasattr(result, "message"):
            msg = result.message
            if isinstance(msg, dict) and "content" in msg:
                content = msg["content"]
                if isinstance(content, list):
                    parts = [c.get("text","") for c in content if isinstance(c, dict) and "text" in c]
                    text = "\n".join(parts) if parts else str(content)
                else:
                    text = str(content)
            elif isinstance(msg, list):
                parts = [b.get("text","") for b in msg if isinstance(b, dict) and "text" in b]
                text = "\n".join(parts) if parts else str(msg)
            else:
                text = str(msg)
        elif hasattr(result, "content"):
            text = str(result.content)
        else:
            text = str(result)
            # strip python list representation like "[{'text': '...'}]" if present
            if text.startswith("[{'text'"):
                import re as _re_text, ast
                try:
                    parsed = ast.literal_eval(text)
                    if isinstance(parsed, list):
                        parts = [p.get("text","") for p in parsed if isinstance(p, dict) and "text" in p]
                        if parts:
                            text = "\n".join(parts)
                except:
                    pass
    except AgentBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        # Gemini 401 etc — fallback to deterministic letter generation instead of 500
        logger.warning(f"Agent fallback due to error: {e} — using deterministic letters/room")
        text = f"[Our AI assistant is temporarily unavailable, but your event has been created successfully. Room and letters were generated with standard templates — please review the draft below and edit if needed. Your selected date {req.date or ''} {req.start_time or ''}-{req.end_time or ''} has been reserved.]"

    # Persist 1-chat heart metadata to newly created event (for send)
    _latest_for_persist = get_latest_event()
    if not req.event_id and _latest_for_persist:
        _latest = _latest_for_persist
        needs_save = False
        if req.fields and not _latest.form_fields_json:
            _latest.form_fields_json = _fields_to_json(req.fields)
            needs_save = True
        if req.start_time and not _latest.start_time:
            _latest.start_time = req.start_time
            needs_save = True
        if req.end_time and not _latest.end_time:
            _latest.end_time = req.end_time
            needs_save = True
        if req.speaker and not _latest.speaker:
            _latest.speaker = req.speaker
            needs_save = True
        if req.purpose and not _latest.purpose:
            _latest.purpose = req.purpose
            needs_save = True
        if req.chairperson and not _latest.chairperson:
            _latest.chairperson = req.chairperson
            needs_save = True
        if req.staff_in_charge and not _latest.staff_in_charge:
            _latest.staff_in_charge = req.staff_in_charge
            needs_save = True
        if req.need_onfoot is not None and not _latest.need_onfoot:
            _latest.need_onfoot = bool(req.need_onfoot)
            needs_save = True
        if needs_save:
            save_event(_latest)
        _latest_for_persist = get_latest_event()
        # Fallback: ensure room/status set even if agent failed (Gemini fallback)
        try:
            _evf = get_latest_event()
            if _evf and not _evf.room and req.date and req.start_time and req.end_time:
                from app.tools.room import check_room_availability as _chk2
                import json as _js2
                cap2 = 30
                import re as _re2
                m2 = _re2.search(r"for\s+(\d+)\s+students", req.message, _re2.IGNORECASE)
                if m2:
                    try: cap2 = int(m2.group(1))
                    except: pass
                raw2 = _chk2(req.date, cap2, req.start_time, req.end_time)
                d2 = _js2.loads(raw2)
                if d2.get("room"):
                    _evf.room = d2["room"]
                    _evf.room_capacity = d2.get("capacity")
                    _evf.date = req.date
                    _evf.status = EventStatus.PENDING_APPROVAL
                    save_event(_evf)
            elif _evf and _evf.room and _evf.status == EventStatus.DRAFT:
                _evf.status = EventStatus.PENDING_APPROVAL
                save_event(_evf)
        except: pass

    # Fix title if agent used description as title (e.g. "Learn GIT..." instead of "GIT Workshop")
    _title_fixed = False
    _old_title = ""
    _pre_latest = get_latest_event()
    if _pre_latest and not req.event_id and _pre_latest.title:
        _low = _pre_latest.title.lower()
        if len(_pre_latest.title) > 35 or "powerfull" in _low or "simple" in _low or _low == (_pre_latest.purpose or "").lower():
            extracted = _extract_title_from_message(req.message)
            if extracted and extracted.lower() not in _low:
                _old_title = _pre_latest.title
                _pre_latest.title = extracted
                save_event(_pre_latest)
                _title_fixed = True

    # Fallback: ensure high-quality letters exist even if agent didn't call tools (e.g. draft_permission_email instead)
    latest_for_letters = get_latest_event()
    if latest_for_letters and not req.event_id:
        need_perm = not latest_for_letters.permission_letter
        # If title was just fixed but letter still has old title, force regeneration
        if _title_fixed and latest_for_letters.permission_letter and _old_title and _old_title in latest_for_letters.permission_letter:
            need_perm = True
        need_onfoot = bool(latest_for_letters.need_onfoot) and not latest_for_letters.onfoot_letter
        if need_perm or need_onfoot:
            try:
                from app.tools.letters import generate_permission_letter, generate_onfoot_letter
                # Resolve dynamic defaults from org settings
                _s = get_org_settings(latest_for_letters.org or req.message[:30])
                _def_org = _s.org if _s.org and _s.org != "default" else (latest_for_letters.org or "FOSS MEC")
                _def_chair = _s.chairperson or "Charles Xavier"
                _def_staff = _s.staff_in_charge or "Joby John"
                if need_perm:
                    generate_permission_letter(
                        latest_for_letters.org or _def_org,
                        latest_for_letters.title or "Workshop",
                        latest_for_letters.date or "2026-08-31",
                        latest_for_letters.start_time or req.start_time or "3:30 PM",
                        latest_for_letters.end_time or req.end_time or "4:30 PM",
                        latest_for_letters.room or "SDPK",
                        latest_for_letters.speaker or req.speaker or "",
                        latest_for_letters.purpose or req.purpose or req.description or "",
                        latest_for_letters.chairperson or req.chairperson or _def_chair,
                        latest_for_letters.staff_in_charge or req.staff_in_charge or _def_staff
                    )
                if need_onfoot:
                    generate_onfoot_letter(
                        latest_for_letters.org or _def_org,
                        latest_for_letters.title or "Workshop",
                        latest_for_letters.date or "2026-08-31",
                        latest_for_letters.start_time or req.start_time or "3:30 PM",
                        latest_for_letters.end_time or req.end_time or "4:30 PM",
                        latest_for_letters.room or "SDPK",
                        latest_for_letters.speaker or req.speaker or "",
                        latest_for_letters.purpose or req.purpose or req.description or "",
                        latest_for_letters.chairperson or req.chairperson or _def_chair,
                        latest_for_letters.staff_in_charge or req.staff_in_charge or _def_staff
                    )
            except Exception as le:
                logger.warning("letter fallback failed: %s", le)

    # Try to track latest event for response - include drafts so frontend can show/edit
    latest = get_latest_event()
    if latest:
        email_preview = latest.email_draft or latest.permission_letter or ""
        # If still empty, build a minimal preview for frontend using org settings
        if not email_preview and latest.title:
            _s_prev = get_org_settings(latest.org or "")
            _inst_n = _s_prev.institution_name or INSTITUTION_NAME
            _inst_p = _s_prev.institution_place or INSTITUTION_PLACE
            _chair = latest.chairperson or _s_prev.chairperson or DEFAULT_CHAIRPERSON
            email_preview = f"To,\nThe Principal,\n{_inst_n},\n{_inst_p}.\n\nSubject: Request for permission to host \"{latest.title}\"\n\nRespected Sir/Madam,\n\nI am writing to request permission to conduct \"{latest.title}\", organized by {latest.org}, on {latest.date} from {latest.start_time or '3:30 PM'} to {latest.end_time or '4:30 PM'} at {latest.room}.\n\n{latest.purpose or ''}\n\nThank you.\n\nWith regards,\nChairperson {latest.org}\n{_chair}"
        return ChatResponse(
            response=text,
            event_id=latest.id,
            status=latest.status,
            permission_letter=latest.permission_letter or email_preview,
            onfoot_letter=latest.onfoot_letter,
            announcement_draft=latest.announcement_draft,
            email_draft=email_preview
        )
    return ChatResponse(response=text, event_id=None, status=None)

@app.post("/events/{event_id}/send-permission-email")
def send_permission_email(event_id: str, body: SendEmailRequest, request: Request, user=Depends(get_current_user)):
    """Club has reviewed/edited the draft shown in /chat. This sends it to principal/staff with PDFs attached."""
    # Validate UUID format
    import re
    if not re.match(r'^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{8})$', event_id):
        raise HTTPException(404, "Not found")
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    # RBAC: only owner org or admin (sandbox can send its own)
    if user["role"] != "admin" and ev.org.strip().lower() != user["org"].strip().lower():
        raise HTTPException(403, "Not your club's event")
    if ev.permission_email_sent:
        return {"sent": True, "already_sent": True, "to": get_org_settings(ev.org or "").faculty_email or FACULTY_EMAIL, "message_id": ev.permission_email_message_id, "event": ev}
    # Allow natural language regeneration via LLM
    if body.regenerate_instruction:
        try:
            agent = get_agent()
            prompt = f"[Event {ev.id} context: {ev.model_dump_json()}] Regenerate permission letter as per instruction: {body.regenerate_instruction}. Use generate_permission_letter and generate_onfoot_letter if needed, then upsert."
            _invoke_agent(agent, prompt)
            ev = get_event(event_id)  # reload after regeneration
        except Exception as e:
            raise HTTPException(500, f"Regeneration failed: {e}")
    # Ensure permission/onfoot letters exist (generate on-the-fly if chat missed them)
    if not ev.permission_letter:
        try:
            from app.tools.letters import generate_permission_letter
            generate_permission_letter(ev.org, ev.title, ev.date, ev.start_time or "3:30 PM", ev.end_time or "4:30 PM", ev.room or "SDPK", ev.speaker or "", ev.purpose or "", ev.chairperson or "", ev.staff_in_charge or "")
            ev = get_event(event_id)
        except:
            pass
    if ev.need_onfoot and not ev.onfoot_letter:
        try:
            from app.tools.letters import generate_onfoot_letter
            generate_onfoot_letter(ev.org, ev.title, ev.date, ev.start_time or "3:30 PM", ev.end_time or "4:30 PM", ev.room or "SDPK", ev.speaker or "", ev.purpose or "", ev.chairperson or "", ev.staff_in_charge or "")
            ev = get_event(event_id)
        except:
            pass
    # If club edited the permission letter in textarea, that text is the LETTER (for PDF), not the email body
    if body.edited_email and body.edited_email.strip() and body.edited_email.strip() != ev.permission_letter:
        # Treat edited_email as edited permission letter content → save for PDF, email stays brief
        ev.permission_letter = body.edited_email.strip()
        save_event(ev)
    # Brief email body always references PDFs, never duplicates full letter
    onfoot_note = " Also attached is the on-foot publicity request letter." if ev.need_onfoot else ""
    
    # Build detailed event info for email
    speaker_info = f"\nSpeaker: {ev.speaker}" if ev.speaker else ""
    purpose_info = f"\nPurpose: {ev.purpose}" if ev.purpose else ""
    headcount_info = f"Expected Headcount: {ev.expected_headcount}"
    capacity_info = f"Room Capacity: {ev.room_capacity or 'as per venue'}"
    time_info = f"Time: {ev.start_time or '3:30 PM'} to {ev.end_time or '4:30 PM'}"
    venue_info = f"Venue: {ev.room}"
    date_info = f"Date: {ev.date}"
    
    # Resolve org settings for signature fallback
    _s_email = get_org_settings(ev.org or "")
    # Block send if org not configured (faculty/announcement missing) — warn and require Settings
    from .state import is_org_configured as _is_cfg
    _cfg_ok, _cfg_missing = _is_cfg(ev.org or "")
    if not _cfg_ok:
        raise HTTPException(status_code=400, detail={"error": f"Please complete Settings for {ev.org} before sending permission email", "missing_fields": _cfg_missing, "action": "Go to Settings → fill principal email, announcement recipients, chairperson, staff"})
    _c = ev.chairperson or _s_email.chairperson or DEFAULT_CHAIRPERSON
    _st = ev.staff_in_charge or _s_email.staff_in_charge or DEFAULT_STAFF
    full_body = f"""Respected Sir/Madam,

I hope you are well. On behalf of {ev.org}, I am writing to seek your kind permission to host "{ev.title}" on {ev.date}.

Event Details:
{date_info}
{time_info}
{venue_info}
{headcount_info}
{capacity_info}{speaker_info}{purpose_info}

Please find attached the detailed permission letter (PDF){onfoot_note} Kindly review the PDFs at your convenience.

We would be grateful for your approval. Thank you for your continued support.

With regards,
Chairperson {ev.org}
{_c}

Staff In Charge {ev.org}
{_st}

---
This email was generated via CampusOps. For queries, contact {_c} ({_st}) from {ev.org}.
"""

    # Build PDFs
    import os, base64
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication
    from app.pdf import permission_letter_pdf, onfoot_letter_pdf
    from app.google.auth import get_credentials
    from googleapiclient.discovery import build
    faculty_email = _s_email.faculty_email or FACULTY_EMAIL
    subject = f"Request for permission to host \"{ev.title}\" - {ev.org}"

    mock_mode = MOCK_MODE
    if mock_mode:
        return {"mock": True, "to": faculty_email, "subject": subject, "body_preview": full_body[:400], "event": ev, "note": "MOCK_MODE=true - email not sent. Set false to actually send with PDFs."}

    try:
        from app.email import send_permission_email
        
        pdf_attachments = []
        if ev.permission_letter:
            pdf_bytes = permission_letter_pdf(ev.permission_letter)
            pdf_attachments.append((f"Permission_Letter_{ev.title.replace(' ', '_')}.pdf", pdf_bytes))
        if ev.need_onfoot and ev.onfoot_letter:
            pdf_bytes = onfoot_letter_pdf(ev.onfoot_letter)
            pdf_attachments.append((f"OnFoot_Publicity_{ev.title.replace(' ', '_')}.pdf", pdf_bytes))
        
        result = send_permission_email(
            to_email=faculty_email,
            subject=subject,
            html_body=full_body.replace("\n", "<br>"),
            pdf_attachments=pdf_attachments
        )
        ev.email_draft = full_body
        ev.permission_email_sent = True
        ev.permission_email_message_id = result["message_id"]
        from datetime import datetime, timezone
        ev.permission_email_sent_at = datetime.now(timezone.utc).isoformat()
        save_event(ev)
        return {"sent": True, "to": faculty_email, "message_id": result["message_id"], "subject": subject, "event": ev}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to send email: {e}")

@app.get("/events/{event_id}/registrations")
def get_registrations(event_id: str, request: Request, user=Depends(get_current_user)):
    """On-demand count with 60s cache. Native DB -> COUNT(*) from event_responses, Google -> Forms API."""
    import re, json, time
    if not re.match(r'^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{8})$', event_id):
        raise HTTPException(404, "Not found")
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    # Native DB path - on-demand count from Neon/SQLite event_responses
    if ev.form_id and ev.form_id.startswith("native_"):
        from .state import count_responses
        cnt = count_responses(ev.id)
        # update cached count if changed
        if cnt != ev.registrant_count:
            ev.registrant_count = cnt
            save_event(ev)
        return {"event_id": event_id, "form_id": ev.form_id, "form_link": ev.form_link, "sheet_id": ev.sheet_id, "sheet_link": ev.sheet_link, "count": cnt, "source": "native_db", "native": True}
    if not ev.form_id or ev.form_id.startswith("mock_"):
        return {"event_id": event_id, "form_id": ev.form_id, "sheet_id": ev.sheet_id, "sheet_link": ev.sheet_link, "count": ev.registrant_count or 0, "mock": True, "note": "Mock form - no live registrations"}
    from app.tools.registrations import get_registration_count, sync_responses_to_sheet
    sync_res = {}
    if ev.sheet_id and not ev.sheet_id.startswith("mock_") and not ev.sheet_id.startswith("sheet_"):
        try:
            sync_res = sync_responses_to_sheet(ev.form_id, ev.sheet_id)
        except Exception as e:
            sync_res = {"synced": False, "error": str(e)}
    raw = get_registration_count(ev.sheet_id or "", ev.form_id or "")
    data = json.loads(raw)
    try:
        ev.registrant_count = int(data.get("registrant_count", 0) or 0)
        save_event(ev)
    except:
        pass
    return {"event_id": event_id, "form_id": ev.form_id, "form_link": ev.form_link, "sheet_id": ev.sheet_id, "sheet_link": ev.sheet_link, "count": data.get("registrant_count", 0), "source": data.get("source"), "sync": sync_res, "raw": data}

@app.post("/events/{event_id}/sync")
def sync_event(event_id: str, request: Request, user=Depends(get_current_user)):
    """Force sync Forms responses → Sheet without LLM. Makes sheet_link show registrations."""
    # Validate UUID format
    import re
    if not re.match(r'^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{8})$', event_id):
        raise HTTPException(404, "Not found")
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    if not ev.form_id or ev.form_id.startswith("mock_") or not ev.sheet_id or ev.sheet_id.startswith("mock_") or ev.sheet_id.startswith("sheet_"):
        raise HTTPException(400, "Need real form_id and sheet_id - event was mock or sheet not created")
    from app.tools.registrations import sync_responses_to_sheet
    res = sync_responses_to_sheet(ev.form_id, ev.sheet_id)
    return {"event_id": event_id, "sheet_link": ev.sheet_link, "sync": res}

@app.post("/events/{event_id}/reset")
def reset_event(event_id: str, request: Request, user=Depends(get_current_user)):
    """Testing helper: reset event to pending_approval and clear form/sheet so you can re-test approve. Admin only."""
    if user["role"] != "admin":
        raise HTTPException(403, "Only admin can reset")
    # Validate UUID format
    import re
    if not re.match(r'^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{8})$', event_id):
        raise HTTPException(404, "Not found")
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    ev.status = EventStatus.PENDING_APPROVAL
    ev.form_id = None
    ev.form_link = None
    ev.sheet_id = None
    ev.sheet_link = None
    ev.announcement_sent = False
    save_event(ev)
    return {"reset": True, "event": ev}

class FormCreateRequest(BaseModel):
    fields: Optional[List[FieldModel]] = None
    description: Optional[str] = ""

@app.post("/events/{event_id}/form")
def create_form_direct(event_id: str, body: FormCreateRequest, request: Request, user=Depends(get_current_user)):
    """Low-level deterministic form creation - frontend calls this with chip-selected fields (no LLM needed)."""
    # Validate UUID format
    import re
    if not re.match(r'^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{8})$', event_id):
        raise HTTPException(404, "Not found")
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    if ev.status not in [EventStatus.LIVE, EventStatus.PENDING_APPROVAL, EventStatus.ROOM_IDENTIFIED]:
        raise HTTPException(400, f"Event status {ev.status} not ready for form creation. Approve first.")
    import json, os
    from app.tools.forms import create_registration_form as _create_form
    # Strands tool is wrapped; call underlying logic via direct import
    # We invoke the tool's python function by calling it as regular function (tool decorator preserves callable)
    fields_json = _fields_to_json(body.fields) if body.fields else ""
    desc = body.description or f"Registration for {ev.title}"
    # persist chosen fields for audit/reuse
    if fields_json:
        ev.form_fields_json = fields_json
        save_event(ev)
    result_json = _create_form(ev.title, ev.date, desc, fields_json)
    result = json.loads(result_json)
    if result.get("form_link"):
        ev.form_id = result.get("form_id")
        ev.form_link = result.get("form_link")
        ev.sheet_id = result.get("sheet_id") or ev.sheet_id
        ev.sheet_link = result.get("sheet_link") or result.get("responses_link") or ev.sheet_link
        save_event(ev)
    return {"event": ev, "form_result": result}

# --- Org Settings Endpoints (dynamic, per-club) ---
@app.get("/settings")
def list_settings(request: Request, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Only admin can list all settings")
    return list_org_settings()

@app.get("/settings/{org}")
def get_settings(org: str, request: Request, user=Depends(get_current_user)):
    # URL-decode org name
    import urllib.parse
    org = urllib.parse.unquote(org)
    return get_org_settings(org)

@app.put("/settings/{org}")
def upsert_settings(org: str, body: OrgSettings, request: Request, user=Depends(get_current_user)):
    import urllib.parse
    org = urllib.parse.unquote(org)
    # RBAC: only owner org or admin (sandbox can edit its own)
    if user["role"] != "admin" and org.strip().lower() != user["org"].strip().lower():
        raise HTTPException(403, "Not your org")
    # Ensure path org matches body org if provided
    body.org = org
    # basic email validation: allow comma-separated list for announcement_recipients, single email for faculty_email
    if body.faculty_email and "@" not in body.faculty_email:
        raise HTTPException(400, "faculty_email must be a valid email")
    # announcement_recipients can be comma separated; validate each
    if body.announcement_recipients:
        for part in [p.strip() for p in body.announcement_recipients.split(",") if p.strip()]:
            if "@" not in part:
                raise HTTPException(400, f"Invalid announcement recipient email: {part}")
    return save_org_settings(body)

# --- Native DB Responses (replaces Sheets) ---
@app.get("/r/{event_id}")
def get_public_form(event_id: str):
    """Public: fetch event form metadata for native submission. No auth required."""
    import re
    if not re.match(r'^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{8})$', event_id):
        raise HTTPException(404, "Not found")
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    if ev.status not in [EventStatus.LIVE, EventStatus.CLOSED]:
        raise HTTPException(400, f"Event not live (status: {ev.status}) - registration not open")
    import json
    fields = []
    if ev.form_fields_json:
        try:
            fields = json.loads(ev.form_fields_json)
            if isinstance(fields, str):
                fields = json.loads(fields)
        except: fields = []
    if not fields:
        fields = [{"title":"Full Name","type":"text","required":True},{"title":"Email","type":"text","required":True}]
    return {"event_id": ev.id, "title": ev.title, "org": ev.org, "date": ev.date, "room": ev.room, "start_time": ev.start_time, "end_time": ev.end_time, "purpose": ev.purpose, "speaker": ev.speaker, "expected_headcount": ev.expected_headcount, "fields": fields, "status": ev.status}

@app.post("/r/{event_id}/submit")
@limiter.limit("30/minute")
def submit_response(event_id: str, request: Request):
    """Public form submission -> stored in Neon/SQLite event_responses."""
    import re, json, hashlib
    if not re.match(r'^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{8})$', event_id):
        raise HTTPException(404, "Not found")
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    if ev.status not in [EventStatus.LIVE, EventStatus.CLOSED]:
        raise HTTPException(400, f"Registration not open (status: {ev.status})")
    # Check capacity
    from .state import count_responses, add_response
    cnt = count_responses(ev.id)
    if ev.expected_headcount and cnt >= ev.expected_headcount * 1.2:  # allow 20% overfill
        raise HTTPException(409, "Registration full")
    # Parse body as dict of field_title -> value (frontend sends { responses: {title: value} })
    import asyncio
    # FastAPI will parse JSON automatically if we use dict
    # Use raw body
    try:
        body = _json_global.loads(request._body.decode() if hasattr(request,'_body') else "{}") if False else None
    except: body=None
    # Fallback: try sync read via starlette
    # Simpler: use request.json via dependency - we handle via pydantic below by reading body bytes
    return {"error":"Use /r/{event_id}/submit-json endpoint"}  # placeholder

@app.post("/r/{event_id}/submit-json")
@limiter.limit("30/minute")
def submit_response_json(event_id: str, payload: dict, request: Request):
    """Public JSON submit: {responses: {FieldTitle: value}, email?: str}"""
    import re, json
    if not re.match(r'^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{8})$', event_id):
        raise HTTPException(404, "Not found")
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    if ev.status not in [EventStatus.LIVE, EventStatus.CLOSED]:
        raise HTTPException(400, f"Registration not open (status: {ev.status})")
    from .state import count_responses, add_response
    cnt = count_responses(ev.id)
    if ev.expected_headcount and cnt >= ev.expected_headcount * 1.5:
        raise HTTPException(409, "Registration full - capacity reached")
    responses = payload.get("responses") if isinstance(payload.get("responses"), dict) else payload
    # sanitize: ensure dict
    if not isinstance(responses, dict):
        raise HTTPException(400, "Invalid payload: expected {responses: {Field: value}} or {Field: value}")
    # Validate required fields
    import json as _js
    required = []
    if ev.form_fields_json:
        try:
            fields = _js.loads(ev.form_fields_json)
            if isinstance(fields, str): fields=_js.loads(fields)
            for f in fields:
                if f.get("required"):
                    required.append(f.get("title"))
        except: pass
    for r in required:
        if not responses.get(r) or not str(responses.get(r)).strip():
            raise HTTPException(400, f"Missing required field: {r}")
    email = responses.get("Email") or responses.get("email") or payload.get("email") or ""
    rid = add_response(ev.id, responses, str(email)[:120])
    # update cached count
    try:
        ev.registrant_count = cnt + 1
        save_event(ev)
    except: pass
    return {"ok": True, "response_id": rid, "event_id": event_id, "count": cnt+1}

@app.get("/events/{event_id}/responses")
def get_responses(event_id: str, request: Request, user=Depends(get_current_user), limit: int = 100, offset: int = 0, format: str = ""):
    """Private: club view of native DB responses. Unique link replaces Sheets. Supports ?format=csv."""
    import re, json, csv, io
    if not re.match(r'^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{8})$', event_id):
        raise HTTPException(404, "Not found")
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    if user["role"] != "admin" and ev.org.strip().lower() != user["org"].strip().lower():
        raise HTTPException(403, "Not your club's event")
    from .state import list_responses, count_responses
    total = count_responses(ev.id)
    rows = list_responses(ev.id, limit=min(limit,200), offset=offset)
    # Build headers from event fields
    headers=[]
    if ev.form_fields_json:
        try:
            f=_js2=json.loads(ev.form_fields_json)
            if isinstance(f,str): f=json.loads(f)
            headers=[x.get("title") for x in f if x.get("title")]
        except: pass
    if not headers and rows:
        headers=list(rows[0]["data"].keys())
    if format.lower()=="csv":
        from fastapi.responses import StreamingResponse
        output=io.StringIO()
        w=csv.writer(output)
        w.writerow(["submitted_at","email"]+headers)
        all_rows = list_responses(ev.id, limit=10000, offset=0)
        for r in all_rows:
            w.writerow([r["created_at"], r["respondent_email"]] + [r["data"].get(h,"") for h in headers])
        output.seek(0)
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=responses_{event_id}.csv"})
    return {"event_id": event_id, "title": ev.title, "org": ev.org, "total": total, "headers": headers, "rows": rows, "limit": limit, "offset": offset, "native": True}

# Helper endpoint to create/update event manually (for testing)
@app.post("/events")
def create_event(ev: Event, request: Request, user=Depends(get_current_user)):
    ev.ensure_id()
    if user["role"] != "admin" and ev.org.strip().lower() != user["org"].strip().lower():
        # Force org to caller's org if mismatch (prevent spoofing)
        ev.org = user["org"]
    save_event(ev)
    return ev

# Serve frontend static files (built with Vite)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import pathlib

FRONTEND_DIST = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

logger.info(f"FRONTEND_DIST = {FRONTEND_DIST}, exists={FRONTEND_DIST.exists()}, index_exists={(FRONTEND_DIST / 'index.html').exists()}")

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # API routes that should NOT serve index.html (let FastAPI handle them)
        api_prefixes = ("api/", "chat", "test")
        is_api = any(full_path.startswith(p) for p in api_prefixes)
        logger.info(f"SPA catch-all: full_path='{full_path}', is_api={is_api}")
        if is_api:
            raise HTTPException(404, "Not found")
        # Serve index.html for all other routes (React Router handles them)
        index_file = FRONTEND_DIST / "index.html"
        logger.info(f"index_file = {index_file}, exists={index_file.exists()}")
        if index_file.exists():
            return FileResponse(index_file)
        raise HTTPException(404, "Frontend not built")
