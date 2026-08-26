import os
import base64
from email.mime.text import MIMEText
from strands import tool

@tool
def draft_permission_email(organization: str, event_title: str, date: str, room: str, expected_headcount: int) -> str:
    """
    Prepare a permission request draft for faculty approval.
    Args:
        organization: Organizer org name e.g. MACS
        event_title: Event title e.g. Python Workshop
        date: Event date YYYY-MM-DD
        room: Room name e.g. LH-302
        expected_headcount: Expected attendees
    Returns:
        Status string with draft id or mock message.
    """
    faculty_email = os.getenv("FACULTY_EMAIL", "faculty@example.com")
    mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"

    subject = f"Permission Request — {organization} {event_title} on {date}"

    # Generate announcement preview that authority can review - will be reused after approval (no regeneration)
    announcement_preview = f"""ANNOUNCEMENT PREVIEW (to be sent to students after approval):
---
Hello,

We are excited to announce: {event_title} by {organization}

Date: {date}
Venue: {room}
Expected: {expected_headcount} students
Registration will open after approval - form link to be attached.

Seats are limited. Please register soon.
- CampusOps
---"""

    body = f"""Respected Sir/Madam,

{organization} would like to conduct "{event_title}" on {date} in {room}.
Expected headcount: {expected_headcount}
Room capacity verified as suitable.

{announcement_preview}

Kindly grant permission for the same. Upon approval, the above announcement will be sent as-is to students.

Regards,
{organization} - CampusOps (auto-drafted, requires human approval)
"""

    # Persist announcement draft for reuse so we don't regenerate
    try:
        from ..state import get_latest_event, save_event
        _ev = get_latest_event()
        if _ev:
            _ev.announcement_draft = announcement_preview
            save_event(_ev)
    except:
        pass

    if mock_mode:
        return f"[MOCK] Draft prepared for {faculty_email} | Subject: {subject} | Body preview: {body[:120]}... | Action: Human must review & send."

    try:
        from ..google.auth import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        if not creds:
            return f"[MOCK - no creds] Draft prepared for {faculty_email} | Subject: {subject}"
        service = build("gmail", "v1", credentials=creds)
        message = MIMEText(body)
        message["to"] = faculty_email
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        draft = service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
        return f"Draft created with ID {draft['id']} for {faculty_email} | Subject: {subject}"
    except Exception as e:
        return f"[MOCK fallback - Gmail error: {e}] Draft prepared for {faculty_email} | Subject: {subject}"
