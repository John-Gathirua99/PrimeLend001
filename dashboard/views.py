
from loans.models import LoanApplication

from django.shortcuts import render, get_object_or_404


from notification.models import Notification

from django.contrib.auth.decorators import login_required


from django.shortcuts import render
from loans.models import LoanApplication


def loan_detail(request, loan_id):
    loan = get_object_or_404(LoanApplication, id=loan_id, user=request.user)
    return render(request, 'dashboard/loan_detail.html', {'loan': loan})


@login_required
def user_dashboard(request):
    user_loans = LoanApplication.objects.filter(user=request.user)

    # Filter by GET parameter
    status_filter = request.GET.get('status')
    if status_filter:
        user_loans = user_loans.filter(status=status_filter)
    

    unread_notifications = Notification.objects.filter(
        user=request.user,
        is_read=False
    ).count()

    return render(request, 'dashboard/dashboard.html', {
        'loans': user_loans,
        'status_filter': status_filter,
        "unread_notifications": unread_notifications,
    })


def loan_detail(request, loan_id):
    loan = get_object_or_404(LoanApplication, id=loan_id, user=request.user)
    return render(request, 'dashboard/loan_detail.html', {'loan': loan})
