from django.conf import settings

# URL patterns to exclude from logging
UNREGISTERED_URLS = [r"^/admin/", r"^/static/", r"^/favicon.ico$"]
UNREGISTERED_URLS = getattr(
    settings, "DJANGO_EASY_AUDIT_UNREGISTERED_URLS_DEFAULT", UNREGISTERED_URLS
)
UNREGISTERED_URLS.extend(
    getattr(settings, "DJANGO_EASY_AUDIT_UNREGISTERED_URLS_EXTRA", [])
)

# URL patterns to include in logging (if empty, all URLs are logged)
REGISTERED_URLS = getattr(settings, "DJANGO_EASY_AUDIT_REGISTERED_URLS", [])
