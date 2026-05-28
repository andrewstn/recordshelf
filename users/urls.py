from django.urls import include, path, reverse_lazy
from django.contrib.auth.views import (
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
)
from .views import ResendPasswordResetView, SignUpView, VerifiedLoginView, user_profile
from users import views

urlpatterns = [
    path('login/', VerifiedLoginView.as_view(), name='login'),
    path('password_reset/', ResendPasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html',
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        success_url=reverse_lazy('password_reset_complete'),
    ), name='password_reset_confirm'),
    path('reset/done/', PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html',
    ), name='password_reset_complete'),
    path('', include('django.contrib.auth.urls')), 
    path('signup/', SignUpView.as_view(), name='signup'),
    path('verify-email/sent/', views.email_verification_sent, name='email_verification_sent'),
    path('verify-email/resend/', views.resend_verification, name='resend_verification'),
    path('verify-email/<uidb64>/<token>/', views.verify_email, name='verify_email'),
    path('delete-account/<uidb64>/<token>/', views.confirm_delete_account, name='confirm_delete_account'),
    
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
