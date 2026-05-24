from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='collection')
    record = models.ForeignKey('Record', on_delete=models.CASCADE, related_name='collected_by')
    date_added = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    # Variant tracking
    variant_description = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        help_text="e.g., 180g Black, Pink Marble Splatter, 1973 Original Pressing"
    )
    
    # Rating System (1 to 5 stars)
    rating = models.IntegerField(
        blank=True, 
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="1 to 5 star rating"
    )
    
    # Review Text?
    review = models.TextField(blank=True, null=True)
    
    class Meta:
        unique_together = ('user', 'record')

    def __str__(self):
        return f"{self.user.username}'s copy of {self.record.title}"