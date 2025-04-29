from easy_logging.constants import CONSOLE_FORMAT


def get_console_formatter() -> dict:
    return {
        "format": CONSOLE_FORMAT,
    }


def get_json_file_formatter() -> dict:
    return {
        "()": "config.settings.local.JsonFileFormatter",
    }


def get_json_file_handler(level) -> dict:
    return {
        "level": level,
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "json",
        "filename": "logs/app.log",
        "maxBytes": 1024 * 1024 * 10,  # 10MB
        "backupCount": 5,
    }
