import json
import logging
import os

import django
import pytest


def pytest_configure():
    """Configure Django settings for pytest."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.test_settings")
    django.setup()


class LogCapture(logging.Handler):
    """In-memory log handler that captures records during a test.

    When a formatter is attached (via setFormatter), each record is also
    formatted immediately on emit and stored in `formatted_outputs` as a parsed
    dict. This matters for formatters (e.g. AppFormatter) that read thread-local
    state at format time — by the time assertions run, that state may be gone.
    """

    def __init__(self):
        super().__init__(level=1)
        self.records = []
        self.formatted_outputs = []

    def emit(self, record):
        self.records.append(record)
        if self.formatter:
            try:
                self.formatted_outputs.append(json.loads(self.formatter.format(record)))
            except Exception:
                pass

    def clear(self):
        self.records.clear()
        self.formatted_outputs.clear()

    def by_event_type(self, event_type):
        return [r for r in self.records if getattr(r, "event_type", None) == event_type]

    def by_level(self, level_name):
        return [r for r in self.records if r.levelname == level_name]


@pytest.fixture
def model_log_capture():
    """Attach a capture handler to the model audit logger for the duration of a test."""
    capture = LogCapture()
    logger = logging.getLogger("audit.model")
    logger.addHandler(capture)
    yield capture
    logger.removeHandler(capture)


@pytest.fixture
def request_log_capture():
    """Attach a capture handler to the request audit logger for the duration of a test."""
    capture = LogCapture()
    logger = logging.getLogger("audit.request")
    logger.addHandler(capture)
    yield capture
    logger.removeHandler(capture)


@pytest.fixture
def app_log_capture():
    """Attach a capturing handler with AppFormatter to the app.publications logger.

    Records are formatted immediately on emit so that request_id is read from
    the thread-local while the request is still active.
    """
    from activity_audit.formatters import AppFormatter

    capture = LogCapture()
    capture.setFormatter(AppFormatter())

    logger = logging.getLogger("app.publications")
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(capture)
    yield capture
    logger.removeHandler(capture)
    logger.setLevel(previous_level)


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def author_data():
    return {
        "name": "Test Author",
        "experience": "Experienced writer with 10 years in publishing",
    }
