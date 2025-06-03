import logging
from logging.handlers import RotatingFileHandler
from .formatter import APIFormatter, AuditFormatter
from .logger_level import API, AUDIT


class EasyLogHandler(RotatingFileHandler):
    """Custom handler for audit.request logger that ensures proper formatting and validation of audit logs."""

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
        if self.level == API:
            self.setFormatter(APIFormatter())
        elif self.level == AUDIT:
            print("*" * 50)
            print("AUDIT", self.level)
            print("*" * 50)
            self.setFormatter(AuditFormatter())

    def emit(self, record):
        """
        Emit a record with additional values for audit-specific fields.
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
            logging.getLogger().error(f"Error in AuditLogHandler: {str(e)}")
