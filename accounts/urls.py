from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),

    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/',views.profile,name='profile'),

     path("2fa/verify/", views.verify_otp,  name="verify_otp"),
    


     path('edit/', views.edit_profile, name='edit_profile'),
]
