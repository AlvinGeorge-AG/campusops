import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from ..config import GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH, SCOPES

def get_credentials():
    creds = None
    token_path = GOOGLE_TOKEN_PATH
    creds_path = GOOGLE_CREDENTIALS_PATH

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                return None
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        # save
        with open(token_path, "w") as token:
            token.write(creds.to_json())
    return creds
