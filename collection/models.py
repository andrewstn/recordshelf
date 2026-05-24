from django.db import models
from django.conf import settings

class Artist(models.Model):
    name = models.CharField(max_length=255)
    
    def __str__(self):
        return self.name

class Record(models.Model):
    title = models.CharField(max_length=255)
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='records')
    release_year = models.IntegerField(blank=True, null=True)
    cover_art_url = models.URLField(max_length=500, blank=True, null=True)
    discogs_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    
    def __str__(self):
        return f"{self.title} by {self.artist.name}"

class CollectionItem(models.Model):
    # This links the specific record to a specific user
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='collection')
    record = models.ForeignKey(Record, on_delete=models.CASCADE, related_name='collected_by')
    
    # User-specific data for their copy
    date_added = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        # Prevents a user from adding the exact same record twice (unless you want to allow multiples later!)
        unique_together = ('user', 'record')

    def __str__(self):
        return f"{self.user.username}'s copy of {self.record.title}"