from django.urls import path
from . import views

urlpatterns = [
    path('search/', views.search_page, name='search'),
    path('add/', views.add_record, name='add_record'),
    path('album/<int:discogs_id>/', views.album_detail, name='album_detail'),
]
