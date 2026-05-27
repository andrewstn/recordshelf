import requests
from django.conf import settings


def email_list(value):
    if isinstance(value, str):
        return [value]
    return list(value)


def send_resend_email(*, subject, body, to, reply_to=None):
    if not settings.RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY is not configured.")

    payload = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": email_list(to),
        "subject": subject,
        "text": body,
    }
    if reply_to:
        payload["reply_to"] = email_list(reply_to)

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
