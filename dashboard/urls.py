from django.urls import path
from .views import user_dashboard
from . import views

urlpatterns = [
    path('', user_dashboard, name='dashboard'),
    
     path('loan/<int:loan_id>/', views.loan_detail, name='loan_detail'),
]
