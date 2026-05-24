from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser
from django import forms
from django.contrib.auth import get_user_model

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
        fields = ['profile_picture']
        widgets = {
            'profile_picture': forms.FileInput(attrs={
                'class': 'w-full bg-zinc-900 border border-zinc-700 rounded-md p-4 text-white focus:border-brand transition cursor-pointer'
            })
        }
