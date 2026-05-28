import hashlib
import mimetypes
from io import BytesIO
from urllib.parse import urlparse

import posthog
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView
from django.contrib.auth.views import LoginView, PasswordResetView
from .forms import CustomUserCreationForm, DeleteAccountForm, ResendVerificationForm, SupportContactForm, User, VerifiedAuthenticationForm
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import ProfileEditForm
from django.contrib.auth import logout
from .models import Activity
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.core.mail import EmailMessage
from django.utils import timezone
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseBadRequest
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_GET, require_POST
from .tokens import account_deletion_token, email_verification_token

SHARE_IMAGE_TIMEOUT = 8
SHARE_IMAGE_CACHE_TIMEOUT = 60 * 60 * 24
SHARE_IMAGE_MAX_BYTES = 6 * 1024 * 1024
SHARE_IMAGE_ALLOWED_HOST_SUFFIXES = (
    "discogs.com",
    "scdn.co",
)
SHARE_IMAGE_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
RECORDSHELF_USERNAME = "recordshelf"


def establish_recordshelf_mutual_follow(user):
    if not user or not user.is_active or not user.email_verified:
        return False

    recordshelf_user = User.objects.filter(username__iexact=RECORDSHELF_USERNAME).first()
    if not recordshelf_user or recordshelf_user.pk == user.pk:
        return False

    user.following.add(recordshelf_user)
    recordshelf_user.following.add(user)
    return True


class VerifiedLoginView(LoginView):
    template_name = 'registration/login.html'
    authentication_form = VerifiedAuthenticationForm

    def form_valid(self, form):
        user = form.get_user()
        is_first_login = user.last_login is None
        response = super().form_valid(form)
        if is_first_login and establish_recordshelf_mutual_follow(user):
            messages.info(
                self.request,
                "You're now following @recordshelf for featured collections, updates, and community picks.",
            )
        return response

class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    template_name = 'registration/signup.html'

    def form_valid(self, form):
        user = form.save(commit=False)
        user.is_active = False
        user.email_verified = False
        user.email_verified_at = None
        user.save()
        try:
            send_email_verification(self.request, user)
        except Exception:
            messages.error(self.request, "Your account was created, but the verification email could not be sent. Please try resending it.")
            return redirect('resend_verification')

        with posthog.new_context():
            posthog.identify_context(str(user.id))
            posthog.capture('user_signed_up')

        messages.success(self.request, "Account created. Check your email to verify your account before logging in.")
        return redirect('email_verification_sent')

User = get_user_model()

class ResendPasswordResetView(PasswordResetView):
    template_name = 'registration/password_reset_form.html'
    email_template_name = 'registration/password_reset_email.txt'
    subject_template_name = 'registration/password_reset_subject.txt'
    success_url = reverse_lazy('password_reset_done')

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except (requests.RequestException, ValueError):
            messages.error(self.request, "Password reset email is not configured yet. Please try again later.")
            return self.form_invalid(form)

def throttle_key(prefix, *parts):
    raw_value = ":".join(str(part or "") for part in parts)
    digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"

def user_from_uid(uidb64):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        return User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None

def send_email_verification(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    verification_url = request.build_absolute_uri(
        reverse('verify_email_short', kwargs={'uidb64': uid, 'token': token})
    )
    body = "\n".join([
        f"Hi {user.username},",
        "",
        "Welcome to recordshelf. Please verify your email address before logging in:",
        verification_url,
        "",
        "If you did not create this account, you can ignore this email.",
    ])
    EmailMessage(
        subject="Verify your recordshelf email",
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    ).send(fail_silently=False)

def send_account_deletion_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = account_deletion_token.make_token(user)
    deletion_url = request.build_absolute_uri(
        reverse('confirm_delete_account_short', kwargs={'uidb64': uid, 'token': token})
    )
    body = "\n".join([
        f"Hi {user.username},",
        "",
        "A request was made to permanently delete your recordshelf account.",
        "Open the link below, then use the confirmation button to delete your account:",
        deletion_url,
        "",
        "This will permanently remove your profile, collection, shelf, wishlist, follows, and activity.",
        "If you did not request this, you can ignore this email and your account will remain active.",
    ])
    EmailMessage(
        subject="Confirm recordshelf account deletion",
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    ).send(fail_silently=False)

def send_support_email_via_resend(subject, body, reply_to):
    return EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.RESEND_FROM_EMAIL,
        to=[settings.SUPPORT_EMAIL],
        reply_to=[reply_to],
    ).send(fail_silently=False)

def delete_user_account(user):
    username = user.username
    profile_picture = user.profile_picture
    profile_picture_name = profile_picture.name if profile_picture else ''
    profile_picture_storage = profile_picture.storage if profile_picture else None

    user.delete()
    try:
        if profile_picture_name and profile_picture_storage.exists(profile_picture_name):
            profile_picture_storage.delete(profile_picture_name)
    except Exception:
        pass

    return username

def email_verification_sent(request):
    return render(request, 'registration/email_verification_sent.html')

def verify_email(request, uidb64, token):
    user = user_from_uid(uidb64)
    if user and user.email_verified and user.is_active:
        messages.success(request, "Email already verified. You can log in.")
    elif user and email_verification_token.check_token(user, token):
        user.mark_email_verified()
        messages.success(request, "Email verified. You can log in now.")
    else:
        messages.error(request, "That verification link is invalid or expired. Please request a new one.")
    return redirect('login')

def resend_verification(request):
    form = ResendVerificationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email'].strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if user and not user.email_verified and cache.add(throttle_key("verify-resend", email), True, 60):
            try:
                send_email_verification(request, user)
            except Exception:
                messages.error(request, "The verification email could not be sent. Please try again later.")
                return redirect('resend_verification')

        messages.success(request, "If a pending account exists for that email, a verification link has been sent.")
        return redirect('login')

    return render(request, 'registration/resend_verification.html', {'form': form})

def confirm_delete_account(request, uidb64, token):
    user = user_from_uid(uidb64)
    if not user or not account_deletion_token.check_token(user, token):
        messages.error(request, "That account deletion link is invalid or expired.")
        return redirect('login')

    if request.method != 'POST':
        return render(request, 'registration/confirm_delete_account.html', {
            'delete_user': user,
            'uidb64': uidb64,
            'token': token,
        })

    username = delete_user_account(user)
    if request.user.is_authenticated and request.user.username == username:
        logout(request)
    messages.success(request, f"Account @{username} has been deleted.")
    return redirect('home')

def support_contact(request):
    initial = {}
    if request.user.is_authenticated:
        initial = {
            "name": request.user.get_username(),
            "email": request.user.email,
        }

    form = SupportContactForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        if not settings.SUPPORT_EMAIL:
            messages.error(request, "Support email is not configured yet. Please try again soon.")
        elif not settings.RESEND_API_KEY:
            messages.error(request, "Support email API is not configured yet. Please try again soon.")
        elif not cache.add(
            throttle_key("support-contact", request.META.get("REMOTE_ADDR"), form.cleaned_data["email"]),
            True,
            60,
        ):
            messages.error(request, "Please wait a minute before sending another support message.")
        else:
            topic_label = dict(SupportContactForm.TOPIC_CHOICES).get(form.cleaned_data["topic"], "Support")
            user_line = "Anonymous user"
            if request.user.is_authenticated:
                user_line = f"{request.user.username} (id: {request.user.id})"

            body = "\n".join([
                f"Topic: {topic_label}",
                f"Name: {form.cleaned_data['name']}",
                f"Email: {form.cleaned_data['email']}",
                f"Account: {user_line}",
                "",
                form.cleaned_data["message"],
            ])

            try:
                send_support_email_via_resend(
                    subject=f"[recordshelf support] {form.cleaned_data['subject']}",
                    body=body,
                    reply_to=form.cleaned_data["email"],
                )
            except (requests.RequestException, ValueError):
                messages.error(request, "Your message could not be sent. Please try again later.")
            else:
                user_id = str(request.user.id) if request.user.is_authenticated else 'anonymous'
                with posthog.new_context():
                    posthog.identify_context(user_id)
                    posthog.capture('support_message_sent', properties={
                        'topic': form.cleaned_data.get('topic', ''),
                    })
                messages.success(request, "Thanks, your message was sent.")
                return redirect("support")

    return render(request, "support.html", {
        "form": form,
        "support_email": settings.SUPPORT_EMAIL,
    })

def remove_password_autofocus(form):
    for field in form.fields.values():
        field.widget.attrs.pop('autofocus', None)

def is_allowed_share_image_url(raw_url):
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False

    hostname = parsed.hostname.lower()
    return any(
        hostname == allowed or hostname.endswith(f".{allowed}")
        for allowed in SHARE_IMAGE_ALLOWED_HOST_SUFFIXES
    )

def fetch_share_image_content(raw_url):
    if not raw_url or not is_allowed_share_image_url(raw_url):
        return None

    cache_key = f"share-image:{hashlib.sha256(raw_url.encode('utf-8')).hexdigest()}"
    cached_image = cache.get(cache_key)
    if cached_image is not None:
        return cached_image

    try:
        response = requests.get(
            raw_url,
            headers={"User-Agent": "recordshelf/1.0"},
            timeout=SHARE_IMAGE_TIMEOUT,
        )
    except requests.RequestException:
        return None

    content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
    if (
        response.status_code != 200
        or not is_allowed_share_image_url(response.url)
        or content_type not in SHARE_IMAGE_ALLOWED_CONTENT_TYPES
        or len(response.content) > SHARE_IMAGE_MAX_BYTES
    ):
        return None

    cache.set(cache_key, (content_type, response.content), SHARE_IMAGE_CACHE_TIMEOUT)
    return content_type, response.content

@require_GET
def share_image_proxy(request):
    fetched_image = fetch_share_image_content(request.GET.get("url", "").strip())
    if not fetched_image:
        return HttpResponseBadRequest("Image could not be used.")

    content_type, content = fetched_image
    return HttpResponse(content, content_type=content_type)

def load_share_font(size, bold=False):
    paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()

def text_width(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]

def fit_text(draw, text, font, max_width):
    text = str(text or "")
    if text_width(draw, text, font) <= max_width:
        return text

    ellipsis = "..."
    while text and text_width(draw, f"{text}{ellipsis}", font) > max_width:
        text = text[:-1]
    return f"{text}{ellipsis}" if text else ellipsis

def wrap_text(draw, text, font, max_width, max_lines=2):
    words = str(text or "").split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if text_width(draw, test, font) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
        if len(lines) == max_lines:
            break

    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) == max_lines and words:
        used_words = " ".join(lines).split()
        if len(used_words) < len(words):
            lines[-1] = fit_text(draw, lines[-1], font, max_width)

    return lines

def rounded_image(image, size, radius):
    fitted = ImageOps.fit(image.convert("RGB"), (size, size), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=radius, fill=255)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(fitted, (0, 0), mask)
    return output

def circular_image(image, size):
    fitted = ImageOps.fit(image.convert("RGB"), (size, size), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(fitted, (0, 0), mask)
    return output

def image_from_url(raw_url):
    fetched_image = fetch_share_image_content(raw_url)
    if not fetched_image:
        return None

    try:
        return Image.open(BytesIO(fetched_image[1])).convert("RGB")
    except (OSError, UnidentifiedImageError):
        return None

def image_from_profile(profile_user):
    if not profile_user.profile_picture:
        return None

    try:
        with profile_user.profile_picture.open("rb") as image_file:
            return Image.open(image_file).convert("RGB")
    except (OSError, ValueError, UnidentifiedImageError):
        return None

def draw_centered_text(draw, xy, text, font, fill):
    x, y = xy
    box = draw.textbbox((0, 0), text, font=font)
    draw.text((x - (box[2] - box[0]) / 2, y), text, font=font, fill=fill)

def draw_centered_box_text(draw, box, text, font, fill):
    left, top, right, bottom = box
    text_box = draw.textbbox((0, 0), text, font=font)
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]
    draw.text(
        (
            left + (right - left - text_width) / 2 - text_box[0],
            top + (bottom - top - text_height) / 2 - text_box[1],
        ),
        text,
        font=font,
        fill=fill,
    )

@require_GET
def profile_picture_proxy(request, username):
    profile_user = get_object_or_404(User, username=username)
    if not profile_user.profile_picture:
        return HttpResponseBadRequest("No profile picture.")

    try:
        with profile_user.profile_picture.open("rb") as picture_file:
            content = picture_file.read()
    except (OSError, ValueError):
        return HttpResponseBadRequest("Profile picture could not be used.")

    content_type = mimetypes.guess_type(profile_user.profile_picture.name)[0] or "image/webp"
    if content_type not in SHARE_IMAGE_ALLOWED_CONTENT_TYPES:
        content_type = "image/webp"

    return HttpResponse(content, content_type=content_type)

def make_share_background(size):
    width, height = size
    base = Image.new("RGBA", size, "#09090b")
    draw = ImageDraw.Draw(base)
    for y in range(height):
        blend = y / height
        r = int(9 + blend * 6)
        g = int(9 + blend * 22)
        b = int(11 + blend * 16)
        draw.line((0, y, width, y), fill=(r, g, b, 255))

    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-260, -260, 760, 760), fill=(16, 185, 129, 56))
    glow_draw.ellipse((560, 940, 1540, 1940), fill=(16, 185, 129, 34))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    return Image.alpha_composite(base, glow)

@require_GET
def profile_share_image(request, username):
    profile_user = get_object_or_404(User, username=username)
    full_collection = profile_user.collection.select_related('record', 'record__artist')
    total_records = full_collection.count()

    profile_shelf_record_ids = list(profile_user.shelf.values_list('id', flat=True))
    shelf_items = list(
        profile_user.collection.filter(record_id__in=profile_shelf_record_ids).select_related('record', 'record__artist')
    )
    order_list = profile_user.shelf_order or []
    shelf_items.sort(key=lambda x: order_list.index(x.record.id) if x.record.id in order_list else 999)
    shelf_items = shelf_items[:6]

    favorite_item = None
    if profile_user.favorite_record:
        favorite_item = profile_user.collection.select_related('record', 'record__artist').filter(record=profile_user.favorite_record).first()

    width, height = 1200, 1600
    image = make_share_background((width, height))
    draw = ImageDraw.Draw(image)

    title_font = load_share_font(66, bold=True)
    stat_font = load_share_font(78, bold=True)
    heading_font = load_share_font(24, bold=True)
    body_font = load_share_font(30)
    body_bold_font = load_share_font(34, bold=True)
    small_font = load_share_font(22, bold=True)
    tiny_font = load_share_font(18, bold=True)

    card_margin = 78
    card = (card_margin, 76, width - card_margin, height - 76)
    draw.rounded_rectangle(card, radius=44, fill=(9, 9, 11, 244), outline=(16, 185, 129, 70), width=2)

    card_glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card_glow)
    card_draw.ellipse((30, -80, 660, 480), fill=(16, 185, 129, 38))
    card_draw.ellipse((500, 960, 1260, 1640), fill=(16, 185, 129, 26))
    card_glow = card_glow.filter(ImageFilter.GaussianBlur(50))
    image = Image.alpha_composite(image, card_glow)
    draw = ImageDraw.Draw(image)

    x = card_margin + 58
    y = 146
    profile_size = 118
    profile_image = image_from_profile(profile_user)
    if profile_image:
        image.alpha_composite(circular_image(profile_image, profile_size), (x, y))
        draw.ellipse((x, y, x + profile_size, y + profile_size), outline=(16, 185, 129, 120), width=3)
    else:
        draw.ellipse((x, y, x + profile_size, y + profile_size), fill=(24, 24, 27, 255), outline=(16, 185, 129, 120), width=3)
        draw_centered_box_text(draw, (x, y, x + profile_size, y + profile_size), profile_user.username[:1].upper(), title_font, (52, 211, 153, 255))

    text_x = x + profile_size + 30
    draw.text((text_x, y + 4), "RECORDSHELF", font=small_font, fill=(52, 211, 153, 255))
    draw.text((text_x, y + 34), fit_text(draw, f"@{profile_user.username}", title_font, 600), font=title_font, fill=(255, 255, 255, 255))

    if profile_user.tagline:
        tagline_lines = wrap_text(draw, profile_user.tagline, body_font, 610, max_lines=2)
        line_y = y + 112
        for line in tagline_lines:
            draw.text((text_x, line_y), line, font=body_font, fill=(212, 212, 216, 255))
            line_y += 38

    stat_x = width - card_margin - 190
    draw.text((stat_x, y + 20), str(total_records), font=stat_font, fill=(255, 255, 255, 255))
    draw.text((stat_x + 6, y + 100), f"RECORD{'S' if total_records != 1 else ''}", font=tiny_font, fill=(113, 113, 122, 255))

    draw.line((x, 316, width - card_margin - 58, 316), fill=(255, 255, 255, 28), width=2)

    current_y = 356
    if favorite_item:
        draw.rounded_rectangle((x, current_y, width - card_margin - 58, current_y + 128), radius=26, fill=(6, 78, 59, 72), outline=(16, 185, 129, 62), width=2)
        draw.ellipse((x + 28, current_y + 56, x + 48, current_y + 76), fill=(16, 185, 129, 255))
        cover = image_from_url(favorite_item.record.cover_art_url)
        info_x = x + 70
        if cover:
            image.alpha_composite(rounded_image(cover, 82, 14), (x + 66, current_y + 23))
            info_x = x + 168
        draw.text((info_x, current_y + 24), "CURRENTLY SPINNING", font=tiny_font, fill=(52, 211, 153, 255))
        draw.text((info_x, current_y + 52), fit_text(draw, favorite_item.record.title, body_bold_font, 720), font=body_bold_font, fill=(255, 255, 255, 255))
        draw.text((info_x, current_y + 92), fit_text(draw, favorite_item.record.artist.name, body_font, 720), font=body_font, fill=(161, 161, 170, 255))
        grid_y = 552
    else:
        grid_y = 392

    draw.text((x, grid_y - 48), "MY SHELF", font=small_font, fill=(113, 113, 122, 255))
    draw.text((width - card_margin - 300, grid_y - 48), "RECORD-SHELF.COM", font=tiny_font, fill=(82, 82, 91, 255))

    tile_size = 295
    gap = 34
    for index, item in enumerate(shelf_items):
        row = index // 3
        col = index % 3
        tile_x = x + col * (tile_size + gap)
        tile_y = grid_y + row * 420

        shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle((tile_x + 6, tile_y + 18, tile_x + tile_size + 6, tile_y + tile_size + 18), radius=24, fill=(0, 0, 0, 110))
        shadow = shadow.filter(ImageFilter.GaussianBlur(12))
        image = Image.alpha_composite(image, shadow)
        draw = ImageDraw.Draw(image)

        cover = image_from_url(item.record.cover_art_url)
        if cover:
            image.alpha_composite(rounded_image(cover, tile_size, 24), (tile_x, tile_y))
        else:
            draw.rounded_rectangle((tile_x, tile_y, tile_x + tile_size, tile_y + tile_size), radius=24, fill=(24, 24, 27, 255), outline=(39, 39, 42, 255), width=2)
            draw_centered_text(draw, (tile_x + tile_size / 2, tile_y + 132), "No Art", body_font, (82, 82, 91, 255))

        overlay = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle((0, tile_size - 120, tile_size, tile_size), fill=(0, 0, 0, 92))
        image.alpha_composite(overlay, (tile_x, tile_y))
        draw.rounded_rectangle((tile_x, tile_y, tile_x + tile_size, tile_y + tile_size), radius=24, outline=(39, 39, 42, 210), width=2)

        draw.text((tile_x, tile_y + tile_size + 18), fit_text(draw, item.record.title, body_bold_font, tile_size), font=body_bold_font, fill=(255, 255, 255, 255))
        draw.text((tile_x, tile_y + tile_size + 58), fit_text(draw, item.record.artist.name, body_font, tile_size), font=body_font, fill=(113, 113, 122, 255))

    footer_y = height - 164
    draw.line((x, footer_y, width - card_margin - 58, footer_y), fill=(255, 255, 255, 28), width=2)
    draw.text((x, footer_y + 38), "recordshelf", font=heading_font, fill=(161, 161, 170, 255))

    output = BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    return HttpResponse(output.getvalue(), content_type="image/png")

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
    profile_form = ProfileEditForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)
    delete_account_form = DeleteAccountForm(user=request.user)
    remove_password_autofocus(password_form)

    if request.method == 'POST':
        # Check which form was submitted based on the button's name attribute
        if 'update_profile' in request.POST:
            profile_form = ProfileEditForm(request.POST, request.FILES, instance=request.user)
            
            if profile_form.is_valid():
                user = profile_form.save(commit=False)
                # If the username changed, update the timestamp
                if 'username' in profile_form.changed_data:
                    user.last_username_change = timezone.now()
                if profile_form.cleaned_data.get('reset_profile_picture'):
                    user.profile_picture.delete(save=False)
                    user.profile_picture = None
                user.save()
                profile_form.delete_replaced_profile_picture()
                messages.success(request, "Profile updated successfully!")
                return redirect('edit_profile')
                
        elif 'update_password' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            remove_password_autofocus(password_form)
            
            if password_form.is_valid():
                user = password_form.save()
                # Crucial: This prevents the user from being logged out after changing their password!
                update_session_auth_hash(request, user)
                messages.success(request, "Password updated securely!")
                return redirect('edit_profile')

        elif 'delete_account' in request.POST:
            delete_account_form = DeleteAccountForm(request.POST, user=request.user)

            if delete_account_form.is_valid():
                deletion_email_cache_key = f"delete-account-email:{request.user.pk}"
                if not cache.add(deletion_email_cache_key, True, 300):
                    messages.error(request, "Please wait a few minutes before requesting another deletion email.")
                    return redirect('edit_profile')

                try:
                    send_account_deletion_email(request, request.user)
                except Exception:
                    cache.delete(deletion_email_cache_key)
                    messages.error(request, "Your account deletion email could not be sent. Please try again later.")
                else:
                    with posthog.new_context():
                        posthog.identify_context(str(request.user.id))
                        posthog.capture('account_deletion_requested')
                    messages.success(request, "Check your email to confirm account deletion.")
                    return redirect('edit_profile')
        
    return render(request, 'edit_profile.html', {
        'profile_form': profile_form,
        'password_form': password_form,
        'delete_account_form': delete_account_form,
    })

@login_required
@require_POST
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
        with posthog.new_context():
            posthog.identify_context(str(request.user.id))
            posthog.capture('user_followed')
        messages.success(request, f"You are now following @{user_to_toggle.username}!")

    return redirect('profile', username=username)

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
