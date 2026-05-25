from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView
from .forms import CustomUserCreationForm, User
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import ProfileEditForm
from django.contrib.auth import login
from .models import Activity
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.utils import timezone

class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login') 
    template_name = 'registration/signup.html'

User = get_user_model()

def remove_password_autofocus(form):
    for field in form.fields.values():
        field.widget.attrs.pop('autofocus', None)

def user_profile(request, username):
    profile_user = get_object_or_404(User, username=username)
    
    # Check which tab is active (default is 'collection')
    current_tab = request.GET.get('tab', 'collection')
    search_query = request.GET.get('q', '').strip()
    
    # Fetch the standard Collection
    full_collection = profile_user.collection.all().select_related('record', 'record__artist').order_by('-date_added')
    
    # Fetch the new Wishlist
    wishlist_items = profile_user.wishlist.all().select_related('artist')
    
    total_records = full_collection.count()

    page_obj = None
    if current_tab == 'wishlist':
        if search_query:
            wishlist_items = wishlist_items.filter(
                Q(title__icontains=search_query) | Q(artist__name__icontains=search_query)
            )
        paginator = Paginator(wishlist_items, 16)
        wishlist_items = paginator.get_page(request.GET.get('page'))
        page_obj = wishlist_items
    else:
        if search_query:
            full_collection = full_collection.filter(
                Q(record__title__icontains=search_query) | Q(record__artist__name__icontains=search_query)
            )
        paginator = Paginator(full_collection, 16)
        full_collection = paginator.get_page(request.GET.get('page'))
        page_obj = full_collection

    profile_shelf_record_ids = list(profile_user.shelf.values_list('id', flat=True))
    shelf_items = list(
        profile_user.collection.filter(record_id__in=profile_shelf_record_ids).select_related('record', 'record__artist')
    )
    order_list = profile_user.shelf_order or []
    shelf_items.sort(key=lambda x: order_list.index(x.record.id) if x.record.id in order_list else 999)
    
    favorite_item = None
    if profile_user.favorite_record:
        favorite_item = profile_user.collection.select_related('record', 'record__artist').filter(record=profile_user.favorite_record).first()
        
    user_collection_discogs_ids = []
    user_wishlist_discogs_ids = []
    owner_shelf_record_ids = []
    favorite_record_id = None
    is_following_profile = False
    if request.user.is_authenticated:
        user_collection_discogs_ids = [str(did) for did in request.user.collection.values_list('record__discogs_id', flat=True) if did]
        user_wishlist_discogs_ids = [str(did) for did in request.user.wishlist.values_list('discogs_id', flat=True) if did]
        if request.user == profile_user:
            owner_shelf_record_ids = list(request.user.shelf.values_list('id', flat=True))
            favorite_record_id = request.user.favorite_record_id
        else:
            is_following_profile = request.user.following.filter(pk=profile_user.pk).exists()
    
    context = {
        'profile_user': profile_user,
        'shelf_items': shelf_items,
        'favorite_item': favorite_item,
        'full_collection': full_collection,
        'wishlist_items': wishlist_items,
        'total_records': total_records,
        'current_tab': current_tab,
        'search_query': search_query,
        'page_obj': page_obj,
        'user_collection_discogs_ids': user_collection_discogs_ids,
        'user_wishlist_discogs_ids': user_wishlist_discogs_ids,
        'owner_shelf_record_ids': owner_shelf_record_ids,
        'favorite_record_id': favorite_record_id,
        'is_following_profile': is_following_profile,
    }
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'partials/profile_collection.html', context)
        
    return render(request, 'profile.html', context)

@login_required
def edit_profile(request):
    if request.method == 'POST':
        # Check which form was submitted based on the button's name attribute
        if 'update_profile' in request.POST:
            profile_form = ProfileEditForm(request.POST, request.FILES, instance=request.user)
            password_form = PasswordChangeForm(request.user) # Blank password form
            remove_password_autofocus(password_form)
            
            if profile_form.is_valid():
                user = profile_form.save(commit=False)
                # If the username changed, update the timestamp
                if 'username' in profile_form.changed_data:
                    user.last_username_change = timezone.now()
                user.save()
                messages.success(request, "Profile updated successfully!")
                return redirect('edit_profile')
                
        elif 'update_password' in request.POST:
            profile_form = ProfileEditForm(instance=request.user) # Blank profile form
            password_form = PasswordChangeForm(request.user, request.POST)
            remove_password_autofocus(password_form)
            
            if password_form.is_valid():
                user = password_form.save()
                # Crucial: This prevents the user from being logged out after changing their password!
                update_session_auth_hash(request, user)
                messages.success(request, "Password updated securely!")
                return redirect('edit_profile')
    else:
        profile_form = ProfileEditForm(instance=request.user)
        password_form = PasswordChangeForm(request.user)
        remove_password_autofocus(password_form)
        
    return render(request, 'edit_profile.html', {
        'profile_form': profile_form,
        'password_form': password_form
    })

@login_required
def toggle_follow(request, username):
    """Allows a user to follow or unfollow another user."""
    user_to_toggle = get_object_or_404(User, username=username)
    
    # Prevent users from following themselves
    if request.user == user_to_toggle:
        messages.warning(request, "You cannot follow yourself.")
        return redirect('profile', username=username)

    if request.user.following.filter(pk=user_to_toggle.pk).exists():
        request.user.following.remove(user_to_toggle)
        messages.info(request, f"You unfollowed @{user_to_toggle.username}.")
    else:
        request.user.following.add(user_to_toggle)
        messages.success(request, f"You are now following @{user_to_toggle.username}!")

    return redirect('profile', username=username)

def signup(request):
    """Handles new user registration."""
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Log the user in immediately after registering
            login(request, user)
            messages.success(request, f"Welcome to the club, {user.username}!")
            return redirect('profile', username=user.username)
    else:
        form = CustomUserCreationForm()
        
    return render(request, 'registration/signup.html', {'form': form})

def social_feed(request):
    """Displays a chronological feed. Personalized for users, global for guests."""
    
    if request.user.is_authenticated:
        # Personalized Feed
        users_to_show = list(request.user.following.all())
        users_to_show.append(request.user)
        activities = Activity.objects.filter(user__in=users_to_show).select_related(
            'user', 'record', 'record__artist'
        )[:50]
        feed_title = "Activity Feed"
        feed_subtitle = "Latest updates from you and the people you follow."
    else:
        # Global Feed for Guests
        activities = Activity.objects.all().select_related(
            'user', 'record', 'record__artist'
        )[:50]
        feed_title = "Global Activity"
        feed_subtitle = "See what the community is spinning right now."
        
    return render(request, 'feed.html', {
        'activities': activities,
        'feed_title': feed_title,
        'feed_subtitle': feed_subtitle
    })


def user_directory(request):
    """Displays a searchable directory of users, ranked by followers."""
    query = request.GET.get('q', '')
    
    # Base query: Annotate every user with their follower count
    users = User.objects.annotate(
        follower_count=Count('followers')
    ).select_related('favorite_record', 'favorite_record__artist')
    
    # Exclude the current logged-in user FIRST (before any slicing)
    if request.user.is_authenticated:
        users = users.exclude(id=request.user.id)
        
    # Apply search filter if there is a query
    if query:
        users = users.filter(username__icontains=query)
        
    # 4. Finally, order the results and apply the slice at the very end!
    users = users.order_by('-follower_count')[:50]
    request_user_following_ids = []
    if request.user.is_authenticated:
        request_user_following_ids = list(request.user.following.values_list('id', flat=True))
        
    return render(request, 'user_directory.html', {
        'users': users,
        'query': query,
        'request_user_following_ids': request_user_following_ids,
    })

def followers_list(request, username):
    """Displays the list of users following a specific profile."""
    profile_user = get_object_or_404(User, username=username)
    
    # Grab the followers and annotate them with their own follower counts
    users = profile_user.followers.annotate(
        follower_count=Count('followers')
    ).select_related('favorite_record', 'favorite_record__artist')
    request_user_following_ids = []
    if request.user.is_authenticated:
        request_user_following_ids = list(request.user.following.values_list('id', flat=True))
    
    return render(request, 'user_list.html', {
        'profile_user': profile_user,
        'users': users,
        'list_type': 'Followers',
        'request_user_following_ids': request_user_following_ids,
    })

def following_list(request, username):
    """Displays the list of users a specific profile is following."""
    profile_user = get_object_or_404(User, username=username)
    
    # Grab the users they are following
    users = profile_user.following.annotate(
        follower_count=Count('followers')
    ).select_related('favorite_record', 'favorite_record__artist')
    request_user_following_ids = []
    if request.user.is_authenticated:
        request_user_following_ids = list(request.user.following.values_list('id', flat=True))
    
    return render(request, 'user_list.html', {
        'profile_user': profile_user,
        'users': users,
        'list_type': 'Following',
        'request_user_following_ids': request_user_following_ids,
    })
