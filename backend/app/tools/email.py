import os
import base64
from email.mime.text import MIMEText
from strands import tool
from ..config import FACULTY_EMAIL, DEFAULT_CHAIRPERSON, DEFAULT_STAFF, MOCK_MODE

@tool
def draft_permission_email(organization: str, event_title: str, date: str, room: str, expected_headcount: int, 
                           start_time: str = "", end_time: str = "", speaker: str = "", purpose: str = "",
                           chairperson: str = "", staff_in_charge: str = "") -> str:
    """
    Prepare a permission request draft for faculty approval.
    Args:
        organization: Organizer org name e.g. MACS
        event_title: Event title e.g. Python Workshop
        date: Event date YYYY-MM-DD
        room: Room name e.g. LH-302
        expected_headcount: Expected attendees
        start_time: Event start time e.g. 3:30 PM
        end_time: Event end time e.g. 4:30 PM
        speaker: Speaker name and details e.g. "Dr. John Doe (Alumni)"
        purpose: Detailed purpose/description of the event
        chairperson: Chairperson name for signature
        staff_in_charge: Staff in charge name for signature
    Returns:
        Status string with draft id or mock message.
    """
    # Resolve dynamic org settings: faculty_email / chairperson / staff per club
    faculty_email = FACULTY_EMAIL
    try:
        from ..state import get_org_settings
        _s = get_org_settings(organization)
        if _s.faculty_email:
            faculty_email = _s.faculty_email
        if not chairperson and _s.chairperson:
            chairperson = _s.chairperson
        if not staff_in_charge and _s.staff_in_charge:
            staff_in_charge = _s.staff_in_charge
    except:
        pass
    mock_mode = MOCK_MODE

    subject = f"Permission Request — {organization} {event_title} on {date}"

    # Generate announcement preview that authority can review - will be reused after approval (no regeneration)
    announcement_preview = f"""ANNOUNCEMENT PREVIEW (to be sent to students after approval):
---
Hello,

We are excited to announce: {event_title} by {organization}

Date: {date}
Venue: {room}
{f"Time: {start_time} - {end_time}" if start_time and end_time else ""}
Expected: {expected_headcount} students
{f"Speaker: {speaker}" if speaker else ""}
Registration will open after approval - form link to be attached.

Seats are limited. Please register soon.
- CampusOps
---"""

    # Build detailed email body
    time_info = f"{start_time} to {end_time}" if start_time and end_time else "TBD"
    speaker_info = f"\nSpeaker: {speaker}" if speaker else ""
    purpose_info = f"\n\nPurpose:\n{purpose}" if purpose else ""
    
    body = f"""Respected Sir/Madam,

I hope you are well. On behalf of {organization}, I am writing to seek your kind permission to host "{event_title}" on {date}.

Event Details:
Date: {date}
Time: {time_info}
Venue: {room}
Expected Headcount: {expected_headcount}
Room Capacity: Verified as suitable{speaker_info}{purpose_info}

{announcement_preview}

Please find attached the detailed permission letter (PDF) for your review. Kindly grant permission for the same. Upon approval, the above announcement will be sent as-is to students.

We would be grateful for your approval. Thank you for your continued support.

With regards,
Chairperson {organization}
{chairperson or DEFAULT_CHAIRPERSON}

Staff In Charge {organization}
{staff_in_charge or DEFAULT_STAFF}

---
This email was generated via CampusOps. For queries, contact {chairperson or DEFAULT_CHAIRPERSON} ({staff_in_charge or DEFAULT_STAFF}) from {organization}.
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
