from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

def _env(key: str, default: str) -> str:
    return os.getenv(key, default)

# Google OAuth
GOOGLE_CREDENTIALS_PATH = _env("GOOGLE_CREDENTIALS_PATH", str(BASE_DIR / "credentials.json"))
GOOGLE_TOKEN_PATH = _env("GOOGLE_TOKEN_PATH", str(BASE_DIR / "token.json"))
SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# Institution fallbacks (overridden per-org via Settings UI → org_settings table)
# Previously hard-coded; now dynamic. These env fallbacks only used when no org-specific setting exists.
INSTITUTION_NAME = _env("INSTITUTION_NAME", "Govt. Model Engineering College")
INSTITUTION_PLACE = _env("INSTITUTION_PLACE", "Thrikkakara")
DEFAULT_ORG = _env("DEFAULT_ORG", "FOSS MEC")
DEFAULT_CHAIRPERSON = _env("DEFAULT_CHAIRPERSON", "Arthana Sreekesh")
DEFAULT_STAFF = _env("DEFAULT_STAFF", "Aysha Fymin Majeed")

# Database (absolute path to avoid CWD issues)
DB_PATH = _env("DB_PATH", str(BASE_DIR / "events.db"))

# Email
FACULTY_EMAIL = _env("FACULTY_EMAIL", "principal@example.com")
ANNOUNCEMENT_RECIPIENTS = _env("ANNOUNCEMENT_RECIPIENTS", "students@example.com")

# App settings
MOCK_MODE = _env("MOCK_MODE", "false").lower() == "true"
POLLER_ENABLED = _env("POLLER_ENABLED", "false").lower() == "true"
GEMINI_MODEL_ID = _env("GEMINI_MODEL_ID", "gemini-3.5-flash-lite")