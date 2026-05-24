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
    """Fetches a user's profile, their Top 6 shelf, and their favorite record."""
    # 404s automatically if someone types a username that doesn't exist
    profile_user = get_object_or_404(User, username=username)
    
    context = {
        'profile_user': profile_user,
        'shelf_records': profile_user.shelf.all(),
        'favorite': profile_user.favorite_record,
    }
    return render(request, 'profile.html', context)