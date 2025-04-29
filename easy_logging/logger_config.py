import logging
import datetime
import json


class JsonFileFormatter(logging.Formatter):
    def __init__(self):
        super().__init__()

    def format(self, record):
        log_data = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )[:-3],
            "level": record.levelname,
            "path": record.pathname,
            "module": record.module,
            "function": record.funcName,
            "message": record.getMessage(),
        }

        log_data["exception"] = ""
        log_data["request"] = ""

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = "{}".format(self.formatException(record.exc_info))

        # Add request info if available
        if hasattr(record, "request"):
            log_data["request"] = {
                "method": getattr(record.request, "method", None),
                "path": getattr(record.request, "path", None),
                "user": str(getattr(record.request, "user", None)),
            }

        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)
