from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from .views import send_support_email_via_resend


class ResendSupportEmailTests(SimpleTestCase):
    @override_settings(
        RESEND_API_KEY="re_test",
        RESEND_API_URL="https://api.resend.com/emails",
        RESEND_FROM_EMAIL="recordshelf <hello@record-shelf.com>",
        SUPPORT_EMAIL="support@record-shelf.com",
        EMAIL_TIMEOUT=10,
    )
    @patch("users.views.requests.post")
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
