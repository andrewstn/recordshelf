from io import BytesIO
from uuid import uuid4

from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser
from django import forms
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PROFILE_PICTURE_UPLOAD_SIZE = 2 * 1024 * 1024
PROFILE_PICTURE_SIZE = (512, 512)
PROFILE_PICTURE_QUALITY = 80
PROFILE_PICTURE_WIDGET_ATTRS = {
    'class': 'w-full text-zinc-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-zinc-800 file:text-white hover:file:bg-zinc-700 transition cursor-pointer',
}

class ProfilePictureField(forms.ImageField):
    def to_python(self, data):
        if data and getattr(data, 'size', 0) > MAX_PROFILE_PICTURE_UPLOAD_SIZE:
            raise forms.ValidationError("Profile picture uploads must be 2 MB or smaller.")
        return super().to_python(data)

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
    profile_picture = ProfilePictureField(
        required=False,
        widget=forms.FileInput(attrs=PROFILE_PICTURE_WIDGET_ATTRS),
    )
    reset_profile_picture = forms.BooleanField(required=False)

    class Meta:
        model = User
        fields = ['profile_picture', 'username', 'tagline']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'w-full bg-zinc-900/50 border border-zinc-700 rounded-lg p-3 text-white focus:border-brand focus:ring-1 focus:ring-brand outline-none transition'}),
            'tagline': forms.TextInput(attrs={
                'class': 'w-full bg-zinc-900/50 border border-zinc-700 rounded-lg p-3 text-white focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition',
                'placeholder': 'Vinyl enthusiast...',
                'maxlength': '50'
            }),
        }

    def clean_profile_picture(self):
        if self.data.get('reset_profile_picture'):
            return self.instance.profile_picture

        uploaded_picture = self.files.get('profile_picture')
        if not uploaded_picture:
            return self.cleaned_data.get('profile_picture')

        try:
            image = Image.open(uploaded_picture)
            image.verify()
        except (OSError, UnidentifiedImageError):
            raise forms.ValidationError("Upload a valid image file.")
        finally:
            uploaded_picture.seek(0)

        return uploaded_picture

    def save(self, commit=True):
        old_picture_name = self.instance.profile_picture.name if self.instance.profile_picture else ''
        user = super().save(commit=False)
        uploaded_picture = self.files.get('profile_picture')
        self._old_profile_picture_name = ''
        self._new_profile_picture_name = ''

        if uploaded_picture and not self.cleaned_data.get('reset_profile_picture'):
            processed_picture = self.process_profile_picture(uploaded_picture)
            filename_prefix = slugify(user.username) or 'profile'
            filename = f"{filename_prefix}-{uuid4().hex}.webp"
            user.profile_picture.save(filename, ContentFile(processed_picture), save=False)
            self._old_profile_picture_name = old_picture_name
            self._new_profile_picture_name = user.profile_picture.name

        if commit:
            user.save()
            self.save_m2m()
            self.delete_replaced_profile_picture()

        return user

    def process_profile_picture(self, uploaded_picture):
        uploaded_picture.seek(0)
        image = Image.open(uploaded_picture)
        image = ImageOps.exif_transpose(image).convert('RGB')
        image = ImageOps.fit(
            image,
            PROFILE_PICTURE_SIZE,
            method=Image.Resampling.LANCZOS,
        )

        output = BytesIO()
        image.save(output, format='WEBP', quality=PROFILE_PICTURE_QUALITY, method=6)
        return output.getvalue()

    def delete_replaced_profile_picture(self):
        if not self._old_profile_picture_name or self._old_profile_picture_name == self._new_profile_picture_name:
            return

        storage = self.instance.profile_picture.storage
        if storage.exists(self._old_profile_picture_name):
            storage.delete(self._old_profile_picture_name)

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
