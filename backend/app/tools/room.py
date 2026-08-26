import os
from strands import tool

# Mock room database - same as CampsOps-System-Design.md:910
MOCK_ROOMS = [
    {"room": "LH-101", "capacity": 60, "date": "Saturday", "available": False},
    {"room": "LH-201", "capacity": 75, "date": "Saturday", "available": True},
    {"room": "LH-302", "capacity": 100, "date": "Saturday", "available": True},
    {"room": "Seminar Hall", "capacity": 150, "date": "Saturday", "available": False},
    {"room": "LH-101", "capacity": 60, "date": "2026-08-29", "available": True},
    {"room": "LH-201", "capacity": 75, "date": "2026-08-29", "available": True},
    {"room": "LH-302", "capacity": 100, "date": "2026-08-29", "available": True},
]

@tool
def check_room_availability(date: str, capacity: int) -> str:
    """
    Find a suitable room for the requested event date and capacity.
    Args:
        date: Event date as YYYY-MM-DD or day name like Saturday
        capacity: Expected headcount (int)
    Returns:
        JSON string with room suggestion or no-room message.
    """
    import json

    mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"
    # Try real Google Sheets if not mock
    if not mock_mode:
        try:
            from ..google.auth import get_credentials
            from googleapiclient.discovery import build
            creds = get_credentials()
            sheet_id = os.getenv("MOCK_ROOM_SHEET_ID")
            if creds and sheet_id:
                service = build("sheets", "v4", credentials=creds)
                result = service.spreadsheets().values().get(
                    spreadsheetId=sheet_id, range="Sheet1!A2:D"
                ).execute()
                rows = result.get("values", [])
                candidates = []
                for r in rows:
                    if len(r) < 4:
                        continue
                    room, cap, d, avail = r[0], int(r[1]), r[2], r[3].lower() == "true"
                    if avail and cap >= capacity and (d.lower() in date.lower() or date.lower() in d.lower() or d == date):
                        candidates.append({"room": room, "capacity": cap, "available": True})
                if candidates:
                    best = sorted(candidates, key=lambda x: x["capacity"])[0]
                    return json.dumps(best)
                # fallback to mock if no candidate in sheet
        except Exception as e:
            # fall through to mock
            pass

    # Mock lookup
    candidates = []
    for r in MOCK_ROOMS:
        # match date loosely
        date_match = r["date"].lower() in date.lower() or date.lower() in r["date"].lower()
        if r["available"] and r["capacity"] >= capacity and date_match:
            candidates.append(r)
    # also try any date if no exact match
    if not candidates:
        for r in MOCK_ROOMS:
            if r["available"] and r["capacity"] >= capacity:
                candidates.append(r)

    if not candidates:
        return json.dumps({"error": f"No available room for {capacity} on {date}. Try alternative date/capacity.", "available": False})

    # pick smallest room that fits
    best = sorted(candidates, key=lambda x: x["capacity"])[0]
    return json.dumps({"room": best["room"], "capacity": best["capacity"], "available": True})
