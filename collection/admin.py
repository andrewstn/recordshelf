from django.contrib import admin
from .models import Artist, Record, CollectionItem

@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

@admin.register(Record)
class RecordAdmin(admin.ModelAdmin):
    list_display = ('title', 'artist', 'release_year', 'discogs_id')
    # This adds a search bar that can look through titles AND related artist names
    search_fields = ('title', 'artist__name', 'discogs_id')
    # Adds a filter sidebar on the right side
    list_filter = ('release_year',) 

@admin.register(CollectionItem)
class CollectionItemAdmin(admin.ModelAdmin):
    list_display = ('user', 'record', 'date_added')
    search_fields = ('user__username', 'record__title')
    list_filter = ('date_added',)