from easy_logging.constants import CONSOLE_FORMAT
from easy_logging.logger_level import API, AUDIT


def get_console_formatter() -> dict:
    return {
        "format": CONSOLE_FORMAT,
    }


def get_json_file_formatter() -> dict:
    return {
        "()": "easy_logging.formatter.JsonFileFormatter",
    }


def get_api_file_formatter() -> dict:
    return {
        "()": "easy_logging.formatter.APIFormatter",
    }


def get_audit_file_formatter() -> dict:
    return {
        "()": "easy_logging.formatter.AuditFormatter",
    }


def get_json_file_handler(
    level: str,
    filename: str = "easy_logs/app.log",
    formatter: str = "json",
    max_bytes: int = 1024 * 1024 * 10,
    backup_count: int = 5,
) -> dict:
    return {
        "level": level,
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": formatter,
        "filename": filename,
        "maxBytes": max_bytes,
        "backupCount": backup_count,
    }


def get_api_handler(
    filename: str = "easy_logs/api.log",
    formatter: str = "api_json",
) -> dict:
    return {
        "level": API,
        "class": "easy_logging.handlers.EasyLogHandler",
        "filename": filename,
        "maxBytes": 1024 * 1024 * 10,  # 10MB
        "backupCount": 5,
        "formatter": formatter,
    }


def get_audit_handler(
    filename: str = "easy_logs/audit.log",
    formatter: str = "audit_json",
) -> dict:
    return {
        "level": AUDIT,
        "class": "easy_logging.handlers.EasyLogHandler",
        "filename": filename,
        "maxBytes": 1024 * 1024 * 10,  # 10MB
        "backupCount": 5,
        "formatter": formatter,
    }
