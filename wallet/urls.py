


from django.urls import path
from . import views
from .views import wallet_dashboard, repay_loan,withdraw_to_mpesa

urlpatterns = [
    path('', wallet_dashboard, name='wallet_dashboard'),
    path('repay-loan/<int:loan_id>/', repay_loan, name='repay_loan'),
    path('withdraw/', withdraw_to_mpesa, name='withdraw_to_mpesa'),
    path("transactions/", views.transaction_history, name="transaction_history"),
     path("admin/finance/", views.admin_finance_dashboard, name="admin_finance_dashboard"),
    path("admin/topup/", views.admin_topup, name="admin_topup"),
    path("my/history/", views.user_wallet_history, name="user_wallet_history"),
    path("my/statement/", views.download_user_statement, name="download_user_statement"),


]
