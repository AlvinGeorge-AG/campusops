import os
import base64
from email.mime.text import MIMEText
from strands import tool

@tool
def send_announcement(event_title: str, event_date: str, room: str, registration_link: str) -> str:
    """
    Send event announcement email.
    Args:
        event_title: Event title
        event_date: Event date YYYY-MM-DD
        room: Room name
        registration_link: Google Form link
    Returns:
        Status string.
    """
    mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"
    recipients = os.getenv("ANNOUNCEMENT_RECIPIENTS", "students@example.com")

    # Reuse announcement draft that was already approved by authority if available
    reused = False
    try:
        from ..state import get_latest_event
        _ev = get_latest_event()
        if _ev and _ev.announcement_draft and "ANNOUNCEMENT PREVIEW" in _ev.announcement_draft:
            # Reuse preview but inject the real registration_link
            body = _ev.announcement_draft.replace("ANNOUNCEMENT PREVIEW (to be sent to students after approval):", "ANNOUNCEMENT (approved):")
            if "Registration will open after approval" in body:
                body = body.replace("Registration will open after approval - form link to be attached.", f"Register here: {registration_link}")
            else:
                body += f"\nRegister here: {registration_link}\n"
            reused = True
        else:
            raise Exception("no draft")
    except:
        if not reused:
            body = f"""Hello,

We are excited to announce: {event_title}

Date: {event_date}
Venue: {room}
Register here: {registration_link}

Seats are limited. Please register soon.

- CampusOps
"""

    subject = f"Announcement: {event_title} on {event_date} - Room {room}"
    if reused:
        subject += " (pre-approved)"

    if mock_mode:
        return f"[MOCK] Announcement prepared for {recipients} | Subject: {subject} | Link: {registration_link}"

    try:
        from ..google.auth import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        if not creds:
            return f"[MOCK - no creds] Announcement for {recipients} | {subject}"
        service = build("gmail", "v1", credentials=creds)
        message = MIMEText(body)
        message["to"] = recipients
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Announcement sent to {recipients} with ID {sent['id']} | Link: {registration_link}"
    except Exception as e:
        return f"[MOCK fallback - Gmail error: {e}] Announcement for {recipients} | {subject} | Link: {registration_link}"
