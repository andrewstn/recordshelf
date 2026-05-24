from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from collection.models import Artist, Record, CollectionItem

class Command(BaseCommand):
    help = 'Seeds the database with test records and variants'

    def handle(self, *args, **kwargs):
        User = get_user_model()
        user = User.objects.first()

        if not user:
            self.stdout.write(self.style.ERROR("No users found. Create a superuser first!"))
            return

        self.stdout.write("Generating test data...")

        # Create Artists
        pink_floyd, _ = Artist.objects.get_or_create(name="Pink Floyd")
        daft_punk, _ = Artist.objects.get_or_create(name="Daft Punk")
        fleetwood, _ = Artist.objects.get_or_create(name="Fleetwood Mac")
        kendrick, _ = Artist.objects.get_or_create(name="Kendrick Lamar")

        # Records (Using highly stable Wikipedia URLs)
        records_data = [
            (pink_floyd, "The Dark Side of the Moon", 1973, "https://upload.wikimedia.org/wikipedia/en/3/3b/Dark_Side_of_the_Moon.png", "1"),
            (daft_punk, "Random Access Memories", 2013, "https://upload.wikimedia.org/wikipedia/commons/4/49/Daft_Punk_Rockness_2007.JPG", "2"),
            (fleetwood, "Rumours", 1977, "https://upload.wikimedia.org/wikipedia/en/f/fb/FMacRumours.PNG", "3"),
            (kendrick, "Good Kid, M.A.A.D City", 2012, "https://upload.wikimedia.org/wikipedia/commons/0/00/Kendrick_Lamar_Yeezus.jpg", "4"),
        ]

        for artist, title, year, cover, d_id in records_data:
            record, created = Record.objects.get_or_create(
                discogs_id=d_id,
                defaults={'title': title, 'artist': artist, 'release_year': year, 'cover_art_url': cover}
            )

            # Add to Collection with Variants
            variants = {
                "The Dark Side of the Moon": ("180g Remaster, Solid Prism Cover", 5),
                "Random Access Memories": ("10th Anniversary Edition, 180g", 5),
                "Rumours": ("Standard Black, 1977 Pressing", 4),
                "Good Kid, M.A.A.D City": ("Clear 2xLP Vinyl", 5),
            }

            if title in variants:
                desc, rating = variants[title]
                CollectionItem.objects.get_or_create(
                    user=user,
                    record=record,
                    defaults={'variant_description': desc, 'rating': rating}
                )
                
                # Automatically add them to the top 6 shelf for testing
                user.shelf.add(record)

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded database! {user.username} now has 4 records."))