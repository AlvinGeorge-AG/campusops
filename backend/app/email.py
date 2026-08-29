import os
import base64
from typing import List, Tuple
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import logging

logger = logging.getLogger(__name__)

def _get_brevo_config():
    """Read Brevo config at call-time (not import-time) so dotenv ordering doesn't break it."""
    # Ensure .env loaded if called outside FastAPI context (e.g., scripts)
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
    except Exception:
        pass
    return (
        os.getenv("BREVO_API_KEY"),
        os.getenv("FROM_EMAIL", "your-email@gmail.com"),
        os.getenv("FROM_NAME", "CampusOps"),
    )

def send_permission_email(
    to_email: str,
    subject: str,
    html_body: str,
    pdf_attachments: List[Tuple[str, bytes]]
) -> dict:
    """
    Send email via Brevo (Sendinblue) API with PDF attachments.
    Returns: {"sent": True, "message_id": "..."} or raises Exception
    """
    BREVO_API_KEY, FROM_EMAIL, FROM_NAME = _get_brevo_config()
    if not BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY not set (check backend/.env)")
    if not FROM_EMAIL or "@" not in FROM_EMAIL or FROM_EMAIL == "your-email@gmail.com":
        raise RuntimeError("FROM_EMAIL is not configured with a verified Brevo sender (check backend/.env)")
    if not to_email or "@" not in to_email:
        raise RuntimeError(f"Principal recipient email is invalid: {to_email!r}")
    
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = BREVO_API_KEY
    
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
    
    attachments = []
    for filename, pdf_bytes in pdf_attachments:
        encoded = base64.b64encode(pdf_bytes).decode()
        attachments.append({
            "content": encoded,
            "name": filename
        })
    
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": to_email}],
        sender={"email": FROM_EMAIL, "name": FROM_NAME},
        subject=subject,
        html_content=html_body,
        attachment=attachments
    )
    
    try:
        response = api_instance.send_transac_email(send_smtp_email)
        logger.info("Permission email accepted by Brevo: to=%s message_id=%s", to_email, response.message_id)
        return {
            "sent": True,
            "message_id": str(response.message_id)
        }
    except ApiException as e:
        logger.error("Brevo rejected permission email: to=%s status=%s reason=%s body=%s", to_email, e.status, e.reason, e.body)
        raise RuntimeError(f"Brevo API error [{e.status} {e.reason}]: {e.body}")