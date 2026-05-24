from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    following = models.ManyToManyField(
        'self', 
        symmetrical=False, 
        related_name='followers', 
        blank=True
    )
    
    # The single favorite record
    favorite_record = models.ForeignKey(
        'collection.Record', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='favorited_by'
    )
    
    # The Top 6 Display Shelf
    shelf = models.ManyToManyField(
        'collection.Record', 
        related_name='shelved_by', 
        blank=True
    )

    def __str__(self):
        return self.username