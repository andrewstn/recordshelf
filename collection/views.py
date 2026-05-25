from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from collection.spotify import get_spotify_album_id
from .discogs import search_discogs, fetch_discogs_master, fetch_discogs_artist, fetch_discogs_artist_releases
from .services import add_record_to_collection, get_or_create_record
from .models import CollectionItem, Record
from .forms import CollectionItemForm
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from users.models import Activity
from django.db.models import Count, Avg

def search_page(request):
    query = request.GET.get('q', '')
    page = request.GET.get('page', 1)
    sort_by = request.GET.get('sort', 'relevance')
    
    results = []
    pagination = {}
    popular_records = []
    
    if query:
        # If there's a query, hit the Discogs API (your existing logic)
        results, pagination = search_discogs(query, page, sort_by)
    else:
        # If no query, grab the top 12 most collected records from our local DB
        popular_records = Record.objects.annotate(
            collection_count=Count('collected_by')
        ).order_by('-collection_count')[:12]
        
    user_collection_ids = []
    if request.user.is_authenticated:
        user_collection_ids = [str(did) for did in request.user.collection.values_list('record__discogs_id', flat=True) if did]
        
    return render(request, 'search.html', {
        'query': query,
        'results': results,
        'pagination': pagination,
        'popular_records': popular_records,
        'user_collection_ids': user_collection_ids,
        'current_sort': sort_by,
    })

@login_required
def add_record(request):
    """Processes the button click to save an API result to the database."""
    if request.method == 'POST':
        discogs_id = request.POST.get('discogs_id')
        
        if discogs_id:
            item, created = add_record_to_collection(request.user, discogs_id)
            
            if created:
                if request.user.wishlist.filter(id=item.record.id).exists():
                    request.user.wishlist.remove(item.record)
                Activity.objects.create(user=request.user, activity_type='ADD', record=item.record)
                messages.success(request, f"Added {item.record.title} to your collection!")
            else:
                messages.info(request, f"{item.record.title} is already in your collection.")
                
    # Check if a 'next' url was provided
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url:
        return redirect(next_url)
        
    # Redirect back to the user's profile to see their new addition
    return redirect('profile', username=request.user.username)

def album_detail(request, discogs_id):
    """Fetches and displays canonical master release details from Discogs."""
    album_data = fetch_discogs_master(discogs_id)
    
    if not album_data:
        messages.error(request, "Could not retrieve album details from Discogs.")
        return redirect('search')

    # 1. Initialize default state for guest users
    in_collection = False
    in_wishlist = False
    
    # 2. Safely check user-specific attributes only if authenticated
    if request.user.is_authenticated:
        # Check Collection
        in_collection = CollectionItem.objects.filter(
            user=request.user, 
            record__discogs_id=discogs_id
        ).exists()
        
        # Check Wishlist
        in_wishlist = request.user.wishlist.filter(
            discogs_id=discogs_id
        ).exists()
    
    # 3. Fetch metadata for Spotify integration
    title = album_data.get('title', '')
    artist_name = ''
    if album_data.get('artists'):
        artist_name = album_data['artists'][0].get('name', '')
        
    spotify_id = get_spotify_album_id(title, artist_name)
    
    # Calculate average rating
    average_rating = None
    rating_count = 0
    record = Record.objects.filter(discogs_id=discogs_id).first()
    if record:
        aggregation = record.collected_by.aggregate(avg_rating=Avg('rating'))
        if aggregation['avg_rating'] is not None:
            average_rating = round(aggregation['avg_rating'], 1)
            rating_count = record.collected_by.filter(rating__isnull=False).count()
        
    context = {
        'album': album_data,
        'in_collection': in_collection,
        'in_wishlist': in_wishlist,
        'discogs_id': discogs_id,
        'spotify_id': spotify_id,
        'average_rating': average_rating,
        'rating_count': rating_count,
    }
    return render(request, 'album_detail.html', context)

@login_required
def edit_item(request, item_id):
    """Displays a form to edit variant/rating for a specific collection item."""
    # Ensure the item exists AND belongs to the logged-in user
    item = get_object_or_404(CollectionItem, id=item_id, user=request.user)
    
    if request.method == 'POST':
        form = CollectionItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated your copy of {item.record.title}!")
            return redirect('profile', username=request.user.username)
    else:
        form = CollectionItemForm(instance=item)
        
    return render(request, 'edit_item.html', {'form': form, 'item': item})

@login_required
def remove_item(request, item_id):
    """Removes an item from the user's collection and cleans up their shelf."""
    item = get_object_or_404(CollectionItem, id=item_id, user=request.user)
    
    if request.method == 'POST':
        # Cleanup: If this record is on their shelf or is their favorite, remove it first
        if item.record in request.user.shelf.all():
            request.user.shelf.remove(item.record)
        if request.user.favorite_record == item.record:
            request.user.favorite_record = None
            request.user.save()
            
        item.delete()
        messages.success(request, f"Removed {item.record.title} from your collection.")
        return redirect('profile', username=request.user.username)
        
    # If someone tries to GET this route, redirect them to the edit page safely
    return redirect('edit_item', item_id=item.id)

@login_required
def toggle_shelf(request, item_id):
    """Adds or removes a record from the user's Top 6 shelf."""
    item = get_object_or_404(CollectionItem, id=item_id, user=request.user)
    
    if item.record in request.user.shelf.all():
        request.user.shelf.remove(item.record)
        messages.info(request, f"Removed {item.record.title} from your shelf.")
    else:
        if request.user.shelf.count() >= 6:
            messages.error(request, "Your shelf is full! Remove one first.")
        else:  
            request.user.shelf.add(item.record)
            Activity.objects.create(user=request.user, activity_type='SHELF', record=item.record)
            messages.success(request, f"Added {item.record.title} to your shelf.")
            
    return redirect('profile', username=request.user.username)

@login_required
def toggle_favorite(request, item_id):
    """Sets or unsets a record as the user's all-time favorite (current spin)."""
    item = get_object_or_404(CollectionItem, id=item_id, user=request.user)
    
    if request.method == 'POST':
        # If it's already the favorite, unset it
        if request.user.favorite_record == item.record:
            request.user.favorite_record = None
            messages.info(request, "Removed Current Spin.")
        else:
            request.user.favorite_record = item.record
            Activity.objects.create(user=request.user, activity_type='FAVORITE', record=item.record)
            messages.success(request, f"{item.record.title} is now your Current Spin!")
            
        request.user.save()
            
    return redirect('profile', username=request.user.username)

@login_required
@require_POST
def update_shelf_order(request):
    """Receives an AJAX POST from SortableJS and saves the new shelf order."""
    try:
        data = json.loads(request.body)
        request.user.shelf_order = data.get('order', [])
        request.user.save()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
def toggle_wishlist(request):
    if request.method == 'POST':
        discogs_id = request.POST.get('discogs_id')
        
        # Ensures the record has a title and cover art
        record = get_or_create_record(discogs_id)
        
        if not record:
            messages.error(request, "Could not find this record to add to wishlist.")
            return redirect(request.META.get('HTTP_REFERER', 'search'))
            
        # Toggle the relationship
        if record in request.user.wishlist.all():
            request.user.wishlist.remove(record)
            messages.success(request, f"Removed {record.title} from your wishlist.")
        else:
            request.user.wishlist.add(record)
            # Log the activity
            Activity.objects.create(user=request.user, activity_type='WISHLIST', record=record)
            messages.success(request, f"Added {record.title} to your wishlist!")
            
    # Redirect back to exactly where they came from (the album page)
    return redirect(request.META.get('HTTP_REFERER', 'search'))

from .models import Artist
def artist_detail(request, artist_id):
    # Get local artist if exists
    artist = Artist.objects.filter(discogs_id=artist_id).first()
    
    # Needs to fetch artist data
    discogs_artist = fetch_discogs_artist(artist_id)
    if not discogs_artist:
        messages.error(request, "Could not load artist data from Discogs.")
        return redirect('search')
        
    if artist:
        # Update text/image if we didn't have them
        changed = False
        if not artist.profile_text and discogs_artist.get('profile'):
            artist.profile_text = discogs_artist.get('profile')
            changed = True
        
        images = discogs_artist.get('images', [])
        if not artist.image_url and images:
            artist.image_url = images[0].get('resource_url') or images[0].get('uri')
            changed = True
            
        if changed:
            artist.save()
    else:
        # Create it mapping the discogs ID
        images = discogs_artist.get('images', [])
        image_url = images[0].get('resource_url') or images[0].get('uri') if images else None
        
        artist, created = Artist.objects.get_or_create(name=discogs_artist.get('name', 'Unknown Artist'))
        artist.discogs_id = artist_id
        artist.profile_text = discogs_artist.get('profile')
        artist.image_url = image_url
        artist.save()
        
    # Get releases (albums)
    page = request.GET.get('page', 1)
    releases_data, pagination = fetch_discogs_artist_releases(artist_id, page)
    
    # Filter only main masters
    releases = [r for r in releases_data if r.get('type') == 'master' and r.get('role') == 'Main']
        
    # Count local collectors
    collector_count = Record.objects.filter(artist=artist).aggregate(total=Count('collected_by'))['total'] or 0
    
    context = {
        'artist': artist,
        'discogs_artist': discogs_artist,
        'releases': releases,
        'pagination': pagination,
        'collector_count': collector_count
    }
    return render(request, 'artist_detail.html', context)

def sync_artist(request, local_artist_id):
    from django.conf import settings
    import requests
    
    artist = get_object_or_404(Artist, id=local_artist_id)
    if artist.discogs_id:
        return redirect('artist_detail', artist_id=artist.discogs_id)
        
    url = "https://api.discogs.com/database/search"
    headers = {
        'User-Agent': 'recordshelf/1.0 +http://127.0.0.1:8000',
        'Authorization': f'Discogs token={settings.DISCOGS_API_TOKEN}'
    }
    
    params = {'q': f'"{artist.name}"', 'type': 'artist', 'per_page': 1}
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        results = data.get('results', [])
        if results:
            discogs_id = results[0].get('id')
            artist.discogs_id = str(discogs_id)
            artist.save()
            return redirect('artist_detail', artist_id=discogs_id)
            
    messages.error(request, f"Could not map {artist.name} to a valid Discogs artist.")
    return redirect(request.META.get('HTTP_REFERER', 'home'))
