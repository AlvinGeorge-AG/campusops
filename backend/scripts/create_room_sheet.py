"""Create production Room Sheet in your throwaway Google account.
Usage:
  source .venv/bin/activate
  python scripts/create_room_sheet.py
# Prints Sheet URL to put in .env as ROOM_SHEET_ID
Does NOT consume credentials beyond one Sheets create call.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import csv

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "rooms_production.csv")

def main():
    try:
        from app.google.auth import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        if not creds:
            print("No credentials - run python scripts/auth_google.py first with throwaway account")
            return
        service = build("sheets", "v4", credentials=creds)
        # Create spreadsheet
        spreadsheet = {
            "properties": {"title": "CampusOps - Production Rooms (editable by authorized ppl)"},
            "sheets": [{"properties": {"title": "Rooms"}}]
        }
        created = service.spreadsheets().create(body=spreadsheet).execute()
        sheet_id = created["spreadsheetId"]
        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        print(f"✓ Created: {sheet_url}")
        print(f"  Add to backend/.env: ROOM_SHEET_ID={sheet_id}")

        # Populate with CSV
        with open(CSV_PATH) as f:
            rows = list(csv.reader(f))
        # rows includes header
        body = {"values": rows}
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id, range="Rooms!A1",
            valueInputOption="RAW", body=body
        ).execute()
        print(f"✓ Populated {len(rows)-1} rooms. Share this sheet with authorized editors.")

        # Make header bold (optional)
        try:
            service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={
                "requests": [{
                    "repeatCell": {
                        "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat.textFormat.bold"
                    }
                }]
            }).execute()
        except:
            pass

    except Exception as e:
        print(f"Failed: {e}")
        print("Fallback: manually upload backend/data/rooms_production.csv to Google Sheets and set ROOM_SHEET_ID in .env")

if __name__ == "__main__":
    main()
