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
    # Resolve dynamic org settings - try to find event matching title/date to get correct org (not just latest)
    try:
        from ..state import get_latest_event, get_org_settings, list_events
        org_to_use = None
        # Try to find event by title+date
        for ev in list_events():
            if ev.title == event_title and ev.date == event_date:
                org_to_use = ev.org
                break
        if not org_to_use:
            _ev2 = get_latest_event()
            if _ev2 and _ev2.org:
                org_to_use = _ev2.org
        if org_to_use:
            _s = get_org_settings(org_to_use)
            if _s.announcement_recipients:
                recipients = _s.announcement_recipients
    except:
        pass

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

    # Ensure registration_link is absolute (fix /r/xxx relative bug)
    if registration_link.startswith("/r/"):
        try:
            from ..config import FRONTEND_ORIGIN
            base = (FRONTEND_ORIGIN or "").rstrip("/")
            if base and base != "*" and "localhost" not in base:
                registration_link = f"{base}{registration_link}"
            elif base:
                registration_link = f"{base}{registration_link}"
        except:
            pass

    if mock_mode:
        return f"[MOCK] Announcement prepared for {recipients} | Subject: {subject} | Link: {registration_link}"

    # Prefer Brevo (reliable transactional) over Gmail API
    # Try Brevo first if configured
    brevo_key = os.getenv("BREVO_API_KEY")
    from_email = os.getenv("FROM_EMAIL", "your-email@gmail.com")
    from_name = os.getenv("FROM_NAME", "CampusOps")
    # Ensure dotenv loaded
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
            brevo_key = os.getenv("BREVO_API_KEY", brevo_key)
            from_email = os.getenv("FROM_EMAIL", from_email)
            from_name = os.getenv("FROM_NAME", from_name)
    except:
        pass

    if brevo_key and recipients and "@" in recipients and "example.com" not in recipients:
        try:
            import sib_api_v3_sdk
            from sib_api_v3_sdk.rest import ApiException
            cfg = sib_api_v3_sdk.Configuration()
            cfg.api_key['api-key'] = brevo_key
            api = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(cfg))
            # recipients may be comma-separated
            to_list = [{"email": r.strip()} for r in recipients.split(",") if r.strip() and "@" in r]
            html_body = body.replace("\n", "<br>")
            # Include registration link prominently
            if registration_link not in html_body:
                html_body += f"<br><br><a href='{registration_link}'>Register here: {registration_link}</a>"
            email = sib_api_v3_sdk.SendSmtpEmail(
                to=to_list,
                sender={"email": from_email, "name": from_name},
                subject=subject,
                html_content=f"<div style='font-family:sans-serif; white-space:pre-wrap'>{html_body}</div>"
            )
            resp = api.send_transac_email(email)
            return f"Announcement sent via Brevo to {recipients} with ID {resp.message_id} | Link: {registration_link}"
        except Exception as e:
            # fall through to Gmail
            pass

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
        return f"Announcement sent via Gmail to {recipients} with ID {sent['id']} | Link: {registration_link}"
    except Exception as e:
        return f"[MOCK fallback - Gmail error: {e}] Announcement for {recipients} | {subject} | Link: {registration_link}"
