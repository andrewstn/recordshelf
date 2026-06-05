import posthog
from config.analytics import posthog_distinct_id
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from collection.spotify import get_spotify_album_id
from .discogs import search_discogs, fetch_discogs_master, fetch_discogs_artist, fetch_discogs_artist_releases
from .services import add_record_to_collection, get_or_create_record
from .models import Artist, CollectionItem, Record
from .forms import CollectionItemForm
import json
import re
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from users.models import Activity
from django.db.models import Count, Avg
from .utils import clean_artist_name

SPOTIFY_ALBUM_ID_RE = re.compile(r'^[A-Za-z0-9]{22}$')

def safe_redirect(request, target_url, fallback):
    if target_url and url_has_allowed_host_and_scheme(
        target_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(target_url)
    return redirect(fallback)

def prepare_discogs_search_results(results):
    result_ids = [str(result.get('id')) for result in results if result.get('id')]
    site_counts = {
        str(discogs_id): count
        for discogs_id, count in Record.objects.filter(
            discogs_id__in=result_ids,
        ).annotate(
            site_collection_count=Count('collected_by')
        ).values_list('discogs_id', 'site_collection_count')
    }
    display_artist_names = []
    for result in results:
        full_title = result.get('title', '')
        if ' - ' in full_title:
            display_artist_names.append(clean_artist_name(full_title.split(' - ', 1)[0]))
    local_artists = {
        artist.name.lower(): artist.discogs_id
        for artist in Artist.objects.filter(
            name__in=display_artist_names,
            discogs_id__isnull=False,
        ).exclude(discogs_id='')
    }

    prepared_results = []
    for result in results:
        prepared = result.copy()
        result_id = str(prepared.get('id') or '')
        prepared['site_collection_count'] = site_counts.get(result_id, 0)
        full_title = prepared.get('title', '')
        if ' - ' in full_title:
            artist_name, record_title = full_title.split(' - ', 1)
            prepared['display_artist'] = clean_artist_name(artist_name)
            prepared['display_title'] = record_title.strip()
        else:
            prepared['display_artist'] = ''
            prepared['display_title'] = full_title
        prepared['artist_discogs_id'] = ''
        if prepared['display_artist']:
            local_discogs_id = local_artists.get(prepared['display_artist'].lower())
            if local_discogs_id:
                prepared['artist_discogs_id'] = local_discogs_id
            elif prepared.get('id'):
                master_data = fetch_discogs_master(prepared.get('id'))
                if master_data and master_data.get('artists'):
                    artist_data = master_data['artists'][0]
                    prepared['artist_discogs_id'] = artist_data.get('id') or ''
                    prepared['display_artist'] = clean_artist_name(
                        artist_data.get('name') or prepared['display_artist']
                    )
        prepared_results.append(prepared)
    return prepared_results

def sort_results_by_site_collection(results):
    return sorted(
        results,
        key=lambda result: (
            -result.get('site_collection_count', 0),
            result.get('display_artist', '').lower(),
            result.get('display_title', '').lower(),
        )
    )

def enrich_artist_release_images(releases):
    release_ids = [str(release.get('id')) for release in releases if release.get('id')]
    local_covers = {
        str(discogs_id): cover_url
        for discogs_id, cover_url in Record.objects.filter(
            discogs_id__in=release_ids,
            cover_art_url__isnull=False,
        ).exclude(cover_art_url='').values_list('discogs_id', 'cover_art_url')
    }

    enriched_releases = []
    for release in releases:
        enriched = release.copy()
        release_id = str(enriched.get('id') or '')
        cover_image = local_covers.get(release_id)

        if not cover_image and release_id:
            master_data = fetch_discogs_master(release_id)
            if master_data and master_data.get('images'):
                image = master_data['images'][0]
                cover_image = image.get('resource_url') or image.get('uri')

        enriched['cover_image'] = cover_image or enriched.get('thumb')
        enriched_releases.append(enriched)

    return enriched_releases

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
        results = prepare_discogs_search_results(results)
        if sort_by == 'popularity':
            results = sort_results_by_site_collection(results)
        with posthog.new_context():
            posthog.identify_context(posthog_distinct_id(request))
            posthog.capture('record_searched', properties={
                'result_count': len(results),
                'sort_by': sort_by,
            })
    else:
        # If no query, grab the top 12 most collected records from our local DB
        popular_records = Record.objects.select_related('artist').annotate(
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
@require_POST
def add_record(request):
    """Processes the button click to save an API result to the database."""
    discogs_id = request.POST.get('discogs_id')

    if discogs_id:
        item, created = add_record_to_collection(request.user, discogs_id)

        if created:
            if request.user.wishlist.filter(id=item.record.id).exists():
                request.user.wishlist.remove(item.record)
            Activity.objects.create(user=request.user, activity_type='ADD', record=item.record)
            with posthog.new_context():
                posthog.identify_context(str(request.user.id))
                posthog.capture('record_added_to_collection', properties={
                    'discogs_id': discogs_id,
                })
            messages.success(request, f"Added {item.record.title} to your crate!")
        else:
            messages.info(request, f"{item.record.title} is already in your crate.")
                
    # Check if a 'next' url was provided
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url:
        return safe_redirect(request, next_url, 'search')
        
    # Redirect back to the user's profile to see their new addition
    return redirect('profile', username=request.user.username)

def album_detail(request, discogs_id):
    """Fetches and displays canonical master release details from Discogs."""
    album_data = fetch_discogs_master(discogs_id)
    
    if not album_data:
        messages.error(request, "Could not retrieve album details from Discogs.")
        return redirect('search')

    album_artists = album_data.get('artists') or []
    for artist in album_artists:
        cleaned_name = clean_artist_name(artist.get('name', ''))
        if cleaned_name:
            artist['name'] = cleaned_name

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
        artist_name = clean_artist_name(album_data['artists'][0].get('name', ''))
        
    spotify_override = request.GET.get('spotify_album_id', '').strip()
    if SPOTIFY_ALBUM_ID_RE.match(spotify_override):
        spotify_id = spotify_override
        spotify_status = 'manual'
    else:
        spotify_id, spotify_status = get_spotify_album_id(title, artist_name, include_status=True)
    
    # Calculate average rating
    average_rating = None
    rating_count = 0
    record = Record.objects.filter(discogs_id=discogs_id).first()
    if record:
        aggregation = record.collected_by.aggregate(avg_rating=Avg('rating'))
        if aggregation['avg_rating'] is not None:
            average_rating = round(aggregation['avg_rating'], 1)
            rating_count = record.collected_by.filter(rating__isnull=False).count()
        
    with posthog.new_context():
        posthog.identify_context(posthog_distinct_id(request))
        posthog.capture('album_viewed', properties={
            'discogs_id': discogs_id,
            'in_collection': in_collection,
            'in_wishlist': in_wishlist,
        })

    context = {
        'album': album_data,
        'in_collection': in_collection,
        'in_wishlist': in_wishlist,
        'discogs_id': discogs_id,
        'spotify_id': spotify_id,
        'spotify_status': spotify_status,
        'average_rating': average_rating,
        'rating_count': rating_count,
    }
    return render(request, 'album_detail.html', context)

@login_required
def edit_item(request, item_id):
    """Displays a form to edit variant/rating for a specific collection item."""
    # Ensure the item exists AND belongs to the logged-in user
    item = get_object_or_404(
        CollectionItem.objects.select_related('record', 'record__artist'),
        id=item_id,
        user=request.user,
    )
    
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
@require_POST
def remove_item(request, item_id):
    """Removes an item from the user's collection and cleans up their shelf."""
    item = get_object_or_404(
        CollectionItem.objects.select_related('record'),
        id=item_id,
        user=request.user,
    )
    
    # Cleanup: If this record is on their shelf or is their favorite, remove it first
    if request.user.shelf.filter(pk=item.record_id).exists():
        request.user.shelf.remove(item.record)
    if request.user.favorite_record_id == item.record_id:
        request.user.favorite_record = None
        request.user.save()

    discogs_id = item.record.discogs_id
    item.delete()
    with posthog.new_context():
        posthog.identify_context(str(request.user.id))
        posthog.capture('record_removed_from_collection', properties={
            'discogs_id': discogs_id,
        })
    messages.success(request, f"Removed {item.record.title} from your crate.")
    return redirect('profile', username=request.user.username)

@login_required
@require_POST
def toggle_shelf(request, item_id):
    """Adds or removes a record from the user's Top 6 shelf."""
    item = get_object_or_404(
        CollectionItem.objects.select_related('record'),
        id=item_id,
        user=request.user,
    )
    
    if request.user.shelf.filter(pk=item.record_id).exists():
        request.user.shelf.remove(item.record)
        messages.info(request, f"Removed {item.record.title} from your shelf.")
    else:
        if request.user.shelf.count() >= 6:
            messages.error(request, "Your shelf is full! Remove one first.")
        else:
            request.user.shelf.add(item.record)
            Activity.objects.create(user=request.user, activity_type='SHELF', record=item.record)
            with posthog.new_context():
                posthog.identify_context(str(request.user.id))
                posthog.capture('record_added_to_shelf', properties={
                    'discogs_id': item.record.discogs_id,
                    'shelf_count': request.user.shelf.count(),
                })
            messages.success(request, f"Added {item.record.title} to your shelf.")
            
    return redirect('profile', username=request.user.username)

@login_required
@require_POST
def toggle_favorite(request, item_id):
    """Sets or unsets a record as the user's all-time favorite (current spin)."""
    item = get_object_or_404(
        CollectionItem.objects.select_related('record'),
        id=item_id,
        user=request.user,
    )
    
    # If it's already the favorite, unset it
    if request.user.favorite_record == item.record:
        request.user.favorite_record = None
        messages.info(request, "Removed Current Spin.")
    else:
        request.user.favorite_record = item.record
        Activity.objects.create(user=request.user, activity_type='FAVORITE', record=item.record)
        with posthog.new_context():
            posthog.identify_context(str(request.user.id))
            posthog.capture('current_spin_set', properties={
                'discogs_id': item.record.discogs_id,
            })
        messages.success(request, f"{item.record.title} is now your Current Spin!")

    request.user.save()
            
    return redirect('profile', username=request.user.username)

@login_required
@require_POST
def update_shelf_order(request):
    """Receives an AJAX POST from SortableJS and saves the new shelf order."""
    try:
        data = json.loads(request.body)
        submitted_order = data.get('order', [])
        if not isinstance(submitted_order, list):
            return JsonResponse({'status': 'error', 'message': 'Invalid shelf order.'}, status=400)

        allowed_record_ids = set(request.user.shelf.values_list('id', flat=True))
        sanitized_order = []
        seen_record_ids = set()
        for record_id in submitted_order[:6]:
            try:
                record_id = int(record_id)
            except (TypeError, ValueError):
                continue

            if record_id in allowed_record_ids and record_id not in seen_record_ids:
                sanitized_order.append(record_id)
                seen_record_ids.add(record_id)

        request.user.shelf_order = sanitized_order
        request.user.save()
        return JsonResponse({'status': 'success'})
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON.'}, status=400)

@login_required
@require_POST
def toggle_wishlist(request):
    discogs_id = request.POST.get('discogs_id')

    # Ensures the record has a title and cover art
    record = get_or_create_record(discogs_id)

    if not record:
        messages.error(request, "Could not find this record to add to your wantlist.")
        return safe_redirect(request, request.META.get('HTTP_REFERER'), 'search')

    # Toggle the relationship
    if request.user.wishlist.filter(pk=record.pk).exists():
        request.user.wishlist.remove(record)
        messages.success(request, f"Removed {record.title} from your wantlist.")
    else:
        request.user.wishlist.add(record)
        Activity.objects.create(user=request.user, activity_type='WISHLIST', record=record)
        with posthog.new_context():
            posthog.identify_context(str(request.user.id))
            posthog.capture('record_added_to_wishlist', properties={
                'discogs_id': discogs_id,
            })
        messages.success(request, f"Added {record.title} to your wantlist!")
            
    # Redirect back to exactly where they came from (the album page)
    return safe_redirect(request, request.META.get('HTTP_REFERER'), 'search')

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
        cleaned_name = clean_artist_name(artist.name)
        if cleaned_name and cleaned_name != artist.name:
            artist.name = cleaned_name
            changed = True

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
        
        artist, created = Artist.objects.get_or_create(
            name=clean_artist_name(discogs_artist.get('name', 'Unknown Artist'))
        )
        artist.discogs_id = artist_id
        artist.profile_text = discogs_artist.get('profile')
        artist.image_url = image_url
        artist.save()
        
    # Get releases (albums)
    page = request.GET.get('page', 1)
    releases_data, pagination = fetch_discogs_artist_releases(artist_id, page)
    
    # Filter only main masters
    releases = [r for r in releases_data if r.get('type') == 'master' and r.get('role') == 'Main']
    releases = enrich_artist_release_images(releases)
        
    # Count local collectors
    collector_count = Record.objects.filter(artist=artist).aggregate(total=Count('collected_by'))['total'] or 0

    user_collection_ids = []
    if request.user.is_authenticated:
        user_collection_ids = [
            str(did)
            for did in request.user.collection.values_list('record__discogs_id', flat=True)
            if did
        ]
    
    context = {
        'artist': artist,
        'discogs_artist': discogs_artist,
        'releases': releases,
        'pagination': pagination,
        'collector_count': collector_count,
        'user_collection_ids': user_collection_ids,
    }
    return render(request, 'artist_detail.html', context)

@login_required
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
    response = requests.get(url, headers=headers, params=params, timeout=8)
    
    if response.status_code == 200:
        data = response.json()
        results = data.get('results', [])
        if results:
            discogs_id = results[0].get('id')
            artist.discogs_id = str(discogs_id)
            artist.save()
            return redirect('artist_detail', artist_id=discogs_id)
            
    messages.error(request, f"Could not map {artist.name} to a valid Discogs artist.")
    return safe_redirect(request, request.META.get('HTTP_REFERER'), 'home')
