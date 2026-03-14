from django.apps import AppConfig

class WalletConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'wallet'

    def ready(self):
        import wallet.signals
        # DB setup moved to post_migrate signal to avoid startup query errors
