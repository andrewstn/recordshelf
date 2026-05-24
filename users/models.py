from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
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
    
    # Top 6 Display Shelf
    shelf = models.ManyToManyField(
        'collection.Record', 
        related_name='shelved_by', 
        blank=True
    )

    # Wishlist
    wishlist = models.ManyToManyField('collection.Record', related_name='wishlisted_by', blank=True)

    # Profile Themes
    THEME_CHOICES = [
        ('default', 'Default Dark'),
        ('midnight', 'Midnight Blue'),
        ('sunset', 'Sunset Orange'),
        ('forest', 'Forest Green'),
        ('berry', 'Berry Purple'),
    ]
    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default='default')

    def __str__(self):
        return self.username