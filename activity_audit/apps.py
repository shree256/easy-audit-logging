from django.apps import AppConfig


class AuditLoggingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "activity_audit"
    verbose_name = "Django Activity Audit"

    def ready(self):
        from . import logger_levels
        from .config import configure

        configure()

        from . import unregistered  # noqa
        from . import signals  # noqa
