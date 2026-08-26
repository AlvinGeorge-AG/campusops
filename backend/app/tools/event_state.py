import json
from strands import tool
from ..state import save_event, get_event, get_latest_event
from ..models import Event, EventStatus

@tool
def upsert_event(org: str, title: str, date: str, expected_headcount: int, room: str = "", room_capacity: int = 0, form_id: str = "", form_link: str = "", sheet_id: str = "") -> str:
    """
    Save or update the current event state. Call this after each major step to persist progress.
    Args:
        org: Organization name e.g. MACS
        title: Event title e.g. Python Workshop
        date: Event date YYYY-MM-DD
        expected_headcount: Expected attendees
        room: Room name if identified
        room_capacity: Room capacity if known
        form_id: Google Form ID if created
        form_link: Google Form link if created
        sheet_id: Sheet ID for responses
    Returns:
        JSON with saved event id and status.
    """
    # Always update the latest event if it exists — approval flow creates duplicate if we branch on status
    latest = get_latest_event()
    if latest:
        ev = latest
    else:
        ev = Event()

    ev.org = org
    ev.title = title
    ev.date = date
    ev.expected_headcount = expected_headcount
    if room:
        ev.room = room
    if room_capacity:
        ev.room_capacity = room_capacity
    if form_id:
        ev.form_id = form_id
    if form_link:
        ev.form_link = form_link
    if sheet_id:
        ev.sheet_id = sheet_id

    # auto-status logic
    if room and not ev.status or ev.status == EventStatus.DRAFT:
        ev.status = EventStatus.ROOM_IDENTIFIED
    if room and not form_id:
        # after room + draft, move to pending approval
        ev.status = EventStatus.PENDING_APPROVAL

    save_event(ev)
    return json.dumps({"event_id": ev.id, "status": ev.status, "room": ev.room, "saved": True})
