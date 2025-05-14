from easy_logging.constants import CONSOLE_FORMAT


def get_console_formatter() -> dict:
    return {
        "format": CONSOLE_FORMAT,
    }


def get_json_file_formatter() -> dict:
    return {
        "()": "easy_logging.formatter.JsonFileFormatter",
    }


def get_json_file_handler(
    level: str,
    filename: str = "audit_logs/app.log",
    max_bytes: int = 1024 * 1024 * 10,
    backup_count: int = 5,
) -> dict:
    return {
        "level": level,
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "json",
        "filename": filename,
        "maxBytes": max_bytes,
        "backupCount": backup_count,
    }
