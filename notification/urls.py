from django.urls import path
from . import views



urlpatterns = [
    path('notifications/', views.notifications, name='notifications'),

    path('notifications/<int:notif_id>/go/', views.notif_redirect, name='notif_redirect'),
]