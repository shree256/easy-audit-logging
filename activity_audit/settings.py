import logging

from django.conf import settings


# Handles AUDIT/API level as INFO for Sentry
# Add a filter that maps AUDIT -> INFO
class AuditToSentryFilter(logging.Filter):
    def filter(self, record):
        if record.levelname in ["AUDIT", "API"]:
            # Map level so Sentry accepts it
            record.levelno = logging.INFO
            record.levelname = "INFO"
            # Add tag so you can filter in Sentry UI
            if not hasattr(record, "extra"):
                record.extra = {}
            if "tags" not in record.extra:
                record.extra["tags"] = {}
            record.extra["tags"]["log_type"] = "audit"
        return True


# Attach filter to Sentry logging handler
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    if handler.__class__.__name__.startswith("Sentry"):
        handler.addFilter(AuditToSentryFilter())

# URL patterns to exclude from logging
UNREGISTERED_URLS = [r"^/admin/", r"^/static/", r"^/favicon.ico$"]
UNREGISTERED_URLS = getattr(
    settings, "AUDIT_UNREGISTERED_URLS_DEFAULT", UNREGISTERED_URLS
)
UNREGISTERED_URLS.extend(getattr(settings, "AUDIT_UNREGISTERED_URLS_EXTRA", []))

# URL patterns to include in logging (if empty, all URLs are logged)
REGISTERED_URLS = getattr(settings, "AUDIT_REGISTERED_URLS", [])

# Service name for audit logs
SERVICE_NAME = getattr(settings, "AUDIT_SERVICE_NAME", "default")
