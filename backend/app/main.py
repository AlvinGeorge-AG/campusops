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
        return {"message": "Approved. Agent can now create registration form and send announcement.", "event": ev}
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

    # Load context if event_id provided
    context = ""
    if req.event_id:
        ev = get_event(req.event_id)
        if ev:
            context = f"\n[Current Event Context: {ev.model_dump_json()}]\n"

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

    # Try to track latest event for response
    latest = get_latest_event()
    return ChatResponse(response=text, event_id=latest.id if latest else None, status=latest.status if latest else None)

# Helper endpoint to create/update event manually (for testing)
@app.post("/events")
def create_event(ev: Event):
    ev.ensure_id()
    save_event(ev)
    return ev
