from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('edit/', views.edit_profile, name='edit_profile'),
    path('change-password/', views.change_password, name='change_password'),

    path('verify-otp/', views.verify_otp, name='verify_otp'),

    # ── Forgot Password ────────────────────────────────────────
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('forgot-password/verify/', views.forgot_password_verify_otp, name='forgot_password_verify_otp'),
    path('forgot-password/reset/', views.forgot_password_reset, name='forgot_password_reset'),
]

