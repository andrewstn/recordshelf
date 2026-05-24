from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import CreateView
from .forms import CustomUserCreationForm
from django.shortcuts import render, get_object_or_404
from django.contrib.auth import get_user_model

class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login') 
    template_name = 'registration/signup.html'

User = get_user_model()

def user_profile(request, username):
    profile_user = get_object_or_404(User, username=username)
    
    full_collection = profile_user.collection.all().select_related('record', 'record__artist').order_by('-date_added')
    
    # NEW: Filter the user's collection items to only include the ones on their shelf
    shelf_items = profile_user.collection.filter(record__in=profile_user.shelf.all()).select_related('record', 'record__artist')
    
    context = {
        'profile_user': profile_user,
        'shelf_items': shelf_items, # Pass the new variable
        'favorite': profile_user.favorite_record,
        'full_collection': full_collection,
        'total_records': full_collection.count(),
    }
    return render(request, 'profile.html', context)
