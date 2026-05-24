import requests
import base64
import re
from django.conf import settings

def get_spotify_album_id(album_title, artist_name):
    """Fetches the Spotify Album ID using the title and artist."""
    
    if not getattr(settings, 'SPOTIFY_CLIENT_ID', None) or not getattr(settings, 'SPOTIFY_CLIENT_SECRET', None):
        return None

    # Clean the Discogs data! 
    # Discogs sends "Michael Jackson (2)". This regex strips the " (2)" away.
    clean_artist = re.sub(r'\s\(\d+\)$', '', artist_name).strip()
    # Strip things like "(25th Anniversary Edition)" from titles if present
    clean_title = re.sub(r'\s\([^)]+\)$', '', album_title).strip()

    # Authenticate and get an Access Token
    auth_string = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
    auth_bytes = auth_string.encode("utf-8")
    auth_base64 = str(base64.b64encode(auth_bytes), "utf-8")

    token_url = "https://accounts.spotify.com/api/token"
    headers = {
        "Authorization": f"Basic {auth_base64}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials"}
    
    token_res = requests.post(token_url, headers=headers, data=data)
    if token_res.status_code != 200:
        return None
        
    token = token_res.json().get("access_token")

    # Search Spotify for the Album
    search_url = "https://api.spotify.com/v1/search"
    search_headers = {"Authorization": f"Bearer {token}"}
    
    # Strict Search
    strict_query = f"album:{clean_title} artist:{clean_artist}"
    params = {"q": strict_query, "type": "album", "limit": 1}
    search_res = requests.get(search_url, headers=search_headers, params=params)
    
    if search_res.status_code == 200:
        items = search_res.json().get("albums", {}).get("items", [])
        if items:
            return items[0]["id"]
            
    # Loose Fallback Search (if strict fails)
    loose_query = f"{clean_title} {clean_artist}"
    params = {"q": loose_query, "type": "album", "limit": 1}
    fallback_res = requests.get(search_url, headers=search_headers, params=params)
    
    if fallback_res.status_code == 200:
        items = fallback_res.json().get("albums", {}).get("items", [])
        if items:
            return items[0]["id"]

    return None