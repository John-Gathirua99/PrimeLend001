from django.apps import AppConfig

class WalletConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'wallet'

    def ready(self):
        import wallet.signals
        from .models import SystemWallet
        if not SystemWallet.objects.exists():
            SystemWallet.objects.create(balance=500000)  # initial capital





