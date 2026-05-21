"""
URL configuration for Ai_Loan_System project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path,include
from django.conf import settings
from django.conf.urls.static import static
from loans.kyc_views import kyc_verify_page, kyc_verify_ajax


urlpatterns = [
    path('admin/', admin.site.urls),
     path('accounts/', include('accounts.urls')),
     path('loans/', include('loans.urls')),
     path('dashboard/', include('dashboard.urls')),
     path('',include('home.urls')),
     path('', include('helpdesk.urls')),
     path('payments/', include('payments.urls')),
     path('wallet/', include('wallet.urls')),
     path('notification/', include('notification.urls')),

     path('app/',include('application.urls')),
     path('bot/',include('bot.urls')),

     path('loans/kyc/', kyc_verify_page, name='kyc_verify'),
    path('loans/kyc/ajax/', kyc_verify_ajax, name='kyc_verify_ajax'),

]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)