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
DEFAULT_CHAIRPERSON = _env("DEFAULT_CHAIRPERSON", "Charles Xavier")
DEFAULT_STAFF = _env("DEFAULT_STAFF", "Joby John")

# Database (absolute path to avoid CWD issues) + Neon Postgres
DB_PATH = _env("DB_PATH", str(BASE_DIR / "events.db"))
DATABASE_URL = _env("DATABASE_URL", "").strip()  # Neon postgres pooled URL, e.g. postgres://user:pass@ep-xxx.neon.tech/db?sslmode=require
USE_NATIVE_FORMS = _env("USE_NATIVE_FORMS", "true").lower() == "true"  # native DB forms vs Google Forms
NATIVE_FORM_CACHE_TTL = int(_env("NATIVE_FORM_CACHE_TTL", "60"))  # seconds for on-demand cache

# Email
FACULTY_EMAIL = _env("FACULTY_EMAIL", "principal@example.com")
ANNOUNCEMENT_RECIPIENTS = _env("ANNOUNCEMENT_RECIPIENTS", "students@example.com")

# App settings
MOCK_MODE = _env("MOCK_MODE", "false").lower() == "true"
POLLER_ENABLED = _env("POLLER_ENABLED", "false").lower() == "true"
GEMINI_MODEL_ID = _env("GEMINI_MODEL_ID", "gemini-3.5-flash-lite")
GEMINI_TIMEOUT_MS = int(_env("GEMINI_TIMEOUT_MS", "45000"))

# Auth / RBAC
JWT_SECRET = _env("JWT_SECRET", "dev-secret-change-in-prod-please-rotate")
JWT_ALGORITHM = _env("JWT_ALGORITHM", "HS256")
JWT_EXP_MINUTES = int(_env("JWT_EXP_MINUTES", "60"))
SANDBOX_ORG = _env("SANDBOX_ORG", "TEST_CLUB")
FRONTEND_ORIGIN = _env("FRONTEND_ORIGIN", "http://localhost:5173")
BCRYPT_ROUNDS = int(_env("BCRYPT_ROUNDS", "12"))

CENTRAL_DRIVE = _env("CENTRAL_DRIVE", "true").lower() == "true"
GOOGLE_REDIRECT_URI = _env("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

# Per-club Google tokens
def google_token_path_for_org(org: str) -> str:
    if not org or org.strip().lower() == SANDBOX_ORG.lower():
        return _env("GOOGLE_TOKEN_PATH", str(BASE_DIR / "token.json"))
    safe = "".join(c if c.isalnum() else "_" for c in org.strip().lower())[:32]
    return str(BASE_DIR / f"token_{safe}.json")
