import requests
from django.conf import settings

def search_discogs(query):
    """Searches the Discogs database for a vinyl release."""
    
    url = "https://api.discogs.com/database/search"
    
    headers = {
        # Discogs requires a custom User-Agent identifying your app
        'User-Agent': 'RecordStoreIO/1.0 +http://127.0.0.1:8000',
        'Authorization': f'Discogs token={settings.DISCOGS_API_TOKEN}'
    }
    
    # Only want to search for master releases on the vinyl format
    params = {
        'q': query,
        'type': 'master',
        'format': 'vinyl',
        'per_page': 5 # Keep it small for now
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        return response.json().get('results', [])
    else:
        print(f"Error {response.status_code}: {response.text}")
        return None