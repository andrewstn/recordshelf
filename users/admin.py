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
    )

admin.site.register(CustomUser, CustomUserAdmin)