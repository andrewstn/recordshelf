from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import SimpleTestCase
from django.test import TestCase
from django.urls import reverse

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
        self.assertIn("Added Absolutely to your collection!", messages)
