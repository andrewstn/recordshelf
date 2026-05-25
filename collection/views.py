from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from collection.spotify import get_spotify_album_id
from .discogs import search_discogs, fetch_discogs_master
from .services import add_record_to_collection, get_or_create_record
from .models import CollectionItem, Record
from .forms import CollectionItemForm
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from users.models import Activity
from django.db.models import Count

def search_page(request):
    query = request.GET.get('q', '')
    page = request.GET.get('page', 1)
    
    results = []
    pagination = {}
    popular_records = []
    
    if query:
        # If there's a query, hit the Discogs API (your existing logic)
        results, pagination = search_discogs(query, page)
    else:
        # If no query, grab the top 12 most collected records from our local DB
        popular_records = Record.objects.annotate(
            collection_count=Count('collected_by')
        ).order_by('-collection_count')[:12]
        
    return render(request, 'search.html', {
        'query': query,
        'results': results,
        'pagination': pagination,
        'popular_records': popular_records
    })

@login_required
def add_record(request):
    """Processes the button click to save an API result to the database."""
    if request.method == 'POST':
        discogs_id = request.POST.get('discogs_id')
        
        if discogs_id:
            item, created = add_record_to_collection(request.user, discogs_id)
            
            if created:
                Activity.objects.create(user=request.user, activity_type='ADD', record=item.record)
                messages.success(request, f"Added to your collection!")
            else:
                messages.info(request, f"This record is already in your collection.")
                
    # Redirect back to the user's profile to see their new addition
    return redirect('profile', username=request.user.username)

def album_detail(request, discogs_id):
    """Fetches and displays canonical master release details from Discogs."""
    album_data = fetch_discogs_master(discogs_id)
    
    if not album_data:
        messages.error(request, "Could not retrieve album details from Discogs.")
        return redirect('search')

    # Check if the logged-in user already has this in their collection/wishlist
    in_collection = False
    in_wishlist = False

    if request.user.is_authenticated:
        in_collection = CollectionItem.objects.filter(
            user=request.user, 
            record__discogs_id=discogs_id
        ).exists()
    
    in_wishlist = request.user.wishlist.filter(
        discogs_id=discogs_id
        ).exists()
    
    title = album_data.get('title', '')
    artist_name = ''
    
    # Discogs 'artists' is a list of dictionaries, so we grab the first one safely
    if album_data.get('artists'):
        artist_name = album_data['artists'][0].get('name', '')
        
    spotify_id = get_spotify_album_id(title, artist_name)
        
    context = {
        'album': album_data,
        'in_collection': in_collection,
        'discogs_id': discogs_id,
        'spotify_id': spotify_id,
        'in_wishlist': in_wishlist
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
        messages.info(request, f"Removed {item.record.title} from shelf.")
    else:
        if request.user.shelf.count() >= 6:
            messages.error(request, "Your shelf is full! Remove one first.")
        else:  
            request.user.shelf.add(item.record)
            Activity.objects.create(user=request.user, activity_type='SHELF', record=item.record)
            messages.success(request, f"Added {item.record.title} to shelf.")
            
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
            messages.success(request, "Removed from your wishlist.")
        else:
            request.user.wishlist.add(record)
            # Log the activity
            Activity.objects.create(user=request.user, activity_type='WISHLIST', record=record)
            messages.success(request, "Added to your wishlist!")
            
    # Redirect back to exactly where they came from (the album page)
    return redirect(request.META.get('HTTP_REFERER', 'search'))
