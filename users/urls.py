from django.urls import path, include
from .views import SignUpView, user_profile
from users import views

urlpatterns = [
    path('', include('django.contrib.auth.urls')), 
    path('signup/', SignUpView.as_view(), name='signup'),
    
    # Dynamic profile routing
    path('profile/<str:username>/', user_profile, name='profile'),
    path('edit/', views.edit_profile, name='edit_profile'),

    path('follow/<str:username>/', views.toggle_follow, name='toggle_follow'),
    path('feed/', views.social_feed, name='feed'),
]
