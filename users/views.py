from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView
from .forms import CustomUserCreationForm
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import ProfileEditForm

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
