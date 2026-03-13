

from django.apps import AppConfig
from django.utils import timezone

class LoansConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'loans'

    def ready(self):
        from loans.views import send_due_today_reminders
        try:
            send_due_today_reminders()
        except:
            pass
