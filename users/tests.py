from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from .forms import ResendPasswordResetForm
from .views import send_support_email_via_resend


class ResendSupportEmailTests(SimpleTestCase):
    @override_settings(
        RESEND_API_KEY="re_test",
        RESEND_API_URL="https://api.resend.com/emails",
        RESEND_FROM_EMAIL="recordshelf <hello@record-shelf.com>",
        SUPPORT_EMAIL="support@record-shelf.com",
        EMAIL_TIMEOUT=10,
    )
    @patch("users.email.requests.post")
    def test_support_email_posts_to_resend_api(self, mock_post):
        response = Mock()
        response.json.return_value = {"id": "email_123"}
        mock_post.return_value = response

        result = send_support_email_via_resend(
            subject="[recordshelf support] Need help",
            body="Hello support.",
            reply_to="sender@example.com",
        )

        self.assertEqual(result, {"id": "email_123"})
        mock_post.assert_called_once_with(
            "https://api.resend.com/emails",
            headers={
                "Authorization": "Bearer re_test",
                "Content-Type": "application/json",
                "User-Agent": "recordshelf/1.0",
            },
            json={
                "from": "recordshelf <hello@record-shelf.com>",
                "to": ["support@record-shelf.com"],
                "subject": "[recordshelf support] Need help",
                "text": "Hello support.",
                "reply_to": ["sender@example.com"],
            },
            timeout=10,
        )
        response.raise_for_status.assert_called_once_with()

    @override_settings(RESEND_API_KEY="")
    def test_support_email_requires_resend_api_key(self):
        with self.assertRaises(ValueError):
            send_support_email_via_resend(
                subject="Missing key",
                body="Hello support.",
                reply_to="sender@example.com",
            )


class ResendPasswordResetEmailTests(SimpleTestCase):
    @override_settings(
        RESEND_API_KEY="re_test",
        RESEND_API_URL="https://api.resend.com/emails",
        RESEND_FROM_EMAIL="recordshelf <hello@record-shelf.com>",
        EMAIL_TIMEOUT=10,
    )
    @patch("users.email.requests.post")
    def test_password_reset_email_posts_to_resend_api(self, mock_post):
        user = Mock()
        user.get_username.return_value = "swag"
        response = Mock()
        response.json.return_value = {"id": "email_456"}
        mock_post.return_value = response

        ResendPasswordResetForm().send_mail(
            "registration/password_reset_subject.txt",
            "registration/password_reset_email.txt",
            {
                "user": user,
                "protocol": "https",
                "domain": "record-shelf.com",
                "uid": "abc",
                "token": "token-123",
            },
            None,
            "user@example.com",
        )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["from"], "recordshelf <hello@record-shelf.com>")
        self.assertEqual(payload["to"], ["user@example.com"])
        self.assertEqual(payload["subject"], "Reset your recordshelf password")
        self.assertIn("https://record-shelf.com/accounts/reset/abc/token-123/", payload["text"])
        self.assertNotIn("reply_to", payload)
        response.raise_for_status.assert_called_once_with()
