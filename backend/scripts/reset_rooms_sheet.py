"""Reset past bookings in rooms_sheet (keep future). Run daily via cron: 0 2 * * * python scripts/reset_rooms_sheet.py"""
import os, sys, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.state import reset_past_bookings

def reset_sheet():
    sheet_id = os.getenv("ROOM_SHEET_ID") or os.getenv("MOCK_ROOM_SHEET_ID")
    today = datetime.date.today().isoformat()
    n = reset_past_bookings(today)
    print(f"DB ledger: removed {n} past bookings before {today}")
    if not sheet_id:
        print("No ROOM_SHEET_ID - sheet reset skipped (DB only)")
        return
    mock = os.getenv("MOCK_MODE","false").lower()=="true"
    if mock:
        print("MOCK_MODE true - sheet reset skipped")
        return
    try:
        from app.google.auth import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        if not creds:
            print("No credentials - sheet reset skipped")
            return
        svc = build("sheets","v4", credentials=creds)
        # Read all rows
        rows = svc.spreadsheets().values().get(spreadsheetId=sheet_id, range="Rooms!A2:H").execute().get("values",[])
        if not rows:
            print("Sheet empty")
            return
        kept = []
        header_kept = False
        removed = 0
        for r in rows:
            if len(r) < 3 or not r[2].strip():
                # base room row (no date) - keep
                kept.append(r)
                continue
            date_val = r[2].strip()
            try:
                # Keep if date >= today (future) - allow today
                if date_val >= today:
                    kept.append(r)
                else:
                    removed += 1
            except:
                kept.append(r)
        if removed == 0:
            print(f"Sheet: no past rows to remove (today {today}, rows {len(rows)})")
            return
        # Clear and rewrite
        svc.spreadsheets().values().clear(spreadsheetId=sheet_id, range="Rooms!A2:H").execute()
        if kept:
            svc.spreadsheets().values().update(spreadsheetId=sheet_id, range="Rooms!A2", valueInputOption="RAW", body={"values": kept}).execute()
        print(f"Sheet: removed {removed} past bookings, kept {len(kept)} rows (today {today})")
    except Exception as e:
        print(f"Sheet reset error: {e}")
        import traceback; traceback.print_exc()

if __name__ == "__main__":
    reset_sheet()
