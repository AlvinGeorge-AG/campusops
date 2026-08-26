import os
from strands import tool

@tool
def create_registration_form(event_title: str, event_date: str, description: str) -> str:
    """
    Create a Google Form for event registration.
    Args:
        event_title: Event title
        event_date: Event date YYYY-MM-DD
        description: Form description
    Returns:
        Form URL and IDs or mock response.
    """
    import json
    mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"

    if mock_mode:
        fake_id = f"mock_form_{event_title.replace(' ', '_')}"
        return json.dumps({
            "form_id": fake_id,
            "form_link": f"https://docs.google.com/forms/d/{fake_id}/viewform",
            "sheet_id": f"mock_sheet_{fake_id}",
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
        # Add questions (Name, Email)
        # Forms batchUpdate
        update = {
            "requests": [
                {
                    "createItem": {
                        "item": {
                            "title": "Full Name",
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "textQuestion": {}
                                }
                            }
                        },
                        "location": {"index": 0}
                    }
                },
                {
                    "createItem": {
                        "item": {
                            "title": "Email",
                            "questionItem": {
                                "question": {
                                    "required": True,
                                    "textQuestion": {}
                                }
                            }
                        },
                        "location": {"index": 1}
                    }
                }
            ]
        }
        service.forms().batchUpdate(formId=form_id, body=update).execute()

        form_link = f"https://docs.google.com/forms/d/{form_id}/viewform"
        return json.dumps({
            "form_id": form_id,
            "form_link": form_link,
            "sheet_id": "",  # user links sheet manually or we create separately
            "description": description
        })
    except Exception as e:
        fake_id = f"mock_form_{event_title.replace(' ', '_')}"
        return json.dumps({
            "form_id": fake_id,
            "form_link": f"https://docs.google.com/forms/d/{fake_id}/viewform",
            "sheet_id": f"mock_sheet_{fake_id}",
            "mock": True,
            "error": str(e)
        })
