from django.urls import path, include
from .views import SignUpView

urlpatterns = [
    # Gives standard auth URLs like /login/ and /logout/
    path('', include('django.contrib.auth.urls')), 
    path('signup/', SignUpView.as_view(), name='signup'),
]