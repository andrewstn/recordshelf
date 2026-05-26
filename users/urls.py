from django.urls import path, include
from .views import SignUpView, user_profile
from users import views

urlpatterns = [
    path('', include('django.contrib.auth.urls')), 
    path('signup/', SignUpView.as_view(), name='signup'),
    
    path('edit/', views.edit_profile, name='edit_profile'),
    path('follow/<str:username>/', views.toggle_follow, name='toggle_follow'),
    path('feed/', views.social_feed, name='feed'),
    path('community/', views.user_directory, name='user_directory'),
    path('share-image/', views.share_image_proxy, name='share_image_proxy'),
    path('<str:username>/profile-picture/', views.profile_picture_proxy, name='profile_picture_proxy'),
    path('<str:username>/share.png', views.profile_share_image, name='profile_share_image'),
    
    # Dynamic profile routing
    # NOTE: These generic <str:username> routes must stay at the bottom of the list
    # so they don't accidentally intercept other predefined routes like /edit/ or /feed/
    path('<str:username>/', user_profile, name='profile'),
    path('<str:username>/followers/', views.followers_list, name='followers_list'),
    path('<str:username>/following/', views.following_list, name='following_list'),
]
