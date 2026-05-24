from .models import Record, CollectionItem, Artist
from .discogs import fetch_discogs_master

def get_or_create_record(discogs_id):
    """Safely fetches or creates a fully populated Record from Discogs."""
    # Check if we already have it in the local database
    record = Record.objects.filter(discogs_id=discogs_id).first()
    if record:
        return record
        
    # If not, fetch the full details from Discogs
    album_data = fetch_discogs_master(discogs_id)
    if not album_data:
        return None
        
    # Safely get the artist name
    artist_name = "Unknown Artist"
    if album_data.get('artists'):
        artist_name = album_data['artists'][0].get('name', 'Unknown Artist')
        
    # 1. Get or Create the Artist
    artist, _ = Artist.objects.get_or_create(name=artist_name)
    
    # 2. Create the fully populated Record
    record = Record.objects.create(
        discogs_id=discogs_id,
        title=album_data.get('title', 'Unknown Title'),
        artist=artist,
        year=album_data.get('year'),
        # Ensure your dictionary keys match what fetch_discogs_master returns!
        cover_art_url=album_data.get('images', [{}])[0].get('resource_url', '')
    )
    
    return record

def add_record_to_collection(user, discogs_id):
    """Adds a record to a user's collection, returning the item and a boolean."""
    # NOW we use our new helper function!
    record = get_or_create_record(discogs_id)
    
    if not record:
        return None, False
        
    # Create the collection item
    item, created = CollectionItem.objects.get_or_create(
        user=user,
        record=record
    )
    return item, created
