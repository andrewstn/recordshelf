import base64
from email.mime.base import MIMEBase

from django.core.mail.backends.base import BaseEmailBackend

from .email import send_resend_email


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent_count = 0
        for message in email_messages:
            try:
                self.send_message(message)
            except Exception:
                if not self.fail_silently:
                    raise
            else:
                sent_count += 1
        return sent_count

    def send_message(self, message):
        send_resend_email(
            subject=message.subject,
            body=self.text_body(message),
            to=message.to,
            cc=message.cc,
            bcc=message.bcc,
            reply_to=message.reply_to,
            html=self.html_body(message),
            attachments=self.attachments(message),
        )

    def text_body(self, message):
        if getattr(message, "content_subtype", "plain") == "html":
            return ""
        return message.body or ""

    def html_body(self, message):
        if getattr(message, "content_subtype", "plain") == "html":
            return message.body or ""

        for alternative in getattr(message, "alternatives", []):
            content = getattr(alternative, "content", None)
            mimetype = getattr(alternative, "mimetype", None)
            if content is None and mimetype is None:
                content, mimetype = alternative
            if mimetype == "text/html":
                return content
        return None

    def attachments(self, message):
        encoded_attachments = []
        for attachment in message.attachments:
            encoded = self.encode_attachment(attachment)
            if encoded:
                encoded_attachments.append(encoded)
        return encoded_attachments or None

    def encode_attachment(self, attachment):
        if isinstance(attachment, MIMEBase):
            filename = attachment.get_filename()
            content_type = attachment.get_content_type()
            content = attachment.get_payload(decode=True)
        else:
            filename, content, content_type = attachment

        if not filename or content is None:
            return None

        if isinstance(content, str):
            content = content.encode()

        return {
            "filename": filename,
            "content": base64.b64encode(content).decode("ascii"),
            "content_type": content_type,
        }
