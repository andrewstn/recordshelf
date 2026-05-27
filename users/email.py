import requests
from django.conf import settings


def email_list(value):
    if isinstance(value, str):
        return [value]
    return list(value)


def send_resend_email(
    *,
    subject,
    body,
    to,
    from_email=None,
    cc=None,
    bcc=None,
    reply_to=None,
    html=None,
    attachments=None,
):
    if not settings.RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY is not configured.")

    payload = {
        "from": from_email or settings.RESEND_FROM_EMAIL,
        "to": email_list(to),
        "subject": subject,
        "text": body,
    }
    if cc:
        payload["cc"] = email_list(cc)
    if bcc:
        payload["bcc"] = email_list(bcc)
    if reply_to:
        payload["reply_to"] = email_list(reply_to)
    if html:
        payload["html"] = html
    if attachments:
        payload["attachments"] = attachments

    response = requests.post(
        settings.RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "recordshelf/1.0",
        },
        json=payload,
        timeout=settings.EMAIL_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()
