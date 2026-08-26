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

app = FastAPI(title="CampusOps Backend", version="0.1.0")

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
    fields: Optional[list] = None  # 1-request: collect form fields upfront e.g. [{"title":"Phone","type":"text"}]
    description: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    event_id: Optional[str] = None
    status: Optional[str] = None

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

    # If fields provided in this 1-request, persist upfront so approval reuse works
    if req.fields and req.event_id:
        _ev = get_event(req.event_id)
        if _ev:
            import json as _json
            _ev.form_fields_json = _json.dumps(req.fields)
            save_event(_ev)
            # also refresh context that will be injected below
    elif req.fields and not req.event_id:
        # No event yet: stash fields to inject into prompt so agent's upsert captures them
        import json as _json
        context_fields = f"\n[User selected form fields upfront (1-request): {_json.dumps(req.fields)} - agent must pass this as fields_json to create_registration_form and also save via upsert_event form_fields_json.]\n"
        date_context += context_fields

    # Load context if event_id provided
    context = ""
    if req.event_id:
        ev = get_event(req.event_id)
        if ev:
            # inject stored fields if event already has them
            extra = ""
            if ev.form_fields_json and not req.fields:
                extra = f"\n[Stored form fields for this event: {ev.form_fields_json}]\n"
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
