from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    
    # Tells Django where to inject custom fields on the admin page
    fieldsets = UserAdmin.fieldsets + (
        ('Record Store Profile', {
            'fields': ('favorite_record', 'shelf', 'wishlist', 'theme')
        }),
        ('Onboarding', {
            'fields': (
                'onboarding_started_at',
                'onboarding_viewed_at',
                'onboarding_dismissed_at',
                'onboarding_completed_at',
            )
        }),
    )

admin.site.register(CustomUser, CustomUserAdmin)
