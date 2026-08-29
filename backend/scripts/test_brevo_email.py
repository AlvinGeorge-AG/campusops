#!/usr/bin/env python3
"""
Test Brevo email sending to alvingeorge.mec@gmail.com
Loads credentials from backend/.env via python-dotenv (does not print secrets).
Diagnoses common failure modes and suggests fixes.
"""
import os
import sys
from pathlib import Path

# Resolve backend root = .../backend
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND_DIR / ".env"

# Load .env BEFORE any app imports that read os.getenv at import time
try:
    from dotenv import load_dotenv
    loaded = load_dotenv(dotenv_path=ENV_PATH, override=False)
    print(f"[info] load_dotenv({ENV_PATH}) -> {loaded} | exists={ENV_PATH.exists()}")
except ImportError as e:
    print(f"[error] python-dotenv not installed: {e}")
    print("  Fix: pip install python-dotenv  OR  pip install -r backend/requirements.txt")
    sys.exit(1)

# Now read vars (mask secrets)
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "")
FROM_NAME = os.getenv("FROM_NAME", "CampusOps")
TO_EMAIL = "alvingeorge.mec@gmail.com"

def mask(s: str, keep: int = 4) -> str:
    if not s:
        return "(empty)"
    if len(s) <= keep*2:
        return s[0] + "***" + s[-1] if len(s) > 1 else "***"
    return s[:keep] + "***" + s[-keep:]

print("\n=== Brevo Config Diagnosis ===")
print(f"BACKEND_DIR : {BACKEND_DIR}")
print(f"ENV_PATH    : {ENV_PATH}")
print(f"BREVO_API_KEY : {'SET' if BREVO_API_KEY else 'NOT SET'} | len={len(BREVO_API_KEY) if BREVO_API_KEY else 0} | masked={mask(BREVO_API_KEY,6) if BREVO_API_KEY else '(empty)'}")
print(f"FROM_EMAIL    : {FROM_EMAIL or '(empty - will default to your-email@gmail.com)'}")
print(f"FROM_NAME     : {FROM_NAME}")
print(f"TO_EMAIL      : {TO_EMAIL}")

# quick placeholder checks
has_error = False
if not BREVO_API_KEY:
    print("\n[FAIL] BREVO_API_KEY not set.")
    print("  Fix: Add to backend/.env:")
    print("       BREVO_API_KEY=xkeysib-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    print("  Get key from: https://app.brevo.com/settings/keys/api")
    has_error = True
elif BREVO_API_KEY.strip() in ("your_brevo_api_key_here", "your-brevo-api-key", "test", "changeme"):
    print("\n[FAIL] BREVO_API_KEY looks like a placeholder.")
    has_error = True
elif not BREVO_API_KEY.startswith("xkeysib-"):
    print("\n[WARN] BREVO_API_KEY does not start with 'xkeysib-' (Brevo keys usually start with xkeysib-). Double-check value.")

if not FROM_EMAIL or FROM_EMAIL == "your-email@gmail.com":
    print("\n[WARN] FROM_EMAIL not set or is placeholder 'your-email@gmail.com'.")
    print("  Fix: Set FROM_EMAIL in backend/.env to a sender verified in Brevo:")
    print("       FROM_EMAIL=noreply@yourdomain.com  or your Brevo-verified Gmail")
    print("  Verify sender: Brevo Dashboard -> Transactional -> Senders & Domains -> Add sender & verify via click link.")
    print("  Current value will be used but Brevo will reject 403 if unverified.")
    # not fatal, but warn
    if not FROM_EMAIL:
        FROM_EMAIL = "your-email@gmail.com"

if has_error:
    print("\n[abort] Fix .env first before sending. Exiting.")
    sys.exit(2)

# Check library available
try:
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException
except ImportError as e:
    print(f"\n[error] sib-api-v3-sdk not installed: {e}")
    print("  Fix: pip install sib-api-v3-sdk==7.6.0")
    print("  Or: pip install -r backend/requirements.txt")
    sys.exit(1)

print("\n=== Attempting to send test email via Brevo ===")
html_body = """
<h2>CampusOps Brevo Test</h2>
<p>This is a test email from <b>CampusOps</b> backend (Brevo integration).</p>
<p>If you received this at <code>alvingeorge.mec@gmail.com</code>, the integration is working.</p>
<ul>
  <li>FROM: {from_email} ({from_name})</li>
  <li>TO: {to_email}</li>
</ul>
<p>Timestamp: (server local time)</p>
""".format(from_email=FROM_EMAIL, from_name=FROM_NAME, to_email=TO_EMAIL)

subject = "CampusOps Brevo Test Email - Please ignore"

configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = BREVO_API_KEY
api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
    to=[{"email": TO_EMAIL}],
    sender={"email": FROM_EMAIL, "name": FROM_NAME},
    subject=subject,
    html_content=html_body,
)

try:
    response = api_instance.send_transac_email(send_smtp_email)
    print(f"[SUCCESS] Email sent!")
    print(f"  message_id: {response.message_id}")
    print(f"  to: {TO_EMAIL}")
    print(f"  from: {FROM_EMAIL} ({FROM_NAME})")
    print(f"  Check inbox (and spam) for: {TO_EMAIL}")
    sys.exit(0)
except ApiException as e:
    print(f"\n[FAIL] Brevo API error (ApiException)")
    print(f"  Status : {e.status}")
    print(f"  Reason : {e.reason}")
    body = e.body or ""
    print(f"  Body   : {body[:2000]}")
    print("\n=== Diagnosis ===")
    # Common codes
    if e.status == 401:
        print("  401 Unauthorized -> Invalid BREVO_API_KEY")
        print("  Fixes:")
        print("   - Regenerate key at https://app.brevo.com/settings/keys/api")
        print("   - Ensure .env has BREVO_API_KEY=xkeysib-... with no quotes/spaces")
        print("   - No extra newline; run: python3 -c \"import os;from dotenv import load_dotenv;load_dotenv('backend/.env');print(repr(os.getenv('BREVO_API_KEY')[:15]))\"")
    elif e.status == 403:
        print("  403 Forbidden -> Sender not validated or account issue")
        print("  Fixes:")
        print(f"   - Verify FROM_EMAIL='{FROM_EMAIL}' in Brevo: Senders & Domains -> must show 'Verified' green")
        print("   - If using Gmail, you must still add & verify it as sender in Brevo")
        print("   - Check Brevo account is active, no quota exceeded")
        print(f"   - Try changing FROM_EMAIL in .env to a verified sender and retry")
    elif e.status == 400:
        print("  400 Bad Request -> Payload/format error")
        print(f"   - Check FROM_EMAIL format valid: {FROM_EMAIL}")
        print("   - Check html_content not empty, subject not empty")
        body_lower = body.lower()
        if "sender" in body_lower:
            print("   - Body mentions sender -> verify sender domain")
    else:
        print(f"  Unhandled status {e.status}. See body above.")
        print("  General fixes: check Brevo docs https://developers.brevo.com/docs/transactional-emails")
    sys.exit(3)
except Exception as e:
    import traceback
    print(f"\n[FAIL] Unexpected error: {e}")
    traceback.print_exc()
    print("\n[hint] Check network, .env whitespace, and that sib-api-v3-sdk is latest.")
    sys.exit(4)
