from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .discogs import search_discogs, fetch_discogs_master
from .services import add_record_to_collection
from .models import CollectionItem

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