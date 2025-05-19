import logging
import json
from logging.handlers import RotatingFileHandler
from .formatter import APIFormatter


class APIHandler(RotatingFileHandler):
    """Custom handler for audit.protocols logger that ensures proper formatting and validation of audit logs."""

    def __init__(
        self,
        filename,
        mode="a",
        maxBytes=0,
        backupCount=0,
        encoding=None,
        delay=False,
    ):
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)
        self.setFormatter(APIFormatter())

    def emit(self, record):
        """
        Emit a record with additional validation for audit-specific fields.
        Matches the structure from HTTPLogClient:
        {
            "timestamp": "2021-01-01 12:00:00.000",
            "level": "INFO",
            "name": "audit.protocols",
            "service_name": "default",
            "protocol": "http",
            "request_repr": {
                "endpoint": "https://example.com/api/v1/users",
                "method": "GET",
                "headers": {"Content-Type": "application/json"},
                "body": {"name": "John Doe", "email": "john.doe@example.com"},
            },
            "response_repr": {
                "status_code": 200,
                "body": {"name": "John Doe", "email": "john.doe@example.com"},
            },
            "error_message": "",
            "execution_time": 0,
        }
        """
        try:
            # Handle extra if present
            if hasattr(record, "extra"):
                for key, value in record.extra.items():
                    setattr(record, key, value)

            super().emit(record)

        except Exception as e:
            self.handleError(record)
            # Log the error to the root logger
            logging.getLogger().error(f"Error in APIHandler: {str(e)}")
