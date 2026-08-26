import os
from strands import tool

@tool
def create_registration_form(event_title: str, event_date: str, description: str, fields_json: str = "") -> str:
    """
    Create a Google Form for event registration.
    Args:
        event_title: Event title
        event_date: Event date YYYY-MM-DD
        description: Form description
        fields_json: Optional JSON array of field objects like [{"title":"Full Name","type":"text","required":true}, {"title":"Phone","type":"text"}, {"title":"Year","type":"multiple_choice","options":["1st","2nd"]}] - if empty, uses default fields (Name, Email). Use paragraph type for long text, file_upload for files.
    Returns:
        JSON with form_link AND response sheet_link/sheet_id.
    """
    import json
    mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"

    if mock_mode:
        fake_id = f"mock_form_{event_title.replace(' ', '_')}"
        return json.dumps({
            "form_id": fake_id,
            "form_link": f"https://docs.google.com/forms/d/{fake_id}/viewform",
            "sheet_id": f"mock_sheet_{fake_id}",
            "sheet_link": f"https://docs.google.com/spreadsheets/d/mock_sheet_{fake_id}",
            "responses_link": f"https://docs.google.com/spreadsheets/d/mock_sheet_{fake_id}",
            "mock": True
        })

    try:
        from ..google.auth import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        if not creds:
            raise Exception("No credentials")
        service = build("forms", "v1", credentials=creds)
        # Create form
        form_body = {
            "info": {
                "title": f"{event_title} - Registration ({event_date})",
                "documentTitle": f"{event_title} Registration"
            }
        }
        result = service.forms().create(body=form_body).execute()
        form_id = result["formId"]

        # Build dynamic questions from fields_json or defaults
        import json as _json
        fields = []
        if fields_json:
            try:
                fields = _json.loads(fields_json)
                if isinstance(fields, str):
                    fields = _json.loads(fields)
            except:
                fields = []

        def _make_item(title, ftype, options=None, required=True):
            q = {"required": required}
            if ftype == "paragraph":
                q["textQuestion"] = {"paragraph": True}
            elif ftype == "multiple_choice":
                q["choiceQuestion"] = {
                    "type": "RADIO",
                    "options": [{"value": o} for o in (options or ["Option 1", "Option 2"])],
                    "shuffle": False
                }
            elif ftype == "checkbox":
                q["choiceQuestion"] = {
                    "type": "CHECKBOX",
                    "options": [{"value": o} for o in (options or ["Option 1"])],
                }
            elif ftype == "file_upload":
                q["fileUploadQuestion"] = {"maxFiles": 1, "maxFileSize": "10MB"}
            else:  # text, email, phone, class, section etc.
                q["textQuestion"] = {}
            return {
                "createItem": {
                    "item": {
                        "title": title,
                        "questionItem": {"question": q}
                    },
                    "location": {"index": 0}  # will be fixed below
                }
            }

        if not fields:
            fields = [
                {"title": "Full Name", "type": "text", "required": True},
                {"title": "Email", "type": "text", "required": True},
            ]

        requests = []
        for idx, f in enumerate(fields):
            title = f.get("title") or f.get("name") or f"Question {idx+1}"
            ftype = f.get("type", "text").lower()
            options = f.get("options")
            required = f.get("required", True)
            item = _make_item(title, ftype, options, required)
            item["createItem"]["location"]["index"] = idx
            requests.append(item)

        service.forms().batchUpdate(formId=form_id, body={"requests": requests}).execute()

        form_link = f"https://docs.google.com/forms/d/{form_id}/viewform"

        # Create linked response Sheet so we can return BOTH links (Forms API doesn't auto-link)
        sheet_link = ""
        sheet_id = ""
        try:
            sheets_service = build("sheets", "v4", credentials=creds)
            sheet_title = f"{event_title} - Responses ({event_date})"
            ss = sheets_service.spreadsheets().create(body={
                "properties": {"title": sheet_title},
                "sheets": [{"properties": {"title": "Responses"}}]
            }).execute()
            sheet_id = ss["spreadsheetId"]
            sheet_link = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
            # Add header row with field titles for easy tracking
            headers = [f.get("title") or f.get("name") for f in fields]
            if headers:
                sheets_service.spreadsheets().values().update(
                    spreadsheetId=sheet_id, range="Responses!A1",
                    valueInputOption="RAW",
                    body={"values": [headers]}
                ).execute()
        except Exception as se:
            # sheet creation is bonus; form still succeeds
            pass

        return json.dumps({
            "form_id": form_id,
            "form_link": form_link,
            "sheet_id": sheet_id,
            "sheet_link": sheet_link,
            "responses_link": sheet_link,
            "description": description
        })
    except Exception as e:
        fake_id = f"mock_form_{event_title.replace(' ', '_')}"
        return json.dumps({
            "form_id": fake_id,
            "form_link": f"https://docs.google.com/forms/d/{fake_id}/viewform",
            "sheet_id": f"mock_sheet_{fake_id}",
            "sheet_link": f"https://docs.google.com/spreadsheets/d/mock_sheet_{fake_id}",
            "responses_link": f"https://docs.google.com/spreadsheets/d/mock_sheet_{fake_id}",
            "mock": True,
            "error": str(e)
        })
