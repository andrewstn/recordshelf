from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.http import HttpResponse
from django.core.cache import cache
from django.test import SimpleTestCase
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from .spotify import get_spotify_album_id
from .models import Artist, CollectionItem, Record
from .services import get_or_create_record
from .utils import clean_artist_name


class CleanArtistNameTests(SimpleTestCase):
    def test_removes_discogs_numeric_suffix(self):
        self.assertEqual(clean_artist_name("Clairo (2)"), "Clairo")
        self.assertEqual(clean_artist_name("Dijon (7)"), "Dijon")

    def test_leaves_non_discogs_suffixes_unchanged(self):
        self.assertEqual(clean_artist_name("The Band (Live)"), "The Band (Live)")
        self.assertEqual(clean_artist_name("!!!"), "!!!")

    def test_handles_blank_values(self):
        self.assertEqual(clean_artist_name(""), "")
        self.assertIsNone(clean_artist_name(None))


class GetOrCreateRecordArtistCleanupTests(TestCase):
    @patch("collection.services.fetch_discogs_master")
    def test_existing_artist_is_cleaned_by_discogs_id(self, mock_fetch_discogs_master):
        artist = Artist.objects.create(name="Clairo (2)", discogs_id="123")
        mock_fetch_discogs_master.return_value = {
            "title": "Charm",
            "year": 2024,
            "artists": [{"id": "123", "name": "Clairo (2)"}],
            "images": [{"resource_url": "https://example.com/charm.jpg"}],
        }

        record = get_or_create_record("456")

        artist.refresh_from_db()
        self.assertEqual(artist.name, "Clairo")
        self.assertEqual(record.artist, artist)


class ArtistDetailCleanupTests(TestCase):
    @patch("collection.views.fetch_discogs_artist_releases")
    @patch("collection.views.fetch_discogs_artist")
    def test_existing_artist_detail_cleans_database_name(self, mock_fetch_artist, mock_fetch_releases):
        artist = Artist.objects.create(name="EDEN (86)", discogs_id="86")
        mock_fetch_artist.return_value = {"name": "EDEN (86)", "profile": "", "images": []}
        mock_fetch_releases.return_value = ([], {"pages": 1, "page": 1})

        response = self.client.get(reverse("artist_detail", args=[86]))

        self.assertEqual(response.status_code, 200)
        artist.refresh_from_db()
        self.assertEqual(artist.name, "EDEN")
        self.assertContains(response, "EDEN")
        self.assertNotContains(response, "EDEN (86)")


class AlbumDetailCleanupTests(TestCase):
    @patch("collection.views.get_spotify_album_id", return_value=(None, "not_found"))
    @patch("collection.views.fetch_discogs_master")
    @patch("collection.views.posthog")
    def test_album_detail_cleans_discogs_artist_suffixes(
        self,
        mock_posthog,
        mock_fetch_discogs_master,
        mock_get_spotify_album_id,
    ):
        mock_fetch_discogs_master.return_value = {
            "title": "Charm",
            "year": 2024,
            "artists": [{"id": "123", "name": "Clairo (2)"}],
            "images": [],
        }

        response = self.client.get(reverse("album_detail", args=[456]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Clairo")
        self.assertNotContains(response, "Clairo (2)")
        mock_get_spotify_album_id.assert_called_once_with("Charm", "Clairo", include_status=True)

    @patch("collection.views.get_spotify_album_id")
    @patch("collection.views.fetch_discogs_master")
    @patch("collection.views.posthog")
    def test_album_detail_can_use_manual_spotify_album_id(
        self,
        mock_posthog,
        mock_fetch_discogs_master,
        mock_get_spotify_album_id,
    ):
        mock_fetch_discogs_master.return_value = {
            "title": "Blonde",
            "year": 2016,
            "artists": [{"id": "123", "name": "Frank Ocean"}],
            "images": [],
        }

        response = self.client.get(
            reverse("album_detail", args=[1046042]),
            {"spotify_album_id": "3mH6qwIy9crq0I9YQbOuDf"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "open.spotify.com/embed/album/3mH6qwIy9crq0I9YQbOuDf")
        mock_get_spotify_album_id.assert_not_called()


class SpotifyAlbumLookupTests(TestCase):
    class Response:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self.payload = payload or {}

        def json(self):
            return self.payload

    def setUp(self):
        cache.clear()

    @override_settings(SPOTIFY_CLIENT_ID="client", SPOTIFY_CLIENT_SECRET="secret")
    @patch("collection.spotify.requests.get")
    @patch("collection.spotify.requests.post")
    def test_refreshes_cached_token_after_unauthorized_search(self, mock_post, mock_get):
        cache.set("spotify:client_credentials_token", "stale-token")
        mock_post.return_value = self.Response(200, {
            "access_token": "fresh-token",
            "expires_in": 3600,
        })
        mock_get.side_effect = [
            self.Response(401),
            self.Response(200, {"albums": {"items": [{"id": "spotify-album-id"}]}}),
        ]

        album_id = get_spotify_album_id("Charm", "Clairo")

        self.assertEqual(album_id, "spotify-album-id")
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(mock_get.call_args.kwargs["headers"]["Authorization"], "Bearer fresh-token")

    @override_settings(SPOTIFY_CLIENT_ID="client", SPOTIFY_CLIENT_SECRET="secret")
    @patch("collection.spotify.requests.get")
    @patch("collection.spotify.requests.post")
    def test_search_api_errors_are_not_cached_as_missing_albums(self, mock_post, mock_get):
        mock_post.return_value = self.Response(200, {
            "access_token": "token",
            "expires_in": 3600,
        })
        mock_get.side_effect = [
            self.Response(500),
            self.Response(500),
        ]

        self.assertIsNone(get_spotify_album_id("Charm", "Clairo"))
        self.assertIsNone(get_spotify_album_id("Charm", "Clairo"))

        self.assertEqual(mock_get.call_count, 2)

    @override_settings(SPOTIFY_CLIENT_ID="client", SPOTIFY_CLIENT_SECRET="secret")
    @patch("collection.spotify.requests.get")
    @patch("collection.spotify.requests.post")
    def test_rate_limit_status_is_cached_from_retry_after(self, mock_post, mock_get):
        mock_post.return_value = self.Response(200, {
            "access_token": "token",
            "expires_in": 3600,
        })
        response = self.Response(429)
        response.headers = {"Retry-After": "3600"}
        mock_get.return_value = response

        self.assertEqual(get_spotify_album_id("Charm", "Clairo", include_status=True), (None, "rate_limited"))
        self.assertEqual(get_spotify_album_id("Blonde", "Frank Ocean", include_status=True), (None, "rate_limited"))

        self.assertEqual(mock_get.call_count, 1)


class AddRecordRedirectTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="collector",
            email="collector@example.com",
            password="password123",
        )
        self.artist = Artist.objects.create(name="Dijon", discogs_id="7")
        self.record = Record.objects.create(
            title="Absolutely",
            artist=self.artist,
            year=2021,
            discogs_id="123",
        )
        self.item = CollectionItem.objects.create(user=self.user, record=self.record)
        self.client.force_login(self.user)

    @patch("collection.views.posthog")
    @patch("collection.views.add_record_to_collection")
    def test_add_record_returns_to_safe_next_url(self, mock_add_record_to_collection, mock_posthog):
        mock_add_record_to_collection.return_value = (self.item, True)

        response = self.client.post(reverse("add_record"), {
            "discogs_id": "123",
            "next": "/collection/search/?q=dijon&sort=popularity",
        })

        self.assertRedirects(
            response,
            "/collection/search/?q=dijon&sort=popularity",
            fetch_redirect_response=False,
        )
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("Added Absolutely to your crate!", messages)


class SearchPageQueryTests(TestCase):
    def test_popular_records_load_artists_in_the_initial_query(self):
        for index in range(3):
            artist = Artist.objects.create(name=f"Artist {index}", discogs_id=str(index))
            Record.objects.create(
                title=f"Album {index}",
                artist=artist,
                discogs_id=str(index),
            )

        with self.assertNumQueries(1):
            response = self.client.get(reverse("search"))

        self.assertEqual(response.status_code, 200)


class AlbumDetailAnalyticsTests(TestCase):
    album_data = {
        "title": "Absolutely",
        "artists": [{"name": "Dijon"}],
        "images": [],
    }

    @patch("collection.views.render", return_value=HttpResponse("ok"))
    @patch("collection.views.get_spotify_album_id", return_value=(None, "not_found"))
    @patch("collection.views.fetch_discogs_master")
    @patch("collection.views.posthog")
    def test_anonymous_album_view_uses_session_distinct_id(
        self,
        mock_posthog,
        mock_fetch_discogs_master,
        mock_get_spotify_album_id,
        mock_render,
    ):
        mock_fetch_discogs_master.return_value = self.album_data

        response = self.client.get(reverse("album_detail", args=[123]))

        self.assertEqual(response.status_code, 200)
        distinct_id = mock_posthog.identify_context.call_args.args[0]
        self.assertTrue(distinct_id.startswith("anon:"))
        self.assertNotEqual(distinct_id, "anonymous")
        self.assertEqual(distinct_id, f"anon:{self.client.session.session_key}")
        mock_posthog.capture.assert_called_once_with("album_viewed", properties={
            "discogs_id": 123,
            "in_collection": False,
            "in_wishlist": False,
        })

    @patch("collection.views.render", return_value=HttpResponse("ok"))
    @patch("collection.views.get_spotify_album_id", return_value=(None, "not_found"))
    @patch("collection.views.fetch_discogs_master")
    @patch("collection.views.posthog")
    def test_authenticated_album_view_uses_user_distinct_id(
        self,
        mock_posthog,
        mock_fetch_discogs_master,
        mock_get_spotify_album_id,
        mock_render,
    ):
        user = get_user_model().objects.create_user(
            username="collector",
            email="collector@example.com",
            password="password123",
        )
        self.client.force_login(user)
        mock_fetch_discogs_master.return_value = self.album_data

        response = self.client.get(reverse("album_detail", args=[123]))

        self.assertEqual(response.status_code, 200)
        mock_posthog.identify_context.assert_called_once_with(str(user.id))
