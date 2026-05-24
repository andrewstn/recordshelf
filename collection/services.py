from .models import Artist, Record, CollectionItem
from .discogs import fetch_discogs_master

def add_record_to_collection(user, discogs_id):
    """
    Checks if a record exists locally. If not, fetches from Discogs.
    Then adds the record to the user's collection.
    """
    # Check if the Record already exists in the database
    record = Record.objects.filter(discogs_id=discogs_id).first()
    
    if not record:
        # If it doesn't exist, fetch the full data from Discogs
        data = fetch_discogs_master(discogs_id)
        if not data:
            return None, False
            
        # Get or create the Artist
        # Discogs data structure puts artists in a list
        artist_name = data['artists'][0]['name']
        artist, created = Artist.objects.get_or_create(name=artist_name)
        
        # Extract the best image (fallback to empty string if none exist)
        cover_url = ""
        if 'images' in data and len(data['images']) > 0:
            cover_url = data['images'][0]['resource_url']
            
        # Create the Record in PostgreSQL
        record = Record.objects.create(
            title=data['title'],
            artist=artist,
            release_year=data.get('year'),
            cover_art_url=cover_url,
            discogs_id=discogs_id
        )
        
    # Link the Record to the User's collection
    # get_or_create prevents adding the exact same record twice to the same user
    collection_item, created = CollectionItem.objects.get_or_create(
        user=user,
        record=record
    )
    
    return collection_item, created