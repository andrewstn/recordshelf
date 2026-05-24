from django.urls import path
from . import views

urlpatterns = [
    path('search/', views.search_page, name='search'),
    path('add/', views.add_record, name='add_record'),
    path('album/<int:discogs_id>/', views.album_detail, name='album_detail'),
    path('item/<int:item_id>/edit/', views.edit_item, name='edit_item'),
    path('item/<int:item_id>/remove/', views.remove_item, name='remove_item'),
    path('item/<int:item_id>/toggle-shelf/', views.toggle_shelf, name='toggle_shelf'),
    path('item/<int:item_id>/toggle-favorite/', views.toggle_favorite, name='toggle_favorite'),
    path('update-shelf-order/', views.update_shelf_order, name='update_shelf_order'),
]
