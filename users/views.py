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

class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login') 
    template_name = 'registration/signup.html'

User = get_user_model()

def user_profile(request, username):
    profile_user = get_object_or_404(User, username=username)
    
    full_collection = profile_user.collection.all().select_related('record', 'record__artist').order_by('-date_added')
    
    # list() wrapper around the entire query below
    shelf_items = list(
        profile_user.collection.filter(record__in=profile_user.shelf.all()).select_related('record', 'record__artist')
    )
    order_list = profile_user.shelf_order or []
    shelf_items.sort(key=lambda x: order_list.index(x.record.id) if x.record.id in order_list else 999)
    
    favorite_item = None
    if profile_user.favorite_record:
        favorite_item = profile_user.collection.filter(record=profile_user.favorite_record).first()
    
    context = {
        'profile_user': profile_user,
        'shelf_items': shelf_items,
        'favorite_item': favorite_item,
        'full_collection': full_collection,
        'total_records': full_collection.count(),
    }
    return render(request, 'profile.html', context)

@login_required
def edit_profile(request):
    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('profile', username=request.user.username)
    else:
        form = ProfileEditForm(instance=request.user)
        
    return render(request, 'edit_profile.html', {'form': form})

@login_required
def toggle_follow(request, username):
    """Allows a user to follow or unfollow another user."""
    user_to_toggle = get_object_or_404(User, username=username)
    
    # Prevent users from following themselves
    if request.user == user_to_toggle:
        messages.warning(request, "You cannot follow yourself.")
        return redirect('profile', username=username)

    if user_to_toggle in request.user.following.all():
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

@login_required
def social_feed(request):
    """Displays a chronological feed of activity from followed users."""
    # Get users I follow, and add myself to the list
    users_to_show = list(request.user.following.all())
    users_to_show.append(request.user)
    
    # Fetch the latest 50 activities. select_related drastically speeds up database queries!
    activities = Activity.objects.filter(user__in=users_to_show).select_related(
        'user', 'record', 'record__artist'
    )[:50]
    
    return render(request, 'feed.html', {'activities': activities})