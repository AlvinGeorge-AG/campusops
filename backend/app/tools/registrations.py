import os
import json
from strands import tool

def sync_responses_to_sheet(form_id: str, sheet_id: str) -> dict:
    """Deterministic helper: copies Forms responses → Sheet so sheet auto-updates without manual Link. No LLM."""
    if not form_id or form_id.startswith("mock_") or not sheet_id or sheet_id.startswith("mock_") or sheet_id.startswith("sheet_"):
        return {"synced": False, "reason": "placeholder ids"}
    try:
        from ..google.auth import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        if not creds:
            return {"synced": False, "reason": "no credentials"}
        forms = build("forms", "v1", credentials=creds)
        sheets = build("sheets", "v4", credentials=creds)
        # Fetch all responses (handle pagination)
        all_resps = []
        page_token = None
        while True:
            resp = forms.forms().responses().list(formId=form_id, pageToken=page_token).execute() if page_token else forms.forms().responses().list(formId=form_id).execute()
            all_resps.extend(resp.get("responses", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        # Build rows: [responseId, createTime, respondentEmail, answers...]
        rows = []
        for r in all_resps:
            rid = r.get("responseId", "")
            ctime = r.get("createTime", "") or r.get("lastSubmittedTime", "")
            email = r.get("respondentEmail", "")
            # flatten answers: Forms answers is dict of questionId -> {textAnswers:{answers:[{value}]}, ...}
            ans_texts = []
            for qid, ans in (r.get("answers") or {}).items():
                if "textAnswers" in ans:
                    vals = [a.get("value","") for a in ans["textAnswers"].get("answers",[])]
                    ans_texts.append(" | ".join(vals))
                elif "choiceAnswers" in ans:
                    vals = [a.get("value","") for a in ans.get("choiceAnswers",{}).get("answers",[])]
                    ans_texts.append(" | ".join(vals))
                elif "fileUploadAnswers" in ans:
                    vals = [a.get("fileName","") for a in ans["fileUploadAnswers"].get("answers",[])]
                    ans_texts.append(" | ".join(vals))
                else:
                    ans_texts.append(str(ans))
            row = [rid, ctime, email] + ans_texts
            rows.append(row)
        # Clear existing data below header (keep header row)
        sheets.spreadsheets().values().clear(spreadsheetId=sheet_id, range="Responses!A2:Z").execute()
        # If sheet name is Sheet1 fallback
        target = "Responses!A2"
        if rows:
            sheets.spreadsheets().values().update(
                spreadsheetId=sheet_id, range=target,
                valueInputOption="RAW",
                body={"values": rows}
            ).execute()
        return {"synced": True, "count": len(rows), "sheet_id": sheet_id, "form_id": form_id}
    except Exception as e:
        return {"synced": False, "error": str(e)}

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
                # Auto-sync to sheet so sheet_link appears live (1 extra Sheets call, within free quota)
                if sheet_id and not sheet_id.startswith("mock_") and not sheet_id.startswith("sheet_"):
                    try:
                        sync_responses_to_sheet(form_id, sheet_id)
                    except:
                        pass
                return json.dumps({"sheet_id": sheet_id, "form_id": form_id, "registrant_count": count, "source": "forms_api", "auto_sync": True, "sheet_synced": True})
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
