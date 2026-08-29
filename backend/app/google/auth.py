import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from ..config import GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH, SCOPES

def _token_path_for_org(org: str | None = None) -> str:
    if org:
        try:
            from ..config import google_token_path_for_org
            return google_token_path_for_org(org)
        except: pass
    return GOOGLE_TOKEN_PATH

def get_credentials(org: str | None = None):
    creds = None
    token_path = _token_path_for_org(org)
    creds_path = GOOGLE_CREDENTIALS_PATH

    # Fallback to legacy token.json if per-org not found
    if org and not os.path.exists(token_path) and os.path.exists(GOOGLE_TOKEN_PATH):
        token_path = GOOGLE_TOKEN_PATH

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_path, "w") as token:
                    token.write(creds.to_json())
                return creds
            except: pass
        # Non-interactive: return None if interactive not possible (API mode)
        if not os.path.exists(creds_path):
            return None
        # Only run flow if called interactively (scripts/auth_google.py passes --org)
        if org is None and os.getenv("ALLOW_INTERACTIVE_AUTH", "false").lower() != "true":
            return None
        flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token:
            token.write(creds.to_json())
    return creds

def get_credentials_for_org(org: str):
    return get_credentials(org)
