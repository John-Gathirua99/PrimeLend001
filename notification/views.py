from .models import Notification
from django.shortcuts import render
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Notification
from django.core.paginator import Paginator

@login_required
def notifications(request):
    # Get user's notifications
    user_notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')

    # Mark all as read
    user_notifications.update(is_read=True)

    # Pagination: 5 notifications per page
    paginator = Paginator(user_notifications, 5)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, "notification/notifications.html", {
        'notifications': page_obj  # pass the paginated page object only
    })

@login_required
def notif_redirect(request, notif_id):
    from .models import Notification
    notif = get_object_or_404(Notification, id=notif_id, user=request.user)
    notif.is_read = True
    notif.save()
    if notif.link:
        return redirect(notif.link)
    return redirect("notifications")
