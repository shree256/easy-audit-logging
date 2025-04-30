default_app_config = "easy_logging.apps.EasyLoggingConfig"

from easy_logging.utils import (
    get_console_formatter,
    get_json_file_formatter,
    get_json_file_handler,
)

__all__ = [
    "get_console_formatter",
    "get_json_file_formatter",
    "get_json_file_handler",
]
