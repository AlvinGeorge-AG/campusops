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

def _parse_time(t: str) -> int:
    """Parse '3:30 PM' or '15:30' to minutes since midnight for overlap check."""
    if not t:
        return -1
    t = t.strip().lower()
    try:
        # Handle 3:30 pm
        if "am" in t or "pm" in t:
            import datetime as _dt
            # normalize
            t = t.replace(" ", "")
            # 3:30pm
            dt = _dt.datetime.strptime(t, "%I:%M%p")
            return dt.hour * 60 + dt.minute
        # Handle 15:30
        if ":" in t:
            h, m = t.split(":")
            return int(h) * 60 + int(m)
    except:
        return -1
    return -1

def _overlap(s1, e1, s2, e2):
    if s1 == -1 or e1 == -1 or s2 == -1 or e2 == -1:
        return True  # if no time, assume overlap (whole day blocked)
    return max(s1, s2) < min(e1, e2)

@tool
def check_room_availability(date: str, capacity: int, start_time: str = "", end_time: str = "") -> str:
    """
    Find a suitable room for the requested event date/time and capacity.
    Args:
        date: Event date as YYYY-MM-DD
        capacity: Expected headcount (int)
        start_time: Start time like 3:30 PM (optional)
        end_time: End time like 4:30 PM (optional)
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
                # New manual-friendly format: Room,Capacity,Date,Start,End,Available,Booked By,Notes
                # Also supports old formats for backward compat
                for sheet_range in ["Rooms!A2:H", "Rooms!A2:D", "Sheet1!A2:H", "Sheet1!A2:D"]:
                    try:
                        result = service.spreadsheets().values().get(
                            spreadsheetId=sheet_id, range=sheet_range
                        ).execute()
                        rows = result.get("values", [])
                        if not rows:
                            continue
                        # Separate base rooms and bookings
                        base_rooms = {}  # room -> capacity
                        bookings = []  # list of {room, date, start, end}
                        for r in rows:
                            if len(r) < 2:
                                continue
                            room = r[0].strip() if len(r) > 0 else ""
                            cap_str = r[1].strip() if len(r) > 1 else "0"
                            try:
                                cap = int(cap_str)
                            except:
                                continue
                            # New 8-col: check if Date col present
                            date_val = r[2].strip() if len(r) > 2 else ""
                            start_val = r[3].strip() if len(r) > 3 else ""
                            end_val = r[4].strip() if len(r) > 4 else ""
                            avail_str = r[5].strip().lower() if len(r) > 5 else (r[2].strip().lower() if len(r) <= 4 else "")
                            booked_by = r[6].strip() if len(r) > 6 else ""
                            # Determine if this is a booking row (has date and Available FALSE)
                            is_booking = date_val and avail_str == "false"
                            if is_booking:
                                bookings.append({"room": room, "date": date_val, "start": start_val, "end": end_val, "booked_by": booked_by})
                            else:
                                # Base room definition: Available TRUE or no date
                                avail = avail_str == "true" if avail_str in ["true","false"] else True
                                if avail:
                                    # Keep smallest capacity if duplicate
                                    if room not in base_rooms or cap < base_rooms[room]:
                                        base_rooms[room] = cap
                            # Handle old 3-col/4-col fallback where avail is in col 2
                            if len(r) == 3 and r[2].lower() in ["true","false"] and room not in base_rooms:
                                if r[2].lower() == "true":
                                    base_rooms[room] = cap
                        # Now find candidates that are not booked for requested date/time
                        req_s = _parse_time(start_time)
                        req_e = _parse_time(end_time)
                        candidates = []
                        for room, cap in base_rooms.items():
                            if cap < capacity:
                                continue
                            # Check if any booking for this room/date/time overlaps
                            conflict = False
                            for b in bookings:
                                if b["room"].lower() != room.lower():
                                    continue
                                if b["date"] != date:
                                    continue
                                b_s = _parse_time(b["start"])
                                b_e = _parse_time(b["end"])
                                if _overlap(req_s, req_e, b_s, b_e):
                                    conflict = True
                                    break
                            if not conflict:
                                candidates.append({"room": room, "capacity": cap, "available": True})
                        if candidates:
                            best = sorted(candidates, key=lambda x: x["capacity"])[0]
                            best["source"] = "live_sheet"
                            return json.dumps(best)
                    except Exception as inner_e:
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

@tool
def book_room_slot(room: str, date: str, start_time: str, end_time: str, event_id: str) -> str:
    """Book a room for a specific date/time slot by writing to the live Sheet. Call after room is selected."""
    import json as _json
    sheet_id = os.getenv("ROOM_SHEET_ID") or os.getenv("MOCK_ROOM_SHEET_ID")
    if not sheet_id or os.getenv("MOCK_MODE", "false").lower() == "true":
        return _json.dumps({"booked": False, "reason": "mock_mode or no sheet", "room": room})
    try:
        from ..google.auth import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        if not creds:
            return _json.dumps({"booked": False, "reason": "no credentials"})
        service = build("sheets", "v4", credentials=creds)
        # Append a booking row: Room,Capacity,Date,Start,End,Available=FALSE,Booked By,Notes
        # Need capacity - fetch from base rooms
        # For simplicity, use MOCK_ROOMS capacity or fetch from sheet
        cap = next((r["capacity"] for r in MOCK_ROOMS if r["room"].lower() == room.lower()), 60)
        # Try to get real capacity from sheet
        try:
            res = service.spreadsheets().values().get(spreadsheetId=sheet_id, range="Rooms!A2:B").execute()
            for r in res.get("values", []):
                if r[0].lower() == room.lower() and len(r) > 1:
                    cap = int(r[1])
                    break
        except:
            pass
        row = [room, str(cap), date, start_time or "", end_time or "", "FALSE", event_id, f"Booked for {event_id}"]
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id, range="Rooms!A:H",
            valueInputOption="RAW",
            body={"values": [row]}
        ).execute()
        return _json.dumps({"booked": True, "room": room, "date": date, "start": start_time, "end": end_time, "event_id": event_id})
    except Exception as e:
        return _json.dumps({"booked": False, "error": str(e)})
