from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser
from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

class CustomUserCreationForm(UserCreationForm):
    # Explicitly add the email field and force it to be required
    email = forms.EmailField(required=True, help_text="Required for account recovery.")

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        # Include email right after username
        fields = ('username', 'email')
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Override the default 150-character limit from Django's AbstractUser
        self.fields['username'].max_length = 20
        self.fields['username'].help_text = "Required. 20 characters or fewer."

User = get_user_model()

class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['profile_picture', 'username', 'tagline', 'theme']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'w-full bg-zinc-900/50 border border-zinc-700 rounded-lg p-3 text-white focus:border-brand focus:ring-1 focus:ring-brand outline-none transition'}),
            'tagline': forms.TextInput(attrs={
                'class': 'w-full bg-zinc-900/50 border border-zinc-700 rounded-lg p-3 text-white focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition',
                'placeholder': 'Vinyl enthusiast...',
                'maxlength': '100'
            }),
            'theme': forms.Select(attrs={'class': 'w-full bg-zinc-900/50 border border-zinc-700 rounded-lg p-3 text-white focus:border-brand outline-none'}),
            'profile_picture': forms.FileInput(attrs={'class': 'w-full text-zinc-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-zinc-800 file:text-white hover:file:bg-zinc-700 transition cursor-pointer'}),
        }

    def clean_username(self):
        new_username = self.cleaned_data.get('username')
        user = self.instance
        
        # If the username is actually being changed
        if new_username != user.username:
            # Check if they have a recorded change and if it's within 30 days
            if user.last_username_change and timezone.now() < user.last_username_change + timedelta(days=30):
                days_left = (user.last_username_change + timedelta(days=30) - timezone.now()).days
                raise forms.ValidationError(f"Username can only be changed once every 30 days. Try again in {days_left} days.")
        return new_username
