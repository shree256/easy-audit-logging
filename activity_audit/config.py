import structlog

from activity_audit.shared_processors import (
    _json_default,
    _orjson_dumps,
    shared_processors,
)


class AuditBoundLogger(structlog.stdlib.BoundLogger):
    """Extends structlog BoundLogger with AUDIT, API, and LOGIN log levels."""

    def audit(self, event=None, *args, **kw):
        return self._proxy_to_logger("audit", event, *args, **kw)

    def api(self, event=None, *args, **kw):
        return self._proxy_to_logger("api", event, *args, **kw)

    def login(self, event=None, *args, **kw):
        return self._proxy_to_logger("login", event, *args, **kw)


def get_plain_formatter() -> dict:
    """
    LOGGING formatter dict that routes stdlib loggers through the structlog
    processor chain but renders as plain text instead of JSON. Use for local
    development when human-readable output is preferred over structured JSON.
    """
    return {
        "()": structlog.stdlib.ProcessorFormatter,
        "processors": [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        "foreign_pre_chain": shared_processors,
    }


def get_stdlib_formatter() -> dict:
    """
    LOGGING formatter dict that routes stdlib loggers through the structlog
    processor chain. Use for any logger that isn't a native structlog logger
    (e.g. celery, django, uvicorn).
    """
    return {
        "()": structlog.stdlib.ProcessorFormatter,
        "processors": [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(
                serializer=_orjson_dumps, default=_json_default
            ),
        ],
        "foreign_pre_chain": shared_processors,
    }


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
    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=AuditBoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> AuditBoundLogger:
    return structlog.get_logger(name)
