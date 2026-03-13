from django.urls import path
from . import views

urlpatterns = [
    path('pay/processing-fee/<int:loan_id>/', views.pay_processing_fee, name='pay_processing_fee'),
     path("mpesa/callback/", views.mpesa_callback, name="mpesa_callback"),
    path('disburse/<int:loan_id>/', views.disburse_loan, name='disburse_loan'),
    path('repay/<int:loan_id>/', views.mpesa_repay_loan, name='mpesa_repay_loan'),
    path('mpesa/repayment-callback/', views.repayment_callback, name='repayment_callback'),
]
