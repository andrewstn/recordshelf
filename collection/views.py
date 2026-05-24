from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .discogs import search_discogs, fetch_discogs_master
from .services import add_record_to_collection
from .models import CollectionItem
from .forms import CollectionItemForm

def search_page(request):
    """Handles user search queries, pagination, and hits the Discogs API."""
    query = request.GET.get('q', '')
    
    # Get the page number from the URL, defaulting to 1
    page = request.GET.get('page', 1)
    
    results = []
    pagination = {}
    
    if query:
        results, pagination = search_discogs(query, page)
        
    context = {
        'query': query, 
        'results': results, 
        'pagination': pagination
    }
    return render(request, 'search.html', context)

@login_required
def add_record(request):
    """Processes the button click to save an API result to the database."""
    if request.method == 'POST':
        discogs_id = request.POST.get('discogs_id')
        
        if discogs_id:
            item, created = add_record_to_collection(request.user, discogs_id)
            
            if created:
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

    # Check if the logged-in user already has this in their collection
    in_collection = False
    if request.user.is_authenticated:
        in_collection = CollectionItem.objects.filter(
            user=request.user, 
            record__discogs_id=discogs_id
        ).exists()
        
    context = {
        'album': album_data,
        'in_collection': in_collection,
        'discogs_id': discogs_id
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
            messages.success(request, f"Added {item.record.title} to shelf.")
            
    return redirect('profile', username=request.user.username)

@login_required
def toggle_favorite(request, item_id):
    """Sets or unsets a record as the user's all-time favorite."""
    item = get_object_or_404(CollectionItem, id=item_id, user=request.user)
    
    if request.method == 'POST':
        # If it's already the favorite, unset it
        if request.user.favorite_record == item.record:
            request.user.favorite_record = None
            messages.info(request, "Removed Top Spin.")
        else:
            request.user.favorite_record = item.record
            messages.success(request, f"{item.record.title} is now your Top Spin!")
            
        request.user.save()
            
    return redirect('profile', username=request.user.username)
