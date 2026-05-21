from django.urls import path
from . import views
from loans import admin_views,review_views
from loans.kyc_views import kyc_verify_page, kyc_verify_ajax, kyc_redo
from loans.views import finalize_loan

from loans.admin_views import loan_ocr_debug, kyc_comparison_board, admin_loan_detail, admin_kyc_approve, admin_reevaluate_loan, admin_delete_loan,admin_analytics

from loans.admin_views import admin_nav

urlpatterns = [
    path('admin/nav/', admin_nav, name='admin_nav'),
     
    path('apply/', views.apply_loan, name='loan_apply'),
    path('my-loans/', views.loan_list, name='loan_list'),
    path('accept-terms/<int:loan_id>/', views.accept_terms, name='accept_terms'),
  
    path('fund-loan/<int:loan_id>/', views.fund_loan, name='fund_loan'),
    path("loan/result/<int:loan_id>/", views.loan_result, name="loan_result"),
path("check-id/", views.check_id_number, name="check_id_number"),
path('finalize/<int:loan_id>/', finalize_loan, name='finalize_loan'),


  
path("statement/<int:loan_id>/", views.download_statement, name="loan_statement"),
path("repayment/<int:loan_id>/", views.repayment_schedule, name="repayment_schedule"),



path("admin/pending/",admin_views.admin_pending_loans,  name="admin_pending_loans"),
path("admin/dashboard/",admin_views.admin_dashboard,     name="admin_loan_dashboard"),
path("admin/approve/<int:loan_id>/", admin_views.admin_approve_loan,   name="admin_approve_loan"),
path("admin/reject/<int:loan_id>/",  admin_views.admin_reject_loan,    name="admin_reject_loan"),
path("review/<int:loan_id>/",review_views.loan_review_thread,     name="loan_review_thread"),
path("review/<int:loan_id>/respond/",review_views.user_submit_info, name="user_submit_info"),
    path("review/<int:loan_id>/admin-reply/", review_views.admin_reply_thread, name="admin_reply_thread"),

path("admin/request-info/<int:loan_id>/", review_views.admin_request_info_v2, name="admin_request_info"),
  path("admin/loan/<int:loan_id>/detail/", admin_views.admin_loan_detail, name="admin_loan_detail"),
  path('admin/loan/<int:loan_id>/', admin_loan_detail, name='admin_loan_detail_view'),
    path('admin/loan/<int:loan_id>/ocr-debug/', loan_ocr_debug, name='loan_ocr_debug'),
    path('admin/loan/<int:loan_id>/kyc-approve/', admin_kyc_approve, name='admin_kyc_approve'),


path('admin/kyc-board/', kyc_comparison_board, name='kyc_comparison_board'),
 path('admin/analytics/', admin_analytics, name='admin_analytics'),
    path('admin/loan/<int:loan_id>/reevaluate/', admin_reevaluate_loan, name='admin_reevaluate_loan'),
    path('admin/loan/<int:loan_id>/delete/', admin_delete_loan, name='admin_delete_loan'),

path('kyc/redo/', kyc_redo, name='kyc_redo'),
path('credit-history/', views.credit_score_history, name='credit_score_history'),
    path('how-to-apply/', views.loan_tutorial, name='loan_tutorial'),
    # ── BULK ACTIONS ──
    path('admin/bulk-action/', admin_views.admin_bulk_action, name='admin_bulk_action'),
    path('admin/export-loans/', admin_views.admin_export_loans, name='admin_export_loans'),

    # ── USER MANAGEMENT ──
    path('admin/users/', admin_views.admin_user_list, name='admin_user_list'),
    path('admin/users/<int:user_id>/', admin_views.admin_user_detail, name='admin_user_detail'),
    path('admin/users/<int:user_id>/suspend/', admin_views.admin_suspend_user, name='admin_suspend_user'),
    path('admin/users/<int:user_id>/reset-kyc/', admin_views.admin_reset_kyc, name='admin_reset_kyc'),
    path('admin/users/<int:user_id>/set-tier/', admin_views.admin_set_tier, name='admin_set_tier'),

    # ── LOAN MANAGEMENT ──
    path('admin/loan/<int:loan_id>/extend/', admin_views.admin_extend_loan, name='admin_extend_loan'),
    path('admin/loan/<int:loan_id>/default/', admin_views.admin_mark_default, name='admin_mark_default'),
    path('admin/loan/<int:loan_id>/writeoff/', admin_views.admin_write_off, name='admin_write_off'),
    path('admin/loan/<int:loan_id>/reminder/', admin_views.admin_send_reminder, name='admin_send_reminder'),
    path('admin/loan/<int:loan_id>/note/', admin_views.admin_add_note, name='admin_add_note'),
    path('admin/loan/<int:loan_id>/flag/', admin_views.admin_flag_loan, name='admin_flag_loan'),

    # ── SYSTEM CONTROLS ──
    path('admin/system-settings/', admin_views.admin_system_settings, name='admin_system_settings'),


]









