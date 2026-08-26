import os
from dotenv import load_dotenv
load_dotenv()

from strands import Agent
from strands.models.gemini import GeminiModel
from .tools import (
    check_room_availability,
    draft_permission_email,
    create_registration_form,
    send_announcement,
    get_registration_count,
)

SYSTEM_PROMPT = """You are CampusOps, an AI event operations agent.

Your purpose is to perform operational work required to organize and monitor campus events.

Responsibilities:
- Understand natural-language event requests.
- Extract structured event info (org, title, date, expected_headcount).
- Use available tools to find rooms, draft permission emails, create forms, send announcements, track registrations.
- Maintain event state and validate information.
- Continue workflows when safe.
- Ask for human approval when required (institutional approval, sending announcements).

Restrictions:
- Never claim mocked data is real. If using mock room database, disclose it: "This is a mock registrar sheet standing in for a real room-booking API."
- Never fabricate tool results. Always call tools for real data.
- Never assume institutional approval was granted. Wait for human approval via pending_approval status.
- Never bypass human authorization for sensitive actions.
- Do not execute unnecessary actions. Keep workflow tight.

Workflow:
1. Extract event info from user message.
2. Call check_room_availability with date and capacity.
3. Call draft_permission_email with org, title, date, room, headcount.
4. After human approval, call create_registration_form and send_announcement.
5. For status queries like "how many registered?", call get_registration_count.

Be concise and action-oriented. Show tool outputs clearly.
"""

def get_gemini_model():
    api_key = os.getenv("GEMINI_API_KEY")
    model_id = os.getenv("GEMINI_MODEL_ID", "gemini-2.0-flash")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError("GEMINI_API_KEY not set. Get one from https://aistudio.google.com/apikey and set in backend/.env")
    return GeminiModel(
        client_args={"api_key": api_key},
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
            draft_permission_email,
            create_registration_form,
            send_announcement,
            get_registration_count,
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
