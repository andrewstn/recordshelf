from unittest.mock import Mock, patch

from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.contrib.messages import get_messages
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from collection.models import Artist, CollectionItem, Record
from .views import send_support_email_via_resend
from .models import CustomUser


class ResendSupportEmailTests(SimpleTestCase):
    @override_settings(
        RESEND_API_KEY="re_test",
        RESEND_API_URL="https://api.resend.com/emails",
        RESEND_FROM_EMAIL="recordshelf <hello@record-shelf.com>",
        SUPPORT_EMAIL="support@record-shelf.com",
        EMAIL_TIMEOUT=10,
        EMAIL_BACKEND="users.email_backend.ResendEmailBackend",
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

        self.assertEqual(result, 1)
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

    @override_settings(EMAIL_BACKEND="users.email_backend.ResendEmailBackend", RESEND_API_KEY="")
    def test_support_email_requires_resend_api_key(self):
        with self.assertRaises(ValueError):
            send_support_email_via_resend(
                subject="Missing key",
                body="Hello support.",
                reply_to="sender@example.com",
            )


class ResendEmailBackendTests(SimpleTestCase):
    @override_settings(
        EMAIL_BACKEND="users.email_backend.ResendEmailBackend",
        RESEND_API_KEY="re_test",
        RESEND_API_URL="https://api.resend.com/emails",
        RESEND_FROM_EMAIL="recordshelf <hello@record-shelf.com>",
        EMAIL_TIMEOUT=10,
    )
    @patch("users.email.requests.post")
    def test_django_email_posts_to_resend_api(self, mock_post):
        response = Mock()
        response.json.return_value = {"id": "email_456"}
        mock_post.return_value = response

        result = EmailMessage(
            subject="Reset your recordshelf password",
            body="Open the reset link.",
            from_email="ignored@example.com",
            to=["user@example.com"],
        ).send()

        self.assertEqual(result, 1)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["from"], "recordshelf <hello@record-shelf.com>")
        self.assertEqual(payload["to"], ["user@example.com"])
        self.assertEqual(payload["subject"], "Reset your recordshelf password")
        self.assertEqual(payload["text"], "Open the reset link.")
        self.assertNotIn("reply_to", payload)
        response.raise_for_status.assert_called_once_with()

    @override_settings(
        EMAIL_BACKEND="users.email_backend.ResendEmailBackend",
        RESEND_API_KEY="re_test",
        RESEND_API_URL="https://api.resend.com/emails",
        RESEND_FROM_EMAIL="recordshelf <hello@record-shelf.com>",
        EMAIL_TIMEOUT=10,
    )
    @patch("users.email.requests.post")
    def test_django_html_email_includes_html_payload(self, mock_post):
        response = Mock()
        response.json.return_value = {"id": "email_789"}
        mock_post.return_value = response

        message = EmailMultiAlternatives(
            subject="HTML email",
            body="Plain fallback.",
            from_email="ignored@example.com",
            to=["user@example.com"],
        )
        message.attach_alternative("<p>HTML body.</p>", "text/html")
        message.send()

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["from"], "recordshelf <hello@record-shelf.com>")
        self.assertEqual(payload["to"], ["user@example.com"])
        self.assertEqual(payload["text"], "Plain fallback.")
        self.assertEqual(payload["html"], "<p>HTML body.</p>")
        response.raise_for_status.assert_called_once_with()


class VerifiedLoginViewTests(TestCase):
    def setUp(self):
        self.recordshelf = CustomUser.objects.create_user(
            username="recordshelf",
            email="hello@record-shelf.com",
            password="password123",
            is_active=True,
            email_verified=True,
        )
        self.user = CustomUser.objects.create_user(
            username="newcollector",
            email="newcollector@example.com",
            password="password123",
            is_active=True,
            email_verified=True,
        )

    def test_first_verified_login_adds_mutual_recordshelf_follow(self):
        response = self.client.post(reverse("login"), {
            "username": "newcollector",
            "password": "password123",
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.user.following.filter(pk=self.recordshelf.pk).exists())
        self.assertTrue(self.recordshelf.following.filter(pk=self.user.pk).exists())
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn(
            "You're now following @recordshelf for featured collections, updates, and community picks.",
            messages,
        )

    def test_later_login_does_not_readd_recordshelf_follow_after_unfollow(self):
        self.user.last_login = timezone.now()
        self.user.save(update_fields=["last_login"])

        response = self.client.post(reverse("login"), {
            "username": "newcollector",
            "password": "password123",
        })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.user.following.filter(pk=self.recordshelf.pk).exists())
        self.assertFalse(self.recordshelf.following.filter(pk=self.user.pk).exists())
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertNotIn(
            "You're now following @recordshelf for featured collections, updates, and community picks.",
            messages,
        )


class ToggleFollowRedirectTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="collector",
            email="collector@example.com",
            password="password123",
        )
        self.other_user = CustomUser.objects.create_user(
            username="neighbor",
            email="neighbor@example.com",
            password="password123",
        )
        self.client.force_login(self.user)

    @patch("users.views.posthog")
    def test_toggle_follow_returns_to_safe_next_url(self, mock_posthog):
        response = self.client.post(reverse("toggle_follow", args=[self.other_user.username]), {
            "next": "/accounts/community/?q=neighbor",
        })

        self.assertRedirects(
            response,
            "/accounts/community/?q=neighbor",
            fetch_redirect_response=False,
        )
        self.assertTrue(self.user.following.filter(pk=self.other_user.pk).exists())
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("You are now following @neighbor!", messages)

    @patch("users.views.posthog")
    def test_toggle_follow_rejects_external_next_url(self, mock_posthog):
        response = self.client.post(reverse("toggle_follow", args=[self.other_user.username]), {
            "next": "https://example.com/",
        })

        self.assertRedirects(
            response,
            reverse("profile", args=[self.other_user.username]),
            fetch_redirect_response=False,
        )


class LinkEmbedTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="embedtest",
            email="embedtest@example.com",
            password="password123",
            tagline="A shelf built for link previews.",
        )
        self.artist = Artist.objects.create(name="Preview Artist", discogs_id="77")
        self.records = []
        for index in range(1, 4):
            record = Record.objects.create(
                title=f"Preview Record {index}",
                artist=self.artist,
                year=2020 + index,
                discogs_id=str(8000 + index),
            )
            CollectionItem.objects.create(user=self.user, record=record)
            self.records.append(record)
        self.user.shelf.set(self.records)

    def test_sitewide_default_embed_meta_tags(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, '<meta property="og:title" content="recordshelf">')
        self.assertContains(
            response,
            "Showcase your vinyl collection. A digital archive for vinyl record enthusiasts. Display your favorite records, discover new pressings, and connect with fellow collectors.",
        )
        self.assertContains(response, reverse("site_share_image"))
        self.assertContains(response, '<meta name="twitter:card" content="summary_large_image">')

    def test_profile_embed_meta_tags(self):
        response = self.client.get(reverse("profile", args=[self.user.username]))

        self.assertContains(response, f'<title>@{self.user.username} - recordshelf</title>')
        self.assertContains(response, f'<meta property="og:title" content="@{self.user.username} on recordshelf">')
        self.assertContains(response, reverse("profile_embed_image", args=[self.user.username]))
        self.assertContains(response, "profile picture and shelf display")

    def test_embed_image_endpoints_return_pngs(self):
        site_response = self.client.get(reverse("site_share_image"))
        profile_response = self.client.get(reverse("profile_embed_image", args=[self.user.username]))

        self.assertEqual(site_response.status_code, 200)
        self.assertEqual(site_response["Content-Type"], "image/png")
        self.assertTrue(site_response.content.startswith(b"\x89PNG"))
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response["Content-Type"], "image/png")
        self.assertTrue(profile_response.content.startswith(b"\x89PNG"))
