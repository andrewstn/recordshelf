from io import BytesIO
from uuid import uuid4

from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser
from django import forms
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from django.template import loader
from datetime import timedelta
from PIL import Image, ImageOps, UnidentifiedImageError

from .email import send_resend_email

MAX_PROFILE_PICTURE_UPLOAD_SIZE = 2 * 1024 * 1024
PROFILE_PICTURE_SIZE = (512, 512)
PROFILE_PICTURE_QUALITY = 80
USERNAME_MAX_LENGTH = 20
PROFILE_PICTURE_WIDGET_ATTRS = {
    'class': 'w-full text-zinc-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-zinc-800 file:text-white hover:file:bg-zinc-700 transition cursor-pointer',
}

def validate_username_length(username):
    if username and len(username) > USERNAME_MAX_LENGTH:
        raise forms.ValidationError(f"Username must be {USERNAME_MAX_LENGTH} characters or fewer.")
    return username

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
        self.fields['username'].max_length = USERNAME_MAX_LENGTH
        self.fields['username'].widget.attrs['maxlength'] = USERNAME_MAX_LENGTH
        self.fields['username'].help_text = f"Required. {USERNAME_MAX_LENGTH} characters or fewer."

    def clean_username(self):
        return validate_username_length(super().clean_username())

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

class VerifiedAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        'inactive': "Please verify your email before logging in.",
    }

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            user = User.objects.filter(username__iexact=username).first()
            if user is None:
                user = User.objects.filter(email__iexact=username).first()

            if user and user.check_password(password) and (not user.is_active or not user.email_verified):
                raise ValidationError(
                    self.error_messages['inactive'],
                    code='inactive',
                )

        return super().clean()

class ResendVerificationForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full bg-zinc-900 border border-zinc-700 rounded-md p-3 text-white focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition',
            'placeholder': 'you@example.com',
        }),
    )

class ResendPasswordResetForm(PasswordResetForm):
    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        subject = loader.render_to_string(subject_template_name, context)
        subject = ''.join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)
        send_resend_email(
            subject=subject,
            body=body,
            to=to_email,
        )

class SupportContactForm(forms.Form):
    TOPIC_CHOICES = [
        ('help', 'Help with my account'),
        ('bug', 'Report a bug'),
        ('content', 'Content or copyright concern'),
        ('feedback', 'Feedback or feature idea'),
        ('other', 'Something else'),
    ]

    name = forms.CharField(
        max_length=80,
        widget=forms.TextInput(attrs={
            'class': 'w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-white focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition',
            'placeholder': 'Your name',
        }),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-white focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition',
            'placeholder': 'you@example.com',
        }),
    )
    topic = forms.ChoiceField(
        choices=TOPIC_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-white focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition',
        }),
    )
    subject = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={
            'class': 'w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-white focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition',
            'placeholder': 'What can I help with?',
        }),
    )
    message = forms.CharField(
        max_length=3000,
        widget=forms.Textarea(attrs={
            'class': 'w-full min-h-40 bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-white focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none transition resize-y',
            'placeholder': 'Share the details, including any usernames, records, or steps to reproduce if relevant.',
            'rows': 7,
        }),
    )
    website = forms.CharField(
        required=False,
        widget=forms.HiddenInput,
    )

    def clean_website(self):
        if self.cleaned_data.get('website'):
            raise forms.ValidationError("Invalid submission.")
        return ''

class DeleteAccountForm(forms.Form):
    confirm_username = forms.CharField(
        label="Type your username",
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'w-full bg-zinc-950 border border-red-950/70 rounded-lg p-3 text-white focus:border-red-500 focus:ring-1 focus:ring-red-500 outline-none transition',
            'placeholder': 'Enter your username',
            'autocomplete': 'off',
        }),
    )
    password = forms.CharField(
        label="Current password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full bg-zinc-950 border border-red-950/70 rounded-lg p-3 text-white focus:border-red-500 focus:ring-1 focus:ring-red-500 outline-none transition',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_confirm_username(self):
        confirm_username = self.cleaned_data.get('confirm_username', '').strip()
        if self.user and confirm_username != self.user.username:
            raise forms.ValidationError("This must match your username exactly.")
        return confirm_username

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if self.user and not self.user.check_password(password):
            raise forms.ValidationError("Enter your current password.")
        return password

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
            'username': forms.TextInput(attrs={
                'class': 'w-full bg-zinc-900/50 border border-zinc-700 rounded-lg p-3 text-white focus:border-brand focus:ring-1 focus:ring-brand outline-none transition',
                'maxlength': str(USERNAME_MAX_LENGTH),
            }),
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
        new_username = validate_username_length(self.cleaned_data.get('username'))
        user = self.instance
        
        # If the username is actually being changed
        if new_username != user.username:
            # Check if they have a recorded change and if it's within 30 days
            if user.last_username_change and timezone.now() < user.last_username_change + timedelta(days=30):
                days_left = (user.last_username_change + timedelta(days=30) - timezone.now()).days
                raise forms.ValidationError(f"Username can only be changed once every 30 days. Try again in {days_left} days.")
        return new_username
