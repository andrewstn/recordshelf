import base64
import hashlib
import logging
import re

import requests
from django.conf import settings
from django.core.cache import cache

REQUEST_TIMEOUT = 8
TOKEN_CACHE_TIMEOUT = 60 * 50
ALBUM_CACHE_TIMEOUT = 60 * 60 * 24 * 7
NO_MATCH_CACHE_TIMEOUT = 60 * 60
NO_SPOTIFY_MATCH = "__no_spotify_match__"
TOKEN_CACHE_KEY = "spotify:client_credentials_token"
RATE_LIMIT_CACHE_KEY = "spotify:search_rate_limited"
MAX_RATE_LIMIT_CACHE_TIMEOUT = 60 * 60 * 12
logger = logging.getLogger(__name__)


def _result(album_id=None, status="unavailable", include_status=False):
    if include_status:
        return album_id, status
    return album_id


def _get_access_token():
    token = cache.get(TOKEN_CACHE_KEY)
    if token:
        return token

    auth_string = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
    auth_bytes = auth_string.encode("utf-8")
    auth_base64 = str(base64.b64encode(auth_bytes), "utf-8")

    token_url = "https://accounts.spotify.com/api/token"
    logger.info("Spotify token cache miss")
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

    payload = token_res.json()
    token = payload.get("access_token")
    if not token:
        return None

    expires_in = payload.get("expires_in", TOKEN_CACHE_TIMEOUT)
    cache_timeout = max(60, min(TOKEN_CACHE_TIMEOUT, int(expires_in) - 60))
    cache.set(TOKEN_CACHE_KEY, token, cache_timeout)
    return token


def _search_album(search_url, token, query):
    search_headers = {"Authorization": f"Bearer {token}"}
    params = {"q": query, "type": "album", "limit": 1}
    try:
        search_res = requests.get(search_url, headers=search_headers, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return None, "error"

    if search_res.status_code == 401:
        return None, "unauthorized"

    if search_res.status_code == 429:
        retry_after = search_res.headers.get("Retry-After")
        try:
            retry_after = int(retry_after)
        except (TypeError, ValueError):
            retry_after = 60 * 10
        retry_after = max(60, min(MAX_RATE_LIMIT_CACHE_TIMEOUT, retry_after))
        cache.set(RATE_LIMIT_CACHE_KEY, True, retry_after)
        return None, "rate_limited"

    if search_res.status_code != 200:
        return None, "error"

    items = search_res.json().get("albums", {}).get("items", [])
    if not items:
        return None, "empty"

    return items[0]["id"], "matched"


def get_spotify_album_id(album_title, artist_name, include_status=False):
    """Fetches the Spotify Album ID using the title and artist."""
    
    if not getattr(settings, 'SPOTIFY_CLIENT_ID', None) or not getattr(settings, 'SPOTIFY_CLIENT_SECRET', None):
        return _result(status="credentials_missing", include_status=include_status)

    if cache.get(RATE_LIMIT_CACHE_KEY):
        return _result(status="rate_limited", include_status=include_status)

    # Clean the Discogs data! 
    # Discogs sends "Michael Jackson (2)". This regex strips the " (2)" away.
    clean_artist = re.sub(r'\s\(\d+\)$', '', artist_name).strip()
    # Strip things like "(25th Anniversary Edition)" from titles if present
    clean_title = re.sub(r'\s\([^)]+\)$', '', album_title).strip()
    cache_hash = hashlib.sha256(f"{clean_artist.lower()}:{clean_title.lower()}".encode("utf-8")).hexdigest()
    cache_key = f"spotify:v2:album:{cache_hash}"
    cached_album_id = cache.get(cache_key)
    if cached_album_id is not None:
        if cached_album_id == NO_SPOTIFY_MATCH:
            return _result(status="not_found", include_status=include_status)
        return _result(cached_album_id, "matched", include_status)

    token = _get_access_token()
    if not token:
        return _result(status="auth_error", include_status=include_status)

    # Search Spotify for the Album
    search_url = "https://api.spotify.com/v1/search"
    logger.info("Spotify album lookup cache miss", extra={"album_title": clean_title, "artist_name": clean_artist})
    queries = (
        f'album:"{clean_title}" artist:"{clean_artist}"',
        f"{clean_title} {clean_artist}",
    )

    saw_empty_response = False
    for query in queries:
        album_id, status = _search_album(search_url, token, query)
        if status == "unauthorized":
            cache.delete(TOKEN_CACHE_KEY)
            token = _get_access_token()
            if not token:
                return _result(status="auth_error", include_status=include_status)
            album_id, status = _search_album(search_url, token, query)

        if album_id:
            cache.set(cache_key, album_id, ALBUM_CACHE_TIMEOUT)
            return _result(album_id, "matched", include_status)

        if status == "empty":
            saw_empty_response = True
        elif status == "rate_limited":
            return _result(status="rate_limited", include_status=include_status)
        elif status == "error" or status == "unauthorized":
            return _result(status="error", include_status=include_status)

    if saw_empty_response:
        cache.set(cache_key, NO_SPOTIFY_MATCH, NO_MATCH_CACHE_TIMEOUT)
        return _result(status="not_found", include_status=include_status)
    return _result(status="unavailable", include_status=include_status)
