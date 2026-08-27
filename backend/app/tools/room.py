import os
from strands import tool

# Production room database - fallback when Sheets not configured
# Matches backend/data/rooms_production.csv - authorized ppl can edit the live Sheet anytime
MOCK_ROOMS = [
    {"room": "SDPK", "capacity": 60, "available": True},
    {"room": "Media Hall", "capacity": 120, "available": True},
    {"room": "Fab Lab", "capacity": 40, "available": True},
    {"room": "Internal Auditorium", "capacity": 350, "available": True},
    {"room": "External Auditorium", "capacity": 600, "available": True},
    {"room": "Elga", "capacity": 80, "available": True},
    {"room": "College Ground", "capacity": 2000, "available": True},
    {"room": "College Library", "capacity": 100, "available": True},
    {"room": "Amphitheater", "capacity": 500, "available": True},
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
    # Try real Google Sheets if configured - supports both old MOCK_ROOM_SHEET_ID and new ROOM_SHEET_ID
    if not mock_mode:
        try:
            from ..google.auth import get_credentials
            from googleapiclient.discovery import build
            creds = get_credentials()
            sheet_id = os.getenv("ROOM_SHEET_ID") or os.getenv("MOCK_ROOM_SHEET_ID")
            if creds and sheet_id:
                service = build("sheets", "v4", credentials=creds)
                # Try new format (Room,Capacity,Available) then old format (Room,Capacity,Date,Available)
                for sheet_range in ["Rooms!A2:D", "Sheet1!A2:D"]:
                    try:
                        result = service.spreadsheets().values().get(
                            spreadsheetId=sheet_id, range=sheet_range
                        ).execute()
                        rows = result.get("values", [])
                        if not rows:
                            continue
                        candidates = []
                        for r in rows:
                            if len(r) < 3:
                                continue
                            # New format: Room, Capacity, Available
                            if len(r) == 3 or (len(r) >=3 and r[2].lower() in ["true","false"]):
                                room, cap, avail = r[0], int(r[1]), r[2].lower() == "true"
                                if avail and cap >= capacity:
                                    candidates.append({"room": room, "capacity": cap, "available": True})
                            else:
                                # Old format: Room, Capacity, Date, Available
                                if len(r) < 4:
                                    continue
                                room, cap, d, avail = r[0], int(r[1]), r[2], r[3].lower() == "true"
                                if avail and cap >= capacity and (d.lower() in date.lower() or date.lower() in d.lower() or d == date):
                                    candidates.append({"room": room, "capacity": cap, "available": True})
                        if candidates:
                            best = sorted(candidates, key=lambda x: x["capacity"])[0]
                            best["source"] = "live_sheet"
                            return json.dumps(best)
                    except:
                        continue
                # fallback to mock if no candidate in sheet
        except Exception as e:
            # fall through to mock
            pass

    # Mock lookup (production fallback) - filter by capacity only, availability already True
    candidates = []
    for r in MOCK_ROOMS:
        if r["available"] and r["capacity"] >= capacity:
            candidates.append({**r, "source": "mock_fallback"})

    if not candidates:
        return json.dumps({"error": f"No available room for {capacity} on {date}. Try alternative date/capacity.", "available": False})

    # pick smallest room that fits
    best = sorted(candidates, key=lambda x: x["capacity"])[0]
    return json.dumps({"room": best["room"], "capacity": best["capacity"], "available": True, "source": best.get("source", "mock_fallback")})
