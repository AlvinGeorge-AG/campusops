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
    body = f"""Respected Sir/Madam,

{organization} would like to conduct "{event_title}" on {date} in {room}.
Expected headcount: {expected_headcount}
Room capacity verified as suitable.

Kindly grant permission for the same.

Regards,
{organization} - CampusOps (auto-drafted, requires human approval)
"""

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
