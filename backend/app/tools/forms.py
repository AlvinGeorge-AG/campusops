import os
import json as _json
import logging
from strands import tool

logger = logging.getLogger(__name__)

def _create_upload_folder(creds, event_title: str, event_date: str) -> str:
    """Create a Google Drive folder for file uploads and return its link."""
    try:
        from googleapiclient.discovery import build
        drive_service = build("drive", "v3", credentials=creds)
        folder_name = f"{event_title} - File Uploads ({event_date})"
        folder_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder"
        }
        folder = drive_service.files().create(body=folder_metadata, fields="id,webViewLink").execute()
        folder_id = folder.get("id")
        folder_link = folder.get("webViewLink")
        # Make folder accessible to anyone with link (editor access for uploads)
        drive_service.permissions().create(
            fileId=folder_id,
            body={"type": "anyone", "role": "writer"},
            fields="id"
        ).execute()
        return folder_link
    except Exception as e:
        logger.error("Failed to create upload folder: %s", e)
        return ""

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
    import json as _json
    mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"

    if mock_mode:
        fake_id = f"mock_form_{event_title.replace(' ', '_')}"
        return _json.dumps({
            "form_id": fake_id,
            "form_link": f"https://docs.google.com/forms/d/{fake_id}/viewform",
            "sheet_id": f"mock_sheet_{fake_id}",
            "sheet_link": f"https://docs.google.com/spreadsheets/d/mock_sheet_{fake_id}",
            "responses_link": f"https://docs.google.com/spreadsheets/d/mock_sheet_{fake_id}",
            "mock": True,
            "upload_folder_link": ""
        })

    try:
        from ..google.auth import get_credentials
        from googleapiclient.discovery import build
        # Resolve org/room from event matching title/date (not just latest) for per-club Drive isolation
        org = ""
        room = ""
        _resolved_org = None
        try:
            from ..state import list_events as _le
            for _ev in _le():
                if _ev.title == event_title and _ev.date == event_date:
                    org = _ev.org or ""; room = _ev.room or ""; _resolved_org = _ev.org; break
        except: pass
        if not org:
            try:
                from ..state import get_latest_event as _get_ev
                _ev2 = _get_ev()
                if _ev2:
                    org = _ev2.org or ""; room = _ev2.room or ""; _resolved_org = _ev2.org
            except: pass
        creds = get_credentials(_resolved_org)
        if not creds:
            # Fallback to default creds
            creds = get_credentials()
        if not creds:
            raise Exception("No credentials")
        service = build("forms", "v1", credentials=creds)
        
        # Check if any field is file_upload type - create Drive folder for uploads
        upload_folder_link = ""
        has_file_upload = False
        if fields_json:
            try:
                _temp_fields = _json.loads(fields_json)
                if isinstance(_temp_fields, str):
                    _temp_fields = _json.loads(_temp_fields)
                has_file_upload = any(f.get("type", "").lower() == "file_upload" for f in _temp_fields)
            except Exception as e:
                pass
        if has_file_upload:
            upload_folder_link = _create_upload_folder(creds, event_title, event_date)
        # Build rich description: heading + venue/date/club + user description
        # Fix leak: agent sometimes passes "Create Google Form for ..." as description - replace with real purpose
        _desc = description.strip() if description else ""
        _low = _desc.lower()
        if _low.startswith("create google form") or _low.startswith("create a google form") or _low == "create google form for java workshop":
            _desc = ""
        # Prefer stored purpose from Event if passed desc is generic/empty
        if not _desc:
            try:
                from ..state import list_events as _le2
                for _evb in _le2():
                    if _evb.title == event_title and _evb.date == event_date and _evb.purpose and len(_evb.purpose.strip()) > 10:
                        _desc = _evb.purpose.strip(); break
                if not _desc:
                    from ..state import get_latest_event as _get_ev2b
                    _evb = _get_ev2b()
                    if _evb and _evb.purpose and len(_evb.purpose.strip()) > 10:
                        _desc = _evb.purpose.strip()
            except: pass
        
        # Get additional event metadata for richer description
        speaker = ""
        start_time = ""
        end_time = ""
        expected_headcount = 0
        try:
            from ..state import list_events as _le3
            found=False
            for _ev3 in _le3():
                if _ev3.title == event_title and _ev3.date == event_date:
                    speaker = _ev3.speaker or ""; start_time = _ev3.start_time or ""; end_time = _ev3.end_time or ""; expected_headcount = _ev3.expected_headcount or 0; found=True; break
            if not found:
                from ..state import get_latest_event as _get_ev3
                _ev3 = _get_ev3()
                if _ev3:
                    speaker = _ev3.speaker or ""; start_time = _ev3.start_time or ""; end_time = _ev3.end_time or ""; expected_headcount = _ev3.expected_headcount or 0
        except: pass
        
        detailed_desc = ""
        if org:
            detailed_desc += f"📋 Organized by: {org}  •  "
        if room:
            detailed_desc += f"📍 Venue: {room}  •  "
        detailed_desc += f"📅 Date: {event_date}"
        if start_time and end_time:
            detailed_desc += f"\n⏰ Time: {start_time} - {end_time}"
        detailed_desc += "\n\n"
        if speaker:
            detailed_desc += f"🎤 Speaker: {speaker}\n\n"
        if expected_headcount:
            detailed_desc += f"👥 Expected Attendees: {expected_headcount}\n\n"
        if _desc:
            detailed_desc += f"📝 About the Event:\n{_desc}\n\n"
        else:
            detailed_desc += f"Join us for {event_title}! Please fill the form to register.\n\n"
        detailed_desc += "⚠️ Seats are limited. Registration will close once capacity is reached.\n"
        detailed_desc += "📩 Confirmation details will be sent via email after submission."
        # Add file upload instructions if needed
        if upload_folder_link:
            detailed_desc += f"\n\n📎 File Uploads:\nFor any file upload fields, please upload your files to this Google Drive folder and paste the shareable link in the form:\n{upload_folder_link}\n\nMake sure the link is set to 'Anyone with the link can view' for our team to access it."
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
            logger.warning("updateFormInfo failed (ignored): %s", de)

        # Build dynamic questions from fields_json or defaults
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
                # Forms API doesn't support file_upload via batchUpdate - use text field for Drive link
                q["textQuestion"] = {}
                if upload_folder_link:
                    title = f"{title} (paste Google Drive file link here)"
                else:
                    title = f"{title} (upload to Drive and paste link)"
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
                logger.warning("header image failed (ignored): %s", ie)

        form_link = f"https://docs.google.com/forms/d/{form_id}/viewform"

        # Create linked response Sheet so we can return BOTH links (Forms API doesn't auto-link)
        sheet_link = ""
        sheet_id = ""
        sheet_error = ""
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
            sheet_error = str(se)
            logger.warning("response sheet creation failed for form %s: %s", form_id, se)

        return _json.dumps({
            "form_id": form_id,
            "form_link": form_link,
            "sheet_id": sheet_id,
            "sheet_link": sheet_link,
            "responses_link": sheet_link,
            "description": description,
            "upload_folder_link": upload_folder_link,
            "sheet_error": sheet_error
        })
    except Exception as e:
        # Surface real error in uvicorn logs so we can debug (don't hide)
        logger.exception("CREATE FAILED: %s", e)
        return _json.dumps({
            "form_id": "",
            "form_link": "",
            "sheet_id": "",
            "sheet_link": "",
            "responses_link": "",
            "mock": False,
            "error": str(e),
            "upload_folder_link": ""
        })
