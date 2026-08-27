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
        # Resolve org/room for detailed heading from latest event
        org = ""
        room = ""
        venue_note = ""
        try:
            from ..state import get_latest_event as _get_ev
            _ev2 = _get_ev()
            if _ev2:
                org = _ev2.org or ""
                room = _ev2.room or ""
        except:
            pass
        # Build rich description: heading + venue/date/club + user description
        detailed_desc = ""
        if org:
            detailed_desc += f"Organized by {org}  •  "
        if room:
            detailed_desc += f"Venue: {room}  •  "
        detailed_desc += f"Date: {event_date}\n\n"
        if description:
            detailed_desc += description.strip()
        else:
            detailed_desc += f"Join us for {event_title}! Please fill the form to register."
        # Header image support (optional) - via Forms API imageItem
        header_image_url = os.getenv("FORM_HEADER_IMAGE_URL", "").strip()  # set in .env if you want banner pic
        # Convert Drive "file/d/ID/view" link to direct "uc?id=ID" that Forms API can fetch
        if "drive.google.com/file/d/" in header_image_url:
            try:
                file_id = header_image_url.split("/d/")[1].split("/")[0]
                header_image_url = f"https://drive.google.com/uc?export=view&id={file_id}"
            except:
                pass

        # Forms API only allows info.title on create - description must be via batchUpdate
        form_body = {
            "info": {
                "title": f"{event_title} - Registration"
            }
        }
        result = service.forms().create(body=form_body).execute()
        form_id = result["formId"]
        # Set description via updateFormInfo (must be separate batchUpdate)
        try:
            service.forms().batchUpdate(formId=form_id, body={
                "requests": [{
                    "updateFormInfo": {
                        "info": {"description": detailed_desc},
                        "updateMask": "description"
                    }
                }]
            }).execute()
        except Exception as de:
            print(f"[forms] updateFormInfo failed (ignored): {de}")

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

        # Build requests without image first (image is risky - separate call)
        requests = []
        for idx, f in enumerate(fields):
            title = f.get("title") or f.get("name") or f"Question {idx+1}"
            ftype = f.get("type", "text").lower()
            options = f.get("options")
            required = f.get("required", True)
            item = _make_item(title, ftype, options, required)
            item["createItem"]["location"]["index"] = idx
            requests.append(item)

        # Execute questions first - this must succeed
        service.forms().batchUpdate(formId=form_id, body={"requests": requests}).execute()

        # Try header image separately - if it fails, form still exists (don't fallback to mock)
        if header_image_url:
            try:
                # Validate URL is https and image-like
                if header_image_url.startswith("https://"):
                    service.forms().batchUpdate(formId=form_id, body={
                        "requests": [{
                            "createItem": {
                                "item": {"title": event_title, "imageItem": {"image": {"sourceUri": header_image_url}}},
                                "location": {"index": 0}
                            }
                        }]
                    }).execute()
            except Exception as ie:
                # Image failed, but form is already created - just log, don't mock
                print(f"[forms] header image failed (ignored): {ie}")

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
            # Header must match sync rows: [Response ID, Timestamp, Email] + field titles
            headers = ["Response ID", "Submitted At", "Email"] + [f.get("title") or f.get("name") for f in fields]
            sheets_service.spreadsheets().values().update(
                spreadsheetId=sheet_id, range="Responses!A1",
                valueInputOption="RAW",
                body={"values": [headers]}
            ).execute()
            # Bold header
            try:
                sheets_service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={
                    "requests": [{"repeatCell": {"range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1}, "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}}, "fields": "userEnteredFormat.textFormat.bold"}}]
                }).execute()
            except:
                pass
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
        # Surface real error in uvicorn logs so we can debug (don't hide)
        import traceback
        print(f"[forms] CREATE FAILED: {e}")
        traceback.print_exc()
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
