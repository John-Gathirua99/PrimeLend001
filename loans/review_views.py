"""
Add to loans/urls.py:
    from loans.review_views import loan_review_thread, user_submit_info, admin_request_info_v2

    path("review/<int:loan_id>/",         loan_review_thread,    name="loan_review_thread"),
    path("review/<int:loan_id>/respond/", user_submit_info,      name="user_submit_info"),
    path("admin/request-info/<int:loan_id>/", admin_request_info_v2, name="admin_request_info"),
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone

is_admin = user_passes_test(lambda u: u.is_staff, login_url="login")


@login_required
@is_admin
def admin_request_info_v2(request, loan_id):
    """
    Admin requests information from the applicant.
    Sets loan status to 'Info Required' and posts first message to thread.
    """
    from loans.models import LoanApplication, LoanReviewMessage
    from notification.utils import create_notification

    loan = get_object_or_404(LoanApplication, id=loan_id)

    if request.method == "POST":
        info_needed = request.POST.get("info_needed", "").strip()
        if not info_needed:
            messages.error(request, "Please specify what information is needed.")
            return redirect("admin_loan_dashboard")

        # Set status to Info Required
        loan.status = "Info Required"
        loan.save()

        # Post message to thread
        LoanReviewMessage.objects.create(
            loan=loan,
            sender=request.user,
            sender_type="admin",
            message=info_needed,
        )

        create_notification(
            loan.user,
            title="Action Required — Loan #{}".format(loan.id),
            message="Your loan application requires additional information. Please log in to respond.",
            link="/loans/review/{}/".format(loan.id),
        )

        messages.success(request, f"Information request sent to {loan.user.username}.")

    return redirect("admin_loan_dashboard")


@login_required
def loan_review_thread(request, loan_id):
    """
    View the full review message thread for a loan.
    Accessible by the applicant (their loan) or any staff member.
    """
    from loans.models import LoanApplication, LoanReviewMessage

    loan = get_object_or_404(LoanApplication, id=loan_id)

    # Only the loan owner or staff can view
    if not request.user.is_staff and loan.user != request.user:
        messages.error(request, "Access denied.")
        return redirect("dashboard")

    thread = loan.review_messages.select_related("sender").all()

    # Mark admin messages as read if applicant is viewing
    if not request.user.is_staff:
        thread.filter(sender_type="admin", read=False).update(read=True)
    else:
        thread.filter(sender_type="applicant", read=False).update(read=True)

    return render(request, "loans/review_thread.html", {
        "loan":   loan,
        "thread": thread,
        "is_admin": request.user.is_staff,
    })


@login_required
def user_submit_info(request, loan_id):  # admin notified on reply
    """
    Applicant submits their response to admin's info request.
    """
    from loans.models import LoanApplication, LoanReviewMessage
    from notification.utils import create_notification

    loan = get_object_or_404(LoanApplication, id=loan_id, user=request.user)

    if loan.status not in ["Info Required", "Pending"]:
        messages.error(request, "This loan is not awaiting additional information.")
        return redirect("loan_list")

    if request.method == "POST":
        response_text = request.POST.get("response_text", "").strip()
        attachment    = request.FILES.get("attachment")

        if not response_text and not attachment:
            messages.error(request, "Please provide a response or upload a document.")
            return redirect("loan_review_thread", loan_id=loan_id)

        LoanReviewMessage.objects.create(
            loan=loan,
            sender=request.user,
            sender_type="applicant",
            message=response_text or "(Document uploaded)",
            attachment=attachment,
        )

        # Move loan back to Pending for admin review
        loan.status = "Pending"
        loan.save()

        # Notify all staff
        from django.contrib.auth.models import User
        for staff in User.objects.filter(is_staff=True):
            create_notification(
                staff,
                title="Applicant Responded — Loan #{}".format(loan.id),
                message="{} submitted additional information for loan #{}.".format(loan.user.get_full_name() or loan.user.username, loan.id),
                link="/loans/admin/loan/{}/detail/".format(loan.id),
            )

        messages.success(request, "Your response has been submitted. We will review and notify you shortly.")
        return redirect("loan_review_thread", loan_id=loan_id)

    return redirect("loan_review_thread", loan_id=loan_id)

@login_required
@is_admin
def admin_reply_thread(request, loan_id):
    """Admin posts a follow-up message to the review thread."""
    from loans.models import LoanApplication, LoanReviewMessage
    from notification.utils import create_notification

    loan = get_object_or_404(LoanApplication, id=loan_id)

    if request.method == "POST":
        msg = request.POST.get("message", "").strip()
        if msg:
            LoanReviewMessage.objects.create(
                loan=loan,
                sender=request.user,
                sender_type="admin",
                message=msg,
            )
            # Keep status as Info Required so user can respond
            if loan.status not in ("Info Required",):
                loan.status = "Info Required"
                loan.save()

            create_notification(
                loan.user,
                title="New message on Loan #{}".format(loan.id),
                message="The PrimeLend team has responded to your application. Log in to view and reply.",
                link="/loans/review/{}/".format(loan.id),
            )
            # Email user
            try:
                from django.core.mail import send_mail
                from django.conf import settings
                send_mail(
                    subject="New Message — Your Loan Application #{}".format(loan.id),
                    message=(
                        "Dear {},\n\n"
                        "The PrimeLend team has sent you a new message regarding your loan application.\n\n"
                        "Message:\n{}\n\n"
                        "Log in to reply: {}/loans/review/{}/\n\n"
                        "Best regards,\nPrimeLend AI Team"
                    ).format(
                        loan.user.get_full_name() or loan.user.username,
                        msg,
                        getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000'),
                        loan.id,
                    ),
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@primelend.ai'),
                    recipient_list=[loan.user.email],
                    fail_silently=True,
                )
            except Exception:
                pass
    return redirect("loan_review_thread", loan_id=loan_id)





