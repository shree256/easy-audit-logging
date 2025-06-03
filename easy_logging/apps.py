from django.apps import AppConfig


class EasyLoggingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "easy_logging"
    verbose_name = "Easy Audit Logging"

    def ready(self):
        # Import and register custom log levels
        from . import logger_level

        # Force registration of custom levels
        logger_level.AUDIT
        logger_level.API

        # Initialize signals
        from . import signals  # noqa
