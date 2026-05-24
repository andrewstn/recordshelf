from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser
from django import forms
from django.contrib.auth import get_user_model

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('username', 'email')

User = get_user_model()

class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['profile_picture']
        widgets = {
            'profile_picture': forms.FileInput(attrs={
                'class': 'w-full bg-zinc-900 border border-zinc-700 rounded-md p-4 text-white focus:border-brand transition cursor-pointer'
            })
        }
        