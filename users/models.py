from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

class CustomUser(AbstractUser):

    profile_picture = models.ImageField(
        upload_to='profiles/', 
        blank=True,
        null=True
    )
    
    following = models.ManyToManyField(
        'self', 
        symmetrical=False, 
        related_name='followers', 
        blank=True
    )
    
    # Favorite record
    favorite_record = models.ForeignKey(
        'collection.Record', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='favorited_by'
    )
    
    # Top 6 Shelf
    shelf = models.ManyToManyField(
        'collection.Record', 
        related_name='shelved_by', 
        blank=True
    )
    shelf_order = models.JSONField(
        default=list,
        blank=True
        )  # To maintain the order of records on the shelf

    # Wishlist
    wishlist = models.ManyToManyField(
        'collection.Record',
        related_name='wishlisted_by',
        blank=True)

    # Theme preferences
    THEME_CHOICES = (
        ('dark', 'Dark (Default)'),
        ('light', 'Light'),
        ('system', 'System Default'),
    )
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default='dark')

    tagline = models.CharField(max_length=50, blank=True, null=True)

    email_verified = models.BooleanField(default=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    onboarding_started_at = models.DateTimeField(null=True, blank=True)
    onboarding_viewed_at = models.DateTimeField(null=True, blank=True)
    onboarding_dismissed_at = models.DateTimeField(null=True, blank=True)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    # Track when the username was last changed
    last_username_change = models.DateTimeField(null=True, blank=True)

    def mark_email_verified(self):
        self.email_verified = True
        self.email_verified_at = timezone.now()
        self.is_active = True
        self.save(update_fields=['email_verified', 'email_verified_at', 'is_active'])

    def __str__(self):
        return self.username
    
class Activity(models.Model):
    ACTIVITY_TYPES = (
        ('ADD', 'added to their collection'),
        ('SHELF', 'placed on their shelf'),
        ('FAVORITE', 'set as their Top Spin'),
        ('WISHLIST', 'added to their wishlist'),
    )
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=15, choices=ACTIVITY_TYPES)
    # We use a string reference 'collection.Record' to avoid circular import errors
    record = models.ForeignKey('collection.Record', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at'] # Always put the newest activity at the top
        indexes = [
            models.Index(fields=['-created_at'], name='activity_created_desc_idx'),
            models.Index(fields=['user', '-created_at'], name='activity_user_created_idx'),
            models.Index(fields=['activity_type', '-created_at'], name='activity_type_created_idx'),
        ]
        verbose_name_plural = "Activities"
        
    def __str__(self):
        return f"{self.user.username} {self.get_activity_type_display()} {self.record.title}"
    
