from django.db import migrations
import re


DISCOGS_ARTIST_SUFFIX_RE = re.compile(r"\s+\(\d+\)$")


def clean_discogs_artist_suffixes(apps, schema_editor):
    Artist = apps.get_model("collection", "Artist")
    for artist in Artist.objects.all().only("id", "name"):
        cleaned_name = DISCOGS_ARTIST_SUFFIX_RE.sub("", artist.name or "").strip()
        if cleaned_name and cleaned_name != artist.name:
            artist.name = cleaned_name
            artist.save(update_fields=["name"])


class Migration(migrations.Migration):

    dependencies = [
        ("collection", "0005_artist_artist_name_lower_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(clean_discogs_artist_suffixes, migrations.RunPython.noop),
    ]
