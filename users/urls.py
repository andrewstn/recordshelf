from django.urls import path, include
from .views import SignUpView, user_profile

urlpatterns = [
    path('', include('django.contrib.auth.urls')), 
    path('signup/', SignUpView.as_view(), name='signup'),
    
    # Dynamic profile routing
    path('profile/<str:username>/', user_profile, name='profile'),
]