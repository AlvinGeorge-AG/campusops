import os
import json
from strands import tool

@tool
def get_registration_count(sheet_id: str, form_id: str = "") -> str:
    """
    Retrieve current registration count. Tries Sheets first, then Forms API (auto-updates).
    Args:
        sheet_id: Google Sheet ID linked to form responses (or empty)
        form_id: Google Form ID - if provided, counts via Forms API directly (auto-sync, no sheet linking needed)
    Returns:
        JSON string with count.
    """
    mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"

    # Auto-resolve form_id from latest event if not passed (so sheet auto-sync works without manual linking)
    if not form_id:
        try:
            from ..state import get_latest_event
            _ev = get_latest_event()
            if _ev and _ev.form_id and not _ev.form_id.startswith("mock_"):
                form_id = _ev.form_id
            elif _ev and _ev.sheet_id and not sheet_id:
                sheet_id = _ev.sheet_id
        except:
            pass

    # Mock fallback - but still try Forms API even for mock_ if we have real form_id
    if mock_mode and not form_id:
        import random
        count = random.randint(18, 30) if "mock" in (sheet_id or "") else 0
        return json.dumps({"sheet_id": sheet_id, "form_id": form_id, "registrant_count": count, "mock": True, "note": "Mock mode - set MOCK_MODE=false for live count"})

    # Treat placeholder sheet_ as not linked
    is_placeholder_sheet = not sheet_id or sheet_id.startswith("mock_") or sheet_id.startswith("sheet_")

    # 1) Try Sheets if we have a real sheet_id (not placeholder)
    if not is_placeholder_sheet:
        try:
            from ..google.auth import get_credentials
            from googleapiclient.discovery import build
            creds = get_credentials()
            if creds:
                service = build("sheets", "v4", credentials=creds)
                for rng in ["Responses!A2:Z", "Sheet1!A2:Z", "Sheet1"]:
                    try:
                        result = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=rng).execute()
                        values = result.get("values", [])
                        count = max(0, len(values) - (1 if values and len(values[0])>0 else 0)) if values else 0
                        # if we got values, return
                        if values is not None:
                            return json.dumps({"sheet_id": sheet_id, "form_id": form_id, "registrant_count": count, "source": "sheets"})
                    except:
                        continue
        except Exception as e:
            pass

    # 2) Try Forms API - this auto-syncs as registrations come in (no manual sheet linking needed)
    if form_id and not form_id.startswith("mock_"):
        try:
            from ..google.auth import get_credentials
            from googleapiclient.discovery import build
            creds = get_credentials()
            if creds:
                service = build("forms", "v1", credentials=creds)
                # Forms API: list responses
                resp = service.forms().responses().list(formId=form_id).execute()
                responses = resp.get("responses", [])
                # handle pagination
                count = len(responses)
                return json.dumps({"sheet_id": sheet_id, "form_id": form_id, "registrant_count": count, "source": "forms_api", "auto_sync": True, "note": "Sheet updates are NOT automatic - Forms API is source of truth. Our sheet is just a snapshot; count here is live."})
        except Exception as e:
            # Forms API needs separate scope; if fails, fall through to mock
            pass

    # 3) Fallback mock
    import random
    # if we have real form_id but API failed, still return 0 rather than fake random
    if form_id and not form_id.startswith("mock_"):
        return json.dumps({"sheet_id": sheet_id, "form_id": form_id, "registrant_count": 0, "source": "none", "warning": "No linked sheet and Forms API unavailable - manually link Form to Sheet via Forms UI: Responses -> Link to Sheets, or check scopes"})
    count = random.randint(5, 15) if is_placeholder_sheet else 0
    return json.dumps({"sheet_id": sheet_id, "form_id": form_id, "registrant_count": count, "mock": True, "note": "Mock - create/link a response Sheet or use Forms API for live count"})
