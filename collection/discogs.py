import requests
from django.conf import settings

def search_discogs(query, page=1):
    """Searches Discogs and returns results along with pagination data."""
    url = "https://api.discogs.com/database/search"
    headers = {
        'User-Agent': 'RecordStoreIO/1.0 +http://127.0.0.1:8000',
        'Authorization': f'Discogs token={settings.DISCOGS_API_TOKEN}'
    }
    
    # Added the page parameter
    params = {'q': query, 'type': 'master', 'per_page': 12, 'page': page}
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        # Return a tuple: (the list of records, the pagination dictionary)
        return data.get('results', []), data.get('pagination', {})
        
    return [], {}

def fetch_discogs_master(master_id):
    """Fetches detailed data for a specific master release from Discogs."""
    url = f"https://api.discogs.com/masters/{master_id}"
    
    headers = {
        'User-Agent': 'RecordStoreIO/1.0 +http://127.0.0.1:8000',
        'Authorization': f'Discogs token={settings.DISCOGS_API_TOKEN}'
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error {response.status_code}: {response.text}")
        return None