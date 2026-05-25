import requests
import base64
import hashlib
import re
from django.conf import settings
from django.core.cache import cache

REQUEST_TIMEOUT = 8
TOKEN_CACHE_TIMEOUT = 60 * 50
ALBUM_CACHE_TIMEOUT = 60 * 60 * 24
NO_SPOTIFY_MATCH = "__no_spotify_match__"

def get_spotify_album_id(album_title, artist_name):
    """Fetches the Spotify Album ID using the title and artist."""
    
    if not getattr(settings, 'SPOTIFY_CLIENT_ID', None) or not getattr(settings, 'SPOTIFY_CLIENT_SECRET', None):
        return None

    # Clean the Discogs data! 
    # Discogs sends "Michael Jackson (2)". This regex strips the " (2)" away.
    clean_artist = re.sub(r'\s\(\d+\)$', '', artist_name).strip()
    # Strip things like "(25th Anniversary Edition)" from titles if present
    clean_title = re.sub(r'\s\([^)]+\)$', '', album_title).strip()
    cache_hash = hashlib.sha256(f"{clean_artist.lower()}:{clean_title.lower()}".encode("utf-8")).hexdigest()
    cache_key = f"spotify:album:{cache_hash}"
    cached_album_id = cache.get(cache_key)
    if cached_album_id is not None:
        if cached_album_id == NO_SPOTIFY_MATCH:
            return None
        return cached_album_id

    # Authenticate and get an Access Token
    token = cache.get("spotify:client_credentials_token")
    if not token:
        auth_string = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
        auth_bytes = auth_string.encode("utf-8")
        auth_base64 = str(base64.b64encode(auth_bytes), "utf-8")

        token_url = "https://accounts.spotify.com/api/token"
        headers = {
            "Authorization": f"Basic {auth_base64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"grant_type": "client_credentials"}

        try:
            token_res = requests.post(token_url, headers=headers, data=data, timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            return None

        if token_res.status_code != 200:
            return None

        token = token_res.json().get("access_token")
        if not token:
            return None
        cache.set("spotify:client_credentials_token", token, TOKEN_CACHE_TIMEOUT)

    # Search Spotify for the Album
    search_url = "https://api.spotify.com/v1/search"
    search_headers = {"Authorization": f"Bearer {token}"}
    
    # Strict Search
    strict_query = f"album:{clean_title} artist:{clean_artist}"
    params = {"q": strict_query, "type": "album", "limit": 1}
    try:
        search_res = requests.get(search_url, headers=search_headers, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return None
    
    if search_res.status_code == 200:
        items = search_res.json().get("albums", {}).get("items", [])
        if items:
            album_id = items[0]["id"]
            cache.set(cache_key, album_id, ALBUM_CACHE_TIMEOUT)
            return album_id
            
    # Loose Fallback Search (if strict fails)
    loose_query = f"{clean_title} {clean_artist}"
    params = {"q": loose_query, "type": "album", "limit": 1}
    try:
        fallback_res = requests.get(search_url, headers=search_headers, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return None
    
    if fallback_res.status_code == 200:
        items = fallback_res.json().get("albums", {}).get("items", [])
        if items:
            album_id = items[0]["id"]
            cache.set(cache_key, album_id, ALBUM_CACHE_TIMEOUT)
            return album_id

    cache.set(cache_key, NO_SPOTIFY_MATCH, ALBUM_CACHE_TIMEOUT)
    return None
