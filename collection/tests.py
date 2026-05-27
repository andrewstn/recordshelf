from unittest.mock import patch

from django.test import SimpleTestCase
from django.test import TestCase

from .models import Artist
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
