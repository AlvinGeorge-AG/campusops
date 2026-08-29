import os
import base64
from typing import List, Tuple
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "your-email@gmail.com")
FROM_NAME = os.getenv("FROM_NAME", "CampusOps")

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
    if not BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY not set")
    
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
        return {
            "sent": True,
            "message_id": str(response.message_id)
        }
    except ApiException as e:
        raise RuntimeError(f"Brevo API error: {e.body}")