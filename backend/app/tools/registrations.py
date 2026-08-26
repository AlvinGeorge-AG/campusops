import os
import json
from strands import tool

@tool
def get_registration_count(sheet_id: str) -> str:
    """
    Retrieve current registration count from linked Google Sheet.
    Args:
        sheet_id: Google Sheet ID linked to form responses
    Returns:
        JSON string with count.
    """
    mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"

    # Treat any missing/invalid sheet as mock for demo — Forms API doesn't auto-create a linked Sheet
    if not sheet_id or sheet_id.startswith("mock_") or sheet_id.startswith("sheet_"):
        import random
        count = random.randint(18, 30) if "mock" in sheet_id else 0
        return json.dumps({"sheet_id": sheet_id, "registrant_count": count, "mock": True, "note": "Mock - link a response Sheet to count real registrations"})

    try:
        from ..google.auth import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        if not creds:
            return json.dumps({"sheet_id": sheet_id, "registrant_count": 0, "error": "No credentials"})
        service = build("sheets", "v4", credentials=creds)
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id, range="Sheet1"
        ).execute()
        values = result.get("values", [])
        # subtract header row
        count = max(0, len(values) - 1) if values else 0
        return json.dumps({"sheet_id": sheet_id, "registrant_count": count})
    except Exception as e:
        return json.dumps({"sheet_id": sheet_id, "registrant_count": 0, "error": str(e)})
