import os
from dotenv import load_dotenv
load_dotenv()

from strands import Agent
from strands.models.gemini import GeminiModel
from google.genai.types import HttpOptions
from .tools import (
    check_room_availability,
    draft_permission_email,
    create_registration_form,
    send_announcement,
    get_registration_count,
)
from .tools.room import book_room_slot
from .tools.letters import generate_permission_letter, generate_onfoot_letter, generate_announcement_preview
from .tools.event_state import upsert_event
from .config import GEMINI_MODEL_ID, GEMINI_TIMEOUT_MS

def _build_system_prompt():
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    weekday = datetime.now().strftime("%A")
    return f"""You are CampusOps, an AI event operations agent.

Today is {today} ({weekday}). Use this as the reference for all relative dates like "next Saturday" or "tomorrow". Always resolve to YYYY-MM-DD format based on TODAY.

Your purpose is to perform operational work required to organize and monitor campus events.

Responsibilities:
- Understand natural-language event requests.
- Extract structured event info (org, title, date, expected_headcount).
- Use available tools to find rooms, draft permission emails, create forms, send announcements, track registrations.
- Maintain event state and validate information.
- Continue workflows when safe.
- Ask for human approval when required (institutional approval, sending announcements).

Restrictions:
- Never claim mocked data is real. If check_room_availability returns "source":"mock_fallback", disclose: "This is a mock registrar sheet standing in for a real room-booking API." If source is "live_sheet", say "Room data from live Google Sheet (production)."
- Never fabricate tool results. Always call tools for real data.
- Never assume institutional approval was granted. Wait for human approval via pending_approval status.
- Never bypass human authorization for sensitive actions.
- Do not execute unnecessary actions. Keep workflow tight.

Workflow (1-chat heart - collect all upfront):
1. Extract event info from user message + 1-chat heart metadata (start_time, end_time, speaker, purpose, chairperson, staff_in_charge, need_onfoot, fields). Resolve date to YYYY-MM-DD using TODAY={today}.
2. Call check_room_availability with date, capacity, start_time, end_time.
3. If a room is found, IMMEDIATELY call book_room_slot with room, date, start_time, end_time, event_id (from placeholder id in context) to lock the time slot in the live Sheet (manual-friendly: adds row Room,Capacity,Date,Start,End,FALSE,event_id).
4. Generate high-quality letters: call generate_permission_letter with org, title, date, start_time, end_time, room, speaker, purpose, chairperson, staff_in_charge. If need_onfoot is true, also call generate_onfoot_letter with same args. Also call generate_announcement_preview.
5. IMMEDIATELY after steps 2-4, call upsert_event to persist the event (include org, title, date, headcount, room, start_time, end_time, speaker, purpose, need_onfoot, form_fields_json). The permission/onfoot letters are auto-saved by the tools.
6. SHOW the generated permission letter (+ onfoot if needed) and announcement preview to the club in your reply - do NOT send email yet. Say: "Here is the draft email for principal - edit manually or tell me 'make more formal' to regenerate, then call /send-permission-email."
7. After club confirms via POST /events/{id}/send-permission-email (with edited text or regenerate instruction), that endpoint sends the email with PDFs attached to principal.
8. After human (principal) approval via POST /events/{id}/approve, call create_registration_form (with stored fields_json) and send_announcement (reusing draft), then upsert_event again with form details (including sheet_link).

Form field handling (non-deterministic, depends on event type):
- If user hasn't specified what responder data to collect, ASK FIRST with quick options before creating form.
  Example: "What should the registration form collect? Tap to select: [Name] [Email] [Class] [Section] [Phone] [Year] [Department] [Expectations - paragraph] [File upload] - or type custom fields."
- Frontend will send back fields_json like '[{{"title": "Full Name", "type": "text"}}, {{"title": "Phone", "type": "text"}}]'
- Pass that fields_json to create_registration_form. Types: text, paragraph, multiple_choice, checkbox, file_upload.
- If no fields specified, defaults to Name+Email are used. File uploads use file_upload type.

Be concise and action-oriented. Show tool outputs clearly.
"""

SYSTEM_PROMPT = _build_system_prompt()

def get_gemini_model():
    api_key = os.getenv("GEMINI_API_KEY")
    model_id = GEMINI_MODEL_ID
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError("GEMINI_API_KEY not set. Get one from https://aistudio.google.com/apikey and set in backend/.env")
    return GeminiModel(
        client_args={
            "api_key": api_key,
            "http_options": HttpOptions(timeout=GEMINI_TIMEOUT_MS),
        },
        model_id=model_id,
        params={"temperature": 0.4}
    )

def create_agent():
    model = get_gemini_model()
    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[
            check_room_availability,
            book_room_slot,
            generate_permission_letter,
            generate_onfoot_letter,
            generate_announcement_preview,
            draft_permission_email,  # legacy, keep for fallback
            create_registration_form,
            send_announcement,
            get_registration_count,
            upsert_event,
        ]
    )
    return agent

# Singleton for FastAPI
_agent = None
def get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent()
    return _agent
