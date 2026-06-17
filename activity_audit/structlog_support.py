import datetime
import decimal
import json
import logging
import sys
import uuid

import structlog
from structlog.processors import CallsiteParameter

from activity_audit.constants import LogType


# ---------------------------------------------------------------------------
# JSON serializer — matches _json_default in formatters.py
# ---------------------------------------------------------------------------

def _json_default(obj):
    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return str(obj)


# ---------------------------------------------------------------------------
# Custom processors — match the existing formatter output field-for-field
# ---------------------------------------------------------------------------

def _audit_timestamp(logger, method, event_dict):
    """Timestamp in the same format as the existing formatters: 'YYYY-MM-DD HH:MM:SS.mmm'."""
    event_dict["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return event_dict


def _uppercase_level(logger, method, event_dict):
    """Uppercase level name to match AUDIT / API / LOGIN convention."""
    if "level" in event_dict:
        event_dict["level"] = event_dict["level"].upper()
    return event_dict


def _rename_structlog_keys(logger, method, event_dict):
    """
    Rename structlog default keys to match the existing JSON field names:
      event  → message
      logger → name
    """
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    if "logger" in event_dict:
        event_dict["name"] = event_dict.pop("logger")
    return event_dict


_LOG_TYPE_MAP = {
    "audit.model": LogType.AUDIT,
    "audit.request": LogType.API,
    "audit.login": LogType.LOGIN,
}


def _add_log_type(logger, method, event_dict):
    """Add log_type field based on logger name, matching the existing formatter convention."""
    name = event_dict.get("name", "")
    event_dict["log_type"] = _LOG_TYPE_MAP.get(name, LogType.APP)
    return event_dict


# ---------------------------------------------------------------------------
# Bound logger — adds the three custom audit levels
# ---------------------------------------------------------------------------

class AuditBoundLogger(structlog.stdlib.BoundLogger):
    """Extends structlog BoundLogger with AUDIT, API, and LOGIN log levels."""

    def audit(self, event=None, *args, **kw):
        return self._proxy_to_logger("audit", event, *args, **kw)

    def api(self, event=None, *args, **kw):
        return self._proxy_to_logger("api", event, *args, **kw)

    def login(self, event=None, *args, **kw):
        return self._proxy_to_logger("login", event, *args, **kw)


# ---------------------------------------------------------------------------
# Console handler — shared, attached once per logger
# ---------------------------------------------------------------------------

_AUDIT_LOGGERS = ("audit.model", "audit.request", "audit.login")

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(logging.Formatter("%(message)s"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def configure() -> None:
    """
    Configure structlog for console-only JSON output.

    Produces the same JSON structure as the existing AuditFormatter /
    APIFormatter / LoginFormatter — same field names, same timestamp format,
    same uppercase level names — but outputs to stdout via StreamHandler.
    No file handlers are used.

    merge_contextvars is wired in so Phase 2 (replacing thread-locals with
    structlog contextvars in middleware) only requires middleware changes;
    this function and signals.py do not need to change again.
    """
    for name in _AUDIT_LOGGERS:
        lg = logging.getLogger(name)
        if lg.level == logging.NOTSET:
            lg.setLevel(1)
        if _console_handler not in lg.handlers:
            lg.addHandler(_console_handler)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            _audit_timestamp,
            _uppercase_level,
            _rename_structlog_keys,
            _add_log_type,
            structlog.processors.CallsiteParameterAdder([
                CallsiteParameter.FILENAME,
                CallsiteParameter.LINENO,
                CallsiteParameter.FUNC_NAME,
            ]),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.ExceptionRenderer(),
            structlog.processors.JSONRenderer(default=_json_default),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=AuditBoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> AuditBoundLogger:
    return structlog.get_logger(name)
