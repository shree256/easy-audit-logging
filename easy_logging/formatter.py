import logging
import datetime
import json

from .constants import CONTAINER_LOG_FILE_FORMAT


class JsonFileFormatter(logging.Formatter):
    def __init__(self, timestamp_format: str = "%Y-%m-%d %H:%M:%S.%f"):
        super().__init__()
        self.timestamp_format = timestamp_format

    def format(
        self,
        record,
    ):
        log_data = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).strftime(
                self.timestamp_format
            )[:-3],
            "level": record.levelname,
            "name": record.name,
            "path": record.pathname,
            "module": record.module,
            "function": record.funcName,
            "message": record.getMessage(),
            "exception": "",
            "request": "",
            "extra_fields": "",
        }

        # Add exception info if present for ERROR
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


class AuditFormatter(logging.Formatter):
    def __init__(self, timestamp_format: str = "%Y-%m-%d %H:%M:%S.%f"):
        super().__init__()
        self.timestamp_format = timestamp_format

    def format(self, record):
        log_data = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).strftime(
                self.timestamp_format
            )[:-3],
            "level": record.levelname,
            "name": getattr(record, "name", record.name),
            "message": record.getMessage(),
            "service_name": getattr(record, "service_name", None),
            "protocol": getattr(record, "protocol", None),
            "request_repr": getattr(record, "request_repr", None),
            "response_repr": getattr(record, "response_repr", None),
            "error_message": getattr(record, "error_message", None),
            "execution_time": getattr(record, "execution_time", None),
        }

        return json.dumps(log_data)
