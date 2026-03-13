from .models import Notification

def create_notification(user, title, message, link=""):
    if not user or not user.is_authenticated:
        return
    Notification.objects.create(
        user=user,
        title=title,
        message=message,
        link=link,
    )
