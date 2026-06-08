import hashlib
import logging
import re
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.cache import cache

SEARCH_CACHE_TIMEOUT = 60 * 60 * 12
DETAIL_CACHE_TIMEOUT = 60 * 60 * 24 * 7
ARTIST_CACHE_TIMEOUT = 60 * 60 * 12
REQUEST_TIMEOUT = 8
logger = logging.getLogger(__name__)


def _cache_key(prefix, *parts):
    raw_key = ":".join(str(part) for part in parts)
    cache_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return f"{prefix}:{cache_hash}"


def _normalized_query(query):
    return re.sub(r"\s+", " ", (query or "").strip()).lower()


def fetch_discogs_json(url, params=None, cache_timeout=DETAIL_CACHE_TIMEOUT, cache_prefix="discogs"):
    params_key = urlencode(params or {}, doseq=True)
    cache_key = _cache_key(cache_prefix, url, params_key)
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data

    logger.info("Discogs API cache miss", extra={"url": url, "params": params or {}})
    headers = {
        'User-Agent': 'recordshelf/1.0 +http://127.0.0.1:8000',
        'Authorization': f'Discogs token={settings.DISCOGS_API_TOKEN}'
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return None

    if response.status_code == 200:
        data = response.json()
        cache.set(cache_key, data, cache_timeout)
        return data

    logger.warning("Discogs API error", extra={"status_code": response.status_code, "url": url})
    return None

def search_discogs(query, page=1, sort_by='relevance'):
    """Searches Discogs and returns results along with pagination data."""
    url = "https://api.discogs.com/database/search"
    normalized_query = _normalized_query(query)
    
    # Base parameters - wrap the user query in quotes to force exact-phrase matching globally
    # but only if it's not already wrapped in quotes to prevent double-quoting.
    safe_query = f'"{normalized_query}"' if not (normalized_query.startswith('"') and normalized_query.endswith('"')) else normalized_query
    params = {'q': safe_query, 'type': 'master', 'per_page': 12, 'page': page}
    
    # Sorting combinations
    if sort_by == 'relevance':
        pass # Let Discogs default algorithm rank by text match quality
    elif sort_by == 'popularity':
        pass # Site popularity is applied after results are annotated locally.
    elif sort_by == 'newest':
        params['sort'] = 'year'
        params['sort_order'] = 'desc'
    elif sort_by == 'oldest':
        params['sort'] = 'year'
        params['sort_order'] = 'asc'
        
    data = fetch_discogs_json(
        url,
        params=params,
        cache_timeout=SEARCH_CACHE_TIMEOUT,
        cache_prefix="discogs:search",
    )
    if data:
        # Return a tuple: (the list of records, the pagination dictionary)
        return data.get('results', []), data.get('pagination', {})
        
    return [], {}

def fetch_discogs_master(master_id):
    """Fetches detailed data for a specific master release from Discogs."""
    url = f"https://api.discogs.com/masters/{master_id}"
    
    return fetch_discogs_json(url, cache_timeout=DETAIL_CACHE_TIMEOUT, cache_prefix="discogs:master")

def fetch_discogs_artist(artist_id):
    url = f"https://api.discogs.com/artists/{artist_id}"
    return fetch_discogs_json(url, cache_timeout=ARTIST_CACHE_TIMEOUT, cache_prefix="discogs:artist")

def fetch_discogs_artist_releases(artist_id, page=1):
    url = f"https://api.discogs.com/artists/{artist_id}/releases"
    # type=master doesnt work on artist releases, we could just get them and filter?
    # sort=year and sort_order=desc is good
    params = {"page": page, "per_page": 20, "sort": "year", "sort_order": "desc"}
    data = fetch_discogs_json(
        url,
        params=params,
        cache_timeout=SEARCH_CACHE_TIMEOUT,
        cache_prefix="discogs:artist-releases",
    )
    if data:
        # filter out roles like Appearance? role=Main
        return data.get("releases", []), data.get("pagination", {})
    return [], {}


def search_discogs_artist(name):
    url = "https://api.discogs.com/database/search"
    normalized_name = _normalized_query(name)
    params = {'q': f'"{normalized_name}"', 'type': 'artist', 'per_page': 1}
    data = fetch_discogs_json(
        url,
        params=params,
        cache_timeout=SEARCH_CACHE_TIMEOUT,
        cache_prefix="discogs:artist-search",
    )
    if data:
        return data.get('results', [])
    return []
