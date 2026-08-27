from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
from dotenv import load_dotenv
load_dotenv()

from .agent import get_agent
from .state import save_event, get_event, list_events, get_latest_event, update_event
from .models import Event, EventStatus
import asyncio
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="CampusOps Backend", version="0.1.0")

# --- Optional poller: if POLLER_ENABLED=true, auto-sync Forms→Sheet every 60s without manual Link click ---
_poller_task = None

async def _poll_forms_loop():
    await asyncio.sleep(10)
    while True:
        try:
            if os.getenv("POLLER_ENABLED", "false").lower() != "true" or os.getenv("MOCK_MODE", "false").lower() == "true":
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
    if os.getenv("POLLER_ENABLED", "false").lower() == "true":
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
    return {"status": "ok", "service": "CampusOps Backend", "mock_mode": os.getenv("MOCK_MODE", "false")}

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
    # If this is a new event (no event_id), inject all 1-chat data into prompt so agent generates letters in one go
    if not req.event_id:
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

    # If fields were sent without event_id (first request), persist them to the newly created event
    if req.fields and not req.event_id:
        _latest = get_latest_event()
        if _latest and not _latest.form_fields_json:
            import json as _json2
            _latest.form_fields_json = _json2.dumps(req.fields)
            save_event(_latest)

    # Try to track latest event for response
    latest = get_latest_event()
    return ChatResponse(response=text, event_id=latest.id if latest else None, status=latest.status if latest else None)

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

@app.post("/webhook/form-submit")
def webhook_form_submit(event_id: str, form_id: str = ""):
    """For true instant push: attach this URL as Apps Script onFormSubmit trigger. No polling delay."""
    ev = get_event(event_id) if event_id else None
    fid = form_id or (ev.form_id if ev else "")
    sid = ev.sheet_id if ev else ""
    if not fid or not sid or sid.startswith("mock_") or sid.startswith("sheet_"):
        raise HTTPException(400, "Need real event with form_id+sheet_id")
    from app.tools.registrations import sync_responses_to_sheet
    res = sync_responses_to_sheet(fid, sid)
    return {"synced": True, "event_id": event_id, "sync": res}

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
