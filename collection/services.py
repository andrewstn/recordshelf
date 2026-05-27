from .models import Record, CollectionItem, Artist
from .discogs import fetch_discogs_master
from .utils import clean_artist_name

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
        
    # Safely get the artist metadata
    artist_name = "Unknown Artist"
    artist_discogs_id = None
    if album_data.get('artists'):
        artist_node = album_data['artists'][0]
        artist_name = clean_artist_name(artist_node.get('name', 'Unknown Artist'))
        artist_discogs_id = artist_node.get('id')
        
    # 1. Get or Create the Artist
    artist = None
    if artist_discogs_id:
        artist = Artist.objects.filter(discogs_id=artist_discogs_id).first()

    if artist:
        fields_to_update = []
        if artist.name != artist_name:
            artist.name = artist_name
            fields_to_update.append('name')
        if fields_to_update:
            artist.save(update_fields=fields_to_update)
    else:
        artist, created = Artist.objects.get_or_create(name=artist_name)
        if not artist.discogs_id and artist_discogs_id:
            artist.discogs_id = artist_discogs_id
            artist.save(update_fields=['discogs_id'])
    
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
