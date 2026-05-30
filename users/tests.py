from unittest.mock import Mock, patch

from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages import get_messages
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from collection.models import Artist, CollectionItem, Record
from .views import send_support_email_via_resend
from .models import CustomUser
from .tokens import email_verification_token
from .context_processors import onboarding_progress


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


class NavbarActiveStateTests(SimpleTestCase):
    def active_section_for(self, path):
        request = RequestFactory().get(path)
        request.user = AnonymousUser()
        request.resolver_match = resolve(path)
        return onboarding_progress(request)["active_nav_section"]

    def test_top_level_routes_map_to_nav_sections(self):
        self.assertEqual(self.active_section_for("/"), "home")
        self.assertEqual(self.active_section_for("/collection/search/"), "search")
        self.assertEqual(self.active_section_for("/accounts/community/"), "community")
        self.assertEqual(self.active_section_for("/accounts/feed/"), "feed")
        self.assertEqual(self.active_section_for("/getting-started/"), "getting_started")
        self.assertEqual(self.active_section_for("/support/"), "support")

    def test_nested_routes_keep_parent_nav_section_active(self):
        self.assertEqual(self.active_section_for("/collection/album/123/"), "search")
        self.assertEqual(self.active_section_for("/collection/artist/123/"), "search")
        self.assertEqual(self.active_section_for("/collection/item/123/edit/"), "profile")
        self.assertEqual(self.active_section_for("/accounts/edit/"), "profile")
        self.assertEqual(self.active_section_for("/accounts/collector/"), "profile")


class NavbarRenderedStateTests(TestCase):
    def test_home_logo_is_marked_active_on_landing_page(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, '<a href="/" aria-current="page"')

    def test_search_link_is_marked_active_on_search_page(self):
        response = self.client.get(reverse("search"))

        self.assertContains(
            response,
            f'<a href="{reverse("search")}" aria-current="page"',
        )
        self.assertContains(response, "border-emerald-400 text-emerald-400")


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
            "You're now following @recordshelf for featured collections, updates, and community picks. To begin, check out the 'Getting Started' page.",
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
            "You're now following @recordshelf for featured collections, updates, and community picks. To begin, check out the 'Getting Started' page.",
            messages,
        )

    def test_first_login_with_incomplete_onboarding_redirects_to_getting_started(self):
        self.user.onboarding_started_at = timezone.now()
        self.user.save(update_fields=["onboarding_started_at"])

        response = self.client.post(reverse("login"), {
            "username": "newcollector",
            "password": "password123",
        })

        self.assertRedirects(response, reverse("getting_started"), fetch_redirect_response=False)


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


class UserListFollowerCountTests(TestCase):
    def setUp(self):
        self.profile_user = CustomUser.objects.create_user(
            username="profile",
            email="profile@example.com",
            password="password123",
        )
        self.alice = CustomUser.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="password123",
        )
        self.bob = CustomUser.objects.create_user(
            username="bob",
            email="bob@example.com",
            password="password123",
        )
        self.fan_one = CustomUser.objects.create_user(
            username="fanone",
            email="fanone@example.com",
            password="password123",
        )
        self.fan_two = CustomUser.objects.create_user(
            username="fantwo",
            email="fantwo@example.com",
            password="password123",
        )
        self.fan_three = CustomUser.objects.create_user(
            username="fanthree",
            email="fanthree@example.com",
            password="password123",
        )

        self.alice.following.add(self.profile_user)
        self.bob.following.add(self.profile_user)
        self.profile_user.following.add(self.alice, self.bob)
        self.fan_one.following.add(self.alice)
        self.fan_two.following.add(self.alice)
        self.fan_three.following.add(self.bob)

    def test_followers_list_shows_each_users_actual_follower_count(self):
        response = self.client.get(reverse("followers_list", args=[self.profile_user.username]))

        self.assertContains(response, "@alice")
        self.assertContains(response, "3 followers")
        self.assertContains(response, "@bob")
        self.assertContains(response, "2 followers")

    def test_following_list_shows_each_users_actual_follower_count(self):
        response = self.client.get(reverse("following_list", args=[self.profile_user.username]))

        self.assertContains(response, "@alice")
        self.assertContains(response, "3 followers")
        self.assertContains(response, "@bob")
        self.assertContains(response, "2 followers")


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

        self.assertContains(
            response,
            '<meta property="og:title" content="recordshelf | Find records. Share shelves. Spin your favorites.">',
        )
        self.assertContains(
            response,
            "Showcase your vinyl collection. A digital archive for vinyl record enthusiasts. Display your favorite records, discover new pressings, and connect with fellow collectors.",
        )
        self.assertContains(response, '<meta property="og:image:height" content="1200">')
        self.assertContains(response, reverse("site_share_image"))
        self.assertContains(response, '<meta name="twitter:card" content="summary">')

    def test_profile_embed_meta_tags(self):
        response = self.client.get(reverse("profile", args=[self.user.username]))

        self.assertContains(response, f'<title>@{self.user.username} - recordshelf</title>')
        self.assertContains(
            response,
            '<meta property="og:title" content="recordshelf | Find records. Share shelves. Spin your favorites.">',
        )
        self.assertContains(response, f"Check out @{self.user.username}'s vinyl collection on recordshelf.")
        self.assertContains(response, reverse("profile_embed_image", args=[self.user.username]))
        self.assertContains(response, "recordshelf logo")

    def test_embed_image_endpoints_return_pngs(self):
        site_response = self.client.get(reverse("site_share_image"))
        profile_response = self.client.get(reverse("profile_embed_image", args=[self.user.username]))

        self.assertEqual(site_response.status_code, 200)
        self.assertEqual(site_response["Content-Type"], "image/png")
        self.assertTrue(site_response.content.startswith(b"\x89PNG"))
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response["Content-Type"], "image/png")
        self.assertTrue(profile_response.content.startswith(b"\x89PNG"))


class OnboardingTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="starter",
            email="starter@example.com",
            password="password123",
            onboarding_started_at=timezone.now(),
        )
        self.client.force_login(self.user)

    @patch("users.onboarding.capture_onboarding_event")
    def test_new_user_sees_live_checklist_on_getting_started_page(self, mock_capture):
        response = self.client.get(reverse("getting_started"))

        self.assertContains(response, "Build your first shelf")
        self.assertContains(response, "0 of 6 steps complete")
        self.assertContains(response, "Upload a profile picture")
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.onboarding_viewed_at)
        mock_capture.assert_called_once_with(self.user, "getting_started_viewed")

    def test_landing_page_stays_clean_for_authenticated_user(self):
        response = self.client.get(reverse("home"))

        self.assertNotContains(response, "Build your first shelf")
        self.assertContains(response, "Getting Started 0/6")

    def test_anonymous_user_does_not_see_checklist_or_nav_link(self):
        self.client.logout()

        response = self.client.get(reverse("home"))

        self.assertNotContains(response, "Build your first shelf")
        self.assertNotContains(response, "Getting Started")

    def test_getting_started_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("getting_started"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('getting_started')}",
            fetch_redirect_response=False,
        )

    @patch("users.onboarding.capture_onboarding_event")
    def test_completed_steps_are_computed_from_existing_data(self, mock_capture):
        self.user.tagline = "Always digging."
        self.user.save(update_fields=["tagline"])

        response = self.client.get(reverse("getting_started"))

        checklist = response.context["onboarding_checklist"]
        statuses = {step["key"]: step["completed"] for step in checklist["steps"]}
        self.assertTrue(statuses["tagline"])
        self.assertFalse(statuses["collection"])
        self.assertContains(response, "1 of 6 steps complete")

    @patch("users.onboarding.capture_onboarding_event")
    def test_all_complete_user_is_marked_complete_and_checklist_hides(self, mock_capture):
        artist = Artist.objects.create(name="Starter Artist")
        record = Record.objects.create(title="Starter Record", artist=artist, discogs_id="101")
        CollectionItem.objects.create(user=self.user, record=record, rating=5)
        self.user.profile_picture = "profiles/starter.webp"
        self.user.tagline = "Always digging."
        self.user.favorite_record = record
        self.user.save(update_fields=["profile_picture", "tagline", "favorite_record"])
        self.user.shelf.add(record)

        response = self.client.get(reverse("home"))

        self.assertNotContains(response, "Build your first shelf")
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.onboarding_completed_at)
        mock_capture.assert_called_once_with(self.user, "onboarding_completed")
        self.assertNotContains(response, "Getting Started")

    @patch("users.views.capture_onboarding_event")
    def test_step_click_is_tracked_and_redirects(self, mock_capture):
        response = self.client.get(reverse("onboarding_step", args=["profile-picture"]))

        self.assertRedirects(response, reverse("edit_profile"), fetch_redirect_response=False)
        mock_capture.assert_called_once_with(
            self.user,
            "onboarding_step_clicked",
            step="profile-picture",
        )


class SignupOnboardingTests(TestCase):
    @patch("users.views.posthog")
    @patch("users.views.send_email_verification")
    def test_signup_starts_onboarding(self, mock_send_email_verification, mock_posthog):
        response = self.client.post(reverse("signup"), {
            "username": "brandnew",
            "email": "brandnew@example.com",
            "password1": "valid-password-123",
            "password2": "valid-password-123",
        })

        self.assertRedirects(response, reverse("email_verification_sent"))
        user = CustomUser.objects.get(username="brandnew")
        self.assertIsNotNone(user.onboarding_started_at)

    def test_successful_verification_sends_user_to_login_then_getting_started(self):
        user = CustomUser.objects.create_user(
            username="pending",
            email="pending@example.com",
            password="password123",
            is_active=False,
            email_verified=False,
            onboarding_started_at=timezone.now(),
        )
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)

        response = self.client.get(reverse("verify_email", args=[uid, token]))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('getting_started')}",
            fetch_redirect_response=False,
        )
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.email_verified)
