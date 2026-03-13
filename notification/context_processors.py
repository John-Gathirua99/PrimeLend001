from .models import Notification

def notification_count(request):
    if request.user.is_authenticated:
        unread = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()
    else:
        unread = 0

    return {"unread_notifications": unread}
