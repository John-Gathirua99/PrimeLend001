
from django.urls import path
from . import views

urlpatterns = [
    path('support/', views.create_ticket, name='create_ticket'),
    path('support/my-tickets/', views.my_tickets, name='my_tickets'),
     path('support/<int:ticket_id>/', views.ticket_detail, name='ticket_detail'),
      path('support/<int:ticket_id>/chat/', views.ticket_chat, name='ticket_chat'), 

      path('support/admin/', views.admin_ticket_list, name='admin_ticket_list'),
    path('support/<int:ticket_id>/chat/admin', views.admin_ticket_chat, name='admin_ticket_chat'),
    path('support/<int:ticket_id>/rate/', views.rate_ticket, name='rate_ticket'),
]
