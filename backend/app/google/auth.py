import os
import time
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import requests
from ..config import GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH, SCOPES

class TimeoutHTTPAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, timeout=3.0, *args, **kwargs):
        self.timeout = timeout
        super().__init__(*args, **kwargs)
    def send(self, request, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        return super().send(request, **kwargs)

def _get_auth_request():
    session = requests.Session()
    adapter = TimeoutHTTPAdapter(timeout=3.0)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return Request(session=session)

_creds_cache: dict[str, tuple[float, any]] = {}

def _token_path_for_org(org: str | None = None) -> str:
    if org:
        try:
            from ..config import google_token_path_for_org
            return google_token_path_for_org(org)
        except: pass
    return GOOGLE_TOKEN_PATH

def get_credentials(org: str | None = None):
    cache_key = (org or "default").strip().lower()
    now = time.time()
    if cache_key in _creds_cache:
        ts, cached = _creds_cache[cache_key]
        if now - ts < 60:
            if cached is None or (hasattr(cached, "valid") and cached.valid):
                return cached

    creds = None
    token_path = _token_path_for_org(org)
    creds_path = GOOGLE_CREDENTIALS_PATH

    # Fallback to legacy token.json if per-org not found
    if org and not os.path.exists(token_path) and os.path.exists(GOOGLE_TOKEN_PATH):
        token_path = GOOGLE_TOKEN_PATH

    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        _creds_cache[cache_key] = (now, creds)
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            req = _get_auth_request()
            creds.refresh(req)
            try:
                with open(token_path, "w") as token:
                    token.write(creds.to_json())
            except Exception:
                pass
            _creds_cache[cache_key] = (now, creds)
            return creds
        except Exception:
            pass

    # Never launch interactive browser server in backend API mode (prevents Render 502 server hang)
    if os.getenv("ALLOW_INTERACTIVE_AUTH", "false").lower() != "true":
        _creds_cache[cache_key] = (now, None)
        return None
    if not os.path.exists(creds_path):
        _creds_cache[cache_key] = (now, None)
        return None
    try:
        flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token:
            token.write(creds.to_json())
        _creds_cache[cache_key] = (now, creds)
        return creds
    except Exception:
        _creds_cache[cache_key] = (now, None)
        return None

def get_credentials_for_org(org: str):
    return get_credentials(org)
