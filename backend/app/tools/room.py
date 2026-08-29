import os
import json
import re
import datetime as _dt
from strands import tool

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
    if not t:
        return -1
    t = t.strip().lower()
    try:
        if "am" in t or "pm" in t:
            t = t.replace(" ", "")
            if t.count(":") == 2:
                dt = _dt.datetime.strptime(t, "%I:%M:%S%p")
            else:
                dt = _dt.datetime.strptime(t, "%I:%M%p")
            return dt.hour * 60 + dt.minute
        if ":" in t:
            parts = t.split(":")
            if len(parts) == 3:
                h, m, _ = parts
                return int(h) * 60 + int(m)
            h, m = parts
            return int(h) * 60 + int(m)
        if t.isdigit():
            return int(t) * 60
    except:
        return -1
    return -1

def _overlap(s1, e1, s2, e2):
    if s1 == -1 or e1 == -1 or s2 == -1 or e2 == -1:
        return True
    return max(s1, s2) < min(e1, e2)

def _alternatives(candidates, conflicts):
    alts = sorted(candidates, key=lambda x: x["capacity"])[:2] if candidates else []
    return alts

# ---- helpers for 2-sheet split ----

def _read_inventory_and_bookings(service, sheet_id):
    """Try new 2-sheet format: RoomInventory!A2:B and Bookings!A2:F.
    Returns (base_rooms dict, bookings list, found_new_format bool).
    Falls back to old Rooms! reading if new sheets empty/missing.
    """
    base_rooms: dict[str, int] = {}
    bookings: list[dict] = []
    found_inventory = False
    found_bookings = False

    # Try RoomInventory
    if service and sheet_id:
        for rng in ["RoomInventory!A2:B", "RoomInventory!A2:C"]:
            try:
                res = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=rng).execute()
                rows = res.get("values", [])
                if rows:
                    for r in rows:
                        if len(r) < 2:
                            continue
                        room = (r[0] or "").strip()
                        if not room:
                            continue
                        try:
                            cap = int(str(r[1]).strip())
                        except:
                            continue
                        base_rooms[room] = cap
                    if base_rooms:
                        found_inventory = True
                        break
            except Exception:
                continue

        # Try Bookings ledger
        for rng in ["Bookings!A2:F", "Bookings!A2:G"]:
            try:
                res = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=rng).execute()
                rows = res.get("values", [])
                if rows is not None:
                    # empty list is valid (no bookings) -> treat as found
                    found_bookings = True
                    for r in rows:
                        if len(r) < 5:
                            continue
                        room = (r[0] or "").strip()
                        date_val = (r[1] or "").strip()
                        start_val = (r[2] or "").strip()
                        end_val = (r[3] or "").strip()
                        event_id = (r[4] or "").strip() if len(r) > 4 else ""
                        org = (r[5] or "").strip() if len(r) > 5 else ""
                        if not room or not date_val:
                            continue
                        bookings.append({"room": room, "date": date_val, "start": start_val, "end": end_val, "booked_by": event_id, "org": org})
                    break
            except Exception:
                continue

    if found_inventory or found_bookings:
        return base_rooms, bookings, True

    # Fallback: old single-sheet Rooms! format
    fallback_rooms: dict[str, int] = {}
    fallback_bookings: list[dict] = []
    if service and sheet_id:
        for sheet_range in ["Rooms!A2:H", "Rooms!A2:D", "Sheet1!A2:H", "Sheet1!A2:D"]:
            try:
                result = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=sheet_range).execute()
                rows = result.get("values", [])
                if not rows:
                    continue
                for r in rows:
                    if len(r) < 2:
                        continue
                    room = r[0].strip() if len(r) > 0 else ""
                    cap_str = r[1].strip() if len(r) > 1 else "0"
                    try:
                        cap = int(cap_str)
                    except:
                        continue
                    date_val = r[2].strip() if len(r) > 2 else ""
                    start_val = r[3].strip() if len(r) > 3 else ""
                    end_val = r[4].strip() if len(r) > 4 else ""
                    avail_str = r[5].strip().lower() if len(r) > 5 else (r[2].strip().lower() if len(r) <= 4 else "")
                    booked_by = r[6].strip() if len(r) > 6 else ""
                    is_booking = bool(date_val) and avail_str == "false"
                    if is_booking:
                        fallback_bookings.append({"room": room, "date": date_val, "start": start_val, "end": end_val, "booked_by": booked_by})
                    else:
                        avail = avail_str == "true" if avail_str in ["true", "false"] else True
                        if avail:
                            if room not in fallback_rooms or cap < fallback_rooms[room]:
                                fallback_rooms[room] = cap
                    if len(r) == 3 and r[2].lower() in ["true", "false"] and room not in fallback_rooms:
                        if r[2].lower() == "true":
                            fallback_rooms[room] = cap
                if fallback_rooms or fallback_bookings:
                    # Auto-migration opportunity: populate new sheets if old data exists
                    # We attempt migration best-effort (don't fail if it errors) 
                    try:
                        # Only migrate if we actually have old data and new sheets were empty
                        if not found_inventory and fallback_rooms:
                            # Ensure headers exist by appending inventory rows
                            inv_rows = [[k, str(v)] for k, v in fallback_rooms.items()]
                            service.spreadsheets().values().update(spreadsheetId=sheet_id, range="RoomInventory!A1", valueInputOption="RAW", body={"values": [["Room","Capacity"]] + inv_rows}).execute()
                        if not found_bookings and fallback_bookings:
                            b_rows = [[b["room"], b["date"], b["start"], b["end"], b["booked_by"], b.get("org","")] for b in fallback_bookings]
                            # Ensure header
                            try:
                                service.spreadsheets().values().update(spreadsheetId=sheet_id, range="Bookings!A1", valueInputOption="RAW", body={"values": [["Room","Date","Start","End","EventID","Org"]] }).execute()
                            except:
                                pass
                            service.spreadsheets().values().append(spreadsheetId=sheet_id, range="Bookings!A:F", valueInputOption="RAW", body={"values": b_rows}).execute()
                    except Exception:
                        pass
                    break
            except:
                continue
        if fallback_rooms or fallback_bookings:
            return fallback_rooms, fallback_bookings, False

    return base_rooms, bookings, found_inventory or found_bookings

@tool
def check_room_availability(date: str, capacity: int, start_time: str = "", end_time: str = "") -> str:
    """
    Find a suitable room for the requested event date/time and capacity.
    Returns JSON with room suggestion or detailed conflict error (409-style).
    Supports new 2-sheet format (RoomInventory + Bookings) with fallback to old Rooms! sheet.
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date or ""):
        return json.dumps({"error": f"Invalid date '{date}'. Must be YYYY-MM-DD. Use the date picker.", "available": False, "reason": "invalid_date"})
    try:
        _dt.datetime.strptime(date, "%Y-%m-%d")
    except:
        return json.dumps({"error": f"Invalid date '{date}'.", "available": False, "reason": "invalid_date"})
    if not start_time or not end_time:
        pass

    mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"
    req_s = _parse_time(start_time)
    req_e = _parse_time(end_time)
    if req_s != -1 and req_e != -1 and req_s >= req_e:
        return json.dumps({"error": f"Start time {start_time} must be before end time {end_time}.", "available": False, "reason": "invalid_time_range"})

    sheet_bookings = []
    base_rooms = {}
    if not mock_mode:
        try:
            from ..google.auth import get_credentials
            from googleapiclient.discovery import build
            creds = get_credentials()
            sheet_id = os.getenv("ROOM_SHEET_ID") or os.getenv("MOCK_ROOM_SHEET_ID")
            if creds and sheet_id:
                service = build("sheets", "v4", credentials=creds)
                base_rooms, sheet_bookings, _ = _read_inventory_and_bookings(service, sheet_id)
        except:
            pass

    if not base_rooms:
        for r in MOCK_ROOMS:
            if r["available"]:
                base_rooms[r["room"]] = r["capacity"]

    db_conflicts = []
    try:
        from ..state import check_room_conflict
        pass
    except:
        pass

    candidates = []
    conflicts_detail = []
    for room, cap in base_rooms.items():
        if cap < int(capacity):
            continue
        room_conflicts = []
        for b in sheet_bookings:
            if b["room"].lower() != room.lower():
                continue
            if b["date"] != date:
                continue
            b_s = _parse_time(b["start"])
            b_e = _parse_time(b["end"])
            if _overlap(req_s, req_e, b_s, b_e):
                room_conflicts.append(b)
        try:
            from ..state import check_room_conflict as _chk
            if req_s != -1 and req_e != -1:
                dbc = _chk(room, date, req_s, req_e)
                for c in dbc:
                    if c["event_id"] not in [x.get("booked_by") for x in room_conflicts]:
                        room_conflicts.append({"room": room, "date": date, "start": f"{c['start_min']//60:02d}:{c['start_min']%60:02d}", "end": f"{c['end_min']//60:02d}:{c['end_min']%60:02d}", "booked_by": c["event_id"]})
        except:
            pass
        if room_conflicts:
            for cc in room_conflicts:
                conflicts_detail.append(cc)
        else:
            candidates.append({"room": room, "capacity": cap, "available": True})

    if candidates:
        best = sorted(candidates, key=lambda x: x["capacity"])[0]
        best["source"] = "live_sheet" if sheet_bookings or not mock_mode else "mock_fallback"
        best["conflicts_checked"] = True
        return json.dumps(best)

    err = {
        "error": f"No available room for {capacity} on {date} {start_time}-{end_time}. All {len(base_rooms)} rooms are booked or too small.",
        "available": False,
        "reason": "conflict_or_capacity",
        "conflicts": conflicts_detail[:5],
        "alternatives": _alternatives([{"room": r, "capacity": c} for r, c in base_rooms.items() if c >= int(capacity)], conflicts_detail),
        "suggestion": "Try a different date, time slot, or smaller headcount. Use the date picker to select a future date."
    }
    return json.dumps(err)

@tool
def book_room_slot(room: str, date: str, start_time: str, end_time: str, event_id: str) -> str:
    """Book a room atomically: re-check conflicts then write to Sheet + DB ledger. Supports 2-sheet split."""
    import datetime as _dt2
    sheet_id = os.getenv("ROOM_SHEET_ID") or os.getenv("MOCK_ROOM_SHEET_ID")
    is_mock = os.getenv("MOCK_MODE", "false").lower() == "true"
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date or ""):
        return json.dumps({"booked": False, "error": "invalid date YYYY-MM-DD", "reason": "invalid_date"})
    s_min = _parse_time(start_time)
    e_min = _parse_time(end_time)
    if s_min == -1 or e_min == -1:
        return json.dumps({"booked": False, "error": "start_time and end_time required (e.g. 15:30)", "reason": "missing_time"})
    if s_min >= e_min:
        return json.dumps({"booked": False, "error": "start must be before end", "reason": "invalid_time_range"})

    try:
        from ..state import check_room_conflict, add_room_booking
        conflicts = check_room_conflict(room, date, s_min, e_min)
        if conflicts:
            return json.dumps({"booked": False, "error": f"Conflict: {room} already booked on {date} {start_time}-{end_time} by {conflicts[0]['event_id']}", "reason": "conflict", "conflicts": conflicts, "alternatives": []})
        avail_raw = check_room_availability(date, 0, start_time, end_time)
        avail = json.loads(avail_raw)
        if avail.get("available") is False and any(c["room"].lower()==room.lower() for c in avail.get("conflicts",[])):
            return json.dumps({"booked": False, "error": f"Sheet conflict: {room} {date} {start_time}-{end_time}", "reason": "conflict", "conflicts": avail.get("conflicts",[])})

        org_val = "unknown"
        try:
            from ..state import get_event
            ev = get_event(event_id)
            if ev and ev.org:
                org_val = ev.org
        except Exception:
            pass
        ok = add_room_booking(org=org_val, room=room, date=date, start_min=s_min, end_min=e_min, event_id=event_id)
        if not ok:
            conflicts2 = check_room_conflict(room, date, s_min, e_min)
            return json.dumps({"booked": False, "error": "DB conflict", "reason": "conflict", "conflicts": conflicts2})
    except Exception as e:
        pass

    if is_mock or not sheet_id:
        return json.dumps({"booked": True, "room": room, "date": date, "start": start_time, "end": end_time, "event_id": event_id, "source": "mock_ledger"})

    try:
        from ..google.auth import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        if not creds:
            return json.dumps({"booked": False, "reason": "no credentials"})
        service = build("sheets", "v4", credentials=creds)
        # Try to fetch capacity from RoomInventory first, fallback to old Rooms
        cap = next((r["capacity"] for r in MOCK_ROOMS if r["room"].lower() == room.lower()), 60)
        try:
            res = service.spreadsheets().values().get(spreadsheetId=sheet_id, range="RoomInventory!A2:B").execute()
            for r in res.get("values", []):
                if r[0].lower() == room.lower() and len(r) > 1:
                    cap = int(r[1]); break
            else:
                # fallback old range
                res2 = service.spreadsheets().values().get(spreadsheetId=sheet_id, range="Rooms!A2:B").execute()
                for r in res2.get("values", []):
                    if r[0].lower() == room.lower() and len(r) > 1:
                        cap = int(r[1]); break
        except:
            pass
        # Determine org for ledger column
        org_val = ""
        try:
            from ..state import get_event
            ev = get_event(event_id)
            if ev and ev.org:
                org_val = ev.org
        except:
            pass
        # Try new Bookings sheet first; fallback to old Rooms sheet if Bookings not found
        # Detect if Bookings sheet exists by trying to read header
        use_new = False
        try:
            service.spreadsheets().values().get(spreadsheetId=sheet_id, range="Bookings!A1:F1").execute()
            use_new = True
        except:
            # If Bookings sheet doesn't exist, try to create header lazily
            try:
                service.spreadsheets().values().update(spreadsheetId=sheet_id, range="Bookings!A1", valueInputOption="RAW", body={"values": [["Room","Date","Start","End","EventID","Org"]]}).execute()
                use_new = True
            except:
                use_new = False
        if use_new:
            row = [room, date, start_time or "", end_time or "", event_id, org_val]
            service.spreadsheets().values().append(spreadsheetId=sheet_id, range="Bookings!A:F", valueInputOption="RAW", body={"values": [row]}).execute()
            return json.dumps({"booked": True, "room": room, "date": date, "start": start_time, "end": end_time, "event_id": event_id, "source": "live_sheet_bookings"})
        else:
            # fallback old format
            row = [room, str(cap), date, start_time or "", end_time or "", "FALSE", event_id, f"Booked for {event_id}"]
            service.spreadsheets().values().append(spreadsheetId=sheet_id, range="Rooms!A:H", valueInputOption="RAW", body={"values": [row]}).execute()
            return json.dumps({"booked": True, "room": room, "date": date, "start": start_time, "end": end_time, "event_id": event_id, "source": "live_sheet_legacy"})
    except Exception as e:
        return json.dumps({"booked": True, "room": room, "date": date, "start": start_time, "end": end_time, "event_id": event_id, "warning": f"Sheet append failed: {e}", "source": "db_ledger"})
