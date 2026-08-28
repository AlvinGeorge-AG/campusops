from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from typing import Optional
import os
from dotenv import load_dotenv
load_dotenv()

from .agent import get_agent
from .state import save_event, get_event, list_events, get_latest_event
from .models import Event, EventStatus
from .config import (
    MOCK_MODE, POLLER_ENABLED, FACULTY_EMAIL, 
    DEFAULT_CHAIRPERSON, DEFAULT_STAFF, INSTITUTION_NAME, INSTITUTION_PLACE
)
import asyncio
import logging
import re

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

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

# --- Optional poller: if POLLER_ENABLED=true, auto-sync Forms→Sheet every 60s without manual Link click ---
_poller_task = None

async def _poll_forms_loop():
    await asyncio.sleep(10)
    while True:
        try:
            if not POLLER_ENABLED or MOCK_MODE:
                await asyncio.sleep(60)
                continue
            events = list_events()
            for ev in events:
                if ev.status != EventStatus.LIVE or not ev.form_id or ev.form_id.startswith("mock_") or not ev.sheet_id or ev.sheet_id.startswith("mock_") or ev.sheet_id.startswith("sheet_"):
                    continue
                try:
                    from app.tools.registrations import sync_responses_to_sheet, get_registration_count
                    import json
                    sync_responses_to_sheet(ev.form_id, ev.sheet_id)
                    raw = get_registration_count(ev.sheet_id, ev.form_id)
                    data = json.loads(raw)
                    cnt = int(data.get("registrant_count", 0) or 0)
                    if cnt != ev.registrant_count:
                        ev.registrant_count = cnt
                        save_event(ev)
                except Exception:
                    pass
        except Exception:
            pass
        await asyncio.sleep(60)

@app.on_event("startup")
async def start_poller():
    global _poller_task
    if POLLER_ENABLED:
        _poller_task = asyncio.create_task(_poll_forms_loop())
        logger.info("Poller enabled (60s)")

@app.on_event("shutdown")
async def stop_poller():
    global _poller_task
    if _poller_task:
        _poller_task.cancel()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    event_id: Optional[str] = None
    fields: Optional[list] = None  # 1-request: form fields e.g. [{"title":"Phone","type":"text"}]
    description: Optional[str] = None
    # Heart of 1-chat: collect all for high-quality letters upfront
    start_time: Optional[str] = None  # e.g. 3:30 PM
    end_time: Optional[str] = None  # e.g. 4:30 PM
    speaker: Optional[str] = None
    purpose: Optional[str] = None
    chairperson: Optional[str] = None
    staff_in_charge: Optional[str] = None
    need_onfoot: Optional[bool] = None

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

@app.get("/")
def health():
    return {"status": "ok", "service": "CampusOps Backend", "mock_mode": MOCK_MODE}

@app.get("/events")
def get_events():
    return list_events()

@app.get("/events/{event_id}")
def get_one_event(event_id: str):
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    return ev

@app.post("/events/{event_id}/approve")
def approve_event(event_id: str, body: ApproveRequest):
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    if ev.status != EventStatus.PENDING_APPROVAL:
        raise HTTPException(400, f"Event not in pending_approval, current: {ev.status}")
    if body.approved:
        ev.status = EventStatus.LIVE
        save_event(ev)
        # --- AUTO-RESUME: intelligently continue without manual /chat, reusing stored fields + announcement draft ---
        try:
            agent = get_agent()
            from datetime import datetime
            import json as _json
            today_str = datetime.now().strftime("%Y-%m-%d (%A)")
            fields_note = ""
            if ev.form_fields_json:
                try:
                    _fields = _json.loads(ev.form_fields_json)
                    fields_note = f"Use this exact fields_json for form: {ev.form_fields_json}. "
                    # also ensure agent reuses preview announcement
                except:
                    pass
            announcement_note = ""
            if ev.announcement_draft:
                announcement_note = f"Reuse this announcement draft (already approved by authority): {ev.announcement_draft} "
            resume_prompt = (
                f"[System: Today is {today_str}. Human APPROVED event {ev.id}. "
                f"Event context: {ev.model_dump_json()} "
                f"Resume workflow: create registration form and send announcement. "
                f"{fields_note}{announcement_note}"
                f"If no fields specified, use defaults. Persist with upsert_event including sheet_link.]"
            )
            result = agent(resume_prompt)
            # normalize agent response like chat does
            if isinstance(result, list):
                parts = [b.get("text","") for b in result if isinstance(b, dict) and "text" in b]
                text = "\n".join(parts) if parts else str(result)
            elif hasattr(result, "message"):
                msg = result.message
                text = str(msg)
                if isinstance(msg, list):
                    parts = [b.get("text","") for b in msg if isinstance(b, dict) and "text" in b]
                    text = "\n".join(parts) if parts else text
            else:
                text = str(result)
            latest = get_latest_event()
            # also fetch updated event (upsert may have updated latest)
            updated = get_event(event_id)
            return {"message": "Approved and auto-resumed. " + text, "event": updated or latest, "agent_response": text}
        except Exception as e:
            # approval succeeded even if agent resume fails
            return {"message": f"Approved but agent resume failed: {e}. Call POST /chat with event_id to retry.", "event": ev}
    else:
        ev.status = EventStatus.DRAFT
        save_event(ev)
        return {"message": "Rejected. Event returned to draft.", "event": ev}

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        agent = get_agent()
    except ValueError as e:
        raise HTTPException(500, str(e))

    # Inject current date for every call so relative dates resolve correctly
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d (%A)")
    date_context = f"[System: Today is {today_str}. Resolve 'next Saturday' etc. to YYYY-MM-DD from this date.]\n"

    # 1-chat heart: persist all extra metadata upfront (time/speaker/purpose/onfoot etc)
    import json as _json
    # If this is a new event (no event_id), create a fresh Event row BEFORE agent so upsert doesn't overwrite old event
    new_event_id = None
    if not req.event_id:
        from app.models import Event as _Event
        _new = _Event()
        _new.ensure_id()
        _new.status = EventStatus.DRAFT
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
            _new.form_fields_json = _json.dumps(req.fields)
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
            date_context += f"\n[Form fields upfront: {_json.dumps(req.fields)} - save via upsert_event form_fields_json and use for create_registration_form.]\n"
        if req.description:
            date_context += f"\n[User event description: {req.description}]\n"
        # Also tell agent the new event_id to use
        date_context += f"\n[New event placeholder created with id={new_event_id} - upsert will update this id.]\n"
    else:
        # Existing event: persist fields/metadata to event for later send
        _ev = get_event(req.event_id)
        if _ev:
            if req.fields:
                _ev.form_fields_json = _json.dumps(req.fields)
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

    full_prompt = date_context + context + req.message

    try:
        result = agent(full_prompt)
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
                import re, ast
                try:
                    parsed = ast.literal_eval(text)
                    if isinstance(parsed, list):
                        parts = [p.get("text","") for p in parsed if isinstance(p, dict) and "text" in p]
                        if parts:
                            text = "\n".join(parts)
                except:
                    pass
    except Exception as e:
        raise HTTPException(500, f"Agent error: {e}")

    # Persist 1-chat heart metadata to newly created event (for send)
    _latest_for_persist = get_latest_event()
    if not req.event_id and _latest_for_persist:
        _latest = _latest_for_persist
        needs_save = False
        if req.fields and not _latest.form_fields_json:
            _latest.form_fields_json = _json.dumps(req.fields)
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
        need_ann = not latest_for_letters.announcement_draft
        # Also regenerate announcement if title fixed and it contains old title
        if _title_fixed and latest_for_letters.announcement_draft and _old_title and _old_title in latest_for_letters.announcement_draft:
            need_ann = True
        if need_perm or need_onfoot or need_ann:
            try:
                from app.tools.letters import generate_permission_letter, generate_onfoot_letter, generate_announcement_preview
                if need_perm:
                    generate_permission_letter(
                        latest_for_letters.org or "FOSS MEC",
                        latest_for_letters.title or "Workshop",
                        latest_for_letters.date or "2026-08-31",
                        latest_for_letters.start_time or req.start_time or "3:30 PM",
                        latest_for_letters.end_time or req.end_time or "4:30 PM",
                        latest_for_letters.room or "SDPK",
                        latest_for_letters.speaker or req.speaker or "",
                        latest_for_letters.purpose or req.purpose or req.description or "",
                        latest_for_letters.chairperson or req.chairperson or "Arthana Sreekesh",
                        latest_for_letters.staff_in_charge or req.staff_in_charge or "Aysha Fymin Majeed"
                    )
                if need_onfoot:
                    generate_onfoot_letter(
                        latest_for_letters.org or "FOSS MEC",
                        latest_for_letters.title or "Workshop",
                        latest_for_letters.date or "2026-08-31",
                        latest_for_letters.start_time or req.start_time or "3:30 PM",
                        latest_for_letters.end_time or req.end_time or "4:30 PM",
                        latest_for_letters.room or "SDPK",
                        latest_for_letters.speaker or req.speaker or "",
                        latest_for_letters.purpose or req.purpose or req.description or "",
                        latest_for_letters.chairperson or req.chairperson or "Arthana Sreekesh",
                        latest_for_letters.staff_in_charge or req.staff_in_charge or "Aysha Fymin Majeed"
                    )
                if need_ann:
                    generate_announcement_preview(
                        latest_for_letters.org or "FOSS MEC",
                        latest_for_letters.title or "Workshop",
                        latest_for_letters.date or "2026-08-31",
                        latest_for_letters.room or "SDPK",
                        latest_for_letters.expected_headcount or 50,
                        latest_for_letters.purpose or req.purpose or req.description or ""
                    )
            except Exception as le:
                logger.warning("letter fallback failed: %s", le)

    # Try to track latest event for response - include drafts so frontend can show/edit
    latest = get_latest_event()
    if latest:
        email_preview = latest.email_draft or latest.permission_letter or ""
        # If still empty, build a minimal preview for frontend
        if not email_preview and latest.title:
            email_preview = f"To,\nThe Principal,\n{INSTITUTION_NAME},\n{INSTITUTION_PLACE}.\n\nSubject: Request for permission to host \"{latest.title}\"\n\nRespected Sir/Madam,\n\nI am writing to request permission to conduct \"{latest.title}\", organized by {latest.org}, on {latest.date} from {latest.start_time or '3:30 PM'} to {latest.end_time or '4:30 PM'} at {latest.room}.\n\n{latest.purpose or ''}\n\nThank you.\n\nWith regards,\nChairperson {latest.org}\n{latest.chairperson or DEFAULT_CHAIRPERSON}"
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
def send_permission_email(event_id: str, body: SendEmailRequest):
    """Club has reviewed/edited the draft shown in /chat. This sends it to principal/staff with PDFs attached."""
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    # Allow natural language regeneration via LLM
    if body.regenerate_instruction:
        try:
            agent = get_agent()
            prompt = f"[Event {ev.id} context: {ev.model_dump_json()}] Regenerate permission letter as per instruction: {body.regenerate_instruction}. Use generate_permission_letter and generate_onfoot_letter if needed, then upsert."
            agent(prompt)
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
{ev.chairperson or DEFAULT_CHAIRPERSON}

Staff In Charge {ev.org}
{ev.staff_in_charge or DEFAULT_STAFF}

---
This email was generated via CampusOps. For queries, contact {ev.chairperson or DEFAULT_CHAIRPERSON} ({ev.staff_in_charge or DEFAULT_STAFF}) from {ev.org}.
"""

    # Build PDFs
    import os, base64
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication
    from app.pdf import permission_letter_pdf, onfoot_letter_pdf
    faculty_email = FACULTY_EMAIL
    subject = f"Request for permission to host \"{ev.title}\" - {ev.org}"

    mock_mode = MOCK_MODE
    if mock_mode:
        return {"mock": True, "to": faculty_email, "subject": subject, "body_preview": full_body[:400], "event": ev, "note": "MOCK_MODE=true - email not sent. Set false to actually send with PDFs."}

    try:
        from app.google.auth import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        if not creds:
            raise Exception("No credentials")
        service = build("gmail", "v1", credentials=creds)
        msg = MIMEMultipart()
        msg["to"] = faculty_email
        msg["subject"] = subject
        msg.attach(MIMEText(full_body, "plain"))
        # Attach permission letter PDF (only this + onfoot, no announcement PDF)
        if ev.permission_letter:
            pdf_bytes = permission_letter_pdf(ev.permission_letter)
            part = MIMEApplication(pdf_bytes, _subtype="pdf")
            part.add_header("Content-Disposition", "attachment", filename=f"Permission_Letter_{ev.title.replace(' ', '_')}.pdf")
            msg.attach(part)
        # Attach on-foot letter PDF if needed (now guaranteed if need_onfoot)
        if ev.need_onfoot and ev.onfoot_letter:
            pdf_bytes = onfoot_letter_pdf(ev.onfoot_letter)
            part = MIMEApplication(pdf_bytes, _subtype="pdf")
            part.add_header("Content-Disposition", "attachment", filename=f"OnFoot_Publicity_{ev.title.replace(' ', '_')}.pdf")
            msg.attach(part)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        # Update event status to reflect sent
        ev.email_draft = full_body
        ev.status = ev.status  # stay pending_approval until admin approves
        save_event(ev)
        return {"sent": True, "to": faculty_email, "message_id": sent["id"], "subject": subject, "event": ev}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to send email: {e}")

@app.get("/events/{event_id}/registrations")
def get_registrations(event_id: str):
    """Live count without LLM - also auto-syncs Forms responses → Sheet so sheet_link stays live."""
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    if not ev.form_id or ev.form_id.startswith("mock_"):
        # still return stored count for mock forms
        return {"event_id": event_id, "form_id": ev.form_id, "sheet_id": ev.sheet_id, "sheet_link": ev.sheet_link, "count": 0, "mock": True, "note": "Mock form - no live registrations"}
    import json
    from app.tools.registrations import get_registration_count, sync_responses_to_sheet
    # Trigger sync first so sheet_link shows rows automatically
    sync_res = {}
    if ev.sheet_id and not ev.sheet_id.startswith("mock_") and not ev.sheet_id.startswith("sheet_"):
        try:
            sync_res = sync_responses_to_sheet(ev.form_id, ev.sheet_id)
        except Exception as e:
            sync_res = {"synced": False, "error": str(e)}
    raw = get_registration_count(ev.sheet_id or "", ev.form_id or "")
    data = json.loads(raw)
    # also update stored count
    try:
        ev.registrant_count = int(data.get("registrant_count", 0) or 0)
        save_event(ev)
    except:
        pass
    return {"event_id": event_id, "form_id": ev.form_id, "form_link": ev.form_link, "sheet_id": ev.sheet_id, "sheet_link": ev.sheet_link, "count": data.get("registrant_count", 0), "source": data.get("source"), "sync": sync_res, "raw": data}

@app.post("/events/{event_id}/sync")
def sync_event(event_id: str):
    """Force sync Forms responses → Sheet without LLM. Makes sheet_link show registrations."""
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    if not ev.form_id or ev.form_id.startswith("mock_") or not ev.sheet_id or ev.sheet_id.startswith("mock_") or ev.sheet_id.startswith("sheet_"):
        raise HTTPException(400, "Need real form_id and sheet_id - event was mock or sheet not created")
    from app.tools.registrations import sync_responses_to_sheet
    res = sync_responses_to_sheet(ev.form_id, ev.sheet_id)
    return {"event_id": event_id, "sheet_link": ev.sheet_link, "sync": res}

@app.post("/events/{event_id}/reset")
def reset_event(event_id: str):
    """Testing helper: reset event to pending_approval and clear form/sheet so you can re-test approve. No auth."""
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
    fields: Optional[list] = None  # e.g. [{"title":"Phone","type":"text"}, {"title":"Year","type":"multiple_choice","options":["1st","2nd"]}]
    description: Optional[str] = ""

@app.post("/events/{event_id}/form")
def create_form_direct(event_id: str, body: FormCreateRequest):
    """Low-level deterministic form creation - frontend calls this with chip-selected fields (no LLM needed)."""
    ev = get_event(event_id)
    if not ev:
        raise HTTPException(404, "Event not found")
    if ev.status not in [EventStatus.LIVE, EventStatus.PENDING_APPROVAL, EventStatus.ROOM_IDENTIFIED]:
        raise HTTPException(400, f"Event status {ev.status} not ready for form creation. Approve first.")
    import json, os
    from app.tools.forms import create_registration_form as _create_form
    # Strands tool is wrapped; call underlying logic via direct import
    # We invoke the tool's python function by calling it as regular function (tool decorator preserves callable)
    fields_json = json.dumps(body.fields) if body.fields else ""
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

# Helper endpoint to create/update event manually (for testing)
@app.post("/events")
def create_event(ev: Event):
    ev.ensure_id()
    save_event(ev)
    return ev
